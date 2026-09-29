"""Regression tests for the citation runner audit findings.

Covers:
- P0.2: `Any` import fix (typing.get_type_hints must not raise NameError)
- P0.2: All 4 providers have real live query methods routed through key manager
- Honest simulation labelling (was_simulated flags)
"""

import typing
import pytest
from unittest.mock import AsyncMock, patch

import answrank.citations.runner as runner_mod
from answrank.citations.runner import MultiLLMCitationRunner, MODELS, MODEL_PROVIDER_MAP
from answrank.citations.key_manager import HybridKeyManager, LLMProvider


def test_runner_get_telemetry_type_hints_resolve():
    """REGRESSION (denetim bulgusu A.2): get_telemetry used `Dict[str, Any]` without
    importing Any. typing.get_type_hints() (used by pydantic/FastAPI introspection)
    must resolve without NameError."""
    hints = typing.get_type_hints(MultiLLMCitationRunner.get_telemetry)
    assert "return" in hints


def test_all_four_providers_have_live_methods():
    """Every model in MODELS must map to a provider with a real live query method."""
    for model_name in MODELS:
        provider = MODEL_PROVIDER_MAP[model_name]
        method = MultiLLMCitationRunner.PROVIDER_QUERY_METHODS[provider]
        assert method is not None, f"{model_name} has no live query method"


def test_provider_query_methods_cover_gemini_and_claude():
    """The audit found Gemini and Claude had NO live query code. Both must now
    have dedicated live methods."""
    assert hasattr(MultiLLMCitationRunner, "query_gemini_live")
    assert hasattr(MultiLLMCitationRunner, "query_claude_live")
    assert LLMProvider.GEMINI in MultiLLMCitationRunner.PROVIDER_QUERY_METHODS
    assert LLMProvider.ANTHROPIC in MultiLLMCitationRunner.PROVIDER_QUERY_METHODS


def test_no_any_usage_without_import():
    """Module source must import Any from typing if it uses Any in annotations."""
    import inspect
    src = inspect.getsource(runner_mod)
    if ": Any" in src or "[Any]" in src or "Any]" in src:
        assert "from typing import" in src
        # Extract the typing import line and confirm Any is present
        for line in src.splitlines():
            if line.startswith("from typing import"):
                assert "Any" in line, "Any is used but not imported from typing"


@pytest.mark.anyio
async def test_run_citations_marks_simulation_honestly():
    """Without any provider keys, every item must be flagged was_simulated=True
    and the run result must report live_items_count=0."""
    runner = MultiLLMCitationRunner()  # no keys
    res = await runner.run_citations(
        brand_name="Test",
        domain="test.com",
        sector="dental",
        live=True,
    )
    assert res.total_runs == 20 * len(MODELS)
    assert res.live_items_count == 0
    assert res.live_response_rate_percentage == 0.0
    assert res.is_fully_live is False
    assert all(item.was_simulated for item in res.items)


@pytest.mark.anyio
async def test_key_manager_execute_query_integration():
    """Live calls must be routed through key_manager.execute_query so telemetry
    (latency, cost, fallback counts) reflects reality."""
    km = HybridKeyManager(custom_keys={LLMProvider.OPENAI: "fake_key"})
    runner = MultiLLMCitationRunner(key_manager=km)

    telemetry_before = runner.get_telemetry()["providers"]["OPENAI"]["total_calls"]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"choices": [{"message": {"content": "1. [Test](https://test.com)"}}]}
        mock_post.return_value = mock_resp

        await runner.run_citations(brand_name="Test", domain="test.com", sector="dental", live=True)

    telemetry_after = runner.get_telemetry()["providers"]["OPENAI"]
    assert telemetry_after["total_calls"] == telemetry_before + 20
    assert telemetry_after["successful_calls"] == 20
    assert telemetry_after["estimated_cost_usd"] > 0.0


@pytest.mark.anyio
async def test_simulation_never_invents_fictional_competitor():
    """Çağıran gerçek rakip listesi verse bile simülasyon metnine kurgusal
    'Rakip Örnek A / competitor-sample-a' enjekte edilmemeli — ölçüm
    yanıtında kalmış yapay-zeka izidir."""
    runner = MultiLLMCitationRunner()  # no keys -> tam simülasyon
    res = await runner.run_citations(
        brand_name="Gerçek Klinik", domain="gercek-klinik.example",
        sector="dental", live=True, lang="tr",
        competitors=["rakip-gercek-1.example", "rakip-gercek-2.example"])
    texts = " ".join(i.raw_snippet or "" for i in res.items)
    assert "Rakip Örnek A" not in texts, "kurgusal rakip simülasyon metnine enjekte edildi"
    assert "rakip-ornek-a.example" not in texts
    assert "competitor-sample-a" not in texts
    # çağıranın verdiği gerçek rakip listesi kullanılmış olmalı
    assert "rakip-gercek-1.example" in texts
