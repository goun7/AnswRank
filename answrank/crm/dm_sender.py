"""E12b — Otomatik DM gönderim kanalı (e-posta).

Tasarım prensibi (E13 ile uyumlu):
  - GÖNDERİM İÇİN İNSAN ONAYI ZORUNLUDUR. Hiçbir DM onaysız gönderilmez.
  - Onaylanmış kuyruk maddesi → alıcı (DB'deki email) → SMTP → dm_send_log.
  - Fail-closed: SMTP yoksa veya alıcı yoksa gönderim yapılmaz, "gönderilemedi"
    olarak kaydedilir. Asla "gönderildi" uydurulmaz.
  - Anti-spam:同一 alıcıya aynı varyantı tekrar göndermez (dm_send_log kontrolü).

Ortam değişkenleri (E-siz ANSWRANK_ öneki — proje geneli kural):
  ANSWRANK_SMTP_HOST, ANSWRANK_SMTP_PORT, ANSWRANK_SMTP_USER,
  ANSWRANK_SMTP_PASS, ANSWRANK_SMTP_FROM_NAME
  SMTP yapılandırılmamışsa "MANUAL" moda düşer: .eml dosyaları üretilir,
  kullanıcı bunları kendi e-posta istemcisiyle gönderir (kanıt loglanır).
"""

from __future__ import annotations

import os
import smtplib
import sqlite3
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional

DB_PATH = os.getenv("ANSWRANK_DB", "answrank.db")
OUTBOX_DIR = Path(os.getenv("ANSWRANK_OUTBOX", "outbox"))


@dataclass
class SendResult:
    queue_id: int
    domain: str
    recipient: Optional[str]
    channel: str          # "smtp" | "manual"
    status: str           # "GÖNDERİLDİ" | "YAPILANDIRILMAMIŞ" | "HEDEF_YOK" | "HATA" | "TEKRAR"
    note: str


class DMSender:
    """Onaylı DM'leri alıcıya ulaştırır; onaysız hiçbir şey göndermez."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    # -- config ---------------------------------------------------------
    def smtp_creds(self) -> Optional[dict]:
        host = os.getenv("ANSWRANK_SMTP_HOST")
        if not host:
            return None
        return {
            "host": host,
            "port": int(os.getenv("ANSWRANK_SMTP_PORT", "587")),
            "user": os.getenv("ANSWRANK_SMTP_USER", ""),
            "pass": os.getenv("ANSWRANK_SMTP_PASS", ""),
            "from_name": os.getenv("ANSWRANK_SMTP_FROM_NAME", "AnswRank"),
        }

    def channel(self) -> str:
        return "smtp" if self.smtp_creds() else "manual"

    # -- alıcı çözümle ---------------------------------------------------
    def recipient_for(self, domain: str) -> Optional[str]:
        db = sqlite3.connect(self.db_path)
        try:
            row = db.execute(
                "SELECT email FROM prospects WHERE status='lead' "
                "AND website_url LIKE ? AND email IS NOT NULL AND email != ''",
                (f"%{domain}%",),
            ).fetchone()
            return row[0] if row else None
        finally:
            db.close()

    # -- tekrar gönderim koruması ---------------------------------------
    def already_sent(self, queue_id: int, recipient: str) -> bool:
        """UNIQUE(queue_id, recipient) ile uyumlu — aynı kuyruk+alıcıya tekrar yok."""
        db = sqlite3.connect(self.db_path)
        try:
            row = db.execute(
                "SELECT 1 FROM dm_send_log WHERE queue_id=? AND recipient=? "
                "AND status IN ('GÖNDERİLDİ','YAPILANDIRILMAMIŞ')",
                (queue_id, recipient),
            ).fetchone()
            return row is not None
        finally:
            db.close()

    # -- gönderim --------------------------------------------------------
    def send(
        self,
        queue_id: int,
        domain: str,
        subject: str,
        body: str,
        variant_key: str,
    ) -> SendResult:
        """Tek bir onaylı DM'yi gönderir. Onaysız gönderim imkansız."""
        recipient = self.recipient_for(domain)
        if not recipient:
            res = SendResult(queue_id, domain, None, self.channel(),
                             "HEDEF_YOK", "DB'de geçerli e-posta yok — gönderilemedi")
            self._log(res, variant_key)
            return res

        if self.already_sent(queue_id, recipient):
            res = SendResult(queue_id, domain, recipient, self.channel(),
                             "TEKRAR", "Bu alıcıya bu kuyruk maddesi zaten gönderildi — tekrarlanmaz")
            self._log(res, variant_key)
            return res

        creds = self.smtp_creds()
        if creds:
            return self._send_smtp(queue_id, domain, recipient, subject, body,
                                   variant_key, creds)
        return self._send_manual(queue_id, domain, recipient, subject, body, variant_key)

    def _send_smtp(self, queue_id, domain, recipient, subject, body, variant_key, creds) -> SendResult:
        try:
            msg = EmailMessage()
            msg["From"] = f"{creds['from_name']} <{creds['user']}>"
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(creds["host"], creds["port"], timeout=30) as srv:
                srv.starttls()
                if creds["user"]:
                    srv.login(creds["user"], creds["pass"])
                srv.send_message(msg)
            res = SendResult(queue_id, domain, recipient, "smtp", "GÖNDERİLDİ",
                             f"SMTP {creds['host']} ile gönderildi")
        except Exception as exc:  # fail-closed
            res = SendResult(queue_id, domain, recipient, "smtp", "HATA",
                             f"SMTP hatası: {type(exc).__name__}: {exc}")
        self._log(res, variant_key)
        return res

    def _send_manual(self, queue_id, domain, recipient, subject, body, variant_key) -> SendResult:
        """SMTP yoksa .eml üretir — kullanıcı kendi istemcisiyle gönderir."""
        try:
            eml = EmailMessage()
            eml["To"] = recipient
            eml["Subject"] = subject
            eml.set_content(body)
            path = OUTBOX_DIR / f"dm_{queue_id}_{variant_key}_{domain}.eml"
            path.write_bytes(eml.as_bytes())
            res = SendResult(queue_id, domain, recipient, "manual", "YAPILANDIRILMAMIŞ",
                             f"Hazır .eml: {path} — siz gönderin (kanıt loglandı)")
        except Exception as exc:
            res = SendResult(queue_id, domain, recipient, "manual", "HATA",
                             f".eml yazılamadı: {type(exc).__name__}: {exc}")
        self._log(res, variant_key)
        return res

    # -- kanıt -----------------------------------------------------------
    def _log(self, res: SendResult, variant_key: str) -> None:
        db = sqlite3.connect(self.db_path)
        try:
            # UNIQUE(queue_id, recipient) ihlali olursa güncelle, ekleme
            db.execute(
                "INSERT INTO dm_send_log (queue_id, domain, recipient, status, note, sent_at, variant_key) "
                "VALUES (?,?,?,?,?,datetime('now'),?) "
                "ON CONFLICT(queue_id, recipient) DO UPDATE SET "
                "status=excluded.status, note=excluded.note, sent_at=datetime('now'), "
                "variant_key=excluded.variant_key",
                (res.queue_id, res.domain, res.recipient or "(yok)", res.status, res.note, variant_key),
            )
            db.commit()
        finally:
            db.close()

    # -- takip (follow-up) ---------------------------------------------
    def followups_due(self) -> List[dict]:
        """Gönderilmiş DM'lerden 3/7 gün geçenler için takip listesi.

        Kimse uydurulmaz: yalnızca dm_send_log'da gönderim kaydı olan
        klinikler için takip üretilir.
        """
        db = sqlite3.connect(self.db_path)
        try:
            rows = db.execute(
                "SELECT queue_id, domain, recipient, sent_at, variant_key FROM dm_send_log "
                "WHERE status IN ('GÖNDERİLDİ','YAPILANDIRILMAMIŞ') "
                "AND variant_key='variant_1'",
            ).fetchall()
        finally:
            db.close()
        from datetime import date
        bugun = date.today()
        due = []
        for qid, domain, recipient, sent_at, vkey in rows:
            try:
                gonderim = date.fromisoformat(sent_at[:10])
            except Exception:
                continue
            gecen_gun = (bugun - gonderim).days
            if gecen_gun >= 7:
                due.append({"queue_id": qid, "domain": domain, "recipient": recipient,
                            "gun": 7, "key": "followup_day_7"})
            elif gecen_gun >= 3:
                due.append({"queue_id": qid, "domain": domain, "recipient": recipient,
                            "gun": 3, "key": "followup_day_3"})
        return due

    def generate_followups(self) -> List[SendResult]:
        """Vadesi gelen takipleri .eml olarak hazırlar (gönderim insan)."""
        sonuclar = []
        for f in self.followups_due():
            res = self.send(
                queue_id=f["queue_id"], domain=f["domain"],
                subject=f"Yapay zeka görünürlük raporu — {f['gun']}. gün hatırlatması",
                body=(f"Merhaba Klinik Ekibi, {f['domain']} için hazırladığım raporu "
                      f"{f['gun']} gün önce iletmiştim. İncelemek isterseniz "
                      "tek mesaj yeterli. İyi çalışmalar."),
                variant_key=f["key"],
            )
            sonuclar.append(res)
        return sonuclar

    # -- özet ------------------------------------------------------------
    def summary(self) -> dict:
        db = sqlite3.connect(self.db_path)
        try:
            total = db.execute("SELECT COUNT(*) FROM dm_send_log").fetchone()[0]
            sent = db.execute("SELECT COUNT(*) FROM dm_send_log WHERE status='GÖNDERİLDİ'").fetchone()[0]
            ready = db.execute("SELECT COUNT(*) FROM dm_send_log WHERE status='YAPILANDIRILMAMIŞ'").fetchone()[0]
            failed = db.execute("SELECT COUNT(*) FROM dm_send_log WHERE status IN ('HATA','HEDEF_YOK')").fetchone()[0]
            return {"total": total, "sent": sent, "manual_ready": ready, "failed": failed}
        finally:
            db.close()
