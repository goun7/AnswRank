"""90-Day 4-Phase Execution Roadmap & Milestone Tracker for AnswRank.

Implements the operational roadmap and KPI milestones specified in
Bölüm 11 of ANSWRANK_MASTER_100.md.
"""

from typing import List
from pydantic import BaseModel


class MilestonePhase(BaseModel):
    phase_number: int
    name: str
    day_range: str
    target_kpi: str
    tasks: List[str]
    is_completed: bool = False


class MilestoneProgress(BaseModel):
    current_day: int
    current_phase: int
    active_clients: int
    current_mrr_try: float
    mrr_target_try: float
    progress_pct: float
    status_summary: str
    active_phase_details: MilestonePhase


class MilestonesEngine:
    """Tracks the 90-day 4-phase rollout and KPI achievements."""

    PHASES: List[MilestonePhase] = [
        MilestonePhase(
            phase_number=1,
            name="Faz 1: Doğrulama ve İlk Satışlar (Validation & First Revenue)",
            day_range="Gün 1 - 14",
            target_kpi="İlk 2-3 ücretli müşteri (₺12.000 - ₺18.000 ciro), 5 Calendly görüşmesi",
            tasks=[
                "60 adaylık havuz oluştur ve 5 adımlı eleme filtresiyle 20 A-Tier aday seç.",
                "20 işletmeye kişiselleştirilmiş 45 dakikalık denetim raporu ve DM gönder.",
                "İtiraz yönetimi ve Madde 7 Performans Güvencesi ile ilk satışları kapat.",
            ],
            is_completed=True,  # Validation achieved
        ),
        MilestonePhase(
            phase_number=2,
            name="Faz 2: İlk Teslimatlar ve Delta Ölçümü (Delivery & Delta)",
            day_range="Gün 15 - 30",
            target_kpi="3 müşteride teknik düzeltmelerin yayını, 30. gün S1/S2 delta doğrulaması",
            tasks=[
                "robots.txt, llms.txt, llms-full.txt ve JSON-LD şemalarını web sitelerine yerleştir.",
                "AI crawler bot loglarını (GPTBot, ClaudeBot, PerplexityBot) haftalık tara.",
                "Gün 30: Çoklu-LLM koşumunu tekrarla, delta skorunu ölç ve müşteriye sun.",
            ],
            is_completed=False,
        ),
        MilestonePhase(
            phase_number=3,
            name="Faz 3: Kademe 2 SaaS ve Otonom Araç Geçişi (Automation)",
            day_range="Gün 31 - 60",
            target_kpi="10 aktif retainer müşteri (₺60.000 MRR), MCP sunucu & API entegrasyonu",
            tasks=[
                "FastAPI self-servis arayüzü ve SQLite otomatik raporlama sistemini devreye al.",
                "84-LeadPilot ve 86-CallSnap sinerji kancalarını bağla.",
                "Retainer yenilemelerini otomatik takip tablosuyla yönet.",
            ],
            is_completed=False,
        ),
        MilestonePhase(
            phase_number=4,
            name="Faz 4: Ölçeklenme ve Portföy Entegrasyonu (Full Scale)",
            day_range="Gün 61 - 90",
            target_kpi="20+ aktif müşteri (₺120.000+ MRR / ₺1.4M+ ARR), %95 brüt marj",
            tasks=[
                "Enterprise / Çok Şubeli Markalar paketini (₺15.000/ay) devreye al.",
                "Dikey sektör soru bankasını 3'ten 10 sektöre genişlet (Hukuk, Mimarlık, Turizm).",
                "Portföy yönetim paneline otomatik veri beslemesi sağla.",
            ],
            is_completed=False,
        ),
    ]

    @classmethod
    def evaluate_progress(
        cls,
        current_day: int,
        active_clients: int,
        current_mrr_try: float,
    ) -> MilestoneProgress:
        """Evaluate overall progress against 90-day targets."""
        if current_day <= 14:
            phase_idx = 0
            mrr_target = 18000.0
        elif current_day <= 30:
            phase_idx = 1
            mrr_target = 30000.0
        elif current_day <= 60:
            phase_idx = 2
            mrr_target = 60000.0
        else:
            phase_idx = 3
            mrr_target = 120000.0

        active_phase = cls.PHASES[phase_idx]
        progress_ratio = min(1.0, current_mrr_try / mrr_target) if mrr_target > 0 else 0.0
        pct = round(progress_ratio * 100.0, 1)

        summary = (
            f"Gün {current_day} ({active_phase.name}) · Aktif Müşteri: {active_clients} · "
            f"MRR: ₺{current_mrr_try:,.2f} / Hedef: ₺{mrr_target:,.2f} (%{pct} başarı)."
        )

        return MilestoneProgress(
            current_day=current_day,
            current_phase=phase_idx + 1,
            active_clients=active_clients,
            current_mrr_try=current_mrr_try,
            mrr_target_try=mrr_target,
            progress_pct=pct,
            status_summary=summary,
            active_phase_details=active_phase,
        )
