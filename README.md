<p align="center"><img src="assets/logo.svg" width="96" alt="AnswRank logo"></p>

# AnswRank

[![CI](https://github.com/goun7/AnswRank/actions/workflows/ci.yml/badge.svg)](https://github.com/goun7/AnswRank/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/answrank)](https://pypi.org/project/answrank/)
[![Python](https://img.shields.io/pypi/pyversions/answrank)](https://pypi.org/project/answrank/)
[![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

**Audit your website the way AI search engines see it.**

AnswRank is an Answer Engine Optimization (AEO) and Generative Engine
Optimization (GEO) audit engine. It fetches a site the way ChatGPT Search,
Perplexity and Google AI Overviews do, scores it across eight categories, and
generates the `robots.txt`, `llms.txt` and JSON-LD fixes that close the gaps.

Full product/economics/legal specification: [`ANSWRANK_MASTER_100.md`](ANSWRANK_MASTER_100.md).

---

## In 30 seconds

```bash
pip install answrank

answrank audit https://example-dental.com --sector dental
```

That produces a 0–100 scorecard across eight categories — the things an answer
engine actually checks before it cites you: who is allowed to crawl, whether
your content is machine-readable, whether an entity can be grounded, and
whether negative signals contradict your trust claims. Every finding names the
file, the line and the fix. Unreachable assets are reported as *unverified*
rather than silently scored.

```bash
# generate the ready-to-ship fixes
answrank fix example-dental.com --brand "Example Dental" --sector dental
```

## Why

Traffic discovery is moving from blue links to answers. When a prospective
customer asks ChatGPT or Perplexity for a recommendation, the answer cites
three names — and forty-one pages of SEO score do not tell you whether you are
one of them.

Classic SEO tooling measures the old surface: keyword positions, backlinks,
Core Web Vitals. It says nothing about the machine-readable surface an answer
engine reads: does `robots.txt` let the crawler in, is there an `llms.txt`
declaring your content, does the page carry JSON-LD an entity grounder can
bind to, is the content structured so a retrieval system can actually use it?

AnswRank was built to measure that surface — honestly. That means two design
rules that shape the whole engine:

- **No silent guessing.** If an asset cannot be fetched, the report says
  *unverified* — it never invents a score. If no live LLM API keys are present,
  citation measurement runs a clearly-labelled simulation and labels the output
  statistically invalid, rather than emitting plausible-looking fake numbers.
- **Every number is derived from code.** The bot registry, the category
  weights and the report numbers are computed from the running code, so a
  published number cannot drift from what the engine actually does.

## Install

```bash
pip install answrank
```

Or from a checkout:

```bash
git clone https://github.com/goun7/AnswRank.git
cd AnswRank
pip install -e .
```

Requires Python ≥ 3.10. The audit engine is fully offline: a crawl fetches the
target site and nothing else. Live citation measurement additionally reads
LLM provider keys from the environment (see [Configuration](#configuration)).

## Quickstart

Single-site audit, four output formats:

```bash
answrank audit https://example-dental.com --sector dental --format json --out report.json
answrank audit https://example-dental.com --deep          # adds WAF probe, RAG, adversarial, entity
```

Generate deployable fixes (`robots.txt`, `llms.txt`, JSON-LD):

```bash
answrank fix example-dental.com --brand "Example Dental" --sector dental --out-dir ./fixes
```

Prioritize the weakest pages from a sitemap:

```bash
answrank sitemap https://example-dental.com --max-urls 25
```

Measure whether AI crawlers can actually reach you — a real WAF may silently
block them while your `robots.txt` invites them in:

```bash
answrank probe-waf https://example-dental.com
```

Citation measurement across five LLM providers:

```bash
answrank citations "Example Dental" example-dental.com --sector dental --city Istanbul --lang en --live
```

REST API + dashboard (OpenAPI docs at `/docs`):

```bash
answrank serve --host 127.0.0.1 --port 8770
```

## MCP server — Claude, Cursor, Windsurf

AnswRank ships a Model Context Protocol server (**2025-06-18**, JSON-RPC 2.0
over stdio), so an AI client can run audits, citation tests and fix
generation inline. Full docs: [`mcp/README.md`](mcp/README.md).

```bash
python -m answrank.mcp.server          # stdio JSON-RPC
```

Wire it into a client (only `answrank_citations` needs an LLM key — the audit
and fix tools need none):

```json
{
  "mcpServers": {
    "answrank": {
      "command": "python",
      "args": ["-m", "answrank.mcp.server"],
      "env": { "OPENAI_API_KEY": "sk-..." }
    }
  }
}
```

| Tool | What it does | Key? |
|---|---|---|
| `answrank_audit` | 8-category AEO/GEO audit, 0–100 score, crawl warnings, lost-revenue estimate | **No** |
| `answrank_citations` | Brand citation rate across 5 AI models | Yes (≥1) |
| `answrank_generate_fixes` | Ready-to-paste `robots.txt`, `llms.txt`, JSON-LD | **No** |

Registry-ready: [`mcp/mcp.json`](mcp/mcp.json),
[`mcp/smithery.yaml`](mcp/smithery.yaml), and free-tier publishing notes in
[`mcp/REGISTRIES.md`](mcp/REGISTRIES.md).


## What it audits

Eight categories, each with its own sub-scores and recommendations:

| Category | What it checks |
|---|---|
| **robots / crawler access** | Is the answer-engine crawler allowed in? Built on a curated registry of **39 AI bots** (11 search + 14 training + 14 user-agent), verified against a public bot directory |
| **llms.txt** | Does the site declare its content for language models, per the llms.txt v2 spec? Block/link/section structure, size, optional `llms-full.txt` |
| **schema / JSON-LD** | Is there machine-readable structured data an entity grounder can bind to, and does it match the page's declared entity type? |
| **meta architecture** | Titles, descriptions, canonicals, headings, Open Graph — the document-level signals a retrieval system reads first |
| **citability / RAG-readiness** | A heuristic estimate of how retrievable the content is (term frequency + 3-gram cosine similarity). *A readiness estimate, not a live retrieval measurement* |
| **entity coherence** | Can an entity grounder verify this business (Wikidata / Knowledge Graph) and do the references agree with each other? |
| **trust stack** | Contact details, legal pages, privacy policy, security headers — the signals an answer engine weighs before recommending |
| **negative signals** | Contradictions, broken resources, stale content, spam patterns that undercut the trust claims above |

Beyond the scorecard:

| Capability | Command |
|---|---|
| WAF / silent-block probe with real AI-crawler user agents | `answrank probe-waf <url>` |
| Sitemap crawl, weakest pages ranked | `answrank sitemap <url>` |
| RAG-readiness heuristic per page | `answrank rag <url>` |
| Adversarial scan (hidden CSS, prompt injection, LLM poisoning) | `answrank adversarial <url>` |
| Brand sentiment and zero-click safety | `answrank sentiment "<brand>" --text "<response>"` |
| Multi-LLM citation measurement (5 providers, 20 questions) | `answrank citations <brand> <domain> --live` |
| REST API + dashboard | `answrank serve` |
| MCP server (`answrank_audit`, `answrank_citations`, `answrank_generate_fixes`) | `python -m answrank.mcp.server` |

## How scoring works

The overall score is a weighted aggregate of the eight category scores, each of
which is itself computed from deterministic, per-check sub-scores. Every check
reports the file, line and concrete remediation; nothing is an opaque grade.

Two rules are load-bearing rather than cosmetic:

- **Unreachable is unverified, not zero or perfect.** A `robots.txt` that
  cannot be fetched is reported as *unverified* with a tri-state status, never
  silently scored as permissive or absent.
- **Simulation is labelled.** Without live API keys, citation runs produce a
  Monte Carlo distribution explicitly marked statistically invalid, with the
  confidence interval printed beside it.

## Configuration

The audit engine needs no configuration. Live citation measurement reads
provider keys from the environment:

```bash
export OPENAI_API_KEY=...
export PERPLEXITY_API_KEY=...
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

Keys are never written to the screen or logs. If a provider key is missing,
that provider falls back to simulation and the report says so.

Two tuning variables:

- `ANSWRANK_ASSET_CACHE_TTL` — cache lifetime in seconds for
  robots/llms/sitemap fetches (`0` disables caching)
- `ANSWRANK_LOST_REV_FACTOR` — the lost-revenue estimate multiplier (default 6.5)

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The suite is fully offline: `conftest.py` redirects the database to a temporary
path, and citation tests exercise the simulation path. Cross-repo dogfood tests
that need the sibling Sester package are skipped automatically when it is not
installed.

## Honest limits

- The **RAG-readiness score is a heuristic** (term frequency + 3-gram cosine),
  not a live embedding or retrieval measurement. Treat it as a readiness
  signal, not a predicted citation rate.
- **Citation measurement depends on provider keys.** Without them the engine
  runs a clearly-labelled simulation and labels the output statistically
  invalid — it never presents simulated numbers as live results.
- The **WAF probe is single-vantage-point**: it observes from your egress IP.
  If a CDN differentiates by region, the result reflects that path only.
- The **job queue is in-process memory**, not Redis or a database. Pending jobs
  are lost when the process restarts; horizontal scaling needs an external
  queue.
- The **sentiment engine covers TR / EN / DE keyword sets**; responses outside
  those languages are classified neutral rather than analysed.
- The **AI-bot registry reflects a point in time**: the public bot directory
  changes daily. Last live verification was 16 September 2026; the practical
  rule is to re-verify roughly every six months.

## Roadmap

- Replace the in-memory job queue with a persistent backend
- Wider language coverage for the sentiment engine
- Additional live citation providers and question banks
- Continuous monitoring with scheduled re-audits and honest delta digests

## Research notes

The category weights and measurement choices are grounded in documented
research, in [`docs/arastirma/`](docs/arastirma):

- [`01_llms_txt_standardi.md`](docs/arastirma/01_llms_txt_standardi.md) — the llms.txt v2 spec, read from the source
- [`02_eeat_ve_ai_crawler.md`](docs/arastirma/02_eeat_ve_ai_crawler.md) — E-E-A-T and the RFC 9309 robots equality-breaking rule
- [`03_rank_ve_alinti_ozeti.md`](docs/arastirma/03_rank_ve_alinti_ozeti.md) — rank-vs-citation research behind the scoring weights

## License

Proprietary (source-available). Dağıtım, satış ve ticari kullanım yasaktır — bkz. [LICENSE](LICENSE).

## Akademik Kaynaklar (2024-2026)

Bu çalışma aşağıdaki araştırmaya dayanır (her referans canlı
doğrulanmıştır):

- **[1] Üretken motor optimizasyonu (GEO) — içerik yapısı** —
  *Structural Feature Engineering for Generative Engine Optimization: How
  Content Structure Shapes Citation Behavior* — Yu et al., arXiv 2026.
  İçeriğin yapısal özelliklerinin (başlık, liste, alıntı yeri) üretken
  motorların alıntı davranışını nasıl şekillendirdiğini gösterir;
  AnswRank'ın "citability / RAG-readiness" kategorisinin temelidir.
  [arXiv:2603.29979](https://arxiv.org/abs/2603.29979)
- **[2] Sorgu türüne göre GEO optimizasyonu** —
  *Query Implied Generative Engine Optimization* — Ramakrishna &
  Andreopoulos, arXiv 2026.
  Sorunun türüne (bilgi, işlem, karşılaştırma) göre alıntı eğilimlerinin
  değiştiğini ortaya koyar; `answrank citations` soru bankasının sektörlere
  göre dağıtımına gerekçe oluşturur.
  [arXiv:2609.27845](https://arxiv.org/abs/2609.27845)
- **[3] Ajan tabanlı GEO optimizasyonu** —
  *Agent2UCB: Agentic System for Generative Engine Optimization* —
  Yu et al., arXiv 2026.
  Bir ajanın deneme-yanılma ile içerik değişikliklerinin alıntı etkisini
  ölçtüğü otomatik bir GEO sistemi tanıtır; AnswRank'ın "audit → fix →
  yeniden ölç" döngüsünün akademik karşılığıdır.
  [arXiv:2608.29063](https://arxiv.org/abs/2608.29063)
- **[4] Alıntı hatalarının teşhisi ve onarımı** —
  *Diagnosing and Repairing Citation Failures in Generative Engine
  Optimization* — Tian et al., arXiv 2026.
  Üretken motorların bir kaynağı neden alıntılamadığını sınıflandırır ve
  teşhis edilebilir onarım önerileri gider; "negative signals" kategorisi ile
  her bulgunun dosya/satır/düzeltme raporlamasını gerekçelendirir.
  [arXiv:2603.09296](https://arxiv.org/abs/2603.09296)
- **[5] AI arama motorlarında marka görünürlüğü** —
  *Generative Engine Optimization at Scale: Measuring Brand Visibility Across
  AI Search Engines* — Kumar, arXiv 2026.
  Birden çok AI arama motoru üzerinden marka görünürlüğünü ölçmeye yarayan
  bir metodoloji sunar; `answrank citations`'ın 5 sağlayıcılı ölçümünün
  (ve her sağlayıcı için ayrı raporlamanın) temelidir.
  [arXiv:2606.20065](https://arxiv.org/abs/2606.20065)
- **[6] AEO ve ChatGPT yönlendirme trafiği** —
  *Disentangling Answer Engine Optimization from Platform Growth: A
  Log-Based Natural Experiment on ChatGPT Referral Traffic* — Watanabe &
  Nakayashiki, arXiv 2026.
  ChatGPT yönlendirme trafiğindeki bir artışın AEO çalışmasından mı yoksa
  platformun genel büyümesinden mi kaynaklandığını ayırır; "lost-revenue
  estimate" ve sıralama-ağırlıkları konusundaki gerçekçi olma vurgumuzu
  destekler.
  [arXiv:2606.04362](https://arxiv.org/abs/2606.04362)
- **[7] SEO'dan içerik optimizasyonuna dönüşüm** —
  *Beyond SEO: A Transformer-Based Approach for Reinventing Web Content
  Optimisation* — Lüttgenau et al., arXiv 2025.
  Klasik SEO metriklerinin yerine içeriğin makine tarafından
  anlaşılabilirliğini ölçmeyi önerir; AnswRank'ın "klasik SEO yüzeyini değil,
  makine-okunabilir yüzeyi ölçme" tasarım kararıyla örtüşür.
  [arXiv:2507.03169](https://arxiv.org/abs/2507.03169)
- **[8] Web arama ile üretken AI yanıtlarının karşılaştırması** —
  *Navigating the Shift: A Comparative Analysis of Web Search and Generative
  AI Response Generation* — Chen et al., arXiv 2026.
  Geleneksel web arama ile üretken AI yanıtları arasındaki yapısal farkları
  karşılaştırır; "traffic discovery is moving from blue links to answers"
  motivasyonunun akademik dayanağıdır.
  [arXiv:2601.16858](https://arxiv.org/abs/2601.16858)
