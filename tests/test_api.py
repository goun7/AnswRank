"""Tests for FastAPI endpoints."""

from fastapi.testclient import TestClient
from answrank.citations.runner import MODELS as _M
from answrank.api.app import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "answrank", "version": "1.0.0"}

def test_generate_fixes_api():
    res = client.post("/api/fix", json={
        "domain": "testdental.com",
        "brand_name": "Test Dental",
        "sector": "dental",
        "city": "İstanbul"
    })
    assert res.status_code == 200
    data = res.json()
    assert "robots_txt" in data
    assert "llms_txt" in data
    assert "json_ld" in data
    assert "OAI-SearchBot" in data["robots_txt"]
    assert "Test Dental" in data["llms_txt"]

def test_citations_api():
    res = client.post("/api/citations", json={
        "brand_name": "Test Dental",
        "domain": "testdental.com",
        "sector": "dental",
        "city": "İstanbul"
    })
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert "citation_rate_percentage" in data
    assert data["total_runs"] == 20 * len(_M)

def test_qualify_api():
    res = client.post("/api/qualify", json={
        "company_name": "API Dental",
        "sector": "dental",
        "domain": "apidental.com",
        "has_custom_domain": True,
        "estimated_ticket_size": 6000.0,
        "estimated_annual_revenue": 2000000.0,
        "has_ad_spend": True,
        "direct_decision_maker_access": True,
        "ai_missing_in_top5": True,
        "has_competitor_cited": True,
    })
    assert res.status_code == 200
    assert res.json()["is_qualified"] is True
    assert res.json()["score"] == 5

def test_objections_api():
    res = client.post("/api/objections", json={
        "objection_text": "Fiyatınız çok yüksek geldi",
        "company_name": "API Dental",
    })
    assert res.status_code == 200
    assert res.json()["matched_code"] == "PRICE_OR_GUARANTEE"

def test_contract_api():
    res = client.post("/api/contract", json={
        "client": {
            "client_name": "Dr. Veli",
            "company_title": "Veli Klinik A.Ş.",
            "tax_number": "1122334455",
            "tax_office": "Kadıköy",
            "address": "Kadıköy / İstanbul",
            "authorized_person": "Dr. Veli",
            "email": "veli@klinik.com",
            "phone": "+905550001122",
            "domain": "veliklinik.com",
            "sector": "dental",
        },
        "meta": {
            "contract_number": "ANSW-API-001",
            "service_tier": "MONTHLY_RETAINER",
            "monthly_fee_try": 6000.0,
            "start_date": "2026-09-14",
        }
    })
    assert res.status_code == 200
    assert "contract_text" in res.json()
    assert "MADDE 7" in res.json()["madde_7_guarantee_text"]

def test_economics_api():
    res = client.get("/api/economics?tier=MONTHLY_RETAINER&clients=10")
    assert res.status_code == 200
    data = res.json()
    assert "packages" in data
    assert data["portfolio_projection"]["mrr_try"] == 60000.0

def test_scenarios_api():
    res = client.post("/api/scenarios", json={
        "baseline_score": 40.0,
        "current_score": 75.0,
        "baseline_citations": 0,
        "current_citations": 5,
    })
    assert res.status_code == 200
    assert res.json()["scenario"] == "S1_SUCCESS"

def test_milestones_api():
    res = client.get("/api/milestones?current_day=14&active_clients=3&current_mrr=18000")
    assert res.status_code == 200
    assert res.json()["current_phase"] == 1

def test_waf_probe_api(monkeypatch):
    async def mock_get(*args, **kwargs):
        class MockResp:
            status_code = 200
            text = "<html><body>OK</body></html>"
            headers = {}
        return MockResp()
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = client.post("/api/waf-probe", json={"url": "https://example.com"})
    assert res.status_code == 200
    assert res.json()["overall_risk"] == "LOW"
    from answrank.audit.waf_probe import WAFProbeEngine
    assert res.json()["accessible_bots_count"] == len(WAFProbeEngine.AI_CRAWLER_USER_AGENTS)

def test_rag_score_api():
    html = "<html><body><h1>İmplant ve Diş Tedavisi</h1><p>İstanbul garantili implant ve gülüş tasarımı.</p></body></html>"
    res = client.post("/api/rag-score", json={
        "url": "https://example.com",
        "html_content": html,
        "sector": "dental",
        "city": "İstanbul"
    })
    assert res.status_code == 200
    data = res.json()
    assert "rag_retrieval_score" in data
    assert len(data["matches"]) > 0

def test_monte_carlo_api():
    res = client.post("/api/citations/monte-carlo", json={
        "brand_name": "TestDental",
        "domain": "testdental.com",
        "iterations": 2
    })
    assert res.status_code == 200
    assert res.json()["iterations_count"] == 2
    assert "stability_grade" in res.json()

def test_multilingual_questions_api():
    res = client.get("/api/questions/multilingual?sector=dental&language=en&city=Istanbul")
    assert res.status_code == 200
    assert res.json()["count"] == 20
    assert "Turkey" in res.json()["questions"][0]

def test_entity_ground_api(monkeypatch):
    from answrank.audit.entity_grounding import EntityGroundingEngine
    async def mock_wiki(*args, **kwargs):
        return {"qid": "Q999", "label": "Test", "description": "Desc", "url": "https://wikidata.org/wiki/Q999", "status": "found"}
    async def mock_p856(*args, **kwargs):
        return {"status": "ok", "urls": ["https://testdental.com/"]}
    monkeypatch.setattr(EntityGroundingEngine, "probe_wikidata", mock_wiki)
    monkeypatch.setattr(EntityGroundingEngine, "probe_official_websites", mock_p856)

    res = client.post("/api/entity-ground", json={
        "brand_name": "Test Dental",
        "domain": "testdental.com",
        "html_content": "<html><body><script type='application/ld+json'>{\"@type\": \"Dentist\"}</script></body></html>"
    })
    assert res.status_code == 200
    assert res.json()["has_wikidata"] is True

def test_adversarial_api():
    html_clean = "<html><body><h1>Temiz Klinik</h1><p>Sağlıklı dişler için buradayız.</p></body></html>"
    res = client.post("/api/audit/adversarial", json={"html_content": html_clean})
    assert res.status_code == 200
    assert res.json()["is_clean"] is True
    assert res.json()["threat_level"] == "CLEAN"

def test_deep_audit_api(monkeypatch):
    from answrank.audit.crawler import CrawlData
    async def mock_fetch(*args, **kwargs):
        return CrawlData(
            url="https://testdental.com",
            domain="testdental.com",
            html_content="<html><head><title>Test</title></head><body><h1>Klinik</h1></body></html>",
            status_code=200,
            headers={"content-type": "text/html"},
            robots_txt="User-agent: *\nAllow: /",
            is_https=True,
        )
    from answrank.audit.crawler import WebCrawler
    # Patch at CLASS level: monkeypatch on an instance permanently pins the
    # originally-resolved bound method into the instance __dict__ on undo,
    # shadowing every later class-level patch of engine.crawler.fetch.
    monkeypatch.setattr(WebCrawler, "fetch", mock_fetch)

    res = client.post("/api/audit/deep", json={
        "url": "https://testdental.com",
        "sector": "dental",
        "probe_waf": False,
        "check_grounding": False,
    })
    assert res.status_code == 200
    data = res.json()
    assert "composite_deep_score" in data
    assert "deep_tier" in data
    assert "base_audit" in data

def test_landing_page_api():
    res = client.get("/")
    assert res.status_code == 200
    assert "AnswRank" in res.text
    assert "Autonomous Swarm" in res.text

def test_swarm_api(monkeypatch):
    from answrank.audit.crawler import CrawlData
    async def mock_fetch(*args, **kwargs):
        return CrawlData(
            url="https://testdental.co.uk",
            domain="testdental.co.uk",
            html_content="<html><head><title>UK Dental</title></head><body><h1>Dental Implant</h1></body></html>",
            status_code=200,
            headers={"content-type": "text/html"},
            robots_txt="User-agent: *\nAllow: /",
            is_https=True,
        )
    from answrank.audit.engine import WebCrawler
    monkeypatch.setattr(WebCrawler, "fetch", mock_fetch)

    res = client.post("/api/swarm/run", json={
        "brand_name": "London Dental",
        "domain": "testdental.co.uk",
        "sector": "dental",
        "city": "London",
        "country": "UK",
        "currency": "GBP",
        "ticket_size": 2500.0,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["brand_name"] == "London Dental"
    assert data["country"] == "UK"
    assert data["currency"] == "GBP"
    assert data["outreach_pitch"] is not None
    assert "GBP" in data["outreach_pitch"]

def test_sentiment_api():
    res = client.post("/api/sentiment", json={
        "brand_name": "Smile Clinic",
        "raw_text": "Smile Clinic is top recommended and trusted in London.",
        "sector": "dental",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["polarity"] == "POSITIVE_RECOMMENDATION"
    assert data["is_brand_safe"] is True

def test_deploy_local_api(tmp_path):
    res = client.post("/api/deploy", json={
        "brand_name": "Smile Clinic",
        "domain": "smileclinic.co.uk",
        "target": "local",
        "output_dir": str(tmp_path),
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["target"] == "LOCAL_EXPORT"

def test_telemetry_api():
    res = client.get("/api/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert "total_live_calls" in data

def test_fiscal_report_api():
    res = client.get("/api/fiscal-report")
    assert res.status_code == 200
    data = res.json()
    assert "total_gross_revenue_try" in data
    assert "effective_tax_shield_pct" in data
    # Frontend↔backend contract: the dashboard table binds to `records` and reads
    # these per-invoice keys. If any disappears, the fiscal table silently empties.
    for key in ("records", "fx_source", "fx_rates", "persist_error"):
        assert key in data
    assert isinstance(data["records"], list)
    assert data["fx_source"] in ("static_default", "custom", "env", "explicit")
    for ccy in ("GBP", "USD", "EUR", "TRY"):
        assert ccy in data["fx_rates"]


def test_fiscal_report_records_keys_match_dashboard(tmp_path, monkeypatch):
    """An issued invoice must surface in the API with the exact field names the
    dashboard renders (was previously absent because records were in-memory only)."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "api-fiscal.db"))
    from answrank.finance.tax_ledger import TaxLedger
    TaxLedger(custom_rates={"GBP": 46.0}).record_invoice("Contracted Clinic", "UK", "GBP", 1000.0)

    data = client.get("/api/fiscal-report").json()
    assert data["total_invoices_count"] >= 1
    match = [r for r in data["records"] if r["client_brand"] == "Contracted Clinic"]
    assert match, "persisted invoice missing from fiscal-report records"
    rec = match[0]
    for key in ("invoice_id", "client_brand", "client_country", "currency",
                "amount_foreign", "exchange_rate_tcmb", "fx_source", "amount_try",
                "exempt_income_try", "vat_rate_pct"):
        assert key in rec, f"dashboard binds {key!r} but API omitted it"
    assert rec["amount_try"] == 46000.0

def test_territory_locks_api():
    res = client.get("/api/territory-locks")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_swarm_stream_api():
    res = client.get("/api/swarm/stream?brand=LondonDental&domain=londondental.co.uk")
    assert res.status_code == 200
    assert "data:" in res.text
    assert "AGENT_01_SCOUT" in res.text

def test_territory_locks_check_api():
    res = client.post("/api/territory-locks/check", json={
        "city": "London",
        "niche": "dental",
        "country": "UK",
        "domain": "newdental.co.uk",
    })
    assert res.status_code == 200
    data = res.json()
    assert "locked" in data
    assert "city" in data

def test_artifacts_preview_api():
    res = client.post("/api/artifacts/preview", json={
        "brand_name": "Test Clinic",
        "domain": "testclinic.com",
        "sector": "dental",
        "city": "London",
    })
    assert res.status_code == 200
    data = res.json()
    assert "robots_txt" in data
    assert "llms_txt" in data
    assert "schema_jsonld" in data

def test_inquiry_api():
    res = client.post("/api/inquiry", json={
        "brand_name": "Inquiry Dental",
        "domain": "inquirydental.com",
        "sector": "dental",
        "city": "London",
        "country": "UK",
        "email_or_phone": "ceo@inquirydental.com",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "reservation_code" in data
    assert data["reservation_code"].startswith("ANSW-LK-")






def test_validation_errors_reply_in_turkish():
    """Pydantic 422 İngilizce mesaj döndürmemeli — kullanıcı yüzeyi Türkçe."""
    res = client.post("/api/miniprobe", json={"domain": "ab"})
    assert res.status_code == 422
    detail = str(res.json())
    for eng in ("String should have at least 3 characters",
                "string_too_short"):
        assert eng not in detail, f"İngilizce doğrulama mesajı sızdı: {eng}"
    assert "en az 3 karakter" in detail.lower() or "3 karakter" in detail.lower()


def test_miniprobe_form_supports_enter_key():
    """UX: mini-probe formu Enter tuşuyla gönderilebilir olmalı — input
    bir <form> içinde ve submit handler runMiniProbe'a bağlı."""
    html = open("answrank/api/templates/landing.html", encoding="utf-8").read()
    assert 'id="mp-form"' in html, "mini-probe bir form içinde değil"
    assert "onsubmit=\"event.preventDefault(); runMiniProbe();\"" in html
    # buton form içinde submit olmalı
    import re
    form = re.search(r'<form id="mp-form"[\s\S]*?</form>', html)
    assert form and 'type="submit"' in form.group(0)
    # kurgusal rakip ve İngilizce makine mesajı kalıntısı yok
    assert "Rakip Örnek A" not in html
    assert "rakip-ornek-a.example" not in html
    assert "competitor-sample-a" not in html


def test_landing_has_accessibility_basics():
    """Kullanıcı gözünden: ekran okuyucu içeriğe atlayabilmeli, dil ve başlık
    tanımlı olmalı, butonlar açık tipli olmalı."""
    html = client.get("/").text
    assert '<html lang="tr"' in html
    assert "İçeriğe geç" in html, "skip-link eksik"
    assert 'id="main-content"' in html
    assert 'href="#main-content"' in html
    import re
    assert not [m.group(0) for m in re.finditer(r"<button[^>]*>", html) if "type=" not in m.group(0)]


def test_no_unproven_percent_claims_in_illustrative_samples():
    """EN/DE i18n bloklarında kanıtsız '%100' veya 'sıfır maliyet' vaadi
    kalmamalı — TR sürümdeki gibi temsilî örnek olarak nitelendirilmeli."""
    html = client.get("/").text
    import re
    # tüm comp_body_after metinlerini topla (i18n JSON + statik div)
    for m in re.finditer(r"comp_body_after:\s*(\".*?\")\s*,", html, re.S):
        blob = m.group(1)
        assert "100% direct" not in blob, "kanıtsız %100 kazanım vaadi"
        assert "zero cost-per-click" not in blob, "kanıtsız sıfır maliyet vaadi"
    assert "illustrative sample" in html or "not a guaranteed outcome" in html


def test_dashboard_discloses_simulation_mode():
    """Dashboard'ta 0 canlı koşum sarı renkle gösteriliyorsa nedeni de
    belirtilmeli — kullanıcı 'simülasyon modu' bilgisinden mahrum bırakılmamalı."""
    html = open("answrank/api/templates/dashboard.html", encoding="utf-8").read()
    assert "simülasyon modu — API anahtarı yok" in html


def test_lead_inquiry_defaults_to_tr_locale():
    """Lead kayıt formu TR ürününde varsayılan olarak Türkiye ile kaydetmeli;
    'London'/'UK' varsayılanı müşteriyi yanlış pazara yazdırırdı. Swarm EN
    ihracat senaryosu bilinçli olarak London/UK kullanır (ayrı test)."""
    r = client.post("/api/inquiry", json={
        "brand_name": "Örnek Klinik", "domain": "ornek-klinik.example",
        "email_or_phone": "ornek@example.com"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("country") == "TR", "lead varsayılan ülke TR olmalı"


def test_api_error_messages_are_turkish():
    """Kullanıcıya dönen HTTP hata mesajları Türkçe olmalı; İngilizce makine
    mesajı dil kalitesi sözleşmesini ihlal eder."""
    cases = [
        (404, "Denetim raporu bulunamadı"),
        (404, "İş bulunamadı"),
        (400, "Url veya html_content sağlanmalı."),
        (404, "Aday bulunamadı"),
    ]
    src = open("answrank/api/app.py", encoding="utf-8").read()
    for _code, msg in cases:
        assert f'detail="{msg}"' in src, f"mesaj eksik: {msg}"
    # İngilizce kalıntı yok
    for eng in ("not found", "must be provided", "is required for"):
        assert eng not in src, f"İngilizce hata mesajı kalmış: {eng}"
