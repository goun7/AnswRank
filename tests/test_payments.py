"""E11 ödeme/tahsilat entegrasyonu testleri.

PSP anlaşmamız yok — bu testlerin TÜMÜ sahte PSP yanıtı ÜRETMEZ;
niyet/manual-onay/imza-doğrulama/rejim/idempotens/iaade yollarını
gerçek DB ve gerçek TaxLedger ile ölçer.
"""
import hashlib
import hmac
import json

import pytest

from answrank.config import settings
from answrank.db import Database
from answrank.finance.payments import (PaymentError, PaymentProvider,
                                       PaymentRequest, PaymentService,
                                       PaymentStatus)
from answrank.finance.tax_ledger import TaxLedger


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("ANSWRANK_DB_PATH", str(tmp_path / "pay.db"))
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "pay.db"))
    ledger = TaxLedger(custom_rates={"USD": 35.0, "EUR": 38.0, "AED": 9.6,
                                      "GBP": 46.0, "TRY": 1.0},
                       load_persisted=False)
    return PaymentService(db=Database(), ledger=ledger)


def _req(country="AE", currency="AED", amount=5500.0):
    return PaymentRequest(contract_ref="SC-001", brand="Test Klinik",
                          country=country, currency=currency, amount=amount)


# --- 1) PSP'siz durum dürüst ---------------------------------------------

def test_psp_unconfigured_is_honest(svc, monkeypatch):
    for env in ("ANSWRANK_PAYTR_MERCHANT_ID", "ANSWRANK_PAYTR_API_KEY",
                "ANSWRANK_IYZICO_API_KEY", "ANSWRANK_IYZICO_SECRET",
                "ANSWRANK_PADDLE_VENDOR", "ANSWRANK_PADDLE_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    assert "YAPILANDIRILMAMIŞ" in svc.provider_status(PaymentProvider.PAYTR)
    assert "YAPILANDIRILMAMIŞ" in svc.provider_status(PaymentProvider.IYZICO)
    assert "YAPILANDIRILMAMIŞ" in svc.provider_status(PaymentProvider.PADDLE)


def test_unconfigured_psp_never_succeeds(svc, monkeypatch):
    monkeypatch.delenv("ANSWRANK_PAYTR_MERCHANT_ID", raising=False)
    with pytest.raises(PaymentError) as exc:
        svc.create_intent(_req(), PaymentProvider.PAYTR)
    assert "sahte başarılı ödeme üretilmez" in str(exc.value)


def test_manual_without_iban_is_honest(svc, monkeypatch):
    monkeypatch.delenv("ANSWRANK_MANUAL_IBAN", raising=False)
    assert "IBAN YOK" in svc.provider_status(PaymentProvider.MANUAL)


# --- 2) niyet + rejim ------------------------------------------------------

def test_manual_intent_pending_not_succeeded(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00 0001 2345")
    res = svc.create_intent(_req(), PaymentProvider.MANUAL)
    assert res.status == PaymentStatus.PENDING
    assert "ödeme alınmadı" in res.note


def test_export_regime_zero_vat_full_deduction(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(country="AE", currency="AED"), PaymentProvider.MANUAL)
    res = svc.confirm_manual(intent.intent_id, "DEKONT-2026-001")
    assert res.status == PaymentStatus.SUCCEEDED
    assert res.regime is not None and res.regime.value.startswith("EXPORT")
    assert res.invoice_id


def test_domestic_regime_20pct_vat(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(country="TR", currency="TRY", amount=6000.0),
                               PaymentProvider.MANUAL)
    res = svc.confirm_manual(intent.intent_id, "DEKONT-TR-001")
    assert res.status == PaymentStatus.SUCCEEDED
    assert res.regime is not None and res.regime.value.startswith("DOMESTIC")


def test_missing_country_refuses_verdict(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    with pytest.raises(PaymentError) as exc:
        svc.create_intent(_req(country=""), PaymentProvider.MANUAL)
    assert "rejim" in str(exc.value).lower()


def test_manual_confirm_requires_bank_proof(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    with pytest.raises(PaymentError) as exc:
        svc.confirm_manual(intent.intent_id, "")
    assert "kanıtsız onay" in str(exc.value)


# --- 3) webhook imza + idempotens -----------------------------------------

def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_webhook_bad_signature_rejected(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_PAYTR_MERCHANT_ID", "M1")
    monkeypatch.setenv("ANSWRANK_PAYTR_API_KEY", "SECRET")
    body = json.dumps({"intent_id": "PAY-00001", "status": "SUCCEEDED"}).encode()
    with pytest.raises(PaymentError) as exc:
        svc.handle_webhook(PaymentProvider.PAYTR, body, "0" * 64, "EVT-1")
    assert "imza doğrulanamadı" in str(exc.value)


def test_webhook_double_delivery_no_double_invoice(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_PAYTR_MERCHANT_ID", "M1")
    monkeypatch.setenv("ANSWRANK_PAYTR_API_KEY", "SECRET")
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    body = json.dumps({"intent_id": intent.intent_id,
                       "status": "SUCCEEDED"}).encode()
    sig = _sign("SECRET", body)
    first = svc.handle_webhook(PaymentProvider.PAYTR, body, sig, "EVT-DUP")
    assert first.status == PaymentStatus.SUCCEEDED
    second = svc.handle_webhook(PaymentProvider.PAYTR, body, sig, "EVT-DUP")
    assert "tekrar fatura kesilmedi" in second.note
    # yalnız tek fatura
    with svc.db._get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) n FROM payment_events"
                         " WHERE psp_event_id = 'EVT-DUP'").fetchone()["n"]
    assert n == 1


def test_webhook_non_success_event_no_invoice(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_PAYTR_MERCHANT_ID", "M1")
    monkeypatch.setenv("ANSWRANK_PAYTR_API_KEY", "SECRET")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    body = json.dumps({"intent_id": intent.intent_id, "status": "FAILED"}).encode()
    res = svc.handle_webhook(PaymentProvider.PAYTR, body, _sign("SECRET", body), "EVT-F")
    assert res.status == PaymentStatus.PENDING
    assert res.invoice_id is None


# --- 4) iade (credit note, silme yok) -------------------------------------

def test_refund_creates_credit_note_not_delete(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(country="GB", currency="GBP"), PaymentProvider.MANUAL)
    svc.confirm_manual(intent.intent_id, "DEKONT-GB")
    res = svc.refund(intent.intent_id, "Müşteri iptali")
    assert res.status == PaymentStatus.REFUNDED
    with pytest.raises(PaymentError):
        svc.refund(intent.intent_id, "tekrar")
    with svc.db._get_connection() as conn:
        row = conn.execute("SELECT * FROM payment_credit_notes"
                           " WHERE intent_id = ?", (intent.intent_id,)).fetchone()
        still = conn.execute("SELECT status FROM payment_intents"
                             " WHERE intent_id = ?", (intent.intent_id,)).fetchone()
    assert row is not None and row["reason"] == "Müşteri iptali"
    assert still["status"] == "REFUNDED"


def test_refund_requires_reason(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    with pytest.raises(PaymentError):
        svc.refund(intent.intent_id, "  ")


def test_refund_pending_intent_refused(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    with pytest.raises(PaymentError) as exc:
        svc.refund(intent.intent_id, "henüz ödenmedi")
    assert "başarı durumunda değil" in str(exc.value)


# --- 5) negatif/uye tutar --------------------------------------------------

def test_negative_amount_refused(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    with pytest.raises(PaymentError):
        svc.create_intent(PaymentRequest("SC-1", "B", "AE", "AED", -100.0),
                          PaymentProvider.MANUAL)


def test_paddle_mor_canli_when_configured(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_PADDLE_VENDOR", "V1")
    monkeypatch.setenv("ANSWRANK_PADDLE_API_KEY", "K1")
    assert svc.provider_status(PaymentProvider.PADDLE) == "CANLI"


# --- 6) API yüzeyi: kanal durumu dürüst ----------------------------------

def test_api_payment_channels_honest(monkeypatch):
    from fastapi.testclient import TestClient
    import tempfile
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ANSWRANK_DB_PATH", d + "/api.db")
    monkeypatch.setattr(settings, "db_path", d + "/api.db")
    for env in ("ANSWRANK_PAYTR_MERCHANT_ID", "ANSWRANK_PAYTR_API_KEY",
                "ANSWRANK_IYZICO_API_KEY", "ANSWRANK_IYZICO_SECRET",
                "ANSWRANK_PADDLE_VENDOR", "ANSWRANK_PADDLE_API_KEY",
                "ANSWRANK_MANUAL_IBAN"):
        monkeypatch.delenv(env, raising=False)
    from answrank.api.app import app, db as _db
    _db.db_path = d + "/api.db"
    client = TestClient(app)
    r = client.get("/api/payments/channels")
    assert r.status_code == 200
    ch = r.json()["channels"]
    assert "YAPILANDIRILMAMIŞ" in ch["PAYTR"]
    assert ch["MANUAL"].startswith("IBAN YOK")


# --- 7) kalan dallar: bozuk gövde, yeniden settle, as_dict ----------------

def test_webhook_malformed_body_rejected(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_PAYTR_MERCHANT_ID", "M1")
    monkeypatch.setenv("ANSWRANK_PAYTR_API_KEY", "SECRET")
    with pytest.raises(PaymentError) as exc:
        svc.handle_webhook(PaymentProvider.PAYTR, b"{not json",
                           _sign("SECRET", b"{not json"), "EVT-BAD")
    assert "gövdesi okunamadı" in str(exc.value)


def test_settle_twice_is_idempotent(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    first = svc.confirm_manual(intent.intent_id, "DEKONT-A")
    assert first.status == PaymentStatus.SUCCEEDED
    second = svc.confirm_manual(intent.intent_id, "DEKONT-B")
    assert "tekrar fatura kesilmedi" in second.note
    assert second.invoice_id is None


def test_as_dict_serialization(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    res = svc.confirm_manual(intent.intent_id, "DEKONT-C")
    d = res.as_dict()
    assert d["status"] == "SUCCEEDED" and d["invoice_id"]
    assert d["regime"].startswith("EXPORT")


def test_sign_uses_secret_key(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_PAYTR_MERCHANT_ID", "M1")
    monkeypatch.setenv("ANSWRANK_PAYTR_API_KEY", "SECRET")
    body = b"{}"
    assert svc._sign(PaymentProvider.PAYTR, body) == _sign("SECRET", body)


# --- 8) son 5 dal: yok niyet, iade-edilmiş settle, bilinmeyen PSP ---------

def test_confirm_unknown_intent_refused(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    with pytest.raises(PaymentError) as exc:
        svc.confirm_manual("PAY-99999", "DEKONT-X")
    assert "niyeti yok" in str(exc.value)


def test_settle_refunded_intent_refused(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    intent = svc.create_intent(_req(), PaymentProvider.MANUAL)
    svc.confirm_manual(intent.intent_id, "DEKONT-R")
    svc.refund(intent.intent_id, "İptal")
    with pytest.raises(PaymentError) as exc:
        svc.confirm_manual(intent.intent_id, "DEKONT-R2")
    assert "iade edilmiş" in str(exc.value)


def test_refund_unknown_intent_refused(svc, monkeypatch):
    monkeypatch.setenv("ANSWRANK_MANUAL_IBAN", "TR00")
    with pytest.raises(PaymentError) as exc:
        svc.refund("PAY-99998", "yok")
    assert "niyeti yok" in str(exc.value)


def test_unknown_provider_creds_returns_none(svc):
    from enum import Enum
    class Ghost(str, Enum):
        GHOST = "GHOST"
    assert svc._psp_creds(Ghost.GHOST) is None


def test_webhook_unconfigured_psp_refused(svc, monkeypatch):
    """API yüzeyi PSP'siz webhook alırsa hata döner — olay işlenmez."""
    monkeypatch.delenv("ANSWRANK_PAYTR_MERCHANT_ID", raising=False)
    monkeypatch.delenv("ANSWRANK_PAYTR_API_KEY", raising=False)
    with pytest.raises(PaymentError) as exc:
        svc.handle_webhook(PaymentProvider.PAYTR, b"{}", "sig", "EVT-U")
    assert "YAPILANDIRILMAMIŞ" in str(exc.value)


# --- 9) CLI yüzeyi (payments status/collect/confirm/refund) ---------------

def _run_cli(monkeypatch, tmp_path, argv, env: dict):
    import sys
    dbp = str(tmp_path / "cli.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp)
    monkeypatch.setattr(settings, "db_path", dbp)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["answrank"] + argv)
    from answrank.cli import main
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main()
    return out.getvalue()


def test_cli_payments_status_honest(monkeypatch, tmp_path):
    out = _run_cli(monkeypatch, tmp_path, ["payments", "status"], {})
    assert "YAPILANDIRILMAMIŞ" in out
    assert "IBAN YOK" in out


def test_cli_collect_requires_all_fields(monkeypatch, tmp_path):
    out = _run_cli(monkeypatch, tmp_path, ["payments", "collect", "--brand", "X"],
                   {"ANSWRANK_MANUAL_IBAN": "TR00"})
    assert "gerekli" in out


def test_cli_collect_and_confirm_end_to_end(monkeypatch, tmp_path):
    env = {"ANSWRANK_MANUAL_IBAN": "TR00 0001", "ANSWRANK_FX_RATES": "AED:9.6"}
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "collect", "--brand", "Royal Dental",
                    "--country", "AE", "--currency", "AED", "--amount", "5500"], env)
    assert "PAY-00001" in out
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "confirm", "--intent", "PAY-00001",
                    "--proof", "DEKONT-1"], env)
    # TEK-MÜKELLEF: fatura öneki UNPUMP-INV ( ürün değil tek-kurum)
    assert "EXPORT_SERVICE" in out and "UNPUMP-INV" in out


def test_cli_confirm_without_proof_refused(monkeypatch, tmp_path):
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "confirm", "--intent", "PAY-00001"],
                   {"ANSWRANK_MANUAL_IBAN": "TR00"})
    assert "kanitsiz" in out or "kanıtsız" in out


def test_cli_refund_requires_reason(monkeypatch, tmp_path):
    env = {"ANSWRANK_MANUAL_IBAN": "TR00"}
    _run_cli(monkeypatch, tmp_path, ["payments", "collect", "--brand", "Klinik",
             "--country", "TR", "--currency", "TRY", "--amount", "1000"], env)
    _run_cli(monkeypatch, tmp_path, ["payments", "confirm", "--intent", "PAY-00001",
             "--proof", "D"], env)
    out = _run_cli(monkeypatch, tmp_path, ["payments", "refund", "--intent", "PAY-00001"],
                   env)
    assert "gerekli" in out


def test_cli_refund_credit_note(monkeypatch, tmp_path):
    env = {"ANSWRANK_MANUAL_IBAN": "TR00"}
    _run_cli(monkeypatch, tmp_path, ["payments", "collect", "--brand", "Klinik",
             "--country", "TR", "--currency", "TRY", "--amount", "1000"], env)
    _run_cli(monkeypatch, tmp_path, ["payments", "confirm", "--intent", "PAY-00001",
             "--proof", "D"], env)
    out = _run_cli(monkeypatch, tmp_path, ["payments", "refund", "--intent", "PAY-00001",
             "--reason", "İptal"], env)
    assert "credit note" in out


def test_cli_webhook_bad_signature_rejected(monkeypatch, tmp_path):
    import json as _json
    env = {"ANSWRANK_PAYTR_MERCHANT_ID": "M1", "ANSWRANK_PAYTR_API_KEY": "SECRET"}
    f = tmp_path / "evt.json"
    f.write_text(_json.dumps({"intent_id": "PAY-00001", "status": "SUCCEEDED"}))
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "webhook", "--file", str(f),
                    "--signature", "0" * 64, "--event-id", "EVT-CLI"], env)
    assert "imza doğrulanamadı" in out


def test_cli_webhook_missing_args(monkeypatch, tmp_path):
    out = _run_cli(monkeypatch, tmp_path, ["payments", "webhook"], {})
    assert "gerekli" in out


def test_cli_collect_negative_amount_error_branch(monkeypatch, tmp_path):
    """CLI hata dalı: negatif tutar niyet üretmez, hata ekrana gelir."""
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "collect", "--brand", "X", "--country", "AE",
                    "--currency", "AED", "--amount", "-5"],
                   {"ANSWRANK_MANUAL_IBAN": "TR00"})
    assert "pozitif olmalı" in out


def test_cli_webhook_unconfigured_psp_error_branch(monkeypatch, tmp_path):
    import json as _json
    f = tmp_path / "evt.json"
    f.write_text(_json.dumps({"intent_id": "PAY-00001", "status": "SUCCEEDED"}))
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "webhook", "--file", str(f),
                    "--signature", "0" * 64, "--event-id", "EVT-U2"], {})
    assert "YAPILANDIRILMAMIŞ" in out


def test_cli_refund_error_branch(monkeypatch, tmp_path):
    """İade olmayan niyete reddedilir — hata dalı."""
    env = {"ANSWRANK_MANUAL_IBAN": "TR00"}
    _run_cli(monkeypatch, tmp_path, ["payments", "collect", "--brand", "K",
             "--country", "TR", "--currency", "TRY", "--amount", "100"], env)
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "refund", "--intent", "PAY-00001", "--reason", "x"], env)
    assert "başarı durumunda değil" in out or "durumunda değil" in out


def test_cli_refund_unknown_intent_error(monkeypatch, tmp_path):
    """Olumsuz niyette iade hata dalı (888-890)."""
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "refund", "--intent", "PAY-99999", "--reason", "x"],
                   {"ANSWRANK_MANUAL_IBAN": "TR00"})
    assert "niyeti yok" in out


def test_cli_webhook_success_branch(monkeypatch, tmp_path):
    """Başarılı webhook CLI dalı (910-911) — imzalı olay işlenir."""
    import json as _json, hmac, hashlib
    env = {"ANSWRANK_PAYTR_MERCHANT_ID": "M1", "ANSWRANK_PAYTR_API_KEY": "SECRET",
           "ANSWRANK_MANUAL_IBAN": "TR00"}
    out = _run_cli(monkeypatch, tmp_path, ["payments", "collect", "--brand", "Klinik",
             "--country", "AE", "--currency", "AED", "--amount", "1000"], env)
    import re as _re
    m = _re.search(r"PAY-\d+", out)
    assert m, "niyet id cikmadi"
    intent = m.group(0)
    body = _json.dumps({"intent_id": intent, "status": "SUCCEEDED"}).encode()
    sig = hmac.new(b"SECRET", body, hashlib.sha256).hexdigest()
    f = tmp_path / "evt.json"
    f.write_bytes(body)
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "webhook", "--file", str(f),
                    "--signature", sig, "--event-id", "EVT-CLI-OK"], env)
    assert "Fatura kesildi" in out


def test_cli_refund_already_refused_via_cli_twice(monkeypatch, tmp_path):
    """İki kez iade deneyince ikincide hata dalı (888-890) çalışır."""
    env = {"ANSWRANK_MANUAL_IBAN": "TR00"}
    _run_cli(monkeypatch, tmp_path, ["payments", "collect", "--brand", "K",
             "--country", "TR", "--currency", "TRY", "--amount", "100"], env)
    _run_cli(monkeypatch, tmp_path, ["payments", "confirm", "--intent", "PAY-00001",
             "--proof", "D"], env)
    _run_cli(monkeypatch, tmp_path, ["payments", "refund", "--intent", "PAY-00001",
             "--reason", "x"], env)
    out = _run_cli(monkeypatch, tmp_path, ["payments", "refund", "--intent", "PAY-00001",
             "--reason", "tekrar"], env)
    assert "iade edilmez" in out


def test_cli_confirm_nonexistent_intent_error(monkeypatch, tmp_path):
    """Confirm hata dalı (888-890): olmayan niyet reddedilir."""
    out = _run_cli(monkeypatch, tmp_path,
                   ["payments", "confirm", "--intent", "PAY-99999", "--proof", "X"],
                   {"ANSWRANK_MANUAL_IBAN": "TR00"})
    assert "niyeti yok" in out


def test_cli_dm_draft_with_visibility_and_without(monkeypatch, tmp_path):
    """E12: --with-visibility bayrağı ölçümü kanıt olarak DM'e ekler;
    ölçüm yoksa uydurulmaz (CLI 345-348 dalları)."""
    import sys, io, contextlib
    dbp = str(tmp_path / "dm.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp)
    monkeypatch.setattr(settings, "db_path", dbp)

    def _run(argv):
        monkeypatch.setattr(sys, "argv", ["answrank"] + argv)
        from answrank.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main()
        return out.getvalue()

    # 1) ölçüm yokken --with-visibility: uydurma yok, mini-probe da yok
    out = _run(["crm", "draft", "--from-lead", "yok.example",
                "--with-visibility"])
    assert "ÖLÇÜMLÜ mini-probe lead'i yok" in out

    # 2) mini-probe + doğrulanmış tam-canlı ölçüm kaydı (kanıt olarak)
    import asyncio
    from answrank.db import Database as _DB
    from answrank.models import CitationQueryItem, CitationRunResult
    from answrank.probe.miniprobe import MiniProbeResult
    dbp2 = str(tmp_path / "dm2.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp2)
    monkeypatch.setattr(settings, "db_path", dbp2)
    db = _DB()
    asyncio.run(db.save_miniprobe_lead(MiniProbeResult(
        domain="yok.example", verdict="TEMİZ", robots_line="İZİNLİ",
        llms_line="VAR", bots_line="3/3 örnek bot erişebiliyor",
        blocked_bots=[], probed=3, measured=True)))
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="dm1", brand_name="Yok", domain="yok.example", sector="dental",
        city="İzmir", total_runs=10, brand_citations_found=2,
        citation_rate_percentage=20.0, live_items_count=10,
        live_response_rate_percentage=100.0, is_fully_live=True,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                 model="test-model", was_simulated=False,
                                 brand_mentioned=i < 2) for i in range(10)])))

    out = _run(["crm", "draft", "--from-lead", "yok.example"])
    assert "görünürlüğünü" not in out  # bayrak yoksa eklenmez

    out = _run(["crm", "draft", "--from-lead", "yok.example",
                "--with-visibility"])
    # Rich Panel satır sarması kutu karakterlerini cümle ortasına koyar:
    # kenar karakterlerini temizleyip normalize ederek ara
    flat = " ".join(out.replace("│", " ").split())
    assert "10 test yanıtının 2 tanesinde marka adı veya domain eşleşmesi" in flat
    assert "kullanıcı arama trafiğini" in flat
