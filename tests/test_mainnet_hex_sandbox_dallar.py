"""mainnet_verify + mainnet_guard dal-kesen testleri (LEED) — 2 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — ag/RPC YOK, sadece saf fonksiyonlar.
mainnet_verify._hex_to_int + mainnet_guard._sandbox_keys.
"""
import pytest

import mainnet_guard as MG
import mainnet_verify as MV


# == _hex_to_int ============================================================================

@pytest.mark.parametrize("h, beklenen", [
    ("0x0", 0), ("0", 0), ("0x1", 1), ("0x10", 16), ("10", 16),
    ("0xff", 255), ("FF", 255), ("0xFF", 255), ("0xDEADBEEF", 3735928559),
    ("deadbeef", 3735928559), ("0x0000000000000000000000000000000000000000", 0),
])
def test_hex_to_int_gecerli(h, beklenen):
    assert MV._hex_to_int(h) == beklenen


def test_hex_to_int_donus_tipi_int():
    assert isinstance(MV._hex_to_int("0xff"), int)


def test_hex_to_int_0x_on_ek_opsiyonel():
    """ORTAM: int(h, 16) '0x' on-ekini tolere eder."""
    assert MV._hex_to_int("0x2a") == MV._hex_to_int("2a") == 42


def test_hex_to_int_case_insensitive():
    assert MV._hex_to_int("AbCdEf") == MV._hex_to_int("abcdef") == 11259375


@pytest.mark.parametrize("h", ["", "gg", "xyz", "0xZZ", "  ", "12 34"])
def test_hex_to_int_gecersiz_valueerror(h):
    with pytest.raises(ValueError):
        MV._hex_to_int(h)


@pytest.mark.parametrize("h, beklenen", [("-ff", -255), ("-0x10", -16), ("-1", -1)])
def test_hex_to_int_eksili_isaret_kabul(h, beklenen):
    """ORTAM-OGRENDI: int(h, 16) bastaki '-' isaretini KABUL EDER (-ff -> -255);
    production quirk — hex_to_int imzasiz varsaymaz (Kural-5)."""
    assert MV._hex_to_int(h) == beklenen


@pytest.mark.parametrize("h", [None, 255, [], {}])
def test_hex_to_int_tip_hatasi(h):
    """ORTAM: int(None,16) TypeError; int(255,16) calisir ama string-beklenti
    testi None/sayi/liste icin TypeError-garantisi koyar."""
    if isinstance(h, str):
        pytest.skip("string'ler yukarida test edildi")
    with pytest.raises(TypeError):
        MV._hex_to_int(h)


def test_hex_to_int_buyuk_deger_64bit():
    """32-byte topic/uint256 degerleri kayipsiz doner."""
    big = "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    assert MV._hex_to_int(big) == 2**256 - 1


# == _sandbox_keys ==========================================================================

def test_sandbox_keys_env_yok_bos_kume(monkeypatch):
    monkeypatch.delenv("UNPUMP_SANDBOX_KEYS", raising=False)
    assert MG._sandbox_keys() == set()


def test_sandbox_keys_bos_env_bos_kume(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "")
    assert MG._sandbox_keys() == set()


def test_sandbox_keys_tek_adres(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xabc123")
    assert MG._sandbox_keys() == {"0xabc123"}


def test_sandbox_keys_lowercase(monkeypatch):
    """ORTAM: k.strip().lower() — buyuk harf kucuklenir."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xABCDEF")
    assert MG._sandbox_keys() == {"0xabcdef"}


def test_sandbox_keys_virgul_ayirir(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xaaa,0xbbb,0xccc")
    assert MG._sandbox_keys() == {"0xaaa", "0xbbb", "0xccc"}


@pytest.mark.parametrize("raw, beklenen", [
    (" 0xaaa , 0xbbb ", {"0xaaa", "0xbbb"}),
    ("0xaaa,,0xbbb", {"0xaaa", "0xbbb"}),
    ("  ,  ,  ", set()),
    (",,,0xzzz,,,", {"0xzzz"}),
    ("0xAAA,0xaaa", {"0xaaa"}),
])
def test_sandbox_keys_bosluk_ve_tekrar(monkeypatch, raw, beklenen):
    """ORTAM: bos parcalar ve tekrarlar set() ile elenir/dedup olur."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", raw)
    assert MG._sandbox_keys() == beklenen


def test_sandbox_keys_donus_tipi_set(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xaaa")
    out = MG._sandbox_keys()
    assert isinstance(out, set)


def test_sandbox_keys_elemanlar_string(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xaaa,0xbbb")
    assert all(isinstance(x, str) for x in MG._sandbox_keys())


def test_sandbox_keys_unicode_ve_emoji(monkeypatch):
    """ORTAM: strip/lower her karakteri isa eder; format-kontrolu YOK."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "İSTANBUL,😀")
    assert MG._sandbox_keys() == {"İstanbul".lower(), "😀"}


def test_sandbox_keys_true_adres_uzunlugu(monkeypatch):
    addr = "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", addr)
    assert MG._sandbox_keys() == {addr.lower()}


# == is_sandbox_payer etkilesim (kapali davranis) ============================================

def test_is_sandbox_payer_env_yok_false(monkeypatch):
    monkeypatch.delenv("UNPUMP_SANDBOX_KEYS", raising=False)
    monkeypatch.delenv("UNPUMP_SANDBOX", raising=False)
    assert MG.is_sandbox_payer("0xabc") is False


def test_is_sandbox_payer_whitelist_disi(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xabc")
    monkeypatch.setenv("UNPUMP_SANDBOX", "1")
    assert MG.is_sandbox_payer("0xzzz") is False


def test_is_sandbox_payer_whitelist_icinde(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xABC")
    monkeypatch.setenv("UNPUMP_SANDBOX", "1")
    assert MG.is_sandbox_payer("0xabc") is True


def test_is_sandbox_payer_case_insensitive(monkeypatch):
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0xAbC123")
    monkeypatch.setenv("UNPUMP_SANDBOX", "1")
    assert MG.is_sandbox_payer("0xaBc123") is True
