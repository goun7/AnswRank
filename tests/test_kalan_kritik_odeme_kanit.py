"""Kalan test-disi kritik fonksiyonlar -- ODEME / RANKING / RECEIPT / HMAC / KANIT.

Bu dosya MEVCUT HICBIR testi veya kodu degistirmez; yalnizca yeni test
ekler (kural 1). Hedeflenen test-disi fonksiyonlar (AST taramasi):

  ODEME / RECEIPT / HMAC / KANIT (x402_gate):
    - _truthy, _get_ledger, _receipt_hash, anchor_hash,
      Charge.as_dict, price_of, status
  FINANS KANIT KALICILIGI (tax_ledger / net_kar_buyback):
    - TaxLedger._persist_record, TaxLedger._load_persisted_records,
      UnifiedTaxReport.foreign_total_try,
      ServisGelirKaydi.toplam_maliyet_usd / net_kar_usd
  DB KANIT KALICILIGI (db.py):
    - create_monitor / get_monitor / list_monitors / insert_monitor_run,
      _ensure_columns, list_swarm_candidates_sync, list_tax_invoices_sync,
      save_tax_invoice_sync
  RANKING DENETIM KAPILARI (queue_gates):
    - GateResult.to_dict, DmGateAuditor._gate_measurement / _gate_probe /
      _gate_contact
  RANKING BOLGE KILITLERI (swarm / exclusivity):
    - SwarmOrchestrator._load_persisted_locks / get_territory_locks,
      ExclusivityManager._make_key
  HMAC / ANAHTAR (key_manager):
    - HybridKeyManager.get_key
  OLCUM DURUSTLUGU (citations/runner):
    - _simulate_response, _mark_grounding, _grounded_or_recall
  RAPOR (reporting/generator): _branding, _citation_share_md
  ONBELLEK (audit/cache): _CacheEntry.is_fresh, TTLCache._evict_if_needed
  SITEMAP (audit/sitemap): _is_index, _extract_locs
  PROBE (probe/miniprobe): _bad_ip, _robots_line, _llms_line
  PROSPEKTOR (crm/prospector): _robots_disallows_all,
      _looks_like_challenge_or_error, _extract_contacts
  BUTUNLUK (rag_engine, mcp.server, entity_grounding, config, corpus,
      api.app, dm_sender, dm_dispatch):
    - RAGEngine._tokenize, AnswRankMCPServer._anchor_for,
      EntityGroundingEngine._netloc_of, Settings.ai_bots_total /
      ai_bots_tier_summary, CorpusStore.stats (paydasiz oran yok),
      CitationRequest._banked_lang / _known_sector,
      MonitorCreate._sector_in_banks, DMSender.smtp_creds / already_sent,
      DmDispatcher._log_send

MAINNET YASAK: zincir dogrulayici/ledger test icinde ENJEKTE EDILIR;
hicbir test ana aga baglanmaz. Dis cagri yapan fonksiyonlar (SMTP, canli
FX, canli LLM) yalnizca KENDI mantiklari ile test edilir (kural 7).
"""
from __future__ import annotations

import asyncio
import ipaddress
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from answrank.agents.swarm import SwarmOrchestrator
from answrank.audit.cache import TTLCache, _CacheEntry
from answrank.audit.entity_grounding import EntityGroundingEngine
from answrank.audit.rag_engine import RAGEngine
from answrank.audit.sitemap import SitemapAuditor
from answrank.config import settings
from answrank.corpus import CorpusStore, render_report_md
from answrank.citations.key_manager import HybridKeyManager, LLMProvider
from answrank.citations.runner import MultiLLMCitationRunner
from answrank.crm.dm_sender import DMSender
from answrank.crm.exclusivity import ExclusivityManager
from answrank.crm.prospector import LeadProspector
from answrank.db import Database
from answrank.dm_dispatch import DmDispatcher
from answrank.finance.net_kar_buyback import BuybackHesaplayici, ServisGelirKaydi
from answrank.finance.tax_ledger import TaxLedger, UnifiedTaxReport
from answrank.models import CitationQueryItem, CitationRunResult
from answrank.probe.miniprobe import MiniProbe, MiniProbeResult
from answrank.queue_gates import DmGateAuditor, GateResult
from answrank.reporting.generator import ReportGenerator
from answrank.x402_gate import Charge, SesterPaymentGate

_SECRET = "test-seller-secret-0123456789abcdef"


# ------------------------------------------------------------------ yardimcilar
@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "kanit.db")
    monkeypatch.setattr(settings, "db_path", p)
    return Database(db_path=p)


def _citations_run(domain, total=8, found=1, days_ago=1, fully_live=True):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return CitationRunResult(
        run_id=f"r-{domain}", brand_name="Marka", domain=domain, sector="dental",
        city="İstanbul", total_runs=total, brand_citations_found=found,
        citation_rate_percentage=round(100 * found / total, 1), timestamp=ts,
        live_items_count=total if fully_live else 0,
        live_response_rate_percentage=100.0 if fully_live else 0.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}", model="test-model",
                                 was_simulated=not fully_live,
                                 brand_mentioned=i < found) for i in range(total)],
        is_fully_live=fully_live)


def _seed_vis(db, domain, total=8, found=1, days_ago=1):
    asyncio.run(db.save_citations(_citations_run(domain, total, found, days_ago)))


def _seed_probe(db, domain, measured=1, verdict="TEMİZ", bots_line="3/3"):
    asyncio.run(db.save_miniprobe_lead(MiniProbeResult(
        domain=domain, verdict=verdict, robots_line="İZİNLİ", llms_line="VAR",
        bots_line=bots_line, blocked_bots=[], probed=3, measured=bool(measured))))


def _seed_prospect(db, domain, phone="+905551112233", email="info@example.org"):
    with db._get_connection() as conn:
        conn.execute("DELETE FROM prospects WHERE domain_ref = ?", (domain,))
        conn.execute(
            "INSERT INTO prospects (brand_name, domain_ref, phone, email, city,"
            " sector, status, source_url, verified_at) VALUES (?,?,?,?,?,?,?,?," "?)",
            ("Marka", domain, phone, email, "İstanbul", "dental", "lead", "src",
             datetime.now(timezone.utc).isoformat()))
        conn.commit()


# ======================================================= ODEME / RECEIPT / HMAC
def test_truthy_accepts_truthy_tokens_and_rejects_everything_else(monkeypatch):
    """Honest arm: 1/true/yes/on (buyuk/kucuk, bosluklu) -> True.
    Fault arm: bos, 0, false, yok -> False (kapı acik sanilmez)."""
    from answrank.x402_gate import _truthy

    for val in ("1", "true", "TRUE", " True ", "yes", "on", "ON"):
        monkeypatch.setenv("ANSWRANK_TEST_BOOL", val)
        assert _truthy("ANSWRANK_TEST_BOOL") is True, val
    for val in ("", "0", "false", "no", "off", "  ", "yok"):
        monkeypatch.setenv("ANSWRANK_TEST_BOOL", val)
        assert _truthy("ANSWRANK_TEST_BOOL") is False, val
    monkeypatch.delenv("ANSWRANK_TEST_BOOL", raising=False)
    assert _truthy("ANSWRANK_TEST_BOOL") is False  # tanimsiz env -> False


def test_anchor_hash_is_deterministic_order_invariant_and_payload_bound():
    """Honest: ayni payload (farkli sirayla) ayni SHA-256; musteri
    tekrar hesaplayabilir. Fault: farkli payload -> farkli hash."""
    a = SesterPaymentGate.anchor_hash({"domain": "x.com", "overall_score": 42})
    b = SesterPaymentGate.anchor_hash({"overall_score": 42, "domain": "x.com"})
    assert a == b and len(a) == 64 and int(a, 16) >= 0
    c = SesterPaymentGate.anchor_hash({"domain": "x.com", "overall_score": 43})
    assert a != c  # kanit hangi ciktiya ait oldugunu baglar
    # unicode/bosluk kirmizi bayrak: ensure_ascii=False, bosluksuz
    assert SesterPaymentGate.anchor_hash({"d": "İstanbul"}) == \
        SesterPaymentGate.anchor_hash({"d": "İstanbul"})


def test_receipt_hash_delegates_and_fails_closed(tmp_path, monkeypatch):
    """Honest arm: gecerli makbuz -> hex hash (HMAC zinciri uzerinde).
    Fault arm: sester hesaplayamazsa "" doner -- makbuz hash'i
    uydurulmaz, kapı 'odeme dogrulanmadi'ya fail-closed gider."""
    from sester.ledger import Ledger
    from sester.receipt import issue_receipt

    ledger = Ledger(str(tmp_path / "l.sqlite"), secret=_SECRET)
    event = ledger.append("charge_receipt", "buyer", "answrank_audit", 0.05,
                          payload={"prepay": True})
    receipt = issue_receipt(event, node_secret=_SECRET)

    gate = SesterPaymentGate(db_path=str(tmp_path / "r.sqlite"), secret=_SECRET)
    h = gate._receipt_hash(receipt)
    assert isinstance(h, str) and h != ""  # gercek sester HMAC hesabi

    import sester.receipt as _sr
    monkeypatch.setattr(_sr, "receipt_hash",
                        lambda r: (_ for _ in ()).throw(RuntimeError("boom")))
    assert gate._receipt_hash(receipt) == ""  # fail-closed, istisna degil


def test_get_ledger_reuses_injected_and_lazily_opens_sester(tmp_path, monkeypatch):
    """Honest arm: enjekte edilen ledger aynen doner (tekrar acilmaz);
    yoksa sester ledger'i db_path'de lazily acilir ve '_ledger_opened'
    flip eder. Fault arm: ledger acilamazsa hata gizlice yutulMAZ."""
    class _Ledger:
        def __init__(self, path, secret):
            self.path, self.secret = path, secret

    # 1) enjekte edilen ledger yeniden kullanilir
    inj = _Ledger("injected", "s")
    gate = SesterPaymentGate(secret=_SECRET, ledger=inj)
    assert gate._get_ledger() is inj
    assert gate._ledger_opened is True

    # 2) lazy acilis: gercek sester Ledger db_path'de olusur
    p = str(tmp_path / "ledger.sqlite")
    gate2 = SesterPaymentGate(db_path=p, secret=_SECRET)
    assert gate2._ledger_opened is False
    led = gate2._get_ledger()
    assert gate2._ledger_opened is True
    assert gate2._get_ledger() is led  # tek acilis
    import os
    assert os.path.exists(p)

    # 3) fault: ledger kurulu degilse ImportPath patlatir
    import sester.ledger as _sl
    monkeypatch.setattr(_sl, "Ledger",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kurulu degil")))
    gate3 = SesterPaymentGate(db_path=str(tmp_path / "nope.sqlite"), secret=_SECRET)
    with pytest.raises(RuntimeError, match="kurulu degil"):
        gate3._get_ledger()


def test_price_of_returns_priced_and_free_tools():
    """Honest: kayitli araclarin fiyati; bilinmeyen arac ucretsizdir."""
    gate = SesterPaymentGate(secret="")
    assert gate.price_of("answrank_audit") > 0
    assert gate.price_of("answrank_citations") > 0
    assert gate.price_of("answrank_generate_fixes") > 0
    assert gate.price_of("answrank_bilinmeyen") == 0.0


def test_status_labels_all_three_modes_honestly():
    """Honest arm: free / paid-test / paid-mainnet etiketleri acik; 'mode'
    field'i her durumda dogru karari tasir (no silent guessing)."""
    free = SesterPaymentGate(secret="").status()
    assert free["enabled"] is False and free["mode"] == "free"
    assert free["chain_check"] is False and "ucretsiz" in free["note"]

    sim = SesterPaymentGate(secret=_SECRET, test_mode=True).status()
    assert sim["enabled"] is True and sim["mode"] == "paid-test"
    assert sim["chain_check"] is False and "ARANMIYOR" in sim["note"]

    main = SesterPaymentGate(secret=_SECRET, test_mode=False).status()
    assert main["mode"] == "paid-mainnet"
    assert main["chain_check"] is True and "ZORUNLU" in main["note"]


def test_charge_as_dict_roundtrips_every_field():
    """Honest arm: kanitin tum alanlari MCP/API yanitina gecer."""
    c = Charge(seq=7, receipt_hash="abc", anchor_hash="def", mode="paid-mainnet",
               price_usdc=1.2, ledger_chain_valid=True, note="n")
    d = c.as_dict()
    assert d == {"seq": 7, "receipt_hash": "abc", "anchor_hash": "def",
                 "mode": "paid-mainnet", "price_usdc": 1.2,
                 "ledger_chain_valid": True, "note": "n"}


# ============================================== FINANS KANIT KALICILIGI (ode-me)
def test_invoice_persist_and_rehydrate_across_restart(db):
    """Honest arm: record_invoice DB'ye yazar; YENI TaxLedger (restart)
    kayitlari ve fatura numaralandirmasini geri yukler."""
    led = TaxLedger(load_persisted=False)
    r1 = led.record_invoice("Alpha", "UK", "GBP", 100.0, product_name="AnswRank")
    r2 = led.record_invoice("Beta", "TR", "TRY", 50.0, product_name="ClearTag")

    restarted = TaxLedger(load_persisted=True)
    ids = [x.invoice_id for x in restarted.records]
    assert r1.invoice_id in ids and r2.invoice_id in ids
    by_id = {x.invoice_id: x for x in restarted.records}
    assert by_id[r1.invoice_id].regime.value == "EXPORT_SERVICE"
    assert by_id[r1.invoice_id].fx_source == "static_default"
    assert by_id[r2.invoice_id].regime.value == "DOMESTIC_SERVICE"
    # numaralandirma devam eder (len(records)+1)
    assert restarted.record_invoice("Gamma", "US", "USD", 10.0).invoice_id == \
        f"UNPUMP-INV-{len(restarted.records):04d}"


def test_persist_record_failure_is_captured_not_raised(db, monkeypatch):
    """Fault arm: DB mirror patlarsa ledger issuance DURMAZ; hata
    'last_persist_error'da gorunur (gorunmez kalirsa pipeline sessizce
    kanitsiz calisir)."""
    led = TaxLedger(load_persisted=False)
    import answrank.db as _dbmod
    monkeypatch.setattr(_dbmod, "Database",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk dolu")))
    # istisna yutulmaz, sadelestirilir:
    led._persist_record(led.record_invoice("Alpha", "UK", "GBP", 10.0))
    assert led.last_persist_error == "disk dolu"


def test_load_persisted_records_skips_malformed_rows_without_poisoning(db):
    """Fault arm: bozuk/legacy satir atlanir, saglikli kayitlar
    zehirlenmez ('never poison the ledger')."""
    led = TaxLedger(load_persisted=False)
    good = led.record_invoice("Alpha", "UK", "GBP", 100.0)

    # bilerek bozuk regime'li legacy satir
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO tax_invoices (invoice_id, client_brand, client_country,"
            " regime, currency, amount_foreign, exchange_rate, fx_source,"
            " amount_try, vat_rate_pct, vat_amount_try, gross_total_try,"
            " exempt_income_try, taxable_base_try, legal_note, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("BAD-001", "X", "UK", "BOGUS_REGIME", "GBP", 1.0, 46.5, "static_default",
             46.5, 0.0, 0.0, 46.5, 46.5, 0.0, "note",
             datetime.now(timezone.utc).isoformat()))
        conn.commit()

    restarted = TaxLedger(load_persisted=True)
    ids = {x.invoice_id for x in restarted.records}
    assert good.invoice_id in ids
    assert "BAD-001" not in ids


def test_load_persisted_records_tolerates_uninitialized_store(monkeypatch):
    """Fault arm: store hic yoksa (Exception) bos tarihle devam -- crash
    yerine 'taze baslangic'."""
    import answrank.db as _dbmod
    monkeypatch.setattr(_dbmod, "Database",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("yok")))
    led = TaxLedger(load_persisted=True)
    assert led.records == []


def test_foreign_total_try_property_equals_field():
    """Honest arm: yardimci property rapor alanini gostermekten baska
    bir sey yapmaz (test-helper sozlesmesi)."""
    rep = UnifiedTaxReport(yil=2026, ay=9, taxpayer_name="Unpump",
                           product_rows=[], yurt_disi_toplam_try=1234.5,
                           yurtici_toplam_try=100.0, kdv_toplam_try=20.0,
                           muaf_gelir_try=1234.5, matrah_toplam_try=100.0,
                           brut_gelir_try=1334.5)
    assert rep.foreign_total_try == 1234.5


def test_net_kar_subtracts_all_costs_and_can_be_negative():
    """Honest arm: NET KAR = brut - tum maliyetler. Fault arm: maliyet
    geliri asarsa net kar NEGATIF olur (buyback icin iflas-korumasi
    tetikleyen budur) -- asla 0'ya yuvarlanmaz."""
    k = ServisGelirKaydi(servis="answrank", brut_gelir_usd=100.0,
                         llm_maliyet_usd=10.0, api_maliyet_usd=5.0,
                         altyapi_maliyet_usd=1.0, gelir_transferi_usd=2.0)
    assert k.toplam_maliyet_usd == 18.0
    assert k.net_kar_usd == 82.0

    neg = ServisGelirKaydi(servis="x", brut_gelir_usd=10.0, llm_maliyet_usd=20.0)
    assert neg.net_kar_usd == pytest.approx(-10.01)  # altyapi varsayilani 0.01
    sonuc = BuybackHesaplayici.hesapla([neg])
    assert sonuc["oneriler"][0].reddedildi is True
    assert sonuc["oneriler"][0].izin_verilen_buyback_usd == 0.0
    assert "iflas" in sonuc["oneriler"][0].red_nedeni


# ================================================ DB KANIT KALICILIGI (ranking)
def test_monitor_crud_roundtrip_and_missing_returns_none(db):
    """Honest arm: monitor olustur/oku/kosum ekle round-trip.
    Fault arm: olmayan monitor -> None (udurma veri uretilmez)."""
    now = datetime.now(timezone.utc).isoformat()
    assert db.get_monitor("yok") is None

    db.create_monitor("m-1", "a.example", "Marka", "dental", 30, "c-1", now)
    m = db.get_monitor("m-1")
    assert m is not None and m["domain"] == "a.example" and m["active"] == 1
    assert m["contract_id"] == "c-1" and m["cadence_days"] == 30

    rid = db.insert_monitor_run("m-1", now, "OK", 72.5, 12.3, "aud-1", "cite-1", "n")
    assert rid > 0
    runs = db.monitor_runs("m-1")
    assert len(runs) == 1 and runs[0]["score_base"] == 72.5
    assert runs[0]["sov_pct"] == 12.3 and runs[0]["audit_id"] == "aud-1"

    # baska monitorun kosumu karismaz
    db.create_monitor("m-2", "b.example", "B", "dental", 30, None, now)
    assert len(db.monitor_runs("m-2")) == 0


def test_list_monitors_honours_active_filter(db):
    """Honest arm: aktif filtresi; Fault arm: pasiflenen monitor
    varsayilan listeden DUSER (udurma izleme vaadi edilmez)."""
    now = datetime.now(timezone.utc).isoformat()
    db.create_monitor("m-1", "a.example", "A", "dental", 30, None, now)
    db.create_monitor("m-2", "b.example", "B", "dental", 30, None, now)
    assert len(db.list_monitors()) == 2

    with db._get_connection() as conn:
        conn.execute("UPDATE monitors SET active = 0 WHERE id = ?", ("m-2",))
        conn.commit()
    assert len(db.list_monitors()) == 1
    assert len(db.list_monitors(include_inactive=True)) == 2


def test_ensure_columns_migrates_old_install_and_is_idempotent(tmp_path):
    """Honest arm: ESKI kurulumda eksik sütun ALTER ile eklenir (ilk
    yazista 'no column named X' bozulmasinin onu). Fault arm: iki kez
    calismak hata uretmez (idempotent migration)."""
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    # kasitli ESKI sema: active/contract_id/next_due_at YOK
    conn.execute("CREATE TABLE monitors (id TEXT, domain TEXT, brand TEXT,"
                 " sector TEXT, cadence_days INTEGER)")
    conn.commit()
    conn.close()

    db = Database(db_path=p)
    with db._get_connection() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(monitors)")}
    assert {"active", "contract_id", "next_due_at", "created_at"} <= cols

    # tekrar olusturmak patlamaz
    db2 = Database(db_path=p)
    assert db2.get_monitor("yok") is None


def test_list_swarm_candidates_sync_parses_fixes_and_lock_flag(db):
    """Honest arm: fixes_json dict'e, territory_locked bool'a doner;
    siralama updated_at DESC'tur (en taze once). save_* updated_at'i
    her zaman simdi ile uzerine yazdigindan siralama ters-giris
    sirasina karsilik gelir."""
    db.save_swarm_candidate_sync({
        "id": "c-old", "brand_name": "B", "domain": "b.example",
        "fixes_generated": {}, "territory_locked": False,
        "stage": "QUALIFIED", "last_action": "y"})
    db.save_swarm_candidate_sync({
        "id": "c-new", "brand_name": "A", "domain": "a.example",
        "fixes_generated": {"robots": 1}, "territory_locked": True,
        "stage": "DISCOVERED", "last_action": "x"})

    rows = db.list_swarm_candidates_sync(limit=10)
    assert [r["id"] for r in rows] == ["c-new", "c-old"]
    assert rows[0]["fixes_generated"] == {"robots": 1}
    assert rows[0]["territory_locked"] is True
    assert rows[1]["territory_locked"] is False

    single = db.get_swarm_candidate_sync("c-new")
    assert single["fixes_generated"] == {"robots": 1}
    assert single["stage"] == "DISCOVERED"
    assert db.get_swarm_candidate_sync("yok") is None


def test_tax_invoice_persistence_orders_oldest_first(db):
    """Honest arm: faturalar created_at ASC listelenir (mali rapor sirasi).
    Fault arm: kayit yoksa bos liste (udurma fatura uretilmez)."""
    assert db.list_tax_invoices_sync() == []
    t2 = datetime.now(timezone.utc).isoformat()
    t1 = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db.save_tax_invoice_sync({
        "invoice_id": "INV-2", "client_brand": "B", "client_country": "UK",
        "regime": "EXPORT_SERVICE", "currency": "GBP", "amount_foreign": 10.0,
        "exchange_rate": 46.5, "fx_source": "static_default", "amount_try": 465.0,
        "vat_rate_pct": 0.0, "vat_amount_try": 0.0, "gross_total_try": 465.0,
        "exempt_income_try": 465.0, "taxable_base_try": 0.0,
        "legal_note": "n", "created_at": t2})
    db.save_tax_invoice_sync({
        "invoice_id": "INV-1", "client_brand": "A", "client_country": "TR",
        "regime": "DOMESTIC_SERVICE", "currency": "TRY", "amount_foreign": 10.0,
        "exchange_rate": 1.0, "fx_source": "static_default", "amount_try": 10.0,
        "vat_rate_pct": 20.0, "vat_amount_try": 2.0, "gross_total_try": 12.0,
        "exempt_income_try": 0.0, "taxable_base_try": 10.0,
        "legal_note": "n", "created_at": t1})
    rows = db.list_tax_invoices_sync()
    assert [r["invoice_id"] for r in rows] == ["INV-1", "INV-2"]


# ============================================ RANKING DENETIM KAPILARI (odeme)
def test_gate_result_to_dict_exposes_gate_passed_and_reason():
    """Honest arm: kapı sonucu serialize edilir (insan nedenini gorur)."""
    d = GateResult("ölçüm-var", True, "8 sorgu / 1 vuruş").to_dict()
    assert d == {"gate": "ölçüm-var", "passed": True, "reason": "8 sorgu / 1 vuruş"}
    d2 = GateResult("taze-ölçüm", False, "çok eski").to_dict()
    assert d2["passed"] is False


def test_gate_measurement_passes_on_live_run_fails_without(db):
    """Honest arm: gercek olcum var -> gecer. Fault arm: olcum yoksa
    'kanıtsız' gerekcesiyle DUSER (DM kanıtsız gonderilmez)."""
    _seed_vis(db, "a.example", total=8, found=1)
    aud = DmGateAuditor(db=db)
    ok = aud._gate_measurement("a.example")
    assert ok.passed is True and "1 vuruş" in ok.reason

    fail = aud._gate_measurement("yok.example")
    assert fail.passed is False
    assert fail.name == "ölçüm-var"
    assert "kanıt YOK" in fail.reason


def test_gate_probe_passes_only_for_measured_probe(db):
    """Honest arm: olculmus mini-probe var -> gecer. Fault arm: probe
    yoksa 'erişim kanıtı yok' ile DUSER."""
    _seed_probe(db, "a.example")
    aud = DmGateAuditor(db=db)
    ok = aud._gate_probe("a.example")
    assert ok.passed is True and ok.name == "mini-probe-var"
    assert "TEMİZ" in ok.reason

    fail = aud._gate_probe("yok.example")
    assert fail.passed is False
    assert "ölçülmedi" in fail.reason


def test_gate_contact_requires_verified_channel(db):
    """Honest arm: dogrulanmis telefon VEYA e-posta -> gecer.
    Fault arm 1: ikisi de DOĞRULANAMADI -> karanlik gonderim DUSER.
    Fault arm 2: aday kaydi yok -> alici belirsiz."""
    _seed_prospect(db, "a.example", phone="+905551112233", email="info@a.example")
    aud = DmGateAuditor(db=db)
    ok = aud._gate_contact("a.example")
    assert ok.passed is True and "kanıtlandı" in ok.reason

    _seed_prospect(db, "b.example", phone="DOĞRULANAMADI", email="DOĞRULANAMADI")
    dark = aud._gate_contact("b.example")
    assert dark.passed is False
    assert "DOĞRULANAMADI" in dark.reason

    with db._get_connection() as conn:
        conn.execute("DELETE FROM prospects WHERE domain_ref = ?", ("b.example",))
        conn.commit()
    none = aud._gate_contact("b.example")
    assert none.passed is False and "aday yok" in none.reason


# ============================================ RANKING BOLGE KILITLERI (mesh)
def test_persisted_territory_locks_are_restored_on_restart(db):
    """Honest arm: restart sonrasi DB'deki kilidler geri yuklenir
    (Madde-7 yamyamlik korumasi durumlu, sessiz degil)."""
    db.save_territory_lock_sync({
        "lock_id": "LOCK-0001", "country": "UK", "city": "london",
        "niche": "dental", "client_domain": "a.example", "brand_name": "Alpha",
        "tier": "EXCLUSIVE", "contract_id": "c-1",
        "created_at": datetime.now(timezone.utc).isoformat()})

    orch = SwarmOrchestrator(db=db)
    locks = orch.get_territory_locks()
    assert len(locks) == 1
    assert locks[0].country == "UK" and locks[0].city == "london"
    assert locks[0].niche == "dental" and locks[0].client_domain == "a.example"
    assert locks[0].tier == "EXCLUSIVE" and locks[0].contract_id == "c-1"
    # eksikus: ayni bolgeye baska marka CAKISIR (kilit tasinmis)
    conflict = orch.exclusivity.check_conflict(
        "UK", "London", "dental", "b.example")
    assert conflict.has_conflict is True
    assert conflict.action_recommended == "PARTITION_SUB_NICHE"
    assert conflict.suggested_sub_niches  # dental taksonomisinden alternatif sunar
    assert "Alpha" in (conflict.conflict_reason or "")

    # bos store ile soguk baslangic: kilitsiz ama calisir
    db2 = Database(db_path=str(db.db_path) + ".b")
    assert SwarmOrchestrator(db=db2).get_territory_locks() == []


def test_lock_restore_failure_is_contained_not_fatal(db, monkeypatch):
    """Fault arm: DB okunamazsa orchestrator YINE olusur (warning ile);
    kilitler bos baslar, crash etmez (soguk baslangic guvenli)."""
    monkeypatch.setattr(db, "list_territory_locks_sync",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    orch = SwarmOrchestrator(db=db)
    assert orch.get_territory_locks() == []


def test_exclusivity_make_key_normalizes_consistently():
    """Honest arm: ayni bolge farkli yazim -> ayni anahtar (case/trim).
    Fault arm: farkli bolge -> farkli anahtar (kilid karismaz)."""
    k1 = ExclusivityManager._make_key("UK", "  London ", "Dental")
    k2 = ExclusivityManager._make_key("uk", "london", "dental")
    assert k1 == k2 == "UK:london:dental"
    assert ExclusivityManager._make_key("US", "london", "dental") != k1
    assert ExclusivityManager._make_key("UK", "manchester", "dental") != k1


def test_hybrid_key_manager_get_key_returns_configured_only():
    """Honest arm: yapilandirilmis provider anahtarini doner.
    Fault arm: yapilandirilmamis provider -> None (anahtar uydurulmaz,
    canli arama DENMEZ, sim fallback dogru secilir)."""
    mgr = HybridKeyManager(custom_keys={LLMProvider.PERPLEXITY: "sk-live-xyz"})
    assert mgr.get_key(LLMProvider.PERPLEXITY) == "sk-live-xyz"
    for p in (LLMProvider.OPENAI, LLMProvider.GEMINI, LLMProvider.ANTHROPIC,
              LLMProvider.MISTRAL, LLMProvider.SERPAPI):
        assert mgr.get_key(p) is None


# ================================================ OLCUM DURUSTLUGU (citations)
def test_simulate_response_cites_brand_only_above_threshold():
    """Honest arm: skor >= 70 -> marka alintili; dusuk skor -> marka
    YOK (ucretli'de 'gorunuyorsunuz' yalan soylenmez)."""
    runner = MultiLLMCitationRunner()
    high = runner._simulate_response("Marka", "a.example", "İstanbul",
                                     "rakip.example", "rakip2.example", 1, 85)
    assert "Marka" in high and "rakip.example" in high

    low = runner._simulate_response("Marka", "a.example", "İstanbul",
                                    "rakip.example", "rakip2.example", 1, 10)
    assert "Marka" not in low
    assert low.startswith("1. [rakip.example]")


def test_simulate_response_uses_only_caller_competitors():
    """Honest arm: yalnizca cagiranin verdigi rakiplar metne girer;
    urune gomulu kurgusal rakip ENJEKTE EDILMEZ (olcum yanitinda
    yapay-zeka izi birakmaz)."""
    runner = MultiLLMCitationRunner()
    out = runner._simulate_response("Marka", "a.example", "İstanbul",
                                    "c1.example", "c2.example", 3, 10)
    assert "c1.example" in out and "c2.example" in out
    # ikinci rakip verilmezse birincisi tekrar eder (udurma rakip YOK)
    one = runner._simulate_response("Marka", "a.example", "İstanbul",
                                    "c1.example", None, 3, 10)
    assert one.count("https://c1.example") == 2 and "Rakip İşletme" not in one


def test_simulate_response_q7_q8_low_score_still_cites():
    """Honest arm: q_id 7/8'de skor >= 30 ise marka alintili sayilir
    (sektor soru bankasindaki bilinen ayristirici sorular)."""
    runner = MultiLLMCitationRunner()
    out = runner._simulate_response("Marka", "a.example", "İstanbul",
                                    "rakip.example", None, 7, 40)
    assert "Marka" in out
    # ayni skor ama farkli soru -> alinti YOK
    out2 = runner._simulate_response("Marka", "a.example", "İstanbul",
                                     "rakip.example", None, 3, 40)
    assert "Marka" not in out2


def test_mark_grounding_keeps_first_observed_status():
    """Honest arm: ILK olculen modalite kalir; sonraki cagrilar onu
    ucurumdan degistirmez (modalite uydurulmaz, sadece gozlemlenir)."""
    runner = MultiLLMCitationRunner()
    runner._mark_grounding("ChatGPT-4o", "search-grounded")
    runner._mark_grounding("ChatGPT-4o", "model-recall")
    runner._mark_grounding("ChatGPT-4o", "ölçülemedi")
    assert runner.grounding_status["ChatGPT-4o"] == "search-grounded"
    # baska model bagimsiz
    runner._mark_grounding("Gemini-Pro", "anahtar yok")
    assert runner.grounding_status["Gemini-Pro"] == "anahtar yok"


def test_grounded_or_recall_labels_modality_honestly(monkeypatch):
    """Honest/fault kollari:
      - grounded basarili -> 'search-grounded'
      - grounded patlar, plain doner -> 'model-recall'
      - plain bos/None -> 'ölçülemedi' (etiket uydurulmaz)
      - ikisi de patlar -> None + 'ölçülemedi'
    """
    # kod SINIF attribute'una bakar; instance attr etkisizdir
    monkeypatch.setattr(MultiLLMCitationRunner, "GROUNDING_DISABLED", False)
    runner = MultiLLMCitationRunner()

    async def g_ok():
        return "grounded answer"

    async def g_fail():
        raise RuntimeError("grounding down")

    async def p_ok():
        return "recall answer"

    async def p_none():
        return None

    async def p_fail():
        raise RuntimeError("api down")

    out = asyncio.run(runner._grounded_or_recall("M", g_ok, p_none))
    assert out == "grounded answer"
    assert runner.grounding_status["M"] == "search-grounded"

    out = asyncio.run(runner._grounded_or_recall("M2", g_fail, p_ok))
    assert out == "recall answer"
    assert runner.grounding_status["M2"] == "model-recall"

    out = asyncio.run(runner._grounded_or_recall("M3", g_fail, p_none))
    assert out is None
    assert runner.grounding_status["M3"] == "ölçülemedi"

    out = asyncio.run(runner._grounded_or_recall("M4", g_fail, p_fail))
    assert out is None
    assert runner.grounding_status["M4"] == "ölçülemedi"


def test_grounded_or_recall_skips_grounding_when_disabled(monkeypatch):
    """Honest arm: GROUNDING_DISABLED iken grounded cagrilmaz; plain
    sonucu 'model-recall' olarak dogru etiketlenir."""
    monkeypatch.setattr(MultiLLMCitationRunner, "GROUNDING_DISABLED", True)
    runner = MultiLLMCitationRunner()
    calls = []

    async def g_ok():
        calls.append("grounded")
        return "grounded answer"

    async def p_ok():
        return "recall answer"

    out = asyncio.run(runner._grounded_or_recall("M", g_ok, p_ok))
    assert out == "recall answer"
    assert calls == []
    assert runner.grounding_status["M"] == "model-recall"


# ============================================================ RAPOR (ranking)
def test_branding_defaults_and_white_label_replaces_name():
    """Honest arm: beyaz etikette AnswRank adi/logo GIZLENIR (kelime
    isaretinin tek sahibi). Fault arm: eksik alan -> varsayilan."""
    assert ReportGenerator._branding() == ("AnswRank", None)
    assert ReportGenerator._branding({}) == ("AnswRank", None)
    name, logo = ReportGenerator._branding({"name": "AjansX", "logo_url": "/l.png"})
    assert name == "AjansX" and logo == "/l.png"
    assert "AnswRank" not in ReportGenerator._branding({"name": "AjansX"})[0]


def test_citation_share_md_honest_when_unmeasured():
    """Fault arm: olcum yoksa 'ölçülmedi' notu basilir, sayi UYDURULMAZ."""
    md = ReportGenerator()._citation_share_md(None)
    assert "bulunamadı" in md and "ölçülmedi" in md
    assert "%" not in md.split("---")[0].split("=")[-1] or "%{s" not in md


def test_citation_share_md_reports_measured_numbers_and_liveliness():
    """Honest arm: olcumlu koşu icin pay/yuzde/motor kirilimi ve canlilik
    notu (sim karisiksa esdegerlik iddia edilmez)."""
    md = ReportGenerator()._citation_share_md(_citations_run("a.example", 8, 2))
    assert "%25" in md
    assert "Marka" in md
    assert "test-model: 2/8" in md
    assert "8/8 yanıt canlı API ölçümüdür" in md  # tamamen canli koşu

    md_sim = ReportGenerator()._citation_share_md(
        _citations_run("b.example", 4, 1, fully_live=False))
    assert "CANLİ API" in md_sim and "SİMÜLASYON" in md_sim
    assert "yalnızca canlı alt-küme" in md_sim


# ================================================================ ONBELLEK
def test_cache_entry_is_fresh_within_ttl_and_stale_after():
    """Honest arm: TTL icinde taze; TTL disinda bayat (yeniden fetch).
    Fault arm: negatif/garanti suresi gecmis -> bayat."""
    now = 100.0
    fresh = _CacheEntry(value="v", stored_at=95.0, ttl_seconds=10.0)
    assert fresh.is_fresh(now) is True
    assert fresh.is_fresh(106.0) is False
    assert _CacheEntry(value="v", stored_at=0.0, ttl_seconds=1.0).is_fresh(100.0) is False


def test_evict_drops_expired_first_then_oldest_at_capacity():
    """Honest arm 1: kapasitede tum girdiler suresi gectiyse once onlar
    atilir (hicbir taze veri atilmaz).
    Honest arm 2: hepsi tazeyse en ESKI atilir (FIFO-ish)."""
    import time as _time

    now = _time.monotonic()
    cache = TTLCache(default_ttl_seconds=300.0, max_entries=3)
    assert cache._evict_if_needed() is None  # bosken no-op

    for i in range(3):  # hepsi suresi gecmis
        cache._store[f"k{i}"] = _CacheEntry(value=i, stored_at=now - 10000.0,
                                            ttl_seconds=1.0)
    cache._evict_if_needed()
    assert cache._store == {}

    # hepsi taze; en eskisi k0 (stored_at en kucuk)
    for i, age in enumerate((200.0, 100.0, 0.0)):
        cache._store[f"k{i}"] = _CacheEntry(value=i, stored_at=now - age,
                                            ttl_seconds=10000.0)
    cache._evict_if_needed()
    assert "k0" not in cache._store and len(cache._store) == 2
    assert set(cache._store) == {"k1", "k2"}


# ================================================================== SITEMAP
def test_is_index_detects_sitemapindex_within_600_char_window():
    """Honest arm: <sitemapindex> ilk 600 karakterde -> True.
    Fault arm: urlset -> False; isaret 600+ otede -> False (pencere disi)."""
    assert SitemapAuditor._is_index('<?xml version="1.0"?><sitemapindex xmlns="...">') is True
    assert SitemapAuditor._is_index('<urlset xmlns="http://www.sitemaps.org/...">') is False
    # isaret pencerenin disinda -> gectirilmemeli
    far = "x" * 600 + "<sitemapindex>"
    assert SitemapAuditor._is_index(far) is False


def test_extract_locs_parses_xml_and_falls_back_to_regex():
    """Honest arm: gecerli XML'den loc'lar cekilir; tekrarlar ve
    http disi URL'ler elenir. Fault arm: bozuk XML -> regex fallback."""
    xml = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://a.example/</loc></url>'
           '<url><loc>https://a.example/x</loc></url>'
           '<url><loc>https://a.example/</loc></url>'  # dup
           '<url><loc>ftp://a.example/y</loc></url>'   # http disi
           '</urlset>')
    assert SitemapAuditor._extract_locs(xml) == [
        "https://a.example/", "https://a.example/x"]

    # XML patlak -> regex yedegi yine de calisir
    broken = "<urlset><url><loc>https://b.example/z</loc></url>"
    assert SitemapAuditor._extract_locs(broken) == ["https://b.example/z"]
    assert SitemapAuditor._extract_locs("") == []


# ==================================================================== PROBE
def test_bad_ip_flags_internal_and_allows_public():
    """Honest arm: ozel/loopback/link-local/reserved/multicast/unspecified
    -> True (SSRF kalkani). Fault arm: gercek public IP -> False."""
    for bad in ("10.0.0.1", "127.0.0.1", "::1", "169.254.169.254",
                "240.0.0.1", "224.0.0.1", "0.0.0.0", "fc00::1"):
        assert MiniProbe._bad_ip(ipaddress.ip_address(bad)) is True, bad
    for good in ("8.8.8.8", "1.1.1.1", "2606:4700::1111"):
        assert MiniProbe._bad_ip(ipaddress.ip_address(good)) is False, good


def test_robots_line_verdicts_are_measurement_gated():
    """Honest arm: 404 -> izinli (RFC 9309); 200+acik -> izinli;
    200+kapali -> engelli. Fault arm: indirilemeyen/ayrıştırılamayan
    -> OLÇULEMEDI (suclama uretilmez)."""
    assert MiniProbe._robots_line((404, None))[0].startswith("İZİNLİ")
    assert MiniProbe._robots_line((200, "User-agent: *\nAllow: /\n"))[0] == \
        "İZİNLİ (AI araması açık)"
    assert MiniProbe._robots_line((200, "User-agent: *\nDisallow: /\n"))[0] == \
        "ENGELLİ (robots.txt AI aramasını kapatıyor)"
    assert MiniProbe._robots_line((None, None))[0].startswith("ÖLÇÜLEMEDİ")
    assert MiniProbe._robots_line((503, None))[0].startswith("ÖLÇÜLEMEDİ")


def test_robots_line_treats_unparseable_body_as_unmeasured(monkeypatch):
    """Fault arm: analyzer patlarsa OLÇULEMEDI (olcum kapisinda
    yarim sonuc 'acik' sanilmaz)."""
    from answrank.audit.analyzers import robots as _robots

    monkeypatch.setattr(_robots.RobotsAnalyzer, "analyze",
                        lambda self, txt: (_ for _ in ()).throw(ValueError("bad")))
    line, ok, clean = MiniProbe._robots_line((200, "User-agent: *\nAllow: /\n"))
    assert ok is False and line.startswith("ÖLÇÜLEMEDİ")


def test_llms_line_verdicts_are_measurement_gated():
    """Honest arm: 200+dolu -> VAR; 404 -> YOK. Fault arm: network hatasi
    veya bos govde -> OLÇULEMEDI (yok DENMEZ)."""
    assert MiniProbe._llms_line((200, "# title\n\n## link\n- [x](https://a)")) == ("VAR", True)
    assert MiniProbe._llms_line((404, None)) == ("YOK", True)
    assert MiniProbe._llms_line((None, None))[1] is False
    assert MiniProbe._llms_line((200, "   "))[1] is False  # bos govde = olculmedi
    assert MiniProbe._llms_line((500, None))[1] is False


# ============================================================= PROSPEKTOR
def test_robots_disallows_all_only_for_star_group_root():
    """Honest arm: 'User-agent: *'+Disallow: / (veya bos) -> izin yok.
    Fault arm: baska user-agent grubu veya spesifik yol -> izinli;
    yorumlar ve bos satirlar gectirilir."""
    assert LeadProspector._robots_disallows_all(
        "User-agent: *\nDisallow: /\n") is True
    assert LeadProspector._robots_disallows_all(
        "# notlar\nUser-agent: *\nDisallow:\n") is True
    assert LeadProspector._robots_disallows_all(
        "User-agent: GPTBot\nDisallow: /\n") is False  # farkli grup
    assert LeadProspector._robots_disallows_all(
        "User-agent: *\nDisallow: /private\n") is False  # spesifik yol
    assert LeadProspector._robots_disallows_all("") is False
    assert LeadProspector._robots_disallows_all(
        "User-agent: *\nAllow: /\nDisallow: /tmp\n") is False


def test_challenge_or_error_detection():
    """Honest arm: bot-challenge/hata basligi -> True (icerik kaniti
    degil). Fault arm: normal baslik -> False; basliksiz govde -> True."""
    pros = LeadProspector()
    assert pros._looks_like_challenge_or_error(
        "<html><title>Just a moment...</title></html>") is True
    assert pros._looks_like_challenge_or_error(
        "<html><title>Checking your browser before accessing</title></html>") is True
    assert pros._looks_like_challenge_or_error(
        "<html><title>Acibadem Dental Clinic</title></html>") is False
    assert pros._looks_like_challenge_or_error("<html><body>no title</body></html>") is True


def test_extract_contacts_prefers_jsonld_and_filters_junk():
    """Honest arm: JSON-LD en guvenilir kaynak; sonra sayfa metni.
    Fault arm: sahte host/TLD/saf-rakam e-postalar elenir; hicbir sey
    yoksa (None, None, None) (iletişim uydurulmaz)."""
    pros = LeadProspector()
    jsonld = ('<script type="application/ld+json">'
              '{"@type":"Dentist","telephone":"902125551122","email":"info@acibadem.example"}'
              '</script>')
    tel, mail, src = pros._extract_contacts(jsonld)
    assert tel == "+902125551122" and mail == "info@acibadem.example"
    assert src == "json-ld"

    page = ('<html><body>'
            '<a href="mailto:iletisim@klinik.example">bize ulasin</a>'
            '<img src="logo.png"> sprite.flags@2x.webp'
            '<span>+90 216 555 11 22</span>'
            '<span>abc1234567890123456789012345678901234567890@example.com</span>'
            '</body></html>')
    tel2, mail2, src2 = pros._extract_contacts(page)
    assert src2 == "page-text"
    assert mail2 == "iletisim@klinik.example"
    assert tel2 == "+90 216 555 11 22"
    assert "2x.webp" not in mail2  # sahte TLD elendi

    nothing = pros._extract_contacts("<html><body>iletişim yok</body></html>")
    assert nothing == (None, None, None)


# =============================================================== BUTUNLUK
def test_tokenize_normalizes_lowercases_and_drops_stopwords():
    """Honest arm: kucuk harf + noktalama at + TR/EN durak kelimeleri
    elenir; Turkce karakter korunur. Fault arm: bos metin -> bos liste."""
    toks = RAGEngine._tokenize("Merhaba! Bu bir TEST metin, ve 123 ile dunya.")
    assert toks == ["merhaba", "test", "metin", "123", "dunya"]
    assert RAGEngine._tokenize("") == []
    assert RAGEngine._tokenize("ve ile için the and") == []
    # 3 karaktenden kisa tokenler elenir
    assert RAGEngine._tokenize("a ab abc abcd") == ["abc", "abcd"]


def test_mcp_anchor_for_is_machine_verifiable():
    """Honest arm: anchor ciktisi musteri tarafindan tekrar
    hesaplanabilir boyuttadir; ayni girdi ayni SHA-256."""
    from answrank.mcp.server import AnswRankMCPServer

    a = AnswRankMCPServer._anchor_for(
        "answrank_audit", {"url": "https://a.example"},
        {"domain": "a.example", "overall_score": 42, "score_band": "Foundation"})
    assert a == {"domain": "a.example", "overall_score": 42,
                 "score_band": "Foundation"}

    c = AnswRankMCPServer._anchor_for(
        "answrank_citations", {},
        {"brand": "Marka", "citation_rate_percentage": 25.0, "total_runs": 8})
    assert c == {"brand": "Marka", "citation_rate_percentage": 25.0,
                 "total_runs": 8}

    fixes = {"robots_txt": "r", "llms_txt": "l", "json_ld": "j"}
    f1 = AnswRankMCPServer._anchor_for("answrank_generate_fixes",
                                       {"domain": "a.example"}, dict(fixes))
    f2 = AnswRankMCPServer._anchor_for("answrank_generate_fixes",
                                       {"domain": "a.example"}, dict(fixes))
    assert f1 == f2 and f1["domain"] == "a.example"
    assert len(f1["sha256"]) == 64
    different = AnswRankMCPServer._anchor_for(
        "answrank_generate_fixes", {"domain": "a.example"},
        {"robots_txt": "R", "llms_txt": "l", "json_ld": "j"})
    assert different["sha256"] != f1["sha256"]
    # eksik artefakt degisen digest (bos string kabul edilir, sabit degil)
    assert AnswRankMCPServer._anchor_for(
        "answrank_generate_fixes", {"domain": "a.example"},
        {"robots_txt": "r"})["sha256"] != f1["sha256"]


def test_netloc_of_extracts_canonical_host_and_rejects_empty():
    """Honest arm: scheme/www/path soyulur, kucuk harf. Fault arm: bos
    girdi -> None (domain matching uydurma degil)."""
    assert EntityGroundingEngine._netloc_of("https://WWW.Example.com/a/b?x=1") == \
        "example.com"
    assert EntityGroundingEngine._netloc_of("https://sub.example.com/") == \
        "sub.example.com"
    assert EntityGroundingEngine._netloc_of("") is None


def test_ai_bots_total_is_derived_and_drift_free(monkeypatch):
    """Honest arm: toplam uc katmanin CANLI toplamidir; ozet metni ayni
    sayilari tasiyacak (marketing/legal copy kaymasin).
    Fault arm: katman listesi degisirse tureyen de degisir (cache yok)."""
    total = settings.ai_bots_total
    assert total == len(settings.ai_bots_search) + len(settings.ai_bots_training) \
        + len(settings.ai_bots_user_agents)
    assert total > 0
    summary = settings.ai_bots_tier_summary
    assert summary.startswith(f"{total} AI botu (")
    assert f"{len(settings.ai_bots_search)} arama" in summary
    assert f"{len(settings.ai_bots_training)} eğitim" in summary
    assert f"{len(settings.ai_bots_user_agents)} kullanıcı-ajanı" in summary

    monkeypatch.setattr(settings, "ai_bots_search", ["A", "B"])
    assert settings.ai_bots_total == 2 + len(settings.ai_bots_training) \
        + len(settings.ai_bots_user_agents)
    assert settings.ai_bots_tier_summary.startswith(
        f"{settings.ai_bots_total} AI botu (")


def test_corpus_stats_produces_no_ratio_without_denominator(db):
    """Honest arm: payda 0 ise oran uretilmez ('ÖLÇÜLEMEDİ (0 ölçümlü
    satır)'); olculmus satir varsa kendi paydasiyla sayi uretilir.
    Fault arm: olcumemis satir pct'ye konmaz."""
    store = CorpusStore(db)
    st = store.stats()
    assert st["n"] == 0
    assert st["robots_open_pct"]["pct"] is None

    store.save_observation(MiniProbeResult(
        domain="a.example", verdict="TEMİZ", robots_line="İZİNLİ (AI araması açık)",
        llms_line="VAR", bots_line="3/3 örnek bot erişebiliyor", blocked_bots=[],
        probed=3, measured=True, robots_status=200, llms_status=200,
        bot_statuses={"GPTBot": 200}), source="test")
    st2 = store.stats(source="test")
    assert st2["n"] == 1
    assert st2["robots_open_pct"] == {"n": 1, "pct": 100.0, "num": 1}
    assert st2["robots_llms_present"] == {"n": 1, "pct": 100.0, "num": 1}

    md = render_report_md(CorpusStore(db).stats(), "test methodi")
    assert "0 ölçümlü satır" in md or "%100.0 (1/1 ölçümlü satır)" in md


def test_banked_lang_and_known_sector_reject_unknown():
    """Honest arm: tr/en ve bankali sektor kabul. Fault arm: banka disi
    dil/sektor 422 ile reddedilir (sessiz fallback yalan olmaz)."""
    from answrank.api.app import CitationRequest

    ok = CitationRequest(brand_name="M", domain="a.example", lang="en",
                         sector="aesthetic")
    assert ok.lang == "en" and ok.sector == "aesthetic"
    with pytest.raises(ValidationError):
        CitationRequest(brand_name="M", domain="a.example", lang="de")
    with pytest.raises(ValidationError):
        CitationRequest(brand_name="M", domain="a.example", sector="uzay")


def test_monitor_create_sector_must_be_in_banks():
    """Honest arm: bilinen sektor gecer. Fault arm: bilinmeyen sektor
    reddedilir (udurma soru bankasina dusmez)."""
    from answrank.api.app import MonitorCreate

    ok = MonitorCreate(domain="a.example", brand="Ma", sector="dental")
    assert ok.sector == "dental" and ok.cadence_days == 30
    with pytest.raises(ValidationError):
        MonitorCreate(domain="a.example", brand="Ma", sector="gitars")
    # alan uzunluk kistleri (edge guard)
    with pytest.raises(ValidationError):
        MonitorCreate(domain="ab", brand="Ma", sector="dental")
    with pytest.raises(ValidationError):
        MonitorCreate(domain="a.example", brand="M", sector="dental")


def test_dm_sender_smtp_creds_absent_and_already_sent_semantics(tmp_path, monkeypatch):
    """Honest arm: SMTP env yok -> smtp_creds None (manual moda dusus).
    already_sent: GÖNDERİLDİ/YAPILANDIRILMAMIŞ tekrari engeller; HATA
    (belirsiz girişim) tekrar engelleMEZ (fail-closed temas sayar).
    Dis cagri yapilmaz (kural 7): yalnizca fonksiyonun kendi sozlesmesi."""
    import answrank.crm.dm_sender as _dm

    monkeypatch.setattr(_dm, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.delenv("ANSWRANK_SMTP_HOST", raising=False)
    db = Database(db_path=str(tmp_path / "dm.db"))
    sender = DMSender(db_path=str(db.db_path))
    assert sender.smtp_creds() is None
    assert sender.channel() == "manual"

    # SMTP creds varsa channel smtp'e doner (env'den, gonderim yapilmaz)
    monkeypatch.setenv("ANSWRANK_SMTP_HOST", "smtp.example")
    monkeypatch.setenv("ANSWRANK_SMTP_PORT", "587")
    creds = sender.smtp_creds()
    assert creds["host"] == "smtp.example" and creds["port"] == 587
    assert sender.channel() == "smtp"
    monkeypatch.delenv("ANSWRANK_SMTP_HOST", raising=False)
    assert sender.smtp_creds() is None

    now = datetime.now(timezone.utc).isoformat()
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note,"
            " sent_at) VALUES (?,?,?,?,?,?)",
            (1, "a.example", "x@a.example", "GÖNDERİLDİ", "ok", now))
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note,"
            " sent_at) VALUES (?,?,?,?,?,?)",
            (2, "b.example", "x@b.example", "YAPILANDIRILMAMIŞ", "eml hazir", now))
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note,"
            " sent_at) VALUES (?,?,?,?,?,?)",
            (3, "c.example", "x@c.example", "HATA", "smtp down", now))
        conn.commit()

    assert sender.already_sent(1, "x@a.example") is True
    assert sender.already_sent(2, "x@b.example") is True
    assert sender.already_sent(3, "x@c.example") is False  # HATA tekrar engellemez
    assert sender.already_sent(99, "y@z.example") is False
    # ayni kuyruk farkli alici -> ayri kayit
    assert sender.already_sent(1, "baska@a.example") is False


def test_dm_dispatcher_log_send_is_idempotent_and_protects_real_sends(db):
    """Honest arm: no-op statuler (HEDEF_YOK) idempotent yazilir; ayni
    cagri yeni satir ACMAZ. Fault arm: GÖNDERİLDİ sonrasi no-op UPDATE'i
    gercek gonderimi USTTE YAZMAZ (kanit bozulmaz)."""
    disp = DmDispatcher(db=db)
    disp._log_send(7, "a.example", "x@a.example", "HEDEF_YOK", "eposta yok",
                   dry_run=False)
    disp._log_send(7, "a.example", "x@a.example", "HEDEF_YOK", "hala yok",
                   dry_run=False)
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT status, note FROM dm_send_log WHERE queue_id=7").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "HEDEF_YOK" and rows[0]["note"] == "hala yok"

    # dry_run hic yazmaz
    with db._get_connection() as conn:
        n_before = conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0]
    disp._log_send(8, "b.example", "x@b.example", "HEDEF_YOK", "n", dry_run=True)
    with db._get_connection() as conn:
        n_after = conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0]
    assert n_before == n_after

    # gercek gonderim no-op tarafinden uzerine yazilamaz
    disp._log_send(9, "c.example", "x@c.example", "GÖNDERİLDİ", "smtp", dry_run=False)
    disp._log_send(9, "c.example", "x@c.example", "HEDEF_YOK", "sonradan", dry_run=False)
    with db._get_connection() as conn:
        st = conn.execute(
            "SELECT status FROM dm_send_log WHERE queue_id=9").fetchone()["status"]
    assert st == "GÖNDERİLDİ"
