"""Gorev: test derinlestir — T9 x-payer-address binding + resolve_treasury
fail-closed + net-kar buyback negatif-kar edge case.

PARCA 2 ( LEAD gorevi, 2026-09-28):
  (a) resolve_treasury() fail-closed yolu ( kotu treasury -> SystemExit)
  (b) x-payer-address binding ( T9 guvenlik) testi
  (c) net-kar buyback kalkani edge case: negatif kar -> buyback TETIKLENMEMELI

Yazma kapsami: tests/** + bu dosya. Uretim .py'lere DOKUNMA ( bu testler
mainnet_guard.py'yi DISARIDAN cagirir — import eder, degistirmez).
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

_PROJE = "/home/gokun/projects/Yeni Fikirler/oncu_fikirler_havuzu_2026/23_Unpump_Cash_Otonom_Ajan_Borsasi_Ve_Nakit_Akisli_AMM"
if _PROJE not in sys.path:
    sys.path.insert(0, _PROJE)

mainnet_guard = importlib.import_module("mainnet_guard")
resolve_treasury = mainnet_guard.resolve_treasury
_valid_eoa = mainnet_guard._valid_eoa

# ajan_hazinesi ( bu repoda, G-001/G-002 ile ayni yerde)
ajan_hazinesi = importlib.import_module("ajan_hazinesi")
bolusum_hesapla = ajan_hazinesi.bolusum_hesapla
GelirKaydi = ajan_hazinesi.GelirKaydi

_GECERLI_EOA = "0x" + "ab" * 20   # 0x + 40 hex
_KOTU_EOA = "0xDEAD"               # kisa
_HATALI_EOA = "0xZZ" + "00" * 19   # hex degil


# ---------------------------------------------------------------------------
# PARCA 2a — resolve_treasury() fail-closed yolu
# ---------------------------------------------------------------------------

class TestResolveTreasuryFailClosed:
    """resolve_treasury: odeme-hedefi YOKSA/BOZUKSA servis BASLAYAMAMALI."""

    def test_hic_treasury_yoksa_systemexit(self, monkeypatch):
        """Iki env de yok -> SystemExit ( fail-closed)."""
        monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
        monkeypatch.delenv("SVC_MAINNET_PAY_TO", raising=False)
        with pytest.raises(SystemExit):
            resolve_treasury("svc")

    def test_bos_treasury_systemexit(self, monkeypatch):
        """Bosluk-dolu env -> SystemExit."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", "   ")
        monkeypatch.delenv("SVC_MAINNET_PAY_TO", raising=False)
        with pytest.raises(SystemExit):
            resolve_treasury("svc")

    def test_kisa_kotu_eoa_systemexit(self, monkeypatch):
        """Kotu EOA ( kisa) -> SystemExit, geri-uyum de DEGIL."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", _KOTU_EOA)
        with pytest.raises(SystemExit):
            resolve_treasury("svc")

    def test_hex_olmayan_eoa_systemexit(self, monkeypatch):
        """Hex olmayan EOA -> SystemExit."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", _HATALI_EOA)
        with pytest.raises(SystemExit):
            resolve_treasury("svc")

    def test_kotu_legacy_eoa_systemexit(self, monkeypatch):
        """UNPUMP_TREASURY_EOA bos + <SVC>_MAINNET_PAY_TO kotu -> SystemExit."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", "")
        monkeypatch.setenv("TESTSVC_MAINNET_PAY_TO", _KOTU_EOA)
        with pytest.raises(SystemExit):
            resolve_treasury("testsvc")

    def test_kotu_eoa_mesaj_treasury_icerir(self, monkeypatch):
        """Hata mesajinda 'treasury-invalid' gecmeli ( arama kolayligi)."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", _KOTU_EOA)
        with pytest.raises(SystemExit) as excinfo:
            resolve_treasury("svc")
        assert "treasury-invalid" in str(excinfo.value)

    def test_gecerli_treasury_donuyor(self, monkeypatch):
        """Gecerli EOA -> ayni adres donmeli ( pozitif yol)."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", _GECERLI_EOA)
        assert resolve_treasury("svc") == _GECERLI_EOA

    def test_gecerli_legacy_geri_uyum(self, monkeypatch):
        """UNPUMP_TREASURY_EOA yoksa <SVC>_MAINNET_PAY_TO geri-uyum calisir."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", "")
        monkeypatch.setenv("TESTSVC_MAINNET_PAY_TO", _GECERLI_EOA)
        assert resolve_treasury("testsvc") == _GECERLI_EOA

    def test_treasury_oncegi_legacy_gozardi(self, monkeypatch):
        """UNPUMP_TREASURY_EOA varsa legacy GORULMEZ ( tek-kasa kurali)."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", _GECERLI_EOA)
        monkeypatch.setenv("TESTSVC_MAINNET_PAY_TO", "0x" + "cd" * 20)
        assert resolve_treasury("testsvc") == _GECERLI_EOA

    def test_valid_eoa_yardimci_dogru(self):
        """_valid_eoa: gecerli/kotu ayirt eder."""
        assert _valid_eoa(_GECERLI_EOA) is True
        assert _valid_eoa(_KOTU_EOA) is False
        assert _valid_eoa(_HATALI_EOA) is False
        assert _valid_eoa("") is False
        assert _valid_eoa("0x" + "ab" * 19) is False   # 39 hex
        assert _valid_eoa("0x" + "ab" * 21) is False   # 41 hex


# ---------------------------------------------------------------------------
# PARCA 2b — T9: x-payer-address binding ( odeme imzasi ile payer aynisi)
# ---------------------------------------------------------------------------

class FakeRequest:
    """FastAPI Request taklidi ( sadece headers + url)."""

    class _Url:
        def __init__(self, path: str):
            self.path = path

    def __init__(self, headers: dict, path: str = "/svc"):
        self.headers = headers
        self.url = self._Url(path)


class TestXPayerAddressBinding:
    """T9: X-Payer-Address, X-Payment imzasindan cikan agent ile ESLESMELI.

    Saldiri: saldirgan baskasinin odemesinin basligini kopyalayip baska
    bir agent adina cagri yapar. Guard, imzadaki agent ile header'daki
    payer'i karsilastirir -> uyumsuzsa 402.
    """

    @staticmethod
    def _mainnet_mod(monkeypatch):
        """require_mainnet_payment'i zincir-moduna zorla ( test degil)."""
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", _GECERLI_EOA)
        monkeypatch.setenv("UNPUMP_TEST", "0")
        monkeypatch.setenv("SVC_MAINNET", "1")

    def test_payer_eslesirse_kalkani_gecer(self, monkeypatch):
        """Imzadaki agent == x-payer-address -> payer_mismatch VERILMEZ.

        Zincir aramasi bu testte basarisiz olabilir ( RPC erisimi) —
        biz T9 bagini test ediyoruz: odeme-imza-agent'i == payer ise
        'payer_mismatch' hatasi ZULLENMEMELI. RPC hatasi ( 402/503)
        olabilir ama payer_mismatch ASLA.
        """
        from fastapi import HTTPException
        self._mainnet_mod(monkeypatch)

        def fake_verify(header, kaynak):
            return {"agent": "0x" + "12" * 20}

        # sester yalnizca .venv'de ( system python'da YOK) —
        # olmayan ortamda T9 mock testleri skip edilir ( importorskip)
        schemes = pytest.importorskip("sester.schemes")
        monkeypatch.setattr(schemes, "verify_exact_sester", fake_verify)

        req = FakeRequest({
            "x-payment": "GECERLI-IMZA",
            "x-payer-address": "0x" + "12" * 20,
        })
        with pytest.raises(HTTPException) as excinfo:
            mainnet_guard.require_mainnet_payment(
                req, price=1.0, pay_to=_GECERLI_EOA, service_name="svc")
        # odeme bulunamadi olabilir ( 402) ama T9 payer_mismatch DEGIL
        assert "payer_mismatch" not in str(excinfo.value.detail)

    def test_payer_uyusmazsa_402(self, monkeypatch):
        """Imzadaki agent != x-payer-address -> HTTPException 402 payer_mismatch.

        T9 binding zincir aramasindan ONCE calisir ( saldiri一旦 tespit
        edilir, zincir aramaya gerek kalmaz).
        """
        from fastapi import HTTPException
        self._mainnet_mod(monkeypatch)

        def fake_verify(header, kaynak):
            return {"agent": "0x" + "12" * 20}

        # sester yalnizca .venv'de ( system python'da YOK) — importorskip
        schemes = pytest.importorskip("sester.schemes")
        monkeypatch.setattr(schemes, "verify_exact_sester", fake_verify)

        req = FakeRequest({
            "x-payment": "GECERLI-IMZA",
            "x-payer-address": "0x" + "cd" * 20,
        })
        with pytest.raises(HTTPException) as excinfo:
            mainnet_guard.require_mainnet_payment(
                req, price=1.0, pay_to=_GECERLI_EOA, service_name="svc")
        assert excinfo.value.status_code == 402
        assert "payer_mismatch" in str(excinfo.value.detail)

    def test_odeme_header_yoksa_402(self, monkeypatch):
        """x-payment YOK -> T9 atlanir, zincir aramasi 402/503 ( fail-closed).

        Odeme kaniti YOK -> zincirde transfer bulunamaz -> 402. RPC
        erisimi yoksa 503 ( fail-closed). Ikisi de 'odeme yok' anlamina
        gelir; hangisi oldugu bu testin odagi DEGIL.
        """
        from fastapi import HTTPException
        self._mainnet_mod(monkeypatch)

        req = FakeRequest({"x-payer-address": "0x" + "12" * 20})
        with pytest.raises(HTTPException) as excinfo:
            mainnet_guard.require_mainnet_payment(
                req, price=1.0, pay_to=_GECERLI_EOA, service_name="svc")
        assert excinfo.value.status_code in (402, 503)

    def test_gecersiz_payer_format_402(self, monkeypatch):
        """x-payer-address '0x'+40hex DEGIL -> 402 ( format kontrolu)."""
        from fastapi import HTTPException
        self._mainnet_mod(monkeypatch)

        req = FakeRequest({"x-payer-address": "0xDEAD"})
        with pytest.raises(HTTPException) as excinfo:
            mainnet_guard.require_mainnet_payment(
                req, price=1.0, pay_to=_GECERLI_EOA, service_name="svc")
        assert excinfo.value.status_code == 402


# ---------------------------------------------------------------------------
# PARCA 2c — net-kar buyback: negatif kar -> buyback TETIKLENMEMELI
# ---------------------------------------------------------------------------

class TestNegatifKarBuybackKalkani:
    """DCBM Solvency Actuator: net kâr <= 0 ise buyback YOK ( iflas-korumasi)."""

    def test_negatif_kar_buyback_sifir(self):
        """Brut < maliyet -> buyback 0 ( negatif kar yakilamaz)."""
        kayitlar = [GelirKaydi("callsnap", brut_gelir_usd=5.0,
                               api_maliyet_usd=11.27)]
        rapor = bolusum_hesapla(kayitlar, dev_payi_orani=0.10)
        assert rapor.buyback_ayrilan_usd == 0.0

    def test_negatif_kar_dev_payi_da_sifir(self):
        """Negatif kâr -> hicbir bolusum YOK ( dev payi bile)."""
        kayitlar = [GelirKaydi("svc", brut_gelir_usd=1.0,
                               altyapi_maliyet_usd=5.0)]
        rapor = bolusum_hesapla(kayitlar, dev_payi_orani=0.10)
        assert rapor.dev_payi_usd == 0.0
        assert rapor.operasyon_usd == 0.0
        assert rapor.protokol_usd == 0.0
        assert rapor.buyback_ayrilan_usd == 0.0

    def test_sifir_kar_da_buyback_yok(self):
        """Brut == maliyet -> net 0 -> buyback 0 ( sinir durumu)."""
        kayitlar = [GelirKaydi("svc", brut_gelir_usd=5.0,
                               altyapi_maliyet_usd=5.0)]
        rapor = bolusum_hesapla(kayitlar, dev_payi_orani=0.10)
        assert rapor.buyback_ayrilan_usd == 0.0

    def test_pozitif_kar_buyback_var(self):
        """Pozitif DIS kâr -> buyback > 0 ( kalkan calisiyor).

        G-001 dairesellik kurali: buyback YALNIZCA DISARIDAN gelen net
        kardan; bu yuzden dis_musteri_mi=True veriyoruz.
        """
        kayitlar = [GelirKaydi("svc", brut_gelir_usd=10.0,
                               altyapi_maliyet_usd=1.0)]
        rapor = bolusum_hesapla(kayitlar, dev_payi_orani=0.0,
                                dis_musteri_mi={"svc": True})
        # net=9; DCBM tavan 9*0.50=4.5; §9 saf 9*0.90=8.1 -> min = 4.5
        assert rapor.buyback_ayrilan_usd == pytest.approx(4.5)

    def test_dairesel_ic_gelirle_buyback_yok(self):
        """Ic/test geliriyle ( dis_musteri_mi=False) buyback YAKILMAZ ( G-001)."""
        kayitlar = [GelirKaydi("test-servis", brut_gelir_usd=311.76,
                               altyapi_maliyet_usd=5.0)]
        rapor = bolusum_hesapla(kayitlar, dev_payi_orani=0.10,
                                dis_musteri_mi={"test-servis": False})
        assert rapor.buyback_ayrilan_usd == 0.0

    def test_dis_gelirle_buyback_var(self):
        """Disaridan gelen gelir -> buyback > 0 ( dairesel-DEGIL)."""
        kayitlar = [GelirKaydi("kodincelemesi", brut_gelir_usd=25.0,
                               altyapi_maliyet_usd=0.25)]
        rapor = bolusum_hesapla(kayitlar, dev_payi_orani=0.10,
                                dis_musteri_mi={"kodincelemesi": True})
        assert rapor.buyback_ayrilan_usd > 0.0
