"""answrank.monitor.fulfillment dal-kesen testleri (LEED) — 3 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gerkek ag YOK; sqlite conftest'in tmp db'si +
ApprovalQueue.modul-nitelik stub. FulfillmentEvaluator._persist + evaluate
(NO_LINK/INSUFFICIENT/SATISFIED/TRIGGERED) + list_events.
"""
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from answrank.monitor import fulfillment
from answrank.monitor.fulfillment import FulfillmentEvaluator


def _insert_monitor(p, mid, contract_id=None):
    with sqlite3.connect(p) as c:
        c.execute(
            "INSERT INTO monitors (id, domain, brand, sector, cadence_days,"
            " active, contract_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (mid, f"{mid}.example", "Marka", "dental", 30, 1, contract_id,
             "2026-01-01T00:00:00"))
        c.commit()


def _events(p, mid=None):
    with sqlite3.connect(p) as c:
        c.row_factory = sqlite3.Row
        q = "SELECT * FROM fulfillment_events"
        rows = list(c.execute(q + (" WHERE monitor_id = ?" if mid else ""),
                              (mid,) if mid else ()))
        return [dict(r) for r in rows]


def _queue(p):
    with sqlite3.connect(p) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM approval_queue")]


@pytest.fixture
def fe(tmp_path, monkeypatch):
    """ORTAM: settings.db_path -> tmp; Database semayi olusturur."""
    from answrank.config import settings
    p = str(tmp_path / "ful.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    ev = FulfillmentEvaluator(db=Database())
    ev._dbpath = p
    return ev


@pytest.fixture
def stub_queue(monkeypatch):
    """ORTAM: ApprovalQueue modul-niteligi STUBLA (from-import runtime okur)."""
    cagrilan = []

    class _Q:
        def __init__(self, db=None):
            self.db = db

        def add(self, kind, ref_id, summary):
            cagrilan.append((kind, ref_id, summary))
            return True

    import answrank.queue as qmod
    monkeypatch.setattr(qmod, "ApprovalQueue", _Q)
    return cagrilan


# == _persist — TRIGGERED kuyruk ================================================================

def test_persist_triggered_kuyruğa_ekler(fe, stub_queue):
    ev = {"monitor_id": "mon-abc123", "contract_id": "C1",
          "kind": FulfillmentEvaluator.TRIGGERED, "delta": -4.2,
          "free_cycle_id": "FREE-CYCLE-abc123-20260101",
          "reason": "MADDE 7.3 TETİKLENDİ: ..."}
    fe._persist(ev)
    assert len(stub_queue) == 1
    kind, ref, summary = stub_queue[0]
    assert kind == "FREE_CYCLE"
    assert ref == "FREE-CYCLE-abc123-20260101"
    assert summary == "MADDE 7.3 — MADDE 7.3 TETİKLENDİ: ..."


def test_persist_triggered_olay_yazar(fe, stub_queue):
    ev = {"monitor_id": "mon-x", "contract_id": "C2",
          "kind": FulfillmentEvaluator.TRIGGERED, "delta": -1.5,
          "free_cycle_id": "F-1", "reason": "r"}
    fe._persist(ev)
    rows = _events(fe._dbpath)
    assert len(rows) == 1
    r = rows[0]
    assert r["monitor_id"] == "mon-x"
    assert r["contract_id"] == "C2"
    assert r["kind"] == "TRIGGERED"
    assert r["delta"] == -1.5
    assert r["free_cycle_id"] == "F-1"
    assert r["reason"] == "r"
    assert r["evaluated_at"]


def test_persist_triggered_gerçek_kuyruk_satırı(fe):
    """ORTAM: stub YOK — gercek ApprovalQueue.add approval_queue'a yazar."""
    ev = {"monitor_id": "mon-y", "contract_id": "C3",
          "kind": FulfillmentEvaluator.TRIGGERED, "delta": -3.0,
          "free_cycle_id": "F-2", "reason": "tetik"}
    fe._persist(ev)
    rows = _queue(fe._dbpath)
    assert len(rows) == 1
    assert rows[0]["kind"] == "FREE_CYCLE"
    assert rows[0]["ref_id"] == "F-2"
    assert rows[0]["summary"] == "MADDE 7.3 — tetik"


# == _persist — TRIGGERED olmayan dallar kuyruğa GİTMEZ ========================================

@pytest.mark.parametrize("kind, delta", [
    (FulfillmentEvaluator.NO_LINK, None),
    (FulfillmentEvaluator.INSUFFICIENT, None),
    (FulfillmentEvaluator.SATISFIED, 7.5),
])
def test_persist_triggered_disinda_kuyruk_yok(fe, stub_queue, kind, delta):
    """ORTAM-OGRENDI: yalniz TRIGGERED onay kuyruğuna gider — gelir-düşüren
    karar degilse operatör onayı gerekmez."""
    ev = {"monitor_id": "m", "contract_id": "C", "kind": kind,
          "delta": delta, "free_cycle_id": None, "reason": "r"}
    fe._persist(ev)
    assert stub_queue == []
    assert _events(fe._dbpath)[0]["kind"] == kind


def test_persist_satisfied_olay_yazar(fe, stub_queue):
    ev = {"monitor_id": "m", "contract_id": "C",
          "kind": FulfillmentEvaluator.SATISFIED, "delta": 7.5,
          "free_cycle_id": None, "reason": "Güvence karşlandı"}
    fe._persist(ev)
    r = _events(fe._dbpath)[0]
    assert r["delta"] == 7.5 and r["free_cycle_id"] is None


def test_persist_no_link_contract_none(fe, stub_queue):
    ev = {"monitor_id": "m", "contract_id": "NONE",
          "kind": FulfillmentEvaluator.NO_LINK, "delta": None,
          "free_cycle_id": None, "reason": "bağ yok"}
    fe._persist(ev)
    r = _events(fe._dbpath)[0]
    assert r["contract_id"] == "NONE"
    assert r["delta"] is None


def test_persist_contract_id_none_integrity(fe, stub_queue):
    """ORTAM-OGRENDI: fulfillment_events.contract_id NOT NULL — NULL INSERT
    IntegrityError. (Production NO_LINK yolu _persist'i HIC cagirmaz.)"""
    ev = {"monitor_id": "m", "contract_id": None,
          "kind": FulfillmentEvaluator.NO_LINK, "delta": None,
          "free_cycle_id": None, "reason": "bağ yok"}
    with pytest.raises(sqlite3.IntegrityError):
        fe._persist(ev)


def test_persist_cok_olay_sirali(fe, stub_queue):
    """ORTAM: her _persist yeni fulfillment_events satırı (append)."""
    for i in range(4):
        fe._persist({"monitor_id": f"m{i}", "contract_id": "C", "kind": "SATISFIED",
                     "delta": float(i), "free_cycle_id": None, "reason": "r"})
    rows = _events(fe._dbpath)
    assert [r["monitor_id"] for r in rows] == ["m0", "m1", "m2", "m3"]
    assert [r["id"] for r in rows] == [1, 2, 3, 4]


def test_persist_evaluated_at_iso(fe, stub_queue):
    """ORTAM: evaluated_at datetime.now(UTC).isoformat() — parse edilebilir."""
    ev = {"monitor_id": "m", "contract_id": "C", "kind": "SATISFIED",
          "delta": 1.0, "free_cycle_id": None, "reason": "r"}
    fe._persist(ev)
    ts = _events(fe._dbpath)[0]["evaluated_at"]
    assert datetime.fromisoformat(ts).tzinfo is not None


def test_persist_unicode_reason(fe, stub_queue):
    ev = {"monitor_id": "m", "contract_id": "C", "kind": "SATISFIED",
          "delta": 1.0, "free_cycle_id": None,
          "reason": "İĞÜŞÖ — ölçülen delta karşılandı 🔥"}
    fe._persist(ev)
    assert _events(fe._dbpath)[0]["reason"] == "İĞÜŞÖ — ölçülen delta karşılandı 🔥"


# == evaluate — NO_LINK (persist YOK) ===========================================================

def test_evaluate_no_link_kayit_yoksa_keyerror(fe, tmp_path):
    """ORTAM: monitor yoksa KeyError('İzleme kaydı yok: X')."""
    with pytest.raises(KeyError) as e:
        fe.evaluate("yok-id")
    assert "İzleme kaydı yok: yok-id" in str(e.value)


def test_evaluate_no_link_contract_yok(fe, stub_queue):
    """ORTAM-OGRENDI: contract_id yoksa NO_LINK — hüküm kurulamaz, sayı
    uydurulmaz; _persist CAGRILMAZ (kanıt loglanmaz)."""
    _insert_monitor(fe._dbpath, "mon-1")
    ev = fe.evaluate("mon-1")
    assert ev["kind"] == "NO_LINK"
    assert ev["contract_id"] is None
    assert ev["delta"] is None
    assert "hüküm kurulamaz" in ev["reason"]
    assert stub_queue == []
    assert _events(fe._dbpath) == []


# == evaluate — digest ile SATISFIED / TRIGGERED ================================================

@pytest.fixture
def fe_digest(fe, monkeypatch):
    _insert_monitor(fe._dbpath, "mon-trg", contract_id="C-7")
    fe2 = FulfillmentEvaluator(db=fe.db)
    fe2._dbpath = fe._dbpath
    return fe2


def _stub_digest(fe2, delta_base):
    fe2.svc.digest = lambda mid: {
        "status": "İZLENİYOR", "delta_base": delta_base}


def test_evaluate_satisfied(fe_digest, stub_queue, monkeypatch):
    """ORTAM: delta >= monitor_guarantee_score_delta_min -> SATISFIED."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "monitor_guarantee_score_delta_min", 3.0)
    _stub_digest(fe_digest, 5.5)
    ev = fe_digest.evaluate("mon-trg")
    assert ev["kind"] == "SATISFIED"
    assert ev["delta"] == 5.5
    assert "Güvence karşlandı" in ev["reason"]
    assert "+5.5" in ev["reason"]
    assert "+3.0" in ev["reason"]
    assert ev["free_cycle_id"] is None
    assert stub_queue == []


def test_evaluate_satisfied_esik_tam_üstü(fe_digest, stub_queue, monkeypatch):
    from answrank.config import settings
    monkeypatch.setattr(settings, "monitor_guarantee_score_delta_min", 3.0)
    _stub_digest(fe_digest, 3.0)
    assert fe_digest.evaluate("mon-trg")["kind"] == "SATISFIED"


def test_evaluate_triggered(fe_digest, stub_queue, monkeypatch):
    """ORTAM: delta < esik -> TRIGGERED + FREE-CYCLE id + kuyruk + persist."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "monitor_guarantee_score_delta_min", 3.0)
    """ORTAM-OGRENDI: monitor_id[-6:] = 'on-trg' (7 karakterden son 6)."""
    _stub_digest(fe_digest, -2.4)
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    ev = fe_digest.evaluate("mon-trg", now=now)
    assert ev["kind"] == "TRIGGERED"
    assert ev["delta"] == -2.4
    assert ev["free_cycle_id"] == "FREE-CYCLE-on-trg-20260115"
    assert "MADDE 7.3 TETİKLENDİ" in ev["reason"]
    assert "HİÇBİR EK ÜCRET" in ev["reason"]
    assert len(stub_queue) == 1
    assert stub_queue[0][0] == "FREE_CYCLE"
    assert stub_queue[0][2] == ("MADDE 7.3 — MADDE 7.3 TETİKLENDİ: ölçülen delta"
                                " +-2.4 < +3.0 — takip eden 30 günlük çalışma"
                                " takvimi HİÇBİR EK ÜCRET talep edilmeden"
                                " icra edilecek. Kayıt: FREE-CYCLE-on-trg-20260115.")
    assert _events(fe_digest._dbpath)[0]["kind"] == "TRIGGERED"


def test_evaluate_triggered_free_cycle_id_mono(fe_digest, stub_queue,
                                              monkeypatch):
    """ORTAM-OGRENDI: free_cycle_id = 'FREE-CYCLE-' + monitor_id[-6:] + tarih."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "monitor_guarantee_score_delta_min", 5.0)
    _insert_monitor(fe_digest._dbpath, "mon-ABCDEFGH", contract_id="C")
    fe_digest.db.get_monitor = lambda mid: {"id": mid, "contract_id": "C"}
    _stub_digest(fe_digest, 0.0)
    ev = fe_digest.evaluate("mon-ABCDEFGH",
                            now=datetime(2026, 3, 4, tzinfo=timezone.utc))
    assert ev["free_cycle_id"] == "FREE-CYCLE-CDEFGH-20260304"


def test_evaluate_insufficient(fe_digest, stub_queue, monkeypatch):
    """ORTAM: status != İZLENİYOR veya delta_base None -> INSUFFICIENT."""
    fe_digest.svc.digest = lambda mid: {"status": "BEKLEMEDE",
                                        "delta_base": None}
    ev = fe_digest.evaluate("mon-trg")
    assert ev["kind"] == "INSUFFICIENT"
    assert ev["delta"] is None
    assert "ÖLÇÜM YETERSİZ" in ev["reason"]
    assert "sayı uydurulmaz" in ev["reason"]
    assert stub_queue == []
    assert _events(fe_digest._dbpath)[0]["kind"] == "INSUFFICIENT"


def test_evaluate_insufficient_delta_none_izleniyor(fe_digest, stub_queue):
    """ORTAM: İZLENİYOR ama delta_base None -> yine INSUFFICIENT."""
    fe_digest.svc.digest = lambda mid: {"status": "İZLENİYOR",
                                        "delta_base": None}
    assert fe_digest.evaluate("mon-trg")["kind"] == "INSUFFICIENT"


def test_evaluate_triggered_delta_float_cevirimi(fe_digest, stub_queue,
                                                 monkeypatch):
    """ORTAM: delta_base float() ile cevrilir — int/string de calisir."""
    from answrank.config import settings
    monkeypatch.setattr(settings, "monitor_guarantee_score_delta_min", 3.0)
    fe_digest.svc.digest = lambda mid: {"status": "İZLENİYOR",
                                        "delta_base": 1}
    ev = fe_digest.evaluate("mon-trg")
    assert ev["delta"] == 1.0
    assert ev["kind"] == "TRIGGERED"


# == list_events =================================================================================

def test_list_events_bos(fe):
    assert fe.list_events() == []


def test_list_events_tümü(fe, stub_queue):
    for i, kind in enumerate(["NO_LINK", "SATISFIED", "TRIGGERED", "INSUFFICIENT"]):
        fe._persist({"monitor_id": f"m{i}", "contract_id": "C", "kind": kind,
                     "delta": None, "free_cycle_id": None, "reason": "r"})
    rows = fe.list_events()
    assert len(rows) == 4
    assert [r["kind"] for r in rows] == ["NO_LINK", "SATISFIED", "TRIGGERED",
                                        "INSUFFICIENT"]


def test_list_events_monitor_filtresi(fe, stub_queue):
    fe._persist({"monitor_id": "ma", "contract_id": "C", "kind": "SATISFIED",
                 "delta": None, "free_cycle_id": None, "reason": "r"})
    fe._persist({"monitor_id": "mb", "contract_id": "C", "kind": "TRIGGERED",
                 "delta": None, "free_cycle_id": None, "reason": "r"})
    rows = fe.list_events(monitor_id="mb")
    assert len(rows) == 1 and rows[0]["monitor_id"] == "mb"


def test_list_events_id_sirali(fe, stub_queue):
    """ORTAM: ORDER BY id — ekleme sirasi korunur."""
    for i in range(3):
        fe._persist({"monitor_id": f"m{i}", "contract_id": "C", "kind": "SATISFIED",
                     "delta": None, "free_cycle_id": None, "reason": "r"})
    assert [r["id"] for r in fe.list_events()] == [1, 2, 3]
