"""Tests for Unit Economics & Pricing Model."""

from answrank.economics import EconomicsEngine, PricingTier


def test_packages_exist():
    assert len(EconomicsEngine.PACKAGES) == 5  # + E1 GEO İzleme (D-16.09-M)
    assert PricingTier.MONTHLY_RETAINER in EconomicsEngine.PACKAGES
    assert EconomicsEngine.PACKAGES[PricingTier.MONTHLY_RETAINER].price_try == 6000.0


def test_monitor_package_price_is_config_single_source():
    from answrank.config import settings
    pkg = EconomicsEngine.PACKAGES[PricingTier.GEO_MONITOR]
    assert pkg.price_try == settings.monitor_monthly_price_try


def test_calculate_cogs():
    cogs = EconomicsEngine.calculate_cogs(question_count=20, provider_count=4, include_crawl=True)
    assert cogs > 0
    # 20 * 4 * 0.025 * 35 = 70 TL + 50 TL crawl = 120 TL
    assert cogs == 120.0


def test_evaluate_unit_economics_retainer():
    metrics = EconomicsEngine.evaluate_unit_economics(PricingTier.MONTHLY_RETAINER)
    assert metrics.price_try == 6000.0
    assert metrics.gross_profit_try > 5000.0
    assert metrics.gross_margin_pct > 90.0
    assert metrics.ltv_try == 36000.0
    assert metrics.ltv_to_cac_ratio > 30.0


def test_project_portfolio():
    proj = EconomicsEngine.project_portfolio(client_count=20, primary_tier=PricingTier.MONTHLY_RETAINER)
    assert proj.active_client_count == 20
    assert proj.mrr_try == 120000.0
    assert proj.arr_try == 1440000.0
    assert proj.gross_margin_pct > 90.0
