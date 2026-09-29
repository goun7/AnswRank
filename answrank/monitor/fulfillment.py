"""E6 — Madde 7.3 garanti icra (fulfillment) motoru.

Sözleşmenin sattığı hüküm: 30. gün sonunda hedef delta yoksa takip eden ay
HİÇBİR EK ÜCRET (₺0/AED 0) olmadan icra edilir. Bu motor hükmü YALNIZ gerçek
izleme ölçümleriyle değerlendirir:

  * izleme ↔ sözleşme bağı yok  → NO_LINK (hüküm kurulamaz; boş varsayım yok)
  * iki ölçümlü koşu yok        → INSUFFICIENT ("ÖLÇÜM YETERSİZ" — sayı uydurulmaz)
  * delta < eşik                → TRIGGERED (FREE-CYCLE kaydı + 7.3 gerekçesi)
  * delta ≥ eşik                → SATISFIED (ölçümlü karşılama kaydı)

Eşik settings.monitor_guarantee_score_delta_min (=12, satılan bandın tabanı).
"""
from __future__ import annotations
import logging

from datetime import datetime, timezone
from typing import Dict, List, Optional

from answrank.config import settings
from answrank.monitor.service import MonitorService


logger = logging.getLogger("answrank.fulfillment")

class FulfillmentEvaluator:
    NO_LINK = "NO_LINK"
    INSUFFICIENT = "INSUFFICIENT"
    TRIGGERED = "TRIGGERED"
    SATISFIED = "SATISFIED"

    def __init__(self, db=None):
        self.svc = MonitorService(db=db)
        self.db = self.svc.db

    def evaluate(self, monitor_id: str, now: Optional[datetime] = None) -> Dict:
        """Tek bir teslimat kuralını değerlendirir."""
        m = self.db.get_monitor(monitor_id)
        if not m:
            raise KeyError(f"İzleme kaydı yok: {monitor_id}")
        when = now or datetime.now(timezone.utc)
        if not m.get("contract_id"):
            ev = {"monitor_id": monitor_id, "contract_id": None, "kind": self.NO_LINK,
                  "delta": None, "free_cycle_id": None,
                  "reason": "Madde-7 fulfillment'ı izlemeye, izleme sözleşmeye bağlıdır — "
                            "bağ yoksa hüküm kurulamaz, sayı üretilmez."}
            return ev
        d = self.svc.digest(monitor_id)
        if d["status"] != "İZLENİYOR" or d.get("delta_base") is None:
            ev = {"monitor_id": monitor_id, "contract_id": m["contract_id"],
                  "kind": self.INSUFFICIENT, "delta": None, "free_cycle_id": None,
                  "reason": "ÖLÇÜM YETERSİZ — delta hükmü için iki ölçümlü koşu gerekir; "
                            "sayı uydurulmaz."}
            self._persist(ev)
            return ev
        delta = float(d["delta_base"])
        thr = settings.monitor_guarantee_score_delta_min
        if delta >= thr:
            ev = {"monitor_id": monitor_id, "contract_id": m["contract_id"],
                  "kind": self.SATISFIED, "delta": delta, "free_cycle_id": None,
                  "reason": f"Güvence karşlandı: ölçülen delta +{delta:.1f} ≥ +{thr} "
                            "(iki MEASURED koşu arasıdır; uydurma değildir)."}
        else:
            free = f"FREE-CYCLE-{monitor_id[-6:]}-{when.strftime('%Y%m%d')}"
            ev = {"monitor_id": monitor_id, "contract_id": m["contract_id"],
                  "kind": self.TRIGGERED, "delta": delta, "free_cycle_id": free,
                  "reason": f"MADDE 7.3 TETİKLENDİ: ölçülen delta +{delta:.1f} < +{thr} — "
                            f"takip eden 30 günlük çalışma takvimi HİÇBİR EK ÜCRET talep "
                            f"edilmeden icra edilecek. Kayıt: {free}."}
        self._persist(ev)
        return ev

    def _persist(self, ev: Dict) -> None:
        if ev["kind"] == self.TRIGGERED:
            # Gelir-düşüren karar: operatör onayı gerektirir — tek kuyrukta maddelenir.
            from answrank.queue import ApprovalQueue
            ApprovalQueue(db=self.db).add("FREE_CYCLE", ev["free_cycle_id"],
                                          "MADDE 7.3 — " + ev["reason"])
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO fulfillment_events (monitor_id, contract_id, kind, delta,"
                " free_cycle_id, reason, evaluated_at) VALUES (?,?,?,?,?,?,?)",
                (ev["monitor_id"], ev["contract_id"], ev["kind"], ev["delta"],
                 ev["free_cycle_id"], ev["reason"],
                 datetime.now(timezone.utc).isoformat()))
            conn.commit()

    def list_events(self, monitor_id: Optional[str] = None) -> List[Dict]:
        """events kayıtlarını listeler."""
        q = "SELECT * FROM fulfillment_events"
        args: tuple = ()
        if monitor_id:
            q += " WHERE monitor_id = ?"
            args = (monitor_id,)
        with self.db._get_connection() as conn:
            return [dict(r) for r in conn.execute(q + " ORDER BY id", args)]

    def evaluate_all(self, now: Optional[datetime] = None) -> List[Dict]:
        """Tüm teslimat kurallarını değerlendirir."""
        out = []
        for m in self.svc.list():
            try:
                out.append(self.evaluate(m["id"], now=now))
            except KeyError:
                logger.debug("fulfillment: monitor koşu arasında buharlaştı — atlandı: %s", m["id"])
                continue
        return out
