"""E11 ödeme/tahsilat entegrasyonu (16 Eylül 2026).

Tasarım ilkesi — PSP anlaşmamız YOK: kod hazır, ama canlı ödeme almaz.
- PAYTR / IYZICO / PADDLE: PSP kimlik bilgileri config'te değilse
  `PaymentError("yapılandırılmamış")` fırlatır; asla sahte başarılı ödeme
  üretmez.
- MANUAL (havale/EFT): PSP'siz tek kanal. Para bankada gerçekten görülmeden
  onaylanmaz — operatör kararı insan-kapısıdır.
- Başarılı ödeme → TaxLedger'da fatura doğar (rejim ülkeye bağlı:
  TR = DOMESTIC %20 KDV; yurt dışı = EXPORT %0 KDV + 11257 CBK %100 indirim).
- Webhook imzası HMAC ile doğrulanır; imzasız/geçersiz olay işlenmez.
- Olay kimliği (psp_event_id) idempotent: aynı olay iki kere gelirse
  fatura iki kez kesilmez (çift tahsilat koruması).
- İade: fatura silinmez, ters kayıt (credit note) işlenir.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from answrank.db import Database
from answrank.finance.tax_ledger import TaxLedger, TaxRegime

logger = logging.getLogger("answrank.payments")


class PaymentProvider(str, Enum):
    PAYTR = "PAYTR"      # yerel kart / Sanal POS / Abonelik (paytr.com)
    IYZICO = "IYZICO"   # yerel + 3D Secure
    PADDLE = "PADDLE"   # Merchant of Record — uluslararası USD/EUR
    MANUAL = "MANUAL"   # havale/EFT — PSP gerektirmez


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


@dataclass
class PaymentRequest:
    """Sözleşmeden türeyen tahsilat talebi."""
    contract_ref: str        # swarm_candidates.id veya sözleşme no
    brand: str
    country: str             # ISO kodu — rejim buradan türetilir
    currency: str            # TRY/GBP/USD/EUR/AED
    amount: float            # anlaşma tutarı (currency cinsinden)
    description: str = "AnswRank AEO denetim hizmeti"


@dataclass
class PaymentResult:
    intent_id: str
    status: PaymentStatus
    invoice_id: Optional[str]
    regime: Optional[TaxRegime]
    note: str

    def as_dict(self) -> Dict[str, Any]:
        """Ödme kanalı yapılandırmasını sözlük olarak döndürür."""
        return {
            "intent_id": self.intent_id,
            "status": self.status.value,
            "invoice_id": self.invoice_id,
            "regime": self.regime.value if self.regime else None,
            "note": self.note,
        }


class PaymentError(RuntimeError):
    """Yapılandırma/parametre hatası — ödeme alınamaz (uydurma yapılmaz)."""


class PaymentService:
    """Tek tahsilat noktası. PSP'siz çalışır; PSP'li kanal kapalıyken
    'yapılandırılmamış' der."""

    def __init__(self, db: Optional[Database] = None,
                 ledger: Optional[TaxLedger] = None,
                 sandbox: bool = False) -> None:
        self.db = db or Database()
        self.ledger = ledger or TaxLedger()
        self.sandbox = sandbox

    # --- yapılandırma durumu (dürüst yüzey) -------------------------------

    def _psp_creds(self, provider: PaymentProvider) -> Optional[Dict[str, str]]:
        """PSP kimlik bilgilerini çevreden okur; yoksa None döner."""
        if provider == PaymentProvider.PAYTR:
            mid, key = os.getenv("ANSWRANK_PAYTR_MERCHANT_ID"), os.getenv("ANSWRANK_PAYTR_API_KEY")
            return {"merchant_id": mid, "api_key": key} if mid and key else None
        if provider == PaymentProvider.IYZICO:
            key, secret = os.getenv("ANSWRANK_IYZICO_API_KEY"), os.getenv("ANSWRANK_IYZICO_SECRET")
            return {"api_key": key, "secret": secret} if key and secret else None
        if provider == PaymentProvider.PADDLE:
            vendor, key = os.getenv("ANSWRANK_PADDLE_VENDOR"), os.getenv("ANSWRANK_PADDLE_API_KEY")
            return {"vendor_id": vendor, "api_key": key} if vendor and key else None
        if provider == PaymentProvider.MANUAL:
            iban = os.getenv("ANSWRANK_MANUAL_IBAN")
            return {"iban": iban} if iban else None
        return None

    def provider_status(self, provider: PaymentProvider) -> str:
        """PSP anlaşması yoksa 'YAPILANDIRILMAMIŞ' — asla 'hazır' demez."""
        if provider == PaymentProvider.MANUAL:
            return "HAZIR" if self._psp_creds(provider) else "IBAN YOK (havale kanalı açık değil)"
        return "YAPILANDIRILMAMIŞ — PSP anlaşması yok" if not self._psp_creds(provider) \
            else ("SANDBOX" if self.sandbox else "CANLI")

    # --- tahsilat ----------------------------------------------------------

    def create_intent(self, req: PaymentRequest, provider: PaymentProvider) -> PaymentResult:
        """Tahsilat niyeti yaratır. PSP'siz kanalda asla SUCCEEDED üretmez."""
        if req.amount <= 0:
            raise PaymentError(f"Tutar pozitif olmalı: {req.amount}")
        if provider != PaymentProvider.MANUAL and not self._psp_creds(provider):
            raise PaymentError(
                f"{provider.value} {self.provider_status(provider)} — "
                "sahte başarılı ödeme üretilmez")
        # ülke bilinmiyorsa ihracat/yerel ayrımı yapılamaz → hüküm verilemez
        country = (req.country or "").strip().upper()
        if not country:
            raise PaymentError("Ülke kodu gerekli — rejim (KDV %0/%20) buradan türetilir")

        with self.db._get_connection() as conn:
            next_n = (conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM"
                " (SELECT rowid AS seq FROM payment_intents)").fetchone()[0])
            intent_id = f"PAY-{next_n:05d}"
            conn.execute(
                "INSERT INTO payment_intents"
                " (intent_id, contract_ref, brand, country, currency, amount, provider, status)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (intent_id, req.contract_ref, req.brand, country, req.currency.upper(),
                 float(req.amount), provider.value, PaymentStatus.PENDING.value))
            conn.commit()
        return PaymentResult(intent_id, PaymentStatus.PENDING, None, None,
                             f"Niyet yaratıldı ({provider.value}) — ödeme alınmadı")

    def confirm_manual(self, intent_id: str, proof: str) -> PaymentResult:
        """Havale ile para bankada GÖRÜLDÜKTEN sonra operatör onayı.
        proof: banka dekontu referansı — boşsa onaylanmaz (uydurma kanıt yok)."""
        if not proof or not proof.strip():
            raise PaymentError("Banka kanıtı (dekont ref) gerekli — kanıtsız onay yapılmaz")
        return self._settle(intent_id, PaymentProvider.MANUAL, proof.strip())

    def handle_webhook(self, provider: PaymentProvider, raw_body: bytes,
                       signature: Optional[str], event_id: str) -> PaymentResult:
        """PSP webhook'u. İmza doğrulanmazsa olay işlenmez (asla güvenme)."""
        if not self._psp_creds(provider):
            raise PaymentError(f"{provider.value} {self.provider_status(provider)}")
        expected = self._sign(provider, raw_body)
        if not signature or not hmac.compare_digest(expected, signature):
            logger.warning("%s webhook imza doğrulanamadı — olay REDDEDİLDİ", provider.value)
            raise PaymentError("Webhook imza doğrulanamadı — olay işlenmedi")
        # idempotency: aynı olay ikinci kez gelirse ikinci fatura kesilmez
        with self.db._get_connection() as conn:
            seen = conn.execute(
                "SELECT 1 FROM payment_events WHERE psp_event_id = ?", (event_id,)).fetchone()
        if seen:
            return PaymentResult("?", PaymentStatus.SUCCEEDED, None, None,
                                 f"Olay {event_id} zaten işlendi — tekrar fatura kesilmedi")
        import json
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PaymentError(f"Webhook gövdesi okunamadı: {exc}")
        intent_id = payload.get("intent_id")
        status = payload.get("status", "").upper()
        if status != "SUCCEEDED" or not intent_id:
            with self.db._get_connection() as conn:
                conn.execute(
                    "INSERT INTO payment_events (psp_event_id, provider, intent_id, status, raw)"
                    " VALUES (?,?,?,?,?)",
                    (event_id, provider.value, intent_id, status, raw_body.decode("utf-8", "replace")))
                conn.commit()
            return PaymentResult(intent_id or "?", PaymentStatus.PENDING, None, None,
                                 f"Olay {status or 'belirsiz'} — ödeme alınmadı")
        return self._settle(intent_id, provider, event_id)

    def _settle(self, intent_id: str, provider: PaymentProvider,
                proof_ref: str) -> PaymentResult:
        """Ödemeyi başarıyla kapatır → fatura doğar (rejim ülkeyle belirlenir)."""
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT intent_id, contract_ref, brand, country, currency, amount, status"
                " FROM payment_intents WHERE intent_id = ?", (intent_id,)).fetchone()
            if not row:
                raise PaymentError(f"Tahsilat niyeti yok: {intent_id}")
            if row["status"] == PaymentStatus.SUCCEEDED.value:
                return PaymentResult(intent_id, PaymentStatus.SUCCEEDED, None, None,
                                     "Zaten başarıyla kapatılmış — tekrar fatura kesilmedi")
            if row["status"] == PaymentStatus.REFUNDED.value:
                raise PaymentError(f"{intent_id} iade edilmiş — yeniden kapatılamaz")
            rec = self.ledger.record_invoice(
                client_brand=row["brand"], country=row["country"],
                currency=row["currency"], amount=row["amount"])
            conn.execute(
                "UPDATE payment_intents SET status=?, invoice_id=?, proof_ref=?, settled_at=?"
                " WHERE intent_id=?",
                (PaymentStatus.SUCCEEDED.value, rec.invoice_id, proof_ref,
                 _now(), intent_id))
            conn.execute(
                "INSERT INTO payment_events (psp_event_id, provider, intent_id, status, raw)"
                " VALUES (?,?,?,?,?)",
                (proof_ref, provider.value, intent_id, PaymentStatus.SUCCEEDED.value,
                 f"settled; invoice={rec.invoice_id}"))
            conn.commit()
        logger.info("ödeme %s kapatıldı → fatura %s (%s)", intent_id,
                    rec.invoice_id, rec.regime.value)
        return PaymentResult(intent_id, PaymentStatus.SUCCEEDED, rec.invoice_id,
                             rec.regime, f"Fatura kesildi: {rec.invoice_id}")

    def refund(self, intent_id: str, reason: str) -> PaymentResult:
        """İade — fatura SİLİNMEZ, ters kayıt (credit note) işlenir."""
        if not reason.strip():
            raise PaymentError("İade sebebi gerekli — denetim izi için")
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT intent_id, invoice_id, status FROM payment_intents"
                " WHERE intent_id = ?", (intent_id,)).fetchone()
            if not row:
                raise PaymentError(f"Tahsilat niyeti yok: {intent_id}")
            if row["status"] != PaymentStatus.SUCCEEDED.value:
                raise PaymentError(
                    f"{intent_id} başarı durumunda değil ({row['status']}) — iade edilmez")
            conn.execute(
                "UPDATE payment_intents SET status=? WHERE intent_id=?",
                (PaymentStatus.REFUNDED.value, intent_id))
            conn.execute(
                "INSERT INTO payment_credit_notes (intent_id, invoice_id, reason, created_at)"
                " VALUES (?,?,?,?)",
                (intent_id, row["invoice_id"], reason.strip(), _now()))
            conn.commit()
        logger.warning("ödeme %s iade edildi (credit note) — sebep: %s", intent_id, reason)
        return PaymentResult(intent_id, PaymentStatus.REFUNDED, row["invoice_id"], None,
                             "İade işlendi — fatura ters kayıtla kapatıldı")

    def _sign(self, provider: PaymentProvider, body: bytes) -> str:
        creds = self._psp_creds(provider)
        secret = (creds or {}).get("api_key") or (creds or {}).get("secret") or ""
        return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
