"""Tests for CRMSync and OutreachGenerator."""

import asyncio
from answrank.crm.sync import CRMSync
from answrank.crm.outreach import OutreachGenerator
from answrank.audit.engine import AuditEngine
from answrank.audit.crawler import CrawlData

def test_crm_sync():
    crm = CRMSync(csv_path="takip_tablosu.csv")
    imported = asyncio.run(crm.import_csv_to_db())
    assert imported >= 1
    leads = asyncio.run(crm.list_prospects())
    assert len(leads) >= 1

def test_outreach_generator():
    engine = AuditEngine()
    outreach = OutreachGenerator()
    crawl = CrawlData(url="https://yilmazdental.com", domain="yilmazdental.com", html_content="<p>Test</p>", status_code=200, headers={})
    audit_res = engine.audit_crawl_data(crawl, sector="dental")

    variants = outreach.generate_all_variants(
        audit_res,
        contact_name="Dr. Ahmet",
        top_competitor="Hospitadent",
    )
    assert "variant_1_pain_numbers" in variants
    assert "variant_2_lost_revenue" in variants
    assert "variant_3_case_study" in variants
    assert "Dr. Ahmet" in variants["variant_1_pain_numbers"]
    # 16 Eyl derin-tarama kilidi: ölçülmemiş rakip istatistiği DM'e sızamaz
    assert "Hospitadent" not in variants["variant_1_pain_numbers"]
    assert "80 cevabın" not in variants["variant_1_pain_numbers"]
    assert "1.500 kişi" not in variants["variant_2_lost_revenue"]
    assert "%0'dan %38'e" not in variants["variant_3_case_study"]
    assert "sadece 2 kliniğe" not in variants["followup_day_3"]
    assert "45 dakikada" not in variants["variant_3_case_study"]
    for v in variants.values():
        assert "İstanbul" not in v or "bölgenizde" in v
    assert "followup_day_3" in variants
    assert "followup_day_7" in variants


def _cit(brand="Test", domain="t.example", total=100, found=30, rate=30.0,
         live=0, comps=None, full=None):
    from answrank.models import CitationRunResult, CitationQueryItem
    items = [CitationQueryItem(question="soru", question_id=1, model="ChatGPT-4o", brand_mentioned=bool(found),
                               domain_cited=False, answer_snippet="", was_simulated=(live == 0),
                               cited_rank=None, latency_ms=10)]
    return CitationRunResult(
        run_id="r1", brand_name=brand, domain=domain, sector="dental", city="Istanbul",
        items=items, total_runs=total, brand_citations_found=found,
        citation_rate_percentage=rate, live_items_count=live,
        live_response_rate_percentage=100.0 * live / total,
        is_fully_live=(live == total) if full is None else full,
        top_competitors=comps or {},
    )


def _audit_min():
    from answrank.audit.engine import AuditEngine
    from answrank.audit.crawler import CrawlData
    return AuditEngine().audit_crawl_data(CrawlData(
        url="https://t.example", domain="t.example", html_content="", status_code=200,
        headers={}), sector="dental")


def test_outreach_citation_branches_all_honest():
    o = OutreachGenerator()
    a = _audit_min()
    # fully live
    v = o.generate_all_variants(a, citation=_cit(live=100, comps={"rakip-a.example": 60}))
    assert "100/100 koşu canlı API ölçümü" in v["variant_1_pain_numbers"]
    assert "rakip-a.example" in v["variant_1_pain_numbers"]  # measured leader named
    # mixed live
    v2 = o.generate_all_variants(a, citation=_cit(live=40, comps={}))
    assert "40/100 koşu gerçek API" in v2["variant_1_pain_numbers"]
    # simulation-only
    v3 = o.generate_all_variants(a, citation=_cit(live=0))
    assert "simülasyon" in v3["variant_1_pain_numbers"]
    # v2/v3 variants react to citation presence
    assert "simülasyon karışıklı" in v2["variant_2_lost_revenue"]
    assert "henüz ölçülmedi" in v3["variant_2_lost_revenue"] or "simülasyon" in v2["variant_2_lost_revenue"]
    v4 = o.generate_all_variants(a)
    assert "ölçülmedi" in v4["variant_2_lost_revenue"]
    assert "model kestirimidir" in v4["variant_2_lost_revenue"] or "sağlam bir model girdisi" in v4["variant_2_lost_revenue"]
    assert "uydurma" in OutreachGenerator().generate_all_variants(a)["variant_3_case_study"] or \
           "Vaka rakamı uydurmuyoruz" in v4["variant_3_case_study"]


def test_outreach_findings_clause_uses_booleans():
    o = OutreachGenerator()
    clause = o._audit_findings_clause(_audit_min())
    assert isinstance(clause, str) and clause  # empty-html audit -> honest placeholder sentence
    # no fabricated numeric ratios (\d+/\d+) in a findings clause built from booleans
    import re
    assert not re.search(r"\d+/\d+", clause)


def test_outreach_findings_all_branches():
    o = OutreachGenerator()
    a = _audit_min()
    a.lost_revenue_estimate_monthly_try = None  # no model input -> honest no-number clause
    v = o.generate_all_variants(a)
    assert "boşuna bir rakam paylaşmıyoruz" in v["variant_2_lost_revenue"]
    # robots present but AI search closed
    a.categories.robots.exists = True
    a.categories.robots.ai_search_allowed = False
    assert "AI arama botlarına kapalı" in o._audit_findings_clause(a)
    # robots open but sitemap undeclared
    a.categories.robots.ai_search_allowed = True
    a.categories.robots.sitemap_declared = False
    assert "sitemap bildirimi eksik" in o._audit_findings_clause(a)
    # llms missing + warnings counted
    a.categories.llms_txt.has_llms_txt = False
    a.crawl_warnings = ["w1", "w2"]
    clause = o._audit_findings_clause(a)
    assert "llms.txt" in clause and "2 teknik uyarı" in clause


def test_outreach_v3_with_citation_present():
    o = OutreachGenerator()
    a = _audit_min()
    v = o.generate_all_variants(a, citation=_cit(live=100))
    assert "Alıntı testiniz de ölçüldü" in v["variant_3_case_study"]
    assert "çıta" in v["variant_3_case_study"]
