"""Additional crawler coverage: SPA detection branches, headless fallback
paths, hydrate SSR fallback variants, and per-field fetch behaviors."""

import pytest
from unittest.mock import AsyncMock, patch

from answrank.audit.crawler import WebCrawler, HeadlessRenderer


RICH_HTML = """
<html><head><title>Dental Clinic London</title></head><body>
<h1>Leading Dental Implants in London</h1>
<p>We offer specialized All-on-4 dental implant restorations with over 20 years of accredited
clinical excellence in Harley Street, London.</p>
<p>Transparent fee structures, zero hidden costs, and comprehensive patient warranties are
guaranteed for every London patient.</p>
</body></html>
"""


# ---------------- HeadlessRenderer branches ----------------

def test_is_spa_stub_empty_html():
    assert HeadlessRenderer.is_spa_stub("") is True


def test_is_spa_stub_app_root():
    html = "<html><body><app-root></app-root></body></html>"
    assert HeadlessRenderer.is_spa_stub(html) is True


def test_is_spa_stub_noscript_javascript_required():
    html = ("<html><body><noscript>Please enable JavaScript to use this site. "
            "JavaScript is required for rendering.</noscript></body></html>")
    assert HeadlessRenderer.is_spa_stub(html) is True


def test_is_spa_stub_rich_text_not_stub():
    assert HeadlessRenderer.is_spa_stub(RICH_HTML) is False


def test_hydrate_ssr_fallback_no_next_data():
    """Without __NEXT_DATA__, the HTML returns unchanged."""
    html = "<html><body><p>plain content here</p></body></html>"
    assert HeadlessRenderer.hydrate_ssr_fallback(html) == html


def test_hydrate_ssr_fallback_invalid_json():
    """Invalid JSON inside __NEXT_DATA__ is tolerated (returns original)."""
    html = ('<html><body><div id="__next"></div>'
            '<script id="__NEXT_DATA__" type="application/json">{invalid json</script>'
            '</body></html>')
    assert HeadlessRenderer.hydrate_ssr_fallback(html) == html


def test_hydrate_ssr_fallback_walks_nested_state():
    """Deeply nested state strings are extracted into hydrated paragraphs."""
    html = (
        '<html><body><div id="__next"></div>'
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props": {"pageProps": {"clinic": {"title": "Harley Street Implants London Centre", '
        '"stats": {"successRate": "98 percent over twenty years of London practice"}}}}}'
        '</script></body></html>'
    )
    hydrated = HeadlessRenderer.hydrate_ssr_fallback(html)
    assert "Harley Street Implants London Centre" in hydrated
    assert "98 percent over twenty years of London practice" in hydrated
    assert "answrank-hydrated-content" in hydrated


@pytest.mark.anyio
async def test_render_playwright_returns_none_on_error():
    """Playwright missing/failing must degrade to None, never raise."""
    with patch("answrank.audit.crawler.HeadlessRenderer.render_playwright",
               AsyncMock(return_value=None)):
        result = await HeadlessRenderer.render_playwright("https://x.com")
        assert result is None


# ---------------- WebCrawler.fetch branches ----------------

class _FakeResp:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"content-type": "text/html"}
        import datetime as dt
        self.elapsed = dt.timedelta(milliseconds=50)


@pytest.mark.anyio
async def test_fetch_adds_https_scheme_when_missing():
    crawler = WebCrawler(enable_headless=False)

    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            r = _FakeResp(200, "User-agent: *\nAllow: /", {"content-type": "text/plain"})
        elif url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            r = _FakeResp(404, "", {"content-type": "text/plain"})
        else:
            r = _FakeResp(200, RICH_HTML, {"content-type": "text/html"})
        return r

    with patch("httpx.AsyncClient.get", new=fake_get):
        data = await crawler.fetch("noscheme.example.com")  # no scheme

    assert data.is_https is True  # https:// was assumed
    assert data.status_code == 200
    assert "Dental Implants" in data.html_content
    assert data.robots_txt == "User-agent: *\nAllow: /"


@pytest.mark.anyio
async def test_fetch_spa_stub_triggers_headless_render():
    """A React stub must trigger the headless render path; when the renderer
    returns richer HTML, it is used and flagged."""
    stub_html = ('<html><head><title>App</title></head><body>'
                 '<div id="root"></div>'
                 '<script src="/bundle.js"></script><script src="/vendor.js"></script>'
                 '</body></html>')
    rendered_html = ('<html><body><div id="root"><h1>Fully Rendered Clinic Content London</h1>'
                     '<p>Long descriptive text about dental services appears after hydration here.</p>'
                     '<p>More rendered content with pricing and warranty information.</p></div></body></html>')

    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            return _FakeResp(200, "User-agent: *\nAllow: /", {"content-type": "text/plain"})
        if url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            return _FakeResp(404, "", {"content-type": "text/plain"})
        return _FakeResp(200, stub_html, {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=True)
    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch.object(HeadlessRenderer, "render_playwright", AsyncMock(return_value=rendered_html)):
        data = await crawler.fetch("https://spa-test.com")

    assert data.headless_rendered is True
    assert data.is_spa_hydrated is True
    assert "Fully Rendered Clinic" in data.html_content
    assert data.status_code == 200


@pytest.mark.anyio
async def test_fetch_spa_stub_playwright_fails_falls_back_to_ssr_hydration():
    """When Playwright yields nothing usable, the SSR __NEXT_DATA__ hydration
    fallback must run."""
    stub_html = ('<html><body><div id="__next"></div>'
                '<script id="__NEXT_DATA__" type="application/json">'
                '{"props": {"pageProps": {"content": "Server rendered dental clinic text for London patients"}}}'
                '</script></body></html>')

    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            return _FakeResp(200, "User-agent: *\nAllow: /", {"content-type": "text/plain"})
        if url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            return _FakeResp(404, "", {"content-type": "text/plain"})
        return _FakeResp(200, stub_html, {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=True)
    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch.object(HeadlessRenderer, "render_playwright", AsyncMock(return_value=None)):
        data = await crawler.fetch("https://ssr-fallback.com")

    # SSR hydration extracted the text
    assert data.is_spa_hydrated is True
    assert "Server rendered dental clinic text" in data.html_content
    assert data.headless_rendered is False


@pytest.mark.anyio
async def test_fetch_status_403_triggers_headless_attempt():
    """A 403 (Cloudflare challenge) also triggers the headless fallback path."""
    rendered = ("<html><body><h1>Challenge-solved clinic page content</h1>"
                "<p>Rich rendered content follows after the challenge page bypass rendering.</p></body></html>")

    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            return _FakeResp(200, "User-agent: *\nAllow: /", {"content-type": "text/plain"})
        if url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            return _FakeResp(404, "", {"content-type": "text/plain"})
        return _FakeResp(403, "<html>challenge</html>", {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=True)
    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch.object(HeadlessRenderer, "render_playwright", AsyncMock(return_value=rendered)):
        data = await crawler.fetch("https://challenge-test.com")

    assert data.status_code == 200  # upgraded after successful render
    assert data.headless_rendered is True


@pytest.mark.anyio
async def test_fetch_aux_asset_non_text_content_type_not_parsed():
    """robots.txt served with a binary content type must NOT be treated as text."""
    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            return _FakeResp(200, "\x89PNG", {"content-type": "image/png"})
        if url.endswith("/llms.txt"):
            return _FakeResp(200, "# Index", {"content-type": "text/plain"})
        if url.endswith("/llms-full.txt"):
            return _FakeResp(404, "", {"content-type": "text/plain"})
        return _FakeResp(200, RICH_HTML, {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=False)
    with patch("httpx.AsyncClient.get", new=fake_get):
        data = await crawler.fetch("https://binary-robots.com")

    assert data.robots_txt is None  # rejected: not text/*
    assert data.llms_txt == "# Index"


@pytest.mark.anyio
async def test_fetch_network_errors_swallowed_for_aux_assets():
    """Network failures on aux assets must leave them None, not crash the audit —
    and must be recorded as fetch_warnings so a failure is never reported as a
    confirmed absence downstream."""
    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt") or url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            raise ConnectionError("aux down")
        return _FakeResp(200, RICH_HTML, {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=False)
    with patch("httpx.AsyncClient.get", new=fake_get):
        data = await crawler.fetch("https://auxerror.com")

    assert data.robots_txt is None
    assert data.llms_txt is None
    assert data.llms_full_txt is None
    assert data.status_code == 200  # main page still fetched
    assert len(data.fetch_warnings) == 3
    assert any("robots.txt" in w and "doğrulanamadı" in w for w in data.fetch_warnings)
    assert any("llms.txt" in w and "llms-full" not in w for w in data.fetch_warnings)
    assert any("llms-full.txt" in w for w in data.fetch_warnings)


@pytest.mark.anyio
async def test_fetch_true_404_absence_produces_no_warning():
    """A clean 404 is proven absence, not an unverifiable asset — no warning."""
    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt") or url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            return _FakeResp(404, "", {"content-type": "text/html"})
        return _FakeResp(200, RICH_HTML, {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=False)
    with patch("httpx.AsyncClient.get", new=fake_get):
        data = await crawler.fetch("https://absent.example")

    assert data.llms_txt is None
    assert data.fetch_warnings == []


@pytest.mark.anyio
async def test_audit_result_carries_crawl_warnings_end_to_end():
    """engine.audit_url -> AuditResult.crawl_warnings (UI/report must see them)."""
    from answrank.audit.engine import AuditEngine

    async def fake_get(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            raise ConnectionError("transient")
        if url.endswith("/llms.txt") or url.endswith("/llms-full.txt"):
            return _FakeResp(404, "", {"content-type": "text/html"})
        return _FakeResp(200, RICH_HTML, {"content-type": "text/html"})

    engine = AuditEngine()
    with patch("httpx.AsyncClient.get", new=fake_get):
        result = await engine.audit_url("https://carry-warnings.example")

    assert result.crawl_warnings, "transient robots.txt error must surface on AuditResult"
    assert any("robots.txt" in w for w in result.crawl_warnings)
    # round-trips through pydantic serialization (stored JSON contract)
    parsed = type(result).model_validate_json(result.model_dump_json())
    assert parsed.crawl_warnings == result.crawl_warnings


@pytest.mark.anyio
async def test_fetch_spa_total_render_failure_warns_partial_html():
    """When headless AND SSR-hydration both fail on an SPA stub the audit must
    warn that it scored partial HTML — never silently pretend completeness."""
    stub_html = ('<html><head><title>App</title></head><body>'
                 '<div id="root"></div>'
                 '<script src="/a.js"></script><script src="/b.js"></script>'
                 '</body></html>')

    async def fake_get(self, url, **kwargs):
        if url.endswith(("/robots.txt", "/llms.txt", "/llms-full.txt")):
            return _FakeResp(404, "", {"content-type": "text/html"})
        return _FakeResp(200, stub_html, {"content-type": "text/html"})

    crawler = WebCrawler(enable_headless=True)
    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch.object(HeadlessRenderer, "render_playwright", AsyncMock(return_value=None)):
        data = await crawler.fetch("https://unrenderable.example")

    assert data.headless_rendered is False
    assert data.is_spa_hydrated is False
    assert any("kısmi HTML" in w for w in data.fetch_warnings)
