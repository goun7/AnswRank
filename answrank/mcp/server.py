"""AnswRank Model Context Protocol (MCP) Server.

Exposes AEO/GEO auditing, citation testing, and fix generation tools to Claude Desktop, Cursor, and Windsurf.
"""

import sys
import json
import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger("answrank.mcp")
from answrank.audit.engine import AuditEngine
from answrank.citations.runner import MultiLLMCitationRunner, MODELS as _MODELS
from answrank.citations.questions import QUESTION_COUNT as _QC
from answrank.reporting.fix_generator import FixGenerator
from answrank.reporting.generator import ReportGenerator
from answrank.db import Database
from answrank.x402_gate import (
    SesterPaymentGate, PaymentRequired, TOOL_PRICES as _TOOL_PRICES,
)
from answrank import __version__

class AnswRankMCPServer:
    """Standard JSON-RPC 2.0 Model Context Protocol Server."""

    def __init__(self):
        self.engine = AuditEngine()
        self.runner = MultiLLMCitationRunner()
        self.fix_gen = FixGenerator()
        self.rep_gen = ReportGenerator()
        self.db = Database()
        # mesh code bond (2026-10-05): Sester x402 odeeme kapisi.
        # Ucretsiz modda (ANSWRANK_SELLER_SECRET yok) etkisizdir; mevcut
        # davranis ve testler korunur. Odemeli modda fail-closed: makbuz
        # dogrulanir, mainnet'te zincirde USDC transferi aranir.
        self.gate = SesterPaymentGate()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns tool schema definitions for MCP discovery."""
        return [
            {
                "name": "answrank_audit",
                "description": (
                    f"Audits a website for AI answer engine visibility (AEO/GEO)"
                    f" across 8 categories (0-100 score). Paid tool:"
                    f" ${_TOOL_PRICES['answrank_audit']:.2f} USDC via Sester x402"
                    f" (free when the server runs without ANSWRANK_SELLER_SECRET;"
                    f" pass a Sester receipt as `payment_receipt` to settle)."),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target website URL"},
                        "sector": {"type": "string", "enum": ["dental", "accounting", "aesthetic", "general"], "default": "general"},
                        "payment_receipt": {"type": "object", "description": "Sester x402 receipt for this call (required only when the payment gate is enabled)"},
                        "payer_address": {"type": "string", "description": "Payer EOA (0x + 40 hex); required only for mainnet payment verification"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "answrank_citations",
                "description": (
                    f"Runs {_QC} sector questions across {len(_MODELS)} AI models"
                    f" ({', '.join(m.split('-')[0] for m in _MODELS)}) to test brand"
                    f" citation rate. Paid tool:"
                    f" ${_TOOL_PRICES['answrank_citations']:.2f} USDC via Sester x402"
                    f" (the most expensive tool: multi-LLM calls)."),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "brand": {"type": "string", "description": "Brand name"},
                        "domain": {"type": "string", "description": "Website domain name"},
                        "sector": {"type": "string", "enum": ["dental", "accounting", "aesthetic", "general"], "default": "dental"},
                        "city": {"type": "string", "default": "İstanbul"},
                        "lang": {"type": "string", "enum": ["tr", "en"], "default": "tr",
                                 "description": "Soru-bankası dili (E4 EN bankaları; bankasız dil reddedilir)"},
                        "payment_receipt": {"type": "object", "description": "Sester x402 receipt for this call (required only when the payment gate is enabled)"},
                        "payer_address": {"type": "string", "description": "Payer EOA (0x + 40 hex); required only for mainnet payment verification"},
                    },
                    "required": ["brand", "domain"],
                },
            },
            {
                "name": "answrank_generate_fixes",
                "description": (
                    "Auto-generates ready-to-copy robots.txt, llms.txt, and JSON-LD"
                    f" schema for a domain. Paid tool:"
                    f" ${_TOOL_PRICES['answrank_generate_fixes']:.2f} USDC via"
                    f" Sester x402."),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "description": "Website domain"},
                        "brand": {"type": "string", "description": "Brand name"},
                        "sector": {"type": "string", "default": "dental"},
                        "city": {"type": "string", "default": "İstanbul"},
                        "payment_receipt": {"type": "object", "description": "Sester x402 receipt for this call (required only when the payment gate is enabled)"},
                        "payer_address": {"type": "string", "description": "Payer EOA (0x + 40 hex); required only for mainnet payment verification"},
                    },
                    "required": ["domain"],
                },
            },
        ]

    @staticmethod
    def _require(arguments: Dict[str, Any], *names: str) -> None:
        """Friendly MCP contract errors: a bare KeyError like "'brand'" made
        clients show 'Tool answrank_citations failed: \'brand\'' with no clue."""
        if not isinstance(arguments, dict):
            raise ValueError(f"arguments must be an object, got {type(arguments).__name__}")
        missing = [n for n in names if n not in arguments]
        if missing:
            raise ValueError(
                "missing required argument(s): "
                + ", ".join(f"'{m}'" for m in missing)
                + f" (provided keys: {sorted(arguments) or 'none'})")

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches and executes MCP tool requests.

        Mesh code bond (2026-10-05): paid tools pass the Sester x402 gate
        BEFORE any work runs (fail-closed: no receipt, no audit), and the
        delivery is anchored to the receipt ledger AFTER the result exists.
        """
        # once arguman nesnesi dogrulanir (dostu hata), sonra odeme kapisi
        self._require(arguments)
        if name in _TOOL_PRICES:
            try:
                self.gate.require(
                    tool=name,
                    receipt=arguments.get("payment_receipt"),
                    payer=arguments.get("payer_address"),
                )
            except PaymentRequired as pe:
                # MCP sematigi: istemci-hatasi isError RESULT olarak doner,
                # boylece kullanici 402 sebebini gorur (transport hatasi degil)
                raise ValueError(f"payment required ({name}): {pe}") from pe

        if name == "answrank_audit":
            self._require(arguments, "url")
            url = arguments["url"]
            sector = arguments.get("sector", "general")
            audit_res = await self.engine.audit_url(url, sector=sector)
            await self.db.save_audit(audit_res)
            result = {
                "overall_score": audit_res.overall_score,
                "score_band": audit_res.score_band,
                "domain": audit_res.domain,
                "crawl_warnings": audit_res.crawl_warnings,
                "lost_revenue_estimate_monthly_try": audit_res.lost_revenue_estimate_monthly_try,
                "recommendations": [r.model_dump() for r in audit_res.recommendations],
                "markdown_report": self.rep_gen.to_markdown(audit_res),
            }

        elif name == "answrank_citations":
            self._require(arguments, "brand", "domain")
            res = await self.runner.run_citations(
                brand_name=arguments["brand"],
                domain=arguments["domain"],
                sector=arguments.get("sector", "dental"),
                city=arguments.get("city", "İstanbul"),
                lang=arguments.get("lang", "tr"),
            )
            await self.db.save_citations(res)
            result = {
                "brand": res.brand_name,
                "citation_rate_percentage": res.citation_rate_percentage,
                "citations_found": res.brand_citations_found,
                "total_runs": res.total_runs,
                "live_items_count": res.live_items_count,
                "live_response_rate_percentage": res.live_response_rate_percentage,
                "is_fully_live": res.is_fully_live,
                "top_competitors": res.top_competitors,
            }

        elif name == "answrank_generate_fixes":
            self._require(arguments, "domain")
            domain = arguments["domain"]
            brand = arguments.get("brand", domain)
            sector = arguments.get("sector", "dental")
            city = arguments.get("city", "İstanbul")

            result = {
                "robots_txt": self.fix_gen.generate_robots_txt(domain),
                "llms_txt": self.fix_gen.generate_llms_txt(brand, domain, sector, city),
                "json_ld": self.fix_gen.generate_json_ld(brand, domain, sector, city),
            }

        else:
            raise ValueError(f"Unknown tool: {name}")

        # mesh code bond: teslimat kaniiti -- odenen ciktinin anchor hash'i
        # receipt ledger'a yazilir; ucretsiz modda yine de hesaplanir ve
        # yanit acikca 'free' olarak etiketlenir (no silent guessing).
        result["payment"] = self.gate.settle(
            tool=name,
            anchor=self._anchor_for(name, arguments, result),
            receipt=arguments.get("payment_receipt"),
            payer=arguments.get("payer_address"),
        ).as_dict()
        return result

    @staticmethod
    def _anchor_for(name: str, arguments: Dict[str, Any],
                    result: Dict[str, Any]) -> Dict[str, Any]:
        """Ledger'a yazilacak machine-checkable cikti ozeti.

        Musteri ayni degerlerle anchor_hash'i tekrar hesaplayip makbuzun
        HANGI ciktiya ait oldugunu bagimsiz dogrular.
        """
        if name == "answrank_audit":
            return {
                "domain": result.get("domain"),
                "overall_score": result.get("overall_score"),
                "score_band": result.get("score_band"),
            }
        if name == "answrank_citations":
            return {
                "brand": result.get("brand"),
                "citation_rate_percentage": result.get("citation_rate_percentage"),
                "total_runs": result.get("total_runs"),
            }
        # generate_fixes: uretilen 3 artefaktin SHA-256'i = teslimat kaniiti
        import hashlib as _hashlib
        digest = _hashlib.sha256()
        for key in ("robots_txt", "llms_txt", "json_ld"):
            digest.update(f"{key}:{result.get(key, '')}".encode("utf-8"))
        return {"domain": arguments.get("domain"), "sha256": digest.hexdigest()}

    async def run_stdio(self, reader=None):
        """Standard JSON-RPC line loop implementing the MCP lifecycle.

        Spec compliance (verified against real MCP clients):
        - `initialize` must be answered with protocolVersion/capabilities/serverInfo.
        - `notifications/*` receive NO response (they have no id).
        - `ping` answers an empty result.
        - Tool execution failures return a result with isError=true and the
          human-readable reason as text content — never a bare transport error,
          so clients surface "why" instead of a dropped call.

        `reader` can be injected for testing; by default it is wired to stdin.
        """
        if reader is None:
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break
            req_id = None  # JSON-RPC 2.0: error responses echo the request id when known
            try:
                req = json.loads(line.decode("utf-8"))
                req_id = req.get("id")
                method = req.get("method")

                if method == "initialize":
                    requested = (req.get("params") or {}).get("protocolVersion", "")
                    supported = {"2024-11-05", "2025-03-26", "2025-06-18"}
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                        "protocolVersion": requested if requested in supported else "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "answrank", "version": __version__},
                    }}
                elif method == "ping":
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                elif method == "notifications/initialized" or (method or "").startswith("notifications/"):
                    # JSON-RPC notification: must not be answered (no id).
                    continue
                elif method == "tools/list":
                    resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.get_tool_definitions()}}
                elif method == "tools/call":
                    params = req.get("params", {})
                    tool_name = params.get("name")
                    args = params.get("arguments", {})
                    try:
                        output = await self.call_tool(tool_name, args)
                        content = [{"type": "text", "text": json.dumps(output, ensure_ascii=False, indent=2)}]
                        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": content, "isError": False}}
                    except Exception as tool_err:
                        # MCP semantics: a failing TOOL is a normal result flagged isError.
                        # Kullanım hatası (Unknown tool vb.) istemciye açılır; beklenmeyen
                        # istisna detayı günlüğe yazılır ve genel mesajla gönderilir.
                        is_usage = isinstance(tool_err, (ValueError, KeyError, LookupError))
                        if not is_usage:
                            logger.exception("Tool %s beklenmeyen hatası", tool_name)
                        detail = str(tool_err) if is_usage else \
                            "beklenmeyen iç hata (ayrıntılar sunucu günlüğünde)"
                        resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                            "content": [{"type": "text", "text": f"Tool {tool_name} failed: {detail}"}],
                            "isError": True,
                        }}
                else:
                    resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method {method} not found"}}

                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            except Exception:
                logger.exception("MCP JSON-RPC hatası (müşteriye iletilmedi)")
                err_resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "İç sunucu hatası (ayrıntılar günlüklendi)"}}
                sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()

def main():
    """CLI giriş noktası; komutları parse edip yürütür."""
    server = AnswRankMCPServer()
    asyncio.run(server.run_stdio())

if __name__ == "__main__":
    main()
