"""E13: çok-kapılı DM denetimi — otomatik onayın riskli yarısı güvenli kılınır."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from answrank.config import settings
from answrank.db import Database
from answrank.models import CitationQueryItem, CitationRunResult
from answrank.probe.miniprobe import MiniProbeResult
from answrank.queue import ApprovalQueue
from answrank.queue_gates import DmGateAuditor


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "gates.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", p)
    monkeypatch.setattr(settings, "db_path", p)
    return Database()


def _seed_measurement(db, domain, days_ago=1, total=8, found=1, fully_live=True):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    asyncio.run(db.save_citations(CitationRunResult(
        run_id=f"g-{domain}", brand_name="X", domain=domain, sector="dental",
        city="Dubai", total_runs=total, brand_citations_found=found,
        citation_rate_percentage=round(100 * found / total, 1), timestamp=ts,
        live_items_count=total if fully_live else 0,
        live_response_rate_percentage=100.0 if fully_live else 0.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                 model="test-model", was_simulated=not fully_live,
                                 brand_mentioned=i < found) for i in range(total)],
        is_fully_live=fully_live)))


def _seed_probe(db, domain):
    asyncio.run(db.save_miniprobe_lead(MiniProbeResult(
        domain=domain, verdict="TEMİZ", robots_line="İZİNLİ", llms_line="VAR",
        bots_line="3/3", blocked_bots=[], probed=3, measured=True)))


def _seed_prospect(db, domain, phone="5000", email=None):
    with db._get_connection() as conn:
        conn.execute("DELETE FROM prospects WHERE domain_ref = ?", (domain,))
        conn.execute(
            "INSERT INTO prospects (brand_name, domain_ref, phone, email, city,"
            " sector, status, source_url, verified_at) VALUES (?,?,?,?,?,?,?,?," "?)",
            ("X", domain, phone, email, "Dubai", "dental", "lead", "src",
             datetime.now(timezone.utc).isoformat()))
        conn.commit()


# --- kapıların tek tek çalışması ------------------------------------------

def test_all_gates_pass_then_auto_eligible(db):
    _seed_measurement(db, "a.example", total=8, found=1)
    _seed_probe(db, "a.example")
    _seed_prospect(db, "a.example", phone="+971500000000")
    auditor = DmGateAuditor(db=db)
    out = auditor.audit("a.example", dm_text="8 soruda 1 vuruş (kalan 7)")
    assert out["all_passed"] is True
    assert [g["gate"] for g in out["gates"]] == [
        "ölçüm-var", "mini-probe-var", "taze-ölçüm",
        "iletişim-doğrulandı", "tekerrür-yok", "içerik-izlenebilir"]


def test_no_measurement_blocks(db):
    _seed_probe(db, "b.example")
    _seed_prospect(db, "b.example", phone="+971500000001")
    out = DmGateAuditor(db=db).audit("b.example")
    assert out["all_passed"] is False
    assert out["gates"][0]["passed"] is False


def test_stale_measurement_blocks(db):
    _seed_measurement(db, "c.example", days_ago=30)
    _seed_probe(db, "c.example")
    _seed_prospect(db, "c.example", phone="+971500000002")
    out = DmGateAuditor(db=db).audit("c.example")
    fresh = [g for g in out["gates"] if g["gate"] == "taze-ölçüm"][0]
    assert fresh["passed"] is False and "taze değil" in fresh["reason"]
    assert out["all_passed"] is False


def test_unverified_contact_blocks(db):
    """Telefon ve e-posta DOĞRULANAMADI — karanlık gönderim yok."""
    _seed_measurement(db, "d.example", total=8, found=0)
    _seed_probe(db, "d.example")
    _seed_prospect(db, "d.example", phone="DOĞRULANAMADI",
                   email="DOĞRULANAMADI")
    out = DmGateAuditor(db=db).audit("d.example")
    g = [x for x in out["gates"] if x["gate"] == "iletişim-doğrulandı"][0]
    assert g["passed"] is False and "DOĞRULANAMADI" in g["reason"]
    assert out["all_passed"] is False


def test_traceable_content_rejects_invented_numbers(db):
    _seed_measurement(db, "e.example", total=8, found=1)
    _seed_probe(db, "e.example")
    _seed_prospect(db, "e.example", phone="+971500000004")
    auditor = DmGateAuditor(db=db)
    good = auditor.audit("e.example", dm_text="8 soruda 1 vuruş")
    assert good["all_passed"] is True
    bad = auditor.audit("e.example", dm_text="8 soruda 99 vuruş")
    g = [x for x in bad["gates"] if x["gate"] == "içerik-izlenebilir"][0]
    assert g["passed"] is False and "izlenemeyen sayı" in g["reason"]
    assert bad["all_passed"] is False


def test_stamp_digits_cannot_whitelist_invented_numbers(db):
    """Koşu tarihindeki rakamlar uydurma sayıları meşrulaştıramaz —
    damga yalnız kendi tam dizisi olarak kanıttır, alt-dizgi kaynağı değil."""
    import re as _re
    _seed_measurement(db, "n.example", total=8, found=1)
    _seed_probe(db, "n.example")
    _seed_prospect(db, "n.example")
    with db._get_connection() as conn:
        created = conn.execute(
            "SELECT created_at FROM citations WHERE domain='n.example'"
        ).fetchone()["created_at"]
    assert "00" in _re.sub(r"\D", "", created)  # UTC damgası +00:00 taşır
    out = DmGateAuditor(db=db).audit("n.example", dm_text="8 soruda 00 vuruş")
    g = [x for x in out["gates"] if x["gate"] == "içerik-izlenebilir"][0]
    assert g["passed"] is False and "izlenemeyen sayı" in g["reason"]


def test_recent_auto_approve_blocks_repeat(db):
    """Aynı domain'e 14 gün içinde tekrar temas yok (onay taahhüdü de sayılır)."""
    _seed_measurement(db, "f.example", total=8, found=0)
    _seed_probe(db, "f.example")
    _seed_prospect(db, "f.example", phone="+971500000005")
    q = ApprovalQueue(db=db)
    q.add("DM", "f.example", "önceki")
    row = q.pending()[0]
    q.decide(row["id"], True, note="insan")
    # AUTO_APPROVED olarak işaretle (denetim sonrası durum)
    with db._get_connection() as conn:
        conn.execute("UPDATE approval_queue SET status='AUTO_APPROVED' WHERE id=?",
                     (row["id"],))
        conn.commit()
    out = DmGateAuditor(db=db).audit("f.example")
    g = [x for x in out["gates"] if x["gate"] == "tekerrür-yok"][0]
    assert g["passed"] is False and "zaten onaylandı" in g["reason"]


def test_audit_pending_covers_only_dm_pending(db):
    _seed_measurement(db, "g.example", total=8, found=1)
    _seed_probe(db, "g.example")
    _seed_prospect(db, "g.example", phone="+971500000007")
    q = ApprovalQueue(db=db)
    q.scan()
    auditor = DmGateAuditor(db=db)
    items = auditor.audit_pending()
    assert len(items) == 1
    assert items[0]["domain"] == "g.example"


def test_invented_two_digit_number_still_blocked(db):
    """İki-haneli+ uyduru sayılar hâlâ yakalanır (kural gevşetilmedi)."""
    _seed_measurement(db, "h.example", total=8, found=1)
    _seed_probe(db, "h.example")
    _seed_prospect(db, "h.example", phone="+971500000008")
    auditor = DmGateAuditor(db=db)
    for bad in ("99 vuruş", "250 sorgu", "17 puan"):
        out = auditor.audit("h.example", dm_text=f"8 soruda {bad}")
        g = [x for x in out["gates"] if x["gate"] == "içerik-izlenebilir"][0]
        assert g["passed"] is False, bad


def test_auto_approve_dry_run_marks_nothing(db):
    _seed_measurement(db, "i.example", total=8, found=1)
    _seed_probe(db, "i.example")
    _seed_prospect(db, "i.example", phone="+971500000009")
    q = ApprovalQueue(db=db)
    q.scan()
    auditor = DmGateAuditor(db=db)
    res = auditor.auto_approve(dry_run=True)
    assert res["dry_run"] is True
    with db._get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM approval_queue"
                         " WHERE status='AUTO_APPROVED'").fetchone()
    assert n["c"] == 0  # dry-run hiçbir şeyi değiştirmez


def test_auto_approve_apply_marks_only_passing(db):
    _seed_measurement(db, "j.example", total=8, found=1)
    _seed_probe(db, "j.example")
    _seed_prospect(db, "j.example", phone="+971500000010")
    # başarısız madde: iletişimsiz
    _seed_measurement(db, "k.example", total=8, found=0)
    _seed_probe(db, "k.example")
    _seed_prospect(db, "k.example", phone="DOĞRULANAMADI")
    q = ApprovalQueue(db=db)
    q.scan()
    auditor = DmGateAuditor(db=db)
    res = auditor.auto_approve(dry_run=False)
    assert any(a["domain"] == "j.example" for a in res["auto_approved"])
    assert any(b["domain"] == "k.example" for b in res["still_pending"])
    # AUTO_APPROVED insan APPROVED'tan AYRI — gönderim ayrı kanaldır
    with db._get_connection() as conn:
        row = conn.execute("SELECT status, decision_note FROM approval_queue"
                           " WHERE ref_id='j.example'").fetchone()
    assert row["status"] == "AUTO_APPROVED"
    assert "çok-kapılı denetim" in row["decision_note"]


def test_gate_audit_log_persists_reasons(db):
    """Denetim izi kalıcıdır — her kapı nedeniyle yazılır."""
    _seed_measurement(db, "l.example", total=8, found=1)
    _seed_probe(db, "l.example")
    _seed_prospect(db, "l.example", phone="DOĞRULANAMADI")
    DmGateAuditor(db=db).audit("l.example")
    with db._get_connection() as conn:
        rows = conn.execute("SELECT gate, passed, reason FROM gate_audit_log"
                            " WHERE domain='l.example'").fetchall()
    assert len(rows) == 6
    failed = [r for r in rows if not r["passed"]]
    assert any("DOĞRULANAMADI" in r["reason"] for r in failed)


def test_missing_probe_blocks(db):
    _seed_measurement(db, "m2.example", total=8, found=1)
    _seed_prospect(db, "m2.example", phone="+971500000011")
    out = DmGateAuditor(db=db).audit("m2.example")
    g = [x for x in out["gates"] if x["gate"] == "mini-probe-var"][0]
    assert g["passed"] is False


def test_no_prospect_record_blocks(db):
    _seed_measurement(db, "m3.example", total=8, found=1)
    _seed_probe(db, "m3.example")
    out = DmGateAuditor(db=db).audit("m3.example")
    g = [x for x in out["gates"] if x["gate"] == "iletişim-doğrulandı"][0]
    assert g["passed"] is False


def test_unparseable_measurement_date_blocks(db):
    _seed_measurement(db, "m4.example", total=8, found=1)
    _seed_probe(db, "m4.example")
    _seed_prospect(db, "m4.example", phone="+971500000012")
    with db._get_connection() as conn:
        conn.execute("UPDATE citations SET created_at='not-a-date'"
                     " WHERE domain='m4.example'")
        conn.commit()
    out = DmGateAuditor(db=db).audit("m4.example")
    g = [x for x in out["gates"] if x["gate"] == "taze-ölçüm"][0]
    # Bozuk tarihli son koşu ortak doğrulamada reddedilir; tazelik kapısı
    # aynı kaynaktan geldiği için fail-closed kalır (başka kaynağa dönüş yok).
    assert g["passed"] is False


def test_unparseable_repeat_date_blocks(db):
    _seed_measurement(db, "m5.example", total=8, found=1)
    _seed_probe(db, "m5.example")
    _seed_prospect(db, "m5.example", phone="+971500000013")
    q = ApprovalQueue(db=db)
    q.add("DM", "m5.example", "eski")
    row = q.pending()[0]
    q.decide(row["id"], True, note="insan")
    with db._get_connection() as conn:
        conn.execute("UPDATE approval_queue SET status='AUTO_APPROVED',"
                     " decided_at='not-a-date' WHERE id=?", (row["id"],))
        conn.commit()
    out = DmGateAuditor(db=db).audit("m5.example")
    g = [x for x in out["gates"] if x["gate"] == "tekerrür-yok"][0]
    assert g["passed"] is False and "okunamadı" in g["reason"]


def test_old_repeat_is_allowed(db):
    """14 günden eski gönderim varsa tekerrür kapısı geçer."""
    _seed_measurement(db, "m6.example", total=8, found=1)
    _seed_probe(db, "m6.example")
    _seed_prospect(db, "m6.example", phone="+971500000014")
    q = ApprovalQueue(db=db)
    q.add("DM", "m6.example", "eski")
    row = q.pending()[0]
    q.decide(row["id"], True, note="insan")
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with db._get_connection() as conn:
        conn.execute("UPDATE approval_queue SET status='AUTO_APPROVED',"
                     " decided_at=? WHERE id=?", (old, row["id"]))
        conn.commit()
    out = DmGateAuditor(db=db).audit("m6.example")
    g = [x for x in out["gates"] if x["gate"] == "tekerrür-yok"][0]
    assert g["passed"] is True


def test_auto_approve_preserves_human_rejection_during_audit(db, monkeypatch):
    domain = "rejected.example"
    _seed_measurement(db, domain)
    _seed_probe(db, domain)
    _seed_prospect(db, domain)
    q = ApprovalQueue(db=db)
    q.scan()
    item = q.pending()[0]
    auditor = DmGateAuditor(db=db)
    original_audit = auditor.audit
    rejection = {}

    def audit_then_reject(domain, dm_text="", log=True):
        result = original_audit(domain, dm_text=dm_text, log=log)
        if dm_text:
            assert result["all_passed"]
            q.decide(item["id"], False, note="İnsan gönderimi reddetti")
            with db._get_connection() as conn:
                rejection.update(dict(conn.execute(
                    "SELECT * FROM approval_queue WHERE id=?", (item["id"],)
                ).fetchone()))
        return result

    monkeypatch.setattr(auditor, "audit", audit_then_reject)
    out = auditor.auto_approve(dry_run=False)
    with db._get_connection() as conn:
        actual = dict(conn.execute("SELECT * FROM approval_queue WHERE id=?",
                                   (item["id"],)).fetchone())
    assert actual == rejection, "Makine denetimi insanın nihai kararını değiştirdi"
    assert out["auto_approved"] == []
    assert out["still_pending"] == []
    assert out["conflicts"][0]["id"] == item["id"]


def test_cli_auto_approve_reports_conflict_without_success(db, monkeypatch, capsys):
    import sys
    from answrank.cli import main

    domain = "cli-race.example"
    _seed_measurement(db, domain)
    _seed_probe(db, domain)
    _seed_prospect(db, domain)
    q = ApprovalQueue(db=db)
    q.scan()
    iid = q.pending()[0]["id"]
    original_audit = DmGateAuditor.audit

    def audit_then_reject(self, domain, dm_text="", log=True):
        result = original_audit(self, domain, dm_text=dm_text, log=log)
        if dm_text:
            q.decide(iid, False, note="İnsan reddi")
        return result

    monkeypatch.setattr(DmGateAuditor, "audit", audit_then_reject)
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "audit",
                                    "--auto-approve", "--apply"])
    main()
    output = " ".join(capsys.readouterr().out.split())
    assert "Karar değişti; otomatik onay uygulanmadı" in output
    assert "0 onay uygulandı" in output
    assert "1 karar çakışması" in output


def test_cli_dry_run_does_not_claim_approval_was_applied(db, monkeypatch, capsys):
    """Dry-run hiçbir kararı değiştirmez; çıktı 'uygulandı' diyemez."""
    import sys
    from answrank.cli import main

    domain = "dry.example"
    _seed_measurement(db, domain)
    _seed_probe(db, domain)
    _seed_prospect(db, domain)
    q = ApprovalQueue(db=db)
    q.scan()
    monkeypatch.setattr(sys, "argv", ["answrank", "queue", "audit",
                                      "--auto-approve"])
    main()
    output = " ".join(capsys.readouterr().out.split())
    assert "dry-run" in output
    assert "UYGULANDI" not in output
    assert "onay uygulandı" not in output
    assert "hiçbir karar değişmedi" in output
    with db._get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM approval_queue"
                         " WHERE status='AUTO_APPROVED'").fetchone()
    assert n["c"] == 0


def test_repeat_gate_counts_actual_sends_not_approvals(db):
    """Tekerrür kapısı iki kanalı birleştirir: onay taahhüdü yakın ise kapanır,
    gerçek gönderim de kapıyı kapatır; eski onay + eski gönderim açılır."""
    from datetime import timedelta as td
    domain = "sent.example"
    _seed_measurement(db, domain)
    _seed_probe(db, domain)
    _seed_prospect(db, domain)
    now = datetime.now(timezone.utc)
    with db._get_connection() as conn:
        # Yakın makine onayı var ama hiç gönderim yapılmadı
        conn.execute("INSERT INTO approval_queue (kind, ref_id, summary, status,"
                     " created_at, decided_at, decision_note) VALUES"
                     " ('DM', ?, 'eski', 'AUTO_APPROVED', ?, ?, 'deneme')",
                     (domain, (now - td(days=1)).isoformat(),
                      (now - td(days=1)).isoformat()))
        conn.commit()
    out = DmGateAuditor(db=db).audit(domain)
    repeat = [g for g in out["gates"] if g["gate"] == "tekerrür-yok"][0]
    assert repeat["passed"] is False, "Yakın onay taahhüdü tekerrürü kapatmalı"
    assert "zaten onaylandı" in repeat["reason"]
    # Sonra gerçek gönderim günlüğü yazılır — kapı hâlâ kapalı
    with db._get_connection() as conn:
        conn.execute("INSERT INTO dm_send_log (queue_id, domain, recipient,"
                     " status, note, sent_at) VALUES (1, ?, 'x@y.z', 'GÖNDERİLDİ',"
                     " 'test', ?)", (domain, (now - td(days=1)).isoformat()))
        conn.commit()
    out = DmGateAuditor(db=db).audit(domain)
    repeat = [g for g in out["gates"] if g["gate"] == "tekerrür-yok"][0]
    assert repeat["passed"] is False, "Gerçek gönderim tekerrürü kapatmalı"
    assert "zaten gönderildi" in repeat["reason"]


def test_simulated_only_run_is_not_a_real_measurement(db):
    """Simülasyon koşusu aggregate üretse bile gerçek ölçüm gibi sunulamaz."""
    domain = "sim.example"
    _seed_measurement(db, domain, total=8, found=1, fully_live=False)
    vis = DmGateAuditor(db=db).db_visibility(domain)
    assert vis is None, "Tam-canlı olmayan koşu DM kanıtı olamaz"
    gate = DmGateAuditor(db=db).audit(domain)["gates"][0]
    assert gate["gate"] == "ölçüm-var" and gate["passed"] is False
    assert "simülasyon" in gate["reason"]


def test_fully_live_run_remains_valid_measurement(db):
    """Tam-canlı koşu kanıt olmaya devam eder (mevcut sözleşme korunur)."""
    domain = "live.example"
    _seed_measurement(db, domain, total=8, found=1, fully_live=True)
    vis = DmGateAuditor(db=db).db_visibility(domain)
    assert vis is not None and vis["total"] == 8
    gate = DmGateAuditor(db=db).audit(domain)["gates"][0]
    assert gate["passed"] is True


def test_future_timestamp_measurement_is_not_fresh(db):
    """Geleceğe tarih atılmış ölçüm 'taze' sayılamz; kanıt anormali."""
    from datetime import datetime, timedelta, timezone
    domain = "future.example"
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    asyncio.run(db.save_citations(CitationRunResult(
        run_id=f"g-{domain}", brand_name="X", domain=domain, sector="dental",
        city="Dubai", total_runs=8, brand_citations_found=1,
        citation_rate_percentage=12.5, timestamp=future, is_fully_live=True,
        live_items_count=8, live_response_rate_percentage=100.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                 model="test-model", was_simulated=False,
                                 brand_mentioned=i == 0) for i in range(8)])))
    with db._get_connection() as conn:
        conn.execute("UPDATE citations SET created_at=? WHERE domain=?",
                     (future, domain))
        conn.commit()
    out = DmGateAuditor(db=db).audit(domain, dm_text="8 soruda 1 vuruş")
    fresh = [g for g in out["gates"] if g["gate"] == "taze-ölçüm"][0]
    assert fresh["passed"] is False, "gelecek tarihli ölçüm taze sayıldı"


def test_audit_pending_audits_real_draft_text(db):
    """audit_pending, auto_approve ile AYNI gerçek gövde metnini denetlemeli;
    tam-geçerli madde için 'DM metni boş' sahte içerik-red üretilemez."""
    domain = "pending-dm.example"
    _seed_measurement(db, domain, total=8, found=1)
    _seed_probe(db, domain)
    _seed_prospect(db, domain, phone="+971500000020")
    q = ApprovalQueue(db=db)
    q.scan()
    auditor = DmGateAuditor(db=db)
    items = auditor.audit_pending()
    assert len(items) == 1
    traceable = [g for g in items[0]["gates"] if g["gate"] == "içerik-izlenebilir"][0]
    assert traceable["passed"] is True, traceable["reason"]
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT passed, reason FROM gate_audit_log"
            " WHERE domain=? AND gate='içerik-izlenebilir'"
            " ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
    assert row["passed"] == 1
    assert "DM metni boş" not in row["reason"]


def test_auto_approve_audits_each_item_once_with_text(db):
    """auto_approve tek denetim yazar: audit_pending zaten metinle denetler;
    boş-metin + metinli çift denetim 12 satır sahte iz üretmemeli."""
    domain = "once-audit.example"
    _seed_measurement(db, domain, total=8, found=1)
    _seed_probe(db, domain)
    _seed_prospect(db, domain, phone="+971500000021")
    q = ApprovalQueue(db=db)
    q.scan()
    res = DmGateAuditor(db=db).auto_approve(dry_run=False)
    assert any(a["domain"] == domain for a in res["auto_approved"])
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT passed, reason FROM gate_audit_log WHERE domain=?"
            " ORDER BY id", (domain,)).fetchall()
    assert len(rows) == 6, f"çift denetim: {len(rows)} satır"
    traceable = [r for r in rows if r["reason"] and "boş" in r["reason"]]
    assert not traceable, "boş-metin denetim izi yazıldı"


def test_auto_approve_blocked_without_lead(db):
    """mini-probe lead kaydı yoksa madde kapanır (238-240)."""
    _seed_measurement(db, "m7.example", total=8, found=1)
    _seed_prospect(db, "m7.example", phone="+971500000015")
    q = ApprovalQueue(db=db)
    q.add("DM", "m7.example", "leadsiz")
    res = DmGateAuditor(db=db).auto_approve(dry_run=False)
    assert any(b["domain"] == "m7.example" for b in res["still_pending"])


def test_stale_gate_rejects_future_timestamp(db):
    """Gelecek tarihli ölçüm taze-sayılıp DM geçemez — sahte tazelik engellenmeli."""
    from answrank.queue_gates import DmGateAuditor
    _seed_measurement(db, "future.example", days_ago=-5)
    g = DmGateAuditor(db=db)._gate_fresh("future.example")
    assert not g.passed
    assert "gelecekte" in g.reason


def test_stale_gate_rejects_unreadable_timestamp(db):
    """Okunamayan ölçüm tarihi kapıyı kapatmalı — varsayılan taze sayılmaz."""
    from answrank.queue_gates import DmGateAuditor
    _seed_measurement(db, "badts.example", days_ago=1)
    with db._get_connection() as conn:
        row = conn.execute("SELECT raw_json FROM citations WHERE domain=?",
                           ("badts.example",)).fetchone()
        import json as _json
        raw = _json.loads(row["raw_json"])
        raw["timestamp"] = "tarih-degil"
        conn.execute("UPDATE citations SET created_at=?, raw_json=? WHERE domain=?",
                     ("tarih-degil", _json.dumps(raw), "badts.example"))
        conn.commit()
    # Bozuk tarih fail-closed okuyucuda tüm kanıtı geçersiz kılar; tazelik
    # kapısı 'belirsiz' ile kapanr (varsayılan taze sayılmaz).
    g = DmGateAuditor(db=db)._gate_fresh("badts.example")
    assert not g.passed
    assert "belirsiz" in g.reason


def test_gate_traceable_rejects_empty_dm(db):
    """Boş DM metni izlenebilirlik kapısını kapatmalı."""
    from answrank.queue_gates import DmGateAuditor
    _seed_measurement(db, "empty.example", days_ago=1)
    _seed_probe(db, "empty.example")
    _seed_prospect(db, "empty.example", email="i@empty.example")
    g = DmGateAuditor(db=db)._gate_traceable("empty.example", "")
    assert not g.passed
    assert "boş" in g.reason


def test_gate_traceable_rejects_missing_measurement(db):
    """Doğrulanmış ölçüm yoksa izlenebilirlik kapısı kapanmalı."""
    from answrank.queue_gates import DmGateAuditor
    _seed_probe(db, "nomeas.example")
    _seed_prospect(db, "nomeas.example", email="i@nomeas.example")
    g = DmGateAuditor(db=db)._gate_traceable(
        "nomeas.example", "herhangi bir metin")
    assert not g.passed
    assert "ölçüm yok" in g.reason


def test_gate_repeat_no_previous_send_passes(db):
    """Önceki gönderim yoksa tekerrür kapısı geçmeli."""
    from answrank.queue_gates import DmGateAuditor
    _seed_measurement(db, "norepeat.example", days_ago=1)
    _seed_probe(db, "norepeat.example")
    _seed_prospect(db, "norepeat.example", email="i@norepeat.example")
    g = DmGateAuditor(db=db)._gate_repeat("norepeat.example")
    assert g.passed
    assert "önceki gönderim yok" in g.reason


def test_recurrence_gate_rejects_unreadable_send_timestamp(db):
    """Okunamayan gönderim tarihi tekerrür kapısını kapatmalı (fail-closed)."""
    from answrank.queue_gates import DmGateAuditor
    _seed_measurement(db, "badts2.example", days_ago=1)
    _seed_probe(db, "badts2.example")
    _seed_prospect(db, "badts2.example", email="i@badts2.example")
    # [Fix-2026-10-02] Tarih sabit DEĞIL, bugune göre göreli olmalı —
    # sabit 2026-09-18 testin yazildigi gun gecerliydi, 14 gun sonra
    # repeat_days penceresinin disina cikinca gate gecersiz oluyordu.
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note, sent_at)"
            " VALUES (?,?,?,?,?,?)",
            (1, "badts2.example", "i@badts2.example", "GÖNDERİLDİ",
             "onceki", recent.strftime("%Y-%m-%dT%H:%M:%S")))
        conn.commit()
    DmGateAuditor(db=db)._gate_repeat("badts2.example")  # naive ts
    # naive timestamp tzinfo eklenir, fail-closed kalır
    g2 = DmGateAuditor(db=db)._gate_repeat("badts2.example")
    assert not g2.passed


def test_fresh_gate_handles_naive_and_unparseable_timestamp(db, monkeypatch):
    """_gate_fresh naive tarihe UTC eklemeli ve okunamayan tarihi kapatmalı.
    Bu yollar yalnızca geçerli bir visibility dict ile ulaşılabilir olduğundan
    db_visibility doğrudan sağlanır."""
    from answrank.queue_gates import DmGateAuditor
    a = DmGateAuditor(db=db)

    # naive timestamp → tzinfo eklenir, geçerli sayılır (gate geçer)
    # ( göreceli-tarih: FRESH_DAYS=7'yi aşan sabit tarih ömrü doldu)
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    fresh = (_dt.now(_tz.utc) - _td(days=1)).replace(tzinfo=None)
    monkeypatch.setattr(a, "db_visibility",
                        lambda d: {"created_at": fresh.isoformat(), "run_id": "r"})
    g = a._gate_fresh("x.example")
    assert g.passed

    # okunamayan timestamp → kapanır
    monkeypatch.setattr(a, "db_visibility",
                        lambda d: {"created_at": "tarih-degil", "run_id": "r"})
    g2 = a._gate_fresh("x.example")
    assert not g2.passed
    assert "okunamadı" in g2.reason
