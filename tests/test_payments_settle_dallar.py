"""answrank.finance.payments dal-kesen testleri (LEED) — 2 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek ledger/PSP YOK; TaxLedger STUBLA, sqlite
conftest'in tmp_path yonlendirmesiyle (settings.db_path).
PaymentService._settle + payments._now.
"""
import sqlite3
from types import SimpleNamespace

import pytest

from answrank.config import settings
from answrank.finance.payments import (PaymentError, PaymentProvider,
                                       PaymentResult, PaymentService,
                                       PaymentStatus, _now)
from answrank.finance.tax_ledger import TaxRegime


class FakeLedger:
    """Saf-in-memory ledger — record_invoice cagrisini kanitlar."""

    def __init__(self, invoice_id="F-001", regime=TaxRegime.EXPORT_SERVICE,
                 fail=None):
        self.invoice_id = invoice_id
        self.regime = regime
        self.fail = fail
        self.calls = []

    def record_invoice(self, *, client_brand, country, currency, amount,
                       exchange_rate=None, invoice_no=None, product_name="unknown"):
        self.calls.append(dict(client_brand=client_brand, country=country,
                               currency=currency, amount=amount,
                               exchange_rate=exchange_rate, invoice_no=invoice_no,
                               product_name=product_name))
        if self.fail:
            raise self.fail
        return SimpleNamespace(invoice_id=self.invoice_id, regime=self.regime)


def _service(tmp_path, monkeypatch, ledger=None):
    from answrank.db import Database
    p = str(tmp_path / "pay.db")
    monkeypatch.setattr(settings, "db_path", p)
    db = Database()
    return PaymentService(db=db, ledger=ledger or FakeLedger())


def _insert_intent(db, intent_id="PAY-00001", status="PENDING", amount=100.0,
                   country="AE", currency="USD", brand="Marka",
                   contract_ref="S-1"):
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO payment_intents"
            " (intent_id, contract_ref, brand, country, currency, amount,"
            " provider, status) VALUES (?,?,?,?,?,?,?,?)",
            (intent_id, contract_ref, brand, country, currency, amount,
             "MANUAL", status))
        conn.commit()


def _status(db, intent_id):
    with db._get_connection() as conn:
        return conn.execute(
            "SELECT status, invoice_id, proof_ref, settled_at"
            " FROM payment_intents WHERE intent_id = ?", (intent_id,)).fetchone()


def _events(db):
    with db._get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT psp_event_id, provider, intent_id, status, raw"
            " FROM payment_events")]


# == _now ====================================================================================

def test_now_iso_format():
    v = _now()
    assert "T" in v and v.endswith("+00:00")


def test_now_timespec_seconds():
    """ORTAM: timespec='seconds' — mikrosaniye YOK."""
    v = _now()
    assert "." not in v


def test_now_utc_offset():
    assert _now().endswith("+00:00")


def test_now_parse_edilebilir():
    from datetime import datetime
    datetime.fromisoformat(_now())


def test_now_saniye_yaklasik_simdi():
    from datetime import datetime, timezone
    import time
    t1 = time.time()
    d = datetime.fromisoformat(_now())
    assert abs(d.timestamp() - t1) < 5


@pytest.mark.parametrize("n", range(3))
def test_now_monoton_artar(n):
    from datetime import datetime
    a = datetime.fromisoformat(_now())
    b = datetime.fromisoformat(_now())
    assert b >= a


def test_now_string_donus():
    assert isinstance(_now(), str)


# == _settle — basarili ======================================================================

def test_settle_basarili(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    r = svc._settle("PAY-00001", PaymentProvider.MANUAL, "DEK-1")
    assert isinstance(r, PaymentResult)
    assert r.intent_id == "PAY-00001"
    assert r.status == PaymentStatus.SUCCEEDED
    assert r.invoice_id == "F-001"
    assert r.regime == TaxRegime.EXPORT_SERVICE
    assert "Fatura kesildi" in r.note


def test_settle_db_durumu_gunceller(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db)
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "DEK-1")
    row = _status(svc.db, "PAY-00001")
    assert row["status"] == "SUCCEEDED"
    assert row["invoice_id"] == "F-001"
    assert row["proof_ref"] == "DEK-1"
    assert row["settled_at"] is not None


def test_settle_ledger_cagrisi_argumanlari(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, amount=250.5, country="TR", currency="TRY",
                   brand="TürkMarka")
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert led.calls == [dict(client_brand="TürkMarka", country="TR",
                              currency="TRY", amount=250.5,
                              exchange_rate=None, invoice_no=None,
                              product_name="unknown")]


def test_settle_odeme_olayi_kaydeder(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db)
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "EVT-99")
    evs = _events(svc.db)
    assert len(evs) == 1
    assert evs[0]["psp_event_id"] == "EVT-99"
    assert evs[0]["intent_id"] == "PAY-00001"
    assert evs[0]["status"] == "SUCCEEDED"
    assert "invoice=F-001" in evs[0]["raw"]


def test_settle_provider_event_kaydinda(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db)
    svc._settle("PAY-00001", PaymentProvider.IYZICO, "E-1")
    assert _events(svc.db)[0]["provider"] == "IYZICO"


@pytest.mark.parametrize("prov", list(PaymentProvider))
def test_settle_tum_providerlar(tmp_path, monkeypatch, prov):
    """ORTAM: provider degeri event kaydina string olarak gecer."""
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db, intent_id=f"PAY-{prov.value}")
    svc._settle(f"PAY-{prov.value}", prov, "P")
    assert _events(svc.db)[0]["provider"] == prov.value


def test_settle_regime_ledgerdan_gecer(tmp_path, monkeypatch):
    led = FakeLedger(regime=TaxRegime.DOMESTIC_SERVICE, invoice_id="F-DOM")
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    r = svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert r.invoice_id == "F-DOM"
    assert r.regime == TaxRegime.DOMESTIC_SERVICE


def test_settle_kapasitonun_regimei_kaydedilir(tmp_path, monkeypatch):
    led = FakeLedger(invoice_id="X-9")
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    r = svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert _status(svc.db, "PAY-00001")["invoice_id"] == "X-9"
    assert r.invoice_id == "X-9"


# == _settle — hata dallari ==================================================================

def test_settle_niyet_yok_hatasi(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    with pytest.raises(PaymentError) as exc:
        svc._settle("YOK-1", PaymentProvider.MANUAL, "P")
    assert "Tahsilat niyeti yok" in str(exc.value)


def test_settle_niyet_yok_ledger_cagrilmaz(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    with pytest.raises(PaymentError):
        svc._settle("YOK-1", PaymentProvider.MANUAL, "P")
    assert led.calls == []


def test_settle_zaten_basarili_tekrar_yok(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, status="SUCCEEDED")
    r = svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert r.status == PaymentStatus.SUCCEEDED
    assert "Zaten başarıyla kapatılmış" in r.note
    assert "tekrar fatura kesilmedi" in r.note


def test_settle_zaten_basarili_ledger_cagrilmaz(tmp_path, monkeypatch):
    """ORTAM-OGRENDI: idempotency — SUCCEEDED kayit tekrar fatura URETMEZ."""
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, status="SUCCEEDED")
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert led.calls == []


def test_settle_zaten_basarili_event_eklenmez(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db, status="SUCCEEDED")
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert _events(svc.db) == []


def test_settle_iade_edilmis_hata(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db, status="REFUNDED")
    with pytest.raises(PaymentError) as exc:
        svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert "iade edilmiş" in str(exc.value)


def test_settle_iade_edilmis_ledger_cagrilmaz(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, status="REFUNDED")
    with pytest.raises(PaymentError):
        svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert led.calls == []


def test_settle_ledger_hatasi_yayilir(tmp_path, monkeypatch):
    """ORTAM-OGRENDI: ledger exception DOGRUDAN yayilir — fail-loud;
    DB'ye yarim-settle YAZILMAZ (transaction disinda)."""
    led = FakeLedger(fail=RuntimeError("ledger down"))
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    with pytest.raises(RuntimeError) as exc:
        svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert "ledger down" in str(exc.value)
    assert _status(svc.db, "PAY-00001")["status"] == "PENDING"


def test_settle_ledger_hatasi_event_yazilmaz(tmp_path, monkeypatch):
    led = FakeLedger(fail=RuntimeError("ledger down"))
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    with pytest.raises(RuntimeError):
        svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert _events(svc.db) == []


# == _settle — confirm_manual/webhook entegrasyonu ===========================================

def test_settle_confirm_manual_yoluyla(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    r = svc.confirm_manual("PAY-00001", "  DEK-42  ")
    assert r.status == PaymentStatus.SUCCEEDED
    assert _status(svc.db, "PAY-00001")["proof_ref"] == "DEK-42"


def test_settle_confirm_manual_bos_kanit_reddeder(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db)
    with pytest.raises(PaymentError) as exc:
        svc.confirm_manual("PAY-00001", "  ")
    assert "Banka kanıtı" in str(exc.value)
    assert _status(svc.db, "PAY-00001")["status"] == "PENDING"


def test_settle_webhook_yoluyla(tmp_path, monkeypatch):
    import hmac
    import hashlib
    import json
    monkeypatch.setenv("ANSWRANK_IYZICO_API_KEY", "k1")
    monkeypatch.setenv("ANSWRANK_IYZICO_SECRET", "s1")
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db)
    body = json.dumps({"intent_id": "PAY-00001", "status": "SUCCEEDED"}).encode()
    sig = hmac.new(b"k1", body, hashlib.sha256).hexdigest()
    r = svc.handle_webhook(PaymentProvider.IYZICO, body, sig, "EVT-1")
    assert r.status == PaymentStatus.SUCCEEDED
    assert _status(svc.db, "PAY-00001")["status"] == "SUCCEEDED"


# == _settle — cesitli tutar/ulke ============================================================

@pytest.mark.parametrize("amount", [0.01, 1.0, 99.99, 10000.5])
def test_settle_tutar_ledgera_gecer(tmp_path, monkeypatch, amount):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, amount=amount)
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert led.calls[0]["amount"] == amount


@pytest.mark.parametrize("country, currency", [("AE", "AED"), ("TR", "TRY"),
                                               ("US", "USD"), ("DE", "EUR")])
def test_settle_ulke_para_birimi_ledgera(tmp_path, monkeypatch, country, currency):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, country=country, currency=currency)
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert led.calls[0]["country"] == country
    assert led.calls[0]["currency"] == currency


def test_settle_unicode_marka(tmp_path, monkeypatch):
    led = FakeLedger()
    svc = _service(tmp_path, monkeypatch, led)
    _insert_intent(svc.db, brand="İĞÜŞÖ Marka")
    svc._settle("PAY-00001", PaymentProvider.MANUAL, "P")
    assert led.calls[0]["client_brand"] == "İĞÜŞÖ Marka"


def test_settle_cok_niyet_bagimsiz(tmp_path, monkeypatch):
    svc = _service(tmp_path, monkeypatch=monkeypatch)
    _insert_intent(svc.db, intent_id="PAY-1", amount=10)
    _insert_intent(svc.db, intent_id="PAY-2", amount=20, country="TR",
                   currency="TRY")
    svc._settle("PAY-1", PaymentProvider.MANUAL, "A")
    svc._settle("PAY-2", PaymentProvider.MANUAL, "B")
    assert _status(svc.db, "PAY-1")["invoice_id"] == "F-001"
    assert _status(svc.db, "PAY-2")["invoice_id"] == "F-001"
    assert len(_events(svc.db)) == 2
