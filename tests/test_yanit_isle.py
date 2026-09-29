"""Tests for yanit_isle.py — e-posta yanit siniflandirma.

Isolation: HICBIR test gercek e-posta GONDERMEZ/OKUMAZ; .eml uretimi
tmp_path'te yapilir.
"""
import os

import pytest

import yanit_isle as yi


# ---------------------------------------------------------------------------
# Siniflandirma: SICAK
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metin", [
    "Yes please send the report",
    "I would like to see the report for our clinic",
    "We would like the report please",
    "Please send the report",
    "How much does the full audit cost?",
    "Pricing?",
    "Can we book a demo next week?",
    "We are definitely interested",
    "Absolutely, sounds great",
    "What's my score? How did we do?",
])
def test_sicak_tespiti(metin):
    s = yi.siniflandir(metin)
    assert s["sinif"] == "sicak", (metin, s)


# ---------------------------------------------------------------------------
# Siniflandirma: ILIK
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metin", [
    "Can you tell me more about what the audit involves? Maybe later.",
    "Forwarded this to my partner who handles marketing.",
    "Interested but we're busy right now, next quarter maybe.",
    "Yes, but not a good time at the moment.",
    "What does the full report include?",
])
def test_ilik_tespiti(metin):
    s = yi.siniflandir(metin)
    assert s["sinif"] == "ilik", (metin, s)


# ---------------------------------------------------------------------------
# Siniflandirma: SOGUK
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metin", [
    "Please unsubscribe me from this list",
    "Remove me from your mailing list",
    "No thanks, not interested",
    "We already have an SEO agency",
    "This is spam, I never signed up",
    "Do not contact me again",
    "Ok thanks",
    "",
])
def test_soguk_tespiti(metin):
    s = yi.siniflandir(metin)
    assert s["sinif"] == "soguk", (metin, s)


# ---------------------------------------------------------------------------
# Kritik: "not interested" yanlis SICAK etiket almamali
# ---------------------------------------------------------------------------
def test_not_interested_olumlu_yakalanmaz():
    """Red 'interested' kelimesini icerir ama olumlu sinyal YAKALANMAMALI."""
    s = yi.siniflandir("No thanks, not interested.")
    assert s["sinif"] == "soguk"
    assert "olumlu yanit" not in " ".join(s["isaretler"])


def test_soguk_baskin_kurali():
    """Cikis istegi her olumlu sinyali gecer."""
    s = yi.siniflandir("Yes we are interested, but please UNSUBSCRIBE us now.")
    assert s["sinif"] == "soguk"


# ---------------------------------------------------------------------------
# Skala/guven
# ---------------------------------------------------------------------------
def test_guven_0_1_arasi():
    for m in ["Yes send it", "maybe later", "no thanks", ""]:
        s = yi.siniflandir(m)
        assert 0.0 <= s["guven"] <= 1.0


def test_isaretler_insan_dili():
    """Etiketler raporda okunabilir metinler olmali."""
    s = yi.siniflandir("Yes please send the report and book a call")
    assert all(isinstance(e, str) and e.strip() for e in s["isaretler"])
    assert len(s["isaretler"]) >= 1


def test_onerilen_takip_sinifa_gore():
    sicak = yi.siniflandir("Send the report please")
    ilik = yi.siniflandir("Tell me more, maybe later")
    soguk = yi.siniflandir("Unsubscribe")
    assert "gonder" in sicak["onerilen_takip"]
    assert "GONDERME" in soguk["onerilen_takip"]
    assert ilik["onerilen_takip"] != sicak["onerilen_takip"]


# ---------------------------------------------------------------------------
# Domain cikarma
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("gonderen,beklenen", [
    ("John Smith <info@example.com>", "example.com"),
    ("info@klinik-1.example", "klinik-1.example"),
    ("x@gmail.com", "gmail.com"),
    ("", ""),
])
def test_domain_cikar(gonderen, beklenen):
    assert yi.domain_cikar(gonderen) == beklenen


def test_domain_cikar_klinik_alt_domain():
    assert yi.domain_cikar("mail@sub.example.com") == "example.com"


# ---------------------------------------------------------------------------
# .eml okuma
# ---------------------------------------------------------------------------
def _eml_yaz(tmp_path, isim, govde, gonderen="info@x.com", konu="Re: x"):
    yol = os.path.join(str(tmp_path), isim)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(f"To: a@b.com\nFrom: {gonderen}\nSubject: {konu}\n")
        f.write('Content-Type: text/plain; charset="utf-8"\n')
        f.write("Content-Transfer-Encoding: 7bit\nMIME-Version: 1.0\n\n")
        f.write(govde)
    return yol


def test_eml_oku_metni_verir(tmp_path):
    yol = _eml_yaz(tmp_path, "a.eml", "Yes please send the report")
    g, k, m, t = yi.eml_oku(yol)
    assert "Yes please send the report" in m
    assert g == "info@x.com"
    assert k == "Re: x"


def test_eml_oku_multipart(tmp_path):
    yol = os.path.join(str(tmp_path), "b.eml")
    with open(yol, "w", encoding="utf-8") as f:
        f.write('Content-Type: multipart/alternative; boundary="X"\n')
        f.write('From: info@y.com\nSubject: Re: z\nMIME-Version: 1.0\n\n')
        f.write("--X\nContent-Type: text/plain\n\nYes send it\n\n")
        f.write("--X\nContent-Type: text/html\n\n<p>Yes send it</p>\n--X--\n")
    g, k, m, t = yi.eml_oku(yol)
    assert "Yes send it" in m


def test_dizin_siniflandir_uc_sinif(tmp_path):
    _eml_yaz(tmp_path, "hot.eml", "Yes please send the report",
            gonderen="info@example.com")
    _eml_yaz(tmp_path, "warm.eml", "Tell me more, maybe later",
            gonderen="info@example.com")
    _eml_yaz(tmp_path, "cold.eml", "Unsubscribe please",
            gonderen="info@example.com")

    sonuclar = yi.dizin_siniflandir(str(tmp_path))
    assert len(sonuclar) == 3
    siniflar = {s["sinif"] for s in sonuclar}
    assert siniflar == {"sicak", "ilik", "soguk"}
    # domain'ler cikarilmis
    dom = {s["domain"] for s in sonuclar}
    assert "example.com" in dom


def test_dizin_siniflandir_bos_dizin(tmp_path):
    assert yi.dizin_siniflandir(str(tmp_path)) == []


def test_ozet_hesapla():
    sonuclar = [
        {"sinif": "sicak"}, {"sinif": "sicak"}, {"sinif": "ilik"},
        {"sinif": "soguk"}, {"hata": "okunamadi"},
    ]
    oz = yi.ozet_hesapla(sonuclar)
    assert oz == {"sicak": 2, "ilik": 1, "soguk": 1, "hata": 1}


def test_rapor_metni_siniflari_icerir(tmp_path):
    rapor = yi.rapor_metni(
        [{"sinif": "sicak", "domain": "x.com", "guven": 0.9,
          "isaretler": ["rapor istiyor"], "onerilen_takip": "gonder",
          "metin_onizleme": "Yes"}],
        {"sicak": 1, "ilik": 0, "soguk": 0, "hata": 0})
    assert "SICAK: 1" in rapor
    assert "x.com" in rapor


# ---------------------------------------------------------------------------
# Klinik listesi butunlugu (kampanya 15 klinik)
# ---------------------------------------------------------------------------
def test_klinik_listesi_15():
    assert len(yi.KLINIK_DOMAINLERI) == 15
    assert "example.com" in yi.KLINIK_DOMAINLERI
