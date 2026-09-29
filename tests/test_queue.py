"""Canlıya-geçiş dilimi: ANSINGLE onay kuyruğu (`answrank queue`).

İlke: sistem hiçbir dışa-yönelik fiili kendiliğinden işlemez; kararı insanı
gerektiren her olay (DM gönderimi, sözleşme teslimi, gelir-düşüren FREE-CYCLE,
izleme müdahalesi) TEK kuyrukta toplanır. Kuyruk boşsa boş yazar — iş uydurulmaz.
Kararlar geri-döndürülemez kayıt (decided_at + not), çift-karar REDDEDİLİR.
"""
import asyncio
from datetime import datetime

import pytest

from answrank.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "q.db"))


@pytest.fixture
def q(db):
    from answrank.queue import ApprovalQueue
    return ApprovalQueue(db=db)


def _mk_measured(score=50.0, sov=1.0, cit_id="cit_q"):
    async def ex(domain, sector, brand):
        return {"status": "MEASURED", "score_base": score, "sov_pct": sov,
                "audit_id": None, "citation_run_id": cit_id, "note": ""}
    return ex


# ------------------------------------------------------------------ temel
def test_add_dedups_and_lists_pending(q):
    assert q.add(kind="DM", ref_id="a.example", summary="3/3 bot erişebiliyor") is True
    assert q.add(kind="DM", ref_id="a.example", summary="terar") is False  # dedup
    items = q.pending()
    assert len(items) == 1 and items[0]["kind"] == "DM"
    assert items[0]["status"] == "PENDING"


def test_decision_is_final_and_annotated(q):
    q.add(kind="FREE_CYCLE", ref_id="FREE-X", summary="Madde 7.3: delta +5 < +12")
    iid = q.pending()[0]["id"]
    row = q.decide(iid, approve=False, note="yanlış hesap — müşteriyle konuşuldu")
    assert row["status"] == "REJECTED" and row["decided_at"] and "konuşuldu" in row["decision_note"]
    with pytest.raises(ValueError, match="karar verilmiş"):
        q.decide(iid, approve=True)
    with pytest.raises(KeyError):
        q.decide(9999, approve=True)
    assert q.pending() == []


def test_decide_binds_dm_to_visibility_run_id(q, db):
    """DM kararı, o anki geçerli görünürlük koşu kimliğini bağlar."""
    from answrank.models import CitationQueryItem, CitationRunResult
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="bind-1", brand_name="X", domain="bind.example", sector="dental",
        city="Dubai", total_runs=2, brand_citations_found=1,
        citation_rate_percentage=50.0, is_fully_live=True, live_items_count=2,
        live_response_rate_percentage=100.0, grounding_status={"m": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}", model="m",
               was_simulated=False, brand_mentioned=i == 0) for i in range(2)])))
    q.add(kind="DM", ref_id="bind.example", summary="dm")
    iid = q.pending()[0]["id"]
    row = q.decide(iid, approve=True, note="insan")
    assert row["status"] == "APPROVED"
    with db._get_connection() as conn:
        stored = conn.execute("SELECT evidence_run_id FROM approval_queue WHERE id=?",
                              (iid,)).fetchone()
    assert stored["evidence_run_id"] == "bind-1"


def test_decide_without_evidence_binds_null(q, db):
    """Kanıt yoksa kimlik NULL kalır; gönderim yolu yine bağlar."""
    q.add(kind="DM", ref_id="none.example", summary="dm")
    iid = q.pending()[0]["id"]
    q.decide(iid, approve=True, note="insan")
    with db._get_connection() as conn:
        stored = conn.execute("SELECT evidence_run_id FROM approval_queue WHERE id=?",
                              (iid,)).fetchone()
    assert stored["evidence_run_id"] is None


def test_human_decision_cannot_overwrite_concurrent_final_decision(q, db, monkeypatch):
    from contextlib import contextmanager
    from answrank.queue import ApprovalQueue

    q.add("DM", "race.example", "Karar yarışı")
    iid = q.pending()[0]["id"]
    original_connection = db._get_connection
    competitor = ApprovalQueue(db=Database(db_path=db.db_path))
    winner = {}

    class PausedRead:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            stale = self.cursor.fetchone()
            competitor.decide(iid, False, note="İlk nihai karar")
            with original_connection() as conn:
                winner.update(dict(conn.execute(
                    "SELECT * FROM approval_queue WHERE id=?", (iid,)
                ).fetchone()))
            return stale

    class InterleavedConnection:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, args=()):
            cursor = self.conn.execute(sql, args)
            if sql.startswith("SELECT * FROM approval_queue"):
                return PausedRead(cursor)
            return cursor

        def commit(self):
            self.conn.commit()

    @contextmanager
    def interleaved():
        with original_connection() as conn:
            yield InterleavedConnection(conn)

    monkeypatch.setattr(db, "_get_connection", interleaved)
    with pytest.raises(ValueError, match="karar"):
        q.decide(iid, True, note="Eski PENDING görüntüsü")
    with original_connection() as conn:
        actual = dict(conn.execute("SELECT * FROM approval_queue WHERE id=?",
                                   (iid,)).fetchone())
    assert actual == winner


def test_decision_response_matches_persisted_timestamp(q, db):
    q.add("DM", "time.example", "Tek zaman damgası")
    iid = q.pending()[0]["id"]
    result = q.decide(iid, True, note="İnsan")
    with db._get_connection() as conn:
        saved = dict(conn.execute("SELECT * FROM approval_queue WHERE id=?",
                                  (iid,)).fetchone())
    assert result == saved


def test_unknown_kind_rejected(q):
    with pytest.raises(ValueError):
        q.add(kind="TODO", ref_id="x", summary="y")
    with pytest.raises(ValueError):
        q.add(kind="dm", ref_id="x", summary="y")  # büyük-küçük harf duyarlı tür


# ------------------------------------------------------------------ üreticiler
def test_scan_collects_dm_contract_and_monitor_intervention(q, db):
    # lead: ölçümlü miniprobe
    with db._get_connection() as c:
        c.execute("INSERT INTO miniprobe_leads (domain, verdict, robots_line, llms_line,"
                  " bots_line, measured, created_at) VALUES (?,?,?,?,?,?,?)",
                  ("klinik.example", "BOT ERİŞİMİ ENGELLİ", "İZİNLİ", "YOK",
                   "1/3 örnek bot ENGELLİ: GPTBot", 1, "2026-09-16T00:00:00"))
        # sözleşme: CONTRACT_ISSUED
        c.execute("INSERT INTO swarm_candidates (id, brand_name, domain, sector, city,"
                  " country, currency, ticket_size, stage, contract_text)"
                  " VALUES ('sw_q1','K','klinik.example','dental','Dubai','UAE','AED',"
                  " 5500,'CONTRACT_ISSUED','…sözleşme…')")
        c.commit()
    # izleme: 3 koşu, hiçbiri MEASURED değil → müdahale
    from answrank.monitor.service import MonitorService

    async def boom(domain, sector, brand):
        raise RuntimeError("erişilemiyor")
    svc = MonitorService(db=db)
    mid = svc.add(domain="olumlu.example", brand="O", sector="general")
    for i in range(3):
        asyncio.run(svc.run_one(mid, executor=boom,
                                now=datetime(2026, 9, 10 + i)))
    n = q.scan()
    kinds = {i["kind"] for i in q.pending()}
    assert kinds == {"DM", "CONTRACT", "MONITOR_INTERVENTION"}
    assert n == 3
    assert q.scan() == 0  # dedup: ikinci tarama aynı maddeleri yeniden doğurmaz


def test_fulfillment_trigger_auto_queues_free_cycle(svc_db):
    db, svc, mid = svc_db
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    from answrank.queue import ApprovalQueue
    ev = FulfillmentEvaluator(db=db)
    res = ev.evaluate(mid)
    assert res["kind"] == "TRIGGERED"
    items = ApprovalQueue(db=db).pending()
    fc = [i for i in items if i["kind"] == "FREE_CYCLE"]
    assert len(fc) == 1 and "HİÇBİR EK ÜCRET" in fc[0]["summary"]
    # tekrar evaluate → aynı FREE-CYCLE maddesi yeniden kuyruğa girmemeli
    ev.evaluate(mid)
    assert len([i for i in ApprovalQueue(db=db).pending()
                if i["kind"] == "FREE_CYCLE"]) == 1


@pytest.fixture
def svc_db(db):
    from answrank.monitor.service import MonitorService
    svc = MonitorService(db=db)
    mid = svc.add(domain="delta-q.example", brand="DQ", sector="general",
                  contract_id="SZ-Q")
    for sc in (40.0, 45.0):  # +5 < 12 → TRIGGERED
        asyncio.run(svc.run_one(mid, executor=_mk_measured(score=sc),
                                now=datetime(2026, 9, 12 if sc == 40.0 else 14)))
    return db, svc, mid


# ------------------------------------------------------------------ CLI / API
def test_queue_cli_scan_list_approve(db, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(db.db_path))
    from answrank.cli import main
    argv = ["answrank", "queue", "list"]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert "kuyruk boş" in " ".join(capsys.readouterr().out.split()).lower()
    from answrank.queue import ApprovalQueue
    iid = ApprovalQueue(db=db).add(kind="DM", ref_id="z.example", summary="x")
    iid = ApprovalQueue(db=db).pending()[0]["id"]
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "approve", str(iid),
                                      "--note", "gönderildi"])
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "APPROVED" in out and "gönderildi" in out
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "list"])
    main()
    assert "kuyruk boş" in " ".join(capsys.readouterr().out.split()).lower()


def test_queue_api_decide_and_404(db, monkeypatch):
    from answrank.api import app as appmod
    monkeypatch.setattr(appmod, "db", db)
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    client = TestClient(app)
    from answrank.queue import ApprovalQueue
    ApprovalQueue(db=db).add(kind="MONITOR_INTERVENTION", ref_id="mon_1", summary="3 ölçüm hatası")
    items = client.get("/api/queue").json()["items"]
    assert items[0]["kind"] == "MONITOR_INTERVENTION"
    r = client.post(f"/api/queue/{items[0]['id']}/decision",
                    json={"action": "reject", "note": "erişim müşteriden istendi"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    r2 = client.post("/api/queue/777/decision", json={"action": "approve", "note": ""})
    assert r2.status_code == 404 and "uydurma" in r2.json()["detail"]
    # çift karar → 409
    assert client.post(f"/api/queue/{items[0]['id']}/decision",
                       json={"action": "approve", "note": ""}).status_code == 409


def test_dashboard_queue_card_hook():
    tpl = open("answrank/api/templates/dashboard.html", encoding="utf-8").read()
    assert "Onay Kuyruğu" in tpl and "/api/queue" in tpl


def test_queue_cli_scan_list_with_items_and_decision_errors(db, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    from answrank.queue import ApprovalQueue
    monkeypatch.setattr(settings, "db_path", str(db.db_path))
    with db._get_connection() as c:
        c.execute("INSERT INTO miniprobe_leads (domain, verdict, robots_line, llms_line,"
                  " bots_line, measured, created_at) VALUES (?,?,?,?,?,?,?)",
                  ("tara.example", "TEMİZ", "İZİNLİ", "VAR", "3/3", 1, "2026-09-16T00:00:00"))
        c.commit()
    from answrank.cli import main
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "scan"])
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "1 yeni karar maddesi" in out
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "list"])
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "tara.example" in out and "DM" in out
    iid = ApprovalQueue(db=db).pending()[0]["id"]
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "approve", str(iid)])
    main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "reject", str(iid),
                                      "--note", "çift karar denemesi"])
    main()
    assert "karar verilmiş" in " ".join(capsys.readouterr().out.split())
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "approve", "424242"])
    main()
    assert "uydurma karar" in " ".join(capsys.readouterr().out.split())
