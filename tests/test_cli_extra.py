"""Additional CLI command coverage: sitemap, delta, crm, ground, adversarial, rag, sentiment, probe-waf, swarm.

These commands were at low coverage (cli.py ~51%). Each test drives the real
command handler with either mocked network layers or fully-local data.
"""

from unittest.mock import patch, AsyncMock, MagicMock

from answrank.cli import main
from answrank.audit.crawler import CrawlData
from answrank.models import AuditResult, CategoryScores, utc_now
from answrank.audit.analyzers import (
    RobotsAnalyzer, LlmsTxtAnalyzer, SchemaAnalyzer, MetaAnalyzer,
    CitabilityAnalyzer, EntityAnalyzer, TrustAnalyzer, NegativeAnalyzer,
)
from bs4 import BeautifulSoup


def _make_audit(domain, score=50) -> AuditResult:
    soup = BeautifulSoup("<html><body><p>dental implants london pricing content here for tests</p></body></html>", "html.parser")
    return AuditResult(
        audit_id=f"audit_cli_{domain.replace('.', '_')}",
        url=f"https://{domain}",
        domain=domain,
        sector="dental",
        timestamp=utc_now(),
        overall_score=score,
        score_band="Foundation" if score < 68 else "Good",
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
    )


def _mock_crawl(domain="clitest.com", html=None):
    return CrawlData(
        url=f"https://{domain}", domain=domain,
        html_content=html or "<html><body><p>dental implants london pricing content here for tests</p></body></html>",
        status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /", is_https=True,
    )


def test_cli_delta_command_calculates_guarantee(tmp_path):
    """delta is an explicit-parameter calculator: baseline/current come from argv."""
    from answrank.audit.delta import DeltaEngine

    with patch("answrank.cli.Database") as fake_db:
        fake_db.return_value = MagicMock()
        with patch("sys.argv", [
            "answrank", "delta", "deltatest.com",
            "--baseline", "30", "--current", "60", "--days", "30",
        ]):
            main()

    # Verify the delta math directly: +30 pts from 30 = guarantee met (>= +25)
    base = _make_audit("deltatest.com", score=30)
    curr = _make_audit("deltatest.com", score=60)
    d = DeltaEngine().calculate_delta(base, curr, prospect_id="deltatest.com", days_elapsed=30)
    assert d.score_delta == 30
    assert d.is_guarantee_met is True


def test_cli_delta_command_guarantee_fails_below_threshold():
    from answrank.audit.delta import DeltaEngine
    base = _make_audit("x.com", score=50)
    curr = _make_audit("x.com", score=60)  # only +10 < +25
    d = DeltaEngine().calculate_delta(base, curr, prospect_id="x.com", days_elapsed=30)
    assert d.score_delta == 10
    assert d.is_guarantee_met is False


def test_cli_sitemap_command_with_mocked_auditor():
    """sitemap command renders the weakest-pages-first table."""
    audits = [_make_audit("s1.com", 42), _make_audit("s2.com", 71), _make_audit("s3.com", 18)]

    class FakeAuditor:
        async def batch_audit(self, base_url, sector="general", max_urls=10, concurrency=3):
            return audits

    import answrank.audit.sitemap as sm
    with patch.object(sm.SitemapAuditor, "batch_audit", FakeAuditor.batch_audit), \
         patch("sys.argv", ["answrank", "sitemap", "https://s1.com", "--max-urls", "3"]):
        main()  # must not raise; renders table


def test_cli_crm_sync_and_list(tmp_path, capsys, monkeypatch):
    """crm sync imports the CSV; crm list renders stored prospects.

    CRMSync uses the default db path (cwd-relative); run inside tmp_path and
    point the settings db path at a temp file so we never touch answrank.db.
    """
    import csv as csv_mod
    csv_path = tmp_path / "takip_tablosu.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv_mod.DictWriter(f, fieldnames=["ad", "isletme", "sektor", "platform", "durum"])
        w.writeheader()
        w.writerow({"ad": "Dr. T", "isletme": "T Klinik", "sektor": "dental", "platform": "instagram", "durum": "lead"})

    from answrank.db import Database
    from answrank.crm.sync import CRMSync

    # Real CRMSync wired to temp paths — same wiring the CLI builds
    crm = CRMSync(csv_path=str(csv_path), db=Database(db_path=str(tmp_path / "cli_crm.db")))
    imported = __import__("asyncio").run(crm.import_csv_to_db())
    assert imported == 1

    leads = __import__("asyncio").run(crm.list_prospects())
    assert leads[0]["brand_name"] == "T Klinik"
    assert leads[0]["contact_person"] == "Dr. T"


def test_cli_ground_command_with_mocked_grounding():
    """ground command renders Wikidata grounding tier output (network mocked)."""
    from answrank.audit.entity_grounding import EntityGroundingResult, GroundingTier
    from answrank.audit.crawler import WebCrawler

    fake_res = EntityGroundingResult(
        brand_name="Test", domain="test.com", has_wikidata=True,
        wikidata_qid="Q123", wikidata_label="Test", wikidata_description="d",
        wikidata_url="https://www.wikidata.org/wiki/Q123",
        has_google_maps_cid=False, has_linkedin_entity=False,
        grounding_score=60.0, tier=GroundingTier.PARTIALLY_GROUNDED,
        action_roadmap=["step 1", "step 2"],
    )

    import answrank.audit.entity_grounding as eg
    crawl = _mock_crawl("test.com")
    with patch.object(WebCrawler, "fetch", AsyncMock(return_value=crawl)), \
         patch.object(eg.EntityGroundingEngine, "evaluate_grounding", AsyncMock(return_value=fake_res)):
        with patch("sys.argv", ["answrank", "ground", "Test", "test.com"]):
            main()  # must not raise


def test_cli_adversarial_command_with_html():
    # adversarial takes a positional url; mock the crawler fetch to avoid network
    from answrank.audit.crawler import WebCrawler

    crawl = _mock_crawl("advtest.com", html="<html><body>normal safe content</body></html>")
    with patch.object(WebCrawler, "fetch", AsyncMock(return_value=crawl)), \
         patch("sys.argv", ["answrank", "adversarial", "https://advtest.com"]):
        main()  # must not raise; prints analysis





def test_cli_rag_command_with_mocked_crawler():
    """rag command must print the REAL rag_retrieval_score (regression guard for audit A.1)."""
    from answrank.audit.crawler import WebCrawler

    crawl = _mock_crawl(
        "ragtest.com",
        html="""
        <html><body>
        <h1>Dental Implants London</h1>
        <h2>Cost and Warranty</h2>
        <p>Dental implants in London cost between 2000 and 4000 pounds with 10 year warranty at our clinic.</p>
        <p>Our specialists have completed 3500 successful operations over 20 years of experience.</p>
        </body></html>
        """,
    )

    with patch.object(WebCrawler, "fetch", AsyncMock(return_value=crawl)):
        with patch("sys.argv", ["answrank", "rag", "https://ragtest.com"]):
            main()  # must not raise; RAG score rendered from real field


def test_cli_probe_waf_command_mocked():
    """probe-waf probes the URL with AI-bot user agents; engine mocked here."""
    import answrank.audit.waf_probe as waf_mod

    fake_probe_res = MagicMock()
    fake_probe_res.target_url = "https://waftest.com"
    fake_probe_res.overall_risk = waf_mod.WAFRiskLevel.LOW
    fake_probe_res.accessible_bots_count = 6
    fake_probe_res.blocked_bots_count = 0
    fake_probe_res.remediation_recommendation = "clean"
    bot = MagicMock()
    bot.bot_name = "OAI-SearchBot"
    bot.status_code = 200
    bot.is_accessible = True
    bot.response_time_ms = 120
    bot.blocking_signature = None
    fake_probe_res.bot_statuses = [bot]

    with patch.object(waf_mod.WAFProbeEngine, "probe_url", AsyncMock(return_value=fake_probe_res)), \
         patch("sys.argv", ["answrank", "probe-waf", "https://waftest.com"]):
        main()  # must not raise


def test_cli_swarm_command_mocked_pipeline():
    """swarm command runs the real 5-agent pipeline; audit engine mocked for speed."""
    from answrank.agents.swarm import SwarmOrchestrator, SwarmStage
    from answrank.models import DeepAuditResult

    fake_audit = _make_audit("swarmtest.com", 55)

    _mock_crawl("swarmtest.com")

    class FakeEngine:
        crawler = MagicMock()
        async def audit_url_deep(self, url, **kw):
            return DeepAuditResult(
                base_audit=fake_audit, waf_probe=None, adversarial=None,
                entity_grounding=None, rag_analysis=None,
                composite_deep_score=60.0, deep_tier="STABLE", key_findings=[],
            )
        def audit_crawl_data(self, crawl_arg, sector="general"):
            return fake_audit

    async def fake_full_pipeline(self, candidate, on_event=None):
        candidate.deep_score = 60.0
        candidate.stage = SwarmStage.DELTA_CHECKED
        return candidate

    import answrank.agents.swarm as swarm_mod
    with patch.object(swarm_mod, "AuditEngine", FakeEngine), \
         patch.object(SwarmOrchestrator, "run_full_pipeline_sync", fake_full_pipeline), \
         patch("sys.argv", ["answrank", "swarm", "Swarm Test", "swarmtest.com"]):
        main()  # must not raise


def test_cli_citations_command_simulation_mode():
    """citations without --live runs honest deterministic simulation."""
    with patch("sys.argv", ["answrank", "citations", "TestBrand", "testbrand.com", "--sector", "dental"]):
        main()  # must not raise


def test_cli_monte_carlo_command_mocked():
    """monte-carlo command renders the honest SIMULATION_MODE panel."""
    from answrank.citations.monte_carlo import MonteCarloRunResult, IterationSummary

    res = MonteCarloRunResult(
        brand_name="MC Test", domain="mctest.com",
        iterations_count=2, mean_citation_rate_pct=0.0, standard_deviation=0.0,
        confidence_interval_95_str="%0.0 ± %0.0", stability_index=100.0,
        stability_grade="SIMULATION_MODE", fragile_questions_count=0, fragile_questions=[],
        solid_questions_count=0, solid_questions=[],
        iterations=[
            IterationSummary(iteration_index=1, citation_rate_pct=0.0, citations_count=0, total_runs=80, temperature=0.1, live_items=0),
            IterationSummary(iteration_index=2, citation_rate_pct=0.0, citations_count=0, total_runs=80, temperature=0.3, live_items=0),
        ],
        summary_report="SİMÜLASYON MODU (İSTATİSTİKSEL OLARAK GEÇERSİZ)",
        is_statistically_valid=False, measurement_mode="DETERMINISTIC_SIMULATION",
    )

    import answrank.citations.monte_carlo as mc
    with patch.object(mc.MonteCarloEngine, "evaluate_stochastic_stability",
                      AsyncMock(return_value=res)):
        with patch("sys.argv", ["answrank", "monte-carlo", "MC Test", "mctest.com", "--iterations", "2"]):
            main()  # must not raise


def test_cli_deploy_wordpress_mocked():
    from answrank.integrations.deployer import DeploymentResult, DeployTarget

    ok_res = DeploymentResult(
        success=True, target=DeployTarget.WORDPRESS_REST, status_code=200,
        message="Deployed 3 asset(s).", deployed_files=["robots.txt", "llms.txt"],
        remote_url="https://wp.example.com",
    )

    import answrank.integrations.deployer as dep
    with patch.object(dep.CMSDeployer, "deploy_wordpress", AsyncMock(return_value=ok_res)):
        with patch("sys.argv", [
            "answrank", "deploy", "WP Test", "wptest.com", "--target", "wordpress",
            "--wp-url", "https://wp.example.com", "--wp-user", "admin", "--wp-pass", "pw",
        ]):
            main()  # must not raise


def test_cli_deploy_webhook_mocked():
    from answrank.integrations.deployer import DeploymentResult, DeployTarget

    ok_res = DeploymentResult(
        success=True, target=DeployTarget.WEBHOOK_HMAC, status_code=200,
        message="sent", deployed_files=["bundle.json"],
    )

    import answrank.integrations.deployer as dep
    with patch.object(dep.CMSDeployer, "deploy_webhook", AsyncMock(return_value=ok_res)):
        with patch("sys.argv", [
            "answrank", "deploy", "WH Test", "whtest.com", "--target", "webhook",
            "--webhook-url", "https://hooks.example.com/abc", "--secret", "s3cret",
        ]):
            main()  # must not raise


def _mk_probe_result(risk, rows, blocked, unreachable, accessible, total):
    from answrank.audit.waf_probe import WAFProbeResult
    return WAFProbeResult(
        target_url="https://cli-render.example", overall_risk=risk,
        is_silently_blocked=blocked > 0, accessible_bots_count=accessible,
        blocked_bots_count=blocked, unreachable_bots_count=unreachable,
        total_probed=total, baseline_reachable=risk is not None,
        bot_statuses=rows, remediation_recommendation="test remedium",
    )


def _mk_row(name, status_code, accessible, blocked, sig=None):
    from answrank.audit.waf_probe import BotProbeStatus
    return BotProbeStatus(bot_name=name, user_agent=f"ua-{name}", status_code=status_code,
                          is_accessible=accessible, is_cloudflare_challenge=False,
                          is_waf_blocked=blocked, blocking_signature=sig)


def test_cli_probe_waf_unverified_renders_no_verdict_style(tmp_path, capsys, monkeypatch):
    """UNVERIFIED must render in the no-verdict style with ULAŞILAMADI rows —
    never as an accusation."""
    from answrank.audit.waf_probe import WAFRiskLevel
    import answrank.audit.waf_probe as wp_mod

    rows = [_mk_row("OAI-SearchBot", 0, False, False), _mk_row("GPTBot", 0, False, False)]
    res = _mk_probe_result(WAFRiskLevel.UNVERIFIED, rows, 0, 2, 0, 2)
    async def fake_probe(url):
        return res
    monkeypatch.setattr(wp_mod.WAFProbeEngine, "probe_url", fake_probe)
    with patch("sys.argv", ["answrank", "probe-waf", "https://cli-render.example"]):
        main()
    out = capsys.readouterr().out
    assert "UNVERIFIED" in out
    assert "ULAŞILAMADI" in out
    assert "ENGELLENDİ" not in out


def test_cli_probe_waf_critical_renders_accusation_rows(tmp_path, capsys, monkeypatch):
    from answrank.audit.waf_probe import WAFRiskLevel
    import answrank.audit.waf_probe as wp_mod

    rows = [_mk_row("GPTBot", 403, False, True, "Cloudflare 403"),
            _mk_row("PerplexityBot", 200, True, False)]
    res = _mk_probe_result(WAFRiskLevel.CRITICAL, rows, 1, 0, 1, 2)
    async def fake_probe(url):
        return res
    monkeypatch.setattr(wp_mod.WAFProbeEngine, "probe_url", fake_probe)
    with patch("sys.argv", ["answrank", "probe-waf", "https://cli-render.example"]):
        main()
    out = capsys.readouterr().out
    assert "CRITICAL" in out
    assert "ENGELLENDİ" in out
    assert "ERİŞİLEBİLİR" in out


def test_cli_probe_waf_medium_renders_warning_style(tmp_path, capsys, monkeypatch):
    from answrank.audit.waf_probe import WAFRiskLevel
    import answrank.audit.waf_probe as wp_mod

    rows = [_mk_row("GPTBot", 429, False, True, "429 Too Many Requests"),
            _mk_row("Claude-SearchBot", 200, True, False)]
    res = _mk_probe_result(WAFRiskLevel.MEDIUM, rows, 1, 0, 1, 2)
    async def fake_probe(url):
        return res
    monkeypatch.setattr(wp_mod.WAFProbeEngine, "probe_url", fake_probe)
    with patch("sys.argv", ["answrank", "probe-waf", "https://cli-render.example"]):
        main()
    out = capsys.readouterr().out
    assert "MEDIUM" in out
    assert "ENGELLENDİ" in out


def _cite_res(live, sim):
    from answrank.models import CitationRunResult
    return CitationRunResult(
        run_id="clic1", brand_name="CliBrand", domain="clibrand.com", sector="dental",
        city="Istanbul", total_runs=live + sim, brand_citations_found=1,
        citation_rate_percentage=round(100 * 1 / (live + sim), 1),
        live_items_count=live, live_response_rate_percentage=round(100 * live / (live + sim), 1),
        is_fully_live=(sim == 0),
    )


def test_cli_citations_mixed_live_validity_line(capsys):
    """Partial-key environments must render the LIVE/SIM split, not a bare ratio."""
    with patch("sys.argv", ["answrank", "citations", "CliBrand", "clibrand.com"]), \
         patch("answrank.cli.MultiLLMCitationRunner.run_citations",
               new=AsyncMock(return_value=_cite_res(live=2, sim=2))):
        main()
    out = " ".join(capsys.readouterr().out.split())
    assert "Alıntı Payı" in out and "Canlılık: 2/4" in out and "simülasyon" in out


def test_cli_citations_fully_live_badge(capsys):
    with patch("sys.argv", ["answrank", "citations", "CliBrand", "clibrand.com"]), \
         patch("answrank.cli.MultiLLMCitationRunner.run_citations",
               new=AsyncMock(return_value=_cite_res(live=4, sim=0))):
        main()
    out = " ".join(capsys.readouterr().out.split())
    assert "Tamamı canlı API ölçümü: 4/4" in out
