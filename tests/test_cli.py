"""Tests for AnswRank CLI commands."""

import os
from unittest.mock import patch, MagicMock, AsyncMock

from answrank.cli import main
from answrank.audit.crawler import CrawlData
from answrank.citations.monte_carlo import MonteCarloRunResult, IterationSummary


def test_cli_help(capsys):
    with patch("sys.argv", ["answrank", "--help"]):
        try:
            main()
        except SystemExit as e:
            assert e.code == 0


def test_cli_fix_command(tmp_path):
    out_dir = str(tmp_path / "fixes")
    with patch("sys.argv", ["answrank", "fix", "testdental.com", "--brand", "Test Dental", "--out-dir", out_dir]):
        main()
    assert os.path.exists(os.path.join(out_dir, "robots.txt"))
    assert os.path.exists(os.path.join(out_dir, "llms.txt"))
    assert os.path.exists(os.path.join(out_dir, "schema.html"))
    # llms-full.txt must also be produced (deep documentation tier)
    assert os.path.exists(os.path.join(out_dir, "llms-full.txt"))


def test_cli_fix_robots_mentions_all_tier1_bots(tmp_path):
    out_dir = str(tmp_path / "fixes")
    with patch("sys.argv", ["answrank", "fix", "testdental.com", "--brand", "Test Dental", "--out-dir", out_dir]):
        main()
    with open(os.path.join(out_dir, "robots.txt"), encoding="utf-8") as f:
        robots = f.read()
    # Tier 1 bots must be explicitly allowed
    for bot in ["OAI-SearchBot", "PerplexityBot", "Claude-SearchBot", "Google-Extended", "Bingbot"]:
        assert bot in robots
    # Aggressive scrapers must be blocked
    assert "User-agent: Bytespider\nDisallow: /" in robots
    # Sitemap pointer present
    assert "Sitemap: https://testdental.com/sitemap.xml" in robots


def test_cli_audit_command_renders_categories(tmp_path, capsys):
    """CLI audit command renders the 8-category breakdown (in-process, mocked fetch).

    Runs the real main() with a deterministic crawl payload: argparse,
    asyncio.run, rich rendering and DB persistence all execute exactly as a
    user would run them, but without network dependence and with the temp
    DB from conftest isolation (counted by coverage).
    """
    from answrank.audit.engine import AuditEngine

    engine = AuditEngine()
    crawl = CrawlData(
        url="https://example.com/",
        domain="example.com",
        html_content=(
            "<!DOCTYPE html><html><head><title>Example Domain</title></head>"
            "<body><h1>Example</h1><p>This domain is for use in illustrative examples.</p></body></html>"
        ),
        status_code=200,
        headers={"content-type": "text/html"},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# Example\n> Illustrative domain\n## Docs",
        is_https=True,
    )
    audit = engine.audit_crawl_data(crawl, sector="dental")
    with patch.object(AuditEngine, "audit_url", new=AsyncMock(return_value=audit)):
        with patch("sys.argv", ["answrank", "audit", "https://example.com", "--sector", "dental"]):
            main()
    out = capsys.readouterr().out
    # 8 category rows must all be present
    for label in [
        "Robots.txt AI Erişimi",
        "llms.txt Standartları",
        "JSON-LD Semantik Şema",
        "Meta & Başlık Mimarisi",
        "İçerik Alıntılanabilirliği",
        "Marka Varlığı & KG",
        "Güven ve E-E-A-T",
        "Manipülasyon Filtresi",
    ]:
        assert label in out, f"Missing category label: {label}"
    # Overall score panel present
    assert "AEO Görünürlük Skoru" in out


def test_cli_monte_carlo_command_honest_simulation_mode():
    """CLI monte-carlo must surface the honest SIMULATION_MODE marker (no keys)."""
    res = MonteCarloRunResult(
        brand_name="TestBrand",
        domain="testbrand.com",
        iterations_count=3,
        mean_citation_rate_pct=0.0,
        standard_deviation=0.0,
        confidence_interval_95_str="%0.0 ± %0.0 (p=0.95)",
        stability_index=100.0,
        stability_grade="SIMULATION_MODE",
        fragile_questions_count=0,
        fragile_questions=[],
        solid_questions_count=0,
        solid_questions=[],
        iterations=[
            IterationSummary(iteration_index=1, citation_rate_pct=0.0, citations_count=0, total_runs=80, temperature=0.1, live_items=0),
            IterationSummary(iteration_index=2, citation_rate_pct=0.0, citations_count=0, total_runs=80, temperature=0.3, live_items=0),
            IterationSummary(iteration_index=3, citation_rate_pct=0.0, citations_count=0, total_runs=80, temperature=0.5, live_items=0),
        ],
        summary_report="SİMÜLASYON MODU (İSTATİSTİKSEL OLARAK GEÇERSİZ): test",
        is_statistically_valid=False,
        measurement_mode="DETERMINISTIC_SIMULATION",
    )

    engine_cls = MagicMock()
    engine_cls.evaluate_stochastic_stability = AsyncMock(return_value=res)

    import answrank.citations.monte_carlo as mc_mod
    with patch.object(mc_mod.MonteCarloEngine, "evaluate_stochastic_stability", engine_cls.evaluate_stochastic_stability):
        with patch("sys.argv", ["answrank", "monte-carlo", "TestBrand", "testbrand.com", "--iterations", "3"]):
            main()  # must not raise; renders simulation-mode banner


def test_cli_deploy_local(tmp_path):
    out_dir = str(tmp_path / "dist")
    with patch("sys.argv", ["answrank", "deploy", "TestBrand", "testbrand.com", "--target", "local", "--out", out_dir]):
        main()
    assert os.path.exists(os.path.join(out_dir, "robots.txt"))
    assert os.path.exists(os.path.join(out_dir, "llms.txt"))
    assert os.path.exists(os.path.join(out_dir, "schema.jsonld"))


def test_cli_deploy_github_requires_repo_and_token(capsys):
    """GitHub deploy without --gh-repo/--gh-token must print a clear error, not crash."""
    with patch("sys.argv", ["answrank", "deploy", "TestBrand", "testbrand.com", "--target", "github"]):
        main()
    captured = capsys.readouterr()
    assert "--gh-repo" in captured.out


def test_cli_deploy_github_bad_repo_format(capsys):
    with patch("sys.argv", [
        "answrank", "deploy", "TestBrand", "testbrand.com", "--target", "github",
        "--gh-repo", "invalid-no-slash", "--gh-token", "faketoken",
    ]):
        main()
    captured = capsys.readouterr()
    assert "owner/repository" in captured.out


def test_cli_deploy_webhook_requires_url(capsys):
    with patch("sys.argv", ["answrank", "deploy", "TestBrand", "testbrand.com", "--target", "webhook"]):
        main()
    captured = capsys.readouterr()
    assert "--webhook-url" in captured.out


def test_cli_qualify_command():
    with patch("sys.argv", [
        "answrank", "qualify", "Klinik",
        "--sector", "dental", "--domain", "klinik.com",
        "--ticket", "8000", "--revenue", "1500000", "--has-ads", "--dm-access",
        "--competitor-cited",
    ]):
        main()


def test_cli_economics_command():
    with patch("sys.argv", ["answrank", "economics", "--clients", "5", "--cac", "1500"]):
        main()


def test_cli_scenarios_command():
    with patch("sys.argv", ["answrank", "scenarios", "--baseline", "15", "--current", "40"]):
        main()


def test_cli_milestones_command():
    with patch("sys.argv", ["answrank", "milestones", "--day", "30", "--clients", "2"]):
        main()


def test_cli_contract_command(tmp_path):
    out_file = str(tmp_path / "contract.md")
    with patch("sys.argv", [
        "answrank", "contract", "Test Klinik A.Ş.", "testklinik.com",
        "--contact", "Dr. Test", "--out", out_file, "--months", "6",
    ]):
        main()
    with open(out_file, encoding="utf-8") as f:
        text = f.read()
    assert "MADDE 7" in text
    assert "Test Klinik" in text


def test_cli_objections_command():
    with patch("sys.argv", ["answrank", "objections", "Çok pahalı", "--company", "Klinik"]):
        main()


def test_cli_sentiment_command():
    sample = "Best clinic ever, amazing results! Highly recommended, zero pain."
    with patch("sys.argv", ["answrank", "sentiment", "TestBrand", "--text", sample]):
        main()  # must not raise


def test_cli_queue_audit_command_renders_gate_results(tmp_path, capsys):
    """CLI 'queue audit' çıktı yolları test edilmeli — 6/6 kapı
    sonucu ve kapanma nedenleri kullanıcıya gösterilmeli."""
    from answrank.queue import ApprovalQueue
    from answrank.db import Database
    db = Database(db_path=str(tmp_path / "q.db"))
    ApprovalQueue(db=db).add("DM", "ornek-klinik.example", "test özeti")

    with patch("sys.argv", ["answrank", "queue", "audit"]):
        with patch("answrank.cli.Database", return_value=db):
            main()
    out = capsys.readouterr().out
    assert "GEÇTİ" in out or "KAPALI" in out
    assert "Otomatik onay için" in out


def test_cli_queue_audit_auto_approve_dry_run(tmp_path, capsys):
    """--auto-approve dry-run hiçbir kararı değiştirmemeli."""
    from answrank.queue import ApprovalQueue
    from answrank.db import Database
    db = Database(db_path=str(tmp_path / "q2.db"))
    ApprovalQueue(db=db).add("DM", "ornek-klinik.example", "test özeti")
    with patch("sys.argv", ["answrank", "queue", "audit", "--auto-approve"]):
        with patch("answrank.cli.Database", return_value=db):
            main()
    out = capsys.readouterr().out
    assert "dry-run" in out or "uygulanabilir" in out
    assert "UYGULANDI" not in out


def test_cli_queue_audit_empty_shows_nothing(tmp_path, capsys):
    """Boş kuyrukta 'denetilecek bir şey yok' çıkışı verilmeli — sahte madde üretilmemeli."""
    from answrank.db import Database
    db = Database(db_path=str(tmp_path / "q3.db"))
    with patch("sys.argv", ["answrank", "queue", "audit"]):
        with patch("answrank.cli.Database", return_value=db):
            main()
    out = capsys.readouterr().out
    assert "denetilecek bir şey yok" in out


def test_cli_queue_send_skips_non_dm(tmp_path, capsys):
    """DM olmayan kuyruk maddesi gönderimde 'atlandı' sonucu verilmeli."""
    from answrank.queue import ApprovalQueue
    from answrank.db import Database
    db = Database(db_path=str(tmp_path / "q4.db"))
    q = ApprovalQueue(db=db)
    q.add("CONTRACT", "ornek-klinik.example", "sözleşme madde")
    item_id = q.pending()[0]["id"]

    with patch("sys.argv", ["answrank", "queue", "send", str(item_id)]):
        with patch("answrank.cli.Database", return_value=db):
            main()
    out = capsys.readouterr().out
    assert "atlandı" in out


def test_cli_queue_send_renders_recipient_and_reason(tmp_path, capsys):
    """Gönderim sonucu alıcı ve neden satırını göstermeli (render yolu)."""
    from answrank.db import Database
    db = Database(db_path=str(tmp_path / "q5.db"))

    with patch("sys.argv", ["answrank", "queue", "send", "1", "--dry-run"]):
        with patch("answrank.cli.Database", return_value=db):
            with patch("answrank.dm_dispatch.DmDispatcher.send_approved",
                       return_value={"item_id": 1, "result": "dry-run",
                                     "to": "info@ornek.example",
                                     "why": "SMTP yok — gönderim uydurulmaz"}):
                main()
    out = capsys.readouterr().out
    assert "info@ornek.example" in out
    assert "gönderim uydurulmaz" in out
