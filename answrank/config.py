"""Configuration and settings for AnswRank."""

import os
from typing import Dict, List
from pydantic import BaseModel, Field

class Settings(BaseModel):
    """AnswRank global configuration settings."""
    app_name: str = "AnswRank AEO Engine"
    app_version: str = "1.0.0"

    # GVK 89/13 hizmet-ihracat kazanç indirim orani (11257 sayili CBK, 2026: %100)
    export_income_deduction_rate: float = 1.0

    # E3 mini-probe (D-16.09-M): herkese-açık ücretsiz yüzeyin IP-başına-24saya kotası.
    mini_probe_daily_limit_per_ip: int = 10

    # E1 GEO İzleme kademesi (D-16.09-M karar 4): ayrı MRR kademesi.
    monitor_monthly_price_try: float = 2500.0
    # Madde-7.3 fulfillment eşiği: satılan +12–15 bandının tabanı (C8 ile hizalı —
    # sözleşme target_delta_score defaultu da 12'dir; ikisi birden oynarsa drift testi kırar).
    monitor_guarantee_score_delta_min: int = 12
    db_path: str = Field(default_factory=lambda: os.getenv("ANSWRANK_DB_PATH", "answrank.db"))
    user_agent: str = "AnswRankAuditBot/1.0 (+https://answrank.ai; Generative Engine Compliance Analyzer)"
    timeout_seconds: float = 15.0

    # Auxiliary HTTP asset cache (robots.txt / llms.txt / llms-full.txt / sitemap.xml).
    # The audited page HTML itself is NEVER cached. TTL can be disabled with 0
    # (cache off) — useful for tests and repeated fresh audits.
    asset_cache_ttl_seconds: float = Field(
        default_factory=lambda: float(os.getenv("ANSWRANK_ASSET_CACHE_TTL", "300"))
    )

    # --- Configurable economics (audit finding: hardcoded multipliers) ---
    # Lost-revenue estimate: LTV x visibility-gap x monthly-potential-clients factor.
    # The 6.5 factor is a conservative "potential clients lost per month" constant
    # documented as a model assumption, NOT a measured value (see B.5 in the audit).
    lost_revenue_client_factor: float = Field(
        default_factory=lambda: float(os.getenv("ANSWRANK_LOST_REV_FACTOR", "6.5"))
    )

    # Sector LTV tables (TRY) used by the lost-revenue model — values match the
    # historical engine.py constants exactly (behavior-preserving extraction);
    # exposed so a deployment can calibrate per market.
    sector_ltv_try: Dict[str, float] = Field(
        default_factory=lambda: {
            "dental": 35000.0,
            "aesthetic": 25000.0,
            "accounting": 15000.0,
            "general": 20000.0,
        }
    )

    # Swarm contract fee per currency (audit finding: fee hardcoded in swarm.py)
    swarm_fee_by_currency: Dict[str, float] = Field(
        default_factory=lambda: {
            "TRY": 6000.0,   # domestic monthly retainer
            "GBP": 1500.0,
            "USD": 1500.0,
            "EUR": 1500.0,
            "AED": 5500.0,   # UAE market equivalent
        }
    )

    # 8 Category Weights (Sum must equal 100)

    # Critical AI Bots categorized into 3 tiers (authoritative count = sum of
    # the three lists below — never a literal). Registry re-verified on
    # 15 Sept 2026 against the knownagents.com agent directory (updated daily):
    # each token below was confirmed by HTTP-200 on its /agents/<slug> page AND
    # by the exact `User-agent:` string that directory documents for robots.txt.
    # (Prior revision carried three non-existent Tier-3 tokens — "Google-Sessel",
    # "ChatGPT-SearchUser", "Meta-ExternalAgent-User" — all 404 in the directory
    # and now removed; the real Meta user-initiated fetcher, Meta-ExternalFetcher,
    # already lives in Tier 2. New 2026 answer engines added: xAI/Grok, Kimi, Amazon.)
    #
    # Tier 1 — AI Search & Citation crawlers (11): must be allowed for AEO
    ai_bots_search: List[str] = [
        "OAI-SearchBot",        # OpenAI ChatGPT Search citations
        "PerplexityBot",        # Perplexity Sonar indexing
        "Claude-SearchBot",     # Anthropic Claude web search
        "Google-Extended",      # Google Gemini / AI Overviews
        "Bingbot",              # Microsoft Copilot search corpus
        "Applebot-Extended",    # Apple Intelligence
        "Amazonbot",            # Amazon Rufus / Q search
        "YouBot",               # You.com AI search
        "xAI-SearchBot",        # xAI Grok search index (added Sept 2026)
        "Kimi-SearchBot",       # Moonshot Kimi search index (added Sept 2026)
        "Amzn-SearchBot",       # Amazon Q / Alexa search index (added Sept 2026)
    ]

    # Tier 2 — AI Training & model-preparation / indexing crawlers (14): strategically beneficial
    ai_bots_training: List[str] = [
        "GPTBot",               # OpenAI model training
        "ClaudeBot",            # Anthropic model training
        "Claude-Web",           # Anthropic web fetch (research)
        "CCBot",                # Common Crawl corpus
        "Bytespider",           # ByteDance (abuse tier — blocked by default)
        "Google-CloudVertexBot",# Google Vertex AI agents
        "GoogleOther",          # Google miscellaneous AI fetch
        "Meta-ExternalAgent",   # Meta AI training
        "Meta-ExternalFetcher", # Meta AI user-driven fetch
        "Diffbot",              # Knowledge-graph extraction
        "cohere-ai",            # Cohere training
        "Timpibot",             # Timp personal AI
        "ImagesiftBot",         # Hive image indexing
        "Bravebot",             # Brave independent index feeding AI/RAG (added Sept 2026)
    ]

    # Tier 3 — User-Driven Agent Fetchers: human/agent-initiated fetches.
    # +7 live-verified 16 Sept 2026 against knownagents.com /agents/<slug> pages
    # (HTTP 200 + documented "User-agent:" token). Known-Agents-Browser was
    # deliberately NOT added: its page token rendered truncated ("Known"),
    # an unverifiable UA we refuse to ship on a partial match.
    ai_bots_user_agents: List[str] = [
        "ChatGPT-User",         # OpenAI ChatGPT user browsing
        "Perplexity-User",      # Perplexity user-initiated fetch
        "Claude-User",          # Anthropic Claude user-initiated fetch
        "Kimi-User",            # Moonshot Kimi user-initiated fetch (added Sept 2026)
        "MistralAI-User",       # Mistral Le Chat user browsing (added Sept 2026)
        "Amzn-User",            # Amazon Alexa/Q user fetch (added Sept 2026)
        "DuckAssistBot",        # DuckDuckGo AI-assisted answers fetch (added Sept 2026)
        "AmazonBuyForMe",       # Amazon agentic shopping fetch (16 Eyl 2026 doğrulamalı)
        "CohereBot",            # Cohere agentic fetch — distinct UA from cohere-ai (16 Eyl 2026)
        "QwenBot",              # Alibaba Qwen agentic crawler (16 Eyl 2026)
        "Cursor",               # Anysphere Cursor agent browsing (16 Eyl 2026; generic token — substring match caveat noted in registry test)
        "Browserbase",          # Browserbase headless agent cloud (16 Eyl 2026)
        "Anchor",               # Anchor agentic browser (16 Eyl 2026; short generic token, accepted per directory UA verbatim)
        "SaaSBrowserBot",       # SaaS browser agent (16 Eyl 2026)
    ]

    # Pilot sectors supported

    @property
    def ai_bots_total(self) -> int:
        """Total curated AI bot count across the three tiers (single source of truth
        for marketing/legal copy so the number can never drift from the registry)."""
        return len(self.ai_bots_search) + len(self.ai_bots_training) + len(self.ai_bots_user_agents)

    @property
    def ai_bots_tier_summary(self) -> str:
        """e.g. '39 AI botu (11 arama + 14 eğitim + 14 kullanıcı-ajanı)' — derived live."""
        return (
            f"{self.ai_bots_total} AI botu "
            f"({len(self.ai_bots_search)} arama + {len(self.ai_bots_training)} eğitim "
            f"+ {len(self.ai_bots_user_agents)} kullanıcı-ajanı)"
        )

settings = Settings()
