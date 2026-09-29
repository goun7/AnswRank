"""E13b: DM gönderim kanalı — onay sonrası tek sorumlu adım.

Tasarım kararları (sıfır-trust):
  - Gönderim YALNIZCA onaylı madde için: PENDING hiçbir koşulda gönderilmez.
  - Alıcı: yalnız prospects tablosunda DOĞRULANAN e-posta; telefon yoksa
    veya DOĞRULANAMADI ise 'Hedef YOK' döner — karanlık gönderim yok.
  - Gönderim hakkı kuyruk öğesi başına ayrılır; alıcı değişikliği ikinci
    SMTP girişimi açmaz. Belirsiz girişimler otomatik yeniden denenmez.
  - SMTP yapılandırması yoksa (PSP gibi) 'YAPILANDIRILMAMIŞ' döner; asla
    bir başarılı gönderim UYDURULMAZ. Test gönderimi --dry-run ile yazılır.
"""
from __future__ import annotations

import os
import smtplib
import ssl
import logging
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Dict, Optional

from answrank.db import Database

logger = logging.getLogger(__name__)

SMTP_HOST = "ANSWRANK_SMTP_HOST"
SMTP_PORT = "ANSWRANK_SMTP_PORT"
SMTP_USER = "ANSWRANK_SMTP_USER"
SMTP_PASS = "ANSWRANK_SMTP_PASS"
SMTP_FROM = "ANSWRANK_SMTP_FROM"


class DmDispatcher:
    """Onaylı DM maddelerini alıcıya gönderir — uydurma yok."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # --------------------------------------------------------------- alıcı
    def recipient_for(self, domain: str) -> Optional[str]:
        """Yalnızca KANITLANAN alıcı: e-posta, başarıyla tamamlanmış bir crawl'dan
        gelmiş olmalı. Boş/@-sone yer-tutucular ve kanıtsız (ör. elle girilmiş,
        başarısız HTTP taraması) satırlar gönderim hedefi olamaz."""
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT email, verified_at, http_status, contact_source"
                " FROM prospects WHERE domain_ref = ?"
                " ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
        if not row:
            return None
        addr = (row["email"] or "").strip().lower()
        # doğruluk kanıtı: crawl tamamlanmış (verified_at), HTTP başarılı ve
        # kaynağı belirli olmalı; ayrıca adresin yerel ve etki-alanı parçası dolu
        if not row["verified_at"]:
            return None
        status = row["http_status"]
        if status is None or status >= 400:
            return None
        if not row["contact_source"]:
            return None
        if not addr or "DOĞRULANAMADI" in addr or "@" not in addr:
            return None
        local, _, host = addr.partition("@")
        if not local or not host or "." not in host:
            return None
        return addr

    # --------------------------------------------------------- smtp durumu
    def smtp_configured(self) -> bool:
        """SMTP yapılandırmasının mevcut olup olmadığını döndürür."""
        return all(os.getenv(k) for k in (SMTP_HOST, SMTP_USER, SMTP_PASS))

    # ------------------------------------------------------------- gönder
    def send_approved(self, item_id: int, dry_run: bool = False) -> Dict:
        """Tek onaylı maddeyi gönder. Geri-döndürülemez hata yok: her sonuç
        kaydedilir (başarılı/başarısız/hedef-yok)."""
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT id, kind, ref_id, status, evidence_run_id"
                " FROM approval_queue WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise KeyError(f"Kuyruk maddesi yok: {item_id}")
        if row["kind"] != "DM":
            return {"item_id": item_id, "result": "atlandı",
                    "why": f"DM değil ({row['kind']})"}
        if row["status"] not in ("APPROVED", "AUTO_APPROVED"):
            return {"item_id": item_id, "result": "reddedildi",
                    "why": f"madde onaylı değil (durum: {row['status']}) — "
                           "onaysız gönderim olmaz"}

        recipient = self.recipient_for(row["ref_id"])
        if not recipient:
            self._log_send(item_id, row["ref_id"], "", "HEDEF_YOK",
                           "doğrulanan e-posta yok", dry_run)
            return {"item_id": item_id, "result": "hedef-yok",
                    "why": "bu domain için DOĞRULANAN e-posta yok — "
                           "karanlik gönderim yapilmaz"}

        if dry_run or not self.smtp_configured():
            self._log_send(item_id, row["ref_id"], recipient,
                           "YAPILANDIRILMAMIŞ" if not self.smtp_configured()
                           else "DRY_RUN",
                           "SMTP yok — gönderim uydurulmaz", dry_run)
            label = "yapilandirilmamis" if not self.smtp_configured() else "dry-run"
            return {"item_id": item_id, "result": label, "to": recipient}

        vis = self.db.get_dm_visibility(row["ref_id"])
        # Onay–kanıt kimlik bağlaması: gönderim, onay anında bağlanan koşu
        # ile aynı olmalı. Göç öncesi onay (NULL) veya sonradan değişen
        # kanıt gönderilemez; madde insan için PENDING'e geri açılır.
        # Gövde kontrolünden ÖNCE: kanıt yokluğunda da geri açma çalışsın.
        approved_run = row["evidence_run_id"]
        latest_run = vis["run_id"] if vis else None
        if approved_run is None or latest_run != approved_run:
            self._reopen_stale_approval(
                item_id, approved_run, latest_run, row["status"])
            why = ("onay kanıt run kimliği taşımıyor (göç öncesi onay)"
                   if approved_run is None else
                   f"kanıt onaydan sonra değişti (onay: {approved_run}, "
                   f"son: {latest_run})")
            return {"item_id": item_id, "result": "evidence-blocked",
                    "why": f"{why} — madde yeniden onay için PENDING'e açıldı"}
        body = self._body(row["ref_id"], vis)
        if body is None:
            return {"item_id": item_id, "result": "evidence-blocked",
                    "why": "Ölçümlü mini-probe yok; gönderim durduruldu."}
        # Sıralama önemli: tazelik ÖNCE koşulur. Kanıtı bayatlamış bir
        # maddeye 'already-attempted' demek, geçersiz kanıtla denemiş gibi
        # etiketlemektir; bu yüzden kanıt kontrolü denendi kontrolundan önce
        # gelir. _attempted ile _claim_send'in 'denendi' sorguları birebir
        # aynıdır; _claim_send BEGIN IMMEDIATE altında atomik olduğu için
        # yetkili karar orada kalır ve tekrar çağrıyı yanlış etiketlemez.
        from answrank.queue_gates import FRESH_DAYS
        stale = self._stale_reason(vis, fresh_days=FRESH_DAYS)
        if stale:
            return {"item_id": item_id, "result": "evidence-blocked",
                    "why": f"gönderim-anı denetim geçilmedi — taze-ölçüm: {stale}"}
        if not self._claim_send(item_id, row["ref_id"], recipient):
            return {"item_id": item_id, "result": "already-attempted",
                    "to": recipient}
        out = self._smtp_send(recipient, "[AnswRank] Ücretsiz site probe sonucunuz",
                              body)
        status = "GÖNDERİLDİ" if out["ok"] else "HATA"
        with self.db._get_connection() as conn:
            conn.execute(
                "UPDATE dm_send_log SET status=?, note=?, sent_at=?"
                " WHERE queue_id=? AND recipient=?",
                (status, out.get("error", "SMTP kabul etti; teslim doğrulanmadı"),
                 datetime.now(timezone.utc).isoformat(), item_id, recipient))
            conn.commit()
        # Türkçe locale tuzağı: "GÖNDERİLDİ".lower() -> 'gönderi̇ldi̇'
        # (İ->i̇); karşılaştırmada farklı bayt verir. Anahtar İngilizce.
        label = "sent" if out["ok"] else "error"
        return {"item_id": item_id, "result": label, "to": recipient}

    # ----------------------------------------------------------- yardımcılar
    def _reopen_stale_approval(self, item_id: int, approved_run: Optional[str],
                              latest_run: Optional[str], status: str) -> None:
        """Eskimiş onayı insan için PENDING'e aç; karar ezme değil.

        Orijinal karar decision_note içinde kalır (karar defteri
        geri-döndürülemez). Koşu kimliği temizlenir; yeniden onay
        güncel kanıtla bağlanır. Gönderim gerçekleşmez (fail-closed)."""
        note = (f" | kanıt değişti: {approved_run} -> {latest_run};"
                " yeniden değerlendirme gerekir")
        with self.db._get_connection() as conn:
            changed = conn.execute(
                "UPDATE approval_queue SET status='PENDING',"
                " decision_note=COALESCE(decision_note,'') || ?,"
                " evidence_run_id=NULL"
                " WHERE id=? AND status IN ('APPROVED','AUTO_APPROVED')",
                (note, item_id))
            conn.commit()
        # rowcount 0: başka bir süreç onayı zaten değiştirmiş (REJECTED vb.).
        # Gönderimi RuntimeError ile çökürmek kanıtı kaybeder; mevcut durum
        # geçerli bir karar olduğu için sessizce kabul edilir (fail-closed).
        if changed.rowcount != 1 and status in ("APPROVED", "AUTO_APPROVED"):
            logger.debug("onay %s zaten başka bir süreç tarafından değiştirilmiş",
                         item_id)

    def _stale_reason(self, vis: Optional[dict], fresh_days: int) -> str:
        """Gövdeyi üreten doğrulanmış kaydın yaşı; taze değilse neden döner.

        Yaş, ortak doğrulayıcının döndürdüğü kayıttan gelir (aynı kayıt
        gövdeyi üretti); ayrı sorgu yok, eski koşuya dönüş yok."""
        if vis is None:
            return "geçerli son kanıt yok"
        try:
            created = datetime.fromisoformat(vis["created_at"])
        except (TypeError, ValueError):
            return "ölçüm tarihi okunamadı"
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created
        if age > timedelta(days=fresh_days):
            return f"ölçüm {age.days} gün önce — taze değil"
        return ""

    def _claim_send(self, item_id: int, domain: str, recipient: str) -> bool:
        """Reserve before SMTP; uncertain attempts require manual reconciliation.

        HATA is deliberately fail-closed for legacy schemas: an interrupted
        attempt must never look sent, or be automatically attempted again.
        Only configuration-only records are safe to reuse (no SMTP occurred).
        """
        with self.db._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # A queue approval authorizes one attempt, not one per mutable address.
            attempted = conn.execute(
                "SELECT 1 FROM dm_send_log WHERE queue_id=?"
                " AND status NOT IN ('YAPILANDIRILMAMIŞ','HEDEF_YOK','DRY_RUN')"
                " LIMIT 1", (item_id,)).fetchone()
            if attempted:
                return False
            existing = conn.execute(
                "SELECT status FROM dm_send_log WHERE queue_id=? AND recipient=?",
                (item_id, recipient)).fetchone()
            now = datetime.now(timezone.utc).isoformat()
            note = "SMTP girişimi ayrıldı; sonuç belirsizse elle mutabakat gerekir"
            if existing:
                # YAPILANDIRILMAMIŞ ve DRY_RUN: SMTP hiç çağrılmadı, yeniden
                # kullanılabilir. Diğerleri (GÖNDERİLDİ/HATA/HEDEF_YOK) denendi.
                if existing["status"] not in ("YAPILANDIRILMAMIŞ", "DRY_RUN"):
                    return False
                conn.execute(
                    "UPDATE dm_send_log SET status='HATA', note=?, sent_at=?"
                    " WHERE queue_id=? AND recipient=?",
                    (note, now, item_id, recipient))
            else:
                conn.execute(
                    "INSERT INTO dm_send_log"
                    " (queue_id, domain, recipient, status, note, sent_at)"
                    " VALUES (?,?,?,'HATA',?,?)",
                    (item_id, domain, recipient, note, now))
            conn.commit()
            return True

    def _body(self, domain: str, vis: Optional[dict]) -> Optional[str]:
        """Eksik/geçersiz kanıt gövdeye dönüştürülmez; eski koşu aranmaz.
        Kanıt okuması gönderim akışında tek kez yapılır (vis parametresi)."""
        from answrank.crm.outreach import OutreachGenerator
        lead = self.db.latest_measured_lead(domain)
        if not lead:
            return None
        if vis is None:
            return None
        return OutreachGenerator.lead_dm(lead["domain"], lead["robots_line"],
                                         lead["llms_line"], lead["bots_line"],
                                         lead["verdict"], ai_visibility=vis)

    def _smtp_send(self, to: str, subject: str, body: str) -> Dict:
        host = os.getenv(SMTP_HOST)
        port = int(os.getenv(SMTP_PORT, "587"))
        user = os.getenv(SMTP_USER)
        msg = EmailMessage()
        msg["From"] = os.getenv(SMTP_FROM, user)
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(user, os.getenv(SMTP_PASS))
                s.send_message(msg)
            return {"ok": True}
        except Exception as exc:  # sızıntı yok: hata sınıfı yazılır, içerik değil
            return {"ok": False, "error": type(exc).__name__}

    def _log_send(self, item_id: int, domain: str, to: str, status: str,
                  note: str, dry_run: bool) -> None:
        """No-op sonuçlar (HEDEF_YOK/YAPILANDIRILMAMIŞ) idempotent yazılır:
        tekrar çağrı yeni satır açmaz, mevcut kaydı yeniler. SMTP'ye
        ulaşan GÖNDERİLDİ/HATA kayıtları dokunulmaz (UPDATE yalnız no-op
        statülerinde çalışır)."""
        if dry_run:
            return
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO dm_send_log (queue_id, domain, recipient, status,"
                " note, sent_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(queue_id, recipient) DO UPDATE SET"
                " status=excluded.status, note=excluded.note,"
                " sent_at=excluded.sent_at"
                " WHERE dm_send_log.status IN"
                " ('HEDEF_YOK','YAPILANDIRILMAMIŞ','DRY_RUN')",
                (item_id, domain, to, status, note,
                 datetime.now(timezone.utc).isoformat()))
            conn.commit()
