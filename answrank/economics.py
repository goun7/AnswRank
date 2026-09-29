"""Unit Economics, Pricing Calculator & LTV/CAC Projections for AnswRank.

Implements the financial and economic models specified in
Bölüm 7 of ANSWRANK_MASTER_100.md.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel
from answrank.config import settings


class PricingTier(str, Enum):
    QUICK_AUDIT = "QUICK_AUDIT"
    CORE_FIX = "CORE_FIX"
    MONTHLY_RETAINER = "MONTHLY_RETAINER"
    ENTERPRISE = "ENTERPRISE"
    GEO_MONITOR = "GEO_MONITOR"


class PackageDetails(BaseModel):
    tier: PricingTier
    name: str
    price_try: float
    billing_type: str  # "one_time" or "monthly"
    features: List[str]
    target_audience: str
    estimated_cogs_try: float  # Marginal cost of goods sold


class UnitEconomicsMetrics(BaseModel):
    tier: PricingTier
    price_try: float
    cogs_try: float
    gross_profit_try: float
    gross_margin_pct: float
    estimated_cac_try: float
    average_retention_months: float
    ltv_try: float
    ltv_to_cac_ratio: float


class PortfolioProjection(BaseModel):
    active_client_count: int
    mrr_try: float
    arr_try: float
    monthly_cogs_try: float
    monthly_gross_profit_try: float
    gross_margin_pct: float


class EconomicsEngine:
    """Calculates pricing packages, unit economics, and MRR projections."""

    # Pre-defined Packages from Bölüm 7.1
    PACKAGES: Dict[PricingTier, PackageDetails] = {
        PricingTier.GEO_MONITOR: PackageDetails(
            tier=PricingTier.GEO_MONITOR,
            name="GEO İzleme Aylık Aboneliği",
            price_try=settings.monitor_monthly_price_try,
            billing_type="monthly",
            features=[
                "Aylık otomatik denetim + atıf koşusu (anahtarsız yüzeyde SIMÜLASYON etiketiyle)",
                "Alıntı Payı (SoV) ve skor delta kartı — yalnız iki gerçek ölçüm arasında",
                "Madde-7 delta garantisi ölçüm altyapısı (garanti bu koşulara dayanır)",
                "Aylık digest (CLI/API); ölçülemeyen dönem suçlama değil ÖLÇÜLEMEDİ",
            ],
            target_audience="Sonucu sürekli görmek ve garantinin takibini kanıtla izlemek isteyen mevcut retainer müşterileri",
            estimated_cogs_try=350.0,
        ),
        PricingTier.QUICK_AUDIT: PackageDetails(
            tier=PricingTier.QUICK_AUDIT,
            name="Hızlı AEO Denetimi (Quick Audit)",
            price_try=2500.0,
            billing_type="one_time",
            features=[
                "45 Dakikalık Derin AEO Denetimi",
                "20 Sektörel Soru Çoklu-LLM Testi",
                "8 Kategorili Dürüst Skor Kartı + yöntem envanteri (docs/DENETIM_EXCEPT_ENVANTERI.md)",
                "1 Sayfalık Yönetici Raporu (PDF)",
            ],
            target_audience="Farkındalık arayan, mevcut durumunu görmek isteyen klinikler/işletmeler",
            estimated_cogs_try=200.0,
        ),
        PricingTier.CORE_FIX: PackageDetails(
            tier=PricingTier.CORE_FIX,
            name="Temel AEO Düzeltme Paketi (Core Fix)",
            price_try=4500.0,
            billing_type="one_time",
            features=[
                "Hızlı Denetim Kapsamındaki Her Şey",
                f"{settings.ai_bots_total} AI Botu Uyumlu Özel robots.txt (xAI/Grok, Kimi, Brave, Qwen, Cursor dahil)",
                "Standartlara Uygun llms.txt ve llms-full.txt",
                "JSON-LD Schema Markup Kod Blokları",
                "Geliştirici/Ajans Entegrasyon Kılavuzu",
            ],
            target_audience="Mevcut web ekibi/ajansı olup hızlı kod bloklarına ihtiyaç duyanlar",
            estimated_cogs_try=350.0,
        ),
        PricingTier.MONTHLY_RETAINER: PackageDetails(
            tier=PricingTier.MONTHLY_RETAINER,
            name="Tam Görünürlük & Aylık Koruma (Retainer)",
            price_try=6000.0,
            billing_type="monthly",
            features=[
                "İlk Ay Tüm Temel Düzeltmelerin Kurulumu",
                "Haftalık Çoklu-LLM Atıf Taraması (4 Model)",
                "Sözleşmeli Madde 7 Performans Güvencesi (Delta Garantisi)",
                "Aylık LLM Drift & Rakip Takip Raporu",
                "Öncelikli WhatsApp Destek Hattı",
            ],
            target_audience="Aylık 20+ hasta/danışan hedefleyen, yerel otorite olmak isteyen işletmeler",
            estimated_cogs_try=450.0,
        ),
        PricingTier.ENTERPRISE: PackageDetails(
            tier=PricingTier.ENTERPRISE,
            name="Enterprise / Çok Şubeli Markalar",
            price_try=15000.0,
            billing_type="monthly",
            features=[
                "Tüm Retainer Özellikleri",
                "Çoklu Şube / Çoklu Lokasyon Varlık Şeması",
                "Özel AnswRank MCP Sunucu Entegrasyonu",
                "Anlık Rakip Atıf Alarmları (Slack/Webhook)",
                "Çeyreklik Stratejik Danışmanlık Toplantısı",
            ],
            target_audience="Çok şubeli zincir hastaneler, büyük poliklinikler, kurumsal markalar",
            estimated_cogs_try=1200.0,
        ),
    }

    @classmethod
    def calculate_cogs(
        cls,
        question_count: int = 20,
        provider_count: int = 4,
        include_crawl: bool = True,
        usd_to_try: float = 35.0,
    ) -> float:
        """Calculate marginal COGS for running an audit."""
        # Ortalama sorgu maliyeti: $0.025 per question per LLM
        query_cost_usd = question_count * provider_count * 0.025
        query_cost_try = query_cost_usd * usd_to_try
        crawl_cost_try = 50.0 if include_crawl else 0.0
        return round(query_cost_try + crawl_cost_try, 2)

    @classmethod
    def evaluate_unit_economics(
        cls,
        tier: PricingTier,
        custom_cac_try: Optional[float] = None,
        retention_months: Optional[float] = None,
    ) -> UnitEconomicsMetrics:
        """Evaluate LTV, CAC, and margins for a selected pricing package."""
        pkg = cls.PACKAGES[tier]
        cogs = pkg.estimated_cogs_try
        profit = pkg.price_try - cogs
        margin_pct = round((profit / pkg.price_try) * 100, 2)

        # Assumptions
        is_monthly = pkg.billing_type == "monthly"
        avg_retention = retention_months or (6.0 if is_monthly else 1.0)
        cac = custom_cac_try or (1000.0 if is_monthly else 600.0)

        ltv = pkg.price_try * avg_retention
        ltv_cac = round(ltv / cac, 2) if cac > 0 else 0.0

        return UnitEconomicsMetrics(
            tier=tier,
            price_try=pkg.price_try,
            cogs_try=cogs,
            gross_profit_try=profit,
            gross_margin_pct=margin_pct,
            estimated_cac_try=cac,
            average_retention_months=avg_retention,
            ltv_try=ltv,
            ltv_to_cac_ratio=ltv_cac,
        )

    @classmethod
    def project_portfolio(
        cls,
        client_count: int,
        primary_tier: PricingTier = PricingTier.MONTHLY_RETAINER,
    ) -> PortfolioProjection:
        """Calculate MRR, ARR and financial metrics for a target number of clients."""
        pkg = cls.PACKAGES[primary_tier]
        mrr = client_count * pkg.price_try
        arr = mrr * 12.0
        monthly_cogs = client_count * pkg.estimated_cogs_try
        monthly_profit = mrr - monthly_cogs
        margin = round((monthly_profit / mrr) * 100, 2) if mrr > 0 else 0.0

        return PortfolioProjection(
            active_client_count=client_count,
            mrr_try=mrr,
            arr_try=arr,
            monthly_cogs_try=monthly_cogs,
            monthly_gross_profit_try=monthly_profit,
            gross_margin_pct=margin,
        )
