"""izleyici.delta dal-kesen testleri (LEED) — 2 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — ag/dosya YOK, sadece saf fonksiyonlar.
izleyici.delta._puan + izleyici.delta._alt_puanlar.
"""
import pytest

from izleyici import delta as D


# == _puan ==================================================================================

@pytest.mark.parametrize("snap", [None, {}, "", 0])
def test_puan_falsy_snap_none(snap):
    """ORTAM: falsy snapshot (None/bos/0) -> None."""
    assert D._puan(snap, "ai_alinti_puani") is None


def test_puan_alan_yok_none():
    assert D._puan({"baska": 5}, "ai_alinti_puani") is None


def test_puan_alan_none_none():
    assert D._puan({"ai_alinti_puani": None}, "ai_alinti_puani") is None


@pytest.mark.parametrize("val, beklenen", [
    (0, 0.0), (5, 5.0), (73, 73.0), (73.44, 73.4), (73.45, 73.5),
    (73.46, 73.5), (100, 100.0), (-12, -12.0), (-12.34, -12.3),
])
def test_puan_yuvarlama(val, beklenen):
    """ORTAM-OGRENDI: round(float(v), 1) IEEE-754 ikili-gosterim nedeniyle
    73.45'i 73.4 degil 73.5 yapar (banker's-rounding DEGISIK; Float yuvarlama
    production quirk'idir — Kural-5: oldugu gibi test edilir)."""
    assert D._puan({"ai_alinti_puani": val}, "ai_alinti_puani") == beklenen


@pytest.mark.parametrize("val", ["73", "73.5", " 42 "])
def test_puan_string_coerce(val):
    """ORTAM: deger string ise float() ile coercion."""
    assert D._puan({"x": val}, "x") == float(val)


def test_puan_string_gecersiz_valueerror():
    with pytest.raises(ValueError):
        D._puan({"x": "abc"}, "x")


def test_puan_donus_tipi_float():
    assert isinstance(D._puan({"x": 5}, "x"), float)


def test_puan_baska_alan_oku():
    snap = {"ai_alinti_puani": 10, "diger": 42}
    assert D._puan(snap, "diger") == 42.0


def test_puan_snap_dolu_alan_yok_none():
    snap = {"tarih": "2026-01-01", "domain": "x.com"}
    assert D._puan(snap, "ai_alinti_puani") is None


# == _alt_puanlar ===========================================================================

@pytest.mark.parametrize("snap", [None, {}, "", 0])
def test_alt_puanlar_falsy_snap_bos(snap):
    """ORTAM: falsy snapshot -> bos dict."""
    assert D._alt_puanlar(snap) == {}


def test_alt_puanlar_alan_yok_bos():
    assert D._alt_puanlar({"tarih": "x"}) == {}


def test_alt_puanlar_none_bos():
    assert D._alt_puanlar({"alt_puanlar": None}) == {}


def test_alt_puanlar_temel():
    snap = {"alt_puanlar": {"teknik": {"puan": 80}, "icerik": {"puan": 65.5}}}
    assert D._alt_puanlar(snap) == {"teknik": 80.0, "icerik": 65.5}


@pytest.mark.parametrize("val, beklenen", [
    (0, 0.0), (99.99, 100.0), (55.44, 55.4), (55.45, 55.5), (55.46, 55.5),
    (-3.2, -3.2),
])
def test_alt_puanlar_yuvarlama(val, beklenen):
    snap = {"alt_puanlar": {"a": {"puan": val}}}
    assert D._alt_puanlar(snap) == {"a": beklenen}


def test_alt_puanlar_puan_yoksa_default_sifir():
    """ORTAM: v.get('puan', 0.0) — eksik puan 0.0 sayilir."""
    assert D._alt_puanlar({"alt_puanlar": {"a": {}}}) == {"a": 0.0}


def test_alt_puanlar_string_puan_coerce():
    assert D._alt_puanlar({"alt_puanlar": {"a": {"puan": "42"}}}) == {"a": 42.0}


def test_alt_puanlar_bos_ic_dict():
    assert D._alt_puanlar({"alt_puanlar": {}}) == {}


def test_alt_puanlar_cok_anahtar():
    snap = {"alt_puanlar": {k: {"puan": i} for i, k in enumerate("abcde")}}
    out = D._alt_puanlar(snap)
    assert out == {"a": 0.0, "b": 1.0, "c": 2.0, "d": 3.0, "e": 4.0}


def test_alt_puanlar_donus_tipi():
    out = D._alt_puanlar({"alt_puanlar": {"a": {"puan": 1}}})
    assert isinstance(out, dict)
    assert all(isinstance(v, float) for v in out.values())


def test_alt_puanlar_unicode_anahtar():
    snap = {"alt_puanlar": {"teknik-altyapı": {"puan": 88.8}}}
    assert D._alt_puanlar(snap) == {"teknik-altyapı": 88.8}


def test_alt_puanlar_olcum_disi_alanlar_atlanir():
    """Sadece 'puan' anahtari okunur — diger metadata kopyalanmaz."""
    snap = {"alt_puanlar": {"a": {"puan": 5, "not": "x", "agirlik": 3}}}
    assert D._alt_puanlar(snap) == {"a": 5.0}


# == entegrasyon (hesapla ile) ===============================================================

def test_puanlar_hesapla_icinde_kullanilir():
    """ORTAM: hesapla() _puan/_alt_puanlar'i cagirir — ilk-olcumda eski=None."""
    out = D.hesapla(None, {"domain": "x.com", "tarih": "2026-01-01",
                           "ai_alinti_puani": 70,
                           "alt_puanlar": {"teknik": {"puan": 60}}})
    assert out["puan"] == {"eski": None, "yeni": 70.0, "degisim": None}
    assert out["alt_puanlar"] == {"teknik": {"eski": None, "yeni": 60.0,
                                             "degisim": None}}
    assert out["ilk_olcum"] is True


def test_puanlar_hesapla_delta_hesaplar():
    out = D.hesapla({"tarih": "2026-01-01", "ai_alinti_puani": 60,
                     "alt_puanlar": {"teknik": {"puan": 50}}},
                    {"domain": "x.com", "tarih": "2026-02-01",
                     "ai_alinti_puani": 70,
                     "alt_puanlar": {"teknik": {"puan": 65}}})
    assert out["puan"]["degisim"] == 10.0
    assert out["alt_puanlar"]["teknik"]["degisim"] == 15.0
    assert out["ilk_olcum"] is False
