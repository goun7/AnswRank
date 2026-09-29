"""E13b: DM gönderim kanalı — onay sonrası tek sorumlu adım."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from answrank.config import settings
from answrank.db import Database
from answrank.models import CitationQueryItem, CitationRunResult
from answrank.probe.miniprobe import MiniProbeResult
from answrank.queue import ApprovalQueue
from answrank.dm_dispatch import DmDispatcher


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "disp.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", p)
    monkeypatch.setattr(settings, "db_path", p)
    return Database()


def _seed(db, domain, email="info@example.com", measured=1):
    asyncio.run(db.save_miniprobe_lead(MiniProbeResult(
        domain=domain, verdict="TEMİZ", robots_line="İZİNLİ", llms_line="VAR",
        bots_line="3/3", blocked_bots=[], probed=3, measured=bool(measured))))
    asyncio.run(db.save_citations(CitationRunResult(
        run_id=f"d-{domain}", brand_name="X", domain=domain, sector="dental",
        city="Dubai", total_runs=8, brand_citations_found=1,
        citation_rate_percentage=12.5, is_fully_live=True,
        live_items_count=8, live_response_rate_percentage=100.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                model="test-model", was_simulated=False,
                                brand_mentioned=i == 0) for i in range(8)])))
    with db._get_connection() as conn:
        conn.execute("DELETE FROM prospects WHERE domain_ref = ?", (domain,))
        conn.execute(
            "INSERT INTO prospects (brand_name, domain_ref, phone, email, city,"
            " sector, status, source_url, verified_at, http_status,"
            " contact_source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("X", domain, "+971500000000", email, "Dubai", "dental", "lead",
             "src", datetime.now(timezone.utc).isoformat(), 200, "page-text"))
        conn.commit()


def _approved_item(db, domain):
    """Tarayıp onaylanmış bir kuyruk maddesinin kimliğini döndür."""
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    return item["id"]


def test_pending_item_never_sent(db):
    _seed(db, "p.example")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "reddedildi"
    assert "onaysız" in out["why"]


def test_unverified_recipient_blocked(db):
    """E-posta DOĞRULANAMADI — karanlık gönderim yok."""
    _seed(db, "u.example", email="DOĞRULANAMADI")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "hedef-yok"


def test_no_recipient_record_blocked(db):
    _seed(db, "n.example")
    # prospects satırını sil — alıcı kaydı yok
    with db._get_connection() as conn:
        conn.execute("DELETE FROM prospects WHERE domain_ref = ?", ("n.example",))
        conn.commit()
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "hedef-yok"


def test_unconfigured_smtp_is_honest_not_faked(db):
    """SMTP yoksa 'YAPILANDIRILMAMIŞ' — başarılı gönderim uydurulmaz."""
    _seed(db, "s.example")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    d = DmDispatcher(db=db)
    assert d.smtp_configured() is False
    out = d.send_approved(item["id"])
    assert out["result"] == "yapilandirilmamis"
    with db._get_connection() as conn:
        row = conn.execute("SELECT status FROM dm_send_log WHERE queue_id=?",
                           (item["id"],)).fetchone()
    assert row["status"] == "YAPILANDIRILMAMIŞ"


def test_dry_run_writes_nothing(db):
    _seed(db, "dr.example")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    DmDispatcher(db=db).send_approved(item["id"], dry_run=True)
    with db._get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM dm_send_log").fetchone()
    assert n["c"] == 0


def test_approved_sends_via_mocked_smtp(db, monkeypatch):
    _seed(db, "ok.example")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    monkeypatch.setenv("ANSWRANK_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ANSWRANK_SMTP_USER", "u")
    monkeypatch.setenv("ANSWRANK_SMTP_PASS", "p")
    monkeypatch.setenv("ANSWRANK_SMTP_FROM", "from@example.com")
    calls = {"n": 0}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=30): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): pass
        def login(self, u, p): pass
        def send_message(self, msg): calls["n"] += 1
    monkeypatch.setattr("answrank.dm_dispatch.smtplib.SMTP", _FakeSMTP)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "sent"
    assert calls["n"] == 1
    with db._get_connection() as conn:
        row = conn.execute("SELECT status, recipient FROM dm_send_log"
                           " WHERE queue_id=?", (item["id"],)).fetchone()
    assert row["status"] == "GÖNDERİLDİ"
    assert row["recipient"] == "info@example.com"


def test_send_is_idempotent(db, monkeypatch):
    """Aynı madde iki kez gönderilemez."""
    _seed(db, "idem.example")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    monkeypatch.setenv("ANSWRANK_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ANSWRANK_SMTP_USER", "u")
    monkeypatch.setenv("ANSWRANK_SMTP_PASS", "p")
    calls = []
    class _FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): pass
        def login(self, u, p): pass
        def send_message(self, msg): calls.append(msg)
    monkeypatch.setattr("answrank.dm_dispatch.smtplib.SMTP", _FakeSMTP)
    d = DmDispatcher(db=db)
    d.send_approved(item["id"])
    # Observe both the external effect and the structured duplicate result.
    out = d.send_approved(item["id"])
    assert out["result"] == "already-attempted"
    assert len(calls) == 1, "A duplicate request must not reach SMTP twice"


def test_cli_send_dry_run_and_pending(monkeypatch, tmp_path):
    """CLI 'queue send' — onaysız madde reddedilir, SMTP yoksa dürüst."""
    import sys, io, contextlib
    dbp = str(tmp_path / "cli.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp)
    monkeypatch.setattr(settings, "db_path", dbp)

    def _run(argv):
        monkeypatch.setattr(sys, "argv", ["answrank"] + argv)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            from answrank.cli import main
            main()
        return out.getvalue()

    # kapatma: mini-probe var ama PENDING (onay yok)
    asyncio.run(Database().save_miniprobe_lead(MiniProbeResult(
        domain="cli.example", verdict="TEMİZ", robots_line="İZİNLİ",
        llms_line="VAR", bots_line="3/3", blocked_bots=[], probed=3,
        measured=True)))
    ApprovalQueue(db=Database()).scan()
    out = _run(["queue", "send", "1", "--dry-run"])
    assert "reddedildi" in out


def test_smtp_failure_logs_error_not_sent(db, monkeypatch):
    """SMTP hatası 'GÖNDERİLDİ' değil 'HATA' olarak kaydolur."""
    _seed(db, "err.example")
    q = ApprovalQueue(db=db); q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    monkeypatch.setenv("ANSWRANK_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ANSWRANK_SMTP_USER", "u")
    monkeypatch.setenv("ANSWRANK_SMTP_PASS", "p")
    class _Boom:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): raise OSError("baglanti yok")
        def login(self, u, p): pass
        def send_message(self, m): pass
    monkeypatch.setattr("answrank.dm_dispatch.smtplib.SMTP", _Boom)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "error"
    with db._get_connection() as conn:
        row = conn.execute("SELECT status, note FROM dm_send_log"
                           " WHERE queue_id=?", (item["id"],)).fetchone()
    assert row["status"] == "HATA"
    assert "OSError" in row["note"]  # sınıf adı yazılır, içerik degil


def test_changed_recipient_during_send_cannot_send_twice(db, monkeypatch):
    """Alıcı değişse de tek kuyruk onayı ikinci SMTP girişimi vermez."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _seed(db, "inflight.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    entered, release = Event(), Event()
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(recipient)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=5), "İlk girişim serbest bırakılmadı"
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(DmDispatcher(db=db).send_approved, item["id"])
        try:
            assert entered.wait(timeout=5), "İlk SMTP sınırına ulaşılmadı"
            with db._get_connection() as conn:
                conn.execute("UPDATE prospects SET email=? WHERE domain_ref=?",
                             ("changed@example.com", "inflight.example"))
                conn.commit()
            second = DmDispatcher(db=db).send_approved(item["id"])
        finally:
            release.set()
        assert first.result(timeout=5)["result"] == "sent"
    assert len(calls) == 1, "Alıcı değişikliği aynı onaydan ikinci SMTP üretti"
    assert second["result"] == "already-attempted"


def test_hata_reservation_survives_disk_reopen_and_recipient_change(db, monkeypatch):
    """Belirsiz SMTP girişimi, yeniden açılış/alıcı değişimiyle tekrar denenmez."""
    _seed(db, "uncertain.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    calls = []

    def interrupted(self, recipient, subject, body):
        calls.append(recipient)
        raise RuntimeError("SMTP sınırı sonrası belirsiz kesinti")

    monkeypatch.setattr(DmDispatcher, "_smtp_send", interrupted)
    with pytest.raises(RuntimeError, match="belirsiz kesinti"):
        DmDispatcher(db=db).send_approved(item["id"])
    reopened = Database(db_path=db.db_path)
    with reopened._get_connection() as conn:
        before = dict(conn.execute(
            "SELECT * FROM dm_send_log WHERE queue_id=?", (item["id"],)
        ).fetchone())
        assert before["status"] == "HATA"
        assert "mutabakat" in before["note"]
        conn.execute("UPDATE prospects SET email=? WHERE domain_ref=?",
                     ("new@example.com", "uncertain.example"))
        conn.commit()
    out = DmDispatcher(db=reopened).send_approved(item["id"])
    assert out["result"] == "already-attempted"
    assert calls == ["info@example.com"]
    with reopened._get_connection() as conn:
        rows = conn.execute("SELECT * FROM dm_send_log WHERE queue_id=?",
                            (item["id"],)).fetchall()
    assert [dict(row) for row in rows] == [before]


@pytest.mark.parametrize("invalid", ["missing", "corrupt", "simulated", "new-invalid", "unmeasured"])
def test_approved_without_visibility_never_reaches_smtp(db, monkeypatch, invalid):
    """İnsan onayı, eksik görünürlük kanıtının yerine geçmez."""
    _seed(db, "no-evidence.example")
    if invalid == "missing":
        with db._get_connection() as conn:
            conn.execute("DELETE FROM citations")
            conn.commit()
    elif invalid == "corrupt":
        with db._get_connection() as conn:
            conn.execute("UPDATE citations SET raw_json='{bad' WHERE run_id=?",
                         ("d-no-evidence.example",))
            conn.commit()
    elif invalid == "simulated":
        with db._get_connection() as conn:
            conn.execute("UPDATE citations SET raw_json=? WHERE run_id=?",
                         ('{"is_fully_live": false}', "d-no-evidence.example"))
            conn.commit()
    elif invalid == "new-invalid":
        asyncio.run(db.save_citations(CitationRunResult(
            run_id="new-invalid", brand_name="X", domain="no-evidence.example",
            sector="dental", city="Dubai", is_fully_live=False)))
    if invalid != "unmeasured":
        assert db.get_dm_visibility("no-evidence.example") is None
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    if invalid == "unmeasured":
        with db._get_connection() as conn:
            conn.execute("UPDATE miniprobe_leads SET measured=0")
            conn.commit()
        assert db.latest_measured_lead("no-evidence.example") is None
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert calls == [], "Görünürlük kanıtı yokken SMTP sınırına ulaşıldı"
    assert out["result"] == "evidence-blocked"
    with db._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0] == 0


def test_auto_approved_invalid_evidence_also_blocked(db, monkeypatch):
    """AUTO_APPROVED da kanıt şartını atlatamaz; gönderim durdurulur."""
    _seed(db, "auto.example")
    with db._get_connection() as conn:
        conn.execute("DELETE FROM citations")
        conn.commit()
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    with db._get_connection() as conn:
        conn.execute("UPDATE approval_queue SET status='AUTO_APPROVED',"
                     " decided_at=? WHERE id=?",
                     (datetime.now(timezone.utc).isoformat(), item["id"]))
        conn.commit()
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert calls == []
    assert out["result"] == "evidence-blocked"
    with db._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0] == 0


def test_blocked_send_sends_once_after_evidence_repaired(db, monkeypatch):
    """Kanıt onarılınca madde PENDING'e açılır; yeniden onay tam bir kez gönderir."""
    _seed(db, "repair.example")
    with db._get_connection() as conn:
        conn.execute("DELETE FROM citations")
        conn.commit()
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    blocked = DmDispatcher(db=db).send_approved(item["id"])
    assert blocked["result"] == "evidence-blocked"
    with db._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0] == 0
        st = conn.execute("SELECT status FROM approval_queue WHERE id=?",
                          (item["id"],)).fetchone()
    assert st["status"] == "PENDING", "eskimiş onay insan için geri açılmalı"
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="repaired", brand_name="X", domain="repair.example",
        sector="dental", city="Dubai", total_runs=2, brand_citations_found=1,
        citation_rate_percentage=50.0, is_fully_live=True, live_items_count=2,
        live_response_rate_percentage=100.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                 model="test-model", was_simulated=False,
                                 brand_mentioned=i == 0) for i in range(2)])))
    q.decide(item["id"], True, note="insan, kanıt onarildi")
    sent = DmDispatcher(db=db).send_approved(item["id"])
    assert sent["result"] == "sent"
    assert len(calls) == 1, "Onarım sonrası tam bir gönderim beklenir"
    with db._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dm_send_log"
                            " WHERE status='GÖNDERİLDİ'").fetchone()[0] == 1


def test_noop_results_are_log_idempotent(db, monkeypatch):
    """Yapılandırmasız/hedef-yok tekrar çağrı aynı sonucu yazar;
    IntegrityError üretmez, ikinci satır açmaz."""
    _seed(db, "noop.example", email="DOĞRULANAMADI")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    d = DmDispatcher(db=db)
    first = d.send_approved(item["id"])
    assert first["result"] == "hedef-yok"
    second = d.send_approved(item["id"])
    assert second["result"] == "hedef-yok"
    with db._get_connection() as conn:
        rows = conn.execute("SELECT status FROM dm_send_log WHERE queue_id=?",
                            (item["id"],)).fetchall()
    assert len(rows) == 1, f"{len(rows)} satır — no-op idempotent değil"


def test_stale_measurement_after_approval_blocks_send(db, monkeypatch):
    """Onay taze ölçümle alındı; gönderim anında bayatladıysa DM gitmez."""
    _seed(db, "stale-after-approve.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    # onay geçerliydi; şimdi ölçümü 30 gün bayatlat (satır + raw_json tutarlı)
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with db._get_connection() as conn:
        row = conn.execute("SELECT raw_json FROM citations WHERE domain=?",
                           ("stale-after-approve.example",)).fetchone()
        raw = json.loads(row["raw_json"])
        raw["timestamp"] = old
        conn.execute("UPDATE citations SET created_at=?, raw_json=? WHERE domain=?",
                     (old, json.dumps(raw), "stale-after-approve.example"))
        conn.commit()
    assert db.get_dm_visibility("stale-after-approve.example") is not None, (
        "doğrulayıcı hâlâ geçerli olmalı — kapanan şey tazelik")
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert calls == [], "Bayat ölçümle SMTP sınırına ulaşıldı"
    assert out["result"] == "evidence-blocked"
    assert "taze" in out["why"]
    with db._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0] == 0


def test_fresh_measurement_after_approval_sends_once(db, monkeypatch):
    """Taze kanıt korunduğunda normal gönderim-regresyon."""
    _seed(db, "fresh-after-approve.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "sent"
    assert len(calls) == 1


def test_send_blocked_when_evidence_run_changed_after_approval(db, monkeypatch):
    """Onay sonrası FARKLI geçerli bir koşu gelirse eski/onaysız gövde gitmez."""
    _seed(db, "bind-change.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="changed-run", brand_name="X", domain="bind-change.example",
        sector="dental", city="Dubai", total_runs=2, brand_citations_found=1,
        citation_rate_percentage=50.0, is_fully_live=True, live_items_count=2,
        live_response_rate_percentage=100.0, grounding_status={"m": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}", model="m",
               was_simulated=False, brand_mentioned=i == 0) for i in range(2)])))
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert calls == [], "Onay dışı koşuyla SMTP sınırına ulaşıldı"
    assert out["result"] == "evidence-blocked"
    assert "değişti" in out["why"]
    with db._get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0] == 0
        st = conn.execute("SELECT status, decision_note FROM approval_queue WHERE id=?",
                          (item["id"],)).fetchone()
    assert st["status"] == "PENDING", "eskimiş onay geri açılmalı"
    assert "kanıt değişti" in st["decision_note"], "orijinal karar notta kalmalı"
    # yeniden onay güncel koşuyla bağlanır
    q.decide(item["id"], True, note="insan, güncel kanıt")
    out2 = DmDispatcher(db=db).send_approved(item["id"])
    assert out2["result"] == "sent"
    assert len(calls) == 1


def test_legacy_approval_without_run_id_blocked(db, monkeypatch):
    """Göç öncesi onay (run kimliği NULL) gönderilemez — yeniden onay gerekir."""
    _seed(db, "legacy-bind.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    with db._get_connection() as conn:
        conn.execute("UPDATE approval_queue SET evidence_run_id=NULL WHERE id=?",
                     (item["id"],))
        conn.commit()
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert calls == []
    assert out["result"] == "evidence-blocked"
    assert "run kimliği" in out["why"]
    with db._get_connection() as conn:
        st = conn.execute("SELECT status FROM approval_queue WHERE id=?",
                          (item["id"],)).fetchone()
    assert st["status"] == "PENDING", "göç öncesi onay da geri açılmalı"


def test_legacy_dry_run_row_allows_later_real_send(db, monkeypatch):
    """Kalıcı DRY_RUN satırı (eski DB) gerçek gönderimi engellemez:
    dry-run'da SMTP hiç çağrılmamıştı."""
    _seed(db, "legacy-dry.example")
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    q.decide(item["id"], True, note="insan")
    d = DmDispatcher(db=db)
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    assert d.send_approved(item["id"], dry_run=True)["result"] == "dry-run"
    with db._get_connection() as conn:
        conn.execute("INSERT INTO dm_send_log (queue_id, domain, recipient,"
                     " status, note, sent_at) VALUES (?,?,?,?,'legacy dry-run',?)",
                     (item["id"], "legacy-dry.example", "info@example.com",
                      "DRY_RUN", datetime.now(timezone.utc).isoformat()))
        conn.commit()
    calls = []
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)

    def smtp(self, recipient, subject, body):
        calls.append(body)
        return {"ok": True}

    monkeypatch.setattr(DmDispatcher, "_smtp_send", smtp)
    out = d.send_approved(item["id"])
    assert out["result"] == "sent", "kalıcı DRY_RUN satırı gerçek gönderimi engelledi"
    assert len(calls) == 1


def test_unproven_recipient_is_rejected(db):
    """E-posta ad-resi dolu olsa bile kanıtı yoksa 'doğrulandı' sayılmaz."""
    _seed(db, "unproven.example", email="info@unproven.example")
    with db._get_connection() as conn:
        conn.execute("UPDATE prospects SET verified_at=NULL,"
                     " http_status=NULL, contact_source=NULL"
                     " WHERE domain_ref='unproven.example'")
        conn.commit()
    out = DmDispatcher(db=db).send_approved(_approved_item(db, "unproven.example"))
    assert out["result"] == "hedef-yok"
    assert "DOĞRULANAN" in out["why"]


def test_failed_crawl_recipient_is_rejected(db):
    """Başarısız HTTP taramasından kalan e-posta gönderim hedefi olamaz."""
    _seed(db, "failed.example", email="info@failed.example")
    with db._get_connection() as conn:
        conn.execute("UPDATE prospects SET http_status=503,"
                     " contact_source=NULL WHERE domain_ref='failed.example'")
        conn.commit()
    out = DmDispatcher(db=db).send_approved(_approved_item(db, "failed.example"))
    assert out["result"] == "hedef-yok"


def test_placeholder_recipient_is_rejected(db):
    """Yer-tutucu ad-res geçerli 'doğrulanmış' alıcı olarak işlenemez."""
    _seed(db, "placeholder.example", email="bilgi@")
    out = DmDispatcher(db=db).send_approved(_approved_item(db, "placeholder.example"))
    assert out["result"] == "hedef-yok"


def test_valid_recipient_accepted(db):
    _seed(db, "ok.example", email="info@ok.example")
    out = DmDispatcher(db=db).send_approved(_approved_item(db, "ok.example"))
    assert out["result"] != "hedef-yok"


def test_non_dm_item_skipped(db):
    """CONTRACT maddesi gönderilmez — atlanır."""
    _seed(db, "nd.example")
    q = ApprovalQueue(db=db)
    q.add("CONTRACT", "nd.example", "sozlesme")
    item = [x for x in q.pending() if x["kind"] == "CONTRACT"][0]
    out = DmDispatcher(db=db).send_approved(item["id"])
    assert out["result"] == "atlandı"


def test_stale_evidence_blocks_send_at_send_time(db, monkeypatch):
    """Onay taze ölçümle alındıktan sonra kanıt bayatladıysa DM gitmez
    (gönderim-anı tazelik guard'ı). Red 'evidence-blocked' ile gelir."""
    from answrank.queue_gates import FRESH_DAYS
    from datetime import datetime, timedelta, timezone

    _seed(db, "stale.example", email="info@stale.example")
    item_id = _approved_item(db, "stale.example")

    old = (datetime.now(timezone.utc) - timedelta(days=FRESH_DAYS + 30))
    vis = db.get_dm_visibility("stale.example") or {}
    assert vis, "test verisi geçerli kanıt üretmeli — fixture bozuk"
    # raw_json içindeki timestamp da created_at ile birlikte bayatlatılmalı;
    # aksi halde fail-closed okuyucu tutarsızlık nedeniyle kanıtı reddeder.
    import json as _json
    with db._get_connection() as conn:
        row = conn.execute("SELECT raw_json FROM citations WHERE domain=?",
                           ("stale.example",)).fetchone()
        raw = _json.loads(row["raw_json"])
        raw["timestamp"] = old.isoformat()
        conn.execute("UPDATE citations SET created_at=?, raw_json=? WHERE domain=?",
                     (old.isoformat(), _json.dumps(raw), "stale.example"))
        conn.commit()

    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    out = DmDispatcher(db=db).send_approved(item_id)
    assert out["result"] == "evidence-blocked"
    assert "taze" in out["why"]


def test_stale_reason_reports_missing_and_unreadable(db):
    """_stale_reason hiç kanıt yoksa ve tarih okunamazsa neden dönmeli."""
    d = DmDispatcher(db=db)
    assert d._stale_reason(None, 30) == "geçerli son kanıt yok"
    assert d._stale_reason({"created_at": "tarih-degil"}, 30) == \
        "ölçüm tarihi okunamadı"


def test_missing_queue_item_raises_keyerror(db):
    """Olmayan kuyruk maddesi KeyError vermeli — sessiz başarı olmaz."""
    import pytest as _pytest
    with _pytest.raises(KeyError):
        DmDispatcher(db=db).send_approved(999999)


def test_repeat_send_after_failed_claim_is_already_attempted(db, monkeypatch):
    """Denenmiş gönderim (HATA/HEDEF_YOK) tekrar denenip gönderilmez;
    'already-attempted' döner."""
    _seed(db, "retry.example", email="info@retry.example")
    item_id = _approved_item(db, "retry.example")

    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    monkeypatch.setattr(DmDispatcher, "_smtp_send",
                        lambda self, *a, **k: {"ok": False, "error": "SMTP-error"})

    first = DmDispatcher(db=db).send_approved(item_id)
    assert first["result"] != "already-attempted"
    second = DmDispatcher(db=db).send_approved(item_id)
    assert second["result"] == "already-attempted"


def test_recipient_without_contact_source_is_rejected(db):
    """Sayfadan değil de manuel girilen kontak contact_source olmadan reddedilmeli
    — kaynaksız alıcı karanlık gönderime yol açar."""
    _seed(db, "manual.example", email="info@manual.example")
    item_id = _approved_item(db, "manual.example")
    with db._get_connection() as conn:
        conn.execute("UPDATE prospects SET contact_source=NULL WHERE domain_ref=?",
                     ("manual.example",))
        conn.commit()
    out = DmDispatcher(db=db).send_approved(item_id)
    assert out["result"] == "hedef-yok"


def test_body_without_measurement_is_none(db):
    """Ölçüm yoksa gövde None dönmeli — uydurma DM metni üretilmez."""
    _seed(db, "nobody.example", email="info@nobody.example")
    with db._get_connection() as conn:
        conn.execute("DELETE FROM citations WHERE domain=?", ("nobody.example",))
        conn.commit()
    d = DmDispatcher(db=db)
    assert d._body("nobody.example", None) is None


def test_repeat_send_of_non_reusable_status_is_rejected(db, monkeypatch):
    """GÖNDERİLDİ/HATA/HEDEF_YOK kaydı tekrar kullanılamaz — 'already-attempted'."""
    _seed(db, "sent.example", email="info@sent.example")
    item_id = _approved_item(db, "sent.example")
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note, sent_at)"
            " VALUES (?,?,?,?,?,?)",
            (item_id, "sent.example", "info@sent.example", "GÖNDERİLDİ",
             "önceki", datetime.now(timezone.utc).isoformat()))
        conn.commit()
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    out = DmDispatcher(db=db).send_approved(item_id)
    assert out["result"] == "already-attempted"


def test_stale_reason_normalizes_naive_timestamp(db):
    """Naive (tzinfo'suz) ölçüm tarihi UTC varsayılmalı; geçerli sayılıp
    tazelik hesaplanmalı, hata dönmeli."""
    d = DmDispatcher(db=db)
    naive = "2026-09-17T00:00:00"
    assert d._stale_reason({"created_at": naive}, 30) == ""
    assert d._stale_reason({"created_at": naive}, 0).startswith("ölçüm")


def test_reopen_stale_approval_swallows_concurrent_decision_change(db):
    """Başka bir süreç onayı zaten değiştirdiyse (rowcount 0) RuntimeError
    atılmamalidir. Gönderim çökmek yerine evidence-blocked ile dönmeli;
    call site zaten 'PENDING\'e açildi' diye rapor verir."""
    _seed(db, "race.example", email="info@race.example")
    item_id = _approved_item(db, "race.example")
    d = DmDispatcher(db=db)
    with db._get_connection() as conn:
        conn.execute("UPDATE approval_queue SET status='REJECTED' WHERE id=?",
                     (item_id,))
        conn.commit()
    # Hata firlatilmamali; call site evidence-blocked ile doner.
    d._reopen_stale_approval(item_id, "run-a", "run-b", "APPROVED")


def test_reopen_stale_approval_reports_blocked_when_race(db, monkeypatch):
    """Kanıt onaydan sonra değişip onay hâlâ APPROVED iken reopen çağrılırsa,
    gönderim evidence-blocked dönmeli — RuntimeError ile çökmemeli."""
    _seed(db, "race2.example", email="info@race2.example")
    item_id = _approved_item(db, "race2.example")
    # Kanıtı yeni bir run ile değiştir → approved_run != latest_run → reopen tetiklenir
    from answrank.models import CitationRunResult, CitationQueryItem
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="run-changed", brand_name="X", domain="race2.example",
        sector="dental", city="Dubai", total_runs=8, brand_citations_found=1,
        citation_rate_percentage=12.5, is_fully_live=True,
        live_items_count=8, live_response_rate_percentage=100.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                 model="test-model", was_simulated=False,
                                 brand_mentioned=i == 0) for i in range(8)])))
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    out = DmDispatcher(db=db).send_approved(item_id)
    assert out["result"] == "evidence-blocked"
    assert "PENDING" in out["why"]
    with db._get_connection() as conn:
        st = conn.execute("SELECT status FROM approval_queue WHERE id=?",
                          (item_id,)).fetchone()
    assert st["status"] == "PENDING"


def test_non_reusable_record_for_other_recipient_blocks_claim(db):
    """Başka alıcıya ait denemiş kayıt varken yeni alıcı için claim reddedilir
    (attempted sorgusu, 228). Bir onay = bir deneme, alıcı başına değil."""
    _seed(db, "dryclaim.example", email="info@dryclaim.example")
    item_id = _approved_item(db, "dryclaim.example")
    d = DmDispatcher(db=db)
    rcpt = d.recipient_for("dryclaim.example")
    assert rcpt
    # FARKLI alıcıda HATA: attempt-filter bunu yakalar ve 228'den döner
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note, sent_at)"
            " VALUES (?,?,?,?,?,?)",
            (item_id, "dryclaim.example", "onceki@baska.example", "HATA",
             "önceki hata", datetime.now(timezone.utc).isoformat()))
        conn.commit()
    assert d._claim_send(item_id, "dryclaim.example", rcpt) is False


def test_hedef_yok_record_for_same_recipient_blocks_claim(db):
    """HEDEF_YOK 'denendi' listesinde değildir ama yeniden kullanılmaz; aynı
    alıcı için existing-238 dalı üzerinden de reddedilir."""
    _seed(db, "hedef.example", email="info@hedef.example")
    item_id = _approved_item(db, "hedef.example")
    d = DmDispatcher(db=db)
    rcpt = d.recipient_for("hedef.example")
    assert rcpt
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note, sent_at)"
            " VALUES (?,?,?,?,?,?)",
            (item_id, "hedef.example", rcpt, "HEDEF_YOK", "alıcı yok",
             datetime.now(timezone.utc).isoformat()))
        conn.commit()
    assert d._claim_send(item_id, "hedef.example", rcpt) is False


def test_send_approved_reports_already_attempted_after_prior_error(db, monkeypatch):
    """Önceki HATA kaydı varken gönderim 'already-attempted' dönmeli
    (send_approved içi, _claim_send False)."""
    _seed(db, "again.example", email="info@again.example")
    item_id = _approved_item(db, "again.example")
    d = DmDispatcher(db=db)
    rcpt = d.recipient_for("again.example")
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note, sent_at)"
            " VALUES (?,?,?,?,?,?)",
            (item_id, "again.example", rcpt, "HATA", "önceki",
             datetime.now(timezone.utc).isoformat()))
        conn.commit()
    monkeypatch.setattr(DmDispatcher, "smtp_configured", lambda self: True)
    out = d.send_approved(item_id)
    assert out["result"] == "already-attempted"
