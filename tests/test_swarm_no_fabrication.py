"""Regression tests for the swarm + SSE audit findings.

Covers:
- P0.3: SentryAgent must perform a REAL re-audit (no +25 fabrication)
- P1.2: SSE stream must run the real pipeline (no hard-coded 'Baseline: 38/100')
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from answrank.agents.swarm import (
    SwarmOrchestrator,
    SwarmCandidate,
    SwarmStage,
    SentryAgent,
)
from answrank.audit.crawler import CrawlData


def _make_candidate(**kwargs):
    defaults = dict(
        brand_name="London Dental Studio",
        domain="londondentalstudio.co.uk",
        sector="dental",
        city="London",
        country="UK",
        currency="GBP",
        ticket_size=3000.0,
    )
    defaults.update(kwargs)
    return SwarmCandidate(**defaults)


RICH_HTML = """
<html lang="tr"><head><title>London Dental</title>
<meta name="description" content="Dental implants in London with 20 years experience.">
<script type="application/ld+json">{"@type": "Dentist", "name": "London Dental"}</script>
</head><body>
<h1>Dental Implant London</h1>
<h2>Implant Costs</h2>
<p>London Dental Studio provides implant treatments with 98% success rate over 20 years.</p>
<p>Our specialists in London handle 3500+ cases with transparent pricing.</p>
</body></html>
"""


@pytest.mark.anyio
async def test_sentry_measures_real_score_via_live_fetch():
    """SentryAgent.measure_current_score must fetch the site and produce a real
    audit score (not deep_score + 25)."""
    sentry = SentryAgent()
    cand = _make_candidate(deep_score=30.0)

    mock_crawl = CrawlData(
        url="https://londondentalstudio.co.uk",
        domain="londondentalstudio.co.uk",
        html_content=RICH_HTML,
        status_code=200,
        headers={},
        robots_txt="User-agent: *\nAllow: /",
        is_https=True,
    )

    with patch.object(sentry.audit_engine.crawler, "fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_crawl
        score = await sentry.measure_current_score(cand)

    # The measured score is whatever the real audit yields (plausible band),
    # NOT 30+25=55 by construction.
    assert score is not None
    assert 0 <= score <= 100
    assert score != 55  # the old fabrication hardcoded deep_score + 25


@pytest.mark.anyio
async def test_sentry_does_not_fabricate_when_fetch_fails():
    """If the live fetch fails, no score and no delta may be fabricated."""
    sentry = SentryAgent()
    cand = _make_candidate(deep_score=30.0)

    async def failing_fetch(url):
        raise ConnectionError("site down")

    with patch.object(sentry.audit_engine.crawler, "fetch", side_effect=failing_fetch):
        res = await sentry.evaluate_retention(cand)

    assert res["is_guarantee_met"] is False
    assert res["current_score"] is None
    assert cand.stage == SwarmStage.ACTIVE_MONITORING  # not fake DELTA_CHECKED


@pytest.mark.anyio
async def test_full_pipeline_emits_real_events():
    """run_full_pipeline_sync with on_event must emit genuine step events whose
    messages reflect actual state (real deep score in the auditor message)."""
    orch = SwarmOrchestrator()
    cand = _make_candidate()

    mock_crawl = CrawlData(
        url="https://londondentalstudio.co.uk",
        domain="londondentalstudio.co.uk",
        html_content=RICH_HTML,
        status_code=200,
        headers={},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# London Dental\n> London implant centre.",
        is_https=True,
    )

    events = []

    async def on_event(agent, message):
        events.append((agent, message))

    with patch.object(orch.auditor.engine.crawler, "fetch", new_callable=AsyncMock) as mock_fetch, \
         patch.object(orch.sentry, "measure_current_score", new_callable=AsyncMock) as mock_measure:
        mock_fetch.return_value = mock_crawl
        mock_measure.return_value = 42  # real live re-audit result
        await orch.run_full_pipeline_sync(cand, on_event=on_event)

    agents = [a for a, _ in events]
    assert "AGENT_01_SCOUT" in agents
    assert "AGENT_02_AUDITOR" in agents
    assert "AGENT_03_HUNTER" in agents
    assert "AGENT_05_SENTRY" in agents

    # The auditor event must carry the REAL measured deep score,
    # not a hard-coded "Baseline: 38/100"
    auditor_msg = next(m for a, m in events if a == "AGENT_02_AUDITOR")
    assert "38/100" not in auditor_msg
    assert str(int(cand.deep_score)) in auditor_msg

    # The final stage must reflect the real measured delta path
    assert cand.stage == SwarmStage.DELTA_CHECKED


def test_sse_stream_runs_real_pipeline():
    """/api/swarm/stream must execute the real pipeline — the response events
    must contain the actual final stage, and must NOT contain the old
    hard-coded 'Baseline: 38/100' text."""
    from answrank.api.app import app

    with TestClient(app) as client:
        with patch("answrank.agents.swarm.AuditEngine") as engine_cls, \
             patch("answrank.agents.swarm.SwarmOrchestrator.seed_target") as seed:
            # Build a deterministic fake engine that returns a stable audit
            from answrank.audit.analyzers import (
                RobotsAnalyzer, LlmsTxtAnalyzer, SchemaAnalyzer, MetaAnalyzer,
                CitabilityAnalyzer, EntityAnalyzer, TrustAnalyzer, NegativeAnalyzer,
            )
            from bs4 import BeautifulSoup
            from answrank.models import AuditResult, CategoryScores, utc_now

            soup = BeautifulSoup(RICH_HTML, "html.parser")
            fake_audit = AuditResult(
                audit_id="audit_sse",
                url="https://sse-test.com",
                domain="sse-test.com",
                sector="dental",
                timestamp=utc_now(),
                overall_score=50,
                score_band="Foundation",
                categories=CategoryScores(
                    robots=RobotsAnalyzer().analyze("User-agent: *\nAllow: /"),
                    llms_txt=LlmsTxtAnalyzer().analyze("# T\n> s\n## A\n## B", None),
                    schema_jsonld=SchemaAnalyzer().analyze(soup, sector="dental"),
                    meta_architecture=MetaAnalyzer().analyze(soup),
                    citability_rag=CitabilityAnalyzer().analyze(soup),
                    entity_coherence=EntityAnalyzer().analyze(soup, domain="sse-test.com"),
                    trust_stack=TrustAnalyzer().analyze(soup, is_https=True),
                    negative_signals=NegativeAnalyzer().analyze(soup),
                ),
            )

            class FakeCrawler:
                async def fetch(self, url):
                    return CrawlData(
                        url=url,
                        domain="sse-test.com",
                        html_content=RICH_HTML,
                        status_code=200,
                        headers={},
                        robots_txt="User-agent: *\nAllow: /",
                        is_https=True,
                    )

            class FakeEngine:
                crawler = FakeCrawler()
                async def audit_url_deep(self, url, **kwargs):
                    from answrank.models import DeepAuditResult
                    return DeepAuditResult(
                        base_audit=fake_audit,
                        waf_probe=None,
                        adversarial=None,
                        entity_grounding=None,
                        rag_analysis=None,
                        composite_deep_score=55.0,
                        deep_tier="STABLE",
                        key_findings=[],
                    )
                def audit_crawl_data(self, crawl, sector="general"):
                    return fake_audit

            engine_cls.return_value = FakeEngine()
            cand = _make_candidate(brand_name="SSE Test", domain="sse-test.com")
            seed.return_value = cand

            # Patch sentry's live measurement to a deterministic value
            with patch("answrank.agents.swarm.SentryAgent.measure_current_score", new_callable=AsyncMock) as mm:
                mm.return_value = 50

                with client.stream("GET", "/api/swarm/stream", params={
                    "brand": "SSE Test", "domain": "sse-test.com", "city": "London", "country": "UK",
                }) as response:
                    assert response.status_code == 200
                    body = "".join(response.iter_text())

    # Real pipeline events present
    assert "AGENT_01_SCOUT" in body
    assert "AGENT_02_AUDITOR" in body
    assert "PIPELINE_DONE" in body
    # The old hard-coded fabrication must be GONE
    assert "Baseline: 38/100" not in body


def test_no_unconditional_money_back_guarantee_in_pitches():
    """Madde 7.3 koşulludur (delta >= 12 puan); hiçbir dilde koşulsuz '%100
    para iadesi' vaadi verilemez — kanıtlanmamış satış iddiası."""
    from answrank.agents.swarm import HunterAgent
    hunter = HunterAgent()
    for country in ("TR", "UK", "US", "DE", "UAE"):
        cand = SwarmCandidate(
            brand_name="Klinik", domain="k.example", city="X",
            country=country, currency="EUR", deep_score=30.0,
            lost_revenue_monthly=1000.0)
        pitch = hunter.generate_pitch(cand)
        low = pitch.lower()
        assert "100% money-back" not in low, f"{country}: koşulsuz iade vaadi"
        assert "100% money back" not in low, f"{country}: koşulsuz iade vaadi"


def test_landing_guarantee_matches_engine_threshold():
    """Satış yüzeyi (landing) motorun gerçek eşiği dışında bir aralık vaat
    edemez: delta.py yalnızca score_delta >= 12 (puan) uygular; +%12 ila +%15
    aralığı motorda yoktur ve 'yüzde' motorun puan-farkı semantiğine aykırı."""
    from answrank.audit.delta import DeltaEngine
    import inspect
    src = inspect.getsource(DeltaEngine.calculate_delta)
    # motor tek bir puan eşiği uygular — aralık değil
    assert "guarantee_threshold: int = 12" in src
    assert "15" not in src, "motorda 15 eşiği varsa metinle hizalanmalı"

    html = open("answrank/api/templates/landing.html", encoding="utf-8").read()
    for bad in ("+%12 ila +%15", "+12% to +15%", "+12 ile +15",
                "Wachstum von +12% bis +15%",
                "Minimum +%12 Alıntı Artışı", "+12% Minimum Citation Lift"):
        assert bad not in html, f"landing, motor eşiğine aykırı vaat: {bad}"

    # kesin-sonuç başarı iddiası: sonuç 'olası' olarak sunulmalı
    for bad in ("%100 doğrudan hasta yönlendirmesi",
                "100% doğrudan hasta yönlendirmesi"):
        assert bad not in html, f"landing ölçülmemiş kesin sonuç vaat ediyor: {bad}"
