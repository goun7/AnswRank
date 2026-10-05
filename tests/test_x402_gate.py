"""Tests for the AnswRank <-> Sester x402 payment gate (mesh code bond).

Mesh recetesi: "85-AnswRank -- MCP server'a SADECE Sester sarmasi
gerekiyor" (PORTFOY_SINERJI_HARITASI_2026-09-24.md S7.0.2).

KAPSAM:
  1. ucretsiz mod (secret yok) -- kapı etkisiz, mevcut davranis korunur
  2. odemeli sim modu -- makbuz dogrulanir, ledger'a charge yazilir,
     anchor hash teslimat kaniiti olur, hash-zincir gecerli
  3. fail-closed mainnet -- makbuz yok/yanlis ve zincirde transfer yok
     durumlarinda PaymentRequired (sifir-odeme bypass kapali)
  4. MCP butunlesme -- ucretli arac kapidan gecer, 402 sebebi istemciye
     acilir, odeme ucretsiz modda yanitta acikca etiketlenir

MAINNET YASAK: zincir dogrulayici TAKLIT EDILIR -- hicbir test ana aga
baglanmaz (mesh kurali; mainnet_verify.py'nin gercek RPC'si kullanilmaz).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from answrank.x402_gate import (
    SesterPaymentGate, PaymentRequired, WeakSecretError, Charge,
)
from answrank.mcp.server import AnswRankMCPServer

_SECRET = "test-seller-secret-0123456789abcdef"
_PAYER = "0x" + "11" * 20
_PRICE = 0.05  # answrank_audit (TOOL_PRICES varsayilani)


@dataclass
class _FakeFound:
    found: bool
    detail: str = ""


def _make_receipt(db_path: str, secret: str, *, tool: str = "answrank_audit",
                  price: float = _PRICE, payer: str = _PAYER) -> dict:
    """Satici tarafinda uretilen gecerli bir Sester makbuzu (hash-zincir).

    Gercek akista alici oder, satici (ayni secret ile) makbuzu imzalar ve
    istemciye doner; istemci bunu `payment_receipt` olarak tool cagrisinda
    sunar. Burada satici ledger'i test temp'inde acilir.
    """
    from sester.ledger import Ledger
    from sester.receipt import issue_receipt

    ledger = Ledger(db_path, secret=secret)
    event = ledger.append("charge_receipt", payer, tool, price,
                          payload={"prepay": True})
    return issue_receipt(event, node_secret=secret)


# ------------------------------------------------------------------ 1. ucretsiz

def test_free_mode_when_secret_absent(tmp_path):
    """ANSWRANK_SELLER_SECRET yok -> kapı devre disi, arac ucretsiz calisir.

    Geri-uyumluluk sozlesmesi: mevcut MCP/API davranisi ve testleri bu
    yolla korunur; yanit 'free' olarak etiketlenir (no silent guessing).
    """
    gate = SesterPaymentGate(db_path=str(tmp_path / "should-not-exist.sqlite"),
                             secret="")
    assert gate.enabled is False
    assert gate.status()["mode"] == "free"

    # require() hicbir sey istemez (makbuz yokken bile)
    gate.require(tool="answrank_audit", receipt=None, payer=_PAYER)

    charge = gate.settle(tool="answrank_audit",
                         anchor={"domain": "x.com", "overall_score": 42,
                                 "score_band": "Foundation"},
                         receipt=None, payer=_PAYER)
    assert isinstance(charge, Charge)
    assert charge.mode == "free"
    assert charge.seq == 0
    assert charge.price_usdc == _PRICE
    assert "ucretsiz" in charge.note

    # ucretsiz modda HICBIR ledger dosyasi acilmaz
    assert not os.path.exists(tmp_path / "should-not-exist.sqlite")

    # anchor hash deterministik ve musteri tarafindan tekrar hesaplanabilir
    assert charge.anchor_hash == SesterPaymentGate.anchor_hash(
        {"domain": "x.com", "overall_score": 42, "score_band": "Foundation"})


def test_weak_secret_is_rejected_not_silently_ignored():
    """Zayif secret sessizce kabul edilmez -- bu repo'da daha once
    verify_chain=False'a yol acti (baska-secret ile yazilan zincir)."""
    with pytest.raises(WeakSecretError, match="cok kisa"):
        SesterPaymentGate(secret="short")
    # bos secret = ucretsiz mod (hata DEGIL)
    assert SesterPaymentGate(secret="").enabled is False


# ------------------------------------------------- 2. odemeli sim (ledger + anchor)

def test_paid_test_mode_anchors_delivery_to_ledger(tmp_path):
    """Gecerli makbuz -> require gecer, ledger'a charge yazilir, anchor
    hash teslimat kaniiti olur, hash-zincir gecerli kalir."""
    receipt = _make_receipt(str(tmp_path / "prepay.sqlite"), _SECRET)
    gate = SesterPaymentGate(db_path=str(tmp_path / "receipts.sqlite"),
                             secret=_SECRET, test_mode=True)

    assert gate.enabled is True
    assert gate.status()["mode"] == "paid-test"
    # sim modu: zincir aranmaz, makbuz HMAC dogrulamasi yeterli
    gate.require(tool="answrank_audit", receipt=receipt, payer=_PAYER)

    anchor = {"domain": "clinica.com", "overall_score": 87,
              "score_band": "Optimized"}
    charge = gate.settle(tool="answrank_audit", anchor=anchor,
                         receipt=receipt, payer=_PAYER)

    assert charge.mode == "paid-test"
    assert charge.seq > 0, "ledger'a charge yazilmali"
    assert charge.ledger_chain_valid is True
    assert charge.anchor_hash == SesterPaymentGate.anchor_hash(anchor)
    assert len(charge.receipt_hash) == 64  # sha256 hex
    assert gate.verify_chain() is True

    # makbuzdan baska secret ile imzalanmis olsaydi dogrulanmamali
    forged = dict(receipt)
    forged["node_cosign"] = "00" * 32
    with pytest.raises(PaymentRequired, match="makbuz gecersiz"):
        gate.require(tool="answrank_audit", receipt=forged, payer=_PAYER)


# ------------------------------------------------------- 3. fail-closed mainnet

@pytest.fixture
def mainnet_gate(tmp_path):
    """Mainnet modu (test DEGIL) -- zincirde transfer ZORUNLU; dogrulayici
    taklit edilir, boylece test ana aga DOKUNMAZ."""
    return SesterPaymentGate(
        db_path=str(tmp_path / "mn.sqlite"),
        secret=_SECRET,
        test_mode=False,
        chain_verifier=lambda **kw: _FakeFound(False, "mock: transfer yok"),
    )


def test_mainnet_missing_receipt_is_rejected(mainnet_gate):
    with pytest.raises(PaymentRequired, match="payment_receipt"):
        mainnet_gate.require(tool="answrank_audit", receipt=None, payer=_PAYER)


def test_mainnet_invalid_receipt_is_rejected(mainnet_gate, tmp_path):
    bad_receipt = {"not": "a-receipt"}
    with pytest.raises(PaymentRequired, match="makbuz gecersiz"):
        mainnet_gate.require(tool="answrank_audit", receipt=bad_receipt,
                             payer=_PAYER)


def test_mainnet_no_chain_transfer_is_rejected(tmp_path):
    """Imza 'odemis' dese bile zincirde USDC transferi YOKSA 402 --
    sifir-odeme bypass kapali (mainnet_guard ile ayni kural)."""
    receipt = _make_receipt(str(tmp_path / "prepay2.sqlite"), _SECRET)
    gate = SesterPaymentGate(
        db_path=str(tmp_path / "mn2.sqlite"), secret=_SECRET, test_mode=False,
        chain_verifier=lambda **kw: _FakeFound(False, "son bloklarda yok"))
    with pytest.raises(PaymentRequired, match="zincirde transfer yok"):
        gate.require(tool="answrank_audit", receipt=receipt, payer=_PAYER)


def test_mainnet_valid_chain_transfer_passes(tmp_path):
    """Zincirde transfer VAR ise require gecer -- odeme kanitlandi."""
    receipt = _make_receipt(str(tmp_path / "prepay3.sqlite"), _SECRET)
    seen = {}

    def _verifier(**kw):
        seen.update(kw)
        return _FakeFound(True, "block 123")

    gate = SesterPaymentGate(db_path=str(tmp_path / "mn3.sqlite"),
                             secret=_SECRET, test_mode=False,
                             chain_verifier=_verifier)
    gate.require(tool="answrank_audit", receipt=receipt, payer=_PAYER)
    # dogrulayici dogru argumanlarla cagrildi (dogru taraf, dogru tutar)
    assert seen["from_addr"] == _PAYER
    assert seen["amount_usd"] == _PRICE


def test_mainnet_requires_valid_payer_eoa(mainnet_gate, tmp_path):
    """Zincir aramasi icin gecerli EOA zorunlu -- '?' gibi degerler
    sessizce gecemez."""
    receipt = _make_receipt(str(tmp_path / "prepay4.sqlite"), _SECRET)
    with pytest.raises(PaymentRequired, match="gecerli bir 'payer_address'"):
        mainnet_gate.require(tool="answrank_audit", receipt=receipt,
                             payer="not-an-eoa")


# ------------------------------------------------------------- 4. MCP butunlesme

@pytest.mark.anyio
async def test_mcp_free_mode_labels_payment_in_result():
    """MCP sunucusu varsayilan (secret yok) ayarinda ucretsizdir ve yanit
    odeme durumunu acikca etiketler -- mevcut davranis ve testler korunur."""
    server = AnswRankMCPServer()
    assert server.gate.enabled is False

    result = await server.call_tool("answrank_generate_fixes", {
        "domain": "free-clinic.com", "brand": "Free Clinic", "sector": "dental",
    })
    assert "robots_txt" in result
    assert result["payment"]["mode"] == "free"
    assert result["payment"]["seq"] == 0
    assert len(result["payment"]["anchor_hash"]) == 64


@pytest.mark.anyio
async def test_mcp_paid_tool_settles_with_receipt(tmp_path):
    """Ucretli MCP araci gecerli makbuzla calisir; teslimat kaniiti
    yanita eklenir (mesh: MCP server'a Sester sarmasi)."""
    receipt = _make_receipt(str(tmp_path / "prepay5.sqlite"), _SECRET)
    server = AnswRankMCPServer()
    server.gate = SesterPaymentGate(db_path=str(tmp_path / "mcp.sqlite"),
                                    secret=_SECRET, test_mode=True)

    result = await server.call_tool("answrank_generate_fixes", {
        "domain": "paid-clinic.com", "brand": "Paid Clinic",
        "sector": "dental", "city": "İstanbul",
        "payment_receipt": receipt, "payer_address": _PAYER,
    })
    assert "robots_txt" in result
    pay = result["payment"]
    assert pay["mode"] == "paid-test"
    assert pay["seq"] > 0
    assert pay["price_usdc"] == 0.20  # generate_fixes fiyati
    # anchor, uretilen artefaktlarin SHA-256'ini tasiyor
    assert len(pay["anchor_hash"]) == 64
    from answrank.x402_gate import SesterPaymentGate as _G
    import hashlib
    digest = hashlib.sha256()
    for key in ("robots_txt", "llms_txt", "json_ld"):
        digest.update(f"{key}:{result[key]}".encode("utf-8"))
    assert pay["anchor_hash"] == _G.anchor_hash(
        {"domain": "paid-clinic.com", "sha256": digest.hexdigest()})


@pytest.mark.anyio
async def test_mcp_paid_tool_rejects_missing_receipt(tmp_path):
    """Odemeli modda makbuz yoksa arac CALISMADAN reddedilir (fail-closed):
    ucretsiz denetim hizmeti yanilgisi yok; 402 sebebi istemciye acilir."""
    server = AnswRankMCPServer()
    server.gate = SesterPaymentGate(db_path=str(tmp_path / "mcp2.sqlite"),
                                    secret=_SECRET, test_mode=True)

    with pytest.raises(ValueError, match="payment required"):
        await server.call_tool("answrank_generate_fixes",
                               {"domain": "nopay.com", "brand": "NoPay"})
