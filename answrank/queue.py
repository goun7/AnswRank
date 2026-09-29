"""TEK onay kuyruğu — insan-KARAR yüzeyi (canlıya-geçiş mimarisi).

Hiçbir dışa-yönelik fiil (DM gönderimi, sözleşme teslimi, gelir-düşüren
FREE-CYCLE, izleme müdahalesi) otomatik işlenmez; hepsi burada sıraya girer.
Kuyruk bir KARAR DEFTERİDİR: PENDING → APPROVED/REJECTED geri-döndürülemez
(decided_at + not çift-karara kapalı). Üretici olaylar yalnız GERÇEK
kayıtlardan türer — boş tarama boş rapor verir, iş uydurulmaz.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from answrank.db import Database

KINDS = ("DM", "CONTRACT", "FREE_CYCLE", "MONITOR_INTERVENTION")


class ApprovalQueue:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # ------------------------------------------------------------------ yazma
    def add(self, kind: str, ref_id: str, summary: str) -> bool:
        """Aynı (kind, ref_id) için açık madde varsa yenisini doğurmaz (True=yeni)."""
        if kind not in KINDS:
            raise ValueError(f"Kayıtlı kuyruk türü: {', '.join(KINDS)} — '{kind}' eklenmez.")
        with self.db._get_connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO approval_queue (kind, ref_id, summary, created_at)"
                " VALUES (?,?,?,?)",
                (kind, ref_id, summary, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return cur.rowcount == 1

    def scan(self) -> int:
        """Kalıcı-olmayan türetilmiş maddeleri toplar: lead→DM, sözleşme→teslim,
        3+ ölçülemeyen koşu→izleme müdahalesi. Dönen sayı YENİ maddedir."""
        new = 0
        with self.db._get_connection() as conn:
            leads = conn.execute(
                "SELECT domain, verdict, bots_line FROM miniprobe_leads l"
                " WHERE measured = 1 AND NOT EXISTS ("
                "   SELECT 1 FROM approval_queue q WHERE q.kind='DM' AND q.ref_id=l.domain"
                "     AND q.status='PENDING')").fetchall()
            for l in leads:
                new += self.add("DM", l["domain"],
                                f"Lead {l['verdict']} — {l['bots_line']} — DM onayla/ret")
            prospects = conn.execute(
                "SELECT domain_ref, brand_name, phone, email FROM prospects"
                " WHERE status='lead' AND domain_ref IS NOT NULL AND NOT EXISTS ("
                "   SELECT 1 FROM approval_queue q WHERE q.kind='DM'"
                "     AND q.ref_id=prospects.domain_ref AND q.status='PENDING')").fetchall()
            for pr in prospects:
                contact = " / ".join(x for x in (pr["phone"], pr["email"]) if x) or \
                    "kamuya açık iletişim DOĞRULANAMADI"
                new += self.add("DM", pr["domain_ref"],
                                f"Aday {pr['brand_name']} — {contact} — onay sonrası: "
                                f"answrank crm draft {pr['domain_ref']}")
            contracts = conn.execute(
                "SELECT id, brand_name, domain FROM swarm_candidates"
                " WHERE stage='CONTRACT_ISSUED' AND contract_text IS NOT NULL"
                "   AND contract_text != ''").fetchall()
            for c in contracts:
                new += self.add("CONTRACT", c["id"],
                                f"Sözleşme hazır: {c['brand_name']} ({c['domain']}) — "
                                f"teslim/imza onayı")
            mon = conn.execute(
                "SELECT m.id, m.domain, COUNT(*) AS bad FROM monitors m"
                " JOIN monitor_runs r ON r.monitor_id = m.id"
                " WHERE r.status != 'MEASURED' AND NOT EXISTS ("
                "   SELECT 1 FROM monitor_runs r2 WHERE r2.monitor_id = m.id"
                "     AND r2.status = 'MEASURED' AND r2.id > r.id)"
                " GROUP BY m.id HAVING COUNT(*) >= 3").fetchall()
            for m in mon:
                new += self.add("MONITOR_INTERVENTION", m["id"],
                                f"{m['bad']} ardışık koşu ölçülemedi — erişimi müşteriden "
                                f"iste ya da izlemeyi kapat")
        return new

    # ------------------------------------------------------------------- okuma
    def pending(self) -> List[Dict]:
        """Onay bekleyen kuyruk maddelerini döndürür."""
        with self.db._get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT id, kind, ref_id, summary, status, created_at FROM approval_queue"
                " WHERE status = 'PENDING' ORDER BY id")]

    # ------------------------------------------------------------------- karar
    def decide(self, item_id: int, approve: bool, note: str = "") -> Dict:
        """Bir kuyruk maddesine karar kaydeder."""
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT * FROM approval_queue WHERE id = ?",
                               (item_id,)).fetchone()
            if not row:
                raise KeyError(f"Kuyruk maddesi yok: {item_id}")
            if row["status"] != "PENDING":
                raise ValueError(f"Bu maddeye zaten karar verilmiş ({row['status']}) — "
                                 f"karar defteri çift-kararı kabul etmez.")
            status = "APPROVED" if approve else "REJECTED"
            decided = datetime.now(timezone.utc).isoformat()
            # DM kararı o anki geçerli görünürlük koşu kimliğini bağlar;
            # gönderim ancak aynı koşuyla gerçekleşir (onay–kanıt kimliği).
            run_id = None
            if row["kind"] == "DM":
                vis = self.db.get_dm_visibility(row["ref_id"])
                run_id = vis["run_id"] if vis else None
            changed = conn.execute(
                "UPDATE approval_queue SET status=?, decided_at=?, decision_note=?,"
                " evidence_run_id=? WHERE id=? AND status='PENDING'",
                (status, decided, note, run_id, item_id))
            if changed.rowcount != 1:
                raise ValueError("Bu maddeye zaten karar verilmiş — eşzamanlı karar korunuyor.")
            conn.commit()
            out = dict(row)
            out.update(status=status, decision_note=note, decided_at=decided,
                       evidence_run_id=run_id)
            return out
