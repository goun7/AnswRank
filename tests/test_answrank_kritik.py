"""EN KRITIK test-disi fonksiyonlar icin dal-kesen unit testler (2026-10-06).

Hedefler (AST ile tespit edildi; tests/ icinde kendi adlariyla cagrilmayanlar):
  1. answrank/cli.py:901  run_payments_command  (86L; tahsilat kanali, MANUAL havale, PSP yok)  -- EN KRITIK
  2. answrank/cli.py:24   run_audit_command     (132L; denetim + 360 derin panel + rapor disa-aktarim)
  3. answrank/cli.py:306  run_crm_command       (120L; DM onay-kapisi, onaysiz gonderim yok)
  4. answrank/cli.py:1035 run_queue_command     (75L; insan-onay kuyrugu, auto-approve denetimi)
  5. answrank/api/app.py:587 trigger_swarm_scout (68L; kuratörlü demo havuzu, .example güvenlik klişesi)

Yöntem: her fonksiyon GERÇEK kodu okunup dallarına incektirildi; dış çağrılar
(AuditEngine HTTP taraması, PaymentService DB, SwarmOrchestrator ağ geçidi)
mock'lanır — yalnızca fonksiyonun KENDİ mantığı (dal seçimi, hata yüzeyi,
geçerli/Geçersiz giriş ayıklaması) ölçülür. Sahte başarılı ödeme/ölçüm
üretilmez; fonksiyonların "uydurma yok" kuralları korunur.
"""
import argparse
import asyncio
import json

import pytest

from answrank import cli as cli_mod


# ═════════════════════════════════ yardımcılar ═════════════════════════════════

def _capture(monkeypatch):
    """console.print çıktısını bir buffer'a yönlendirir (ANSI’siz, sarmasız)."""
    import io
    from rich.console import Console

    buf = io.StringIO()
    fake = Console(file=buf, width=200, no_color=True, color_system=None,
                   force_terminal=False, tab_size=4)
    monkeypatch.setattr(cli_mod, "console", fake)
    return buf


def _flat(buf):
    """Rich kutu karakterlerini ve çoklu boşlukları temizleyip düz metin verir."""
    text = buf.getvalue()
    for ch in ("│", "╭", "╮", "╰", "╯", "─", "├", "┤", "┬", "┴", "┼"):
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _args(**kw):
    """Argparse Namespace'ini taklit eden hafif taşıyıcı."""
    return argparse.Namespace(**kw)


def _make_audit(overall=72, lost=None):
    """Sekiz kategoride geçerli bir AuditResult üretir (gerçek model)."""
    from answrank.models import (CategoryScores, CitabilityScore, EntityScore,
                                 MetaScore, NegativeScore, RobotsScore, SchemaScore,
                                 TrustScore, LlmsTxtScore, AuditResult)

    cats = CategoryScores(
        robots=RobotsScore(score=15, details=["robots detay"]),
        llms_txt=LlmsTxtScore(score=14, details=["llms detay"]),
        schema_jsonld=SchemaScore(score=12, details=["schema detay"]),
        meta_architecture=MetaScore(score=10, details=["meta detay"]),
        citability_rag=CitabilityScore(score=9, details=["rag detay"]),
        entity_coherence=EntityScore(score=7, details=["entity detay"]),
        trust_stack=TrustScore(score=5, details=["trust detay"]),
        negative_signals=NegativeScore(score=5, details=["neg detay"]),
    )
    return AuditResult(
        audit_id="kritik-1", url="https://kritik.example",
        domain="kritik.example", sector="dental", overall_score=overall,
        score_band="Good" if overall >= 68 else "Foundation",
        categories=cats, lost_revenue_estimate_monthly_try=lost,
    )


def _make_deep(audit, waf=None, adversarial=None, entity=None, rag=None,
               composite=70.0, tier="STABLE"):
    from answrank.audit.engine import DeepAuditResult
    return DeepAuditResult(
        base_audit=audit, waf_probe=waf, adversarial=adversarial,
        entity_grounding=entity, rag_analysis=rag,
        composite_deep_score=composite, deep_tier=tier, key_findings=[],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1) run_payments_command — EN KRITIK (tahsilat kanali; PSP yok, MANUAL havale)
# ═══════════════════════════════════════════════════════════════════════════════

class FakePaymentService:
    """PaymentService'in karar veren kısımlarını taklit eder.

    `create_intent` / `confirm_manual` / `refund` gerçek DB'ye dokunmadan
    önceden ayarlanmış sonucu döner; çağrıları kaydeder. `provider_status`
    gerçek PaymentService ile aynıdür (PSP yok → YAPILANDIRILMAMIŞ)."""

    def __init__(self, *, ledger=None, intent=None, confirm=None, webhook=None,
                 refund=None, raise_on=None, confirm_raises=False):
        self.ledger = ledger
        self.calls = []
        self._intent = intent
        self._confirm = confirm
        self._webhook = webhook
        self._refund = refund
        self._raise_on = raise_on or {}
        self._confirm_raises = confirm_raises

    def provider_status(self, provider):
        from answrank.finance.payments import PaymentProvider
        if provider == PaymentProvider.MANUAL:
            return "HAZIR" if self._manual_iban else "IBAN YOK (havale kanalı açık değil)"
        return "YAPILANDIRILMAMIŞ — PSP anlaşması yok"

    @property
    def _manual_iban(self):
        import os
        return bool(os.getenv("ANSWRANK_MANUAL_IBAN"))

    def create_intent(self, req, provider):
        if "create_intent" in self._raise_on:
            raise self._raise_on["create_intent"]
        self.calls.append(("create_intent", req, provider))
        if self._intent is None:
            from answrank.finance.payments import (PaymentResult, PaymentStatus)
            return PaymentResult("PAY-00007", PaymentStatus.PENDING, None, None,
                                 "Niyet yaratıldı (MANUAL) — ödeme alınmadı")
        return self._intent

    def confirm_manual(self, intent_id, proof):
        self.calls.append(("confirm_manual", intent_id, proof))
        if self._confirm_raises:
            raise RuntimeError("kanıt geçersiz")
        if self._confirm is None:
            from answrank.finance.payments import (PaymentResult, PaymentStatus)
            from answrank.finance.tax_ledger import TaxRegime
            return PaymentResult(intent_id, PaymentStatus.SUCCEEDED, "UNPUMP-INV-0001",
                                 TaxRegime.EXPORT_SERVICE, "Fatura kesildi: UNPUMP-INV-0001")
        return self._confirm

    def handle_webhook(self, provider, body, signature, event_id):
        self.calls.append(("handle_webhook", provider, body, signature, event_id))
        if self._webhook is None:
            from answrank.finance.payments import PaymentResult, PaymentStatus
            return PaymentResult("PAY-00007", PaymentStatus.SUCCEEDED, None, None,
                                 "Olay işlendi")
        return self._webhook

    def refund(self, intent_id, reason):
        self.calls.append(("refund", intent_id, reason))
        if self._refund is None:
            from answrank.finance.payments import PaymentResult, PaymentStatus
            return PaymentResult(intent_id, PaymentStatus.REFUNDED, "UNPUMP-INV-0001",
                                 None, "İade işlendi — fatura ters kayıtla kapatıldı")
        return self._refund


@pytest.fixture
def pay_svc(monkeypatch):
    """run_payments_command'ın import ettiği PaymentService'i fake ile değiştirir."""
    import answrank.finance.payments as pay_mod

    def _install(**kw):
        svc = FakePaymentService(**kw)
        # import "from answrank.finance.payments import PaymentService" hedefine takılır
        monkeypatch.setattr(pay_mod, "PaymentService",
                            lambda *a, **k: svc)
        return svc

    return _install


def test_payments_status_lists_all_providers_honestly(pay_svc, monkeypatch):
    """status: 4 kanal da listelenir; PSP'li 3 kanal 'YAPILANDIRILMAMIŞ' der."""
    svc = pay_svc()
    buf = _capture(monkeypatch)
    monkeypatch.delenv("ANSWRANK_MANUAL_IBAN", raising=False)

    cli_mod.run_payments_command(_args(pay_cmd="status"))

    out = _flat(buf)
    for prov in ("PAYTR", "IYZICO", "PADDLE", "MANUAL"):
        assert prov in out
    assert out.count("YAPILANDIRILMAMIŞ") >= 3
    # Bu bir "durust durum" panelidir; sahte hazirlik yok
    assert "IBAN YOK" in out


def test_payments_collect_missing_field_is_refused(pay_svc, monkeypatch):
    """collect: --country eksikse niyet uydurulmaz, hata verilir."""
    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="collect", brand="Klinik", country=None,
        currency="TRY", amount=1000.0, contract_ref="SC-1"))

    assert "gerekli" in _flat(buf)
    assert not any(c[0] == "create_intent" for c in svc.calls)


def test_payments_collect_negative_amount_blocked(pay_svc, monkeypatch):
    """collect: negatif tutar niyet üretmez (PaymentError dalı)."""
    from answrank.finance.payments import PaymentError
    svc = pay_svc(raise_on={"create_intent":
                            PaymentError("Tutar pozitif olmalı: -100")})
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="collect", brand="Klinik", country="TR",
        currency="TRY", amount=-100.0, contract_ref="SC-1"))

    out = _flat(buf)
    assert "Tutar pozitif olmalı" in out
    assert not any(c[0] == "create_intent" for c in svc.calls)


def test_payments_collect_success_prints_pending_intent(pay_svc, monkeypatch):
    """collect: geçerli MANUAL niyet PENDING kalır; asla SUCCEEDED basılmaz."""
    from answrank.finance.payments import PaymentResult, PaymentStatus
    svc = pay_svc(intent=PaymentResult("PAY-00021", PaymentStatus.PENDING, None, None,
                                       "Niyet yaratıldı (MANUAL) — ödeme alınmadı"))
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="collect", brand="Royal", country="AE",
        currency="AED", amount=5500.0, contract_ref="SC-7"))

    out = _flat(buf)
    assert "PAY-00021" in out
    assert "5500" in out
    # onay komutu için yönlendirme var
    assert "payments confirm" in out
    # kanıt girilmeden ödendi yok
    assert "SUCCEEDED" not in out


def test_payments_confirm_without_proof_refused(pay_svc, monkeypatch):
    """confirm: --proof yoksa kanıtsız onay yapılmaz."""
    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="confirm", intent_id="PAY-00007", proof=None))

    assert "gerekli" in _flat(buf)
    assert not any(c[0] == "confirm_manual" for c in svc.calls)


def test_payments_confirm_success_shows_invoice_and_regime(pay_svc, monkeypatch):
    """confirm: dekontla onay → fatura + rejim gösterilir (gerçekleşme dalı)."""
    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="confirm", intent_id="PAY-00007", proof="DEKONT-2026-77"))

    out = _flat(buf)
    assert "PAY-00007" in out
    assert "UNPUMP-INV-0001" in out
    assert "EXPORT_SERVICE" in out
    assert [c for c in svc.calls if c[0] == "confirm_manual"][0][2] == "DEKONT-2026-77"


def test_payments_confirm_exception_surfaced(pay_svc, monkeypatch):
    """confirm: servis hatası ekrana gelir; sessiz başarı yok."""
    svc = pay_svc(confirm_raises=True)
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="confirm", intent_id="PAY-00007", proof="D"))

    assert "kanıt geçersiz" in _flat(buf)


def test_payments_webhook_missing_args_refused(pay_svc, monkeypatch):
    """webhook: --file/--signature/--event-id eksikse olay işlenmez."""
    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="webhook", file=None, signature=None, event_id=None))

    assert "gerekli" in _flat(buf)
    assert not any(c[0] == "handle_webhook" for c in svc.calls)


def test_payments_webhook_reads_file_body(pay_svc, monkeypatch, tmp_path):
    """webhook: dosyadaki gövde byte byte okunup imza ile iletilir."""
    import hmac
    import hashlib

    body = json.dumps({"intent_id": "PAY-00007", "status": "SUCCEEDED"}).encode()
    sig = hmac.new(b"SECRET", body, hashlib.sha256).hexdigest()
    f = tmp_path / "evt.json"
    f.write_bytes(body)

    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="webhook", file=str(f), signature=sig, event_id="EVT-KRITIK"))

    wh = [c for c in svc.calls if c[0] == "handle_webhook"]
    assert len(wh) == 1
    assert wh[0][2] == body  # gövde aynen iletildi
    assert wh[0][3] == sig
    assert wh[0][4] == "EVT-KRITIK"


def test_payments_refund_requires_reason(pay_svc, monkeypatch):
    """refund: sebep yoksa iade yapılmaz (denetim izi kuralı)."""
    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="refund", intent_id="PAY-00007", reason=None))

    assert "gerekli" in _flat(buf)
    assert not any(c[0] == "refund" for c in svc.calls)


def test_payments_refund_success_keeps_credit_note(pay_svc, monkeypatch):
    """refund: iade credit-note ile ters kayıt olur; fatura silinmez."""
    svc = pay_svc()
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="refund", intent_id="PAY-00007", reason="İptal talebi"))

    out = _flat(buf)
    assert "PAY-00007" in out
    assert "credit note" in out
    assert [c for c in svc.calls if c[0] == "refund"][0][2] == "İptal talebi"


def test_payments_refund_exception_surfaced(pay_svc, monkeypatch):
    """refund: hata dalı ekrana gelir (ör. başarı durumunda olmayan niyet)."""
    svc = pay_svc(refund=None)
    svc._refund = None
    # refund'u hata fırlatan bir fake olarak yeniden kur
    def _raise(intent_id, reason):
        raise RuntimeError("başarı durumunda değil (PENDING) — iade edilmez")

    class _S(FakePaymentService):
        def refund(self, intent_id, reason):
            self.calls.append(("refund", intent_id, reason))
            raise RuntimeError("başarı durumunda değil — iade edilmez")

    import answrank.finance.payments as pay_mod
    svc2 = _S()
    monkeypatch.setattr(pay_mod, "PaymentService", lambda *a, **k: svc2)
    buf = _capture(monkeypatch)

    cli_mod.run_payments_command(_args(
        pay_cmd="refund", intent_id="PAY-00009", reason="x"))

    assert "iade edilmez" in _flat(buf)


# ═══════════════════════════════════════════════════════════════════════════════
# 2) run_audit_command — denetim + 360° derin panel + rapor dışa-aktarım
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def audit_engine(monkeypatch):
    """AuditEngine.audit_url / audit_url_deep ve Database.save_audit'ı mock'lar."""
    from unittest.mock import AsyncMock
    from answrank.audit.engine import AuditEngine
    from answrank.db import Database

    saved = []
    monkeypatch.setattr(AuditEngine, "audit_url", AsyncMock())
    monkeypatch.setattr(AuditEngine, "audit_url_deep", AsyncMock())
    monkeypatch.setattr(Database, "save_audit", AsyncMock(side_effect=saved.append))

    def _set_url(audit):
        AuditEngine.audit_url.return_value = audit
        return audit

    def _set_deep(deep):
        AuditEngine.audit_url_deep.return_value = deep
        return deep

    return _set_url, _set_deep, saved


def test_audit_standard_renders_score_and_persists(audit_engine, monkeypatch):
    """standart denetim: skor paneli + 8 kategori tablosu; DB'ye yazılır."""
    set_url, _, saved = audit_engine
    audit = set_url(_make_audit(overall=84, lost=125000.0))
    buf = _capture(monkeypatch)

    cli_mod.run_audit_command(_args(
        url="https://kritik.example", sector="dental", deep=False,
        brand=None, format="text", out=None))

    out = _flat(buf)
    assert "kritik.example" in out
    assert "84/100" in out
    assert "125,000 TL" in out  # kaçan ciro basılır
    assert "Robots.txt AI Erişimi" in out  # kategori tablosu
    assert saved == [audit]  # kalıcılaştırıldı


def test_audit_unmeasured_revenue_never_fabricated(audit_engine, monkeypatch):
    """lost_revenue None → 'ÖLÇÜLEMEDİ' yazılır; sayı uydurulmaz."""
    set_url, _, _ = audit_engine
    set_url(_make_audit(overall=30, lost=None))
    buf = _capture(monkeypatch)

    cli_mod.run_audit_command(_args(
        url="https://olculemedi.example", sector="dental", deep=False,
        brand=None, format="text", out=None))

    out = _flat(buf)
    assert "ÖLÇÜLEMEDİ" in out
    assert "TL" not in out.replace("ÖLÇÜLEMEDİ", "")


def test_audit_deep_waf_blocked_bots_panel(audit_engine, monkeypatch):
    """deep: WAF bot engeli tespit edilirse 'Bot Engelli' paneli basılır."""
    set_url, set_deep, _ = audit_engine
    audit = _make_audit()
    set_url(audit)
    set_deep(_make_deep(audit, waf={"blocked_bots_count": 2, "total_probed": 9,
                                    "accessible_bots_count": 7},
                        adversarial={"threat_level": "HIGH"},
                        entity={"has_wikidata": True, "wikidata_qid": "Q1",
                                "qid_confidence": "verified"},
                        rag={"rag_retrieval_score": 61.0},
                        composite=55.0, tier="STABLE"))
    buf = _capture(monkeypatch)

    cli_mod.run_audit_command(_args(
        url="https://waf.example", sector="dental", deep=True,
        brand="WAF Test", format="text", out=None))

    out = _flat(buf)
    assert "2 Bot Engelli" in out
    assert "HIGH" in out  # adversarial tehdit
    assert "STABLE" in out
    assert "%61" in out  # RAG uygunluk


def test_audit_deep_waf_unverifiable_is_honest(audit_engine, monkeypatch):
    """deep: WAF sorgulanamadıysa 'HÜKÜM VERİLEMEDİ' yazılır (ölçüm-kapısı)."""
    set_url, set_deep, _ = audit_engine
    audit = _make_audit()
    set_url(audit)
    set_deep(_make_deep(audit, waf={"overall_risk": "UNVERIFIED",
                                    "unreachable_bots_count": 3,
                                    "total_probed": 9}))
    buf = _capture(monkeypatch)

    cli_mod.run_audit_command(_args(
        url="https://u.example", sector="dental", deep=True,
        brand=None, format="text", out=None))

    assert "HÜKÜM VERİLEMEDİ" in _flat(buf)


def test_audit_deep_waf_clean_panel(audit_engine, monkeypatch):
    """deep: engel yoksa 'Temiz'面板 basılır."""
    set_url, set_deep, _ = audit_engine
    audit = _make_audit()
    set_url(audit)
    set_deep(_make_deep(audit, waf={"blocked_bots_count": 0, "total_probed": 9,
                                    "accessible_bots_count": 9}))
    buf = _capture(monkeypatch)

    cli_mod.run_audit_command(_args(
        url="https://temiz.example", sector="dental", deep=True,
        brand=None, format="text", out=None))

    out = _flat(buf)
    assert "Temiz" in out
    assert "9/9" in out


def test_audit_deep_entity_grounding_all_status_branches(audit_engine, monkeypatch):
    """deep: entity grounding'in 6 durum dalı da doğru etiket basar."""
    set_url, set_deep, _ = audit_engine
    audit = _make_audit()
    set_url(audit)

    cases = [
        ({"wikidata_probe_status": "unreachable"}, "SORGULANAMADI"),
        ({"has_wikidata": False}, "KAYIT YOK"),
        ({"has_wikidata": True, "wikidata_qid": "Q42",
          "qid_confidence": "verified"}, "TEYİTLİ"),
        ({"has_wikidata": True, "wikidata_qid": "Q43",
          "qid_confidence": "rejected"}, "REDDEDİLDİ"),
        ({"has_wikidata": True, "wikidata_qid": "Q44",
          "qid_confidence": "exact_name_no_conflict"}, "birebir etiket"),
        ({"has_wikidata": True, "wikidata_qid": "Q45",
          "qid_confidence": "unverified"}, "resmî site teyidi eksik"),
    ]
    for ent, expected in cases:
        set_deep(_make_deep(audit, entity=ent))
        buf = _capture(monkeypatch)
        cli_mod.run_audit_command(_args(
            url="https://e.example", sector="dental", deep=True,
            brand=None, format="text", out=None))
        assert expected in _flat(buf), f"entity dalı '{expected}' basılmadı"


def test_audit_deep_no_subsystems_falls_back(audit_engine, monkeypatch):
    """deep: tüm alt sistemler None ise 'PROBE EDİLMEDİ' / 'TARANMADI' düşer."""
    set_url, set_deep, _ = audit_engine
    audit = _make_audit()
    set_url(audit)
    set_deep(_make_deep(audit))  # waf/adversarial/entity/rag hepsi None
    buf = _capture(monkeypatch)

    cli_mod.run_audit_command(_args(
        url="https://none.example", sector="dental", deep=True,
        brand=None, format="text", out=None))

    out = _flat(buf)
    assert "PROBE EDİLMEDİ" in out
    assert "TARANMADI" in out


def test_audit_export_html_md_json(audit_engine, monkeypatch, tmp_path):
    """--format html/md/json raporu --out yoluna yazar (3 dal)."""
    set_url, _, _ = audit_engine
    set_url(_make_audit())
    _capture(monkeypatch)

    for fmt, marker in (("html", "<!DOCTYPE html>"), ("md", "# "), ("json", "{")):
        out = tmp_path / f"rapor.{fmt}"
        cli_mod.run_audit_command(_args(
            url="https://ex.example", sector="dental", deep=False,
            brand=None, format=fmt, out=str(out)))
        assert out.exists()
        assert out.read_text(encoding="utf-8").lstrip().startswith(marker), fmt


def test_audit_default_out_path_derived_from_domain(audit_engine, monkeypatch, tmp_path):
    """--out yoksa dosya adı domain'den türetilir."""
    set_url, _, _ = audit_engine
    set_url(_make_audit())
    _capture(monkeypatch)

    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        cli_mod.run_audit_command(_args(
            url="https://sub.klinik.example", sector="dental", deep=False,
            brand=None, format="json", out=None))
    finally:
        os.chdir(cwd)

    expected = tmp_path / "report_kritik_example.json"
    assert expected.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# 3) run_crm_command — DM onay-kapısı; onaysız gönderim yok
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def crm_env(monkeypatch, tmp_path):
    """CRMSync / AuditEngine / DMSender / Database ağ ve IO çağrılarını izole eder."""
    from unittest.mock import AsyncMock, MagicMock
    from answrank.crm.sync import CRMSync
    from answrank.audit.engine import AuditEngine
    from answrank.crm import dm_sender as dm_mod

    monkeypatch.setattr(CRMSync, "import_csv_to_db", AsyncMock(return_value=7))
    monkeypatch.setattr(CRMSync, "list_prospects", AsyncMock(return_value=[
        {"id": "1", "brand_name": "Klinik A", "sector": "dental",
         "platform": "web", "status": "PENDING"}]))
    monkeypatch.setattr(AuditEngine, "audit_url", AsyncMock())

    leads_holder = {"rows": []}
    db = MagicMock()
    db.list_miniprobe_leads.return_value = leads_holder["rows"]
    db.latest_measured_lead.return_value = None
    db.get_latest_citations_for_domain.return_value = None
    # crm send dalı için onay satırı sorgusu
    db._get_connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
    # run_crm_command içi 'from answrank.db import Database' ile alındığı için
    # modül kaynağından patch'liyoruz (cli_mod.Database yetmez)
    import answrank.db as db_mod
    monkeypatch.setattr(db_mod, "Database", lambda *a, **k: db)
    monkeypatch.setattr(cli_mod, "Database", lambda *a, **k: db)

    send_results = []
    sender = MagicMock()
    sender.send.side_effect = lambda **kw: send_results.append(kw) or _send_result("GÖNDERİLDİ")
    monkeypatch.setattr(dm_mod, "DMSender", lambda *a, **k: sender)

    return {
        "db": db, "sender": sender, "send_results": send_results,
        "leads_holder": leads_holder,
    }


def _send_result(status):
    from answrank.crm.dm_sender import SendResult
    return SendResult(queue_id=1, domain="k.example", recipient="info@k.example",
                      channel="smtp", status=status, note="test sonucu")


def test_crm_sync_imports_and_reports_count(crm_env, monkeypatch):
    """sync: CSV'den içe aktarılan adet dürüstçe raporlanır."""
    buf = _capture(monkeypatch)
    cli_mod.run_crm_command(_args(crm_action="sync", domain=None, sector="dental",
                                  contact=None, from_lead=None, with_visibility=False,
                                  body=None, subject=None, variant=None))
    assert "7 potansiyel müşteri" in _flat(buf)


def test_crm_list_renders_prospect_table(crm_env, monkeypatch):
    """list: aday tablosu gerçek DB satırlarıyla basılır."""
    buf = _capture(monkeypatch)
    cli_mod.run_crm_command(_args(crm_action="list", domain=None, sector="dental",
                                  contact=None, from_lead=None, with_visibility=False,
                                  body=None, subject=None, variant=None))
    out = _flat(buf)
    assert "Klinik A" in out
    assert "dental" in out


def test_crm_leads_empty_does_not_invent(crm_env, monkeypatch):
    """leads: mini-probe yoksa 'yok' yazılır; huni uydurulmaz."""
    buf = _capture(monkeypatch)
    cli_mod.run_crm_command(_args(crm_action="leads", domain=None, sector="dental",
                                  contact=None, from_lead=None, with_visibility=False,
                                  body=None, subject=None, variant=None))
    assert "Mini-probe lead'i yok" in _flat(buf)


def test_crm_leads_rows_rendered(crm_env, monkeypatch):
    """leads: ölçülmüş lead satırları domain+verdict ile basılır."""
    crm_env["db"].list_miniprobe_leads.return_value = [
        {"created_at": "2026-10-06T10:00:00", "domain": "olculu.example",
         "verdict": "TEMİZ", "bots_line": "3/3"}]
    buf = _capture(monkeypatch)
    cli_mod.run_crm_command(_args(crm_action="leads", domain=None, sector="dental",
                                  contact=None, from_lead=None, with_visibility=False,
                                  body=None, subject=None, variant=None))
    out = _flat(buf)
    assert "olculu.example" in out
    assert "TEMİZ" in out


def test_crm_draft_from_lead_without_measurement_refused(crm_env, monkeypatch):
    """draft --from-lead: ölçümlü lead yoksa DM üretilmez (C3 kuralı)."""
    buf = _capture(monkeypatch)
    cli_mod.run_crm_command(_args(
        crm_action="draft", domain=None, sector="dental", contact=None,
        from_lead="yok.example", with_visibility=False,
        body=None, subject=None, variant=None))
    assert "ÖLÇÜMLÜ mini-probe lead'i yok" in _flat(buf)


def test_crm_draft_from_lead_renders_dm(crm_env, monkeypatch):
    """draft --from-lead: ölçümlü lead varsa gerçek DM metni basılır."""
    from answrank.crm.outreach import OutreachGenerator
    from unittest.mock import patch

    crm_env["db"].latest_measured_lead.return_value = {
        "domain": "olculu.example", "robots_line": "İZİNLİ",
        "llms_line": "VAR", "bots_line": "3/3", "verdict": "TEMİZ"}
    buf = _capture(monkeypatch)

    with patch.object(OutreachGenerator, "lead_dm", return_value="DM GÖVDESİ ÖLÇÜMDEN"):
        cli_mod.run_crm_command(_args(
            crm_action="draft", domain=None, sector="dental", contact=None,
            from_lead="olculu.example", with_visibility=False,
            body=None, subject=None, variant=None))

    assert "DM GÖVDESİ ÖLÇÜMDEN" in _flat(buf)


def test_crm_draft_without_approval_never_sends(crm_env, monkeypatch):
    """send: APPROVED kuyruk maddesi yoksa DM gönderilmez (onay-kapısı)."""
    buf = _capture(monkeypatch)
    cli_mod.run_crm_command(_args(
        crm_action="send", domain="onaysiz.example", sector="dental",
        contact=None, from_lead=None, with_visibility=False,
        body=None, subject=None, variant=None))

    out = _flat(buf)
    assert "APPROVED kuyruk maddesi YOK" in out
    assert "onaysız DM gönderilmez" in out
    assert crm_env["send_results"] == []  # hiç gönderim yapılmadı


def test_crm_send_with_approval_dispatches(crm_env, monkeypatch):
    """send: APPROVED satırı varsa DMSender tetiklenir; durum etiketi basılır."""
    from unittest.mock import MagicMock

    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (42,)
    crm_env["db"]._get_connection.return_value.__enter__.return_value = conn
    buf = _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="send", domain="onayli.example", sector="dental",
        contact=None, from_lead=None, with_visibility=False,
        body="Merhaba", subject="Konu", variant="variant_1_pain_numbers"))

    assert crm_env["send_results"], "gönderim tetiklenmedi"
    kw = crm_env["send_results"][0]
    assert kw["queue_id"] == 42
    assert kw["domain"] == "onayli.example"
    assert kw["body"] == "Merhaba"
    assert "GÖNDERİLDİ" in _flat(buf)


def test_crm_send_custom_body_used(crm_env, monkeypatch):
    """send: --body verilirse o metin gider; varsayılan uydurma metin değil."""
    from unittest.mock import MagicMock

    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (7,)
    crm_env["db"]._get_connection.return_value.__enter__.return_value = conn
    _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="send", domain="d.example", sector="dental",
        contact=None, from_lead=None, with_visibility=False,
        body="ÖZEL GÖVDE", subject="Başlık", variant="v2"))

    assert crm_env["send_results"][0]["body"] == "ÖZEL GÖVDE"
    assert crm_env["send_results"][0]["subject"] == "Başlık"


def test_crm_followups_none_due_is_honest(crm_env, monkeypatch):
    """followups: vadesi gelen takip yoksa 'yok' yazılır."""
    from answrank.crm import dm_sender as dm_mod
    from unittest.mock import MagicMock

    sender = MagicMock()
    sender.followups_due.return_value = []
    monkeypatch.setattr(dm_mod, "DMSender", lambda *a, **k: sender)
    buf = _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="followups", domain=None, sector="dental", contact=None,
        from_lead=None, with_visibility=False,
        body=None, subject=None, variant=None))

    assert "Vadesi gelen takip yok" in _flat(buf)


def test_crm_followups_due_listed_and_generated(crm_env, monkeypatch):
    """followups: vadesi gelenler listelenir; .eml sayısı raporlanır."""
    from answrank.crm import dm_sender as dm_mod
    from unittest.mock import MagicMock

    sender = MagicMock()
    sender.followups_due.return_value = [
        {"domain": "f.example", "gun": 3, "key": "d3"}]
    sender.generate_followups.return_value = [_send_result("YAPILANDIRILMAMIŞ")]
    monkeypatch.setattr(dm_mod, "DMSender", lambda *a, **k: sender)
    buf = _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="followups", domain=None, sector="dental", contact=None,
        from_lead=None, with_visibility=False,
        body=None, subject=None, variant=None))

    out = _flat(buf)
    assert "1 vadesi-gelen takip" in out
    assert "f.example" in out
    assert "1 takip" in out


def test_crm_outbox_empty_is_honest(crm_env, monkeypatch, tmp_path):
    """outbox: hazır .eml yoksa 'boş' yazılır."""
    from answrank.crm import dm_sender as dm_mod
    from pathlib import Path

    monkeypatch.setattr(dm_mod, "OUTBOX_DIR", tmp_path / "bos_outbox")
    buf = _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="outbox", domain=None, sector="dental", contact=None,
        from_lead=None, with_visibility=False,
        body=None, subject=None, variant=None))

    assert "outbox/ boş" in _flat(buf)


def test_crm_outbox_lists_eml_files(crm_env, monkeypatch, tmp_path):
    """outbox: hazır .eml dosyaları listelenir."""
    from answrank.crm import dm_sender as dm_mod

    d = tmp_path / "outbox2"
    d.mkdir()
    (d / "dm_1_v1_x.example.eml").write_text("test", encoding="utf-8")
    monkeypatch.setattr(dm_mod, "OUTBOX_DIR", d)
    buf = _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="outbox", domain=None, sector="dental", contact=None,
        from_lead=None, with_visibility=False,
        body=None, subject=None, variant=None))

    out = _flat(buf)
    assert "dm_1_v1_x.example.eml" in out
    assert "1 hazır .eml" in out


def test_crm_draft_live_audit_failure_refused(crm_env, monkeypatch):
    """draft (from-lead'siz): canlı denetim başarısızsa DM üretilmez."""
    from answrank.audit.engine import AuditEngine
    from unittest.mock import AsyncMock

    AuditEngine.audit_url = AsyncMock(side_effect=RuntimeError("bağlantı reddedildi"))
    buf = _capture(monkeypatch)

    cli_mod.run_crm_command(_args(
        crm_action="draft", domain="hata.example", sector="dental",
        contact=None, from_lead=None, with_visibility=False,
        body=None, subject=None, variant=None))

    out = _flat(buf)
    assert "denetlenemedi" in out
    assert "ölçülemeyen müşteriye taslak DM üretilmez" in out


def test_crm_draft_from_lead_with_visibility_no_measurement(crm_env, monkeypatch):
    """draft --from-lead --with-visibility: geçerli ölçüm yoksa taslak üretilmez."""
    from answrank.citations.runner import MultiLLMCitationRunner
    from answrank.crm.outreach import OutreachGenerator
    from unittest.mock import patch

    crm_env["db"].latest_measured_lead.return_value = {
        "domain": "v.example", "robots_line": "İ", "llms_line": "V",
        "bots_line": "3/3", "verdict": "TEMİZ"}

    from unittest.mock import MagicMock as _MM
    monkeypatch.setattr(MultiLLMCitationRunner, "visibility_for",
                        _MM(return_value=None))
    buf = _capture(monkeypatch)

    with patch.object(OutreachGenerator, "lead_dm", return_value="ASLA BASILMAMALI"):
        cli_mod.run_crm_command(_args(
            crm_action="draft", domain=None, sector="dental", contact=None,
            from_lead="v.example", with_visibility=True,
            body=None, subject=None, variant=None))

    assert "Geçerli son AI-görünürlük kanıtı yok" in _flat(buf)
    assert "ASLA BASILMAMALI" not in _flat(buf)


# ═══════════════════════════════════════════════════════════════════════════════
# 4) run_queue_command — insan-onay kuyruğu + auto-approve denetimi
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def queue_env(monkeypatch):
    """ApprovalQueue / DmGateAuditor / DmDispatcher'ı izole eder."""
    from unittest.mock import MagicMock
    from answrank.queue import ApprovalQueue
    from answrank.queue_gates import DmGateAuditor
    from answrank.dm_dispatch import DmDispatcher

    q = MagicMock()
    q.scan.return_value = 3
    q.pending.return_value = [
        {"id": 11, "kind": "DM", "ref_id": "k1.example", "summary": "DM özeti"},
        {"id": 12, "kind": "CONTRACT", "ref_id": "k2.example", "summary": "Sözleşme"},
    ]
    q.decide.return_value = {"id": 11, "kind": "DM", "ref_id": "k1.example",
                             "status": "APPROVED", "decision_note": "uygun"}

    def _echo_decision(item_id, approve=True, note=""):
        return {"id": item_id, "kind": "DM", "ref_id": "k1.example",
                "status": "APPROVED" if approve else "REJECTED",
                "decision_note": note}

    q.decide.side_effect = _echo_decision
    monkeypatch.setattr("answrank.queue.ApprovalQueue", lambda *a, **k: q)

    auditor = MagicMock()
    auditor.audit_pending.return_value = []
    auditor.auto_approve.return_value = {
        "dry_run": True, "auto_approved": [{"id": 11, "domain": "k1.example"}],
        "still_pending": [{"id": 12, "domain": "k2.example", "why": "ölçüm yok"}],
        "conflicts": []}
    monkeypatch.setattr("answrank.queue_gates.DmGateAuditor", lambda *a, **k: auditor)

    send_holder = {"out": None}
    dispatcher = MagicMock()

    def _send(item_id, dry_run=False):
        send_holder["out"] = {"item_id": item_id,
                              "result": "GÖNDERİLDİ" if not dry_run else "DRY-RUN",
                              "to": "info@k1.example", "why": "SMTP yolu"}
        return send_holder["out"]

    dispatcher.send_approved.side_effect = _send
    monkeypatch.setattr("answrank.dm_dispatch.DmDispatcher", lambda *a, **k: dispatcher)

    return {"q": q, "auditor": auditor, "dispatcher": dispatcher,
            "send_holder": send_holder}


def test_queue_scan_reports_new_items(queue_env, monkeypatch):
    """scan: yeni madde sayısı + toplam bekleyen dürüstçe raporlanır."""
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="scan", item_id=None, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    out = _flat(buf)
    assert "3 yeni karar maddesi" in out
    assert "2" in out  # toplam bekleyen


def test_queue_list_renders_pending(queue_env, monkeypatch):
    """list: bekleyen maddeler tür+referans ile listelenir."""
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="list", item_id=None, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    out = _flat(buf)
    assert "DM" in out
    assert "k1.example" in out
    assert "İnsan-Onay Kuyruğu" in out


def test_queue_list_empty_does_not_invent(queue_env, monkeypatch):
    """list: boş kuyrukta 'Kuyruk boş' yazılır; iş uydurulmaz."""
    queue_env["q"].pending.return_value = []
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="list", item_id=None, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    out = _flat(buf)
    assert "Kuyruk boş" in out
    assert "iş uydurulmaz" in out


def test_queue_send_dispatches_approved_item(queue_env, monkeypatch):
    """send: onaylı madde gönderime gider; alıcı ve neden basılır."""
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="send", item_id=11, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    out = _flat(buf)
    assert "11" in out
    assert "GÖNDERİLDİ" in out
    assert "info@k1.example" in out
    assert "SMTP yolu" in out
    queue_env["dispatcher"].send_approved.assert_called_once_with(11, dry_run=False)


def test_queue_send_dry_run_marks_output(queue_env, monkeypatch):
    """send --dry-run: sonuç etiketi dry-run yansıtır."""
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="send", item_id=11, dry_run=True,
                                    auto_approve=False, apply=False, note=""))
    assert "DRY-RUN" in _flat(buf)
    queue_env["dispatcher"].send_approved.assert_called_once_with(11, dry_run=True)


def test_queue_audit_pending_empty_is_honest(queue_env, monkeypatch):
    """audit: PENDING DM yoksa 'denetilecek bir şey yok' yazılır."""
    queue_env["auditor"].audit_pending.return_value = []
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="audit", item_id=None, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    assert "denetilecek bir şey yok" in _flat(buf)


def test_queue_audit_renders_gate_results(queue_env, monkeypatch):
    """audit: her madde için 6 kapı sonucu ve nedenleri basılır."""
    queue_env["auditor"].audit_pending.return_value = [
        {"id": 11, "domain": "k1.example", "all_passed": False,
         "gates": [{"gate": "ölçüm-var", "passed": False, "reason": "kanıt yok"},
                   {"gate": "mini-probe-var", "passed": True, "reason": "hüküm: TEMİZ"}]}]
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="audit", item_id=None, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    out = _flat(buf)
    assert "KAPALI" in out
    assert "ölçüm-var" in out
    assert "kanıt yok" in out
    assert "mini-probe-var" in out


def test_queue_audit_auto_approve_dry_run_changes_nothing(queue_env, monkeypatch):
    """audit --auto-approve (apply yok): dry-run etiketi basılır; karar değişmez."""
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="audit", item_id=None, dry_run=False,
                                    auto_approve=True, apply=False, note=""))
    out = _flat(buf)
    assert "dry-run" in out
    assert "uygulanabilir" in out
    assert "k1.example" in out  # onaylanan listelendi
    assert "ölçüm yok" in out  # bekleyen nedeni
    queue_env["auditor"].auto_approve.assert_called_once_with(dry_run=True)


def test_queue_audit_auto_approve_apply_marks_applied(queue_env, monkeypatch):
    """audit --auto-approve --apply: 'UYGULANDI' etiketi basılır."""
    queue_env["auditor"].auto_approve.return_value = {
        "dry_run": False, "auto_approved": [{"id": 11, "domain": "k1.example"}],
        "still_pending": [], "conflicts": []}
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="audit", item_id=None, dry_run=False,
                                    auto_approve=True, apply=True, note=""))
    out = _flat(buf)
    assert "UYGULANDI" in out
    queue_env["auditor"].auto_approve.assert_called_once_with(dry_run=False)


def test_queue_audit_auto_approve_conflict_shown(queue_env, monkeypatch):
    """audit --auto-approve: karar çakışması '⚠' ile gösterilir."""
    queue_env["auditor"].auto_approve.return_value = {
        "dry_run": True, "auto_approved": [],
        "still_pending": [],
        "conflicts": [{"id": 13, "domain": "c.example",
                       "why": "Karar değişti; otomatik onay uygulanmadı"}]}
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="audit", item_id=None, dry_run=False,
                                    auto_approve=True, apply=False, note=""))
    out = _flat(buf)
    assert "c.example" in out
    assert "Karar değişti" in out


def test_queue_approve_writes_decision(queue_env, monkeypatch):
    """approve: insan kararı işlenir; durum + not ekrana basılır."""
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="approve", item_id=11, dry_run=False,
                                    auto_approve=False, apply=False, note="uygun görüldü"))
    out = _flat(buf)
    assert "APPROVED" in out
    assert "uygun görüldü" in out
    queue_env["q"].decide.assert_called_once_with(11, approve=True, note="uygun görüldü")


def test_queue_reject_writes_decision(queue_env, monkeypatch):
    """reject: red kararı işlenir (approve=False)."""
    queue_env["q"].decide.return_value = {"id": 12, "kind": "CONTRACT",
                                          "ref_id": "k2.example", "status": "REJECTED",
                                          "decision_note": "uygun değil"}
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="reject", item_id=12, dry_run=False,
                                    auto_approve=False, apply=False, note="uygun değil")
                             )
    out = _flat(buf)
    assert "REJECTED" in out
    queue_env["q"].decide.assert_called_once_with(12, approve=False, note="uygun değil")


def test_queue_approve_missing_item_is_refused(queue_env, monkeypatch):
    """approve: olmayan madde için 'Madde yok' yazılır; uydurma karar yok."""
    queue_env["q"].decide.side_effect = KeyError("yok")
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="approve", item_id=99999, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    out = _flat(buf)
    assert "Madde yok" in out
    assert "uydurma karar yazılmaz" in out


def test_queue_approve_invalid_transition_shows_error(queue_env, monkeypatch):
    """approve: zaten kararlı madde ValueError ile reddedilir; mesaj basılır."""
    queue_env["q"].decide.side_effect = ValueError("madde zaten kararlı")
    buf = _capture(monkeypatch)
    cli_mod.run_queue_command(_args(queue_cmd="approve", item_id=11, dry_run=False,
                                    auto_approve=False, apply=False, note=""))
    assert "madde zaten kararlı" in _flat(buf)


# ═══════════════════════════════════════════════════════════════════════════════
# 5) trigger_swarm_scout — kuratörlü demo havuzu (.example güvenlik klişesi)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def swarm_orch(monkeypatch):
    """SwarmOrchestrator'ın ağ/dış çağrılarını izole eder; ekilen adayları kaydeder."""
    from unittest.mock import MagicMock
    from answrank.agents import swarm as swarm_mod

    seeded = []
    qualified = []
    persisted = []

    cand_seq = []

    class _Cand:
        def __init__(self, brand, domain, sector, city, country, currency, ticket):
            self.brand_name = brand
            self.domain = domain
            self.sector = sector
            self.city = city
            self.country = country
            self.currency = currency
            self.ticket_size = ticket
            self.id = f"cand-{len(cand_seq) + 1}"
            cand_seq.append(self)

        def model_dump(self):
            return {"id": self.id, "brand_name": self.brand_name,
                    "domain": self.domain, "sector": self.sector, "city": self.city,
                    "country": self.country, "currency": self.currency,
                    "ticket_size": self.ticket_size}

    orch = MagicMock()

    def _seed(**kw):
        seeded.append(kw)
        return _Cand(kw["brand_name"], kw["domain"], kw.get("sector", "dental"),
                     kw.get("city", "London"), kw.get("country", "UK"),
                     kw.get("currency", "USD"), kw.get("ticket_size", 1000.0))

    orch.seed_target.side_effect = _seed
    orch.scout.qualify.side_effect = lambda c: qualified.append(c) or c
    orch.persist_candidate.side_effect = lambda c: persisted.append(c) or None
    monkeypatch.setattr(swarm_mod, "SwarmOrchestrator", lambda *a, **k: orch)

    return {"orch": orch, "seeded": seeded, "qualified": qualified,
            "persisted": persisted}


def _scout(sector="dental", city="London", country="UK"):
    from answrank.api.app import ScoutRequest
    return ScoutRequest(sector=sector, city=city, country=country)


@pytest.mark.anyio
async def test_scout_known_pool_seeds_only_example_domains(swarm_orch):
    """Bilinen (sektor, ulke) havuzu tümüyle .example domain ekler — gerçek
    işletme Probe/fatura edilemez (RFC 2606 güvenlik klişesi)."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout(sector="dental", city="Manchester",
                                           country="UK"))

    assert res["count"] == 3
    assert res["source"] == "curated_demo_pool"
    for kw in swarm_orch["seeded"]:
        assert kw["domain"].endswith(".example")
        assert kw["country"] == "UK"
        assert kw["currency"] == "GBP"
        assert kw["ticket_size"] > 0
    assert len(swarm_orch["qualified"]) == 3
    assert len(swarm_orch["persisted"]) == 3
    for c in res["candidates"]:
        assert c["domain"].endswith(".example")


@pytest.mark.anyio
async def test_scout_us_pool_uses_usd_currency(swarm_orch):
    """US havuzu USD bilet ile eklenir (rejim/para birimi tutarlılığı)."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout(sector="dental", city="Boston",
                                           country="US"))

    assert res["count"] == 2
    currencies = {kw["currency"] for kw in swarm_orch["seeded"]}
    assert currencies == {"USD"}
    for kw in swarm_orch["seeded"]:
        assert kw["ticket_size"] > 0


@pytest.mark.anyio
async def test_scout_tr_pool_uses_try_currency(swarm_orch):
    """TR havuzu TRY bilet ile eklenir; yurtiçi rejim korunur."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout(sector="dental", city="İstanbul",
                                           country="TR"))

    assert res["count"] == 3
    currencies = {kw["currency"] for kw in swarm_orch["seeded"]}
    assert currencies == {"TRY"}


@pytest.mark.anyio
async def test_scout_unknown_pool_falls_back_to_single_demo(swarm_orch):
    """Bilinmeyen (sektor, ulke) için tek kurgusal hedef üretilir; yine .example."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout(sector="legal", city="Lyon",
                                           country="FR"))

    assert res["count"] == 1
    kw = swarm_orch["seeded"][0]
    assert kw["domain"].endswith(".example")
    assert "lyon" in kw["domain"]
    assert "legal" in kw["domain"]
    assert kw["currency"] == "USD"
    assert res["source"] == "curated_demo_pool"


@pytest.mark.anyio
async def test_scout_honest_scope_label_in_response(swarm_orch):
    """Yanıt 'curated_demo_pool' etiketini taşır — canlı keşif gibi sunulmaz."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout())

    assert res["source"] == "curated_demo_pool"
    assert "Küratörlü demo hedef havuzu" in res["note"]
    assert ".example" in res["note"] or "kurgusaldır" in res["note"]


@pytest.mark.anyio
async def test_scout_aesthetic_pool_seeds(swarm_orch):
    """aesthetic/TR havuzu da .example ile eklenir (sektör çeşitliliği dalı)."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout(sector="aesthetic", city="Ankara",
                                           country="TR"))

    assert res["count"] == 2
    for kw in swarm_orch["seeded"]:
        assert kw["domain"].endswith(".example")
        assert kw["currency"] == "TRY"


@pytest.mark.anyio
async def test_scout_de_pool_uses_eur(swarm_orch):
    """DE havuzu EUR bilet ile eklenir (EU para birimi dalı)."""
    from answrank.api.app import trigger_swarm_scout

    res = await trigger_swarm_scout(_scout(sector="dental", city="Berlin",
                                           country="DE"))

    assert res["count"] == 2
    currencies = {kw["currency"] for kw in swarm_orch["seeded"]}
    assert currencies == {"EUR"}
