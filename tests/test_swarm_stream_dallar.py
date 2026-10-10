"""api.app:stream_swarm_execution + run_pipeline dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: TestClient + SwarmOrchestrator stub (gercek ag YOK).
"""
import asyncio
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

_HERE = __file__
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(_HERE))), "izleyici"))

from answrank.api import app as answ_app  # noqa: E402


class _Candidate:
    from answrank.agents.swarm import SwarmStage
    brand_name = "TEST"
    domain = "example.com"
    city = "Istanbul"
    country = "TR"
    stage = SwarmStage.OUTREACH_SENT

    def __getattr__(self, name):
        return "STUB"


class _OrchStub:
    candidate = _Candidate()
    events = []
    raises = None

    def seed_target(self, **kw):
        _OrchStub.seen = kw
        _OrchStub.candidate = _Candidate()
        for k, v in kw.items():
            setattr(_OrchStub.candidate, k, v)
        return _OrchStub.candidate

    async def run_full_pipeline_sync(self, candidate, on_event=None):
        if _OrchStub.raises:
            raise _OrchStub.raises
        for ev in _OrchStub.events:
            if on_event:
                await on_event(ev[0], ev[1])
        return None

    def get_territory_locks(self):
        return []


@pytest.fixture
def client(monkeypatch):
    import answrank.agents.swarm as swarm_mod
    monkeypatch.setattr(swarm_mod, "SwarmOrchestrator", _OrchStub)
    _OrchStub.events = [("AGENT1", "step1"), ("AGENT2", "step2")]
    _OrchStub.raises = None
    _OrchStub.seen = {}
    return TestClient(answ_app.app)


def _stream(client, **kw):
    params = {"brand": "B", "domain": "d.example"}
    params.update(kw)
    return client.get("/api/swarm/stream", params=params)


def _events(body_text):
    out = []
    for chunk in body_text.split("data: "):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    return out


# -- temel ---------------------------------------------------------------------------------

def test_stream_status_200(client):
    assert _stream(client).status_code == 200


def test_stream_content_type(client):
    assert "text/event-stream" in _stream(client).headers.get(
        "content-type", "")


def test_stream_has_events(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    assert len(_events(body)) >= 3


def test_event_keys(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    for ev in _events(body):
        assert set(ev) == {"agent", "message", "timestamp"}


def test_agent_events_streamed(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    agents = [e["agent"] for e in _events(body)]
    assert "AGENT1" in agents
    assert "AGENT2" in agents


def test_messages_streamed(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    msgs = [e["message"] for e in _events(body)]
    assert "step1" in msgs


def test_timestamp_iso(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    ts = _events(body)[0]["timestamp"]
    assert "T" in ts and ts.endswith("+00:00") or "Z" in ts


# -- PIPELINE_DONE ---------------------------------------------------------------------------------

def test_done_event_last(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = _events(body)
    assert evs[-1]["agent"] == "PIPELINE_DONE"


def test_done_message_has_brand(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = _events(body)
    assert "Pipeline finished" in evs[-1]["message"]
    assert "B" in evs[-1]["message"]


def test_done_before_done_events(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = _events(body)
    assert len(evs) >= 3
    assert evs[-2]["agent"] == "AGENT2"


# -- PIPELINE_ERROR ---------------------------------------------------------------------------------

def test_error_event_on_failure(client):
    _OrchStub.raises = ValueError("boom")
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = _events(body)
    assert any(e["agent"] == "PIPELINE_ERROR" for e in evs)


def test_error_message_has_type(client):
    _OrchStub.raises = ValueError("boom")
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = [e for e in _events(body) if e["agent"] == "PIPELINE_ERROR"]
    assert "ValueError" in evs[0]["message"]
    assert "boom" in evs[0]["message"]


def test_error_no_done_event(client):
    _OrchStub.raises = RuntimeError("x")
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = _events(body)
    assert all(e["agent"] != "PIPELINE_DONE" for e in evs)


def test_error_sentinel_ends_stream(client):
    _OrchStub.raises = OSError("net")
    body = _stream(client).content.decode("utf-8", errors="replace")
    assert body.count("data: ") >= 1


# -- parametreler ---------------------------------------------------------------------------------

def test_city_param(client):
    _OrchStub.events = [("CITY", "Izmir")]
    body = _stream(client, city="Izmir").content.decode(
        "utf-8", errors="replace")
    evs = _events(body)
    assert evs[0]["agent"] == "CITY"


def test_country_param(client):
    _OrchStub.events = [("CTRY", "DE")]
    body = _stream(client, country="DE").content.decode(
        "utf-8", errors="replace")
    evs = _events(body)
    assert evs[0]["message"] == "DE"


def test_default_city(client):
    """city default 'Lond...'? brand/domain zorunlu."""
    body = _stream(client).content.decode("utf-8", errors="replace")
    assert "PIPELINE_DONE" in body


# -- seed_target cagrisi ---------------------------------------------------------------------------------

def test_seed_target_called(client):
    _OrchStub.seen = {}
    _stream(client)
    assert _OrchStub.seen.get("brand_name") == "B"
    assert _OrchStub.seen.get("domain") == "d.example"
    assert _OrchStub.seen.get("city") != "B"


# -- event formati ---------------------------------------------------------------------------------

def test_sse_prefix_data(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    assert body.startswith("data: ")


def test_sse_double_newline(client):
    body = _stream(client).content.decode("utf-8", errors="replace")
    assert "\n\n" in body


def test_unicode_preserved(client):
    _OrchStub.events = [("TR", "Türkçe mesaj")]
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = [e for e in _events(body) if e["agent"] == "TR"]
    assert evs[0]["message"] == "Türkçe mesaj"


# -- bos event listesi ---------------------------------------------------------------------------------

def test_no_events_still_done(client):
    _OrchStub.events = []
    body = _stream(client).content.decode("utf-8", errors="replace")
    evs = _events(body)
    assert evs[-1]["agent"] == "PIPELINE_DONE"
    assert len(evs) == 1


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(client):
    a = _stream(client).content
    b = _stream(client).content
    ea = _events(a.decode("utf-8", errors="replace"))
    eb = _events(b.decode("utf-8", errors="replace"))
    assert [e["agent"] for e in ea] == [e["agent"] for e in eb]
