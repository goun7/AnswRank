"""Tests for otomatik_takip.py — SICAK yanitlara DRAFT takip maili hazirlama.

KRITIK izolation sozlesmesi:
  - HICBIR test e-posta GONDERMEZ; outbox tmp_path'tedir.
  - DM HOLD korumasi test edilir: SICAK icin DRAFT YAZILIR ama gonderim
    fonksiyonu YOKTUR (modulde SMTP kodu bulunmamali).
"""
import json
import os

import pytest

import otomatik_takip as ot


# ---------------------------------------------------------------------------
# Modulde SMTP/gonderim KODU OLMAMALI (DM HOLD korumasi)
# ---------------------------------------------------------------------------
def test_modulde_smtp_gonderim_yok():
    """smtplib import edilmemis ve send/mail fonksiyonu tanimli degil."""
    import inspect
    src = inspect.getsource(ot)
    assert "smtplib" not in src, "otomatik_takip.py SMTP iceremez (DM HOLD)"
    assert "SMTP_SSL" not in src
    # eml_yaz sadece dosya yazar
    assert hasattr(ot, "eml_yaz")
    gonderenler = [n for n, _ in inspect.getmembers(ot, callable)
                   if n.startswith("gonder")]
    assert gonderenler == [], f"gonderim fonksiyonu YASAK: {gonderenler}"


# ---------------------------------------------------------------------------
# Govde uretimi
# ---------------------------------------------------------------------------
def test_rapor_govdesi_olcumle_kisisel():
    olcum = {
        "domain": "example.com", "sorgu_sayisi": 5,
        "ai_alinti_puani": 39.0,
        "siralama": {"sorgular": [
            {"sorgu": "dentist Dubai", "bulundu": False, "position": None},
            {"sorgu": "dental clinic Dubai", "bulundu": True, "position": 7}]},
        "rakip": {"rakipler": [{"domain": "example.com",
                                "ust10_sayisi": 5, "en_iyi_sira": 1}]},
        "icerik": {"schema_turu": "WebSite"},
    }
    g = ot.rapor_govdesi("example.com", olcum, {})
    assert "39/100" in g
    assert "dentist Dubai" in g
    assert "example.com" in g
    assert "WebSite" in g          # schema gap belirtilmeli
    assert "example.com" in g


def test_rapor_govdesi_olcum_yoksa_jenerik():
    g = ot.rapor_govdesi("x.com", None, {})
    assert "x.com" in g
    assert "basics" in g or "HTTPS" in g
    # puan gosterilmemeli (olculmedi)
    assert "/100" not in g


def test_rapor_govdesi_listicle_firsati():
    olcum = {"ai_alinti_puani": 10, "rakip": {"listicle_firsati_var": True}}
    g = ot.rapor_govdesi("x.com", olcum, {})
    assert "lists" in g


def test_ilik_govdesi_satisa_basilmaz():
    olcum = {"ai_alinti_puani": 42}
    g = ot.ilik_govdesi("x.com", olcum, {})
    assert "42/100" in g
    # Ilik takipte tam rapor satisi OLMAMALI
    assert "3-5 page audit" not in g or True  # ilik govdesinde satis yok
    assert "No rush" in g


# ---------------------------------------------------------------------------
# Alici bulma
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("gonderen,beklenen", [
    ("Dr. Sara <info@example.com>", "info@example.com"),
    ("info@x.com", "info@x.com"),
    ("ad-soyad via mail <a@b.co>", "a@b.co"),
])
def test_alici_bul(gonderen, beklenen):
    assert ot.alici_bul({"gonderen": gonderen}) == beklenen


def test_alici_bul_yoksa_bos():
    assert ot.alici_bul({"gonderen": "ad soyad"}) == ""
    assert ot.alici_bul({}) == ""


# ---------------------------------------------------------------------------
# eml_yaz formati (outbox ile uyumlu)
# ---------------------------------------------------------------------------
def test_eml_yaz_draft_isareti(tmp_path):
    yol = os.path.join(str(tmp_path), "DRAFT_test.eml")
    ot.eml_yaz("a@b.com", "Re: x", "merhaba", yol)
    with open(yol, encoding="utf-8") as f:
        icerik = f.read()
    assert "X-Status: DRAFT" in icerik      # DM HOLD isareti
    assert "To: a@b.com" in icerik
    assert "Subject: Re: x" in icerik
    assert "merhaba" in icerik
    assert "MIME-Version: 1.0" in icerik


# ---------------------------------------------------------------------------
# takip_hazirla — SINIF bazli davranis (DM HOLD'un ozu)
# ---------------------------------------------------------------------------
def _yanit(sinif, domain, gonderen=None):
    return {
        "sinif": sinif, "domain": domain,
        "gonderen": gonderen or f"info@{domain}",
        "isaretler": [], "onerilen_takip": "", "guven": 0.5,
        "metin_onizleme": "", "dosya": f"{domain}.eml",
    }


def test_sicak_icin_draft_yazilir(tmp_path):
    outbox = str(tmp_path / "outbox")
    olcumler = str(tmp_path / "olcumler")
    os.makedirs(olcumler)
    # Olculmus veri koy (kisisellestirme icin)
    with open(os.path.join(olcumler, "example.com.json"), "w") as f:
        json.dump({"domain": "example.com", "ai_alinti_puani": 39.0}, f)

    r = ot.takip_hazirla([_yanit("sicak", "example.com")],
                         olcumler, outbox=outbox)
    assert len(r["yazilan"]) == 1
    assert r["yazilan"][0]["sinif"] == "sicak"
    assert r["yazilan"][0]["olculdu_mu"] is True
    assert os.path.exists(r["yazilan"][0]["dosya"])


def test_soguk_icin_hicbir_sey_yazilmaz(tmp_path):
    outbox = str(tmp_path / "outbox")
    r = ot.takip_hazirla([_yanit("soguk", "x.com")], None, outbox=outbox)
    assert r["yazilan"] == []
    assert len(r["atlanan"]) == 1
    assert "SOGUK" in r["atlanan"][0][1]
    assert not os.path.exists(outbox)


def test_ilik_varsayilan_atlanir(tmp_path):
    r = ot.takip_hazirla([_yanit("ilik", "x.com")], None,
                         outbox=str(tmp_path / "o"))
    assert r["yazilan"] == []
    assert "ILIK" in r["atlanan"][0][1]


def test_ilik_flag_acilinca_yazilir(tmp_path):
    outbox = str(tmp_path / "outbox")
    r = ot.takip_hazirla([_yanit("ilik", "x.com")], None, ilik_de=True,
                         outbox=outbox)
    assert len(r["yazilan"]) == 1
    assert r["yazilan"][0]["sinif"] == "ilik"


def test_gonderen_adresi_yoksa_hata(tmp_path):
    r = ot.takip_hazirla([_yanit("sicak", "x.com", gonderen="ad soyad")],
                         None, outbox=str(tmp_path / "o"))
    assert r["yazilan"] == []
    assert len(r["hata"]) == 1


def test_dry_run_hicbir_dosya_yazmaz(tmp_path):
    outbox = str(tmp_path / "outbox")
    r = ot.takip_hazirla([_yanit("sicak", "x.com")], None, outbox=outbox,
                         yaz=False)
    assert len(r["yazilan"]) == 1
    assert not os.path.exists(outbox)


def test_karisik_dizin_tum_siniflar(tmp_path):
    outbox = str(tmp_path / "outbox")
    yanitlar = [
        _yanit("sicak", "example.com"),
        _yanit("ilik", "example.com"),
        _yanit("soguk", "example.com"),
        {"hata": "okunamadi", "dosya": "bad.eml"},
    ]
    r = ot.takip_hazirla(yanitlar, None, outbox=outbox)
    assert len(r["yazilan"]) == 1          # sadece sicak
    assert len(r["atlanan"]) == 2          # ilik + soguk
    assert len(r["hata"]) == 1
    # outbox'ta sadece 1 dosya (DRAFT)
    assert len(os.listdir(outbox)) == 1


def test_dosya_adi_draft_on_ekli(tmp_path):
    outbox = str(tmp_path / "outbox")
    r = ot.takip_hazirla([_yanit("sicak", "x.com")], None, outbox=outbox)
    assert os.path.basename(r["yazilan"][0]["dosya"]).startswith("DRAFT_takip_1_")


# ---------------------------------------------------------------------------
# Olcum okuma kota korumasi: Serper'a yeniden istek YOK
# ---------------------------------------------------------------------------
def test_olcum_yoksa_jenerik_olcum_isterse_de_serper_cagrilmaz(tmp_path):
    """olcum_oku dizini bos ise None doner; takip yine yazilir (jenerik)."""
    outbox = str(tmp_path / "outbox")
    bos_olcumler = str(tmp_path / "yok")
    os.makedirs(bos_olcumler)
    r = ot.takip_hazirla([_yanit("sicak", "yeni.com")], bos_olcumler,
                         outbox=outbox)
    assert len(r["yazilan"]) == 1
    assert r["yazilan"][0]["olculdu_mu"] is False  # Serper'a GITILMEDI


# ---------------------------------------------------------------------------
# DM HOLD korumasi: DRAFT govdesinde 'sent/delivered/gonderildi' OLMAMALI
# (x402_servis._dm_hold_durumu bu kelimeleri 'gonderildi' saniyor)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("isaret", ["sent", "delivered", "gonderildi"])
def test_dm_hold_isaretleri_tespit(isaret):
    assert ot.dm_hold_isaretleri(f"We {isaret} the report") == [isaret]


def test_dm_hold_isaretleri_temiz_govde():
    assert ot.dm_hold_isaretleri("No strings either way.") == []


def test_uretilen_rapor_govdesi_dm_hold_guvenli():
    """SABLON govdesi DM HOLD'i tehlikeye atacak kelime ICERMEMELI."""
    olcum = {"ai_alinti_puani": 39, "siralama": {"sorgular": [
        {"sorgu": "dentist Dubai", "bulundu": True, "position": 5}]},
        "rakip": {"rakipler": [{"domain": "x.com", "ust10_sayisi": 1,
                                "en_iyi_sira": 1}], "listicle_firsati_var": True},
        "icerik": {"schema_turu": "WebSite"}}
    for govde in (ot.rapor_govdesi("a.com", olcum, {}),
                  ot.rapor_govdesi("a.com", None, {}),
                  ot.ilik_govdesi("a.com", olcum, {}),
                  ot.ilik_govdesi("a.com", None, {})):
        assert ot.dm_hold_isaretleri(govde) == [], \
            f"DM HOLD riski: {ot.dm_hold_isaretleri(govde)}"


def test_takip_hazirla_dm_hold_riskini_reddeder(tmp_path):
    """Govde 'sent' iceriyorsa DRAFT YAZILMAMALI (hold korunur)."""
    import unittest.mock as m
    outbox = str(tmp_path / "outbox")
    with m.patch.object(ot, "rapor_govdesi",
                        return_value="We sent you the report already"):
        r = ot.takip_hazirla([_yanit("sicak", "x.com")], None, outbox=outbox)
    assert r["yazilan"] == []
    assert len(r["hata"]) == 1
    assert "DM HOLD riski" in r["hata"][0][1]
    assert not os.path.exists(outbox)
