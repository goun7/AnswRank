#!/usr/bin/env python3
"""Klinik için 1 sayfalık AI görünürlük denetim raporu üretir.

Kullanım:
  python3 uret_rapor.py example.com          # ekrana yazar
  python3 uret_rapor.py example.com --goster  # detaylı

Çıktı: düz metin (e-postaya yapıştırılır), insan dilinde.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

timeout_istek = 15

# BAZI siteler bot koruması (Cloudflare/WAF) yüzünden 'audit-check' gibi
# User-Agent'ları 403 Forbidden ile reddeder. Gerçek tarayıcı UA'si şart.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def site_durumu(domain):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # 3xx redirectleri urllib otomatik takip eder, ama bazıları
        # MissingSchema'a düşüyor — www varyantını deneyelim
        return e.code, ""
    except Exception:
        return None, ""


def site_durumu(domain):
    """Site gerçekten erişilebilir mi — redirect'leri de say.

    urllib bazen şema/redirect yüzünden None döner; curl yerine
    www + http varyantlarını dener.
    """
    https = f"https://{domain}"
    https_www = f"https://www.{domain}"
    http = f"http://{domain}"

    for url in (https, https_www, http):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA
            })
            with urllib.request.urlopen(req, timeout=timeout_istek) as r:
                govde = r.read().decode("utf-8", errors="replace")
                son_url = r.url
                return {
                    "erisilebilir": True,
                    "durum": r.status,
                    "https": son_url.startswith("https"),
                    "govde": govde,
                    "son_url": son_url,
                }
        except Exception:
            continue
    return {"erisilebilir": False, "durum": None, "https": False, "govde": "", "son_url": ""}


def temel_kontroller(domain):
    """Site sağlığı — teknik temel."""
    site = site_durumu(domain)
    return {
        "erisilebilir": site["erisilebilir"],
        "durum": site["durum"],
        "https_var": site["https"],
        "son_url": site["son_url"],
    }


def robots_ve_sitemap(domain):
    """robots.txt ve sitemap.xml — AI tarayıcılarına izin veriyor mu."""
    sonuc = {}
    for yol in ("robots.txt", "sitemap.xml"):
        url = f"https://{domain}/{yol}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA
            })
            with urllib.request.urlopen(req, timeout=timeout_istek) as r:
                sonuc[yol] = {"var": True, "boyut": len(r.read())}
        except Exception:
            # www varyantını dene
            url2 = f"https://www.{domain}/{yol}"
            try:
                req = urllib.request.Request(url2, headers={
                    "User-Agent": UA
                })
                with urllib.request.urlopen(req, timeout=timeout_istek) as r:
                    sonuc[yol] = {"var": True, "boyut": len(r.read())}
            except Exception:
                sonuc[yol] = {"var": False, "boyut": 0}
    return sonuc


def yapilandirma(domain):
    """Schema.org structured data — AI'nin anlamlandırdığı veri."""
    site = site_durumu(domain)
    govde = site["govde"]
    if not govde:
        return {"hata": "site okunamadi"}
    bulgular = {
        "schema_org": bool(re.search(r'application/ld\+json', govde, re.I)),
        "open_graph": bool(re.search(r'property="og:', govde, re.I)),
        "meta_aciklama": bool(re.search(r'<meta[^>]+name="description"', govde, re.I)),
        "h1_sayisi": len(re.findall(r'<h1', govde, re.I)),
    }
    m = re.search(r'<title[^>]*>(.*?)</title>', govde, re.S | re.I)
    baslik = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ""
    bulgular["title_uzunlugu"] = len(baslik)
    bulgular["title"] = baslik[:60]
    m2 = re.search(r'<html[^>]+lang="([^"]+)"', govde, re.I)
    bulgular["lang"] = m2.group(1) if m2 else "belirtilmemis"
    return bulgular


def ai_bolumu(domain, api_key, sorgu_sayisi=5, cache_yok=False):
    """AI gorunurluk olcumu — Serper ile GERCEK siralama verisi.

    ai_gorunurluk.py'i LAZY import eder (ai_gorunurluk bizi import ettigi
    icin modul-seviyesinde import circular olur).

    api_key yoksa None doner — o durumda rapor 'olcmedik' yerine
    'SERPER_API_KEY yok, olcum yapilamadi' der.
    """
    if not api_key:
        return None
    import ai_gorunurluk as ag
    sorgular = ag.sorgu_kumesi_sec(sorgu_sayisi)
    return ag.olc(domain, sorgular, api_key, cache_yok=cache_yok)


def puan_hesapla(temel, robots, yap):
    """0-100 puan. Kriterler açık ve dürüst."""
    p = 0
    if temel.get("erisilebilir"):
        p += 10
    if temel.get("https_var"):
        p += 10
    if robots["robots.txt"]["var"]:
        p += 15
    if robots["sitemap.xml"]["var"]:
        p += 15
    if yap.get("schema_org"):
        p += 15
    if yap.get("open_graph"):
        p += 10
    if yap.get("meta_aciklama"):
        p += 10
    if yap.get("h1_sayisi", 0) >= 1:
        p += 5
    if yap.get("title_uzunlugu", 0) >= 30:
        p += 5
    if yap.get("lang") not in ("belirtilmemis",):
        p += 5
    return min(100, p)


def rapor_metni(domain, temel, robots, yap, puan, ai_sonuc=None):
    """İnsani, 1 sayfalik rapor. Duz metin, e-postaya yapistirilir.

    ai_sonuc verilirse (ai_gorunurluk.olc() ciktisi) rapor GERCEK AI
    gorunurluk verisi icerir; verilmezse teknik-temel raporu olur.
    """
    durum = "İyi" if puan >= 70 else "Orta" if puan >= 40 else "Dusuk"

    satirlar = []
    satirlar.append(f"AI GORUNURLUK DENETIMI - {domain}")
    if ai_sonuc:
        satirlar.append(f"AI alinti olasilik puani: {ai_sonuc['ai_alinti_puani']}/100")
    satirlar.append(f"Teknik temel puani: {puan}/100 ({durum})")
    satirlar.append("")
    satirlar.append("Ne baktik (teknik temel):")
    satirlar.append(f"  - Site sagligi: {'erisilebilir' if temel.get('erisilebilir') else 'ERISILEMIYOR'}"
                    f"{', HTTPS var' if temel.get('https_var') else ', HTTPS YOK'}")
    satirlar.append(f"  - robots.txt: {'var' if robots['robots.txt']['var'] else 'YOK'}"
                    f"  (AI tarayicilarina izin metni)")
    satirlar.append(f"  - sitemap.xml: {'var' if robots['sitemap.xml']['var'] else 'YOK'}"
                    f"  (sitenin haritasi)")
    if "hata" in yap:
        satirlar.append(f"  - Yapilandirma: okunamadi ({yap['hata']})")
    else:
        satirlar.append(f"  - Schema.org verisi: {'var' if yap.get('schema_org') else 'YOK'}"
                        f"  (AI'nin anlamlandirdigi yapi)")
        satirlar.append(f"  - Open Graph: {'var' if yap.get('open_graph') else 'YOK'}"
                        f"  (paylasimda gorunen kart)")
        satirlar.append(f"  - Meta aciklama: {'var' if yap.get('meta_aciklama') else 'YOK'}")
        satirlar.append(f"  - Sayfa basligi (H1): {yap.get('h1_sayisi', 0)} adet")
        satirlar.append(f"  - Dil isareti: {yap.get('lang', 'belirtilmemis')}")

    # --- AI gorunurluk olcumu (ANA URUN VAADI) ---
    if ai_sonuc:
        sr = ai_sonuc["siralama"]
        rk = ai_sonuc.get("rakip") or {}
        satirlar.append("")
        satirlar.append("=" * 50)
        satirlar.append("AI GORUNURLUK OLCUMU - GERCEK VERI (Serper API)")
        satirlar.append("=" * 50)
        satirlar.append(f"{ai_sonuc['sorgu_sayisi']} Dubai dis hekimi sorgusunda"
                        " Google'da kacinci siradasiniz:")
        for s in sr["sorgular"]:
            isaret = f"#{s['position']}" if s["bulundu"] else "ilk 10'da DEGIL"
            satirlar.append(f"  * \"{s['sorgu']}\" -> {isaret}")

        if rk.get("rakipler"):
            satirlar.append("")
            satirlar.append("Ayni sorgularda one cikanlar:")
            for r in rk["rakipler"][:3]:
                satirlar.append(f"  - {r['domain']}: {r['ust10_sayisi']}/"
                                f"{ai_sonuc['sorgu_sayisi']} sorguda ust-10"
                                f" (en iyi #{r['en_iyi_sira']})")
        if rk.get("listicle_firsati_var"):
            satirlar.append("")
            satirlar.append("FIRSAT: 'en iyi dis klinikleri' listeleri bu")
            satirlar.append("sorgularda one cikiyor. AI cevaplarindaki alintilarin")
            satirlar.append("~%21'i bu listicle formatina gider (Kumar/Ranqo 2026).")
        satirlar.append("")
        satirlar.append("OLCUM SINIRLARI (akademik durustluk):")
        for u in ai_sonuc.get("uyarilar", []):
            satirlar.append(f"  * {u}")
    else:
        satirlar.append("")
        satirlar.append("AI gorunurluk olcumu YAPILAMADI (SERPER_API_KEY yok).")
        satirlar.append("Teknik temel, AI gorunurlugunu tam olcmez; ChatGPT veya")
        satirlar.append("Perplexity'de 'Dubai'de dis hekimi' diye sordugunuzda")
        satirlar.append("siteniz alinti olarak cikiyor mu — bunu olcmek icin")
        satirlar.append("Serper API anahtari gerekir.")

    # En kritik 2 eksik (teknik)
    eksikler = []
    if not robots["robots.txt"]["var"]:
        eksikler.append("robots.txt yok - AI tarayicilari sitenizi tarayamiyor")
    if not robots["sitemap.xml"]["var"]:
        eksikler.append("sitemap.xml yok - sayfalariniz bulunamiyor")
    if not (yap.get("schema_org") if "hata" not in yap else False):
        eksikler.append("Schema.org verisi yok - AI sorulara cevap verirken sizi atliyor")
    if not (yap.get("meta_aciklama") if "hata" not in yap else False):
        eksikler.append("meta aciklama yok - arama ve AI onyazilarinda bos gozukuyorsunuz")

    if eksikler:
        satirlar.append("")
        satirlar.append("En onemli 2 eksik:")
        for e in eksikler[:2]:
            satirlar.append(f"  1. {e}")
    else:
        satirlar.append("")
        satirlar.append("Teknik temeliniz tam. HTTPS, robots, sitemap, Schema.org hepsi var.")

    satirlar.append("")
    satirlar.append("Bu rapor ucretsiz. Daha derin bir denetim isterseniz")
    satirlar.append("5 gun icinde 3-5 sayfalik tam raporu gonderebiliriz.")
    return "\n".join(satirlar)


def env_oku(yol=None):
    """.env'den KEY=VALUE okur (send_dm.py ile ayni basit parser)."""
    import os
    if yol is None:
        yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env = {}
    if not os.path.exists(yol):
        return env
    with open(yol, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--goster", action="store_true", help="ham veriyi de goster")
    ap.add_argument("--sorgu-sayisi", type=int, default=5,
                    help="AI gorunurluk icin kac Google sorgusu (varsayilan 5)")
    ap.add_argument("--sadece-teknik", action="store_true",
                    help="Serper'a gitme — sadece teknik temel")
    a = ap.parse_args()
    domain = a.domain.lower().lstrip("https://").lstrip("http://").rstrip("/")
    domain = domain.split("/")[0]

    print(f"denetleniyor: {domain} ...", file=sys.stderr)
    temel = temel_kontroller(domain)
    robots = robots_ve_sitemap(domain)
    yap = yapilandirma(domain)
    puan = puan_hesapla(temel, robots, yap)

    # AI gorunurluk olcumu — SERPER_API_KEY varsa GERCEK veri
    ai_sonuc = None
    if not a.sadece_teknik:
        api_key = env_oku().get("SERPER_API_KEY", "")
        if api_key:
            try:
                ai_sonuc = ai_bolumu(domain, api_key, a.sorgu_sayisi)
            except Exception as e:
                print(f"AI gorunurluk olcumu atlandi: {type(e).__name__}: {e}",
                      file=sys.stderr)

    print(rapor_metni(domain, temel, robots, yap, puan, ai_sonuc))
    if a.goster:
        print("\n--- HAM VERI ---")
        print(json.dumps({"temel": temel, "robots": robots, "yapilandirma": yap,
                          "teknik_puan": puan,
                          "ai_gorunurluk": ai_sonuc},
                         ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
