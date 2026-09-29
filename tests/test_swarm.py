import pytest
from unittest.mock import AsyncMock, patch
from answrank.agents.swarm import (
    SwarmOrchestrator,
    SwarmCandidate,
    SwarmStage,
    ScoutAgent,
    HunterAgent,
    FulfillmentAgent,
    SentryAgent,
)
from answrank.audit.crawler import CrawlData

def test_scout_qualification():
    scout = ScoutAgent()
    cand = SwarmCandidate(
        brand_name="Harley Street Dental",
        domain="harleystreetdental.co.uk",
        sector="dental",
        city="London",
        country="UK",
        currency="GBP",
        ticket_size=2500.0,
    )
    assert scout.qualify(cand) is True
    assert cand.stage == SwarmStage.QUALIFIED

def test_hunter_multilingual_pitches():
    hunter = HunterAgent()
    
    # UK Pitch
    uk_cand = SwarmCandidate(
        brand_name="Kensington Clinic",
        domain="kensingtonclinic.co.uk",
        city="London",
        country="UK",
        currency="GBP",
        deep_score=35.0,
        lost_revenue_monthly=5400.0,
    )
    uk_pitch = hunter.generate_pitch(uk_cand)
    assert "GBP 5,400" in uk_pitch
    assert "performance-gated" in uk_pitch.lower()

    # DE Pitch
    de_cand = SwarmCandidate(
        brand_name="Zahnklinik Berlin",
        domain="zahnklinikberlin.de",
        city="Berlin",
        country="DE",
        currency="EUR",
        deep_score=40.0,
        lost_revenue_monthly=6200.0,
    )
    de_pitch = hunter.generate_pitch(de_cand)
    assert "EUR" in de_pitch
    assert "Zahnimplantaten" in de_pitch

def test_fulfillment_and_contract():
    fulfillment = FulfillmentAgent()
    cand = SwarmCandidate(
        brand_name="Elite Aesthetic",
        domain="eliteaesthetic.com",
        city="İstanbul",
        country="TR",
        currency="TRY",
    )
    contract = fulfillment.generate_contract(cand)
    assert "MADDE 7" in contract
    assert cand.stage == SwarmStage.CONTRACT_ISSUED

    fixes = fulfillment.fulfill(cand)
    assert "robots.txt" in fixes
    assert "llms.txt" in fixes
    assert "schema.jsonld" in fixes
    assert cand.stage == SwarmStage.FULFILLED

@pytest.mark.anyio
async def test_sentry_retention_with_measured_score():
    sentry = SentryAgent()
    cand = SwarmCandidate(
        brand_name="Acıbadem Test",
        domain="acibademtest.com",
        deep_score=30.0,
    )
    # Explicit measured current score (e.g. from a live re-audit)
    eval_res = await sentry.evaluate_retention(cand, current_score=60)
    assert eval_res["is_guarantee_met"] is True
    assert eval_res["score_delta"] == 30
    assert cand.stage == SwarmStage.DELTA_CHECKED


@pytest.mark.anyio
async def test_sentry_no_fabrication_when_site_unreachable():
    """If the live re-audit fails, the agent must NOT fabricate a delta."""
    sentry = SentryAgent()
    cand = SwarmCandidate(
        brand_name="Ulaşılamaz Klinik",
        domain="unreachable-site.invalid",
        deep_score=30.0,
    )

    # Force the crawler fetch to raise (site down)
    async def failing_fetch(url):
        raise ConnectionError("site down")

    with patch.object(sentry.audit_engine.crawler, "fetch", side_effect=failing_fetch):
        eval_res = await sentry.evaluate_retention(cand)

    assert eval_res["is_guarantee_met"] is False
    assert eval_res["current_score"] is None
    assert "no delta fabricated" in eval_res["measurement_note"].lower()
    # Candidate stays in monitoring for manual review, not fake DELTA_CHECKED
    assert cand.stage == SwarmStage.ACTIVE_MONITORING


@pytest.mark.anyio
async def test_sentry_no_baseline_skips_delta():
    """Without a recorded baseline, no delta can be computed — no fabrication."""
    sentry = SentryAgent()
    cand = SwarmCandidate(
        brand_name="No Baseline Clinic",
        domain="nobaseline.com",
        deep_score=None,
    )
    eval_res = await sentry.evaluate_retention(cand)
    assert eval_res["current_score"] is None
    assert eval_res["is_guarantee_met"] is False
    assert cand.stage == SwarmStage.ACTIVE_MONITORING

@pytest.mark.anyio
async def test_full_swarm_pipeline_orchestration():
    orch = SwarmOrchestrator()
    cand = orch.seed_target(
        brand_name="London Dental Studio",
        domain="londondentalstudio.co.uk",
        sector="dental",
        city="London",
        country="UK",
        currency="GBP",
        ticket_size=3000.0,
    )

    dummy_html = "<html><head><title>London Dental</title></head><body><h1>Dental Implant London</h1></body></html>"
    mock_crawl = CrawlData(
        url="https://londondentalstudio.co.uk",
        domain="londondentalstudio.co.uk",
        html_content=dummy_html,
        status_code=200,
        headers={"content-type": "text/html"},
        robots_txt="User-agent: *\nAllow: /",
        is_https=True,
    )

    with patch.object(orch.auditor.engine.crawler, "fetch", new_callable=AsyncMock) as mock_fetch, \
         patch.object(orch.sentry.audit_engine.crawler, "fetch", new_callable=AsyncMock) as mock_sentry_fetch:
        # Sentry'nin KENDI AuditEngine'i/crawler'i vardır — yalnız auditor'unkini
        # patch'lemek canlı ağ çağrısı yapar (test ağa bağımlı ve flaky).
        mock_fetch.return_value = mock_crawl
        mock_sentry_fetch.return_value = mock_crawl
        res = await orch.run_full_pipeline_sync(cand)

        assert res.stage == SwarmStage.DELTA_CHECKED
        assert res.outreach_pitch is not None
        assert res.contract_text is not None
        assert res.fixes_generated is not None
        assert "robots.txt" in res.fixes_generated


def test_pipeline_halts_honestly_when_domain_unreachable():
    """Zero-Trust contract: a candidate whose domain cannot be crawled at the
    network level must halt at QUALIFIED with an explicit reason — the pipeline
    never fabricates a deep score, outreach numbers or an invoice from
    unverified evidence."""
    import asyncio
    from answrank.agents.swarm import SwarmOrchestrator

    orch = SwarmOrchestrator()
    cand = orch.seed_target(
        brand_name="Hayalet Klinik", domain="nonexistent-host-badguy.invalid",
        sector="dental", city="London", country="UK", currency="GBP", ticket_size=2500.0,
    )
    result = asyncio.run(orch.run_full_pipeline_sync(cand))
    assert "AUDIT_UNAVAILABLE" in result.last_action


def test_swarm_audit_halts_on_transport_exception():
    """Defense-in-depth (16 Eyl P0-1): an engine that RAISES instead of degrading
    must also halt the pipeline without fabricated data."""
    import asyncio
    import httpx
    from unittest.mock import AsyncMock, patch
    from answrank.agents.swarm import SwarmOrchestrator

    orch = SwarmOrchestrator()
    cand = orch.seed_target(brand_name="Bombalı", domain="boom.test",
                            sector="dental", city="İstanbul", country="TR",
                            currency="TRY", ticket_size=100.0)
    with patch.object(orch.auditor.engine, "audit_url_deep",
                      new=AsyncMock(side_effect=httpx.ConnectError("kabloyu kopardım"))):
        result = asyncio.run(orch.run_full_pipeline_sync(cand))
    assert "AUDIT_UNAVAILABLE" in result.last_action and "ConnectError" in result.last_action
    assert result.deep_score is None


def test_hunter_clause_matrix_all_languages():
    """Every (lang × audited/offer × loss/no_loss) clause path renders localized,
    measurement-gated copy — no language can smuggle an invented claim."""
    hunter = HunterAgent()
    for country, cur_token in (("TR", "₺"), ("UK", "GBP"), ("US", "$"), ("DE", "EUR"), ("UAE", "AED")):
        for score in (None, 42.0):
            for lost in (None, 5000.0):
                c = SwarmCandidate(brand_name="X Clinic", domain="x.example",
                                   country=country, currency=cur_token,
                                   deep_score=score, lost_revenue_monthly=lost,
                                   sector="dental")
                p = hunter.generate_pitch(c)
                assert "X Clinic" in p
                if score is None:
                    assert "free" in p.lower() or "ücretsiz" in p.lower() or "kostenlos" in p.lower()
                if lost is None:
                    assert "not quote" in p or "model girdisi henüz yok" in p or "keine Umsatzfiguren" in p
                else:
                    assert "5,000" in p
    # unknown country falls back to UK clause set
    c = SwarmCandidate(brand_name="Y Clinic", domain="y.example", country="FR",
                       deep_score=None, lost_revenue_monthly=None)
    assert "free 360°" in hunter.generate_pitch(c)
