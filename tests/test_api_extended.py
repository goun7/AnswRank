"""Additional API endpoint coverage (slice-4b): the endpoints the original
test_api.py left uncovered — POST /api/audit, GET /reports/{id},
/api/citations/monte-carlo, /api/deploy error paths, /api/telemetry,
/api/fiscal-report, /api/territory-locks, /api/rag-score, /api/artifacts/preview.
"""

from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from answrank.api.app import app
from answrank.audit.crawler import CrawlData
from answrank.models import AuditResult, CategoryScores, utc_now
from answrank.audit.analyzers import (
    RobotsAnalyzer, LlmsTxtAnalyzer, SchemaAnalyzer, MetaAnalyzer,
    CitabilityAnalyzer, EntityAnalyzer, TrustAnalyzer, NegativeAnalyzer,
)
from bs4 import BeautifulSoup


def _audit(domain="apix.com", score=48) -> AuditResult:
    soup = BeautifulSoup("<html><body><p>dental implants london pricing warranty content</p></body></html>", "html.parser")
    return AuditResult(
        audit_id=f"audit_apix_{domain.replace('.','_')}",
        url=f"https://{domain}", domain=domain, sector="dental", timestamp=utc_now(),
        overall_score=score, score_band="Foundation",
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
        lost_revenue_estimate_monthly_try=12000.0,
    )


def test_post_audit_endpoint_with_mocked_engine():
    fake_audit = _audit()
    crawl = CrawlData(
        url="https://apix.com", domain="apix.com",
        html_content="<html><body><p>dental implants london pricing warranty content</p></body></html>",
        status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /", is_https=True,
    )

    class FakeCrawler:
        async def fetch(self, url):
            return crawl

    fake_engine = MagicMock()
    fake_engine.crawler = FakeCrawler()
    fake_engine.audit_url = AsyncMock(return_value=fake_audit)

    with TestClient(app) as client, patch("answrank.api.app.engine", fake_engine):
        res = client.post("/api/audit", json={"url": "https://apix.com", "sector": "dental"})
    assert res.status_code == 200
    data = res.json()
    assert data["overall_score"] == 48
    assert data["domain"] == "apix.com"
    assert data["lost_revenue_monthly_try"] == 12000.0
    assert "categories" in data


def test_post_audit_endpoint_failure_returns_500():
    failing_engine = MagicMock()
    failing_engine.audit_url = AsyncMock(side_effect=RuntimeError("site down"))

    with TestClient(app) as client, patch("answrank.api.app.engine", failing_engine):
        res = client.post("/api/audit", json={"url": "https://fail.com"})
    assert res.status_code == 500
    detail = res.json()["detail"]
    assert "iç hata" in detail and "site down" not in detail  # no internal leak


def test_reports_endpoint_404_for_missing():
    with TestClient(app) as client:
        res = client.get("/reports/audit_nonexistent999")
    assert res.status_code == 404
    assert "denetim raporu bulunamadı" in res.json()["detail"].lower()


def test_reports_endpoint_serves_saved_audit():
    """Save an audit through the app DB handle, then fetch its HTML report."""

    fake_audit = _audit("reportx.com")

    class FakeDB:
        async def save_audit(self, a):
            self.saved = a
        async def get_audit(self, audit_id):
            if audit_id == fake_audit.audit_id:
                return {"raw_json": fake_audit.model_dump_json()}
            return None
        async def get_latest_citations_for_domain(self, domain):
            return None

    fake_db = FakeDB()
    with TestClient(app) as client, patch("answrank.api.app.db", fake_db):
        res = client.get(f"/reports/{fake_audit.audit_id}")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert fake_audit.domain in res.text


def test_monte_carlo_endpoint_honest_simulation():
    """/api/citations/monte-carlo must return the honest SIMULATION_MODE marker
    when no API keys are present."""
    with TestClient(app) as client:
        res = client.post("/api/citations/monte-carlo", json={
            "brand_name": "Test MC", "domain": "testmc.com", "iterations": 2,
        })
    assert res.status_code == 200
    data = res.json()
    assert data["measurement_mode"] == "DETERMINISTIC_SIMULATION"
    assert data["is_statistically_valid"] is False
    assert data["stability_grade"] == "SIMULATION_MODE"


def test_deploy_endpoint_local_target(tmp_path):
    with TestClient(app) as client:
        res = client.post("/api/deploy", json={
            "domain": "deploytest.com", "brand_name": "Deploy Test",
            "target": "local", "output_dir": str(tmp_path / "dist"),
        })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "robots.txt" in data["deployed_files"]


def test_deploy_endpoint_webhook_requires_url():
    with TestClient(app) as client:
        res = client.post("/api/deploy", json={
            "domain": "d.com", "brand_name": "B", "target": "webhook",
        })
    assert res.status_code == 400


def test_deploy_endpoint_wordpress_requires_credentials():
    with TestClient(app) as client:
        res = client.post("/api/deploy", json={
            "domain": "d.com", "brand_name": "B", "target": "wordpress",
        })
    assert res.status_code == 400


def test_deploy_endpoint_unsupported_target():
    with TestClient(app) as client:
        res = client.post("/api/deploy", json={
            "domain": "d.com", "brand_name": "B", "target": "ftp",
        })
    assert res.status_code == 400


def test_telemetry_endpoint_shape():
    with TestClient(app) as client:
        res = client.get("/api/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data and "is_live_ready" in data  # somut anahtarlar


def test_fiscal_report_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/fiscal-report")
    assert res.status_code == 200
    data = res.json()
    # The honest tax model: 80% exemption, not 100%
    assert "exemption_rate" in data or "exempt" in str(data).lower()
    if "exemption_rate" in data:
        assert data["exemption_rate"] == 0.8


def test_territory_locks_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/territory-locks")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_rag_score_endpoint_with_custom_questions():
    with TestClient(app) as client:
        res = client.post("/api/rag-score", json={
            "url": "https://ragx.com",
            "html_content": "<h1>Dental implants</h1><p>Implant pricing in London with warranty details.</p>",
            "questions": ["implant pricing london"],
        })
    assert res.status_code == 200
    data = res.json()
    assert "rag_retrieval_score" in data
    assert 0.0 <= data["rag_retrieval_score"] <= 100.0


def test_artifacts_preview_endpoint():
    with TestClient(app) as client:
        res = client.post("/api/artifacts/preview", json={
            "domain": "prev.com", "brand_name": "Preview Klinik", "sector": "dental",
        })
    assert res.status_code == 200
    data = res.json()
    assert "robots_txt" in data or "llms_txt" in data


def test_reports_endpoint_renders_citation_share_when_run_exists():
    """SoV bridge: a genuine stored citation run must surface in the report..."""
    from answrank.models import CitationRunResult
    fake_audit = _audit("sharebridge.com")
    cit = CitationRunResult(
        run_id="rb1", brand_name="ShareBridge", domain="sharebridge.com",
        sector="dental", city="Istanbul", total_runs=4, brand_citations_found=2,
        citation_rate_percentage=50.0, live_items_count=4,
        live_response_rate_percentage=100.0, is_fully_live=True,
    )

    class FakeDB:
        async def get_audit(self, audit_id):
            return {"raw_json": fake_audit.model_dump_json()}
        async def get_latest_citations_for_domain(self, domain):
            assert domain == "sharebridge.com"
            return cit

    with TestClient(app) as client, patch("answrank.api.app.db", FakeDB()):
        res = client.get(f"/reports/{fake_audit.audit_id}")
    assert res.status_code == 200
    assert "Alıntı Payı" in res.text and "%50" in res.text
    assert "canlı API ölçümüdür" in res.text


def test_reports_endpoint_says_unmeasured_without_citation():
    """...and its absence is stated honestly, never fabricated."""
    fake_audit = _audit("nocites.com")

    class FakeDB:
        async def get_audit(self, audit_id):
            return {"raw_json": fake_audit.model_dump_json()}
        async def get_latest_citations_for_domain(self, domain):
            return None

    with TestClient(app) as client, patch("answrank.api.app.db", FakeDB()):
        res = client.get(f"/reports/{fake_audit.audit_id}")
    assert "ölçülmedi" in res.text and "uydurulmaz" in res.text


def test_citations_latest_endpoint_serializes_real_run():
    from answrank.models import CitationRunResult
    cit = CitationRunResult(
        run_id="c9", brand_name="Ölçü", domain="latestcase.com", sector="general",
        city="Istanbul", total_runs=100, brand_citations_found=25,
        citation_rate_percentage=25.0, live_items_count=0,
        live_response_rate_percentage=0.0, is_fully_live=False,
    )

    class FakeDB:
        async def get_latest_citations_for_domain(self, domain):
            assert domain == "latestcase.com"
            return cit

    with TestClient(app) as client, patch("answrank.api.app.db", FakeDB()):
        res = client.get("/api/citations/latest", params={"domain": "latestcase.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] == "c9" and body["total_runs"] == 100
    assert body["is_fully_live"] is False and body["live_items_count"] == 0


def test_citations_latest_endpoint_returns_null_without_data():
    """The SoV dashboard cell reads this null and shows "ÖLÇÜLMEDİ" — the API
    itself must never invent a 0% record."""
    class FakeDB:
        async def get_latest_citations_for_domain(self, domain):
            return None

    with TestClient(app) as client, patch("answrank.api.app.db", FakeDB()):
        res = client.get("/api/citations/latest", params={"domain": "ghost.example"})
    assert res.status_code == 200 and res.json() is None


def test_api_audit_unreachable_domain_degrades_honestly():
    """P0-1 (16 Eyl): unreachable domain must not 500 nor fabricate scored verdict."""
    with TestClient(app) as client:
        r = client.post("/api/audit", json={"url": "https://yok-boyle-site-xyzabc.test",
                                            "sector": "dental"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score_band"] == "ÖLÇÜLEMEDİ"
    assert any("DOĞRULANAMADI" in w for w in body["crawl_warnings"])


def test_api_audit_bad_scheme_degrades_not_500():
    with TestClient(app) as client:
        r = client.post("/api/audit", json={"url": "file:///etc/passwd"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score_band"] == "ÖLÇÜLEMEDİ"
    assert any("DOĞRULANAMADI" in w for w in body["crawl_warnings"])


def test_api_deep_audit_unauditable_tier():
    with TestClient(app) as client:
        r = client.post("/api/audit/deep",
                        json={"url": "https://yok-boyle-site-xyzabc.test",
                              "sector": "dental", "brand_name": "Yok",
                              "probe_waf": False, "check_adversarial": False,
                              "check_grounding": False, "check_rag": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deep_tier"] == "UNAUDITABLE"
    assert any("360° derin denetim YAPILAMADI" in f for f in body["key_findings"])


def test_get_audit_by_id_roundtrip_and_honest_404(tmp_path, monkeypatch):
    import asyncio
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "aud.db"))
    from answrank.db import Database
    from answrank.audit.engine import AuditEngine
    from answrank.audit.crawler import CrawlData
    audit = AuditEngine().audit_crawl_data(CrawlData(
        url="https://stored.example", domain="stored.example",
        html_content="", status_code=200, headers={}), sector="dental")
    db = Database()
    asyncio.run(db.save_audit(audit, prospect_id="p1"))
    with TestClient(app) as client, patch("answrank.api.app.db", db):
        r = client.get(f"/api/audits/{audit.audit_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["audit_id"] == audit.audit_id  # id↔audit_id naming normalized
        assert body["domain"] == "stored.example"
        miss = client.get("/api/audits/olmayan-kayit")
        assert miss.status_code == 404
        assert "bulunamadı" in miss.json()["detail"]


def test_post_citations_response_exposes_live_split():
    """P1: rate without live/sim provenance is misreadable — primary response now
    carries the same split as the SoV bridge."""
    from answrank.models import CitationRunResult
    from answrank.citations.runner import MultiLLMCitationRunner
    res = CitationRunResult(
        run_id="r-live", brand_name="B", domain="b.example", sector="general",
        city="İstanbul", items=[], total_runs=100, brand_citations_found=10,
        citation_rate_percentage=10.0, live_items_count=60,
        live_response_rate_percentage=60.0, is_fully_live=False, top_competitors={})
    with TestClient(app) as client, \
         patch.object(MultiLLMCitationRunner, "run_citations",
                      new=AsyncMock(return_value=res)):
        r = client.post("/api/citations", json={"brand_name": "B", "domain": "b.example"})
    assert r.status_code == 200
    body = r.json()
    assert body["live_items_count"] == 60
    assert body["is_fully_live"] is False
    assert body["live_response_rate_percentage"] == 60.0
