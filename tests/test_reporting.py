"""Tests for report generator."""

from answrank.audit.engine import AuditEngine
from answrank.audit.crawler import CrawlData
from answrank.reporting.generator import ReportGenerator

def test_report_generator_markdown_and_html():
    engine = AuditEngine()
    crawl = CrawlData(
        url="https://yilmazdental.com/",
        domain="yilmazdental.com",
        html_content="<!DOCTYPE html><html><head><title>Test Dental</title></head><body><h1>Hizmetler</h1><p>Test</p></body></html>",
        status_code=200,
        headers={},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# Test\n> Desc\n## S1",
        is_https=True,
    )
    audit_res = engine.audit_crawl_data(crawl, sector="dental")
    gen = ReportGenerator()

    # Markdown test
    md = gen.to_markdown(audit_res)
    assert "# AI Görünürlük Denetimi" in md
    assert "yilmazdental.com" in md
    assert "Skor Kartı" in md

    # JSON test
    json_out = gen.to_json(audit_res)
    assert '"audit_id"' in json_out
    assert '"overall_score"' in json_out

    # HTML test
    html = gen.to_html(audit_res)
    assert "<!DOCTYPE html>" in html
    assert "yilmazdental.com" in html
    assert "AEO Görünürlük Skoru" in html
    assert "svg" in html.lower()

# --- to_html score-band branch coverage (4 bands) ---
from answrank.models import AuditResult

def _make_audit_with_score(score: float) -> AuditResult:
    engine = AuditEngine()
    crawl = CrawlData(
        url="https://yilmazdental.com/",
        domain="yilmazdental.com",
        html_content="<!DOCTYPE html><html><head><title>Test Dental</title></head><body><h1>Hizmetler</h1><p>Test</p></body></html>",
        status_code=200,
        headers={},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# Test\n> Desc\n## S1",
        is_https=True,
    )
    audit = engine.audit_crawl_data(crawl, sector="dental")
    audit.overall_score = score
    return audit

def test_html_score_band_critical():
    html = ReportGenerator().to_html(_make_audit_with_score(20))
    assert "#ef4444" in html
    assert "badge-critical" in html

def test_html_score_band_foundation():
    html = ReportGenerator().to_html(_make_audit_with_score(50))
    assert "#f59e0b" in html
    assert "badge-foundation" in html

def test_html_score_band_good():
    html = ReportGenerator().to_html(_make_audit_with_score(75))
    assert "#38bdf8" in html
    assert "badge-good" in html

def test_html_score_band_excellent():
    html = ReportGenerator().to_html(_make_audit_with_score(92))
    assert "#10b981" in html
    assert "badge-excellent" in html

def test_html_with_no_recommendations():
    audit = _make_audit_with_score(92)
    audit.recommendations = []
    html = ReportGenerator().to_html(audit)
    assert "Kritik düzeltme ihtiyacı tespit edilmedi" in html

def test_markdown_with_no_recommendations_and_no_revenue():
    audit = _make_audit_with_score(92)
    audit.recommendations = []
    audit.lost_revenue_estimate_monthly_try = 0
    md = ReportGenerator().to_markdown(audit)
    assert "Hesaplanmadı" in md
    assert "mükemmel AEO sinyalleri" in md


# ---------- Zero-Trust: HTML report escaping & unverified-asset section ----------

def _tainted_audit():
    from answrank.models import Recommendation
    engine = AuditEngine()
    crawl = CrawlData(
        url="https://hedef.example/tr",
        domain="hedef.example",
        html_content="<!DOCTYPE html><html><head><title>X</title></head><body><h1>Merhaba</h1>"
                     "<p>İçerik metni yeterince uzun olmalı ki analizciler patlamasın."
                     " İkinci bir cümle ile destek yoğunluğu artıyor ve sayfa RAG'e uygun."
                     " Üçüncü cümle: 2026 yılında implant başarı oranı %98 olarak ölçülmüştür.</p></body></html>",
        status_code=200, headers={},
        fetch_warnings=["<script>alert('warn')</script> robots.txt ağ hatası nedeniyle doğrulanamadı"],
    )
    res = engine.audit_crawl_data(crawl, sector='dental"><script>alert(1)</script>')
    res.recommendations.append(Recommendation(
        category="xss", priority="HIGH",
        title="<img src=x onerror=alert(2)>",
        action="<script>alert(3)</script>", impact_points=3,
    ))
    return res


def test_html_report_escapes_attacker_controlled_fields():
    res = _tainted_audit()
    html = ReportGenerator().to_html(res)
    for attack in ('<script>alert(1)</script>', '<script>alert(3)</script>',
                   '<img src=x onerror=alert(2)>', "<script>alert('warn')</script>"):
        assert attack not in html, f"raw injected markup reached HTML report: {attack}"
    assert "&lt;script&gt;" in html  # escaped representation present


def test_html_report_surfaces_unverified_assets_banner():
    res = _tainted_audit()
    html = ReportGenerator().to_html(res)
    assert "Doğrulanamayan Varlıklar" in html
    assert "YOK\" değil \"DOĞRULANAMADI" in html.replace("’", "'")


def test_markdown_report_has_unverified_section_only_when_present():
    res = _tainted_audit()
    md = ReportGenerator().to_markdown(res)
    assert "Doğrulanamayan Varlıklar" in md
    res2 = _tainted_audit()
    res2.crawl_warnings = []
    assert "Doğrulanamayan Varlıklar" not in ReportGenerator().to_markdown(res2)


# ---------- B: Citation-Share (SoV dil-köprüsü) ----------

def _citation_fixture(brand="Meridyen Diş", domain="meridyen-klinik.example"):
    from answrank.models import CitationRunResult, CitationQueryItem
    items = [
        CitationQueryItem(question_id=1, question="q1", model="ChatGPT-4o",
                          brand_mentioned=True, was_simulated=False),
        CitationQueryItem(question_id=1, question="q1", model="Perplexity-Sonar",
                          brand_mentioned=False, was_simulated=True),
        CitationQueryItem(question_id=2, question="q2", model="ChatGPT-4o",
                          brand_mentioned=False, was_simulated=False),
        CitationQueryItem(question_id=2, question="q2", model="Perplexity-Sonar",
                          brand_mentioned=True, was_simulated=True),
    ]
    return CitationRunResult(
        run_id="run_b1", brand_name=brand, domain=domain, sector="dental", city="İstanbul",
        total_runs=4, brand_citations_found=2, citation_rate_percentage=50.0,
        live_items_count=2, live_response_rate_percentage=50.0, is_fully_live=False,
        items=items,
    )


def test_citation_share_summary_derives_per_model():
    gen = ReportGenerator()
    s = gen.citation_share_summary(_citation_fixture())
    assert s["per_model"]["ChatGPT-4o"] == {"total": 2, "cited": 1, "live": 2}
    assert s["per_model"]["Perplexity-Sonar"] == {"total": 2, "cited": 1, "live": 0}
    assert s["sim_items"] == 2 and s["live_items"] == 2


def test_markdown_report_includes_share_and_simulation_caveat():
    md = ReportGenerator().to_markdown(_tainted_audit(), citation=_citation_fixture())
    assert "Alıntı Payı" in md and "%50" in md and "2/4" in md
    assert "SİMÜLASYON" in md.upper() and "korpus-kayıtlı" in md


def test_markdown_report_without_citation_says_not_measured():
    md = ReportGenerator().to_markdown(_tainted_audit())
    assert "ölçülmedi" in md and "uydurulmaz" in md


def test_html_report_share_escapes_brand():
    evil = _citation_fixture(brand='X"><script>alert(9)</script>')
    html_out = ReportGenerator().to_html(_tainted_audit(), citation=evil)
    assert "alert(9)" in html_out  # text visible...
    assert "<script>alert(9)</script>" not in html_out  # ...never executable
    assert "Alıntı Payı" in html_out


def test_html_report_share_card_shows_live_split():
    html_out = ReportGenerator().to_html(_tainted_audit(), citation=_citation_fixture())
    assert "2/4 CANLİ API" in html_out and "SİMÜLASYON" in html_out
