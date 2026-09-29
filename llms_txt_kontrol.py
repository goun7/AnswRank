#!/usr/bin/env python3
"""llms.txt standardı denetimi (v2 spesifikasyonu).

llmstxt.org'un v2 standardına göre bir sitenin /llms.txt dosyasını arar,
formatını denetler ve 0-3 arası bir hazırlık skoru üretir.

Kullanım:
  python3 llms_txt_kontrol.py example.com
  python3 llms_txt_kontrol.py example.com --goster

Akademik temel: docs/arastirma/01_llms_txt_standardi.md
ÖNEMLİ: llms.txt'nin AI alıntısı üzerinde ölçülmüş bir etkisi
DOĞRULANMAMIŞTIR — bu yüzden skor bilgilendiricidir, ana görünürlük puanına
yüksek ağırlıkta katılmamalıdır.
"""
import argparse
import re
import sys
import urllib.error
import urllib.request

# Gerçek tarayıcı UA'si — bazı WAF'lar bot UA'lerini 403 ile reddeder.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

timeout_istek = 15

# llms.txt felsefesi: "small enough to fit in context". Çok büyük dosya
# standartla çelişir (docs/arastirma/01, bölüm 5).
BOYUT_ALT = 100          # byte — altında "boş/anlamlısız"
BOYUST_UST = 100_000     # byte — üstünde "felsefeye aykırı" uyarısı
BOYUT_ONERI = 50_000     # byte — önerilen üst sınır


def http_get(url, timeout=timeout_istek):
    """URL'i çeker. (durum_kodu, icerik) döner; hata olursa (None, "")."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # 404/403 vb. — durum kodunu döndür ki "yok" ile "engellendi" ayrışsın
        return e.code, ""
    except Exception:
        return None, ""


def llms_txt_cek(domain, fetch_fn=None):
    """Kök ve www varyantlarında /llms.txt arar.

    Dönüş: {"var": bool, "durum": int|None, "icerik": str, "yer": str}
    """
    fetch = fetch_fn or http_get
    for yer in (f"https://{domain}/llms.txt", f"https://www.{domain}/llms.txt"):
        durum, icerik = fetch(yer)
        if durum == 200 and icerik:
            return {"var": True, "durum": durum, "icerik": icerik, "yer": yer}
    return {"var": False, "durum": durum, "icerik": "", "yer": ""}


def llms_txt_denetle(icerik):
    """llms.txt içeriğini v2 formatına göre denetler.

    v2 spesifikasyonu (llmstxt.org, 2026-08-10):
      1. Opsiyonel BOM
      2. H1 — TEK ZORUNLU bölüm
      3. Blockquote kısa özet (önerilir)
      4. Başlıksız markdown bölümleri
      5. H2+ başlık altında markdown link listeleri
    """
    sonuc = {
        "h1_var": bool(re.search(r"^#\s+\S", icerik, re.M)),
        "blockquote_var": bool(re.search(r"^>\s*\S", icerik, re.M)),
        "h2_sayisi": len(re.findall(r"^##\s+\S", icerik, re.M)),
        # Markdown link: [metin](url)
        "link_sayisi": len(re.findall(r"\[[^\]]+\]\((?P<u>https?://[^\s)]+)\)", icerik)),
        "boyut_byte": len(icerik.encode("utf-8", errors="replace")),
        "html_gorunuyor": bool(re.search(r"<html|<!DOCTYPE", icerik[:500], re.I)),
        "bom_var": icerik.startswith("﻿"),
    }

    # BOM varsa H1 tespiti için içeriği normalize et (BOM regex'i bozabilir)
    if sonuc["bom_var"] and not sonuc["h1_var"]:
        sonuc["h1_var"] = bool(re.search(r"^#\s+\S", icerik.lstrip("﻿"), re.M))

    # Geçersiz link: http(s):// ile başlamayan [metin](...) desenleri
    tum_linkler = re.findall(r"\[[^\]]+\]\(([^)]+)\)", icerik)
    sonuc["gecersiz_link_sayisi"] = sum(
        1 for u in tum_linkler if not u.startswith(("http://", "https://")))

    # llms-full.txt işaretı (opsiyonel pozitif sinyal)
    sonuc["llms_full_isaret"] = bool(re.search(r"llms-full\.txt", icerik))

    # Boyut değerlendirmesi
    boyut = sonuc["boyut_byte"]
    if boyut < BOYUT_ALT:
        sonuc["boyut_durum"] = "bos"
    elif boyut > BOYUST_UST:
        sonuc["boyut_durum"] = "cok_buyuk"
    elif boyut > BOYUT_ONERI:
        sonuc["boyut_durum"] = "buyuk"
    else:
        sonuc["boyut_durum"] = "uygun"

    return sonuc


def llms_full_txt_cek(domain, fetch_fn=None):
    """/llms-full.txt var mı (opsiyonel, pozitif sinyal)."""
    fetch = fetch_fn or http_get
    for yer in (f"https://{domain}/llms-full.txt", f"https://www.{domain}/llms-full.txt"):
        durum, icerik = fetch(yer)
        if durum == 200 and icerik:
            return {"var": True, "boyut_byte": len(icerik.encode("utf-8", errors="replace"))}
    return {"var": False, "boyut_byte": 0}


def llms_txt_skoru(dosya, denetim):
    """0-3 arası hazırlık skoru.

    0 = yok
    1 = var ama H1 (zorunlu bölüm) eksik veya HTML döndürülüyor
    2 = var + geçerli H1
    3 = var + H1 + blockquote özet + en az 1 link bölümü (tam v2 yapısı)
    """
    if not dosya["var"]:
        return 0
    if denetim["html_gorunuyor"] or not denetim["h1_var"]:
        return 1
    if denetim["blockquote_var"] and denetim["link_sayisi"] >= 1:
        return 3
    return 2


def llms_txt_kontrol(domain, fetch_fn=None):
    """Tam llms.txt denetimi. Skor + insan-dili açıklama döner."""
    domain = (domain or "").lower().strip().lstrip("https://").lstrip("http://").rstrip("/")
    domain = domain.split("/")[0].removeprefix("www.")

    dosya = llms_txt_cek(domain, fetch_fn)
    if not dosya["var"]:
        return {
            "domain": domain,
            "var": False,
            "skor": 0,
            "durum": dosya["durum"],
            "yer": "",
            "denetim": None,
            "llms_full_txt": {"var": False, "boyut_byte": 0},
            "aciklama": "llms.txt dosyasi YOK. "
                        "Site, LLM'ler icin kendini tanitamiyor.",
            "onem_derecesi": "dusuk",  # akademik etkisi kanitli degil
        }

    denetim = llms_txt_denetle(dosya["icerik"])
    full = llms_full_txt_cek(domain, fetch_fn)
    skor = llms_txt_skoru(dosya, denetim)

    parcalar = [f"llms.txt VAR ({dosya['yer']})", f"skor: {skor}/3"]
    if denetim["html_gorunuyor"]:
        parcalar.append("UYARI: /llms.txt bir HTML sayfasi donduruyor — "
                        "sunucu yol-yeniden-yazimi yapiyor olabilir")
    if not denetim["h1_var"]:
        parcalar.append("eksik: H1 basligi (standartin TEK zorunlu bolumu)")
    if not denetim["blockquote_var"]:
        parcalar.append("eksik: blockquote ozet bolumu (onerilir)")
    if denetim["gecersiz_link_sayisi"]:
        parcalar.append(f"{denetim['gecersiz_link_sayisi']} gecersiz link formati")
    if denetim["boyut_durum"] == "cok_buyuk":
        parcalar.append(f"cok buyuk: {denetim['boyut_byte']} byte "
                        "(llms.txt 'context'e sigacak kadar kucuk' olmali)")
    if full["var"]:
        parcalar.append("llms-full.txt de VAR (derin icerik icin iyi)")
    else:
        parcalar.append("llms-full.txt YOK (opsiyonel)")

    return {
        "domain": domain,
        "var": True,
        "skor": skor,
        "durum": dosya["durum"],
        "yer": dosya["yer"],
        "denetim": denetim,
        "llms_full_txt": full,
        "aciklama": " | ".join(parcalar),
        "onem_derecesi": "dusuk",
    }


def main():
    ap = argparse.ArgumentParser(description="llms.txt v2 standardi denetimi")
    ap.add_argument("domain")
    ap.add_argument("--goster", action="store_true", help="ham veriyi de goster")
    a = ap.parse_args()

    sonuc = llms_txt_kontrol(a.domain)
    print(f"llms.txt denetimi: {sonuc['domain']}")
    print(f"  {sonuc['aciklama']}")
    if a.goster:
        import json
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
