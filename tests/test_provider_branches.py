"""Branch coverage for live-provider HTTP paths, key manager fallbacks,
MCP stdio protocol loop, job-manager edge paths, exclusivity release."""

import asyncio
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch


from answrank.citations.key_manager import HybridKeyManager, LLMProvider
from answrank.citations.runner import MultiLLMCitationRunner
from answrank.crm.exclusivity import ExclusivityManager


# ---------------- provider HTTP status branches ----------------

class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def _make_client(post_impl):
    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
    _Client.post = post_impl
    return _Client


def _ok_client(content_json):
    async def _post(self, url, **kw):
        return _Resp(200, content_json)
    return _make_client(_post)


def _status_client(code):
    async def _post(self, url, **kw):
        return _Resp(code, {})
    return _make_client(_post)


def _raise_client(exc):
    async def _post(self, url, **kw):
        raise exc
    return _make_client(_post)


def _runner_with(provider):
    km = HybridKeyManager(custom_keys={provider: "test-key"})
    return MultiLLMCitationRunner(key_manager=km)


def test_perplexity_live_success_and_failures():
    runner = _runner_with(LLMProvider.PERPLEXITY)
    # 16 Eyl 2026: Sonar Agent API'ye taşındı (/chat/completions 403); gövde
    # artık responses formatında — output[].message.content[].output_text.
    ok_body = {"output": [
        {"type": "web_search_call", "id": "ws1"},
        {"type": "message", "content": [
            {"type": "output_text", "text": "Perplexity yanıtı",
             "annotations": [{"type": "url_citation",
                              "url_citation": {"title": "K", "url": "https://k.example"}}]}]}]}
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client(ok_body)):
        ans = asyncio.run(runner.query_perplexity_live("q"))
        assert ans is not None and ans.startswith("Perplexity yanıtı")
        assert "https://k.example" in ans  # kaynak listesi gövdeye eklenir
    with patch("answrank.citations.runner.httpx.AsyncClient",
               _ok_client({"output": [{"type": "message", "content": []}]})):
        assert asyncio.run(runner.query_perplexity_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _status_client(429)):
        assert asyncio.run(runner.query_perplexity_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _raise_client(OSError("net down"))):
        assert asyncio.run(runner.query_perplexity_live("q")) is None


def test_openai_live_success_and_failures():
    runner = _runner_with(LLMProvider.OPENAI)
    body = {"choices": [{"message": {"content": "OpenAI yanıtı"}}]}
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client(body)):
        assert asyncio.run(runner.query_openai_live("q")) == "OpenAI yanıtı"
    with patch("answrank.citations.runner.httpx.AsyncClient", _status_client(500)):
        assert asyncio.run(runner.query_openai_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _raise_client(ValueError("bad json"))):
        assert asyncio.run(runner.query_openai_live("q")) is None
    # missing key -> None early
    bare = MultiLLMCitationRunner(key_manager=HybridKeyManager(custom_keys={}))
    assert asyncio.run(bare.query_openai_live("q")) is None


def test_gemini_live_success_and_failures():
    runner = _runner_with(LLMProvider.GEMINI)
    body = {"candidates": [{"content": {"parts": [{"text": "Gemini yanıtı"}]}}]}
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client(body)):
        assert asyncio.run(runner.query_gemini_live("q")) == "Gemini yanıtı"
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client({"candidates": []})):
        assert asyncio.run(runner.query_gemini_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _status_client(403)):
        assert asyncio.run(runner.query_gemini_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _raise_client(OSError("x"))):
        assert asyncio.run(runner.query_gemini_live("q")) is None


def test_claude_live_success_and_failures():
    runner = _runner_with(LLMProvider.ANTHROPIC)
    body = {"content": [{"type": "text", "text": "Claude yanıtı"}]}
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client(body)):
        assert asyncio.run(runner.query_claude_live("q")) == "Claude yanıtı"
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client({"content": []})):
        assert asyncio.run(runner.query_claude_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _status_client(529)):
        assert asyncio.run(runner.query_claude_live("q")) is None
    with patch("answrank.citations.runner.httpx.AsyncClient", _raise_client(OSError("x"))):
        assert asyncio.run(runner.query_claude_live("q")) is None


def test_query_provider_routing_and_unknown_model():
    runner = _runner_with(LLMProvider.PERPLEXITY)
    # 16 Eyl 2026: Sonar Agent API responses formatı.
    body = {"output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "routed-live"}]}]}
    # PROVIDER_QUERY_METHODS stores raw functions; patch the HTTP layer so the
    # dict-bound dispatch (method(self, query)) executes for real.
    with patch("answrank.citations.runner.httpx.AsyncClient", _ok_client(body)):
        out = asyncio.run(runner._query_provider("Perplexity-Sonar", "q"))
        assert out is not None and out.startswith("routed-live")
    # unknown model -> None
    assert asyncio.run(runner._query_provider("NoSuchModel-9", "q")) is None


# ---------------- key_manager execute_query fallback paths ----------------

def test_execute_query_live_none_triggers_fallback():
    km = HybridKeyManager(custom_keys={LLMProvider.OPENAI: "long-enough-key"})
    called = {"fallback": 0}

    async def _live():
        return None
    async def _fb():
        called["fallback"] += 1
        return "simulated"

    out = asyncio.run(km.execute_query(LLMProvider.OPENAI, _live, _fb))
    assert out == "simulated"
    assert called["fallback"] == 1


def test_execute_query_live_exception_triggers_fallback():
    km = HybridKeyManager(custom_keys={LLMProvider.OPENAI: "long-enough-key"})

    async def _live():
        raise RuntimeError("api exploded")
    async def _fb():
        return "recovered"

    out = asyncio.run(km.execute_query(LLMProvider.OPENAI, _live, _fb))
    assert out == "recovered"
    tel = km._telemetry[LLMProvider.OPENAI]
    assert tel.failed_calls == 1


def test_execute_query_no_key_uses_fallback_directly():
    km = HybridKeyManager(custom_keys={})

    async def _live():
        raise AssertionError("must not be called")
    async def _fb():
        return "only-sim"

    assert asyncio.run(km.execute_query(LLMProvider.ANTHROPIC, _live, _fb)) == "only-sim"


# ---------------- MCP stdio protocol loop ----------------

def _run_stdio(lines):
    from answrank.mcp.server import AnswRankMCPServer

    async def _drive():
        reader = asyncio.StreamReader()
        for ln in lines:
            reader.feed_data(ln.encode() + b"\n")
        reader.feed_eof()
        server = AnswRankMCPServer()
        buf = io.StringIO()
        with redirect_stdout(buf):
            await server.run_stdio(reader=reader)
        return buf.getvalue()

    out = asyncio.run(_drive())
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def test_mcp_stdio_tools_list_and_call():
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "answrank_generate_fixes",
                               "arguments": {"domain": "mcpfix.com", "brand_name": "MCP Fix"}}}),
    ]
    resp = _run_stdio(lines)
    tools = next(r for r in resp if r["id"] == 1)["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"answrank_audit", "answrank_citations", "answrank_generate_fixes"} <= names
    call = next(r for r in resp if r["id"] == 2)
    assert "result" in call, call
    payload = json.loads(call["result"]["content"][0]["text"])
    assert "robots_txt" in payload or "robots" in payload


def test_mcp_stdio_unknown_method_and_garbage():
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 7, "method": "bogus/method"}),
        "this is not json {{{",
        json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                    "params": {"name": "nonexistent_tool", "arguments": {}}}),
    ]
    resp = _run_stdio(lines)
    # unknown method -> -32601
    err = next(r for r in resp if r["id"] == 7)
    assert err["error"]["code"] == -32601
    # garbage line -> parse error, id None
    g = next(r for r in resp if r["id"] is None)
    assert g["error"]["code"] == -32000
    # nonexistent tool -> error with id 8 echoed
    t = next(r for r in resp if r["id"] == 8)
    assert "error" in t or "result" in t


# ---------------- jobs manager edges ----------------

def test_report_progress_without_loop_is_safe():
    from answrank.api.jobs import JobManager, Job
    jm = JobManager()
    job = Job(job_id="x1", job_type="t", created_at=0.0)
    # no running loop -> RuntimeError swallowed, progress still recorded
    jm.report_progress(job, 0.42, "sync step")
    assert job.progress == 0.42
    assert job.current_step == "sync step"


def test_publish_swallows_broken_queue():
    from answrank.api.jobs import JobManager

    class _BrokenQueue:
        def put_nowait(self, payload):
            raise RuntimeError("queue closed")

    async def _run():
        jm = JobManager()
        jm._subscribers["j1"] = [_BrokenQueue()]
        await jm._publish("j1", {"event": "progress"})  # must not raise

    asyncio.run(_run())


def test_unsubscribe_cleans_empty_subscriber_lists():
    from answrank.api.jobs import JobManager

    async def _run():
        jm = JobManager()
        q = await jm.subscribe("j9")
        assert "j9" in jm._subscribers
        jm.unsubscribe("j9", q)
        assert "j9" not in jm._subscribers
        # double unsubscribe safe
        jm.unsubscribe("j9", q)

    asyncio.run(_run())


def test_eviction_of_old_completed_jobs():
    from answrank.api.jobs import JobManager
    from answrank.api.jobs import Job, JobStatus
    jm = JobManager(max_completed=2, retention_seconds=0.0)
    import time as _t
    for i in range(4):
        job = Job(job_id=f"e{i}", job_type="t", created_at=_t.time() - 99)
        job.status = JobStatus.COMPLETED
        job.completed_at = _t.time() - 99
        jm._jobs[job.job_id] = job
    jm._evict_old_completed()
    assert len(jm._jobs) <= 2


# ---------------- exclusivity release ----------------

def test_release_lock_true_and_false():
    mgr = ExclusivityManager()
    mgr.lock_territory(country="UK", city="Leeds", niche="dental",
                       client_domain="a.co.uk", brand_name="A")
    assert mgr.release_lock("UK", "Leeds", "dental") is True
    assert mgr.release_lock("UK", "Leeds", "dental") is False
    # after release, the same territory can be re-locked by a different client
    mgr.lock_territory(country="UK", city="Leeds", niche="dental",
                       client_domain="b.co.uk", brand_name="B")
    chk = mgr.check_conflict(country="UK", city="Leeds", niche="dental", candidate_domain="c.co.uk")
    assert chk.has_conflict is True
    assert "B" in chk.conflict_reason


def test_mcp_stdio_stdin_wiring_and_main():
    """Cover reader=None stdin wiring + module main() entry (157-158)."""
    from answrank.mcp import server as mcp_mod

    async def drive():
        loop = asyncio.get_event_loop()
        captured = {}

        async def fake_connect(factory, pipe):
            proto = factory()
            reader = (getattr(proto, "_stream_reader", None)
                      or getattr(proto, "_reader", None)
                      or getattr(proto, "_stream", None))
            captured["reader"] = reader

            class _T:
                def close(self): pass
            return _T(), proto

        orig = loop.connect_read_pipe
        loop.connect_read_pipe = fake_connect
        try:
            task = asyncio.create_task(mcp_mod.AnswRankMCPServer().run_stdio())
            await asyncio.sleep(0.02)  # let wiring happen
            reader = captured["reader"]
            assert reader is not None
            buf = io.StringIO()
            with redirect_stdout(buf):
                reader.feed_data(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode() + b"\n")
                reader.feed_eof()
                await task
            return buf.getvalue()
        finally:
            loop.connect_read_pipe = orig

    out = asyncio.run(drive())
    assert '"tools"' in out

    # main() wiring: patch run_stdio loop so we don't block on stdin
    ran = {}
    async def _fake_stdio(self, reader=None):
        ran["called"] = True
    with patch.object(mcp_mod.AnswRankMCPServer, "run_stdio", _fake_stdio):
        mcp_mod.main()
    assert ran.get("called") is True


def test_sentry_reaudit_non200_no_fabrication():
    """Sentry live re-audit returning 403 must yield None, never a fake delta."""
    from answrank.agents.swarm import SwarmOrchestrator, SwarmStage

    orch = SwarmOrchestrator()
    cand = orch.seed_target(brand_name="Sentry Down", domain="sentrydown.co.uk")
    cand.stage = SwarmStage.ACTIVE_MONITORING
    cand.deep_score = 60  # real baseline on record so the fetch path runs
    orch.pool[cand.id] = cand

    async def _403(*a, **k):
        from answrank.audit.crawler import CrawlData
        return CrawlData(url="https://sentrydown.co.uk", domain="sentrydown.co.uk",
                         html_content="", status_code=403, headers={})
    with patch("answrank.audit.crawler.WebCrawler.fetch", _403):
        score = asyncio.run(orch.sentry.measure_current_score(cand))
        assert score is None  # a 403 stub page never yields a fabricated score
        out = asyncio.run(orch.sentry.evaluate_retention(cand))
    assert out["current_score"] is None
    assert "unreachable" in out["measurement_note"].lower()
    assert cand.stage == SwarmStage.ACTIVE_MONITORING


def test_mcp_stdio_tool_internal_error_is_sanitized(monkeypatch):
    """Beklenmeyen (kullanım dışı) tool istisnası: detay istemciye SIZMAZ,
    genel mesaj gelir; kullanım hatası ise açılır."""
    from answrank.mcp.server import AnswRankMCPServer

    async def boom(self, name, arguments):
        if name == "boom":
            raise RuntimeError("SECRET internal token=abc123")
        raise ValueError("Unknown tool: " + name)

    monkeypatch.setattr(AnswRankMCPServer, "call_tool", boom)
    resp = _run_stdio([
        json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                    "params": {"name": "boom", "arguments": {}}}),
        json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                    "params": {"name": "nope", "arguments": {}}}),
    ])
    internal = next(r for r in resp if r["id"] == 9)["result"]
    assert internal["isError"] is True
    msg = internal["content"][0]["text"]
    assert "SECRET" not in msg and "token=abc123" not in msg
    assert "beklenmeyen iç hata" in msg
    usage = next(r for r in resp if r["id"] == 10)["result"]
    assert "Unknown tool: nope" in usage["content"][0]["text"]  # kullanım hatasi acilir
