import pytest
from unittest.mock import AsyncMock
from answrank.citations.key_manager import HybridKeyManager, LLMProvider

def test_key_manager_detection_and_fallback():
    # Initialize with mock Perplexity key only
    mgr = HybridKeyManager(custom_keys={LLMProvider.PERPLEXITY: "pplx-test-api-key-123456"})
    assert mgr.is_provider_available(LLMProvider.PERPLEXITY) is True
    assert mgr.is_provider_available(LLMProvider.OPENAI) is False
    assert LLMProvider.PERPLEXITY in mgr.get_active_providers()

@pytest.mark.anyio
async def test_key_manager_execution_and_fallback():
    mgr = HybridKeyManager(custom_keys={LLMProvider.PERPLEXITY: "pplx-valid-key-xyz"})

    live_call = AsyncMock(return_value="Live Perplexity answer with citations")
    fallback_call = AsyncMock(return_value="Simulated fallback answer")

    # Call with active provider
    res_live = await mgr.execute_query(LLMProvider.PERPLEXITY, live_call, fallback_call)
    assert res_live == "Live Perplexity answer with citations"
    assert live_call.called

    # Call with unconfigured provider (e.g. GEMINI) -> should trigger fallback
    res_fb = await mgr.execute_query(LLMProvider.GEMINI, live_call, fallback_call)
    assert res_fb == "Simulated fallback answer"
    assert fallback_call.called

    # Check telemetry report
    tel = mgr.get_telemetry_report()
    assert tel["is_live_ready"] is True
    assert "PERPLEXITY" in tel["configured_providers"]
    assert tel["total_live_calls"] == 1
    assert tel["total_fallbacks"] == 1
