"""yanit_isle.yanit_siniflandir_dosya dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: eml_oku + siniflandir stub (dosya okuma YOK).
"""
import sys
import types

import pytest

sys.path.insert(0, ".")
import yanit_isle as yi  # noqa: E402


class _Stub:
    def __init__(self, gonderen="Ali <ali@ornek.com>",
                 konu="Konu", metin="Merhaba, tesekkurler",
                 tarih="2026-01-01"):
        self.gonderen = gonderen
        self.konu = konu
        self.metin = metin
        self.tarih = tarih
        self.reads = []

    def eml_oku(self, yol):
        self.reads.append(yol)
        return (self.gonderen, self.konu, self.metin,
                self.tarih)

    def siniflandir(self, metin, konu, gonderen):
        return {
            "sinif": "sicak",
            "sicak_puan": 80,
            "ilik_puan": 10,
            "soguk_puan": 5,
            "guven": 0.9,
            "isaretler": ["tesekkur"],
            "onerilen_takip": "haftaya hatirlat",
        }


@pytest.fixture
def stub(monkeypatch):
    s = _Stub()
    monkeypatch.setattr(yi, "eml_oku", s.eml_oku)
    monkeypatch.setattr(yi, "siniflandir", s.siniflandir)
    return s


def _call(stub, yol="x.eml"):
    return yi.yanit_siniflandir_dosya(yol)


# -- temel ---------------------------------------------------------------------------------

def test_returns_dict(stub):
    assert isinstance(_call(stub), dict)


def test_dosya_echoed(stub):
    assert _call(stub, "ozel.eml")["dosya"] == "ozel.eml"


def test_eml_oku_called(stub):
    _call(stub, "a.eml")
    assert stub.reads == ["a.eml"]


def test_gonderen(stub):
    assert _call(stub)["gonderen"] == "Ali <ali@ornek.com>"


def test_konu(stub):
    assert _call(stub)["konu"] == "Konu"


def test_tarih(stub):
    assert _call(stub)["tarih"] == "2026-01-01"


# -- domain ---------------------------------------------------------------------------------

def test_domain_extracted(stub):
    assert _call(stub)["domain"] == "ornek.com"


def test_domain_from_plain_email(stub):
    stub.gonderen = "ali@baska.com"
    assert _call(stub)["domain"] == "baska.com"


def test_domain_empty_gonderen(stub):
    stub.gonderen = ""
    assert _call(stub)["domain"] == ""


# -- sinif / puanlar ---------------------------------------------------------------------------------

def test_sinif(stub):
    assert _call(stub)["sinif"] == "sicak"


def test_puanlar_dict(stub):
    assert isinstance(_call(stub)["puanlar"], dict)


def test_puanlar_sicak(stub):
    assert _call(stub)["puanlar"]["sicak"] == 80


def test_puanlar_ilik(stub):
    assert _call(stub)["puanlar"]["ilik"] == 10


def test_puanlar_soguk(stub):
    assert _call(stub)["puanlar"]["soguk"] == 5


def test_puanlar_three_keys(stub):
    assert set(_call(stub)["puanlar"]) == {"sicak", "ilik",
                                           "soguk"}


# -- cozum yayilimi ---------------------------------------------------------------------------------

def test_guven(stub):
    assert _call(stub)["guven"] == 0.9


def test_isaretler(stub):
    assert _call(stub)["isaretler"] == ["tesekkur"]


def test_onerilen_takip(stub):
    r = _call(stub)
    assert r["onerilen_takip"] == "haftaya hatirlat"


def test_siniflandir_receives_metin(stub, monkeypatch):
    seen = []
    monkeypatch.setattr(yi, "siniflandir",
                        lambda m, k, g: seen.append(m) or _Stub(
                            ).siniflandir(m, k, g))
    stub.metin = "OZEL-METIN"
    _call(stub)
    assert seen == ["OZEL-METIN"]


def test_siniflandir_receives_konu(stub, monkeypatch):
    seen = []
    monkeypatch.setattr(yi, "siniflandir",
                        lambda m, k, g: seen.append(k) or _Stub(
                            ).siniflandir(m, k, g))
    stub.konu = "OZEL-KONU"
    _call(stub)
    assert seen == ["OZEL-KONU"]


def test_siniflandir_receives_gonderen(stub, monkeypatch):
    seen = []
    monkeypatch.setattr(yi, "siniflandir",
                        lambda m, k, g: seen.append(g) or _Stub(
                            ).siniflandir(m, k, g))
    stub.gonderen = "a@b.com"
    _call(stub)
    assert seen == ["a@b.com"]


# -- metin_onizleme ---------------------------------------------------------------------------------

def test_metin_onizleme(stub):
    assert _call(stub)["metin_onizleme"] == \
        "Merhaba, tesekkurler"


def test_metin_onizleme_280(stub):
    stub.metin = "A" * 500
    assert len(_call(stub)["metin_onizleme"]) == 280


def test_metin_onizleme_newlines_stripped(stub):
    stub.metin = "satir1\nsatir2\nsatir3"
    assert _call(stub)["metin_onizleme"] == \
        "satir1 satir2 satir3"


def test_metin_onizleme_short(stub):
    stub.metin = "kisa"
    assert _call(stub)["metin_onizleme"] == "kisa"


# -- hata: okuma ---------------------------------------------------------------------------------

def test_eml_oku_exception(stub, monkeypatch):
    def _boom(yol):
        raise FileNotFoundError("yok")
    monkeypatch.setattr(yi, "eml_oku", _boom)
    r = _call(stub)
    assert r["hata"].startswith("okunamadi")


def test_hata_includes_type(stub, monkeypatch):
    def _boom(yol):
        raise ValueError("bad")
    monkeypatch.setattr(yi, "eml_oku", _boom)
    assert "ValueError" in _call(stub)["hata"]


def test_hata_has_dosya(stub, monkeypatch):
    def _boom(yol):
        raise ValueError("x")
    monkeypatch.setattr(yi, "eml_oku", _boom)
    assert _call(stub, "z.eml")["dosya"] == "z.eml"


def test_hata_no_gonderen_key(stub, monkeypatch):
    def _boom(yol):
        raise ValueError("x")
    monkeypatch.setattr(yi, "eml_oku", _boom)
    assert "gonderen" not in _call(stub)


# -- hata: bos metin ---------------------------------------------------------------------------------

def test_empty_metin_hata(stub):
    stub.metin = ""
    assert _call(stub)["hata"] == "bos yanit"


def test_whitespace_metin_hata(stub):
    stub.metin = "   \n\t  "
    assert _call(stub)["hata"] == "bos yanit"


def test_bos_hata_has_gonderen(stub):
    stub.metin = "  "
    assert _call(stub)["gonderen"] == "Ali <ali@ornek.com>"


def test_bos_hata_no_sinif(stub):
    stub.metin = ""
    assert "sinif" not in _call(stub)


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(stub):
    assert _call(stub) == _call(stub)


def test_two_files_two_reads(stub):
    _call(stub, "a.eml")
    _call(stub, "b.eml")
    assert stub.reads == ["a.eml", "b.eml"]


def test_keys_stable(stub):
    assert set(_call(stub)) == {
        "dosya", "gonderen", "domain", "konu", "tarih",
        "sinif", "puanlar", "guven", "isaretler",
        "onerilen_takip", "metin_onizleme"}
