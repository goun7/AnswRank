"""Hybrid LLM Key & Telemetry Manager for AnswRank.

Manages API keys for external search-augmented LLMs:
1. Perplexity Sonar
2. OpenAI Search / GPT-4o
3. Google Gemini
4. Anthropic Claude
5. SerpAPI
Monitors latencies, token consumption, and executes automatic zero-downtime synthetic fallback.
"""

import os
import time
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from pydantic import BaseModel


class LLMProvider(str, Enum):
    PERPLEXITY = "PERPLEXITY"
    OPENAI = "OPENAI"
    GEMINI = "GEMINI"
    ANTHROPIC = "ANTHROPIC"
    MISTRAL = "MISTRAL"
    SERPAPI = "SERPAPI"


class ProviderTelemetry(BaseModel):
    """Real-time provider performance and cost telemetry."""
    provider: LLMProvider
    has_api_key: bool
    is_live_enabled: bool
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    fallback_calls: int = 0
    avg_latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0


class HybridKeyManager:
    """Orchestrates API key validation, rate-limiting, and graceful synthetic degradation."""

    ENV_KEY_MAP = {
        LLMProvider.PERPLEXITY: "PERPLEXITY_API_KEY",
        LLMProvider.OPENAI: "OPENAI_API_KEY",
        LLMProvider.GEMINI: "GEMINI_API_KEY",
        LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        LLMProvider.MISTRAL: "MISTRAL_API_KEY",
        LLMProvider.SERPAPI: "SERPAPI_API_KEY",
    }

    # Estimated cost per 1K query tokens
    COST_PER_QUERY = {
        LLMProvider.PERPLEXITY: 0.005,
        LLMProvider.OPENAI: 0.003,
        LLMProvider.GEMINI: 0.002,
        LLMProvider.ANTHROPIC: 0.004,
        LLMProvider.MISTRAL: 0.004,
        LLMProvider.SERPAPI: 0.010,
    }

    def __init__(self, custom_keys: Optional[Dict[LLMProvider, str]] = None):
        self._keys: Dict[LLMProvider, Optional[str]] = {}
        self._telemetry: Dict[LLMProvider, ProviderTelemetry] = {}

        for provider, env_var in self.ENV_KEY_MAP.items():
            key = (custom_keys.get(provider) if custom_keys else None) or os.getenv(env_var)
            self._keys[provider] = key
            has_key = bool(key and len(key.strip()) > 5)
            self._telemetry[provider] = ProviderTelemetry(
                provider=provider,
                has_api_key=has_key,
                is_live_enabled=has_key,
            )

    def get_key(self, provider: LLMProvider) -> Optional[str]:
        """Returns API key if configured."""
        return self._keys.get(provider)

    def is_provider_available(self, provider: LLMProvider) -> bool:
        """Returns True if provider has a valid key configured."""
        return self._telemetry[provider].has_api_key

    def get_active_providers(self) -> List[LLMProvider]:
        """Lists all providers with active API keys."""
        return [p for p, tel in self._telemetry.items() if tel.has_api_key]

    async def execute_query(
        self,
        provider: LLMProvider,
        live_callable: Callable[[], Any],
        fallback_callable: Callable[[], Any],
    ) -> Any:
        """Executes live API call if key exists; gracefully falls back to simulation on error or missing key."""
        tel = self._telemetry[provider]
        tel.total_calls += 1

        if not tel.has_api_key or not tel.is_live_enabled:
            tel.fallback_calls += 1
            return await fallback_callable()

        start = time.time()
        try:
            result = await live_callable()
            elapsed_ms = (time.time() - start) * 1000
            if result:
                tel.successful_calls += 1
                tel.avg_latency_ms = round(
                    (tel.avg_latency_ms * (tel.successful_calls - 1) + elapsed_ms) / tel.successful_calls, 1
                )
                tel.estimated_cost_usd += self.COST_PER_QUERY.get(provider, 0.003)
                return result
            else:
                # Live call returned empty/None -> trigger fallback
                tel.fallback_calls += 1
                return await fallback_callable()
        except Exception:
            tel.failed_calls += 1
            tel.fallback_calls += 1
            return await fallback_callable()

    def get_telemetry_report(self) -> Dict[str, Any]:
        """Returns full telemetry summary across all providers."""
        total_live_calls = sum(t.successful_calls for t in self._telemetry.values())
        total_fallbacks = sum(t.fallback_calls for t in self._telemetry.values())
        total_cost = sum(t.estimated_cost_usd for t in self._telemetry.values())

        return {
            "configured_providers": [p.value for p in self.get_active_providers()],
            "is_live_ready": len(self.get_active_providers()) > 0,
            "total_live_calls": total_live_calls,
            "total_fallbacks": total_fallbacks,
            "total_estimated_cost_usd": round(total_cost, 4),
            "providers": {p.value: t.model_dump() for p, t in self._telemetry.items()},
        }
