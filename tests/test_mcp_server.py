"""Tests for the MCP (Model Context Protocol) server surface.

The audit found this module at 0% coverage. These tests pin its JSON-RPC
contract: tools/list discovery, tools/call dispatch for all 3 tools, and
error handling for unknown tools/methods — all without spawning the stdio
loop (call_tool is tested directly; run_stdio's readline loop is a thin
wrapper around the same dispatch).
"""

import json
import sys
import pytest
from unittest.mock import AsyncMock, patch

from answrank.mcp.server import AnswRankMCPServer
from answrank.citations.runner import MODELS as _MODELS_T
from answrank.audit.crawler import CrawlData
from answrank.models import AuditResult, CategoryScores, utc_now
from answrank.audit.analyzers import (
    RobotsAnalyzer, LlmsTxtAnalyzer, SchemaAnalyzer, MetaAnalyzer,
    CitabilityAnalyzer, EntityAnalyzer, TrustAnalyzer, NegativeAnalyzer,
)
from bs4 import BeautifulSoup


def _fake_audit(domain="mcp-test.com", score=64) -> AuditResult:
    soup = BeautifulSoup("<html><body><p>dental implants london pricing warranty</p></body></html>", "html.parser")
    return AuditResult(
        audit_id="audit_mcp_1",
        url=f"https://{domain}",
        domain=domain,
        sector="dental",
        timestamp=utc_now(),
        overall_score=score,
        score_band="Foundation",
        categories=CategoryScores(
            robots=RobotsAnalyzer().analyze("User-agent: *\nAllow: /"),
            llms_txt=LlmsTxtAnalyzer().analyze("# T\n> s\n## A\n## B", None),
            schema_jsonld=SchemaAnalyzer().analyze(soup, sector="dental"),
            meta_architecture=MetaAnalyzer().analyze(soup),
            citability_rag=CitabilityAnalyzer().analyze(soup),
            entity_coherence=EntityAnalyzer().analyze(soup, domain=domain),
            trust_stack=TrustAnalyzer().analyze(soup, is_https=True),
            negative_signals=NegativeAnalyzer().analyze(soup),
        ),
        recommendations=[],
        lost_revenue_estimate_monthly_try=5000.0,
    )


def test_tool_definitions_shape():
    server = AnswRankMCPServer()
    tools = server.get_tool_definitions()
    names = {t["name"] for t in tools}
    assert names == {"answrank_audit", "answrank_citations", "answrank_generate_fixes"}
    # MCP spec key is inputSchema (16 Eyl P1: "parameters" was spec-wrong — real
    # clients rendered inputSchema: null). Each def carries required fields.
    for t in tools:
        assert "description" in t and isinstance(t["description"], str)
        assert "inputSchema" in t and "parameters" not in t
        assert isinstance(t["inputSchema"].get("required", []), list)


@pytest.mark.anyio
async def test_call_tool_audit():
    server = AnswRankMCPServer()
    fake_audit = _fake_audit()

    class FakeCrawler:
        async def fetch(self, url):
            return CrawlData(
                url=url, domain="mcp-test.com",
                html_content="<html><body><p>dental implants london pricing warranty</p></body></html>",
                status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /", is_https=True,
            )

    class FakeEngine:
        crawler = FakeCrawler()
        def audit_crawl_data(self, crawl, sector="general"):
            return fake_audit
        async def audit_url(self, url, sector="general"):
            return fake_audit

    with patch.object(server, "engine", FakeEngine()), \
         patch.object(server.db, "save_audit", new=AsyncMock()):
        result = await server.call_tool("answrank_audit", {"url": "https://mcp-test.com", "sector": "dental"})

    assert result["overall_score"] == 64
    assert result["domain"] == "mcp-test.com"
    assert "markdown_report" in result
    assert result["lost_revenue_estimate_monthly_try"] == 5000.0


@pytest.mark.anyio
async def test_call_tool_citations_simulation_mode():
    """Without API keys the citation tool runs honest deterministic simulation."""
    server = AnswRankMCPServer()

    with patch.object(server.db, "save_citations", new=AsyncMock()):
        result = await server.call_tool("answrank_citations", {
            "brand": "Test Klinik", "domain": "testklinik.com", "sector": "dental",
        })

    assert result["brand"] == "Test Klinik"
    assert result["total_runs"] == 20 * len(_MODELS_T)
    assert "citation_rate_percentage" in result
    assert "top_competitors" in result


@pytest.mark.anyio
async def test_call_tool_generate_fixes():
    server = AnswRankMCPServer()
    result = await server.call_tool("answrank_generate_fixes", {
        "domain": "fixme.com", "brand": "FixMe Dental", "sector": "dental", "city": "İstanbul",
    })
    # robots.txt now generated from the 27-bot settings with blocked scrapers
    assert "User-agent: OAI-SearchBot" in result["robots_txt"]
    assert "User-agent: Bytespider\nDisallow: /" in result["robots_txt"]
    assert "# FixMe Dental" in result["llms_txt"]
    assert '"@type"' in result["json_ld"]


@pytest.mark.anyio
async def test_call_tool_unknown_raises():
    server = AnswRankMCPServer()
    with pytest.raises(ValueError, match="Unknown tool"):
        await server.call_tool("no_such_tool", {})


def test_stdio_dispatch_jsonrpc_methods():
    """Drives the REAL run_stdio loop with an injected reader and captured
    stdout: tools/list, an unknown method, and a tools/call error path."""
    import asyncio
    import io

    server = AnswRankMCPServer()

    class FakeReader:
        """Emulates a StreamReader fed with a fixed input."""
        def __init__(self, data: bytes):
            self._stream = io.BytesIO(data)

        async def readline(self):
            line = self._stream.readline()
            return line if line else b""

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 2, "method": "bogus/method"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "unknown_tool_x", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "answrank_generate_fixes", "arguments": {"domain": "stdio.com", "brand": "Stdio Test"}}},
    ]
    raw = ("\n".join(json.dumps(r) for r in requests) + "\n").encode("utf-8")

    captured_out = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = captured_out
    try:
        asyncio.run(server.run_stdio(reader=FakeReader(raw)))
    finally:
        sys.stdout = real_stdout

    lines = [json.loads(l) for l in captured_out.getvalue().strip().splitlines()]
    assert len(lines) == 4

    # tools/list → tool definitions
    assert lines[0]["id"] == 1
    assert "tools" in lines[0]["result"]
    tool_names = {t["name"] for t in lines[0]["result"]["tools"]}
    assert "answrank_audit" in tool_names

    # bogus method → -32601
    assert lines[1]["id"] == 2 and lines[1]["error"]["code"] == -32601

    # unknown tool → MCP-correct isError RESULT (a failing tool is a normal
    # result flagged for the client, not a JSON-RPC transport error envelope)
    assert lines[2]["id"] == 3
    assert "error" not in lines[2]
    assert lines[2]["result"]["isError"] is True
    assert "Unknown tool" in lines[2]["result"]["content"][0]["text"]

    # real tools/call → generate_fixes content, flagged as success
    assert lines[3]["id"] == 4
    assert lines[3]["result"]["isError"] is False
    content_text = lines[3]["result"]["content"][0]["text"]
    parsed = json.loads(content_text)
    assert "robots_txt" in parsed
    assert "User-agent: OAI-SearchBot" in parsed["robots_txt"]


# ---------- stdio lifecycle (the layer real MCP clients handshake with) ----------

@pytest.mark.anyio
async def test_stdio_lifecycle_initialize_notifications_ping_errors(capsys):
    """The readline loop itself must satisfy the MCP handshake: initialize,
    silent notifications, ping, tool-failure-as-result (isError), and -32601
    for genuinely unknown request methods."""
    import asyncio
    server = AnswRankMCPServer()
    reader = asyncio.StreamReader()
    frames = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "bogus/method"},
    ]
    for f in frames:
        reader.feed_data((json.dumps(f) + "\n").encode("utf-8"))
    reader.feed_eof()

    await server.run_stdio(reader=reader)

    out = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert len(out) == 4, "notifications must not be answered"
    init = out[0]["result"]
    assert init["serverInfo"]["name"] == "answrank"
    assert init["protocolVersion"] == "2025-06-18"  # supported version echoed
    assert init["capabilities"]["tools"] == {"listChanged": False}
    assert out[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}
    tc = out[2]
    assert "error" not in tc, "tool failure must be an isError RESULT, not a JSON-RPC error"
    assert tc["result"]["isError"] is True
    assert "failed" in tc["result"]["content"][0]["text"]
    assert out[3]["error"]["code"] == -32601


@pytest.mark.anyio
async def test_stdio_initialize_falls_back_for_unknown_protocol_version(capsys):
    import asyncio
    server = AnswRankMCPServer()
    reader = asyncio.StreamReader()
    reader.feed_data(json.dumps({"jsonrpc": "2.0", "id": 9, "method": "initialize",
                                 "params": {"protocolVersion": "1999-01-01"}}).encode() + b"\n")
    reader.feed_eof()
    await server.run_stdio(reader=reader)
    out = json.loads(capsys.readouterr().out.strip())
    assert out["result"]["protocolVersion"] == "2024-11-05"  # safest supported fallback


def test_mcp_citations_sector_enum_covers_all_banks():
    from answrank.citations.questions import SECTOR_QUESTIONS
    defs = AnswRankMCPServer().get_tool_definitions()
    cite = next(t for t in defs if t["name"] == "answrank_citations")
    assert set(cite["inputSchema"]["properties"]["sector"]["enum"]) == set(SECTOR_QUESTIONS)


def test_mcp_missing_argument_error_is_actionable():
    import asyncio
    server = AnswRankMCPServer()
    try:
        asyncio.run(server.call_tool("answrank_citations", {"domain": "x.example"}))
        assert False, "must raise"
    except ValueError as e:
        assert "missing required argument(s): 'brand'" in str(e)
        assert "provided keys" in str(e)


def test_mcp_serverinfo_version_single_source():
    import asyncio, json, io, contextlib

    async def _drive():
        server = AnswRankMCPServer()
        reader = asyncio.StreamReader()
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18"}}
        reader.feed_data((json.dumps(req) + "\n").encode())
        reader.feed_data((json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n").encode())
        reader.feed_eof()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            await server.run_stdio(reader=reader)
        return buf.getvalue()

    lines = [json.loads(l) for l in asyncio.run(_drive()).splitlines()]
    init = next(l for l in lines if l["id"] == 1)
    from answrank import __version__
    assert init["result"]["serverInfo"]["version"] == __version__


def test_mcp_non_object_arguments_friendly_error():
    import asyncio
    with pytest.raises(ValueError) as e:
        asyncio.run(AnswRankMCPServer().call_tool("answrank_audit", "not-a-dict"))
    assert "must be an object" in str(e.value)
