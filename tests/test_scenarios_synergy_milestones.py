"""Tests for Operational Scenarios (S1-S4), Cross-Portfolio Synergy & Milestones."""

from answrank.audit.scenarios import ScenarioRouter, ScenarioCode
from answrank.crm.milestones import MilestonesEngine


def test_scenario_router_s1_success():
    res = ScenarioRouter.evaluate(
        baseline_score=40.0,
        current_score=70.0,  # Delta +30 >= 25
        baseline_citations=1,
        current_citations=5,
    )
    assert res.scenario == ScenarioCode.S1_SUCCESS
    assert res.trigger_free_month is False


def test_scenario_router_s2_partial_success():
    res = ScenarioRouter.evaluate(
        baseline_score=40.0,
        current_score=50.0,  # Delta +10 < 25
        baseline_citations=10,
        current_citations=11,  # +10% < 30%
    )
    assert res.scenario == ScenarioCode.S2_PARTIAL_SUCCESS
    assert res.trigger_free_month is True


def test_scenario_router_s3_zero_delta():
    res = ScenarioRouter.evaluate(
        baseline_score=40.0,
        current_score=38.0,
        baseline_citations=2,
        current_citations=1,
    )
    assert res.scenario == ScenarioCode.S3_ZERO_DELTA
    assert res.trigger_free_month is True


def test_scenario_router_s4_client_inaction():
    res = ScenarioRouter.evaluate(
        baseline_score=40.0,
        current_score=40.0,
        baseline_citations=0,
        current_citations=0,
        client_cooperation_ok=False,
    )
    assert res.scenario == ScenarioCode.S4_CLIENT_INACTION
    assert res.trigger_free_month is False


def test_milestones_engine_day_14():
    res = MilestonesEngine.evaluate_progress(current_day=14, active_clients=3, current_mrr_try=18000.0)
    assert res.current_phase == 1
    assert res.progress_pct == 100.0
    assert "Doğrulama ve İlk Satışlar" in res.active_phase_details.name


def test_milestones_engine_day_45():
    res = MilestonesEngine.evaluate_progress(current_day=45, active_clients=8, current_mrr_try=48000.0)
    assert res.current_phase == 3
    assert res.progress_pct == 80.0
