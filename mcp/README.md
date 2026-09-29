# AnswRank MCP Server — AEO/GEO Audit for AI clients

Model Context Protocol server (**2025-06-18**, JSON-RPC 2.0 over stdio)
exposing AnswRank's answer-engine visibility tools to Claude Desktop, Cursor,
Windsurf, Cline and any MCP client.

Speak to an AI assistant in the place where your customers actually ask
questions — ChatGPT, Perplexity, Gemini, Claude, Mistral. AnswRank measures
whether your site shows up in those answers and hands you the fixes.

## Tools

| Tool | What it does | Needs a key? |
|---|---|---|
| `answrank_audit` | Audit a site for AI-answer visibility (AEO/GEO) across 8 categories — 0–100 score, crawl warnings, lost-revenue estimate, recommendations | **No** |
| `answrank_citations` | Run sector questions across **5 AI models** to measure a brand's citation rate | Yes (≥1 LLM key) |
| `answrank_generate_fixes` | Generate ready-to-copy `robots.txt`, `llms.txt` and JSON-LD schema for a domain | **No** |

## Install — 30 seconds, $0

```bash
pip install -e .          # or: pip install answrank
python -m answrank.mcp.server     # stdio JSON-RPC
```

Then wire it into your client:

```json
{
  "mcpServers": {
    "answrank": {
      "command": "python",
      "args": ["-m", "answrank.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

Only `answrank_citations` needs an LLM key (one is enough — five are
supported: `PERPLEXITY_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`). The audit and fix tools run with no
key at all.

## Example session

> **You:** Audit `https://example.com` for AI visibility.
>
> **answrank_audit** → `{overall_score: 41, score_band: "weak",
> crawl_warnings: ["no llms.txt", "missing JSON-LD"],
> lost_revenue_estimate_monthly_try: 28400, recommendations: [...],
> markdown_report: "…"}`
>
> **You:** Generate the fixes for that domain.
>
> **answrank_generate_fixes** → ready-to-paste `robots.txt` (25+ AI bot
> rules, AEO-prioritised), `llms.txt`, and JSON-LD (`LocalBusiness` +
> `FAQPage`).

## Verify it works (stdio handshake)

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
  | python -m answrank.mcp.server | head -1
```

The response carries `protocolVersion 2025-06-18` and
`serverInfo {"name":"answrank", ...}`. Then `tools/list` returns the three
tools above.

## Protocol details

- `initialize` answers `protocolVersion 2025-06-18` (also accepts
  `2024-11-05` / `2025-03-26`), capabilities `tools.listChanged: false`.
- `notifications/*` receive no response (JSON-RPC notification, no id).
- `ping` answers an empty result.
- A failing tool returns a result with `isError: true` and the
  human-readable reason as text — never a bare transport error.

## Registry

- Registry definition: [`mcp.json`](mcp.json)
- Smithery config: [`smithery.yaml`](smithery.yaml)
- How to publish (free tiers, no registration done yet):
  [`REGISTRIES.md`](REGISTRIES.md)

## Privacy

LLM keys are read from the environment and used only for citation testing;
they are never logged or persisted. `answrank_audit` fetches the target URL;
`answrank_generate_fixes` makes no network calls.
