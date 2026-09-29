"""Candidate Qualification & Intake Scoring Engine for AnswRank CRM.

Implements the 5-step qualification filter (Bölüm 6.1) and
the Calendly intake scoring rubric (EK E) from ANSWRANK_MASTER_100.md.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    """Business candidate profile for AEO/GEO qualification."""
    company_name: str
    sector: str  # dental, accountant, aesthetics, etc.
    domain: Optional[str] = None
    has_custom_domain: bool = True
    estimated_ticket_size: float = 0.0  # Average transaction size in TRY
    estimated_annual_revenue: float = 0.0  # Annual revenue in TRY
    has_ad_spend: bool = False  # Active Google/Meta ads or marketing
    direct_decision_maker_access: bool = False  # Direct contact with owner/partner
    ai_missing_in_top5: bool = True  # Not cited in top 5 industry questions
    has_competitor_cited: bool = True  # At least 1 competitor cited by AI


class QualificationResult(BaseModel):
    """Result of the 5-step qualification gate."""
    is_qualified: bool
    score: int  # 0 to 5
    passed_criteria: List[str] = Field(default_factory=list)
    failed_criteria: List[str] = Field(default_factory=list)
    reason: str


class IntakeResponse(BaseModel):
    """Answers submitted during intake/Calendly booking."""
    monthly_new_client_goal: str  # "under_10", "10_20", "20_50", "50_plus"
    monthly_marketing_budget: str  # "under_10k", "10k_30k", "30k_plus"
    ai_visibility_awareness: str  # "tested_not_cited", "unknown", "already_ranking"
    decision_maker_status: str  # "sole_owner", "partner_consensus", "employee_agency"
    action_timeline: str  # "immediately_14d", "within_30d", "just_researching"


class IntakeScoreResult(BaseModel):
    """Evaluated intake score and prioritization tier."""
    total_score: int  # 0 to 100
    priority_tier: str  # "PRIORITY_A", "PRIORITY_B", "DISQUALIFIED"
    recommended_action: str
    score_breakdown: Dict[str, int]


class CandidateQualifier:
    """Evaluates candidates against 5-step criteria and intake forms."""

    # Threshold constants
    MIN_TICKET_SIZE_TRY = 3000.0
    MIN_ANNUAL_REVENUE_TRY = 1500000.0

    @classmethod
    def qualify_candidate(cls, candidate: CandidateProfile) -> QualificationResult:
        """Evaluate candidate against 5 core criteria (Bölüm 6.1)."""
        passed = []
        failed = []

        # 1. Ciro & Bilet Eşiği
        has_economic_capacity = (
            candidate.estimated_ticket_size >= cls.MIN_TICKET_SIZE_TRY
            or candidate.estimated_annual_revenue >= cls.MIN_ANNUAL_REVENUE_TRY
        )
        if has_economic_capacity:
            passed.append("1. Ciro & Bilet Eşiği (Ort. İşlem >= ₺3.000 veya Yıllık Ciro >= ₺1.5M)")
        else:
            failed.append("1. Ciro & Bilet Eşiği yetersiz (₺3.000 bilet veya ₺1.5M ciro altında)")

        # 2. Web Varlığı
        if candidate.has_custom_domain and candidate.domain:
            passed.append("2. Web Varlığı (Özel domain ve aktif web sitesi mevcut)")
        else:
            failed.append("2. Web Varlığı eksik (Domain yok veya salt sosyal medya profili)")

        # 3. Dijital Farkındalık
        if candidate.has_ad_spend:
            passed.append("3. Dijital Farkındalık (Aktif reklam/pazarlama harcaması var)")
        else:
            failed.append("3. Dijital Farkındalık (Aktif reklam bütçesi tespit edilemedi)")

        # 4. Karar Vericiye Erişim
        if candidate.direct_decision_maker_access:
            passed.append("4. Karar Vericiye Erişim (Kurucu/hekim/ortakla doğrudan temas kanalı)")
        else:
            failed.append("4. Karar Vericiye Erişim (Doğrudan yetkiliye ulaşılamıyor)")

        # 5. Karşılaştırmalı Boşluk (Comparative Gap)
        if candidate.ai_missing_in_top5 and candidate.has_competitor_cited:
            passed.append("5. Karşılaştırmalı Boşluk (İşletme AI'da yok, en az 1 rakibi kaynak gösteriliyor)")
        else:
            failed.append("5. Karşılaştırmalı Boşluk (Rakip atfı yok veya işletme zaten sıralanıyor)")

        score = len(passed)
        is_qualified = score >= 4  # En az 4/5 kriteri geçmeli

        if is_qualified:
            reason = f"Aday {score}/5 kriteri sağladı. 45 dakikalık derin denetim ve DM için uygun."
        else:
            reason = f"Aday {score}/5 kriterde kaldı ({len(failed)} eksik). Operasyonel filtreye takıldı."

        return QualificationResult(
            is_qualified=is_qualified,
            score=score,
            passed_criteria=passed,
            failed_criteria=failed,
            reason=reason,
        )

    @classmethod
    def score_intake(cls, intake: IntakeResponse) -> IntakeScoreResult:
        """Calculate 0-100 intake score from Calendly/form submission (EK E)."""
        breakdown: Dict[str, int] = {}

        # Soru 1: Aylık yeni hasta/müşteri hedefi (Maks 30p)
        goal_map = {
            "50_plus": 30,
            "20_50": 25,
            "10_20": 15,
            "under_10": 5,
        }
        breakdown["client_goal"] = goal_map.get(intake.monthly_new_client_goal, 5)

        # Soru 2: Mevcut dijital pazarlama bütçesi (Maks 25p)
        budget_map = {
            "30k_plus": 25,
            "10k_30k": 15,
            "under_10k": 5,
        }
        breakdown["marketing_budget"] = budget_map.get(intake.monthly_marketing_budget, 5)

        # Soru 3: AI görünürlük farkındalığı (Maks 20p)
        awareness_map = {
            "tested_not_cited": 20,
            "unknown": 10,
            "already_ranking": 5,
        }
        breakdown["ai_awareness"] = awareness_map.get(intake.ai_visibility_awareness, 10)

        # Soru 4: Karar verici durumu (Maks 15p)
        dm_map = {
            "sole_owner": 15,
            "partner_consensus": 10,
            "employee_agency": 0,
        }
        breakdown["decision_maker"] = dm_map.get(intake.decision_maker_status, 0)

        # Soru 5: Aksiyon takvimi (Maks 10p)
        timeline_map = {
            "immediately_14d": 10,
            "within_30d": 5,
            "just_researching": 0,
        }
        breakdown["timeline"] = timeline_map.get(intake.action_timeline, 0)

        total_score = sum(breakdown.values())

        if total_score >= 70:
            priority = "PRIORITY_A"
            rec = "VIP Görüşme + 45 dk Canlı Denetim Ekranı. 24 saat içinde temas kurun."
        elif total_score >= 50:
            priority = "PRIORITY_B"
            rec = "Standart Acı Odaklı Denetim Raporu PDF iletilmeli ve 48 saatte takip edilmeli."
        else:
            priority = "DISQUALIFIED"
            rec = "Yetersiz bütçe veya yetki. Otomatik AEO Rehberi gönder ve kaynak harcama."

        return IntakeScoreResult(
            total_score=total_score,
            priority_tier=priority,
            recommended_action=rec,
            score_breakdown=breakdown,
        )
