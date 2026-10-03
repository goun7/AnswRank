"""GUVENLIK DERINLESTIRME — treasury fail-closed + payer binding + buyback edge.

Gorev ( acil): derinlestir:
  PARCA 2-A: resolve_treasury() fail-closed yolu ( kotu treasury -> SystemExit)
             + 20/20 servis env'inde TEK EOA dogrulama
  PARCA 2-B: X-Payer-Address binding ( T9 guvenlik) — imza-adres uyuşmazligi
             reddedilmeli ( fail-closed)
  PARCA 2-C: net-kar buyback edge case: negatif/sifir kar -> buyback YOK

KANIT:  python3 -m pytest tests/test_guvenlik_derin.py -q
"""
from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import mainnet_guard  # noqa: E402

VALID_EOA = "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"
ALT_EOA = "0x" + "ab" * 20
SERVICE = "answrank"
LEGACY_VAR = f"{SERVICE.upper()}_MAINNET_PAY_TO"

_AGENT = "0x26dbfe78d63509f845c147b8480079c6fbd28bfc"
_SK = ("0x110a30d15ae588e70dbe1074bb582d385b0ee6b08437"
       "007d23c13e969d266857")


def _imzala(agent, sk, fiyat=0.05, route="/audit", nonce="t9-test"):
    """Sandbox demo agent ile EIP-191 exact-sester imzasi."""
    from sester.schemes import sign_exact_sester
    return sign_exact_sester(sk, agent, nonce, fiyat, route)


@pytest.fixture(autouse=True)
def _clean_treasury_env(monkeypatch):
    monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
    monkeypatch.delenv(LEGACY_VAR, raising=False)


# ================================================================ PARCA 2-A
# resolve_treasury() fail-closed yolu


def test_resolve_treasury_gecersiz_eoa_system_exit(monkeypatch):
    """Bozuk EOA -> SystemExit ( yanlis-adrese odeme riskini sifirla)."""
    for kotu in ("0x123", "yazi", "0x" + "zz" * 20, "F3F0cC9DE0Df5A17a09"):
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", kotu)
        with pytest.raises(SystemExit) as exc:
            mainnet_guard.resolve_treasury(SERVICE)
        assert "treasury-invalid" in str(exc.value), (
            f"kotu EOA {kotu!r} reddedilmedi")


def test_resolve_treasury_bos_env_system_exit(monkeypatch):
    """Iki env de bos -> SystemExit ( servis odeme-hedefisiz BASLAYAMAZ)."""
    monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
    monkeypatch.delenv(LEGACY_VAR, raising=False)
    with pytest.raises(SystemExit) as exc:
        mainnet_guard.resolve_treasury(SERVICE)
    assert "treasury-required" in str(exc.value)


def test_resolve_treasury_gecerli_eoa_donar(monkeypatch):
    """Gecerli tek-kasa EOA -> ayni adres doner."""
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", VALID_EOA)
    assert mainnet_guard.resolve_treasury(SERVICE) == VALID_EOA


def test_resolve_treasury_legacy_geri_uyum(monkeypatch):
    """UNPUMP_TREASURY_EOA yoksa <SVC>_MAINNET_PAY_TO kullanilir."""
    monkeypatch.setenv(LEGACY_VAR, ALT_EOA)
    assert mainnet_guard.resolve_treasury(SERVICE) == ALT_EOA


def test_resolve_treasury_tek_kasa_oncelikli(monkeypatch):
    """Her iki env varsa UNPUMP_TREASURY_EOA kazanir ( tek-kasa kurali)."""
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", VALID_EOA)
    monkeypatch.setenv(LEGACY_VAR, ALT_EOA)
    assert mainnet_guard.resolve_treasury(SERVICE) == VALID_EOA


def test_resolve_treasury_legacy_gecersiz_system_exit(monkeypatch):
    """Legacy env bozuksa -> SystemExit ( tek-kasa kurali her durumda)."""
    monkeypatch.setenv(LEGACY_VAR, "0x123")
    with pytest.raises(SystemExit) as exc:
        mainnet_guard.resolve_treasury(SERVICE)
    assert "treasury-invalid" in str(exc.value)


# ================================================================ PARCA 2-B
# X-Payer-Address binding ( T9 guvenlik) — EIP-191 imza dogrulama

pytest.importorskip("sester")


def test_sign_agent_imzalayan_adresle_uyusmali():
    """T9: imza, agent alani imzalayan cuzdanla AYNI olmali.

    Saldirgan baska cuzdandan imzalayip agent='kurban' yazamaz —
    sign_exact_sester imzalamayi reddeder. Bu ODENEYI KIMLIGINI
    imzaya baglar ( T9: agent = imzalayan).
    """
    from sester.schemes import PaymentError, sign_exact_sester
    try:
        from eth_account import Account
    except ImportError:
        pytest.skip("eth-account yok")
    fake = Account.create()
    with pytest.raises(PaymentError) as exc:
        sign_exact_sester(fake.key.hex(), _AGENT, "t9-spoof", 0.05, "/audit")
    assert "uyuşmuyor" in str(exc.value), (
        "sahte agent imzasi reddedilmedi!")


def test_verify_imza_dogru_ise_kabul():
    """T9 dogru akis: agent kendi key'i ile imzalar -> verify gecer."""
    from sester.schemes import verify_exact_sester
    imza = _imzala(_AGENT, _SK, nonce="t9-verify-ok")
    sonuc = verify_exact_sester(imza, "/audit")
    assert sonuc["agent"].lower() == _AGENT.lower()
    assert sonuc["nonce"] == "t9-verify-ok"
    assert sonuc["amount"] == "0.05"


def test_verify_resource_binding():
    """T9: imza '/audit' icin yapildiysa '/ozet' icin KULLANILAMAZ.

    Odeme kaniti belirli bir resource'a ( route) baglidir — bir
    endpoint icin odenen imza baska bir endpoint'te yeniden oynatilamaz
    ( replay/upgrade saldirisini engeller).
    """
    from sester.schemes import PaymentError, verify_exact_sester
    imza = _imzala(_AGENT, _SK, nonce="t9-resource")
    with pytest.raises(PaymentError):
        # imza '/audit' icin; '/ozet' resource'u ile dogrulanamaz
        verify_exact_sester(imza, "/ozet")


def test_verify_bos_imza_reddedilir():
    """T9: bos/bozuk header -> PaymentError ( fail-closed)."""
    from sester.schemes import PaymentError, verify_exact_sester
    for kotu in ("", "   ", "Sester-EVM ", "baska-sema", "Sester-EVM xxx"):
        with pytest.raises(PaymentError):
            verify_exact_sester(kotu, "/audit")


def test_verify_tutar_binding():
    """T9: imza 0.05 icin; middleware baska tutar reddeder ( tutar baglama).

    Burada imzanin icine gomulu tutari kontrol ediyoruz: verify ciktisi
    amount=0.05 doner — servis sagladigi fiyat ile karsilastirmalidir.
    """
    from sester.schemes import verify_exact_sester
    imza = _imzala(_AGENT, _SK, fiyat=0.05, nonce="t9-tutar")
    sonuc = verify_exact_sester(imza, "/audit")
    assert float(sonuc["amount"]) == 0.05


# ================================================================ PARCA 2-C
# net-kar buyback edge case'ler
# NOT: BuybackHesaplayici.hesapla() dict dondurur:
#   {'oneriler': [BuybackOnerisi...], 'toplam_net_kar_usd': ...,
#    'toplam_izin_verilen_buyback_usd': ..., ...}


def _hesapla(*kayitlar):
    from answrank.finance.net_kar_buyback import BuybackHesaplayici
    return BuybackHesaplayici.hesapla(list(kayitlar))


def _kayit(brut, llm=0.0, api=0.0, altyapi=0.0, transfer=0.0,
           servis="svc", cagri=10):
    from answrank.finance.net_kar_buyback import ServisGelirKaydi
    return ServisGelirKaydi(
        servis=servis, cagri_sayisi=cagri, brut_gelir_usd=brut,
        llm_maliyet_usd=llm, api_maliyet_usd=api,
        altyapi_maliyet_usd=altyapi, transfer_maliyet_usd=transfer)


def test_sifir_net_kar_buyback_yok():
    """Breakeven ( net kar = 0) -> buyback 0 ( zarar olmasa da yok)."""
    sonuc = _hesapla(_kayit(1.0, llm=0.5, api=0.3, altyapi=0.2))
    assert sonuc["toplam_net_kar_usd"] == pytest.approx(0.0)
    assert sonuc["toplam_izin_verilen_buyback_usd"] <= 0
    assert sonuc["oneriler"][0].reddedildi is True


def test_negatif_net_kar_buyback_yok():
    """Zarar eden servis -> buyback YOK ( iflas-korumasi)."""
    sonuc = _hesapla(_kayit(1.0, llm=1.5, api=0.3, altyapi=0.2,
                            servis="zarar"))
    assert sonuc["toplam_net_kar_usd"] < 0
    assert sonuc["toplam_izin_verilen_buyback_usd"] <= 0
    oneri = sonuc["oneriler"][0]
    assert oneri.reddedildi is True
    assert "iflas" in oneri.red_nedeni.lower()


def test_buyback_net_kari_asamaz_edge():
    """Buyback == net_kar'a kadar gidebilir ama ASAMAZ ( sinir degeri)."""
    sonuc = _hesapla(_kayit(10.0, llm=1.0, api=0.5, altyapi=0.5,
                            servis="karli", cagri=100))
    assert sonuc["toplam_net_kar_usd"] == pytest.approx(8.0)
    assert 0 < sonuc["toplam_izin_verilen_buyback_usd"] <= 8.0


def test_buyback_cok_karli_saf_stdlib():
    """%100 marajli saf-stdlib servis -> buyback net kara esit olabilir."""
    sonuc = _hesapla(_kayit(5.0, servis="saf-stdlib", cagri=50))
    assert sonuc["toplam_net_kar_usd"] == pytest.approx(5.0)
    assert sonuc["toplam_izin_verilen_buyback_usd"] <= 5.0


def test_buyback_birlesik_zarar_karli():
    """Birlesik: bir zarar + bir karli -> toplam NET kâr uzerinden.

    Kural: buyback SADECE toplam NET kâr ile ( brut YOK; static-yuzde YOK).
    """
    sonuc = _hesapla(
        _kayit(1.0, llm=2.0, servis="zarar", cagri=5),
        _kayit(10.0, llm=1.0, servis="karli", cagri=50))
    # toplam net = (1-2) + (10-1) = -1 + 9 = 8
    assert sonuc["toplam_net_kar_usd"] == pytest.approx(8.0)
    assert 0 < sonuc["toplam_izin_verilen_buyback_usd"] <= 8.0


def test_buyback_kurali_metni_dcr():
    """Kural metni DCBM kaynakli ( brut YOK, static-yuzde YOK)."""
    sonuc = _hesapla(_kayit(10.0, llm=1.0))
    assert "SADECE net-kar" in sonuc["kural"]
    assert "brut YOK" in sonuc["kural"]
