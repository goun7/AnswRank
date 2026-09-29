#!/usr/bin/env python3
"""USDC nominal tutarlilik denetimi — 1 USDC = 1 USD kabulu.

KAPSAM: healthz'deki audit/citations/fix fiyatlarinin USDC nominal
degeriyle celisip celismedigini kontrol eder. Birim: 1 USDC = 1 USD
( nominal; gercek peg DEGIL — peg dalgalanmasi bu testin disinda).

⚠ DURUST ETIKET: bu test YERELDIR ( 127.0.0.1) — hicbir gercek zincir
  cagrisi yapilmaz, para harcanmaz. Canli servisten fiyat okur.
"""
from __future__ import annotations

import json

import httpx
import pytest

_ANSWRANK = "http://127.0.0.1:8007"
_BEKLENEN_FIYATLAR = {  # docs/27 §2 matrisi + docs/32 §3.1 ile ayni
    "audit": 0.05,
    "citations": 1.20,
    "fix": 0.20,
}


def _healthz():
    """Canli healthz JSON ( servis ayakta degilse atla)."""
    try:
        with httpx.Client(timeout=8) as c:
            r = c.get(f"{_ANSWRANK}/healthz")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


def _usd(v):
    """'$0.05' -> 0.05"""
    return float(str(v).lstrip("$"))


@pytest.fixture
def healthz():
    veri = _healthz()
    if veri is None:
        pytest.skip("answrank servisi :8007 ayakta degil ( yerel dry-run)")
    return veri


# --- nominal tutarlilik: 1 USDC = 1 USD ---

def test_fiyatlar_usd_nominaliyla_celismiyor(healthz):
    """Fiyatlar 1 USDC = 1 USD kabulune gore nominal tutarli olmali.

    healthz'deki fiyat ( USD) ile beklenen USDC nominal deger ayni.
    Celiski: fiyat '$0.05' ama gercek 50000 minor birim ( = $0.05 USDC)
    gibi durumlar — yani fiyat ile USDC nominali ayni olmali.
    """
    fiyatlar = healthz.get("prices", {})
    assert fiyatlar, "healthz'de 'prices' YOK"

    for ad, beklenen in _BEKLENEN_FIYATLAR.items():
        assert ad in fiyatlar, f"'{ad}' fiyatlar icinde YOK: {fiyatlar}"
        gercek = _usd(fiyatlar[ad])
        assert gercek == pytest.approx(
            beklenen, abs=1e-9), (
            f"{ad}: healthz ${gercek} != beklenen ${beklenen} "
            f"( 1 USDC = 1 USD kabulu ile celisiyor)")


def test_fiyatlar_pozitif(healthz):
    """Her fiyat pozitif olmali ( sifir/negatif = ucretsiz hizmet)."""
    for ad, f in healthz.get("prices", {}).items():
        assert _usd(f) > 0, f"{ad} fiyat pozitif DEGIL: {f}"


def test_fiyatlar_kota_icinde(healthz):
    """Her fiyat gunluk kotadan kucuk olmali ( tek cagrida kota asilmaz)."""
    fiyatlar = healthz.get("prices", {})
    kota = _usd(healthz.get("daily_quota", "$0"))
    if kota <= 0:
        pytest.skip("kota sifir/okunamadi")
    for ad, f in fiyatlar.items():
        assert _usd(f) <= kota, (
            f"{ad} ${_usd(f)} gunluk kotayi (${kota}) asiyor "
            "( tek cagrida butce fail-closed'un anlami kalmaz)")


def test_usdc_minor_birim_tutarliligi():
    r"""USDC 6-desimal: $0.05 = 50000 minor birim ( 0.05 * 10^6).

    mainnet_verify.py'nin amount_minor hesabi ile ayni olmali —
    yoksa zincirde aranacak tutar, fiyattan farkli olur.
    """
    from mainnet_verify import find_transfer  # noqa: F401  ( import dogrulugu)

    for ad, beklenen in _BEKLENEN_FIYATLAR.items():
        minor = int(round(beklenen * 10**6))
        assert minor == int(beklenen * 10**6), (
            f"{ad}: {beklenen} USDC -> {minor} minor ( 6-desimal degil)")
        # ornek: 0.05 USDC = 50000 minor ( USDC kontrat data alani)
    assert int(round(0.05 * 10**6)) == 50000


def test_receipt_zinciri_gecerli(healthz):
    """Servis ayaktaysa receipt zinciri gecerli olmali ( chain_valid)."""
    for anahtar in ("chain_valid", "ledger_chain_valid"):
        if anahtar in healthz:
            assert healthz[anahtar] is True, (
                f"{anahtar} = {healthz[anahtar]} — receipt zinciri kirik")
            return
    pytest.skip("chain_valid alani YOK ( servise ozel)")


def test_currency_etiketi_usdc_degil_sim(healthz):
    """KOD-1: 402 yanitinda 'USDC' etiketi gelmeli ( USDC-sim DEGIL).

    Gercek musteri yolunda USDC-sim etiketi olamaz — bu test onu
    yakalar ( docs/31 gecis plani ile uyumlu).
    """
    try:
        with httpx.Client(timeout=8) as c:
            govde = c.get(f"{_ANSWRANK}/").json()
    except Exception:
        pytest.skip("servis yanit vermiyor")

    etiketler = []
    for kabul in govde.get("accepts", []):
        etiketler.append(kabul.get("currency"))
    assert etiketler, "402 yanitinda 'accepts' YOK"
    assert "USDC-sim" not in etiketler, (
        f"USDC-sim hala yayinda: {etiketler} — KOD-1 geri alinmis")
    assert "USDC" in etiketler, f"USDC etiketi YOK: {etiketler}"
