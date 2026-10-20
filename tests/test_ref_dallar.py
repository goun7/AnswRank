"""x402_servis._ref_ayir + _ref_sayac_artir + _ref_kisisel_veri_filtre
dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (FakeRequest stub, sayac-reset fixture, dis cagri YOK).
K1 ref-ayirma + K5 thread-safe sayac + K7 ETIK KAPI kisisel-veri-filtresi.
"""
import os
import sys

import pytest

# G47: sester SDK PyPI-de ( sester==0.7.5, CI-de-kurulu);
# yalnizca-yerel-gelistirme-icin yedek-yol ( CI-de-YOK).
sys.path.insert(0, os.environ.get(
    "MESH_SESTER_ROOT", "/home/gokun/projects/01_unicorn/63-Sester"))
sys.path.insert(0, ".")
os.environ.setdefault("UNPUMP_TREASURY_EOA", "0x" + "a" * 40)
os.environ.setdefault("UNPUMP_SELLER_SECRET", "test-seller-secret")
os.environ.setdefault("ANSWRANK_SELLER_SECRET", "test-answrank-secret")
try:  # G47: kardes-repo-CI-de-YOKSA-acik-gerekceyle-atla
    import x402_servis as xs  # noqa: E402
except ImportError as _g47_hatasi:
    pytest.importorskip(
        "x402_servis",
        reason=("kardes-repo-unpump bu-checkout-ta-YOK; "
                "MESH_UNPUMP_ROOT-ile-kok-verilir ( %s)"
                % _g47_hatasi))


class FakeRequest:
    def __init__(self, ref=None, headers=None):
        self._ref = ref
        self.headers = headers or {}

    @property
    def query_params(self):
        return {"ref": self._ref} if self._ref is not None else {}


@pytest.fixture()
def clear_ref(monkeypatch):
    monkeypatch.setattr(xs, "_REF_SAYACLAR", {})
    return xs._REF_SAYACLAR


# == _ref_ayir: gecerli ======================================================================

@pytest.mark.parametrize("ref", [
    "unpump-p1a-tr-01", "unpump-p1b-tr-99", "unpump-p2a-en-01",
    "unpump-p3b-en-42", "unpump-p2b-tr-50",
])
def test_gecerli_refler(clear_ref, ref):
    assert xs._ref_ayir(FakeRequest(ref)) == ref


def test_returns_str(clear_ref):
    r = xs._ref_ayir(FakeRequest("unpump-p1a-tr-01"))
    assert isinstance(r, str)


def test_strip_whitespace(clear_ref):
    assert xs._ref_ayir(FakeRequest("  unpump-p1a-tr-01  ")) == \
        "unpump-p1a-tr-01"


# == _ref_ayir: red =======================================================================

def test_missing_ref(clear_ref):
    assert xs._ref_ayir(FakeRequest()) is None


def test_none_ref(clear_ref):
    assert xs._ref_ayir(FakeRequest(None)) is None


def test_empty_ref(clear_ref):
    assert xs._ref_ayir(FakeRequest("")) is None


def test_sade_ref(clear_ref):
    assert xs._ref_ayir(FakeRequest("   ")) is None


def test_email_red(clear_ref):
    """K7: e-posta kisisel-veri — red."""
    assert xs._ref_ayir(FakeRequest("user@example.com")) is None


def test_isim_red(clear_ref):
    assert xs._ref_ayir(FakeRequest("Ahmet Yılmaz")) is None


def test_telefon_red(clear_ref):
    assert xs._ref_ayir(FakeRequest("+905551234567")) is None


def test_serbest_metin_red(clear_ref):
    assert xs._ref_ayir(FakeRequest("herhangi bir metin")) is None


@pytest.mark.parametrize("bad", [
    "unpump-p4a-tr-01", "unpump-p1c-tr-01", "unpump-p1a-de-01",
    "unpump-p1a-tr-1", "unpump-p1a-tr-001", "unpump-p1a-tr-",
    "UNPUMP-P1A-TR-01", "unpump-p1a-tr-01x", "xunpump-p1a-tr-01",
])
def test_gecersiz_format(clear_ref, bad):
    assert xs._ref_ayir(FakeRequest(bad)) is None


def test_injection_red(clear_ref):
    """uzunluk-siniri: 64-karakter ustunde."""
    long_ref = "unpump-p1a-tr-01" + "x" * 70
    assert xs._ref_ayir(FakeRequest(long_ref)) is None


def test_path_traversal_red(clear_ref):
    assert xs._ref_ayir(FakeRequest("../../etc/passwd")) is None


def test_sql_injection_red(clear_ref):
    assert xs._ref_ayir(FakeRequest("unpump-p1a-tr-01'; DROP TABLE x")) \
        is None


# == _ref_ayir: query_params hatasi ===========================================================

def test_query_params_exception(clear_ref):
    class Bad:
        @property
        def query_params(self):
            raise RuntimeError("bad")
    assert xs._ref_ayir(Bad()) is None


# == _ref_sayac_artir: temel ===================================================================

def test_deneme_artar(clear_ref):
    xs._ref_sayac_artir("unpump-p1a-tr-01", "deneme")
    assert clear_ref["unpump-p1a-tr-01"]["deneme"] == 1


def test_odeme_artar(clear_ref):
    xs._ref_sayac_artir("unpump-p1a-tr-01", "odeme")
    assert clear_ref["unpump-p1a-tr-01"]["odeme"] == 1


def test_iki_kez(clear_ref):
    xs._ref_sayac_artir("r", "deneme")
    xs._ref_sayac_artir("r", "deneme")
    assert clear_ref["r"]["deneme"] == 2


def test_her_iki_anahtar(clear_ref):
    xs._ref_sayac_artir("r", "deneme")
    xs._ref_sayac_artir("r", "odeme")
    assert clear_ref["r"] == {"deneme": 1, "odeme": 1}


def test_setdefault_sifir_baslangic(clear_ref):
    xs._ref_sayac_artir("r", "odeme")
    assert clear_ref["r"]["deneme"] == 0


def test_returns_none(clear_ref):
    assert xs._ref_sayac_artir("r", "deneme") is None


# == _ref_sayac_artir: red =====================================================================

def test_ref_none(clear_ref):
    xs._ref_sayac_artir(None, "deneme")
    assert clear_ref == {}


def test_ref_empty(clear_ref):
    xs._ref_sayac_artir("", "deneme")
    assert clear_ref == {}


def test_gecersiz_anahtar(clear_ref):
    xs._ref_sayac_artir("r", "goruntuleme")
    assert clear_ref == {}


@pytest.mark.parametrize("anahtar", ["DENEME", "Odeme", "denem", "x"])
def test_anahtar_case_sensitive(clear_ref, anahtar):
    xs._ref_sayac_artir("r", anahtar)
    assert clear_ref == {}


def test_baska_ref_ayri(clear_ref):
    xs._ref_sayac_artir("r1", "deneme")
    xs._ref_sayac_artir("r2", "deneme")
    assert clear_ref["r1"]["deneme"] == 1
    assert clear_ref["r2"]["deneme"] == 1


def test_cok_ref(clear_ref):
    for i in range(5):
        xs._ref_sayac_artir(f"ref{i}", "odeme")
    assert len(clear_ref) == 5


def test_format_disi_ref_kabul(clear_ref):
    """ORTAM: _ref_sayac_artir ref-FORMAT kontrolu YAPMAZ."""
    xs._ref_sayac_artir("serbest-metin", "deneme")
    assert clear_ref["serbest-metin"]["deneme"] == 1


# == _ref_kisisel_veri_filtre ================================================================

def test_filtre_gecerli(clear_ref):
    assert xs._ref_kisisel_veri_filtre("unpump-p1a-tr-01") == \
        "unpump-p1a-tr-01"


def test_filtre_none(clear_ref):
    assert xs._ref_kisisel_veri_filtre(None) is None


def test_filtre_empty(clear_ref):
    assert xs._ref_kisisel_veri_filtre("") is None


def test_filtre_email(clear_ref):
    assert xs._ref_kisisel_veri_filtre("a@b.com") is None


def test_filtre_isim(clear_ref):
    assert xs._ref_kisisel_veri_filtre("Mehmet") is None


def test_filtre_telefon(clear_ref):
    assert xs._ref_kisisel_veri_filtre("0555 123 45 67") is None


def test_filtre_serbest(clear_ref):
    assert xs._ref_kisisel_veri_filtre("selam") is None


def test_filtre_format_disi(clear_ref):
    assert xs._ref_kisisel_veri_filtre("unpump-p9a-tr-01") is None


# == ref_ozet ================================================================================

def test_ozet_bos(clear_ref):
    assert xs.ref_ozet() == {}


def test_ozet_goruntule(clear_ref):
    xs._ref_sayac_artir("r", "deneme")
    assert xs.ref_ozet() == {"r": {"deneme": 1, "odeme": 0}}


def test_ozet_snapshot(clear_ref):
    """ORTAM: ref_ozet kopya doner (mutasyon etkilemez)."""
    xs._ref_sayac_artir("r", "deneme")
    ozet = xs.ref_ozet()
    ozet["r"]["deneme"] = 999
    assert xs.ref_ozet()["r"]["deneme"] == 1


def test_ozet_cok_ref(clear_ref):
    xs._ref_sayac_artir("r1", "deneme")
    xs._ref_sayac_artir("r1", "odeme")
    xs._ref_sayac_artir("r2", "odeme")
    assert len(xs.ref_ozet()) == 2


# == entegrasyon (_ref_ayir -> sayac) ===========================================================

def test_ayir_sonrasi_sayac(clear_ref):
    r = xs._ref_ayir(FakeRequest("unpump-p1a-tr-01"))
    xs._ref_sayac_artir(r, "deneme")
    assert clear_ref["unpump-p1a-tr-01"]["deneme"] == 1


def test_ayir_red_sonrasi_sayac_yok(clear_ref):
    r = xs._ref_ayir(FakeRequest("email@x.com"))
    xs._ref_sayac_artir(r, "deneme")
    assert clear_ref == {}
