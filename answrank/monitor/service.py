"""MonitorService — aylık otomatik ölçüm koşuları ve dürüst delta digest'i.

Ölçüm-kapısı (D-16.09-G) izleme yüzeyindeki hali: delta ancak İKİ gerçek
MEASURED koşu arasında vardır. Koşu yoksa ÖLÇÜLEMEDİ, tek koşu varsa İLK ÖLÇÜM;
UNAUDITABLE koşular seriye sayılmaz ama digest'te şeffaf biçimde anılır.
Varsayılan executor canlıdır (denetim + atıf); testler enjekte eder.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional

from answrank.db import Database

Executor = Callable[[str, str, str], Coroutine[Any, Any, Dict[str, Any]]]


class MonitorService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # ------------------------------------------------------------- yönetim
    def add(self, domain: str, brand: str, sector: str = "general",
            cadence_days: int = 30, contract_id: Optional[str] = None,
            now: Optional[datetime] = None) -> str:
        """İzleme kaydı ekler."""
        when = (now or datetime.now()).isoformat(timespec="seconds")
        mid = "mon_" + secrets.token_hex(6)
        self.db.create_monitor(mid, domain, brand, sector, cadence_days, contract_id, when)
        return mid

    def list(self) -> List[Dict[str, Any]]:
        """list kayıtlarını listeler."""
        return self.db.list_monitors()

    def due(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Vadesi gelen due kayıtlarını döndürür."""
        return self.db.due_monitors((now or datetime.now()).isoformat(timespec="seconds"))

    # ------------------------------------------------------------- koşum
    async def run_due(self, executor: Executor, now: Optional[datetime] = None) -> List[int]:
        """Vadesi gelen tüm izlemeleri yürütür."""
        ids = []
        for m in self.due(now):
            ids.append(await self.run_one(m["id"], executor=executor, now=now))
        return ids

    async def run_one(self, monitor_id: str, executor: Executor,
                      now: Optional[datetime] = None) -> int:
        """Tek bir izlemeyi yürütür."""
        m = self.db.get_monitor(monitor_id)
        if not m:
            raise KeyError(f"monitor {monitor_id} yok — uydurma kayıt işlenmez")
        now = now or datetime.now()
        try:
            res = await executor(m["domain"], m["sector"], m["brand"])
        except Exception as exc:  # executor ağı — kayıt DÜŞÜR ama suçlama üretmez
            res = {"status": "UNAUDITABLE", "score_base": None, "sov_pct": None,
                   "audit_id": None, "citation_run_id": None,
                   "note": f"DOĞRULANAMADI ({type(exc).__name__})"}
        run_id = self.db.insert_monitor_run(
            monitor_id, now.isoformat(timespec="seconds"), res.get("status", "UNAUDITABLE"),
            res.get("score_base"), res.get("sov_pct"), res.get("audit_id"),
            res.get("citation_run_id"), res.get("note", ""))
        self.db.postpone_next_due(monitor_id, now + timedelta(days=int(m["cadence_days"])))
        return run_id

    # ------------------------------------------------------------- digest
    def digest(self, monitor_id: str) -> Dict[str, Any]:
        """İzleme özet raporu üretir."""
        m = self.db.get_monitor(monitor_id)
        if not m:
            raise KeyError(f"monitor {monitor_id} yok — uydurma kayıt işlenmez")
        runs = self.db.monitor_runs(monitor_id)
        measured = [r for r in runs if r["status"] == "MEASURED"]
        out: Dict[str, Any] = {"monitor_id": monitor_id, "domain": m["domain"],
                               "status": "ÖLÇÜLEMEDİ", "baseline": None, "latest": None,
                               "delta_base": None, "delta_sov": None, "runs": len(runs)}
        last = runs[-1] if runs else None
        if not measured:
            out["text"] = (f"{m['domain']}: henüz ölçümlü koşu yok ({len(runs)} deneme, "
                           "hepsi ölçülemedi) — sayı uydurulmaz.")
            return out
        base, latest = measured[0], measured[-1]
        out["baseline"] = {k: base[k] for k in ("ran_at", "score_base", "sov_pct")}
        out["latest"] = {k: latest[k] for k in ("ran_at", "score_base", "sov_pct")}
        if len(measured) == 1:
            out["status"] = "İLK ÖLÇÜM"
            out["text"] = (f"{m['domain']}: ilk ölçüm {base['ran_at']} — taban skor "
                           f"{base['score_base']}, SoV %{base['sov_pct']}; delta henüz hesaplanamaz "
                           "(tek ölçüm kıyaslanamaz).")
        else:
            out["status"] = "İZLENİYOR"
            out["delta_base"] = round(float(latest["score_base"]) - float(base["score_base"]), 1)
            db_sov = None
            if latest.get("sov_pct") is not None and base.get("sov_pct") is not None:
                db_sov = round(float(latest["sov_pct"]) - float(base["sov_pct"]), 1)
            out["delta_sov"] = db_sov
            out["text"] = (f"{m['domain']}: {base['ran_at']} → {latest['ran_at']} arası ölçülen "
                           f"delta skor {out['delta_base']:+.1f} puan"
                           + (f", SoV {db_sov:+.1f} pp" if db_sov is not None else "")
                           + " (yalnız iki gerçek ölçüm arasındadır).")
        if last is not None and last["status"] != "MEASURED":
            out["text"] += " Son koşu ÖLÇÜLEMEDİ — ölçülemeyen dönem garanti hükmü taşımaz."
        return out


async def live_executor(domain: str, sector: str, brand: str) -> Dict[str, Any]:
    """Varsayılan canlı ölçüm: taban denetim + atıf koşusu (runner kendi
    canlı/SİM etiketini taşır). Ulaşılamaz hedef UNAUDITABLE döner — asla 0 puanlık
    bir 'kötü site' suçu değil."""
    from answrank.audit.engine import AuditEngine
    audit = await AuditEngine().audit_url(f"https://{domain}", sector=sector)
    if audit.score_band == "ÖLÇÜLEMEDİ" or getattr(audit, "deep_tier", None) == "UNAUDITABLE":
        return {"status": "UNAUDITABLE", "score_base": None, "sov_pct": None,
                "audit_id": None, "citation_run_id": None, "note": "DOĞRULANAMADI"}
    from answrank.citations.runner import MultiLLMCitationRunner
    from answrank.db import Database
    run = await MultiLLMCitationRunner().run_citations(brand, domain, sector=sector)
    db = Database()
    await db.save_audit(audit)
    await db.save_citations(run)
    return {"status": "MEASURED", "score_base": float(audit.overall_score),
            "sov_pct": float(run.citation_rate_percentage),
            "audit_id": getattr(audit, "audit_id", None),
            "citation_run_id": run.run_id, "note": ""}
