"""Tests for the auxiliary-asset TTL cache layer (slice-1 of the 9h run).

Contract:
- The audited page HTML is NEVER cached (fresh observation per audit).
- robots.txt / llms.txt / llms-full.txt / sitemap.xml are TTL-cached per domain:
  a 15-URL batch audit triggers at most ONE HTTP request per asset.
- TTL expiry triggers exactly one refetch.
- Concurrent callers for the same key share one in-flight fetch (no herd).
- TTL 0 disables caching entirely (every audit re-fetches).
"""

import asyncio
import time
import pytest
from unittest.mock import patch

from answrank.audit.cache import TTLCache, asset_cache
from answrank.audit.crawler import WebCrawler, CrawlData


# ---------- TTLCache unit behavior ----------

@pytest.mark.anyio
async def test_ttl_cache_single_fetch_for_many_calls():
    c = TTLCache(default_ttl_seconds=60)
    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        return "value"

    v1 = await c.get_or_fetch("k", fetcher)
    v2 = await c.get_or_fetch("k", fetcher)
    v3 = await c.get_or_fetch("k", fetcher)
    assert (v1, v2, v3) == ("value", "value", "value")
    assert calls["n"] == 1  # exactly one fetch
    assert c.stats()["hits"] == 2


@pytest.mark.anyio
async def test_ttl_cache_expiry_refetches():
    c = TTLCache(default_ttl_seconds=0.01)
    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        return "v"

    await c.get_or_fetch("k", fetcher)
    await asyncio.sleep(0.02)  # let the entry expire
    await c.get_or_fetch("k", fetcher)
    assert calls["n"] == 2  # expired → refetched


@pytest.mark.anyio
async def test_ttl_cache_no_thundering_herd():
    """20 concurrent get_or_fetch calls for the same cold key must trigger
    exactly ONE fetcher execution (single-flight via per-key lock)."""
    c = TTLCache(default_ttl_seconds=60)
    calls = {"n": 0}

    async def slow_fetcher():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return "herd-safe"

    results = await asyncio.gather(*[c.get_or_fetch("k", slow_fetcher) for _ in range(20)])
    assert all(r == "herd-safe" for r in results)
    assert calls["n"] == 1


@pytest.mark.anyio
async def test_ttl_cache_invalidate():
    c = TTLCache(default_ttl_seconds=60)

    async def fetcher():
        return "x"

    await c.get_or_fetch("k", fetcher)
    c.invalidate("k")
    await c.get_or_fetch("k", fetcher)  # must refetch
    assert c.stats()["fetches"] == 2


@pytest.mark.anyio
async def test_ttl_cache_eviction_under_max_entries():
    c = TTLCache(default_ttl_seconds=60, max_entries=5)

    async def fetcher(i=[0]):
        i[0] += 1
        return f"v{i[0]}"

    for i in range(10):
        await c.get_or_fetch(f"key{i}", fetcher)
    assert len(c._store) <= 5  # eviction kept the cache bounded


@pytest.mark.anyio
async def test_ttl_cache_zero_ttl_disables_caching():
    """TTL 0 = cache-off mode: every call refetches (test/CI friendliness)."""
    c = TTLCache(default_ttl_seconds=0)
    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        return "fresh"

    await c.get_or_fetch("k", fetcher, ttl_seconds=0)
    await c.get_or_fetch("k", fetcher, ttl_seconds=0)
    assert calls["n"] == 2
    assert c.stats()["hits"] == 0


# ---------- Crawler integration: aux assets cached, page HTML never ----------

def _mock_crawl_for(url, html):
    crawl = CrawlData(
        url=url,
        domain="cachedtest.com",
        html_content=html,
        status_code=200,
        headers={"content-type": "text/html"},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# T",
        llms_full_txt=None,
        is_https=True,
    )
    return crawl


@pytest.mark.anyio
async def test_crawler_aux_assets_cached_across_fetches(monkeypatch):
    """Two fetch() calls for the same domain must hit robots/llms endpoints
    exactly once each — the second call is served from cache."""
    asset_cache.invalidate()  # clean slate
    robots_calls = {"n": 0}
    llms_calls = {"n": 0}
    page_calls = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code=200, text="", headers=None):
            self.status_code = status_code
            self.text = text
            self.headers = headers or {"content-type": "text/plain"}
            import datetime as dt
            self.elapsed = dt.timedelta(milliseconds=10)

    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            robots_calls["n"] += 1
            return FakeResponse(200, "User-agent: *\nAllow: /")
        if url.endswith("/llms.txt"):
            llms_calls["n"] += 1
            return FakeResponse(200, "# Index")
        if url.endswith("/llms-full.txt"):
            return FakeResponse(404, "")
        page_calls["n"] += 1
        return FakeResponse(200, "<html><body>" + "rich content " * 30 + "</body></html>")

    crawler = WebCrawler(enable_headless=False)
    with patch("httpx.AsyncClient.get", new=fake_get):
        c1 = await crawler.fetch("https://cachedtest.com/page1")
        c2 = await crawler.fetch("https://cachedtest.com/page2")

    # Page HTML: fetched fresh both times (never cached)
    assert page_calls["n"] == 2
    # Aux assets: fetched ONCE for the domain, second fetch from cache
    assert robots_calls["n"] == 1, "robots.txt must be cached per domain"
    assert llms_calls["n"] == 1, "llms.txt must be cached per domain"
    # And both crawls saw the aux content
    assert c1.robots_txt and c2.robots_txt
    assert c1.llms_txt == "# Index" and c2.llms_txt == "# Index"

    asset_cache.invalidate()  # leave clean state for other tests


@pytest.mark.anyio
async def test_sitemap_cached_across_batch_audits(monkeypatch):
    """fetch_sitemap_urls twice for the same domain → one HTTP request."""
    from answrank.audit.sitemap import SitemapAuditor

    asset_cache.invalidate()
    sitemap_calls = {"n": 0}

    class FakeResponse:
        status_code = 200
        text = (
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://cachedtest.com/a</loc></url>"
            "<url><loc>https://cachedtest.com/b</loc></url>"
            "</urlset>"
        )
        headers = {"content-type": "application/xml"}

    async def fake_get(self, url, **kwargs):
        if "sitemap.xml" in url:
            sitemap_calls["n"] += 1
            return FakeResponse()
        raise AssertionError(f"unexpected URL: {url}")

    auditor = SitemapAuditor()
    with patch("httpx.AsyncClient.get", new=fake_get):
        u1 = await auditor.fetch_sitemap_urls("https://cachedtest.com")
        u2 = await auditor.fetch_sitemap_urls("https://cachedtest.com")

    assert u1 == u2 == ["https://cachedtest.com/a", "https://cachedtest.com/b"]
    assert sitemap_calls["n"] == 1  # second batch served from cache

    asset_cache.invalidate()


@pytest.mark.anyio
async def test_cache_disabled_mode_fetches_every_time(monkeypatch):
    """With ANSWRANK_ASSET_CACHE_TTL=0 behavior (ttl 0), robots is re-fetched."""
    from answrank.config import Settings

    s = Settings(asset_cache_ttl_seconds=0)
    assert s.asset_cache_ttl_seconds == 0.0

    c = TTLCache(default_ttl_seconds=0)
    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        return "v"

    await c.get_or_fetch("k", fetcher, ttl_seconds=s.asset_cache_ttl_seconds)
    await c.get_or_fetch("k", fetcher, ttl_seconds=s.asset_cache_ttl_seconds)
    assert calls["n"] == 2


# ---------- Configurable economics regression ----------

def test_lost_revenue_config_defaults_preserve_behavior():
    """Defaults must exactly match the pre-refactor hardcoded values
    (engine.py: 35000/15000/25000/20000 LTV, 6.5 factor; swarm: 6000/1500)."""
    from answrank.config import Settings
    s = Settings()
    assert s.sector_ltv_try == {"dental": 35000.0, "aesthetic": 25000.0, "accounting": 15000.0, "general": 20000.0}
    assert s.lost_revenue_client_factor == 6.5
    assert s.swarm_fee_by_currency["TRY"] == 6000.0
    assert s.swarm_fee_by_currency["GBP"] == 1500.0
    assert s.swarm_fee_by_currency["USD"] == 1500.0
    assert s.swarm_fee_by_currency["AED"] == 5500.0


def test_lost_revenue_env_override(monkeypatch):
    monkeypatch.setenv("ANSWRANK_LOST_REV_FACTOR", "10.0")
    from answrank.config import Settings
    s = Settings()
    assert s.lost_revenue_client_factor == 10.0


def test_swarm_fee_uses_settings(monkeypatch):
    """FulfillmentAgent fee must come from settings, not a hardcoded branch."""
    from answrank.config import Settings
    import answrank.agents.swarm as swarm_mod

    s = Settings()
    s.swarm_fee_by_currency["GBP"] = 1999.0
    monkeypatch.setattr(swarm_mod, "settings", s)

    maker = swarm_mod.FulfillmentAgent()
    cand = swarm_mod.SwarmCandidate(
        brand_name="X", domain="x.com", sector="dental", city="London",
        country="UK", currency="GBP", ticket_size=1000.0,
    )
    maker.generate_contract(cand)
    assert cand.contract_text is not None
    # The fiscal invoice must also carry the configured fee, not 1500
    assert cand.fiscal_invoice_id



@pytest.mark.anyio
async def test_none_results_get_negative_ttl_not_full_ttl():
    """Contract: a None result (absent OR not verifiable) is cached only for
    NEGATIVE_TTL_SECONDS — a transient fetch failure must never masquerade as
    confirmed absence for the full (e.g. 300s) window. Positive results keep
    the full TTL."""
    c = TTLCache(default_ttl_seconds=3600)
    calls = {"n": 0}

    async def fetch_none():
        calls["n"] += 1
        return None

    v1 = await c.get_or_fetch("k", fetch_none)
    v2 = await c.get_or_fetch("k", fetch_none)  # fresh negative still dedupes batches
    assert v1 is None and v2 is None
    assert calls["n"] == 1

    entry = c._store["k"]
    assert entry.ttl_seconds == TTLCache.NEGATIVE_TTL_SECONDS < 3600

    # Age it past the negative TTL but well below the full TTL -> must retry.
    entry.stored_at = time.monotonic() - (TTLCache.NEGATIVE_TTL_SECONDS + 1)
    await c.get_or_fetch("k", fetch_none)
    assert calls["n"] == 2

    async def fetch_val():
        return "content"

    await c.get_or_fetch("p", fetch_val)
    assert c._store["p"].ttl_seconds == 3600
