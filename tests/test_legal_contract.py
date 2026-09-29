"""Tests for Legal Agreement, Performance Guarantee (Madde 7) & Invoice Generator."""

from answrank.legal.contract_generator import (
    ContractGenerator,
    ClientLegalDetails,
    ContractMetadata,
)
from answrank.economics import PricingTier


def test_generate_madde_7_clause():
    clause = ContractGenerator.generate_madde_7_clause(target_score_delta=25, target_citation_delta_pct=30.0)
    assert "MADDE 7: PERFORMANS VE DELTA GÜVENCESİ PROTOKOLÜ" in clause
    assert "7.3. **Güvence İcrası (Deltasız Ay Ücretsiz Hizmet):**" in clause
    assert "+25" in clause
    assert "+%30.0" in clause


def test_generate_full_contract():
    client = ClientLegalDetails(
        client_name="Dr. Ali Yılmaz",
        company_title="Yılmaz Ağız ve Diş Sağlığı Polikliniği Ltd. Şti.",
        tax_number="9876543210",
        tax_office="Kadıköy",
        address="Bağdat Cad. No:123 Kadıköy / İstanbul",
        authorized_person="Dr. Ali Yılmaz",
        email="ali@yilmazdental.com",
        phone="+905320000000",
        domain="yilmazdental.com",
        sector="dental",
    )
    meta = ContractMetadata(
        contract_number="ANSW-2026-TEST",
        service_tier=PricingTier.MONTHLY_RETAINER,
        monthly_fee_try=6000.0,
        start_date="2026-09-14",
        duration_months=6,
    )
    res = ContractGenerator.generate_contract(client, meta)
    assert "ANSW-2026-TEST" in res.contract_text
    assert "Yılmaz Ağız ve Diş Sağlığı" in res.contract_text
    assert "MADDE 7" in res.contract_text
    assert res.invoice_metadata["net_amount_try"] == 6000.0
    assert res.invoice_metadata["vat_amount_try"] == 1200.0
    assert res.invoice_metadata["total_payable_try"] == 7200.0
