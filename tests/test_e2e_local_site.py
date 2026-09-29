"""End-to-end smoke test: a REAL local HTTP site served by an in-process server.

This is the first fully-integrated test in the suite that exercises the whole
pipeline against a genuine HTTP server (no mocks on the crawler path):

  local site (robots.txt + llms.txt + sitemap.xml + pages)
    → WebCrawler.fetch (real httpx requests against 127.0.0.1)
    → all 8 analyzers
    → AuditEngine.audit_url
    → ReportGenerator markdown/html
    → cache behavior across the batch
"""

import threading
import pytest
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler


SITE_ROBOTS = """# AnswRank E2E test site
User-agent: *
Allow: /
Disallow: /private/

# Priority AI search bots
User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: Google-Extended
Allow: /

# Training bots
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

# Block scraper
User-agent: Bytespider
Disallow: /

Sitemap: http://127.0.0.1:{{PORT}}/sitemap.xml
# LLM discovery: http://127.0.0.1:{{PORT}}/llms.txt
"""

SITE_LLMS = """# E2E Test Klinik — İstanbul Dental Resmi Bilgi Dizini

> E2E Test Klinik, İstanbul bölgesinde garantili implant, zirkonyum kaplama ve estetik diş hekimliği alanında uzmanlaşmış sağlık kuruluşudur.

## Temel Bilgiler
- **Marka:** E2E Test Klinik
- **Konum:** İstanbul, Türkiye
- **Fiyatlandırma Politikası:** Şeffaf taban fiyat tarifesi.

## Uzmanlıklar
- İmplant tedavisi 98% başarı oranı.
- 20 yıllık deneyim.

## İletişim
- https://e2etest.local/iletisim
"""

SITE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>http://127.0.0.1:{port}/</loc></url>
  <url><loc>http://127.0.0.1:{port}/tedavi</loc></url>
</urlset>
"""

# NOTE: contains literal percent signs (%98 etc.) — never use %-formatting on this.
# Port injection happens via .replace("{{PORT}}", str(port)) at request time.
PAGE_HOME = """<!DOCTYPE html>
<html lang="tr">
<head>
<title>E2E Test Klinik — İstanbul İmplant ve Estetik Diş</title>
<meta name="description" content="İstanbul bölgesinde 20 yıllık deneyimle implant, zirkonyum kaplama ve estetik diş tedavileri.">
<link rel="canonical" href="http://127.0.0.1:{{PORT}}/">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Dentist",
  "name": "E2E Test Klinik",
  "telephone": "+902120000000",
  "address": {"@type": "PostalAddress", "addressLocality": "İstanbul"},
  "priceRange": "$$",
  "sameAs": ["https://maps.google.com/?cid=12345", "https://linkedin.com/company/e2etest"]
}
</script>
</head>
<body>
<h1>İstanbul İmplant Tedavisi</h1>
<h2>İmplant Fiyatları ve Garanti</h2>
<p>E2E Test Klinik olarak 20 yılda 10.000 başarılı implant operasyonu gerçekleştirdik. İstanbul implant tedavisi fiyatlarımız şeffaftır.</p>
<p>Dr. Test belirtmektedir: "Kliniğimizde %98 başarı oranıyla 3.500 vaka tamamlanmıştır."</p>
<p>İstanbul bölgesinde uzman hekim kadromuzla implant, zirkonyum ve estetik diş hizmetleri vermekteyiz. Türkiye genelinde hastalarımıza hizmet veriyoruz.</p>
<p>Fiyat bilgisi: implant tedavisi 15.000 TL'den başlar, onaylı malzeme sertifikası ile takdim edilir.</p>
</body>
</html>
"""


class _SiteHandler(BaseHTTPRequestHandler):
    port_holder = {"port": 8123}
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass  # silence

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.port_holder["port"]
        if self.path == "/robots.txt":
            self._send(SITE_ROBOTS.replace("{{PORT}}", str(port)).encode("utf-8"), "text/plain")
        elif self.path == "/llms.txt":
            self._send(SITE_LLMS.encode("utf-8"), "text/plain")
        elif self.path == "/llms-full.txt":
            self._send(b"full", "text/plain")
        elif self.path == "/sitemap.xml":
            self._send(SITE_SITEMAP.format(port=port).encode("utf-8"), "application/xml")
        elif self.path == "/tedavi":
            body = PAGE_HOME.replace("{{PORT}}", str(port)).replace("İstanbul İmplant Tedavisi", "Zirkonyum Tedavisi")
            self._send(body.encode("utf-8"), "text/html")
        elif self.path == "/private/x":
            self.send_response(403)
            self.end_headers()
        else:
            self._send(PAGE_HOME.replace("{{PORT}}", str(port)).encode("utf-8"), "text/html")


@pytest.fixture(scope="module")
def live_site():
    """Starts a real threaded HTTP server on a random localhost port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SiteHandler)
    port = server.server_address[1]
    _SiteHandler.port_holder["port"] = port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_e2e_full_audit_pipeline(live_site):
    """Real HTTP fetch → 8 analyzers → scored report → markdown/html rendering."""
    from answrank.audit.engine import AuditEngine
    from answrank.audit.cache import asset_cache
    from answrank.reporting.generator import ReportGenerator

    asset_cache.invalidate()
    engine = AuditEngine()
    res = await engine.audit_url(live_site, sector="dental")

    assert res.domain == "127.0.0.1" or res.domain.startswith("127.0.0.1")
    assert 0 <= res.overall_score <= 100
    # The site carries strong robots (OAI-SearchBot allowed) and llms.txt
    assert res.categories.robots.score > 10
    assert res.categories.llms_txt.score >= 10  # llms.txt present and structured
    # JSON-LD Dentist schema present
    assert res.categories.schema_jsonld.score > 8
    # Lost-revenue model ran with configured factor
    assert res.lost_revenue_estimate_monthly_try > 0

    # Reports render without error
    md = ReportGenerator().to_markdown(res)
    assert "AI Görünürlük Denetimi" in md
    assert "Ölçüm Şeffaflık Notu" in md  # honesty note (audit B.5 fix)

    # Aux assets were cached during the first audit
    stats = asset_cache.stats()
    assert stats["fetches"] >= 2  # robots + llms at least
    asset_cache.invalidate()


@pytest.mark.anyio
async def test_e2e_cache_across_two_audits(live_site):
    """A second audit of the same site must not re-fetch robots/llms."""
    from answrank.audit.engine import AuditEngine
    from answrank.audit.cache import asset_cache

    asset_cache.invalidate()
    engine = AuditEngine()

    await engine.audit_url(live_site, sector="dental")
    f1 = asset_cache.stats()["fetches"]
    await engine.audit_url(live_site, sector="dental")
    f2 = asset_cache.stats()["fetches"]
    assert f2 == f1, "aux assets must be served from cache on the second audit"

    # And both audits saw robots content
    assert asset_cache.stats()["entries"] >= 2
    asset_cache.invalidate()


@pytest.mark.anyio
async def test_e2e_sitemap_batch_audit(live_site):
    """Sitemap batch audit: real sitemap fetch, real page audits, weakest first."""
    from answrank.audit.sitemap import SitemapAuditor
    from answrank.audit.cache import asset_cache

    asset_cache.invalidate()
    auditor = SitemapAuditor()

    urls = await auditor.fetch_sitemap_urls(live_site, max_urls=5)
    assert any("/tedavi" in u for u in urls), "sitemap must list the /tedavi page"
    assert live_site in urls or urls[0].startswith("http://127.0.0.1")

    results = await auditor.batch_audit(live_site, sector="dental", max_urls=5, concurrency=2)
    assert len(results) >= 2  # both sitemap pages audited
    # Weakest-first ordering invariant
    scores = [r.overall_score for r in results]
    assert scores == sorted(scores)
    asset_cache.invalidate()


@pytest.mark.anyio
async def test_e2e_deep_audit_with_rag(live_site):
    """The 360° deep audit on the real site: RAG must score from the real
    field (regression A.1) and composite must include its 20% weight."""
    from answrank.audit.engine import AuditEngine
    from answrank.audit.cache import asset_cache

    asset_cache.invalidate()
    engine = AuditEngine()
    res = await engine.audit_url_deep(
        url=live_site, sector="dental", brand_name="E2E Test Klinik",
        probe_waf=False, check_grounding=False, check_rag=True,
    )

    assert res.rag_analysis is not None
    real_score = res.rag_analysis.get("rag_retrieval_score")
    assert real_score is not None and 0.0 <= real_score <= 100.0
    # The site has dense, quotable content — RAG must be non-trivial
    assert real_score > 0.0

    # Composite renormalizes over EXECUTED dims only (16 Eyl C9): base 45 + RAG 20
    earned = res.base_audit.overall_score * 0.45 + 20.0 * (real_score / 100.0)
    possible = 45.0 + 20.0
    if res.adversarial:
        earned += max(0.0, 10.0 * (1.0 - (res.adversarial.get("risk_score", 0) / 100.0)))
        possible += 10.0
    expected = round(100.0 * earned / possible, 1)
    assert res.composite_deep_score == pytest.approx(expected, abs=0.15)

    # Key findings quote the REAL RAG score
    if res.rag_analysis.get("total_chunks_extracted", 0) > 0:
        assert any(f"%{real_score:.0f}" in f for f in res.key_findings) or not res.key_findings
    asset_cache.invalidate()


@pytest.mark.anyio
async def test_e2e_fix_generation_for_site(live_site):
    """Fix bundle generated for the live site uses the 27-bot config."""
    from answrank.reporting.fix_generator import FixGenerator

    fg = FixGenerator()
    robots = fg.generate_robots_txt("e2etest.local")
    assert "User-agent: OAI-SearchBot" in robots
    assert "User-agent: Bytespider\nDisallow: /" in robots
    llms = fg.generate_llms_txt("E2E Test Klinik", "e2etest.local", "dental", "İstanbul")
    assert "# E2E Test Klinik" in llms
