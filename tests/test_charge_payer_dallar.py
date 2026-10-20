"""x402_servis._charge + _payer dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (FakeLedger stub + FakeRequest, dis cagri YOK).
_charge: odeme-kaniti ledger hash-chain; _payer: X-Payer-Address header.
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


class FakeLedger:
    def __init__(self, result=None, raises=None):
        self.result = result if result is not None else {"seq": 7}
        self.raises = raises
        self.calls = []

    def append(self, event_type, agent_id, resource, amount, **kw):
        self.calls.append((event_type, agent_id, resource, amount, kw))
        if self.raises is not None:
            raise self.raises
        return self.result


@pytest.fixture()
def ledger(monkeypatch):
    l = FakeLedger()
    monkeypatch.setattr(xs, "ledger", l)
    return l


class FakeReq:
    def __init__(self, payer=None):
        self.headers = {}
        if payer is not None:
            self.headers["X-Payer-Address"] = payer


# == _charge: temel =========================================================================

def test_charge_seq_donar(ledger):
    assert xs._charge(FakeReq(), 0.25, "audit", {}) == 7


def test_charge_ledger_cagrilir(ledger):
    xs._charge(FakeReq(), 0.25, "audit", {})
    assert len(ledger.calls) == 1


def test_charge_event_type(ledger):
    xs._charge(FakeReq(), 0.25, "audit", {})
    assert ledger.calls[0][0] == "charge_receipt"


def test_charge_agent_buyer(ledger):
    xs._charge(FakeReq(), 0.25, "audit", {})
    assert ledger.calls[0][1] == "buyer"


def test_charge_tool_resource(ledger):
    xs._charge(FakeReq(), 0.25, "audit", {"x": 1})
    assert ledger.calls[0][2] == "audit"


def test_charge_price_amount(ledger):
    xs._charge(FakeReq(), 0.75, "citations", {})
    assert ledger.calls[0][3] == 0.75


def test_charge_detail_payload(ledger):
    xs._charge(FakeReq(), 0.20, "fix", {"url": "x.com"})
    assert ledger.calls[0][4]["payload"] == {"url": "x.com"}


def test_charge_returns_int(ledger):
    assert isinstance(xs._charge(FakeReq(), 1.0, "t", {}), int)


# == _charge: seq-alternatifleri ===============================================================

def test_seq_sifir(ledger):
    ledger.result = {"seq": 0}
    assert xs._charge(FakeReq(), 1.0, "t", {}) == 0


def test_seq_buyuk(ledger):
    ledger.result = {"seq": 999999}
    assert xs._charge(FakeReq(), 1.0, "t", {}) == 999999


def test_seq_eksik_negatif_bir(ledger):
    """ORTAM: seq anahtar YOKSA -> -1."""
    ledger.result = {}
    assert xs._charge(FakeReq(), 1.0, "t", {}) == -1


def test_none_dict_negatif_bir(ledger):
    """ORTAM: append None donerse -> -1."""
    ledger.result = None
    assert xs._charge(FakeReq(), 1.0, "t", {}) == -1


def test_list_result_negatif_bir(ledger):
    ledger.result = [1, 2]
    assert xs._charge(FakeReq(), 1.0, "t", {}) == -1


def test_seq_string(ledger):
    """ORTAM: seq string ise string doner (type-check YOK)."""
    ledger.result = {"seq": "abc"}
    assert xs._charge(FakeReq(), 1.0, "t", {}) == "abc"


def test_istisna_yayilir(ledger):
    ledger.raises = RuntimeError("ledger-down")
    with pytest.raises(RuntimeError):
        xs._charge(FakeReq(), 1.0, "t", {})


def test_keyerror_yayilir(ledger):
    ledger.raises = KeyError("k")
    with pytest.raises(KeyError):
        xs._charge(FakeReq(), 1.0, "t", {})


# == _charge: cesitli payload ===================================================================

@pytest.mark.parametrize("detail", [{}, {"a": 1}, {"x": "y", "z": [1, 2]},
                                    {"unicode": "Türkçe"}, {"emoji": "🤖"}])
def test_payload_korumali(ledger, detail):
    xs._charge(FakeReq(), 1.0, "t", detail)
    assert ledger.calls[0][4]["payload"] == detail


def test_fiyat_sifir(ledger):
    xs._charge(FakeReq(), 0.0, "free", {})
    assert ledger.calls[0][3] == 0.0


def test_fiyat_negatif(ledger):
    """ORTAM: negatif-fiyat kontrolu YOK."""
    xs._charge(FakeReq(), -1.0, "t", {})
    assert ledger.calls[0][3] == -1.0


def test_fiyat_buyuk(ledger):
    xs._charge(FakeReq(), 1e9, "t", {})
    assert ledger.calls[0][3] == 1e9


def test_cok_cagri_artar(ledger):
    assert xs._charge(FakeReq(), 1.0, "t", {}) == 7
    assert xs._charge(FakeReq(), 1.0, "t", {}) == 7
    assert len(ledger.calls) == 2


def test_bos_tool(ledger):
    xs._charge(FakeReq(), 1.0, "", {})
    assert ledger.calls[0][2] == ""


def test_turkce_tool(ledger):
    xs._charge(FakeReq(), 1.0, "denetim", {})
    assert ledger.calls[0][2] == "denetim"


def test_para_birimi_payload(ledger):
    xs._charge(FakeReq(), 0.25, "audit", {"currency": "TRY"})
    assert ledger.calls[0][4]["payload"]["currency"] == "TRY"


def test_request_kullanilmaz(ledger):
    """ORTAM: _charge request'i OKUMAZ (middleware oncelikli)."""
    xs._charge(FakeReq(), 1.0, "t", {})
    assert ledger.calls[0][0] == "charge_receipt"


# == _payer: temel ===============================================================================

def test_payer_donar():
    assert xs._payer(FakeReq("0xabc123")) == "0xabc123"


def test_payer_default_isaret():
    assert xs._payer(FakeReq()) == "?"


def test_payer_returns_str():
    assert isinstance(xs._payer(FakeReq("0x")), str)


def test_payer_bos_header():
    assert xs._payer(FakeReq()) == "?"


def test_payer_unicode():
    assert xs._payer(FakeReq("Türkçe")) == "Türkçe"


def test_payer_emoji():
    assert xs._payer(FakeReq("🤖")) == "🤖"


def test_payer_bos_string():
    assert xs._payer(FakeReq("")) == ""


def test_payer_uzun_kirpilir():
    """ORTAM: [:42] ile kirpilir (42-karakter EOA uzunlugu)."""
    a = "0x" + "a" * 100
    assert xs._payer(FakeReq(a)) == a[:42]


def test_payer_none_header():
    class R:
        headers = {"X-Payer-Address": None}
    """ORTAM: str(None) -> 'None'."""
    assert xs._payer(R()) == "None"


def test_payer_int_header():
    class R:
        headers = {"X-Payer-Address": 42}
    assert xs._payer(R()) == "42"


def test_payer_exception_isaret():
    class Bad:
        headers = None
    """headers.get exception -> '?'."""
    assert xs._payer(Bad()) == "?"


def test_payer_no_headers_attr():
    class R:
        pass
    assert xs._payer(R()) == "?"


def test_payer_repeatable():
    r = FakeReq("0xdead")
    assert xs._payer(r) == xs._payer(r)


def test_payer_case_sensitive_header():
    """ORTAM: buyuk-kucuk hassas header."""
    class R:
        headers = {"x-payer-address": "0xl"}
    assert xs._payer(R()) == "?"


@pytest.mark.parametrize("addr", ["0x" + "a" * 40, "0x" + "f" * 40,
                                  "short", ""])
def test_payer_matrix(addr):
    assert xs._payer(FakeReq(addr)) == addr
