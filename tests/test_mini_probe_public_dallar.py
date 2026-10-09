"""api.mini_probe_public dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: MiniProbe + db stub, temp hits dict.
"""
import asyncio
import time

import pytest
from fastapi import HTTPException

import answrank.api.app as api_app
from answrank.api.app import MiniProbeRequest, mini_probe_public


class _Result:
    def model_dump(self):
        return {"domain": "ornek.com", "robots": True,
                "llms": False, "citations": []}


class _FakeReq:
    def __init__(self, host="1.2.3.4"):
        class _C:
            pass
        c = _C()
        c.host = host
        self.client = c


@pytest.fixture
def stubs(monkeypatch):
    calls = {"run": [], "leads": []}

    class _MP:
        @staticmethod
        async def run(domain):
            calls["run"].append(domain)
            return _Result()

    class _DB:
        @staticmethod
        async def save_miniprobe_lead(result):
            calls["leads"].append(result)

    monkeypatch.setitem(__import__("sys").modules,
                        "answrank.probe.miniprobe",
                        type("M", (), {"MiniProbe": _MP}))
    monkeypatch.setattr(api_app, "db", _DB())
    monkeypatch.setattr(api_app, "_miniprobe_hits", {})
    return calls


def _run(domain="ornek.com", host="1.2.3.4"):
    req = MiniProbeRequest(domain=domain)
    return asyncio.run(mini_probe_public(req, _FakeReq(host)))


# -- temel ---------------------------------------------------------------------------------

def test_returns_dict(stubs):
    assert isinstance(_run(), dict)


def test_returns_model_dump(stubs):
    assert _run() == _Result().model_dump()


def test_domain_echoed(stubs):
    assert _run()["domain"] == "ornek.com"


# -- MiniProbe cagrisi ---------------------------------------------------------------------------------

def test_run_called_with_domain(stubs):
    _run("abc.com")
    assert stubs["run"] == ["abc.com"]


def test_run_called_once(stubs):
    _run()
    assert len(stubs["run"]) == 1


def test_run_failure_500(stubs, monkeypatch):
    class _Boom:
        @staticmethod
        async def run(domain):
            raise RuntimeError("backend-down")
    monkeypatch.setitem(__import__("sys").modules,
                        "answrank.probe.miniprobe",
                        type("M", (), {"MiniProbe": _Boom}))
    with pytest.raises(HTTPException) as e:
        _run()
    assert e.value.status_code == 500


# -- lead kaydetme ---------------------------------------------------------------------------------

def test_lead_saved(stubs):
    _run()
    assert len(stubs["leads"]) == 1


def test_lead_saved_after_run(stubs):
    _run()
    assert stubs["leads"][0] is not None


def test_lead_not_saved_on_failure(stubs, monkeypatch):
    class _Boom:
        @staticmethod
        async def run(domain):
            raise RuntimeError("x")
    monkeypatch.setitem(__import__("sys").modules,
                        "answrank.probe.miniprobe",
                        type("M", (), {"MiniProbe": _Boom}))
    with pytest.raises(HTTPException):
        _run()
    assert len(stubs["leads"]) == 0


# -- rate limit ---------------------------------------------------------------------------------

def test_no_limit_under_cap(stubs):
    for _ in range(9):
        _run()
    assert len(stubs["run"]) == 9


def test_limit_blocks_10th(stubs):
    for _ in range(10):
        _run()
    with pytest.raises(HTTPException) as e:
        _run()
    assert e.value.status_code == 429


def test_limit_detail_turkce(stubs):
    for _ in range(10):
        _run()
    with pytest.raises(HTTPException) as e:
        _run()
    assert "limit" in str(e.value.detail).lower()


def test_limit_per_ip(stubs):
    for _ in range(10):
        _run(host="1.1.1.1")
    # baska IP hala kullanabilir
    _run(host="2.2.2.2")
    assert len(stubs["run"]) == 11


def test_limit_counts_same_ip_only(stubs):
    for i in range(5):
        _run(host=f"10.0.0.{i}")
    assert len(stubs["run"]) == 5


def test_expired_hits_pruned(stubs, monkeypatch):
    monkeypatch.setattr(api_app, "_miniprobe_hits", {
        "1.1.1.1": [time.time() - 100000] * 10})
    _run(host="1.1.1.1")
    assert len(stubs["run"]) == 1


def test_recent_hit_blocks(stubs):
    for _ in range(10):
        _run(host="3.3.3.3")
    with pytest.raises(HTTPException):
        _run(host="3.3.3.3")
    assert len(stubs["run"]) == 10


# -- client None ---------------------------------------------------------------------------------

def test_no_client_uses_anonymous(stubs):
    req = MiniProbeRequest(domain="x.com")
    asyncio.run(mini_probe_public(req, type("R", (), {"client": None})()))
    assert len(stubs["run"]) == 1


def test_anonymous_ip_separate_bucket(stubs):
    req = MiniProbeRequest(domain="x.com")
    asyncio.run(mini_probe_public(req, type("R", (), {"client": None})()))
    assert "anonymous" in api_app._miniprobe_hits


# -- domain dogrulama ---------------------------------------------------------------------------------

def test_short_domain_rejected():
    with pytest.raises(Exception) as e:
        MiniProbeRequest(domain="a")
    assert "domain" in str(e.value).lower() or "short" in \
        str(e.value).lower()


def test_empty_domain_rejected():
    with pytest.raises(Exception):
        MiniProbeRequest(domain="")


def test_valid_domain_accepted():
    assert MiniProbeRequest(domain="ornek.com").domain == \
        "ornek.com"


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(stubs):
    assert _run() == _run()


def test_two_domains_two_runs(stubs):
    _run("a.com")
    _run("b.com")
    assert stubs["run"] == ["a.com", "b.com"]
