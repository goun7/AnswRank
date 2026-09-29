"""Delta Tracking and Contractual Performance Guarantee Engine (Madde 7.3)."""

import uuid
from typing import Optional
from answrank.models import AuditResult, DeltaLog, utc_now
from answrank.db import Database

class DeltaEngine:
    """Denetim skoru deltalarını hesaplar ve sözleşmesel performans garantisini değerlendirir.

       DİKKAT: overall_score sorgu-bağımsız bir AEO/GEO denetim skorudur; ölçülmüş
    canlı-atıf görünürlüğü DEĞİL. arXiv:2609.07559 sorgu-bağımsız deterministik
    içerik skorlarının atıf sinyaliyle within-query Spearman'ının 0.11 olduğunu
    gösterdi — bu sınıf skor kalite filtresidir, atıf tahmincisi değildir.
    Madde-7.3 bu skoru sözleşmesel ölçü birimi olarak kullanır; "görünürlük
    skoru" olarak etiketlenmemelidir."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def calculate_delta(
        self,
        baseline_audit: AuditResult,
        current_audit: AuditResult,
        prospect_id: Optional[str] = None,
        days_elapsed: int = 30,
        guarantee_threshold: int = 12,
    ) -> DeltaLog:
        """
        Calculates score delta between baseline and current audit.
        Evaluates Madde 7.3: score_delta >= 12% -> guarantee met.
        """
        b_score = baseline_audit.overall_score
        c_score = current_audit.overall_score
        score_delta = c_score - b_score

        if b_score > 0:
            percentage_change = round(((c_score - b_score) / b_score) * 100, 1)
        else:
            percentage_change = float(c_score * 100) if c_score > 0 else 0.0

        is_guarantee_met = score_delta >= guarantee_threshold

        pid = prospect_id or baseline_audit.domain

        return DeltaLog(
            prospect_id=pid,
            baseline_score=b_score,
            current_score=c_score,
            score_delta=score_delta,
            percentage_change=percentage_change,
            is_guarantee_met=is_guarantee_met,
            days_elapsed=days_elapsed,
        )

    async def record_delta(
        self,
        delta_log: DeltaLog,
    ) -> None:
        """Saves delta record to SQLite database."""
        def _sync_save():
            with self.db._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO delta_logs (
                        id, prospect_id, baseline_score, current_score,
                        score_delta, percentage_change, is_guarantee_met, days_elapsed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"delta_{uuid.uuid4().hex[:10]}",
                        delta_log.prospect_id,
                        delta_log.baseline_score,
                        delta_log.current_score,
                        delta_log.score_delta,
                        delta_log.percentage_change,
                        delta_log.is_guarantee_met,
                        delta_log.days_elapsed,
                        utc_now().isoformat(),
                    ),
                )
                conn.commit()

        import asyncio
        await asyncio.to_thread(_sync_save)
