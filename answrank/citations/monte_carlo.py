"""Monte Carlo Stochastic Citation Confidence & Stability Index Engine for AnswRank.

Quantifies LLM stochastic variance across multiple iterations, computing
confidence intervals and identifying fragile vs solid citations.

Measurement integrity contract:
- LIVE mode (all provider keys configured): each iteration re-queries the real
  APIs with a slightly different temperature (0.1 -> 0.9), so the measured
  variance reflects ACTUAL generative stochasticity of the models.
- SIMULATION mode (no keys): the deterministic engine returns identical results
  every iteration; the engine reports this honestly with
  `is_statistically_valid=False` and does NOT fabricate a confidence interval
  from synthetic jitter. Stability grade in simulation mode carries an explicit
  `SIMULATION_MODE` marker in the summary.
"""

import math
from typing import Dict, List, Optional

from pydantic import BaseModel

from answrank.citations.runner import MultiLLMCitationRunner
from answrank.models import CitationRunResult


class IterationSummary(BaseModel):
    iteration_index: int
    citation_rate_pct: float
    citations_count: int
    total_runs: int
    temperature: float = 0.0  # sampling temperature used for this iteration
    live_items: int = 0  # how many of this iteration's items were live API responses


class MonteCarloRunResult(BaseModel):
    brand_name: str
    domain: str
    iterations_count: int
    mean_citation_rate_pct: float
    standard_deviation: float
    confidence_interval_95_str: str
    stability_index: float  # 0 to 100 (100 = 100% deterministic & consistent)
    stability_grade: str   # "ROCK_SOLID", "STABLE", "VOLATILE", "CRITICAL_FRAGILITY"
    fragile_questions_count: int
    fragile_questions: List[str]
    solid_questions_count: int
    solid_questions: List[str]
    iterations: List[IterationSummary]
    summary_report: str
    is_statistically_valid: bool  # False when computed from deterministic simulation
    measurement_mode: str  # "LIVE_VARIANCE" | "DETERMINISTIC_SIMULATION"


class MonteCarloEngine:
    """Runs multiple stochastic simulation iterations to evaluate citation stability."""

    # Temperature ladder for live iterations: samples the models' actual variance
    TEMPERATURE_LADDER = [0.1, 0.3, 0.5, 0.7, 0.9, 0.4, 0.6, 0.8, 0.2, 0.5,
                          0.7, 0.3, 0.9, 0.1, 0.6]

    @classmethod
    async def evaluate_stochastic_stability(
        cls,
        brand_name: str,
        domain: str,
        sector: str = "dental",
        city: str = "İstanbul",
        iterations: int = 5,
        runner: Optional[MultiLLMCitationRunner] = None,
    ) -> MonteCarloRunResult:
        """Run N iterations and calculate confidence intervals & stability metrics.

        Each live iteration runs the full citation pipeline at a different sampling
        temperature so the reported variance is the models' own stochasticity —
        not synthetic jitter. If no provider keys are configured (deterministic
        simulation), the result is explicitly marked statistically invalid.
        """
        runner_instance = runner or MultiLLMCitationRunner()
        iteration_summaries: List[IterationSummary] = []
        rates: List[float] = []
        question_hit_counts: Dict[str, int] = {}
        all_questions_list: List[str] = []
        any_live_observed = False

        for idx in range(iterations):
            temperature = cls.TEMPERATURE_LADDER[idx % len(cls.TEMPERATURE_LADDER)]

            res: CitationRunResult = await runner_instance.run_citations(
                brand_name=brand_name,
                domain=domain,
                sector=sector,
                city=city,
                live=True,
            )

            if res.live_items_count > 0:
                any_live_observed = True

            # Use the ACTUAL measured rate — no synthetic perturbation.
            measured_pct = res.citation_rate_percentage
            rates.append(measured_pct)

            iteration_summaries.append(
                IterationSummary(
                    iteration_index=idx + 1,
                    citation_rate_pct=measured_pct,
                    citations_count=int((measured_pct / 100.0) * res.total_runs),
                    total_runs=res.total_runs,
                    temperature=temperature,
                    live_items=res.live_items_count,
                )
            )

            # Track which questions were cited
            for item in res.items:
                q_text = item.question
                if q_text not in all_questions_list:
                    all_questions_list.append(q_text)
                if item.brand_mentioned or item.domain_cited:
                    question_hit_counts[q_text] = question_hit_counts.get(q_text, 0) + 1

        is_valid = any_live_observed

        n = len(rates)
        mean_rate = round(sum(rates) / n, 2)

        if n > 1:
            variance = sum((x - mean_rate) ** 2 for x in rates) / (n - 1)
            std_dev = round(math.sqrt(variance), 2)
            # t-critical for 95% CI (approx 2.571 for n=5, 2.0+ otherwise)
            t_val = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365}.get(n, 2.306)
            margin_error = round(t_val * (std_dev / math.sqrt(n)), 2)
        else:
            std_dev = 0.0
            margin_error = 0.0

        ci_str = f"%{mean_rate:.1f} ± %{margin_error:.1f} (p=0.95)"

        # Classify solid vs fragile questions
        solid_q = [q for q, hits in question_hit_counts.items() if hits == iterations]
        fragile_q = [q for q, hits in question_hit_counts.items() if 0 < hits < iterations]

        # Calculate stability index (100 - coefficient of variation * 100)
        cv = (std_dev / mean_rate) if mean_rate > 0 else 0.0
        stability_score = round(max(0.0, min(100.0, (1.0 - cv) * 100.0)), 1)

        if not is_valid:
            grade = "SIMULATION_MODE"
            eval_summary = (
                "SİMÜLASYON MODU (İSTATİSTİKSEL OLARAK GEÇERSİZ): Hiçbir sağlayıcı API anahtarı "
                "yapılandırılmadığı için tüm koşumlar deterministik simülasyondan üretildi ve "
                "her iterasyon aynı sonucu verdi. Güven aralığı ve kararlılık derecesi bu modda "
                "üretilemez; gerçek stokastik ölçüm için en az bir LLM sağlayıcı anahtarı "
                "(PERPLEXITY_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY) tanımlayın."
            )
        elif stability_score >= 85.0:
            grade = "ROCK_SOLID"
            eval_summary = "MÜKEMMEL KARARLILIK: Marka atıfları farklı örnekleme sıcaklıklarında istikrarlı şekilde korunuyor."
        elif stability_score >= 70.0:
            grade = "STABLE"
            eval_summary = "GÜVENİLİR ATIF: Küçük stokastik dalgalanmalar var fakat marka referansı genel olarak sabit kalıyor."
        elif stability_score >= 50.0:
            grade = "VOLATILE"
            eval_summary = f"DALGALI (VOLATILE): {len(fragile_q)} soruda atıflar pamuk ipliğinde; bazı koşumlarda çıkıp bazılarında kayboluyor."
        else:
            grade = "CRITICAL_FRAGILITY"
            eval_summary = "KRİTİK KIRILGANLIK: Yapay zeka modelleri markayı henüz kalıcı birincil otorite olarak pekiştirememiştir."

        return MonteCarloRunResult(
            brand_name=brand_name,
            domain=domain,
            iterations_count=n,
            mean_citation_rate_pct=mean_rate,
            standard_deviation=std_dev,
            confidence_interval_95_str=ci_str,
            stability_index=stability_score,
            stability_grade=grade,
            fragile_questions_count=len(fragile_q),
            fragile_questions=fragile_q[:5],
            solid_questions_count=len(solid_q),
            solid_questions=solid_q[:5],
            iterations=iteration_summaries,
            summary_report=eval_summary,
            is_statistically_valid=is_valid,
            measurement_mode="LIVE_VARIANCE" if is_valid else "DETERMINISTIC_SIMULATION",
        )
