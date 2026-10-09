"""MultiLLMCitationRunner.query_openai_live dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: httpx.AsyncClient monkeypatch (gercek API YOK).
"""
import asyncio
import os
import types

import pytest

from answrank.citations.key_manager import LLMProvider
from answrank.citations.runner import MultiLLMCitationRunner


def _fake_km(key="sk-fake"):
    km = types.SimpleNamespace()
    km.get_key = lambda provider: key
    return km


class _FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class _FakeClient:
    """httpx.AsyncClient sahtesi — POST'lari kaydeder."""
    instances = []

    def __init__(self, *a, **kw):
        self.requests = []
        self.timeout = kw.get("timeout")
        _FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        self.requests.append((url, json, headers))
        if "responses" in url:
            return _FakeResp(200, self._grounded_body)
        return _FakeResp(200, self._plain_body)

def _patch_httpx(monkeypatch, grounded_body=None, plain_body=None,
                 mode="ok"):
    _FakeClient._mode = mode
    _FakeClient._grounded_body = grounded_body
    _FakeClient._plain_body = plain_body
    _FakeClient.instances.clear()

    mod = sys_mod_runner()
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeClient)


def sys_mod_runner():
    import sys
    return sys.modules["answrank.citations.runner"]


def _runner(key="sk-fake"):
    return MultiLLMCitationRunner(key_manager=_fake_km(key))


def _run(coro):
    return asyncio.run(coro)


_GROUNDED_OK = {
    "output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "Sonuc: x",
             "annotations": [
                 {"url_citation": {
                     "title": "Kaynak",
                     "url": "https://ornek.com/x"}}
             ]}
        ]}
    ]
}

_PLAIN_OK = {
    "choices": [
        {"message": {"content": "Duz metin cevap"}}
    ]
}


# -- temel ---------------------------------------------------------------------------------

def test_returns_none_without_key(monkeypatch):
    _patch_httpx(monkeypatch)
    r = _runner(key="")
    assert _run(r.query_openai_live("q")) is None


def test_key_missing_marked(monkeypatch):
    _patch_httpx(monkeypatch)
    r = _runner(key="")
    _run(r.query_openai_live("q"))
    assert r.grounding_status.get("ChatGPT-4o") is not None


def test_grounded_returns_text(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    out = _run(r.query_openai_live("merhaba"))
    assert isinstance(out, str)
    assert len(out) > 0


def test_grounded_text_content(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    assert "Sonuc: x" in _run(r.query_openai_live("q"))


def test_grounded_status_search(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    assert r.grounding_status["ChatGPT-4o"] == "search-grounded"


def test_plain_used_when_grounded_fails(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=None,
                plain_body=_PLAIN_OK)
    r = _runner()
    out = _run(r.query_openai_live("q"))
    assert "Duz metin cevap" in out


def test_plain_status_model_recall(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=None,
                plain_body=_PLAIN_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    assert r.grounding_status["ChatGPT-4o"] == "model-recall"


def test_both_fail_status_olculemedi(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=None, plain_body=None)
    r = _runner()
    out = _run(r.query_openai_live("q"))
    assert out is None
    assert r.grounding_status["ChatGPT-4o"] is not None


# -- http akisi ---------------------------------------------------------------------------------

def test_grounded_url(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    urls = [u for u, _, _ in _FakeClient.instances[0].requests]
    assert any("responses" in u for u in urls)


def test_grounded_payload(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("sorum"))
    payload = _FakeClient.instances[0].requests[0][1]
    assert payload["input"][0]["content"] == "sorum"


def test_grounded_tools_web_search(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    payload = _FakeClient.instances[0].requests[0][1]
    assert payload["tools"] == [{"type": "web_search"}]


def test_grounded_model_field(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    payload = _FakeClient.instances[0].requests[0][1]
    assert payload["model"] is not None


def test_plain_url_fallback(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=None,
                plain_body=_PLAIN_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    urls = [u for c in _FakeClient.instances
            for u, _, _ in c.requests]
    assert any("chat/completions" in u for u in urls)


def test_plain_payload_messages(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=None,
                plain_body=_PLAIN_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    payload = _FakeClient.instances[-1].requests[-1][1]
    roles = [m["role"] for m in payload["messages"]]
    assert "user" in roles


def test_auth_header_sent(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("q"))
    hdrs = _FakeClient.instances[0].requests[0][2]
    assert hdrs["Authorization"] == "Bearer sk-fake"


# -- grounding disabled ---------------------------------------------------------------------------------

def test_grounding_disabled_skips_grounded(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK,
                plain_body=_PLAIN_OK)
    r = _runner()
    monkeypatch.setattr(type(r), "GROUNDING_DISABLED", True)
    _run(r.query_openai_live("q"))
    urls = [u for u, _, _ in _FakeClient.instances[0].requests]
    assert not any("responses" in u for u in urls)


def test_grounding_disabled_uses_plain(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK,
                plain_body=_PLAIN_OK)
    r = _runner()
    monkeypatch.setattr(type(r), "GROUNDING_DISABLED", True)
    out = _run(r.query_openai_live("q"))
    assert "Duz metin cevap" in out


def test_grounding_disabled_status_model_recall(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK,
                plain_body=_PLAIN_OK)
    r = _runner()
    monkeypatch.setattr(type(r), "GROUNDING_DISABLED", True)
    _run(r.query_openai_live("q"))
    assert r.grounding_status["ChatGPT-4o"] == "model-recall"


# -- parse_live_response ---------------------------------------------------------------------------------

def test_parse_empty_data():
    from answrank.citations.runner import parse_live_response
    assert parse_live_response({}) == ("", [])


def test_parse_none_data():
    from answrank.citations.runner import parse_live_response
    assert parse_live_response(None) == ("", [])


def test_parse_text_and_source():
    from answrank.citations.runner import parse_live_response
    text, srcs = parse_live_response(_GROUNDED_OK)
    assert "Sonuc: x" in text
    assert len(srcs) == 1


def test_parse_source_url():
    from answrank.citations.runner import parse_live_response
    _, srcs = parse_live_response(_GROUNDED_OK)
    assert srcs[0][1] == "https://ornek.com/x"


def test_parse_skips_web_search_call():
    from answrank.citations.runner import parse_live_response
    data = {"output": [
        {"type": "web_search_call", "content": [
            {"type": "text", "text": "atla"}]},
        {"type": "message", "content": [
            {"type": "output_text", "text": "kalan"}]}
    ]}
    text, _ = parse_live_response(data)
    assert "atla" not in text
    assert "kalan" in text


def test_parse_bad_type_returns_empty():
    from answrank.citations.runner import parse_live_response
    assert parse_live_response("string") == ("", [])


# -- model config ---------------------------------------------------------------------------------

def test_model_from_env(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    monkeypatch.setenv("ANSWRANK_OPENAI_MODEL", "gpt-test")
    r = _runner()
    _run(r.query_openai_live("q"))
    payload = _FakeClient.instances[0].requests[0][1]
    assert payload["model"] == "gpt-test"


def test_repeatable_grounded(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    a = _run(r.query_openai_live("q"))
    b = _run(r.query_openai_live("q"))
    assert a == b


def test_two_queries_independent(monkeypatch):
    _patch_httpx(monkeypatch, grounded_body=_GROUNDED_OK)
    r = _runner()
    _run(r.query_openai_live("bir"))
    _run(r.query_openai_live("iki"))
    payloads = [p for c in _FakeClient.instances
                for _, p, _ in c.requests]
    assert payloads[0]["input"][0]["content"] == "bir"
    assert payloads[1]["input"][0]["content"] == "iki"
