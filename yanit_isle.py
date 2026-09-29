#!/usr/bin/env python3
"""Gelen e-posta yanitlarini niyetlerine gore siniflandirir.

Uc kategori (nihat'siz, anahtar-kelime + puan tabanli):
  SICAK  — rapor/demo/gorusme istiyor, fiyat soruyor, hizli olumlu yanit
  ILIK   - bilgi istiyor, "sonra", "belki", ekibine yonlendirmis
  SOGUK  - cikis istiyor, "ilgilenmiyorum", zaten ajansi var, tepki yok

Kullanım:
  python3 yanit_isle.py                         # yanit_gelen/*.eml
  python3 yanit_isle.py --dizin ./yanit_gelen   # baska dizin
  python3 yanit_isle.py --metin "Yes, send the report please"
  python3 yanit_isle.py --cikti yanitlar.json   # sonucu JSON'a yaz
  python3 yanit_isle.py --sadece-ekran          # dosyaya yazma

KISITLAR:
  - HICBIR e-posta GONDERILMEZ (sadece okur ve siniflandirir).
  - Ag baglantisi YOKTUR — yerel .eml dosyalarini okur.
"""
import argparse
import email
import email.utils
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VARSAYILAN_DIZIN = os.path.join(HERE, "yanit_gelen")
VARSAYILAN_CIKTI = os.path.join(HERE, "yanitlar_sonuclari.json")

# Kampanyanin gonderildigi 15 klinik (outbox'ten turetilmistir).
KLINIK_DOMAINLERI = [
    # RFC 2606 ornek alanlari — gercek klinik domain'leri yerel .kampanya_adresleri.txt'te
    "example.com", "example.net", "example.org", "test.example",
    "demo.example", "klinik-1.example", "klinik-2.example", "klinik-3.example",
    "klinik-4.example", "klinik-5.example", "klinik-6.example", "klinik-7.example",
    "klinik-8.example", "klinik-9.example", "klinik-10.example",

]

# ---------------------------------------------------------------------------
# Niyet sinyalleri — her biri (regex, puan, insan-dili etiket).
# Puanlar_keyfidir; asil karar SIGNS'in birlesimine ve SOGUK-baskin kuralina
# dayanir. Duzenli ifadeler Ingilizce yanitlar icin (Dubai kampanyasi dili).
# ---------------------------------------------------------------------------
SICAK_ISARETLER = [
    (r"(?i)(send\s+(me\s+|us\s+)?(the\s+)?(report|audit|score)"
     r"|(?:i|we)\s*(?:'d|'ll|would)?\s*(?:like|love|want)\s+(to\s+see|to\s+get|the\s+(report|audit))"
     r"|please\s+send"
     r"|want\s+(the\s+)?(full\s+|deeper\s+)?(report|audit))", 25, "rapor istiyor"),
    (r"(?i)\b(demo|meeting|zoom\s+(call|meeting)|google\s*meet|appointment|book\s+a\s+(call|slot)|get\s+on\s+a\s+call)\b", 25, "gorusme/demo istiyor"),
    # Fiyat sormak tek basina guclu satis sinyalidir — SICAK esigi kadar puan.
    (r"(?i)(how\s+much|what'?s?\s+the\s+(cost|price)|pricing|what\s+do\s+you\s+charge|what\s+are\s+your\s+(rates|fees)|cost\s+of\s+(the\s+)?(full\s+)?(audit|report))", 25, "fiyat soruyor"),
    (r"(?i)(our\s+(visibility|ranking|score|audit)|what\s+(did|does)\s+you\s+find|what'?s\s+(my|our)\s+score|how\s+did\s+we\s+(do|score))", 25, "kendi sonucunu soruyor"),
    # Guclu olumlu (kesin) — tek basina SICAK esigi kadar puan.
    (r"(?i)\b(definitely|absolutely|for\s+sure|count\s+(us|me)\s+in)\b", 25, "olumlu yanit (guclu)"),
    # "interested" sadece olumsuzlugun (not/n't/isn't) OLMADIGI yerde mild sicaktir.
    # Sabit-genislik negatif lookbehind'lar: "not interested" gibi retleri dislar.
    (r"(?i)\b(yes|sure|sounds\s+good|happy\s+to|go\s+ahead|let'?s\s+do\s+it)\b|(?<!not\s)(?<!not,\s)(?<!n't\s)(?<!n',\s)interested\b", 15, "olumlu yanit"),
    (r"(?i)(next\s+week|this\s+week|tomorrow|available\s+on|free\s+on|schedule)", 10, "zamanlama oneriyor"),
]

ILIK_ISARETLER = [
    (r"(?i)(tell\s+me\s+more|more\s+(info|information|details)|can\s+you\s+(explain|share\s+more)|what\s+does\s+(it|this|the\s+(full\s+|deeper\s+)?(report|audit))\s+(involve|include|cover)|what'?s\s+(in|included\s+in)\s+(the\s+)?(the\s+)?(full\s+)?(report|audit))", 10, "daha fazla bilgi istiyor"),
    (r"(?i)(not\s+now|maybe\s+later|next\s+(quarter|month|year)|in\s+the\s+(future|new\s+year)|bad\s+time|busy\s+(right\s+)?now|reach\s+out\s+(again|later))", 10, "sonraya birakiyor"),
    (r"(?i)(interested\s+but|sounds\s+(interesting|good)\s+but|we'?re\s+(considering|looking\s+into\s+it)|need\s+to\s+(think|check|discuss))", 10, "ilgili ama kararsiz"),
    (r"(?i)(forward(ed)?\s+(this\s+)?(to|on)|passed\s+(it\s+)?(on\s+)?to|my\s+(colleague|partner|team|manager|director|co-?founder))", 8, "ekibine yonlendirmis"),
    (r"(?i)\b(maybe|perhaps|possibly|might\s+be)\b", 8, "tereddutlu"),
]

SOGUK_ISARETLER = [
    (r"(?i)(unsubscribe|opt\s*(-|\s)?out|remove\s+(me|us|this\s+email)|stop\s+(sending|emailing|contacting)|do\s+not\s+(contact|email|send)|take\s+(me|us)\s+off)", 40, "cikis istiyor (CAN-SPAM/GDPR)"),
    (r"(?i)(not\s+interested|no\s+(thanks|thank\s+you|interest|longer)|not\s+for\s+us|decline|pass\s+on\s+this\s+one|hard\s+pass)", 30, "dogrudan red"),
    (r"(?i)(spam|scam|unsolicited|never\s+(signed\s+up|subscribed|contacted|emailed\s+me))", 35, "spam itirazi"),
    (r"(?i)(already\s+(have|use)|we\s+(already\s+)?(have|use|work\s+with)\s+(an?\s+)?(seo|agency|marketing|team|consultant)|under\s+(contract|an\s+agreement))", 20, "zaten bir cozumu var"),
]

# Tek bir sinyal bu puani gecerse SOGUK her seyi gecer (cikis istegi kutsal).
SOGUK_BASKIN_ESIK = 30
SICAK_ESIK = 25
ILIK_ESIK = 8


def isaret_bul(metin, sinyaller):
    """Metindeki sinyalleri arar. (toplam_puan, [etiketler]) dondurur."""
    puan = 0
    etiketler = []
    for desen, p, etiket in sinyaller:
        if re.search(desen, metin):
            puan += p
            etiketler.append(etiket)
    return puan, etiketler


def siniflandir(metin, konu="", gonderen=""):
    """Bir yanit metnini siniflandirir. Saf fonksiyon (test edilebilir).

    Donus: {
      "sinif": "sicak"|"ilik"|"soguk",
      "sicak_puan": int, "ilik_puan": int, "soguk_puan": int,
      "isaretler": [str],           # en guclu sinyaller (insan dili)
      "onerilen_takip": str,        # otomatik_takip.py icin yol gosterici
      "guven": float,               # 0-1 siniflandirma guveni
    }
    """
    birlesik = f"{konu}\n{metin}"

    sicak_p, sicak_e = isaret_bul(birlesik, SICAK_ISARETLER)
    ilik_p, ilik_e = isaret_bul(birlesik, ILIK_ISARETLER)
    soguk_p, soguk_e = isaret_bul(birlesik, SOGUK_ISARETLER)

    # SOGUK-baskin: cikis/ret sinyali her seyi gecer
    if soguk_p >= SOGUK_BASKIN_ESIK:
        sinif = "soguk"
        oneri = "HICBIR takip maili GONDERME — cikis/red iste"
        guven = min(1.0, soguk_p / 60.0)
    elif sicak_p >= SICAK_ESIK:
        sinif = "sicak"
        oneri = ("AI gorunurluk raporunu gonder + 24-48s icinde kisa takip; "
                 "olcum verisi varsa kisisellestir")
        guven = min(1.0, sicak_p / 50.0)
    elif ilik_p >= ILIK_ESIK:
        sinif = "ilik"
        oneri = ("3-5 gun sonra deger-odakli takip: sektor verisi + kisa ornek "
                 "rapor; satva basilma")
        guven = min(1.0, ilik_p / 25.0)
    elif sicak_p > 0:
        # Zayif olumlu sinyal ama esik altinda — ilik muamele
        sinif = "ilik"
        oneri = "Dusuk-kiyecli takip: tek cumlelik hatirlatma"
        guven = min(1.0, sicak_p / 25.0)
    else:
        sinif = "soguk"
        oneri = "Takip yok — ilgilenme sinyali yok"
        guven = 0.3

    isaretler = (soguk_e if sinif == "soguk" else
                 (sicak_e + ilik_e) or soguk_e)

    return {
        "sinif": sinif,
        "sicak_puan": sicak_p,
        "ilik_puan": ilik_p,
        "soguk_puan": soguk_p,
        "isaretler": isaretler[:6],
        "onerilen_takip": oneri,
        "guven": round(guven, 2),
    }


def domain_cikar(gonderen):
    """Gonderen e-postasindan veya bilinen klinik listesinden domain bulur."""
    if not gonderen:
        return ""
    # "Ad Soyad <info@x.com>" formatini ayikla
    m = re.search(r"<([^>]+@[^>]+)>", gonderen)
    adres = m.group(1) if m else gonderen.strip()
    m2 = re.search(r"@([\w.-]+)", adres)
    if not m2:
        return ""
    host = m2.group(1).lower().removeprefix("www.")
    # Bilinen klinik domain'lerinden biri mi?
    for k in KLINIK_DOMAINLERI:
        if host == k or host.endswith("." + k) or k in host:
            return k
    return host


def eml_oku(yol):
    """Bir .eml dosyasini okur. (gonderen, konu, metin, tarih) dondurur."""
    with open(yol, encoding="utf-8", errors="replace") as f:
        msg = email.message_from_file(f)

    metin = ""
    if msg.is_multipart():
        for parca in msg.walk():
            if parca.get_content_type() == "text/plain":
                metin += parca.get_payload(decode=True).decode(
                    "utf-8", errors="replace")
    else:
        yuk = msg.get_payload(decode=True)
        metin = yuk.decode("utf-8", errors="replace") if yuk else (
            msg.get_payload() or "")

    return (msg.get("From", ""), msg.get("Subject", ""), metin.strip(),
            msg.get("Date", ""))


def yanit_siniflandir_dosya(yol):
    """Tek bir .eml'i siniflandirir. Dönüş: sonuc dict + hata."""
    try:
        gonderen, konu, metin, tarih = eml_oku(yol)
    except Exception as e:
        return {"dosya": yol, "hata": f"okunamadi: {type(e).__name__}: {e}"}

    if not metin.strip():
        return {"dosya": yol, "hata": "bos yanit", "gonderen": gonderen}

    cozum = siniflandir(metin, konu, gonderen)
    return {
        "dosya": yol,
        "gonderen": gonderen,
        "domain": domain_cikar(gonderen),
        "konu": konu,
        "tarih": tarih,
        "sinif": cozum["sinif"],
        "puanlar": {"sicak": cozum["sicak_puan"],
                    "ilik": cozum["ilik_puan"],
                    "soguk": cozum["soguk_puan"]},
        "guven": cozum["guven"],
        "isaretler": cozum["isaretler"],
        "onerilen_takip": cozum["onerilen_takip"],
        "metin_onizleme": metin[:280].replace("\n", " "),
    }


def dizin_siniflandir(dizin):
    """Dizindeki tum .eml'leri siniflandirir."""
    sonuc = []
    for yol in sorted(glob.glob(os.path.join(dizin, "*.eml"))):
        sonuc.append(yanit_siniflandir_dosya(yol))
    return sonuc


def ozet_hesapla(sonuclar):
    oz = {"sicak": 0, "ilik": 0, "soguk": 0, "hata": 0}
    for s in sonuclar:
        if s.get("hata"):
            oz["hata"] += 1
        else:
            oz[s["sinif"]] += 1
    return oz


def rapor_metni(sonuclar, ozet):
    satirlar = ["YANIT SINIFLANDIRMA SONUCU", "=" * 40]
    satirlar.append(f"Toplam: {len(sonuclar)} yanit")
    satirlar.append(f"  SICAK: {ozet['sicak']}  ILIK: {ozet['ilik']}  "
                    f"SOGUK: {ozet['soguk']}  (hata: {ozet['hata']})")
    satirlar.append("")
    for s in sonuclar:
        if s.get("hata"):
            satirlar.append(f"[HATA] {s['dosya']}: {s['hata']}")
            continue
        satirlar.append(f"[{s['sinif'].upper()}] {s['domain'] or s['gonderen']}"
                        f"  (guven %{s['guven'] * 100:.0f})")
        if s["isaretler"]:
            satirlar.append(f"  isaretler: {', '.join(s['isaretler'])}")
        satirlar.append(f"  oneri: {s['onerilen_takip']}")
        satirlar.append(f"  onizleme: {s['metin_onizleme'][:140]}")
        satirlar.append("")
    return "\n".join(satirlar)


def main():
    ap = argparse.ArgumentParser(
        description="Gelen e-posta yanitlarini siniflandirir (sicak/ilik/soguk)")
    ap.add_argument("--dizin", default=VARSAYILAN_DIZIN,
                    help=f".eml dizini (varsayilan: {VARSAYILAN_DIZIN})")
    ap.add_argument("--metin", help="tek metni siniflandir (.eml aramaz)")
    ap.add_argument("--cikti", default=VARSAYILAN_CIKTI,
                    help="JSON cikti dosyasi")
    ap.add_argument("--sadece-ekran", action="store_true",
                    help="dosyaya yazma, sadece ekrana yaz")
    a = ap.parse_args()

    if a.metin is not None:
        cozum = siniflandir(a.metin)
        cikti = {
            "toplam_yanit": 1,
            "ozet": {k: (1 if k == cozum["sinif"] else 0)
                     for k in ("sicak", "ilik", "soguk")},
            "yanitlar": [{"metin": a.metin[:500], **cozum}],
        }
        print(json.dumps(cikti, ensure_ascii=False, indent=2))
        return 0

    if not os.path.isdir(a.dizin):
        print(f"HATA: dizin yok: {a.dizin}", file=sys.stderr)
        print("  ornek: python3 yanit_isle.py --dizin ./yanit_gelen",
              file=sys.stderr)
        return 1

    sonuclar = dizin_siniflandir(a.dizin)
    if not sonuclar:
        print(f"{a.dizin} icinde .eml yok.", file=sys.stderr)
        return 0

    ozet = ozet_hesapla(sonuclar)
    cikti = {"toplam_yanit": len(sonuclar), "ozet": ozet,
             "yanitlar": sonuclar}

    print(rapor_metni(sonuclar, ozet))
    if not a.sadece_ekran:
        try:
            with open(a.cikti, "w", encoding="utf-8") as f:
                json.dump(cikti, f, ensure_ascii=False, indent=2)
            print(f"\n[yazildi: {a.cikti}]", file=sys.stderr)
        except OSError as e:
            print(f"UYARI: cikti yazilamadi: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
