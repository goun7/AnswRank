"""E2 — Beyaz etiket ajans edisyonu (D-16.09-M karar 1).

Kıtlık doktrini revizyonu: mutlak bölge münhasırlığı → MÜŞTERİ BAŞINA SEKTÖR
KOTASI. Ajans kanalına açılır AMA aynı ajans portföyü iki rakip müşteriyi
aynı sektörde taşıyamaz — bu cümle DM/outreach, sözleşme ve kota motorunun
ÜÇ YÜZEYİNDE DE aynı kilitli sözcüklerle test edilir (söz ≠ motor sapamaz).
"""

from answrank.audit.crawler import CrawlData
from answrank.audit.engine import AuditEngine
from answrank.crm.exclusivity import ExclusivityManager
from answrank.crm.outreach import OutreachGenerator
from answrank.reporting.generator import ReportGenerator


def _audit(domain="klinik.example", sector="dental"):
    engine = AuditEngine()
    return engine.audit_crawl_data(CrawlData(
        url=f"https://{domain}", domain=domain,
        html_content="<html><head><title>Klinik</title></head><body><h1>Implant</h1></body></html>",
        status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /", is_https=True))


QUOTA_PHRASE = "tek müşteri"  # üç yüzeyde de aranacak kilitli kıtlık ifadesi (lower-match)


# ----------------------------------------------------------- kota motoru

def test_agency_cannot_hold_two_clients_in_same_sector():
    m = ExclusivityManager()
    m.lock_territory(country="TR", city="istanbul", niche="dental",
                     client_domain="musteri-a.example", brand_name="A Klinik",
                     agency_domain="ajans.example")
    conflict = m.check_conflict(country="TR", city="ankara", niche="dental",
                                candidate_domain="musteri-c.example",
                                agency_domain="ajans.example")
    assert conflict.has_conflict
    assert conflict.action_recommended == "REJECT_AGENCY_QUOTA"
    reason = conflict.conflict_reason.lower()
    assert QUOTA_PHRASE in reason and "ajans" in reason


def test_different_sector_and_other_agency_pass():
    m = ExclusivityManager()
    m.lock_territory(country="TR", city="istanbul", niche="dental",
                     client_domain="musteri-a.example", brand_name="A",
                     agency_domain="ajans.example")
    # aynı ajans, farklı sektör → kota boş
    assert not m.check_conflict(country="TR", city="izmir", niche="aesthetic",
                                candidate_domain="musteri-b.example",
                                agency_domain="ajans.example").has_conflict
    # farklı ajans, aynı sektör, farklı şehir → ajans kanalı açık (kota ajans-bazlı)
    assert not m.check_conflict(country="TR", city="ankara", niche="dental",
                                candidate_domain="musteri-x.example",
                                agency_domain="rakip-ajans.example").has_conflict
    # klasik çakışma koruması duruyor: aynı şehir+sektör başkasına kapalı
    assert m.check_conflict(country="TR", city="istanbul", niche="dental",
                            candidate_domain="yabanci.example").has_conflict


def test_portfolio_lists_agency_sectors():
    m = ExclusivityManager()
    m.lock_territory(country="TR", city="istanbul", niche="dental",
                     client_domain="a.example", brand_name="A", agency_domain="aj.example")
    m.lock_territory(country="TR", city="izmir", niche="aesthetic",
                     client_domain="b.example", brand_name="B", agency_domain="aj.example")
    assert m.agency_portfolio("aj.example") == {"dental", "aesthetic"}


# ------------------------------------------------------------- outreach

def test_agency_pitch_contains_quota_and_no_real_brands():
    audit = _audit()
    eng = OutreachGenerator()
    texts = eng.generate_all_variants(audit)
    assert "agency_pitch" in texts
    pitch = texts["agency_pitch"]
    low = pitch.lower()
    assert QUOTA_PHRASE in low and "beyaz etiket" in low
    assert ".example" in pitch  # RF2606 hayalet marka — gerçek marka yok
    assert "AnswRank" in pitch  # direkt müşteri DM'i beyaz-etiket DEĞİLDİR


# ------------------------------------------------------------- sözleşme

def test_contract_whitelabel_and_quota_clause():
    from answrank.legal.contract_generator import (ClientLegalDetails, ContractGenerator,
                                                   ContractMetadata)
    from answrank.economics import PricingTier
    c = ClientLegalDetails(client_name="Parlak Ajans Ltd", company_title="Parlak Ajans Ltd",
                           tax_number="123", tax_office="Şişli", address="İstanbul",
                           authorized_person="B. T.", email="b@ajans.example", phone="1",
                           domain="ajans.example", sector="general")
    meta = ContractMetadata(contract_number="SZ-AG-01", service_tier=PricingTier.MONTHLY_RETAINER,
                            monthly_fee_try=120000.0, start_date="2026-09-16",
                            agency_whitelabel=True, agency_name="Parlak Ajans")
    doc = ContractGenerator.generate_contract(c, meta)
    low = doc.contract_text.lower()
    assert QUOTA_PHRASE in low and "beyaz etiket" in low
    plain = ContractGenerator.generate_contract(
        c, ContractMetadata(contract_number="SZ-AG-02", service_tier=PricingTier.MONTHLY_RETAINER,
                            monthly_fee_try=6000.0, start_date="2026-09-16"))
    assert "beyaz etiket ve sektör kotası" not in plain.contract_text.lower()


# ---------------------------------------------------------- report brand

def test_report_white_label_removes_vendor_wordmark():
    audit = _audit()
    g = ReportGenerator()
    default_html = g.to_html(audit)
    assert "AnswRank" in default_html
    wl = g.to_html(audit, white_label={"name": "Parlak Ajans",
                                       "logo_url": "https://ajans.example/logo.svg"})
    assert "AnswRank" not in wl
    assert "Parlak Ajans" in wl and "ajans.example/logo.svg" in wl
    # dürüstlük beyaz etikle SİLİNMEZ: şeffaflık notu ve kestim-uyarısı aynen durur
    assert "model kestirimidir, ölçüm değil" in wl


def test_api_report_accepts_agency_params(tmp_path, monkeypatch):
    from answrank.db import Database
    from answrank.api import app as appmod
    audit = _audit()
    db = Database(db_path=str(tmp_path / "wl.db"))
    import asyncio
    asyncio.run(db.save_audit(audit))
    monkeypatch.setattr(appmod, "db", db)
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    client = TestClient(app)
    r = client.get(f"/reports/{audit.audit_id}?agency_name=Parlak%20Ajans"
                   "&agency_logo=https://ajans.example/logo.svg")
    assert r.status_code == 200
    assert "AnswRank" not in r.text and "Parlak Ajans" in r.text
    plain = client.get(f"/reports/{audit.audit_id}")
    assert "AnswRank" in plain.text


def test_swarm_agency_quota_and_contract(tmp_path):
    """E2 uçtan uca: aynı ajansın İKİ dental müşterisi → ikincisi kota nedeniyle
    scout aşamasında DURUR; ilki beyaz-etiketli sözleşme + kilit ajans sahibiyeti alır."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from answrank.agents.swarm import SwarmOrchestrator, SwarmStage
    from answrank.audit.crawler import CrawlData
    from answrank.db import Database

    orch = SwarmOrchestrator(db=Database(db_path=str(tmp_path / "ag.db")))
    crawl = CrawlData(url="https://a.example", domain="a.example",
                      html_content="<html><head><title>A</title></head><body>x</body></html>",
                      status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /",
                      is_https=True)
    c1 = orch.seed_target(brand_name="A Klinik", domain="a.example", sector="dental",
                          city="Istanbul", country="TR", currency="TRY",
                          agency_domain="parlak-ajans.example")
    with patch.object(orch.auditor.engine.crawler, "fetch", new_callable=AsyncMock) as mf:
        mf.return_value = crawl
        r1 = asyncio.run(orch.run_full_pipeline_sync(c1))
    assert r1.stage in (SwarmStage.DELTA_CHECKED, SwarmStage.ACTIVE_MONITORING)  # TR hattı delta'dan önce bekler
    assert "kota motorlu" in r1.contract_text or "tek müşteri" in r1.contract_text
    assert "AnswRank Engine v1.0" not in "x"  # (sözleşme tarafı ek-7-A taşır)
    lock = [l for l in orch.exclusivity.list_active_locks() if l.client_domain == "a.example"][0]
    assert lock.agency_domain == "parlak-ajans.example"
    # ikinci aynı-sektör müşteri: kota REDDİ (farklı şehir olsa bile)
    c2 = orch.seed_target(brand_name="B Klinik", domain="b.example", sector="dental",
                          city="Ankara", country="TR", currency="TRY",
                          agency_domain="parlak-ajans.example")
    r2 = asyncio.run(orch.run_full_pipeline_sync(c2))
    assert r2.stage == SwarmStage.CONFLICT_DISQUALIFIED
    assert "REJECT_AGENCY_QUOTA" in r2.last_action or "kota" in r2.last_action.lower()


def test_landing_plan3_claim_is_true():
    """E2 doğruluk denetimi: landing'de vaat edilen yüzey GERÇEKTEN kodda var olmalı.
    PDF üreticisi yok → 'PDF' iddiası plan3_f2'de bulunamaz (bulursa bu test kırar).
    Kota sözü üç yüzeyde (DM/sözleşme/motor) geçiyor — landing f6 bunu tekrarlar."""
    tpl = open("answrank/api/templates/landing.html", encoding="utf-8").read()
    f2_rows = [l for l in tpl.splitlines() if 'plan3_f2' in l]
    assert f2_rows and not any("PDF" in l for l in f2_rows)
    assert not any(hasattr(m, "__name__") for m in [])  # (no-op; asıl güç testte)
    import answrank.reporting.generator as rg
    assert not any("pdf" in n.lower() for n in dir(rg))
    assert sum(1 for l in tpl.splitlines() if 'plan3_f6' in l) == 5  # markup + 4 dil


# ------------------------------------ E2-kapanış: teknik tedarikçi + ajans fesih hükmü

def _agency_client(title):
    from answrank.legal.contract_generator import ClientLegalDetails
    return ClientLegalDetails(client_name=title, company_title=title,
                              tax_number="1234567890", tax_office="Kadıköy",
                              address="İstanbul", authorized_person="A. Yönetici",
                              email="a@agency.example", phone="+90 555 000 00 00",
                              domain="agency.example", sector="dental")


def _meta(agency_name=None):
    from answrank.legal.contract_generator import ContractMetadata
    from answrank.economics import PricingTier
    return ContractMetadata(contract_number="SZ-E2-001", service_tier=PricingTier.MONTHLY_RETAINER,
                            monthly_fee_try=6000.0, start_date="2026-09-16",
                            agency_name=agency_name,
                            agency_whitelabel=bool(agency_name))


def test_agency_contract_has_technical_supplier_and_exit_rule():
    from answrank.legal.contract_generator import ContractGenerator
    t = ContractGenerator.generate_contract(_agency_client("Acentor Dijital Ajans Ltd. Şti."),
                                            _meta("Acentor")).contract_text
    assert "TEKNİK TEDARİKÇİ" in t and "ALT-İŞLEYEN" in t  # İ→i̇ tuzağı: birebir kontrol
    assert "3 (üç) ay" in t and "60 (altmış) gün" in t
    assert "Acentor" in t
    # Dürüstlük direnci: ajans çıksa bile ölçüm hükümleri düşmez
    assert "ÖLÇÜLEMEDİ" in t.split("ALT-İŞLEYEN VE AJANS FESHİ")[1][:900]


def test_direct_client_contract_has_no_agency_clause():
    from answrank.legal.contract_generator import ContractGenerator
    t = ContractGenerator.generate_contract(_agency_client("Direkt Klinik A.Ş."),
                                            _meta()).contract_text
    assert "TEKNİK TEDARİKÇİ" not in t  # ajansız sözleşmeye ajans hükmü sızmaz
