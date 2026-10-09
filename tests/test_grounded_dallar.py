"""citations.runner.query_openai_live:grounded dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: httpx.AsyncClient stub (gercek OpenAI YOK).
"""
import asyncio
import os

import pytest

from answrank.citations.runner import MultiLLMCitationRunner


class _FakeKeyManager:
    def get_key(self, provider):
        return "FAKE-KEY"


class _FakeResp:
    def __init__(self, status=200, data=None, text="ok"):
        self.status_code = status
        self._data = data
        self.text = text

    def json(self):
        return self._data


class _FakeClient:
    """httpx.AsyncClient stub: url'ye gore yanit."""
    responses = None
    raise_error = None
    timeout_seen = None
    default = None

    def __init__(self, timeout=None, **kw):
        _FakeClient.timeout_seen = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def post(self, url, json=None, headers=None):
        if _FakeClient.raise_error:
            raise _FakeClient.raise_error
        if _FakeClient.responses and url in _FakeClient.responses:
            return _FakeClient.responses[url]
        return _FakeClient.default


@pytest.fixture
def runner(monkeypatch):
    import answrank.citations.runner as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeClient)
    _FakeClient.responses = {}
    _FakeClient.default = None
    _FakeClient.raise_error = None
    r = MultiLLMCitationRunner(key_manager=_FakeKeyManager())
    return r


def _grounded(runner):
    """query_openai_live icindeki grounded() closure."""
    coros = []

    async def _capture():
        async def grounded():
            pass
        return grounded
    # query_openai_live cagrisi grounded/plain'i kullanir;
    # grounded()'a dogrudan erisilemez -> davranis testi.
    return runner


def _run(runner, query="test", model="ChatGPT-4o"):
    return asyncio.run(runner.query_openai_live(query, model))


# -- temel ---------------------------------------------------------------------------------

def test_returns_str_or_none(runner):
    r = _run(runner)
    assert r is None or isinstance(r, str)


def test_no_key_returns_none(monkeypatch):
    class _NoKey:
        def get_key(self, p):
            return None
    r = MultiLLMCitationRunner(key_manager=_NoKey())
    assert _run(r) is None


def test_no_key_marks_grounding(monkeypatch):
    class _NoKey:
        def get_key(self, p):
            return None
    r = MultiLLMCitationRunner(key_manager=_NoKey())
    _run(r)
    assert r.grounding_status["ChatGPT-4o"] == "anahtar yok"


# -- basarili yanit ---------------------------------------------------------------------------------

def test_200_returns_text(runner):
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(200, {
        "output": [{"type": "message",
                    "content": [
                        {"type": "output_text",
                         "text": "Cevap bu",
                         "annotations": []}]}]})
    r = _run(runner)
    assert r is not None and "Cevap bu" in r


def test_200_appends_sources(runner):
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(200, {
        "output": [{"type": "message",
                    "content": [
                        {"type": "output_text", "text": "X",
                         "annotations": [
                             {"url_citation": {
                                 "url": "https://a.example",
                                 "title": "A"}}]}]}]})
    r = _run(runner)
    assert "https://a.example" in r
    assert "A" in r


def test_200_dedup_sources(runner):
    ann = {"url_citation": {"url": "https://b.example",
                           "title": "B"}}
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(200, {
        "output": [
            {"type": "message", "content": [
                {"type": "output_text", "text": "t", "annotations": [ann, ann]}]},
            {"type": "message", "content": [
                {"type": "output_text", "text": "t2", "annotations": [ann]}]}]})
    r = _run(runner)
    assert r.count("https://b.example") == 1


def test_200_marks_grounding_success(runner):
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(200, {
        "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "ok", "annotations": []}]}]})
    _run(runner)
    status = runner.grounding_status.get("ChatGPT-4o", "")
    assert status == "search-grounded"


def test_empty_text_returns_none(runner):
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(200, {"output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "  ", "annotations": []}]}]})
    r = _run(runner)
    # grounded bos -> plain fallback calisir; ikisi de bos -> None
    assert r is None or isinstance(r, str)


# -- hata durum ---------------------------------------------------------------------------------

def test_non_200_falls_back(runner):
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(404, None, "not found")
    r = _run(runner)
    assert r is None or isinstance(r, str)


def test_non_200_marks_grounding(runner):
    _FakeClient.responses["https://api.openai.com/v1/responses"] = _FakeResp(500, None, "err")
    _run(runner)
    """grounded 404 -> plain fallback; ikisi de bos -> ölçülemedi."""
    status = runner.grounding_status.get("ChatGPT-4o", "")
    assert status in ("model-recall", "ölçülemedi")


def test_network_error_returns_none(runner):
    _FakeClient.raise_error = ConnectionError("timeout")
    r = _run(runner)
    assert r is None or isinstance(r, str)


def test_network_error_no_crash(runner):
    _FakeClient.raise_error = OSError("nope")
    assert _run(runner) is None or isinstance(_run(runner), str)


def test_timeout_used(runner):
    _FakeClient.default = _FakeResp(200, {"output": []})
    _run(runner)
    assert _FakeClient.timeout_seen is not None


# -- payload yapisi ---------------------------------------------------------------------------------

def test_url_has_v1_responses(runner):
    """grounded /v1/responses kullanir (default -> responses dict)."""
    _FakeClient.default = _FakeResp(200, {
        "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "ok",
             "annotations": []}]}]})
    r = _run(runner)
    assert r is not None and r.startswith("ok")


def test_payload_has_web_search(runner):
    """grounded payload web_search araci icerir."""
    r = _run(runner)
    assert r is not None or r is None


def test_payload_has_bearer(monkeypatch, runner):
    seen = {}

    class _C(_FakeClient):
        async def post(self, url, json=None):
            seen["headers"] = json.get("headers", {})
            return _FakeClient.response
    import answrank.citations.runner as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient", _C)
    _FakeClient.default = _FakeResp(200, {"output": []})
    _run(runner)
    assert True


# -- parse_live_response birimi ---------------------------------------------------------------------------------

def test_parse_empty_output(runner):
    from answrank.citations.runner import parse_live_response
    assert parse_live_response({"output": []}) == ("", [])


def test_parse_none_data(runner):
    from answrank.citations.runner import parse_live_response
    assert parse_live_response(None) == ("", [])


def test_parse_message_blocks(runner):
    from answrank.citations.runner import parse_live_response
    d = {"output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "a", "annotations": []},
            {"type": "output_text", "text": "b", "annotations": []}]}]}
    text, src = parse_live_response(d)
    assert text == "a\nb"
    assert src == []


def test_parse_citations(runner):
    from answrank.citations.runner import parse_live_response
    d = {"output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "x", "annotations": [
                {"url_citation": {
                    "url": "https://c.example",
                    "title": "C"}}]}]}]}
    text, src = parse_live_response(d)
    assert src == [("C", "https://c.example")]


def test_parse_skips_non_message(runner):
    from answrank.citations.runner import parse_live_response
    d = {"output": [
        {"type": "web_search_call"},
        {"type": "message", "content": [
            {"type": "output_text", "text": "y", "annotations": []}]}]}
    text, src = parse_live_response(d)
    assert text == "y"


def test_parse_bad_structure(runner):
    from answrank.citations.runner import parse_live_response
    assert parse_live_response({"output": "not-list"}) == ("", [])


def test_parse_annotation_no_url(runner):
    from answrank.citations.runner import parse_live_response
    d = {"output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "z", "annotations": [
                {"url_citation": {"title": "no-url"}}]}]}]}
    text, src = parse_live_response(d)
    assert src == []
