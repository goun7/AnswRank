"""Question-bank integrity + honest-sector locks (v3.9 deep sweep).

The old get_sector_questions() silently fell back to DENTAL for any unknown
sector — an audit run with sector="general" measured implant questions. The
bank now covers all four supported sectors and rejects the unknown loudly.
"""
import re as _re

import pytest
from pydantic import ValidationError

from answrank.citations.questions import (
    SECTOR_QUESTIONS, QUESTION_COUNT, get_sector_questions,
)
from answrank.config import settings


def test_cli_sector_choices_equal_question_banks(capsys):
    """16 Eyl: CLI --sector choices ARE the supported-sector list (settings field
    was a dead duplicate). A typo sector must be rejected and the argparse error
    must enumerate exactly the sectors that have citation banks."""
    from unittest.mock import patch
    from answrank.cli import main
    with patch("sys.argv", ["answrank", "citations", "--sector", "veterinary"]):
        with pytest.raises(SystemExit):
            main()
    err = capsys.readouterr().err
    m = _re.search(r"invalid choice: 'veterinary' \(choose from ([^)]*)\)", err)
    assert m, err[-300:]
    listed = {tok.strip(" '\"") for tok in m.group(1).replace(",", " ").split()}
    assert listed == set(SECTOR_QUESTIONS)


def test_all_banks_are_question_count_strong():
    for sector, bank in SECTOR_QUESTIONS.items():
        assert len(bank) == QUESTION_COUNT, f"{sector} has {len(bank)} questions"
        assert [q["id"] for q in bank] == [str(i) for i in range(1, QUESTION_COUNT + 1)]
        cats = {q["cat"] for q in bank}
        assert cats == {"bilincli_arama", "karar_ani", "guven_uzmanlik", "sss_dogal_dil"}


def test_general_bank_interpolates_like_the_rest():
    qs = get_sector_questions("general", sehir="Ankara", ilce="Çankaya",
                              marka="Nöbetçi Teknokent", rakip="RakipOfis")
    assert len(qs) == QUESTION_COUNT
    joined = " ".join(q["question"] for q in qs)
    assert "Ankara" in joined and "Nöbetçi Teknokent" in joined and "RakipOfis" in joined
    assert "implant" not in joined.lower(), "general must not inherit dental wording"


def test_unknown_sector_raises_loudly_not_silently_dental():
    with pytest.raises(ValueError, match="Bilinmeyen sektör"):
        get_sector_questions("legal")


def test_api_rejects_unknown_sector_with_validation_not_500():
    from answrank.api.app import CitationRequest
    ok = CitationRequest(brand_name="X", domain="x.example", sector="general")
    assert ok.sector == "general"
    with pytest.raises(ValidationError):
        CitationRequest(brand_name="X", domain="x.example", sector="legal")


def test_user_facing_question_count_is_derived():
    """MCP tool description must carry QUESTION_COUNT, never a stale literal."""
    from answrank.mcp.server import AnswRankMCPServer
    desc = next(t["description"] for t in AnswRankMCPServer().get_tool_definitions()
                if t["name"] == "answrank_citations")
    assert desc.startswith(f"Runs {QUESTION_COUNT} sector questions")


def test_documented_api_route_count_is_locked():
    """Docs claim an endpoint count; lock the exact metric (documented APIRoute
    handlers == openapi paths) so README/MASTER can never drift again."""
    from answrank.api.app import app
    from fastapi.routing import APIRoute
    api_routes = [r for r in app.routes if isinstance(r, APIRoute)]
    paths = app.openapi()["paths"]
    assert len(api_routes) == 52 and len(paths) == 51  # E11: /api/payments/channels  # /api/monitors POST+GET paylaşımı (E1)
    job_paths = [p for p in paths if p.startswith("/api/jobs")]
    # v4.0 tour: + /api/miniprobe (public E3 funnel) — 38 sync + 5 jobs
    assert len(job_paths) == 5  # the documented background-job quintet
    assert "/api/citations/latest" in paths
    assert "/api/audits/{audit_id}" in paths
    assert "/api/miniprobe" in paths
    assert "/api/monitors" in paths and "/api/monitors/{monitor_id}/digest" in paths


def test_cli_rejects_unbanked_market_language(monkeypatch, capsys):
    """--lang was a dead knob; E4 banked TR+EN — any OTHER market language must
    still fail at argparse (no silent fall-back to Turkish measurement)."""
    import sys
    monkeypatch.setattr(sys, "argv", ["answrank", "citations", "X", "x.example", "--lang", "de"])
    from answrank.cli import main
    with pytest.raises(SystemExit):
        main()
    err = capsys.readouterr().err
    assert "invalid choice" in err


def test_en_banks_parity_and_interpolation():
    from answrank.citations.questions import (SECTOR_QUESTIONS_EN, get_sector_questions,
                                              QUESTION_COUNT)
    assert sorted(SECTOR_QUESTIONS_EN) == sorted(
        __import__("answrank.citations.questions", fromlist=["SECTOR_QUESTIONS"]).SECTOR_QUESTIONS)
    for sector, bank in SECTOR_QUESTIONS_EN.items():
        assert len(bank) == QUESTION_COUNT, sector
        assert {i["cat"] for i in bank} == {"bilincli_arama", "karar_ani", "guven_uzmanlik", "sss_dogal_dil"}
    qs = get_sector_questions("dental", lang="en", sehir="Dubai")
    assert len(qs) == QUESTION_COUNT
    assert "Dubai" in qs[0]["question"] and " diş" not in qs[0]["question"]
    # TR default şehri EN bankaya sızmaz:
    q_def = get_sector_questions("general", lang="en")
    assert "İstanbul" not in q_def[0]["question"]


def test_lang_reaches_result_and_no_silent_tr_for_unknown():
    from answrank.citations.questions import get_sector_questions
    with pytest.raises(ValueError) as e:
        get_sector_questions("dental", lang="fr")
    assert "Kayıtlı dil" in str(e.value)


def test_api_citations_lang_passthrough(tmp_path, monkeypatch):
    """POST /api/citations accepts lang=en and the stored run carries it."""
    from answrank.db import Database
    from answrank.citations.runner import MultiLLMCitationRunner
    db = Database(db_path=str(tmp_path / "l.db"))
    orig = MultiLLMCitationRunner.run_citations
    captured = {}
    async def spy(self, *a, **k):
        captured.update(k)
        return await orig(self, *a, **{**k, "live": False})
    monkeypatch.setattr(MultiLLMCitationRunner, "run_citations", spy)
    monkeypatch.setattr("answrank.api.app.db", db)
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    client = TestClient(app)
    r = client.post("/api/citations", json={"brand_name": "Klinika", "domain": "klinika.example",
                                            "sector": "dental", "city": "Dubai", "lang": "en",
                                            "simulate": True})
    assert r.status_code == 200
    assert captured.get("lang") == "en"
    bad = client.post("/api/citations", json={"brand_name": "K", "domain": "k.example",
                                              "lang": "de"})
    assert bad.status_code == 422


# ------------------------------------------------------------ E4b: ihracat para birimi bütünlüğü

def _uae_meta():
    from answrank.legal.contract_generator import ContractMetadata, ClientLegalDetails
    from answrank.economics import PricingTier
    client = ClientLegalDetails(
        client_name="Dubai Smile Center LLC", company_title="Dubai Smile Center LLC",
        tax_number="TRN-000", tax_office="DMCC", address="Dubai", authorized_person="J. Doe",
        email="j@dubaismile.example", phone="+971 50 000 0000", domain="dubaismile.example",
        sector="dental")
    return client, ContractMetadata(contract_number="SZ-UAE-001",
                                    service_tier=PricingTier.MONTHLY_RETAINER,
                                    monthly_fee_try=5500.0, start_date="2026-09-16")


def test_uae_contract_currency_not_labeled_as_try():
    """Swarm AED bedeli sözleşmede '₺' ve '%20 KDV' olarak render edilemez —
    hizmet ihracatı KDV'den istisnadır; para birimi etiketi bedelin birimiyle eşmek zorunda."""
    from answrank.legal.contract_generator import ContractGenerator
    client, meta = _uae_meta()
    meta.fee_currency = "AED"
    meta.is_export_service = True
    doc = ContractGenerator.generate_contract(client, meta)
    assert "AED" in doc.contract_text and "₺5,500" not in doc.contract_text
    assert "KDV (%0)" in doc.contract_text or "KDV istisnası" in doc.contract_text


def test_tr_contract_label_unchanged():
    from answrank.legal.contract_generator import ContractGenerator, ContractMetadata, ClientLegalDetails
    from answrank.economics import PricingTier
    c = ClientLegalDetails(client_name="x", company_title="x", tax_number="1", tax_office="o",
                           address="a", authorized_person="p", email="e@x", phone="1",
                           domain="x.example", sector="dental")
    doc = ContractGenerator.generate_contract(
        c, ContractMetadata(contract_number="S2", service_tier=PricingTier.MONTHLY_RETAINER,
                            monthly_fee_try=6000.0, start_date="2026-09-16"))
    assert "₺6,000" in doc.contract_text and "KDV (%20" in doc.contract_text


def test_all_fee_currencies_have_rates_no_silent_one():
    from answrank.config import settings
    from answrank.finance.tax_ledger import TaxLedger
    t = TaxLedger()
    missing = [c for c in settings.swarm_fee_by_currency if c not in t.rates]
    assert not missing, f"sessiz 1.0 dönüşüm tuzağı: {missing}"
    with pytest.raises(ValueError) as e:
        t.record_invoice(client_brand="x", country="UAE", currency="ZWL", amount=1.0)
    assert "uydur" in str(e.value).lower()  # İ.lower() tuzağı: parça kontrolü


def test_swarm_uae_end_to_end_fiscal_chain(tmp_path):
    """Pilot duman: UAE adayı → sözleşme AED + fatura EXPORT_SERVICE %0 KDV + muafiyet
    TRY karşılığı (kur çaprazı). Crawler patch'i mevcut UK kalıbıyla birebir aynı."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from answrank.agents.swarm import SwarmOrchestrator
    from answrank.audit.crawler import CrawlData
    from answrank.db import Database

    orch = SwarmOrchestrator(db=Database(db_path=str(tmp_path / "uae.db")))
    cand = orch.seed_target(brand_name="Dubai Smile Center", domain="dubaismile.example",
                            sector="dental", city="Dubai", country="UAE", currency="AED",
                            ticket_size=2500.0)
    crawl = CrawlData(url="https://dubaismile.example", domain="dubaismile.example",
                      html_content="<html><head><title>Dubai Smile</title></head><body>"
                                   "<h1>Implants Dubai</h1></body></html>",
                      status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /",
                      is_https=True)
    with patch.object(orch.auditor.engine.crawler, "fetch", new_callable=AsyncMock) as mf:
        mf.return_value = crawl
        res = asyncio.run(orch.run_full_pipeline_sync(cand))
    assert "AED" in res.contract_text and "₺5,500" not in res.contract_text
    assert res.fiscal_invoice_id
    rec = [r for r in orch.tax_ledger.records if r.invoice_id == res.fiscal_invoice_id][0]
    assert rec.regime.value == "EXPORT_SERVICE" and rec.vat_amount_try == 0.0
    # 11257 CBK (2026): indirim oranı config'ten gelir — %80'e sabitlenmiş
    # beklenti mevzuat değişince gizli bozulma yaratırdı (D-16.09-Z).
    assert rec.exempt_income_try == pytest.approx(res.fiscal_tax_exempt_try, rel=1e-6)
    assert rec.taxable_base_try == pytest.approx(
        rec.amount_try * (1.0 - settings.export_income_deduction_rate), rel=1e-6)


def test_sim_without_caller_competitors_injects_none():
    """Çağıran rakip listesi vermezse simülasyon kurgusal rakip enjekte etmez;
    'Rakip İşletme' yalnızca metin dolgusu olarak görünür, top_competitors'a
    ölçülmüş rakip olarak yazılmaz (yapay-zeka izi bırakmaz)."""
    import asyncio
    from answrank.citations.runner import MultiLLMCitationRunner
    res = asyncio.run(MultiLLMCitationRunner().run_citations(
        brand_name="Dubai Smile", domain="demo.example", sector="dental",
        city="Dubai", live=False, lang="en"))
    assert res.top_competitors == {}, "kurgusal varsayılan rakip üretilmemeli"
    # çağıran gerçek rakip verirse onlar kullanılır
    res2 = asyncio.run(MultiLLMCitationRunner().run_citations(
        brand_name="Demo", domain="demo.example", sector="dental",
        city="İstanbul", live=False, lang="tr",
        competitors=["gercek-rakip-1.example"]))
    assert "gercek-rakip-1.example" in res2.top_competitors
