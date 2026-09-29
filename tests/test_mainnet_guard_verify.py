#!/usr/bin/env python3
"""mainnet_guard + mainnet_verify entegrasyon testleri ( 85-AnswRank).

KAPSAM — Unpump <-> PQHaven guard bagi mainnet-ready mi:
  1. resolve_treasury: tek-kasa fail-closed ( treasury yok -> SystemExit)
  2. _valid_eoa: gecersiz adres -> SystemExit ( yanlis-adres riski = 0)
  3. require_mainnet_payment: zincirde transfer YOK -> 402 fail-closed
  4. require_mainnet_payment: transfer VAR -> payer doner
  5. sandbox whitelist'li payer zincir aramasindan muaf ( demo)
  6. UNPUMP_TEST=1 -> zincir aramaz ( sim modu)

⚠ DURUST ETIKET: bu testler mainnet_verify'in **gercek RPC'sini**
  network'e dokunmadan test etmek icin verify fonksiyonunu degistirir
  ( monkeypatch). Gercek RPC call'i ayrica manuel kanitlandi:
  verify_mainnet_payment(0x...dEaD -> treasury, $0.05) = found False
  ( son 5000 blokta transfer yok) — base.publicnode.com canli.
"""
from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

import mainnet_guard as mg
import mainnet_verify as mv

_TREASURY = "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"
_PAYER = "0x" + "11" * 20
_OTHER = "0x" + "22" * 20


class _FakeReq:
    """Starlette Request'in header kismi ( require_mainnet_payment icin)."""

    def __init__(self, payer=None):
        self.headers = {}
        if payer:
            self.headers["x-payer-address"] = payer
        self.state = type("S", (), {"sandbox": False})()


@pytest.fixture
def chain_verify(monkeypatch):
    """verify_mainnet_payment'i testte iki-modlu yap: found ayarlanabilir."""

    state = {"found": False, "detail": "mock: zincirde transfer yok"}

    def _fake(**kwargs):
        return mv.TransferFound(found=state["found"],
                                detail=state["detail"])

    monkeypatch.setattr(mv, "verify_mainnet_payment", _fake)
    return state


@pytest.fixture
def mainnet_mode(monkeypatch):
    """mainnet modu acik: UNPUMP_TEST=0, ANSWRANK_MAINNET=1, sandbox bos."""
    monkeypatch.setenv("UNPUMP_TEST", "0")
    monkeypatch.setenv("ANSWRANK_MAINNET", "1")
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "")
    monkeypatch.setenv("UNPUMP_SANDBOX", "1")


# --- 1. resolve_treasury: tek-kasa fail-closed ---

def test_treasury_yoksa_servis_baslamaz(monkeypatch):
    """Treasury EOA yoksa SystemExit — servis ödeme-hedefisiz baslayamaz."""
    monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
    monkeypatch.delenv("ANSWRANK_MAINNET_PAY_TO", raising=False)
    with pytest.raises(SystemExit):
        mg.resolve_treasury("answrank")


def test_treasury_cozulur(monkeypatch):
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", _TREASURY)
    assert mg.resolve_treasury("answrank") == _TREASURY


def test_treasury_gecersiz_eoa_systemexit(monkeypatch):
    """HEAD 2b56e09: gecersiz EOA -> SystemExit ( yanlis-adrese odeme riski)."""
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", "0x123")
    with pytest.raises(SystemExit):
        mg.resolve_treasury("answrank")


def test_treasury_legacy_fallback(monkeypatch):
    """UNPUMP_TREASURY_EOA bossa <SVC>_MAINNET_PAY_TO geri-uyum."""
    monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
    monkeypatch.setenv("ANSWRANK_MAINNET_PAY_TO", _OTHER)
    assert mg.resolve_treasury("answrank") == _OTHER


# --- 2. require_mainnet_payment: zincir dogrulama ---

def test_odeme_yoksa_402_fail_closed(mainnet_mode, chain_verify):
    """Zincirde transfer YOK -> 402 ( imza yetmez; fail-closed)."""
    chain_verify["found"] = False
    with pytest.raises(HTTPException) as exc:
        mg.require_mainnet_payment(
            _FakeReq(_PAYER), price=0.05, pay_to=_TREASURY,
            service_name="answrank")
    assert exc.value.status_code == 402
    assert "payment_required" in str(exc.value.detail)


def test_odeme_varsa_payer_doner(mainnet_mode, chain_verify):
    """Zincirde transfer bulundu -> payer adresi dogrulanmis doner."""
    chain_verify["found"] = True
    chain_verify["detail"] = "mock: transfer bulundu"
    payer = mg.require_mainnet_payment(
        _FakeReq(_PAYER), price=0.05, pay_to=_TREASURY,
        service_name="answrank")
    assert payer == _PAYER


def test_payer_header_yoksa_402(mainnet_mode, chain_verify):
    """X-Payer-Address yok -> mainnet modunda 402."""
    with pytest.raises(HTTPException) as exc:
        mg.require_mainnet_payment(
            _FakeReq(), price=0.05, pay_to=_TREASURY,
            service_name="answrank")
    assert exc.value.status_code == 402


def test_rpc_hatasi_503_fail_closed(mainnet_mode, monkeypatch):
    """RPC hatasi -> 503 ( fail-closed: sonuclar yokken hizmet ACILMAZ)."""

    def _raise(**kwargs):
        raise mv.RPCError("mock: RPC ulasilamadi")

    monkeypatch.setattr(mv, "verify_mainnet_payment", _raise)
    with pytest.raises(HTTPException) as exc:
        mg.require_mainnet_payment(
            _FakeReq(_PAYER), price=0.05, pay_to=_TREASURY,
            service_name="answrank")
    assert exc.value.status_code == 503
    assert "fail-closed" in str(exc.value.detail)


# --- 3. sandbox: whitelist'li payer zincir aramasindan muaf ---

def test_sandbox_payer_zincir_aramaz(mainnet_mode, monkeypatch):
    """Sandbox whitelist'li demo anahtar zincir aramasini atlar ( demo)."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", _PAYER)
    cagrildi = {"n": 0}

    def _izle(**kwargs):
        cagrildi["n"] += 1
        return mv.TransferFound(found=False, detail="")

    monkeypatch.setattr(mv, "verify_mainnet_payment", _izle)
    payer = mg.require_mainnet_payment(
        _FakeReq(_PAYER), price=0.05, pay_to=_TREASURY,
        service_name="answrank")
    assert payer == _PAYER
    assert cagrildi["n"] == 0  # zincir ARANMADI ( sandbox muafiyeti)


def test_sandbox_payer_isaretlenir(mainnet_mode, monkeypatch):
    """Sandbox payer request.state.sandbox=True isaretlenir ( analytics)."""
    monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", _PAYER)
    req = _FakeReq(_PAYER)
    mg.require_mainnet_payment(
        req, price=0.05, pay_to=_TREASURY, service_name="answrank")
    assert req.state.sandbox is True


# --- 4. test/sim modu: zincir aramaz ---

def test_unpump_test_mod_zincir_aramaz(monkeypatch):
    """UNPUMP_TEST=1 -> verify_mainnet_payment hic cagrilmaz."""
    monkeypatch.setenv("UNPUMP_TEST", "1")
    monkeypatch.setenv("ANSWRANK_MAINNET", "1")
    cagrildi = {"n": 0}

    def _izle(**kwargs):
        cagrildi["n"] += 1
        return mv.TransferFound(found=True, detail="")

    monkeypatch.setattr(mv, "verify_mainnet_payment", _izle)
    sonuc = mg.require_mainnet_payment(
        _FakeReq(_PAYER), price=0.05, pay_to=_TREASURY,
        service_name="answrank")
    assert sonuc is None  # test modu: None ( payer dogrulanmadi)
    assert cagrildi["n"] == 0


# --- 5. mainnet_verify: API sabitleri ( kanit zinciri) ---

def test_usdc_contract_base_mainnet():
    """USDC kontratu Base mainnet ( 6 decimal) — PQHaven ile ayni olmali."""
    assert mv.USDC_CONTRACT.lower() == \
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_rpc_base_publicnode():
    """RPC Base publicnode — rate-limit'e dayanikli."""
    assert "base" in mv.RPC_URL and "publicnode" in mv.RPC_URL


def test_transfer_topic_keccak():
    """Transfer(address,address,uint256) event topic — keccak256 sabiti."""
    assert mv.TRANSFER_TOPIC.startswith("0xddf252ad")


def test_transfer_found_dataclass():
    """TransferFound veri yapisi guard ile uyumlu ( found + detail)."""
    t = mv.TransferFound(found=True, detail="test")
    assert t.found is True
    assert t.detail == "test"
