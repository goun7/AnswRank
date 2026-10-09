"""mainnet_verify.find_transfer dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: _rpc monkeypatch edilir (gerçek node YOK).
"""
import pytest

import mainnet_verify as mv

_LATEST = 100000


class _FakeRPC:
    def __init__(self, logs_by_block=None, fail=None,
                 fail_times=1):
        self.calls = []
        self.logs = logs_by_block or []
        self.fail = fail
        self.fail_times = fail_times
        self._fails = 0

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "eth_blockNumber":
            return hex(_LATEST)
        if method == "eth_getLogs":
            if self.fail and self._fails < self.fail_times:
                self._fails += 1
                raise mv.RPCError(self.fail)
            return self.logs
        return []


def _patch(monkeypatch, **kw):
    rpc = _FakeRPC(**kw)
    monkeypatch.setattr(mv, "_rpc", rpc)
    return rpc


def _log(value=1000, tx="0xabc", block=99900,
         data=None):
    return {
        "transactionHash": tx,
        "blockNumber": hex(block),
        "data": data if data is not None else hex(value),
        "topics": [],
    }


# -- temel ---------------------------------------------------------------------------------

def test_returns_transfer_found(monkeypatch):
    _patch(monkeypatch)
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1000)
    assert isinstance(r, mv.TransferFound)


def test_not_found_false(monkeypatch):
    _patch(monkeypatch)
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1000)
    assert r.found is False


def test_found_true(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(1000)])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1000)
    assert r.found is True


def test_tx_hash_returned(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(1000, tx="0xdead")])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1000)
    assert r.tx_hash == "0xdead"


def test_amount_returned(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(777)])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=777)
    assert r.amount_minor == 777


def test_detail_string(monkeypatch):
    _patch(monkeypatch)
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)
    assert isinstance(r.detail, str)


# -- rpc akis ---------------------------------------------------------------------------------

def test_block_number_called(monkeypatch):
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    assert rpc.calls[0][0] == "eth_blockNumber"


def test_getlogs_called(monkeypatch):
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    assert rpc.calls[1][0] == "eth_getLogs"


def test_confirmed_blocks_excluded(monkeypatch):
    """hi = latest - CONFIRMED_BLOCKS."""
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    to_block = int(rpc.calls[1][1][0]["toBlock"], 16)
    assert to_block == _LATEST - mv.CONFIRMED_BLOCKS


def test_max_blocks_bounds_lo(monkeypatch):
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20,
                     amount_minor=1, max_blocks=500)
    lo = int(rpc.calls[1][1][0]["fromBlock"], 16)
    assert lo >= _LATEST - 500 - mv.CONFIRMED_BLOCKS


def test_topics_include_addresses(monkeypatch):
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    topics = rpc.calls[1][1][0]["topics"]
    assert mv._addr_topic("0x" + "aa" * 20) in topics
    assert mv._addr_topic("0x" + "bb" * 20) in topics


def test_transfer_topic_included(monkeypatch):
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    assert mv.TRANSFER_TOPIC in rpc.calls[1][1][0]["topics"]


def test_usdc_contract_target(monkeypatch):
    rpc = _patch(monkeypatch)
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    assert rpc.calls[1][1][0]["address"] == mv.USDC_CONTRACT


# -- eslesme ---------------------------------------------------------------------------------

def test_amount_mismatch_not_found(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(999)])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1000)
    assert r.found is False


def test_second_log_matches(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(1), _log(42)])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=42)
    assert r.found is True


def test_first_match_wins(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(42, tx="0x1"),
                                       _log(42, tx="0x2")])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=42)
    assert r.tx_hash == "0x1"


def test_detail_has_block_number(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(5, block=55555)])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=5)
    assert "55555" in r.detail


def test_zero_amount_found(monkeypatch):
    _patch(monkeypatch, logs_by_block=[_log(0)])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=0)
    assert r.found is True


# -- hata durumlaru ---------------------------------------------------------------------------------

def test_max_results_error_narrows(monkeypatch):
    rpc = _patch(monkeypatch, fail="max results exceeded")
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)
    assert len(rpc.calls) >= 2
    assert rpc.calls[-1][0] == "eth_getLogs"


def test_max_results_too_far_returns_false(monkeypatch):
    """Daraltilmis chunk lo'nun altina dustugunde False."""
    rpc = _patch(monkeypatch, fail="max results exceeded")
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1, max_blocks=50)
    assert r.found is False


def test_other_rpc_error_propagates(monkeypatch):
    _patch(monkeypatch, fail="node down")
    with pytest.raises(mv.RPCError):
        mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)


def test_case_insensitive_error_msg(monkeypatch):
    """'Max Results' buyuk harfle de daraltir."""
    rpc = _patch(monkeypatch, fail="Max Results limit")
    mv.find_transfer(from_addr="0x" + "aa" * 20,
                     to_addr="0x" + "bb" * 20, amount_minor=1)
    assert len(rpc.calls) >= 2


# -- tekrar / veri ---------------------------------------------------------------------------------

def test_data_field_parsing(monkeypatch):
    """data '0x' + 64 hex karakterlik value."""
    _patch(monkeypatch, logs_by_block=[
        {"transactionHash": "0xz", "blockNumber": hex(1),
         "data": "0x" + "0" * 63 + "3", "topics": []}])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=3)
    assert r.found is True


def test_repeatable_not_found(monkeypatch):
    _patch(monkeypatch)
    a = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)
    b = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)
    assert a.found == b.found


def test_detail_mentions_addresses(monkeypatch):
    _patch(monkeypatch)
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)
    assert "aaaa" in r.detail


def test_empty_logs_not_found(monkeypatch):
    _patch(monkeypatch, logs_by_block=[])
    r = mv.find_transfer(from_addr="0x" + "aa" * 20,
                         to_addr="0x" + "bb" * 20,
                         amount_minor=1)
    assert r.found is False
