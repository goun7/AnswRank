#!/usr/bin/env python3
"""AI gorunurluk olcum motoru — Serper API ile Google siralamasini olcer ve
akademik kanita dayali bir "AI alinti olasilik skoru" uretir.

Bu modul AnswRank'in ASIL vaadini yerine getirir: uret_rapor.py'nin
"olcmedik" dedigi kismi olcer — klinik domain'i gercek Dubai dis hekimi
sorgularinda Google'da kacinci sirada ve bu AI alinti olasiligini ne kadar
yumlakiyor.

Kullanim:
  python3 ai_gorunurluk.py example.com                  # varsayilan 5 sorgu
  python3 ai_gorunurluk.py example.com --sorgu-sayisi 3
  python3 ai_gorunurluk.py example.com --json           # sadece JSON
  python3 ai_gorunurluk.py example.com --cache-yok      # cache'i atla

KISITLAR (sert):
  - SERPER_API_KEY ASLA ekrana/log'a yazilmaz (sadece uzunlugu raporlanir).
  - Ucretsiz Serper kotasini (2500) korumak icin her sorgu 24 saat
    dosya-bazli cache'lenir; ayni sorgu tekrar istenmez.
  - Buradan SMTP/e-posta GONDERILMEZ (DM HOLD korumasi).

Akademik temel: docs/arastirma/03_rank_ve_alinti_ozeti.md
Tum agirliklar ve esikler oradaki dogrulanmis arXiv bulgularindandir.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# uret_rapor.py'nin teknik olcum fonksiyonlarini yeniden kullanıyoruz
# (HTTPS/robots/sitemap/yapilandirma) — kod tekrari yok.
from uret_rapor import robots_ve_sitemap, site_durumu, yapilandirma
from llms_txt_kontrol import llms_txt_kontrol

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DOSYASI = os.path.join(HERE, ".env")
CACHE_DIZINI = os.path.join(HERE, ".ai_gorunurluk_cache")
CACHE_TTL_SANIYE = 24 * 60 * 60  # 24 saat — ayni sorgu tekrar Serper'a gitmez

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
timeout_istek = 20

SERPER_URL = "https://google.serper.dev/search"

# ---------------------------------------------------------------------------
# Sorgu kumesi — Dubai dis klinigi icin (docs/arastirma/03, bolum 3.1)
#
# Karisim bilincli:
#   - kategori   : klasik ticari sorgular
#   - soru_formu : Xu 2026 (arXiv:2605.14021) — soru-formu sorgularda AIO
#                  aktivasyonu %64,7 (genelde %13,7)
#   - hizmet     : prosedur-odali niş sorgular
# ---------------------------------------------------------------------------
SORGU_KUMESI = {
    "kategori": [
        "dentist Dubai",
        "dental clinic Dubai",
        "best dentist Dubai",
        "teeth whitening Dubai",
        "dental implants Dubai",
    ],
    "soru_formu": [
        "who is the best dentist in Dubai",
        "where can I get dental implants in Dubai",
        "how much does teeth whitening cost in Dubai",
    ],
    "hizmet": [
        "Invisalign Dubai",
        "root canal Dubai",
        "veneers Dubai",
    ],
}

# Serper ucretsiz katmani 10 organik sonuc dondurur; "num" daha fazla
# istense de ucretsiz katmanda 10 ile sinirlidir.
SERPER_NUM = 10

# AI crawler user-agent'lari (endustri listesi; resmi olarak bu oturumda
# yalnizca PerplexityBot/Perplexity-User dogrulanabildi — docs/arastirma/02).
AI_CRAWLERLARI = {
    "GPTBot": {"sahip": "OpenAI (ChatGPT)", "dogrulandi": False},
    "Google-Extended": {"sahip": "Google (AI Overview/Gemini)", "dogrulandi": False},
    "PerplexityBot": {"sahip": "Perplexity", "dogrulandi": True},
    "CCBot": {"sahip": "Common Crawl", "dogrulandi": False},
    "anthropic-ai": {"sahip": "Anthropic (Claude)", "dogrulandi": False},
    "Bytespider": {"sahip": "ByteDance", "dogrulandi": False},
    "Applebot-Extended": {"sahip": "Apple (Apple Intelligence)", "dogrulandi": False},
}

# Kumar/Ranqo 2026 (arXiv:2606.20065): atiflarin ~%21'i "ranked best-of
# listicle" formatina gider — bu siteler birer RAKIP ve ayni zamanda giris
# FIRSATIDIR. Ust sirada listicle/aggregator varsa raporlamaliyiz.
AGGREGATOR_DOMAINLERI = (
    "whatclinic.com", "doctoruna.com", "tripadvisor.com", "google.com/maps",
    "youtube.com", "instagram.com", "linkedin.com", "facebook.com",
    "wikipedia.org", "gulfnews.com", "khaleejtimes.com", "timeoutdubai.com",
    "thedubaiclinic", "mypromedical", "health-telephone",
)
LISTICLE_DESENI = re.compile(
    r"(?i)(top\s*[\d\u0660-\u0669]+|best\s*[\d\u0660-\u0669]+|"
    r"top\s+(dental|dentist|clinic)|best\s+(dental|dentist|clinic))")

# ---------------------------------------------------------------------------
# Skor agirliklari (docs/arastirma/03, bolum 2)
#   siralama 45  — CiteChoice: rank-1 %85,1 vs rank-5 %42,8 atif
#   icerik   25  — Kai 2026: "longer, more structured, richer evidence"
#   erisim   20  — Grossman 2026: AI crawler engeli AIO'yu azaltiyor
#   rekabet  10  — Kumar 2026: nis marka %11; listicle ~%21 atif
# ---------------------------------------------------------------------------
AGIRLIK = {"siralama": 0.45, "icerik": 0.25, "erisim": 0.20, "rekabet": 0.10}


# ---------------------------------------------------------------------------
# .env okuma (send_dm.py ile ayni basit parser — dotenv bagimliligi yok)
# ---------------------------------------------------------------------------
def env_oku(yol=ENV_DOSYASI):
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


# ---------------------------------------------------------------------------
# Serper API katmani
# ---------------------------------------------------------------------------
def serper_istek(api_key, sorgu, num=SERPER_NUM):
    """Serper'a POST yapar. Hata olursa exception firlatir.

    Anahtar ASLA hata mesajina veya log'a karismaz.
    """
    govde = json.dumps({"q": sorgu, "num": num}).encode("utf-8")
    req = urllib.request.Request(
        SERPER_URL, data=govde,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_istek) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SerperHata("SERPER_API_KEY gecersiz (HTTP 401)")
        if e.code == 429:
            raise SerperHata("Serper kota siniri (HTTP 429) — ucretsiz limit")
        raise SerperHata(f"Serper HTTP {e.code}")
    except Exception as e:
        raise SerperHata(f"Serper istek hatasi: {type(e).__name__}")


class SerperHata(Exception):
    """Serper API hatalari icin (anahtar disinda hicbir veri icermez)."""


def cache_yolu(sorgu, num, cache_dizini=CACHE_DIZINI):
    """Sorgu -> deterministik cache dosya yolu (SHA-256 on-eki)."""
    h = hashlib.sha256(f"{sorgu}|{num}".encode("utf-8")).hexdigest()[:24]
    return os.path.join(cache_dizini, f"{h}.json")


def serper_ara(sorgu, api_key, num=SERPER_NUM, cache_dizini=CACHE_DIZINI,
               cache_yok=False, fetch_fn=None):
    """Cache'li Serper sorgusu.

    Dönüş: {"veri": <serper json>, "cached": bool, "kredi_kullanildi": int}
    Ayni sorgu 24 saat icinde tekrar gelirse Serper'a GITILMEZ.
    """
    fetch = fetch_fn or serper_istek
    yol = cache_yolu(sorgu, num, cache_dizini)

    if not cache_yok and os.path.exists(yol):
        yas = time.time() - os.path.getmtime(yol)
        if yas < CACHE_TTL_SANIYE:
            try:
                with open(yol, encoding="utf-8") as f:
                    return {"veri": json.load(f), "cached": True,
                            "kredi_kullanildi": 0}
            except (json.JSONDecodeError, OSError):
                pass  # bozuk cache — yeniden iste

    veri = fetch(api_key, sorgu, num)

    # Cache'e yaz (basarisiz olursa kritik degil)
    try:
        os.makedirs(cache_dizini, exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
    except OSError:
        pass

    return {"veri": veri, "cached": False, "kredi_kullanildi": 1}


# ---------------------------------------------------------------------------
# Domain esleme
# ---------------------------------------------------------------------------
def domain_normalle(link):
    """URL veya CIPLAK domain -> normalize host. www. on-ekini ve port'u kaldirir.

    Serper link'leri tam URL, bizim hedef domain'imiz ise genelde ciplak
    domain ("example.com") oldugu icin scheme eksigini tamamlar.
    """
    if not link:
        return ""
    s = str(link).strip()
    if "://" not in s:
        s = "https://" + s
    host = urllib.parse.urlparse(s).netloc.lower().split(":")[0]
    return host.removeprefix("www.")


def domain_eslesir_mi(link, hedef_domain):
    """Serper'dan gelen link hedef domain'e ait mi?

    Alt-subdomain'ler (blog.x.com) hedefe dahil sayilir.
    """
    host = domain_normalle(link)
    hedef = (hedef_domain or "").lower().strip().removeprefix("www.")
    if not host or not hedef:
        return False
    return host == hedef or host.endswith("." + hedef)


# ---------------------------------------------------------------------------
# Siralama olcumu
# ---------------------------------------------------------------------------
def sira_puani(position):
    """Google position -> 0-100 puan.

    Esikler docs/arastirma/03 bolum 2.1'den (CiteChoice arXiv:2609.15164 +
    Xu arXiv:2605.14021):
      pos 1     -> 100 (rank-1 atif %85,1)
      pos 2-3   ->  85 (AI'lerin alinti yaptigi "ust-3" bolgesi)
      pos 4-10  ->  60 (ilk sayfa)
      pos 11-20 ->  30 (sayfa-2; AIO atiflarinin ~%30'u 1. sayfada degil)
      pos 21+   ->  10
      yok       ->   0
    """
    if position is None:
        return 0
    if position <= 0:
        return 0
    if position == 1:
        return 100
    if position <= 3:
        return 85
    if position <= 10:
        return 60
    if position <= 20:
        return 30
    return 10


def organic_listesi(veri):
    """Serper yanitindan organic sonuclari normallestirir.

    Serper bazen 'position' alani vermez; eksikse 1'den baslayan sira
    numarasi uretilir (google serde sirasi zaten position sirasidir).
    """
    organic = veri.get("organic") or []
    out = []
    for i, o in enumerate(organic, start=1):
        pos = o.get("position")
        try:
            pos = int(pos) if pos is not None else i
        except (TypeError, ValueError):
            pos = i
        out.append({
            "position": pos,
            "title": o.get("title", ""),
            "link": o.get("link", ""),
            "snippet": o.get("snippet", ""),
            "domain": domain_normalle(o.get("link", "")),
        })
    out.sort(key=lambda x: x["position"])
    return out


def siralama_olc(hedef_domain, sorgular, api_key, cache_dizini=CACHE_DIZINI,
                 cache_yok=False, fetch_fn=None):
    """Her sorguda hedef domain'in sirasini bulur.

    Dönüş: {
      "sorgu_sayisi": int,
      "kredi_kullanildi": int,
      "sorgular": [ {sorgu, bulundu, position, title, link, ust10: [...] } ],
      "hatalar": [str],
    }
    """
    sorgu_sonuclari = []
    kredi = 0
    hatalar = []

    for sorgu in sorgular:
        try:
            r = serper_ara(sorgu, api_key, cache_dizini=cache_dizini,
                           cache_yok=cache_yok, fetch_fn=fetch_fn)
        except SerperHata as e:
            hatalar.append(f"{sorgu}: {e}")
            # Kota/anahtar hatasinda devam etmek anlamsiz — dur
            if "401" in str(e) or "429" in str(e):
                break
            continue

        kredi += r["kredi_kullanildi"]
        ust10 = organic_listesi(r["veri"])

        bulunan = None
        for o in ust10:
            if domain_eslesir_mi(o["link"], hedef_domain):
                bulunan = o
                break

        sorgu_sonuclari.append({
            "sorgu": sorgu,
            "bulundu": bulunan is not None,
            "position": bulunan["position"] if bulunan else None,
            "title": bulunan["title"] if bulunan else "",
            "link": bulunan["link"] if bulunan else "",
            "ust10": ust10,
        })

    return {
        "sorgu_sayisi": len(sorgu_sonuclari),
        "kredi_kullanildi": kredi,
        "sorgular": sorgu_sonuclari,
        "hatalar": hatalar,
    }


# ---------------------------------------------------------------------------
# Rakip analizi
# ---------------------------------------------------------------------------
def rakip_analizi(siralamalar, hedef_domain, en_iyi_n=10):
    """Ayni sorgularda kimler one cikiyor, hedef kacinci.

    Kumar/Ranqo 2026 gerekcesi: nis marka %11 katmaninda; atiflarin ~%21'i
    listicle'lara gider — bu yuzden "klinik kacinci" sorusu "kim one cikiyor"
    sorusundan ayrilmaz.
    """
    frekans = {}  # domain -> {"ust10_sayisi": n, "en_iyi_sira": min, "sorgular": [...]}
    for s in siralamalar:
        for o in s["ust10"][:en_iyi_n]:
            d = o["domain"]
            if not d:
                continue
            if d not in frekans:
                frekans[d] = {"ust10_sayisi": 0, "en_iyi_sira": o["position"],
                              "sorgular": []}
            f = frekans[d]
            f["ust10_sayisi"] += 1
            f["en_iyi_sira"] = min(f["en_iyi_sira"], o["position"])
            if s["sorgu"] not in f["sorgular"]:
                f["sorgular"].append(s["sorgu"])

    hedef_key = None
    hedef_norm = domain_normalle(hedef_domain)
    for d in frekans:
        if d == hedef_norm or d.endswith("." + hedef_norm):
            hedef_key = d
            break

    rakipler = sorted(
        ({"domain": d, **v} for d, v in frekans.items() if d != hedef_key),
        key=lambda x: (-x["ust10_sayisi"], x["en_iyi_sira"]))

    # Aggregator/listicle tespiti — ayni zamanda FIRSAT sinyali
    def aggregator_mu(d):
        return any(a in d for a in AGGREGATOR_DOMAINLERI)

    def listicle_mi(girdi):
        return bool(LISTICLE_DESENI.search(girdi))

    listicle_ve_aggregator = []
    for s in siralamalar:
        for o in s["ust10"][:en_iyi_n]:
            if aggregator_mu(o["domain"]) or listicle_mi(o["title"]):
                listicle_ve_aggregator.append({
                    "domain": o["domain"], "title": o["title"],
                    "position": o["position"], "sorgu": s["sorgu"],
                    "tur": "aggregator" if aggregator_mu(o["domain"]) else "listicle",
                })

    return {
        "hedef_domain": hedef_key or hedef_norm,
        "rakipler": rakipler[:10],
        "toplam_rakip_domain": len(rakipler),
        "listicle_ve_aggregator": listicle_ve_aggregator[:10],
        "listicle_firsati_var": bool(listicle_ve_aggregator),
    }


# ---------------------------------------------------------------------------
# Icerik derinligi (Kai 2026 + Vishwakarma 2026)
# ---------------------------------------------------------------------------
def kelime_sayisi(govde):
    """HTML etiketlerini soyup metin uzunlugunu sayar."""
    metin = re.sub(r"<script.*?</script>", " ", govde, flags=re.S | re.I)
    metin = re.sub(r"<style.*?</style>", " ", metin, flags=re.S | re.I)
    metin = re.sub(r"<[^>]+>", " ", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    return len(metin.split())


def schema_turu(govde):
    """ld+json bloklarindan en spesifik schema.org tipini cikarir."""
    tipler = re.findall(
        r'"@type"\s*:\s*(?:"([^"]+)"|\[([^\]]+)\])', govde, re.I)
    bulgular = set()
    for tek, liste in tipler:
        for t in ([tek] if tek else re.findall(r'"([^"]+)"', liste)):
            bulgular.add(t.strip())
    oncelik = ["Dentist", "MedicalBusiness", "LocalBusiness", "HealthAndBeautyBusiness",
               "Organization", "WebSite", "BreadcrumbList", "FAQPage", "Person"]
    for t in oncelik:
        if t in bulgular:
            return t
    return list(bulgular)[0] if bulgular else None


def icerik_derinligi(govde, yap=None):
    """Icerik derinlik puani 0-25 (docs/arastirma/03 bolum 2.2).

    Kanit: Kai 2026 (arXiv:2604.25707) yuksek-etkili sayfalar "longer, more
    structured, semantically aligned, and richer in extractable evidence";
    Vishwakarma 2026 (arXiv:2605.25517) relevans OR >>10k.
    """
    if not govde:
        return {"puan": 0, "kelime_sayisi": 0, "schema_turu": None,
                "faq_var": False}

    kelime = kelime_sayisi(govde)
    schema = schema_turu(govde)
    faq = bool(re.search(r"(?i)(faq|frequently asked questions)", govde))

    puan = 0
    if schema in ("Dentist", "MedicalBusiness", "LocalBusiness",
                  "HealthAndBeautyBusiness"):
        puan += 8  # CiteChoice: structured rendering +0,50 atif/yanit
    if kelime > 1000:
        puan += 6
    elif kelime >= 500:
        puan += 4
    else:
        puan += 1
    if faq:
        puan += 5  # Xu: soru-formu icerik AIO %64,7
    if yap is None:
        yap = {}
    if yap.get("meta_aciklama"):
        puan += 3
    if (yap.get("title_uzunlugu") or 0) >= 30:
        puan += 3

    return {
        "puan": min(25, puan),
        "kelime_sayisi": kelime,
        "schema_turu": schema,
        "faq_var": faq,
    }


# ---------------------------------------------------------------------------
# AI erisilebilirligi — robots.txt + RFC9309 (docs/arastirma/02)
# ---------------------------------------------------------------------------
def robots_parse(metin):
    """robots.txt'i RFC9309'a gore parse eder.

    Dönüş: {"gruplar": [{"agentlar": [str], "kurallar": [{"yol": str, "izin": bool}]}],
            "hata": str|None}
    """
    if not metin or "<html" in metin[:200].lower():
        return {"gruplar": [], "hata":
                "robots.txt yok veya HTML donduruyor (parse edilemedi)"}

    gruplar = []
    mevcut_agentlar = []
    mevcut_kurallar = []

    for line in metin.splitlines():
        line = line.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()

        if key == "user-agent":
            # Arka arkaya gelen user-agent satirlari AYNI gruba aittir.
            # Aralarinda kural var onceki grubu kapat.
            if mevcut_kurallar:
                gruplar.append({"agentlar": mevcut_agentlar,
                                "kurallar": mevcut_kurallar})
                mevcut_agentlar = []
                mevcut_kurallar = []
            mevcut_agentlar.append(val.lower())
        elif key in ("allow", "disallow"):
            mevcut_kurallar.append({"yol": val, "izin": key == "allow"})

    if mevcut_agentlar or mevcut_kurallar:
        gruplar.append({"agentlar": mevcut_agentlar, "kurallar": mevcut_kurallar})

    return {"gruplar": gruplar, "hata": None}


def yol_eslesir(yol, patika):
    """RFC9309 yol eslesmesi: prefix + '*' (joker) + '$' (satir sonu)."""
    if not patika:
        # RFC9309: bos 'Disallow' yolu = hicbir seyi engelleme. Bos 'Allow'
        # teorik olarak hepsini engeller ama denetim araci icin guvenli
        # yorum: bos kurali eslesme saymiyoruz.
        return False
    yol = urllib.parse.unquote(yol)
    patika = urllib.parse.unquote(patika)
    if "*" in patika or patika.endswith("$"):
        regex = re.escape(patika)
        regex = regex.replace(r"\*", ".*").replace(r"\$", r"\Z")
        return re.match("^" + regex, yol) is not None
    return yol.startswith(patika)


def robots_engelli_mi(parse_edilmis, agent, yol="/"):
    """Agent bu yol icin engelli mi? (RFC9309: en-uzun-eslesme, esitlikte ALLOW).

    Eslesme yoksa veya kural yoksa varsayilan IZINLI (RFC9309).
    """
    gruplar = parse_edilmis.get("gruplar") or []
    # En spesifik eslesme: tam agent adi once, sonra genel '*'
    aday = None
    for g in gruplar:
        if agent.lower() in g["agentlar"]:
            aday = g
            break
    if aday is None:
        for g in gruplar:
            if "*" in g["agentlar"]:
                aday = g
                break
    if aday is None:
        return False  # group yok → izinli

    en_iyi = None
    for k in aday["kurallar"]:
        if not yol_eslesir(yol, k["yol"]):
            continue
        if en_iyi is None or len(k["yol"]) > len(en_iyi["yol"]):
            en_iyi = k
        elif len(k["yol"]) == len(en_iyi["yol"]) and k["izin"]:
            en_iyi = k  # esit uzunlukta ALLOW kazanir (RFC9309)
    if en_iyi is None:
        return False  # kural yok → izinli
    return not en_iyi["izin"]


def ai_crawler_izni(robots_metni):
    """Her bilinen AI crawler icin robots.txt izin durumu.

    Grossman 2026 (arXiv:2604.27790): Google'in AI crawler'ini engelleyen
    siteler AI Overview'da anlamli daha AZ aliniyor.
    """
    parse = robots_parse(robots_metni)
    if parse["hata"]:
        return {"parse_hatasi": parse["hata"], "crawlerlar": {}}

    return {
        "parse_hatasi": None,
        "crawlerlar": {
            agent: {
                "engelli": robots_engelli_mi(parse, agent),
                "sahip": bilgi["sahip"],
            } for agent, bilgi in AI_CRAWLERLARI.items()
        },
    }


def erisim_olce(domain, robots_metni, temel, robots_durum, llms_sonuc):
    """AI erisilebilirligi puani 0-20 (docs/arastirma/03 bolum 2.3)."""
    puan = 0
    engelli_listesi = []

    izin = ai_crawler_izni(robots_metni)
    if izin.get("parse_hatasi"):
        # robots.txt okunamadi — varsayilan izinli sayip uyar
        puan += 8
    else:
        engelli = [a for a, v in izin["crawlerlar"].items() if v["engelli"]]
        engelli_listesi = engelli
        puan += max(0, 8 - 3 * len(engelli))

    if robots_durum.get("sitemap.xml", {}).get("var"):
        puan += 4
    if temel.get("erisilebilir") and temel.get("https_var"):
        puan += 4
    if llms_sonuc.get("var") and (llms_sonuc.get("skor") or 0) >= 2:
        puan += 4  # dusuk agirlik — akademik etkisi KANITLI degil

    return {
        "puan": min(20, puan),
        "engelli_ai_crawlerlar": engelli_listesi,
        "robots_parse_hatasi": izin.get("parse_hatasi"),
    }


# ---------------------------------------------------------------------------
# Rekabet baglami puani (docs/arastirma/03 bolum 2.4)
# ---------------------------------------------------------------------------
def rekabet_puani(siralamalar, rakip_sonuc):
    """Rekabet baglami puani 0-10 (Kumar/Ranqo 2026 gerekcesi)."""
    if not siralamalar:
        return {"puan": 0, "ust10_orani": 0.0, "en_iyi_sira": None}

    ust10_sayisi = sum(1 for s in siralamalar
                       if s["bulundu"] and (s["position"] or 99) <= 10)
    oran = ust10_sayisi / len(siralamalar)
    en_iyi = min((s["position"] for s in siralamalar if s["bulundu"]),
                 default=None)

    puan = oran * 5
    if en_iyi is not None and en_iyi <= 3:
        puan += 3
    if rakip_sonuc.get("listicle_firsati_var"):
        puan += 2  # listicle'lara girmek atiflarin ~%21'ine ulasir

    return {
        "puan": min(10.0, puan),
        "ust10_orani": round(oran, 3),
        "en_iyi_sira": en_iyi,
    }


# ---------------------------------------------------------------------------
# AI alinti olasilik skoru (toplam)
# ---------------------------------------------------------------------------
def normalize(puan, maks):
    """Alt-pili 0-100 olcegine normalize eder (her alt-pil farkli maksimuma
    sahiptir: siralama 100, icerik 25, erisim 20, rekabet 10)."""
    if not maks:
        return 0.0
    return round(100.0 * max(0, min(puan, maks)) / maks, 1)


def ai_alinti_puani(siralama100, icerik100, erisim100, rekabet100):
    """4 alt-pili agirliklandirarak 0-100 toplam skoru uretir.

    Tum girisler 0-100'e NORMALIZE edilmis OLMALIDIR (bkz. normalize()).
    Agirliklar docs/arastirma/03 bolum 2.5'ten; her biri dogrulanmis
    arXiv bulgusunun gucune orantili secilmistir.
    """
    toplam = (AGIRLIK["siralama"] * siralama100
              + AGIRLIK["icerik"] * icerik100
              + AGIRLIK["erisim"] * erisim100
              + AGIRLIK["rekabet"] * rekabet100)
    return round(max(0.0, min(100.0, toplam)), 1)


def alt_puanlar(siralamalar, icerik, erisim, rekabet_sonuc):
    """Siralama alt-pil puanini uretir (0-100)."""
    if not siralamalar:
        return 0.0
    puanlar = [sira_puani(s["position"]) for s in siralamalar]
    return round(sum(puanlar) / len(puanlar), 1)


# ---------------------------------------------------------------------------
# Zorunlu uyarilar (Schulte 2026 — "Don't Measure Once")
# ---------------------------------------------------------------------------
def uret_uyarilar(siralamalar):
    """Bu uyarilar olmadan skor SUNULMAMALIDIR.

    Schulte et al. 2026 (arXiv:2604.07585): gun-gune kaynak Jaccard
    0,34-0,42 (kaynaklarin ~%65'i gun-gune degisir); ChatGPT run'larinin
    %57,8'i sifir atifla doner.
    """
    return [
        "Bu tek-cekim bir olcumdur. AI cevaplarinin kaynaklari gun-gune "
        "~%65 degisir (Schulte 2026, arXiv:2604.07585, Jaccard 0,34).",
        "Skor Google siralamasina dayali bir YORDAMAdir; ChatGPT sorgularin "
        "%57,8'inde hic atif vermez (ayni kaynak).",
        "ChatGPT/Perplexity'de dogrudan olcum icin ayri bir LLM-judge "
        "katmani gerekir — bu modul Google-SERP proxy'sidir.",
    ]


# ---------------------------------------------------------------------------
# Insan-dili rapor metni
# ---------------------------------------------------------------------------
def rapor_metni(sonuc):
    """1 sayfalik, e-postaya yapistirilabilir rapor. Duz metin."""
    d = sonuc["domain"]
    puan = sonuc["ai_alinti_puani"]
    durum = ("Yuksek" if puan >= 60 else "Orta" if puan >= 30 else "Dusuk")
    sr = sonuc["siralama"]
    rk = sonuc.get("rakip") or {}
    er = sonuc.get("erisim") or {}
    ap = sonuc.get("alt_puanlar") or {}

    satirlar = []
    satirlar.append(f"AI GORUNURLUK OLCUMU - {d}")
    satirlar.append(f"AI alinti olasilik puani: {puan}/100 ({durum})")
    satirlar.append("")
    satirlar.append("NE OLCDUK (gercek Google verisi, Serper API):")
    satirlar.append(f"  - {sonuc['sorgu_sayisi']} Dubai dis hekimi sorgusu")
    if sr["sorgular"]:
        en_iyi = min((s["position"] for s in sr["sorgular"] if s["bulundu"]),
                     default=None)
        if en_iyi is not None:
            satirlar.append(f"  - En iyi siraniz: {en_iyi}")
            satirlar.append(f"  - Sorgularda ust-10'da oldugunuz oran: "
                            f"%{round((sonuc.get('rekabet') or {}).get('ust10_orani', 0) * 100)}")
        else:
            satirlar.append("  - HICBIR sorguda ilk 10'da degilsiniz")
        for s in sr["sorgular"]:
            isaret = f"#{s['position']}" if s["bulundu"] else "ilk 10 disinda"
            satirlar.append(f"    * \"{s['sorgu']}\" -> {isaret}")
    satirlar.append("")
    satirlar.append("ALT PUANLAR (0-100'e normalize, agirliklandirilmis):")
    for ad in ("siralama", "icerik", "erisim", "rekabet"):
        b = ap.get(ad) or {}
        if b:
            satirlar.append(f"  - {ad}: {b['puan']}/100 "
                            f"(agirlik %{round(b['agirlik'] * 100)})")
    satirlar.append(f"  - Icerik detay: {sonuc['icerik']['kelime_sayisi']} kelime, "
                    f"schema: {sonuc['icerik']['schema_turu'] or 'YOK'}, "
                    f"FAQ: {'var' if sonuc['icerik']['faq_var'] else 'YOK'}")
    if er.get("engelli_ai_crawlerlar"):
        satirlar.append(f"  * ENGELLI AI crawler: "
                        f"{', '.join(er['engelli_ai_crawlerlar'])} "
                        f"(AI cevaplarinda gorunmeyi azaltir — Grossman 2026)")

    if rk.get("rakipler"):
        satirlar.append("")
        satirlar.append("RAKIP ANALIZI - ayni sorgularda kimler one cikiyor:")
        for r in rk["rakipler"][:5]:
            satirlar.append(f"  - {r['domain']}: {r['ust10_sayisi']}/"
                            f"{sonuc['sorgu_sayisi']} sorguda ust-10 "
                            f"(en iyi #{r['en_iyi_sira']})")

    if rk.get("listicle_firsati_var"):
        satirlar.append("")
        satirlar.append("FIRSAT: Bu sorgularda 'en iyi dis klinikleri' listeleri "
                        "one cikıyor. AI cevaplarindaki atiflarin ~%21'i bu "
                        "listicle formatina gider (Kumar/Ranqo 2026).")
        satirlar.append("Bu listelere girmek, siralamayi yukseltmekten daha "
                        "hizli sonuc verir.")

    satirlar.append("")
    satirlar.append("OLCUM SINIRLARI (academik durustluk):")
    for u in sonuc.get("uyarilar", []):
        satirlar.append(f"  * {u}")

    return "\n".join(satirlar)


# ---------------------------------------------------------------------------
# Ana olcum — tum alt-pilleri birlestirir
# ---------------------------------------------------------------------------
def olc(domain, sorgular, api_key, cache_dizini=CACHE_DIZINI, cache_yok=False,
        fetch_fn=None, site_fetch_fn=None, llms_fetch_fn=None,
        robots_metni=None, govde=None, kaydet=True):
    """Tam AI gorunurluk olcumu. Ag uretimden ayrilmistir — testler icin
    network sonuclari disaridan verilebilir (fetch_fn/site_fetch_fn/...)."""
    domain = (domain or "").lower().strip()
    domain = domain.lstrip("https://").lstrip("http://").rstrip("/")
    domain = domain.split("/")[0]

    # 1) Siralama (Serper)
    sr = siralama_olc(domain, sorgular, api_key, cache_dizini=cache_dizini,
                      cache_yok=cache_yok, fetch_fn=fetch_fn)

    # 2) Icerik (site govdesi) — disaridan verilebilir
    if govde is None:
        site = site_durumu(domain) if site_fetch_fn is None else site_fetch_fn(domain)
        govde = site.get("govde", "")
        temel = {"erisilebilir": site.get("erisilebilir"),
                 "https_var": site.get("https")}
    else:
        temel = {"erisilebilir": True, "https_var": True}

    yap = yapilandirma(domain) if site_fetch_fn is None and govde else {}
    icerik = icerik_derinligi(govde, yap)

    # 3) Erisim — robots.txt
    if robots_metni is None:
        try:
            import urllib.request as _u
            req = _u.Request(f"https://{domain}/robots.txt", headers={"User-Agent": UA})
            with _u.urlopen(req, timeout=timeout_istek) as r:
                robots_metni = r.read().decode("utf-8", errors="replace")
        except Exception:
            robots_metni = ""
    robots_durum = robots_ve_sitemap(domain)

    # 4) llms.txt
    llms_sonuc = llms_txt_kontrol(domain, fetch_fn=llms_fetch_fn)

    erisim = erisim_olce(domain, robots_metni, temel, robots_durum, llms_sonuc)

    # 5) Rakip analizi
    rakip_sonuc = rakip_analizi(sr["sorgular"], domain)

    # 6) Alt puanlar + toplam (hepsi 0-100'e normalize edilir)
    siralama_puan = alt_puanlar(sr["sorgular"], icerik, erisim, rakip_sonuc)
    rekabet_sonuc = rekabet_puani(sr["sorgular"], rakip_sonuc)
    icerik100 = normalize(icerik["puan"], 25)
    erisim100 = normalize(erisim["puan"], 20)
    rekabet100 = normalize(rekabet_sonuc["puan"], 10)

    toplam = ai_alinti_puani(siralama_puan, icerik100, erisim100, rekabet100)

    sonuc = {
        "domain": domain,
        "sorgu_sayisi": sr["sorgu_sayisi"],
        "kredi_kullanildi": sr["kredi_kullanildi"],
        "alt_puanlar": {
            "siralama": {"puan": siralama_puan, "agirlik": AGIRLIK["siralama"],
                         "olcek": "0-100"},
            "icerik": {"puan": icerik100, "ham": icerik["puan"],
                       "agirlik": AGIRLIK["icerik"], "olcek": "0-25 -> 0-100"},
            "erisim": {"puan": erisim100, "ham": erisim["puan"],
                       "agirlik": AGIRLIK["erisim"], "olcek": "0-20 -> 0-100"},
            "rekabet": {"puan": rekabet100, "ham": rekabet_sonuc["puan"],
                        "agirlik": AGIRLIK["rekabet"], "olcek": "0-10 -> 0-100"},
        },
        "siralama": {
            "en_iyi_sira": rekabet_sonuc["en_iyi_sira"],
            "ust10_orani": rekabet_sonuc["ust10_orani"],
            "ortalama_sira_puani": siralama_puan,
            "sorgular": [{"sorgu": s["sorgu"], "bulundu": s["bulundu"],
                          "position": s["position"]} for s in sr["sorgular"]],
            "hatalar": sr["hatalar"],
        },
        "icerik": icerik,
        "erisim": erisim,
        "rakip": rakip_sonuc,
        "rekabet": rekabet_sonuc,
        "ai_alinti_puani": toplam,
        "uyarilar": uret_uyarilar(sr["sorgular"]),
    }
    if kaydet:
        olcum_kaydet(sonuc)
    return sonuc


# ---------------------------------------------------------------------------
# Olcum kalintliligi — olcumleri dosyaya kaydet/oku
# otomatik_takip.py bunu kullanarak SICAK yanitlara kisisel veri yazar.
# ---------------------------------------------------------------------------
OLCUM_DIZINI = os.path.join(HERE, "olcumler")


def olcum_kaydet(sonuc, dizin=OLCUM_DIZINI):
    """Bir olcum sonucunu olcumler/<domain>.json'a yazar (ustune yazar)."""
    try:
        os.makedirs(dizin, exist_ok=True)
        yol = os.path.join(dizin, f"{sonuc['domain']}.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False, indent=2)
        return yol
    except OSError:
        return None


def olcum_oku(domain, dizin=OLCUM_DIZINI):
    """Daha once olculmus bir sonuc okur. Yoksa None.

    otomatik_takip.py bunu kullanir — Serper'a YENIDEN gitmeden
    kayitli olcumle kisisellestirme yapar (kota korumasi).
    """
    d = (domain or "").lower().strip().removeprefix("www.")
    yol = os.path.join(dizin, f"{d}.json")
    if not os.path.exists(yol):
        return None
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def sorgu_kumesi_sec(sayi):
    """Kategori -> soru_formu -> hizmet onceligine gore N sorgu secer."""
    tum = (SORGU_KUMESI["kategori"] + SORGU_KUMESI["soru_formu"]
           + SORGU_KUMESI["hizmet"])
    return tum[:max(1, sayi)]


def main():
    ap = argparse.ArgumentParser(
        description="AI gorunurluk olcum motoru (Serper API)")
    ap.add_argument("domain", help="or. example.com")
    ap.add_argument("--sorgu-sayisi", type=int, default=5,
                    help="kac sorgu olculecek (varsayilan: 5, max 11) — "
                         "Serper ucretsiz kotasini korumak icin")
    ap.add_argument("--json", action="store_true", help="sadece JSON ciktisi")
    ap.add_argument("--cache-yok", action="store_true",
                    help="cache'i atla (Serper kota harcer)")
    a = ap.parse_args()

    env = env_oku()
    api_key = env.get("SERPER_API_KEY", "")
    if not api_key:
        print("HATA: SERPER_API_KEY .env'de yok.", file=sys.stderr)
        print("  .env'e su satiri ekleyin:", file=sys.stderr)
        print("  SERPER_API_KEY=<40 haneli anahtar>", file=sys.stderr)
        return 1

    sorgular = sorgu_kumesi_sec(a.sorgu_sayisi)

    if not a.json:
        print(f"olculuyor: {a.domain} | {len(sorgular)} sorgu ...", file=sys.stderr)

    try:
        sonuc = olc(a.domain, sorgular, api_key, cache_yok=a.cache_yok)
    except SerperHata as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    else:
        print(rapor_metni(sonuc))
        print()
        print(f"[Serper kredi kullanimi: {sonuc['kredi_kullanildi']}"
              f" | anahtar uzunlugu: {len(api_key)}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
