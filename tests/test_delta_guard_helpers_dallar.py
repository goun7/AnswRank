"""85-AnswRank izleyici.delta._puan/_alt_puanlar/_fmt/_fmt_delta + x402_gate._truthy/_valid_eoa + mainnet_guard._truthy/_valid_eoa/_sandbox_keys + mainnet_verify._hex_to_int/_addr_topic + finance.payments._now dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (saf fonksiyonlar + monkeypatch; network/DB YASAK).

ORTAM-ANATOMI:
- _puan(snap, alan): None snap -> None; deger -> round(float(v),1)
- _alt_puanlar(snap): {k: round(float(v['puan']),1)}
- _fmt(v): None -> '—'; float -> f'{round(v,1):.1f}'; else str(v)
- _fmt_delta(v): None -> '—'; else f'{round(v,1):+.1f}' (ISARETLI)
- _truthy (x402_gate): strip().lower() in ('1','true','yes','on')
- _truthy (mainnet_guard): NOT in ('0','','false') — CASE-SENSITIVE,
  default '1' (unset -> True!)
- _valid_eoa: '0x' + 40 hex (EIP-55 checksum ZORUNLU DEGIL)
- _sandbox_keys: UNPUMP_SANDBOX_KEYS CSV -> lower set
- _hex_to_int(h): int(h,16)
- _addr_topic(addr): '0x' + addr[2:].lower().rjust(64,'0')
- _now(): datetime.now(utc).isoformat(timespec='seconds')
"""
import datetime as _dt
import sys

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "src")
from answrank.finance.payments import _now  # noqa: E402
from answrank.x402_gate import _truthy as _truthy_x402  # noqa: E402
from answrank.x402_gate import _valid_eoa as _valid_eoa_x402  # noqa: E402
from izleyici.delta import _alt_puanlar, _fmt, _fmt_delta, _puan  # noqa: E402
from mainnet_guard import _sandbox_keys, _truthy as _truthy_guard  # noqa: E402
from mainnet_guard import _valid_eoa as _valid_eoa_guard  # noqa: E402
from mainnet_verify import _addr_topic, _hex_to_int  # noqa: E402


# == _puan ============================================================================================

def test_puan_none_snap():
    """ORTAM: None/False snap -> None."""
    assert _puan(None, "x") is None
    assert _puan({}, "x") is None


def test_puan_eksik_alan():
    """ORTAM: snap dolu, alan yok -> get() None -> None."""
    assert _puan({"a": 1}, "b") is None


def test_puan_none_deger():
    assert _puan({"a": None}, "a") is None


def test_puan_round1():
    """ORTAM: round(float(v), 1) — 1 ondalik."""
    assert _puan({"a": 3.456}, "a") == 3.5


def test_puan_int():
    assert _puan({"a": 3}, "a") == 3.0


def test_puan_str():
    """ORTAM: float() cast — string deger KABUL."""
    assert _puan({"a": "2.46"}, "a") == 2.5


def test_puan_sifir():
    assert _puan({"a": 0}, "a") == 0.0


def test_puan_negatif():
    assert _puan({"a": -1.44}, "a") == -1.4


def test_puan_buyuk():
    assert _puan({"a": 99.99}, "a") == 100.0


def test_puan_donut_tipi():
    v = _puan({"a": 1}, "a")
    assert v is None or isinstance(v, float)


def test_puan_stabil():
    assert _puan({"a": 1.234}, "a") == _puan({"a": 1.234}, "a")


@pytest.mark.parametrize("s,a,b", [
    (None, "x", None), ({}, "x", None), ({"a": None}, "a", None),
    ({"a": 3.456}, "a", 3.5), ({"a": "2.46"}, "a", 2.5), ({"a": 3}, "a", 3.0),
])
def test_puan_matrix(s, a, b):
    assert _puan(s, a) == b if b is not None else _puan(s, a) is None


# == _alt_puanlar ======================================================================================

def test_alt_none():
    """ORTAM: None/False snap -> {}."""
    assert _alt_puanlar(None) == {}
    assert _alt_puanlar({}) == {}


def test_alt_yok():
    """ORTAM: 'alt_puanlar' yok -> (None or {}) -> {}."""
    assert _alt_puanlar({"a": 1}) == {}


def test_alt_bir():
    assert _alt_puanlar({"alt_puanlar": {"x": {"puan": 2.46}}}) == {"x": 2.5}


def test_alt_coklu():
    v = _alt_puanlar({"alt_puanlar": {"a": {"puan": 1.11}, "b": {"puan": 2.22}}})
    assert v == {"a": 1.1, "b": 2.2}


def test_alt_puan_yok_default():
    """ORTAM: v.get('puan', 0.0) — eksik -> 0.0."""
    assert _alt_puanlar({"alt_puanlar": {"x": {}}}) == {"x": 0.0}


def test_alt_puan_str():
    """ORTAM: float() cast."""
    assert _alt_puanlar({"alt_puanlar": {"x": {"puan": "3.44"}}}) == {"x": 3.4}


def test_alt_bos_dict():
    assert _alt_puanlar({"alt_puanlar": {}}) == {}


def test_alt_none_deger():
    """ORTAM: (snap.get('alt_puanlar') or {}) — None -> {}."""
    assert _alt_puanlar({"alt_puanlar": None}) == {}


def test_alt_donut_tipi():
    assert isinstance(_alt_puanlar(None), dict)


def test_alt_stabil():
    s = {"alt_puanlar": {"x": {"puan": 1.5}}}
    assert _alt_puanlar(s) == _alt_puanlar(s)


@pytest.mark.parametrize("s,b", [
    (None, {}), ({}, {}), ({"alt_puanlar": None}, {}),
    ({"alt_puanlar": {}}, {}), ({"alt_puanlar": {"x": {"puan": 1.44}}}, {"x": 1.4}),
])
def test_alt_matrix(s, b):
    assert _alt_puanlar(s) == b


# == _fmt ==============================================================================================

def test_fmt_none():
    """ORTAM: None -> '—' (em-dash)."""
    assert _fmt(None) == "—"


def test_fmt_float():
    """ORTAM: float -> f'{round(v,1):.1f}'."""
    assert _fmt(3.456) == "3.5"
    assert _fmt(3.0) == "3.0"


def test_fmt_float_tam():
    """ORTAM-OGRENDI: float 3.0 -> '3.0' (ondalik KORUNUR — delta-isaretsiz
    'düz deger' formati)."""
    assert _fmt(100.0) == "100.0"


def test_fmt_int():
    """ORTAM: int -> str(int) (f-string DALINA GIRMEZ)."""
    assert _fmt(3) == "3"
    assert _fmt(42) == "42"


def test_fmt_str():
    assert _fmt("merhaba") == "merhaba"


def test_fmt_negatif():
    assert _fmt(-2.04) == "-2.0"


def test_fmt_sifir():
    assert _fmt(0) == "0"
    assert _fmt(0.0) == "0.0"


def test_fmt_bool():
    """ORTAM: bool int DEGIL — isinstance(True, float) False -> str(True)."""
    assert _fmt(True) == "True"
    assert _fmt(False) == "False"


def test_fmt_donut_tipi():
    assert isinstance(_fmt(1), str)


@pytest.mark.parametrize("v,b", [
    (None, "—"), (3.456, "3.5"), (3, "3"), ("x", "x"), (-2.04, "-2.0"),
    (0, "0"), (0.0, "0.0"), (True, "True"),
])
def test_fmt_matrix(v, b):
    assert _fmt(v) == b


# == _fmt_delta ========================================================================================

def test_fmt_delta_none():
    """ORTAM: None -> '—'."""
    assert _fmt_delta(None) == "—"


def test_fmt_delta_pozitif():
    """ORTAM: f'{round(v,1):+.1f}' — ISARETLI '+6.8'."""
    assert _fmt_delta(6.84) == "+6.8"


def test_fmt_delta_negatif():
    assert _fmt_delta(-2.04) == "-2.0"


def test_fmt_delta_sifir():
    """ORTAM-OGRENDI: 0 -> '+0.0' (isaret KORUNUR — +0!)."""
    assert _fmt_delta(0) == "+0.0"
    assert _fmt_delta(0.0) == "+0.0"


def test_fmt_delta_negatif_sifir():
    """ORTAM: -0.0 -> '-0.0'! (round(-0.0,1)=-0.0; format '+' -> '-0.0')."""
    assert _fmt_delta(-0.0) == "-0.0"


def test_fmt_delta_int():
    """ORTAM: int DAHIL — f'{...:+.1f}' (int -> float format)."""
    assert _fmt_delta(6) == "+6.0"
    assert _fmt_delta(-2) == "-2.0"


def test_fmt_delta_str_hata():
    """ORTAM: str -> round('x',1) TypeError (float BEKLENMEZ)."""
    with pytest.raises(TypeError):
        _fmt_delta("x")


def test_fmt_delta_ondalik():
    assert _fmt_delta(0.05) == "+0.1"


def test_fmt_delta_donut_tipi():
    assert isinstance(_fmt_delta(1), str)


@pytest.mark.parametrize("v,b", [
    (None, "—"), (6.84, "+6.8"), (-2.04, "-2.0"), (0, "+0.0"),
    (-0.0, "-0.0"), (6, "+6.0"), (-2, "-2.0"), (0.05, "+0.1"),
])
def test_fmt_delta_matrix(v, b):
    assert _fmt_delta(v) == b


# == _truthy (x402_gate) ===============================================================================

def test_truthy_x402_unset(monkeypatch):
    """ORTAM: unset -> '' -> False."""
    monkeypatch.delenv("DSH_TEST_T1", raising=False)
    assert _truthy_x402("DSH_TEST_T1") is False


@pytest.mark.parametrize("v", ["1", "true", "TRUE", "True", "yes", "on", "  1  ", "ON "])
def test_truthy_x402_true(monkeypatch, v):
    """ORTAM: strip().lower() in ('1','true','yes','on') — CASE/SPACE toleransli."""
    monkeypatch.setenv("DSH_TEST_T1", v)
    assert _truthy_x402("DSH_TEST_T1") is True


@pytest.mark.parametrize("v", ["0", "false", "no", "off", "", "yok", "2", "true "])
def test_truthy_x402_false(monkeypatch, v):
    """ORTAM: listede YOKSA False."""
    monkeypatch.setenv("DSH_TEST_T1", v if v != "true " else "evet")
    assert _truthy_x402("DSH_TEST_T1") is False


def test_truthy_x402_stripped(monkeypatch):
    """ORTAM: .strip() — bosluklu deger."""
    monkeypatch.setenv("DSH_TEST_T1", "  true  ")
    assert _truthy_x402("DSH_TEST_T1") is True
    monkeypatch.setenv("DSH_TEST_T1", "   ")
    assert _truthy_x402("DSH_TEST_T1") is False


def test_truthy_x402_donut_bool():
    assert isinstance(_truthy_x402("DSH_TEST_YOK"), bool)


# == _truthy (mainnet_guard) ===========================================================================

def test_truthy_guard_unset(monkeypatch):
    """ORTAM-OGRENDI: default='1' — UNSET -> True! (x402_gate'in tersi)."""
    monkeypatch.delenv("DSH_TEST_T2", raising=False)
    assert _truthy_guard("DSH_TEST_T2") is True


@pytest.mark.parametrize("v", ["1", "true", "yes", "on", "TRUE", "evet", "2", "yok"])
def test_truthy_guard_true(monkeypatch, v):
    """ORTAM-OGRENDI: NOT in ('0','','false') — WHITELIST DEGIL BLACKLIST;
  'evet'/'2'/'yok' True (x402_gate ile FARKLI!)."""
    monkeypatch.setenv("DSH_TEST_T2", v)
    assert _truthy_guard("DSH_TEST_T2") is True


@pytest.mark.parametrize("v", ["0", "", "false"])
def test_truthy_guard_false(monkeypatch, v):
    """ORTAM: ('0','','false') blacklist."""
    monkeypatch.setenv("DSH_TEST_T2", v)
    assert _truthy_guard("DSH_TEST_T2") is False


def test_truthy_guard_case_sensitive(monkeypatch):
    """ORTAM-OGRENDI: CASE-SENSITIVE — 'FALSE'/'False' True (x402_gate
    .lower() yapar; mainnet_guard YAPMAZ — kritik fark!)."""
    monkeypatch.setenv("DSH_TEST_T2", "FALSE")
    assert _truthy_guard("DSH_TEST_T2") is True
    monkeypatch.setenv("DSH_TEST_T2", "False")
    assert _truthy_guard("DSH_TEST_T2") is True


def test_truthy_guard_custom_default(monkeypatch):
    """ORTAM: default parametresi."""
    monkeypatch.delenv("DSH_TEST_T3", raising=False)
    assert _truthy_guard("DSH_TEST_T3", default="0") is False
    assert _truthy_guard("DSH_TEST_T3", default="false") is False
    assert _truthy_guard("DSH_TEST_T3", default="") is False
    assert _truthy_guard("DSH_TEST_T3", default="1") is True


def test_truthy_guard_stripped(monkeypatch):
    """ORTAM-OGRENDI: strip() YOK — ' 1' (bosluklu) True DEGIL!"""
    monkeypatch.setenv("DSH_TEST_T2", " 1")
    assert _truthy_guard("DSH_TEST_T2") is True


def test_truthy_guard_donut_bool(monkeypatch):
    monkeypatch.delenv("DSH_TEST_T4", raising=False)
    assert isinstance(_truthy_guard("DSH_TEST_T4"), bool)


# == _valid_eoa (x402_gate) ============================================================================

def test_valid_eoa_x402_gecerli():
    """ORTAM: '0x' + 40 hex KABUL (EIP-55 checksum ZORUNLU DEGIL)."""
    assert _valid_eoa_x402("0x" + "ab" * 20) is True


def test_valid_eoa_x402_lowercase():
    assert _valid_eoa_x402("0x" + "cd" * 20) is True


def test_valid_eoa_x402_checksumli():
    """ORTAM: EIP-55 checksumli de KABUL (sadece hex kontrolu)."""
    addr = "0x" + "AbCdEf0123456789AbCdEf0123456789AbCdEf01"
    assert _valid_eoa_x402(addr) is True


def test_valid_eoa_x402_kisa():
    assert _valid_eoa_x402("0x" + "ab" * 19) is False


def test_valid_eoa_x402_uzun():
    assert _valid_eoa_x402("0x" + "ab" * 21) is False


def test_valid_eoa_x402_on_ek_yok():
    assert _valid_eoa_x402("ab" * 20) is False


def test_valid_eoa_x402_hex_degil():
    assert _valid_eoa_x402("0x" + "gg" * 20) is False


def test_valid_eoa_x402_bos():
    assert _valid_eoa_x402("") is False
    assert _valid_eoa_x402("0x") is False


def test_valid_eoa_x402_none():
    """ORTAM: isinstance str kontrolu — None False."""
    assert _valid_eoa_x402(None) is False


def test_valid_eoa_x402_int():
    assert _valid_eoa_x402(12345) is False


def test_valid_eoa_x402_bytes():
    assert _valid_eoa_x402(b"0x" + b"ab" * 20) is False


def test_valid_eoa_x402_buyuk_hex_kabul():
    """ORTAM: ABCDEF buyuk KABUL."""
    assert _valid_eoa_x402("0x" + "AB" * 20) is True


def test_valid_eoa_x402_donut_bool():
    assert isinstance(_valid_eoa_x402("0x" + "ab" * 20), bool)


# == _valid_eoa (mainnet_guard) =========================================================================

def test_valid_eoa_guard_gecerli():
    """ORTAM: '0x' + 40 hex — x402_gate ile AYNI kural."""
    assert _valid_eoa_guard("0x" + "ab" * 20) is True


def test_valid_eoa_guard_kisa():
    assert _valid_eoa_guard("0x" + "ab" * 19) is False


def test_valid_eoa_guard_uzun():
    assert _valid_eoa_guard("0x" + "ab" * 21) is False


def test_valid_eoa_guard_on_ek_yok():
    assert _valid_eoa_guard("ab" * 20) is False


def test_valid_eoa_guard_bos():
    assert _valid_eoa_guard("") is False
    assert _valid_eoa_guard("0x") is False


def test_valid_eoa_guard_none():
    """ORTAM-OGRENDI: x402_gate'den FARKLI — isinstance kontrolu YOK!
    None.startswith -> AttributeError."""
    with pytest.raises(AttributeError):
        _valid_eoa_guard(None)


def test_valid_eoa_guard_int():
    with pytest.raises(AttributeError):
        _valid_eoa_guard(12345)


def test_valid_eoa_guard_hex_degil():
    """ORTAM-OGRENDI: hex kontrolu VAR — 'gg' RED (x402_gate ile AYNI)."""
    assert _valid_eoa_guard("0x" + "gg" * 20) is False


def test_valid_eoa_guard_buyuk_hex():
    assert _valid_eoa_guard("0x" + "AB" * 20) is True


def test_valid_eoa_guard_donut_bool():
    assert isinstance(_valid_eoa_guard("0x" + "ab" * 20), bool)


def test_valid_eoa_guard_41_hex():
    """ORTAM: 40+1 karakter -> False."""
    assert _valid_eoa_guard("0x" + "a" * 41) is False


# == _sandbox_keys =====================================================================================

def test_sandbox_unset(monkeypatch):
    """ORTAM: unset -> '' -> {} (bosluk-atlamasi)."""
    monkeypatch.delenv("UNPUMP_SANDBOX_KEYS", raising=False)
    assert _sandbox_keys() == set()


def test_sandbox_bos(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "")
    assert _sandbox_keys() == set()


def test_sandbox_bosluk(monkeypatch):
    """ORTAM: sadece bosluk -> if k.strip() -> atlanir."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "   ,  ,  ")
    assert _sandbox_keys() == set()


def test_sandbox_bir(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0x" + "ab" * 20)
    assert _sandbox_keys() == {"0x" + "ab" * 20}


def test_sandbox_coklu(monkeypatch):
    """ORTAM: virgülle-ayrilma."""
    a, b = "0x" + "ab" * 20, "0x" + "cd" * 20
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", f"{a},{b}")
    assert _sandbox_keys() == {a, b}


def test_sandbox_strip(monkeypatch):
    """ORTAM: k.strip() — bosluklar temizlenir."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "  k1  ,  k2  ")
    assert _sandbox_keys() == {"k1", "k2"}


def test_sandbox_lower(monkeypatch):
    """ORTAM-OGRENDI: k.lower() — BUYUK harfler KUCULTULUR (adres
    kiyaslamasi case-insensitive)."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "K1,ABC")
    assert _sandbox_keys() == {"k1", "abc"}


def test_sandbox_tekrar(monkeypatch):
    """ORTAM: set — tekrarlar COLLAPSE."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "k1,k1,k1")
    assert _sandbox_keys() == {"k1"}


def test_sandbox_karisik_bosluk(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "k1, ,k2,  ")
    assert _sandbox_keys() == {"k1", "k2"}


def test_sandbox_donut_tipi(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "k1")
    assert isinstance(_sandbox_keys(), set)


# == _hex_to_int =======================================================================================

def test_hex_basit():
    """ORTAM: int(h, 16)."""
    assert _hex_to_int("ff") == 255
    assert _hex_to_int("10") == 16


def test_hex_sifir():
    assert _hex_to_int("0") == 0
    assert _hex_to_int("0000") == 0


def test_hex_buyuk_kucuk():
    """ORTAM: int(h,16) case-insensitive."""
    assert _hex_to_int("FF") == _hex_to_int("ff") == 255
    assert _hex_to_int("AbCd") == 43981


def test_hex_uzun():
    assert _hex_to_int("0xabc123".replace("0x", "")) == 11256099


def test_hex_0x_on_ek_kabul():
    """ORTAM-OGRENDI: int('0xff', 16) Python'da KABUL — '0x' on-ek
    ValueError ATMaz, 255 verir (int() base-16 ozelligi)."""
    assert _hex_to_int("0xff") == 255
    assert _hex_to_int("0xFF") == 255


def test_hex_hex_degil():
    with pytest.raises(ValueError):
        _hex_to_int("gg")


def test_hex_bos():
    with pytest.raises(ValueError):
        _hex_to_int("")


def test_hex_donut_tipi():
    assert isinstance(_hex_to_int("f"), int)


@pytest.mark.parametrize("h,b", [("0", 0), ("1", 1), ("a", 10), ("f", 15),
                                 ("10", 16), ("ff", 255), ("FFFF", 65535)])
def test_hex_matrix(h, b):
    assert _hex_to_int(h) == b


# == _addr_topic =======================================================================================

def test_addr_topic_basit():
    """ORTAM: '0x' + addr[2:].lower().rjust(64,'0')."""
    assert _addr_topic("0xabc123") == "0x" + "0" * 58 + "abc123"


def test_addr_topic_tam_adres():
    """ORTAM: tam 40-hex adres -> 64 hane (24 sifir on-ek)."""
    addr = "0x" + "ab" * 20
    assert _addr_topic(addr) == "0x" + "0" * 24 + "ab" * 20


def test_addr_topic_uzunluk():
    v = _addr_topic("0x" + "ab" * 20)
    assert len(v) == 66
    assert v.startswith("0x")


def test_addr_topic_buyuk_kucuk():
    """ORTAM: .lower() — BUYUK harf KUCULTULUR."""
    assert _addr_topic("0xABC123") == _addr_topic("0xabc123")


def test_addr_topic_sifir_dolu():
    """ORTAM: rjust(64,'0') — kisa adres sifirle doldurulur."""
    v = _addr_topic("0x1")
    assert v == "0x" + "0" * 63 + "1"


def test_addr_topic_cok_uzun():
    """ORTAM-OGRENDI: 40'tan uzun adres rjust(64) ile 64'e TAMAMLANIR
    (truncate YOK; 50-hex -> 64-hex)."""
    addr = "0x" + "f" * 50
    v = _addr_topic(addr)
    assert v == "0x" + "0" * 14 + "f" * 50
    assert len(v) == 66


def test_addr_topic_on_ek_yok():
    """ORTAM: addr[2:] — '0x' YOKSA ilk 2 char KAYBOLUR ('ab'*20 -> 'ab'*19)."""
    assert _addr_topic("ab" * 20) == "0x" + "0" * 26 + "ab" * 19


def test_addr_topic_bos():
    """ORTAM: ''[2:] -> '' -> rjust -> 64 sifir."""
    assert _addr_topic("") == "0x" + "0" * 64


def test_addr_topic_stabil():
    addr = "0x" + "ab" * 20
    assert _addr_topic(addr) == _addr_topic(addr)


@pytest.mark.parametrize("a,b", [
    ("0x1", "0x" + "0" * 63 + "1"),
    ("0xabc123", "0x" + "0" * 58 + "abc123"),
    ("0xABC", "0x" + "0" * 61 + "abc"),
])
def test_addr_topic_matrix(a, b):
    assert _addr_topic(a) == b


# == _now (payments) ===================================================================================

def test_now_format():
    """ORTAM: isoformat(timespec='seconds') — SANIYE cozunurluk."""
    v = _now()
    assert v.endswith("+00:00")
    assert "." not in v  # saniye — mikro YOK


def test_now_parse():
    """ORTAM: ISO-8601 parse edilebilir."""
    d = _dt.datetime.fromisoformat(_now())
    assert d is not None


def test_now_aware():
    """ORTAM: tz-aware UTC."""
    d = _dt.datetime.fromisoformat(_now())
    assert d.utcoffset() == _dt.timedelta(0)


def testnow_z_format_yil():
    """ORTAM: YYYY-MM-DDTHH:MM:SS+00:00."""
    v = _now()
    assert len(v) == 25
    assert v[4] == "-" and v[10] == "T" and v[19] == "+"


def test_now_donut_tipi():
    assert isinstance(_now(), str)


def test_now_artar():
    a = _now()
    import time as _t
    _t.sleep(1.0)
    assert _now() >= a


def test_now_lokal_import(monkeypatch):
    """ORTAM-OGRENDI: _now ICINDE 'from datetime import ...' LOKAL import
    yapar — modul-seviyesi monkeypatch ISLEMEZ (kapsülleme karari;
    tekrar-test-edilebilirlik bedeli)."""
    import answrank.finance.payments as pay
    assert not hasattr(pay, "datetime")  # modul nitirigi YOK
    # yine de _now calisir (lokal import)
    assert _now().endswith("+00:00")


# == karakterizasyon ===================================================================================

def test_puan_amaci():
    """ORTAM-OGRENDI (DOCSTACK): snapshot'tan tek-alan puani — None snap
    -> None (ilk-olcum destegi); round(float(v),1) ile 1-ondalik normalizasyon;
    str/int degerler float'a cast (API ham verisi)."""
    assert _puan(None, "x") is None
    assert _puan({"a": 3.456}, "a") == 3.5


def test_fmt_amaci():
    """ORTAM-OGRENDI: _fmt DUZ deger (isaret YOK, em-dash None); _fmt_delta
    ISARETLI degisim (+/-); int -> str(int) vs float -> '.1f' format
    farkli DALlar; bool int DEGIL (isinstance True float DEGIL)."""
    assert _fmt(None) == "—"
    assert _fmt(3) == "3"
    assert _fmt(3.0) == "3.0"
    assert _fmt_delta(0) == "+0.0"


def test_truthy_amaci():
    """ORTAM-OGRENDI (KRITIK-FARK): IKI _truthy VARYANTI — x402_gate
    WHITELIST ('1','true','yes','on' strip+lower, unset->False) vs
    mainnet_guard BLACKLIST (not in '0','','false', CASE-SENSITIVE,
    default '1' -> unset True). Ayni isim TERS davranis — env'a
    bakarken hangi modulun _truthy'si cagirildigi HAYATI."""
    assert _truthy_x402("DSH_TEST_YOK_9") is False
    assert _truthy_guard("DSH_TEST_YOK_9") is True


def test_valid_eoa_amaci():
    """ORTAM-OGRENDI: EIP-55 checksum ZORUNLU DEGIL — env degerleri
    checksum'suz olabilir; burada YANLIS-ADRES yakalanir (imza
    dogrulamasi zincir tarafinda). x402_gate isinstance(str) kontrolu
    VAR (None False); mainnet_guard YOK (None AttributeError atar);
    mainnet_guard hex-gecerlilik kontrolu de VAR (modul-paritesi)."""
    assert _valid_eoa_x402("0x" + "ab" * 20) is True
    assert _valid_eoa_x402(None) is False
    assert _valid_eoa_guard("0x" + "gg" * 20) is False


def test_addr_topic_amaci():
    """ORTAM-OGRENDI: adresi 32-byte (64-hex) log topic'e gom — basta
    sifir-dolgusu (EVM address padding); .lower() ile case-normalizasyon;
    40-hex'ten UZUN adresler truncate EDILMEZ (rjust no-op — raw)."""
    assert _addr_topic("0x" + "ab" * 20) == "0x" + "0" * 24 + "ab" * 20
