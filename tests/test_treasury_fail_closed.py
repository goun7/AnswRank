"""TEK-KASA fail-closed testleri — mainnet_guard.resolve_treasury.

Gerekce ( vergi optimizasyonu, 25 Eyl): tum x402 servislerinin odemesi
TEK Unpump kasa EOA'sina gider. resolve_treasury() her servisin
x402_servis.py'sinde MODUL-BASINDA cagrilir; hatali/eksik yapilandirma
varsa SystemExit firlatarak servisin BASLAMASINI engeller (fail-closed).

Bu test gercek RPC cagirmaz — resolve_treasury yalnizca cevre degiskeni
okur; bu yuzden mock env yeterli ( costly chain sorgusu yok).
"""

import os
import sys

import pytest

# repo root'u sys.path'e ekle — mainnet_guard.py paket degil, repo dibinde.
# ( python -m pytest zaten cwd ekler; baska cagri sekilleri icin guvence)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import mainnet_guard  # noqa: E402

VALID_EOA = "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"
ALT_EOA = "0x" + "ab" * 20  # gecerli format, farkli adres
SERVICE = "answrank"
LEGACY_VAR = f"{SERVICE.upper()}_MAINNET_PAY_TO"


@pytest.fixture(autouse=True)
def _clean_treasury_env(monkeypatch):
    """Her test basinda treasury ile ilgili tum env'leri temizle.

    Isolasyon: sistemin canli env'i ( .env.production sistemden gelir)
    test sonucunu bulandirmamali — her test kendi env'ini kurar.
    """
    monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
    monkeypatch.delenv(LEGACY_VAR, raising=False)


def test_iki_env_bos_ise_systemexit_fail_closed():
    """UNPUMP_TREASURY_EOA VE <SVC>_MAINNET_PAY_TO ikisi de bossa -> SystemExit.

    Fail-closed anlami: servis odeme-hedefisiz BASLAYAMAZ. Bu, "odemeyi
    aldik ama yere gitmedi" ( muhasebe kaybi) riskini sifirlar.
    """
    with pytest.raises(SystemExit) as exc:
        mainnet_guard.resolve_treasury(SERVICE)
    msg = str(exc.value)
    assert "treasury-required" in msg
    assert "UNPUMP_TREASURY_EOA" in msg
    #geregi acikca bildirilmeli
    assert "MAINNET_PAY_TO ayarlanmam" not in msg


def test_sadece_treasury_env_kullanilir(monkeypatch):
    """UNPUMP_TREASURY_EOA set ise TEK KAYNAK olarak kullanilir."""
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", VALID_EOA)
    result = mainnet_guard.resolve_treasury(SERVICE)
    assert result == VALID_EOA


def test_legacy_env_geri_uyum_calisir(monkeypatch):
    """Sadece <SVC>_MAINNET_PAY_TO varsa geri-uyum yolu calisir.

    Bu, var olan kurulumlarin tek-kasa gecisinde KIRILMAMASI icin
    kritik ( ayri env'lerle eski servisler hala ayakta kalabilir).
    """
    monkeypatch.setenv(LEGACY_VAR, ALT_EOA)
    assert mainnet_guard.resolve_treasury(SERVICE) == ALT_EOA


def test_treasury_legacy_uzerinde_oncelikli(monkeypatch):
    """Iki env de varsa UNPUMP_TREASURY_EOA kazanir ( tek-kasa kurami)."""
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", VALID_EOA)
    monkeypatch.setenv(LEGACY_VAR, ALT_EOA)
    assert mainnet_guard.resolve_treasury(SERVICE) == VALID_EOA


@pytest.mark.parametrize("bad", [
    "0x123",                    # cok kisa
    "abc",                      # 0x onbasi yok
    "0x" + "z" * 40,            # hex disi karakter
    "0x" + "a" * 39,            # 39 hex (eksik)
    "0x" + "a" * 41,            # 41 hex (fazla)
    "F3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5",  # 0x onbasi yok
])
def test_gecersiz_treasury_adres_systemexit(bad, monkeypatch):
    """Gecersiz formatli treasury EOA -> SystemExit ( yanlis-adres riski).

    Bosluk/zvirve degerlerin kabul edilmesi odemenin yanlis-adrese
    gitmesi demek — fail-closed ile reddedilir.
    """
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", bad)
    with pytest.raises(SystemExit) as exc:
        mainnet_guard.resolve_treasury(SERVICE)
    assert "treasury-invalid" in str(exc.value)


def test_gecersiz_legacy_adres_systemexit(monkeypatch):
    """Legacy env de gecersizse -> SystemExit ( geri-uyum da guvenli)."""
    monkeypatch.setenv(LEGACY_VAR, "0x123")
    with pytest.raises(SystemExit) as exc:
        mainnet_guard.resolve_treasury(SERVICE)
    assert "treasury-invalid" in str(exc.value)
    assert LEGACY_VAR in str(exc.value)


def test_bosluk_dolu_env_fail_closed(monkeypatch):
    """Bosluk-dolu env degeri bos kabul edilir -> SystemExit."""
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", "   ")
    with pytest.raises(SystemExit) as exc:
        mainnet_guard.resolve_treasury(SERVICE)
    assert "treasury-required" in str(exc.value)


def test_valid_eoa_format_kontrolcusu():
    """_valid_eoa yardimcisi format kurallarini uygular."""
    assert mainnet_guard._valid_eoa(VALID_EOA)
    assert mainnet_guard._valid_eoa("0x" + "0" * 40)
    assert not mainnet_guard._valid_eoa("0x123")
    assert not mainnet_guard._valid_eoa("")
    assert not mainnet_guard._valid_eoa("0xZZ" + "0" * 38)
    # checksum'siz kucuk-harf de gecerli ( env uyumu)
    assert mainnet_guard._valid_eoa("0x" + "a" * 40)
