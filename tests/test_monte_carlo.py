"""Tests for Monte Carlo Stochastic Citation Stability Engine."""

import pytest
from unittest.mock import AsyncMock, patch

from answrank.citations.key_manager import HybridKeyManager, LLMProvider
from answrank.citations.monte_carlo import MonteCarloEngine, MonteCarloRunResult
from answrank.citations.runner import MultiLLMCitationRunner
from answrank.models import CitationRunResult, CitationQueryItem, utc_now


@pytest.mark.anyio
async def test_monte_carlo_simulation_mode_is_honest():
    """Without provider keys, the engine must report simulation mode as statistically invalid."""
    res: MonteCarloRunResult = await MonteCarloEngine.evaluate_stochastic_stability(
        brand_name="TestDental",
        domain="testdental.com",
        sector="dental",
        city="İstanbul",
        iterations=3,
    )
    assert res.iterations_count == 3
    assert len(res.iterations) == 3
    assert res.mean_citation_rate_pct >= 0.0
    assert "p=0.95" in res.confidence_interval_95_str
    # Honest simulation labelling
    assert res.is_statistically_valid is False
    assert res.measurement_mode == "DETERMINISTIC_SIMULATION"
    assert res.stability_grade == "SIMULATION_MODE"
    assert "İSTATİSTİKSEL OLARAK GEÇERSİZ" in res.summary_report
    # Deterministic engine -> zero variance across iterations
    assert res.standard_deviation == 0.0


@pytest.mark.anyio
async def test_monte_carlo_live_variance_mode():
    """With live API responses, the engine reports LIVE_VARIANCE with real measured rates."""
    km = HybridKeyManager(custom_keys={LLMProvider.PERPLEXITY: "fake_key"})
    runner = MultiLLMCitationRunner(key_manager=km)

    # Simulate varying live responses across iterations (models genuinely vary)
    iteration_results = []

    def make_result(rate_pct: float, live_items: int = 80) -> CitationRunResult:
        cited = int(rate_pct / 100 * 80)
        items = []
        for i in range(80):
            items.append(
                CitationQueryItem(
                    question_id=i // 4,
                    question=f"Soru {i // 4}",
                    model="Perplexity-Sonar",
                    brand_mentioned=i < cited,
                    domain_cited=i < cited,
                    raw_snippet="...",
                    was_simulated=False,
                )
            )
        return CitationRunResult(
            run_id="x",
            brand_name="TestDental",
            domain="testdental.com",
            sector="dental",
            city="İstanbul",
            timestamp=utc_now(),
            total_runs=80,
            brand_citations_found=cited,
            citation_rate_percentage=rate_pct,
            live_items_count=live_items,
            live_response_rate_percentage=live_items / 80 * 100,
            is_fully_live=live_items == 80,
            items=items,
        )

    rates = [40.0, 50.0, 30.0]  # genuinely varying measurements
    for r in rates:
        iteration_results.append(make_result(r))

    with patch.object(runner, "run_citations", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = iteration_results
        res = await MonteCarloEngine.evaluate_stochastic_stability(
            brand_name="TestDental",
            domain="testdental.com",
            sector="dental",
            city="İstanbul",
            iterations=3,
            runner=runner,
        )

    assert res.is_statistically_valid is True
    assert res.measurement_mode == "LIVE_VARIANCE"
    assert res.stability_grade != "SIMULATION_MODE"
    # Mean of the actual measured rates
    assert res.mean_citation_rate_pct == 40.0
    # Std dev of [40, 50, 30] (sample) = 10.0
    assert res.standard_deviation == 10.0
    # Iteration summaries carry the actual temperatures from the ladder
    assert [it.temperature for it in res.iterations] == [0.1, 0.3, 0.5]
    assert all(it.live_items == 80 for it in res.iterations)

# --- Branch coverage: single-iteration, all stability grades, fragile/solid questions ---

def _make_result(rate_pct: float, live_items: int = 80, n_questions: int = 4) -> CitationRunResult:
    total = n_questions * 20
    cited = int(rate_pct / 100 * total)
    # Cite only the FIRST question so others become fragile when rates vary
    items = []
    per_q = total // n_questions
    for i in range(total):
        q_idx = i // per_q
        is_cited = i < cited
        items.append(
            CitationQueryItem(
                question_id=q_idx,
                question=f"Soru {q_idx}",
                model="Perplexity-Sonar",
                brand_mentioned=is_cited,
                domain_cited=is_cited,
                raw_snippet="...",
                was_simulated=False,
            )
        )
    return CitationRunResult(
        run_id="x",
        brand_name="TestDental",
        domain="testdental.com",
        sector="dental",
        city="İstanbul",
        timestamp=utc_now(),
        total_runs=total,
        brand_citations_found=cited,
        citation_rate_percentage=rate_pct,
        live_items_count=live_items,
        live_response_rate_percentage=live_items / total * 100,
        is_fully_live=live_items == total,
        items=items,
    )


async def _run_with_rates(rates):
    km = HybridKeyManager(custom_keys={LLMProvider.PERPLEXITY: "fake_key"})
    runner = MultiLLMCitationRunner(key_manager=km)
    results = [_make_result(r) for r in rates]
    with patch.object(runner, "run_citations", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = results
        return await MonteCarloEngine.evaluate_stochastic_stability(
            brand_name="TestDental",
            domain="testdental.com",
            sector="dental",
            city="İstanbul",
            iterations=len(rates),
            runner=runner,
        )


@pytest.mark.anyio
async def test_single_iteration_zero_margin():
    """n=1 -> std_dev=0, margin_error=0 branch."""
    res = await _run_with_rates([50.0])
    assert res.iterations_count == 1
    assert res.standard_deviation == 0.0
    assert "± %0.0" in res.confidence_interval_95_str


@pytest.mark.anyio
async def test_stability_grade_rock_solid():
    """Tiny variance -> ROCK_SOLID."""
    res = await _run_with_rates([80.0, 81.0, 80.5])
    assert res.stability_grade == "ROCK_SOLID"
    assert "MÜKEMMEL KARARLILIK" in res.summary_report


@pytest.mark.anyio
async def test_stability_grade_stable():
    """Moderate variance (stability 70-85) -> STABLE."""
    res2 = await _run_with_rates([60.0, 85.0, 70.0])  # cv ~0.175 -> stability ~82 -> STABLE
    assert res2.stability_grade == "STABLE"
    assert "GÜVENİLİR ATIF" in res2.summary_report


@pytest.mark.anyio
async def test_stability_grade_volatile():
    """High variance (stability 50-70) -> VOLATILE."""
    res = await _run_with_rates([30.0, 80.0, 50.0])  # cv ~0.47 -> stability ~53 -> VOLATILE
    assert res.stability_grade == "VOLATILE"
    assert "DALGALI" in res.summary_report


@pytest.mark.anyio
async def test_stability_grade_critical_fragility():
    """Extreme variance (stability <50) -> CRITICAL_FRAGILITY."""
    res = await _run_with_rates([10.0, 90.0, 50.0])  # cv ~0.65 -> stability ~35
    assert res.stability_grade == "CRITICAL_FRAGILITY"
    assert "KRİTİK KIRILGANLIK" in res.summary_report


def _make_one_item_per_question(cited_question_ids, total_questions=4):
    """Each question has exactly ONE item, so per-question hit counting == iteration counting."""
    items = []
    for q in range(total_questions):
        items.append(
            CitationQueryItem(
                question_id=q,
                question=f"Soru {q}",
                model="Perplexity-Sonar",
                brand_mentioned=q in cited_question_ids,
                domain_cited=q in cited_question_ids,
                raw_snippet="...",
                was_simulated=False,
            )
        )
    n_cited = len(cited_question_ids)
    return CitationRunResult(
        run_id="x",
        brand_name="TestDental",
        domain="testdental.com",
        sector="dental",
        city="İstanbul",
        timestamp=utc_now(),
        total_runs=total_questions,
        brand_citations_found=n_cited,
        citation_rate_percentage=n_cited / total_questions * 100,
        live_items_count=total_questions,
        live_response_rate_percentage=100.0,
        is_fully_live=True,
        items=items,
    )


async def _run_one_item_iterations(citation_sets):
    km = HybridKeyManager(custom_keys={LLMProvider.PERPLEXITY: "fake_key"})
    runner = MultiLLMCitationRunner(key_manager=km)
    results = [_make_one_item_per_question(s) for s in citation_sets]
    with patch.object(runner, "run_citations", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = results
        return await MonteCarloEngine.evaluate_stochastic_stability(
            brand_name="TestDental",
            domain="testdental.com",
            sector="dental",
            city="İstanbul",
            iterations=len(results),
            runner=runner,
        )


@pytest.mark.anyio
async def test_solid_and_fragile_question_split():
    """Q0 cited in all iterations (solid); Q1 cited in only one (fragile); Q2/Q3 never (neither)."""
    res = await _run_one_item_iterations([{0, 1}, {0}, {0}])
    # rates: 50, 25, 25 -> cv>0 -> volatile-ish; key assertion is the split
    assert "Soru 0" in res.solid_questions
    assert res.solid_questions_count == 1
    assert "Soru 1" in res.fragile_questions
    assert res.fragile_questions_count == 1
    assert res.solid_questions_count + res.fragile_questions_count == 2
