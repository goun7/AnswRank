"""Tests for SitemapAuditor."""

import asyncio
from unittest.mock import patch, AsyncMock
from answrank.audit.sitemap import SitemapAuditor
from answrank.audit.crawler import CrawlData

def test_sitemap_batch_audit():
    auditor = SitemapAuditor()

    # Mock fetch_sitemap_urls
    with patch.object(
        auditor,
        "fetch_sitemap_urls",
        new=AsyncMock(return_value=["https://test.com/page1", "https://test.com/page2"]),
    ):
        # Mock engine.audit_url
        crawl1 = CrawlData(url="https://test.com/page1", domain="test.com", html_content="<p>Test</p>", status_code=200, headers={})
        res1 = auditor.engine.audit_crawl_data(crawl1)
        res1.overall_score = 40

        crawl2 = CrawlData(url="https://test.com/page2", domain="test.com", html_content="<p>Test</p>", status_code=200, headers={})
        res2 = auditor.engine.audit_crawl_data(crawl2)
        res2.overall_score = 80

        with patch.object(auditor.engine, "audit_url", side_effect=[res2, res1]):
            results = asyncio.run(auditor.batch_audit("https://test.com", max_urls=5))
            assert len(results) == 2
            # Should be sorted weakest page first!
            assert results[0].overall_score <= results[1].overall_score
            assert results[0].overall_score == 40

# --- Branch coverage: fetch failures, XML parse fallback, base-url fallback ---

def test_fetch_sitemap_network_error_falls_back_to_base():
    """Network exception during sitemap fetch -> warning logged, base URL returned."""
    auditor = SitemapAuditor()
    import httpx
    async def _boom(**kwargs):
        raise httpx.ConnectError("boom")
    class _FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): raise httpx.ConnectError("conn refused")
    with patch("answrank.audit.sitemap.httpx.AsyncClient", _FakeClient):
        urls = asyncio.run(auditor.fetch_sitemap_urls("https://test.com/anypage"))
        assert urls == ["https://test.com/anypage"]

def test_fetch_sitemap_non_200_returns_base():
    """Non-200 status -> no text -> fallback to base URL."""
    auditor = SitemapAuditor()
    class _Resp:
        status_code = 404
        text = ""
    class _FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return _Resp()
    with patch("answrank.audit.sitemap.httpx.AsyncClient", _FakeClient):
        urls = asyncio.run(auditor.fetch_sitemap_urls("https://badstatus.com/x"))
        assert urls == ["https://badstatus.com/x"]

def test_fetch_sitemap_malformed_xml_regex_fallback():
    """Malformed XML (but <loc> tags present) -> regex fallback extracts URLs."""
    auditor = SitemapAuditor()
    bad_xml = "<urlset><url><loc>https://regexfb.com/a</loc></url><url><loc>https://regexfb.com/b</loc></url>"
    class _Resp:
        status_code = 200
        text = bad_xml
    class _FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return _Resp()
    with patch("answrank.audit.sitemap.httpx.AsyncClient", _FakeClient):
        urls = asyncio.run(auditor.fetch_sitemap_urls("https://regexfb.com/"))
        assert "https://regexfb.com/a" in urls
        assert "https://regexfb.com/b" in urls

def test_fetch_sitemap_valid_xml_dedup():
    """Valid XML with duplicate URLs -> deduplicated list, max_urls respected."""
    auditor = SitemapAuditor()
    xml = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://dedup.com/a</loc></url>'
           '<url><loc>https://dedup.com/a</loc></url>'
           '<url><loc>https://dedup.com/b</loc></url>'
           '<url><loc>not-a-url</loc></url>'
           '</urlset>')
    class _Resp:
        status_code = 200
        text = xml
    class _FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return _Resp()
    with patch("answrank.audit.sitemap.httpx.AsyncClient", _FakeClient):
        urls = asyncio.run(auditor.fetch_sitemap_urls("https://dedup.com/", max_urls=10))
        assert urls == ["https://dedup.com/a", "https://dedup.com/b"]  # dedup + non-http filtered

def test_batch_audit_single_page_exception_logged():
    """A failing page in batch audit is skipped, others still returned."""
    auditor = SitemapAuditor()
    with patch.object(auditor, "fetch_sitemap_urls", new=AsyncMock(return_value=[
        "https://test.com/fail", "https://test.com/ok"
    ])):
        crawl = CrawlData(url="https://test.com/ok", domain="test.com", html_content="<p>Test</p>", status_code=200, headers={})
        good = auditor.engine.audit_crawl_data(crawl)
        async def _audit_url(url, sector="general"):
            if "fail" in url:
                raise RuntimeError("page exploded")
            return good
        with patch.object(auditor.engine, "audit_url", side_effect=_audit_url):
            results = asyncio.run(auditor.batch_audit("https://test.com"))
            assert len(results) == 1


def test_sitemap_index_expands_children():
    """A <sitemapindex> must be expanded one level into its child urlsets."""
    auditor = SitemapAuditor()
    index_doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://indexed.example/sitemap-pages.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    child_doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://indexed.example/a</loc></url>"
        "<url><loc>https://indexed.example/b</loc></url>"
        "</urlset>"
    )

    async def fake_get(self, url, **kw):
        class R:
            status_code = 200
            text = index_doc if url.endswith("/sitemap.xml") else child_doc
        return R()

    async def _drive():
        with patch("httpx.AsyncClient.get", new=fake_get):
            return await auditor.fetch_sitemap_urls("https://indexed.example")
    urls = asyncio.run(_drive())
    assert urls == ["https://indexed.example/a", "https://indexed.example/b"]


def test_flat_urlset_still_works_after_refactor():
    auditor = SitemapAuditor()
    flat = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://flat.example/x</loc></url>"
        "</urlset>"
    )

    async def fake_get(self, url, **kw):
        class R:
            status_code = 200
            text = flat
        return R()

    async def _drive():
        with patch("httpx.AsyncClient.get", new=fake_get):
            return await auditor.fetch_sitemap_urls("https://flat.example")
    urls = asyncio.run(_drive())
    assert urls == ["https://flat.example/x"]


def test_sitemap_index_stops_at_max_urls():
    auditor = SitemapAuditor()
    index_doc = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://maxed.example/s1.xml</loc></sitemap>"
        "<sitemap><loc>https://maxed.example/s2.xml</loc></sitemap>"
        "</sitemapindex>"
    )

    async def fake_get(self, url, **kw):
        class R:
            status_code = 200
            text = index_doc if url.endswith("/sitemap.xml") else (
                "<urlset><url><loc>https://maxed.example/p1</loc></url>"
                "<url><loc>https://maxed.example/p2</loc></url></urlset>"
            )
        return R()

    async def _drive():
        with patch("httpx.AsyncClient.get", new=fake_get):
            return await auditor.fetch_sitemap_urls("https://maxed.example", max_urls=2)
    urls = asyncio.run(_drive())
    assert urls == ["https://maxed.example/p1", "https://maxed.example/p2"]  # s2 never fetched
