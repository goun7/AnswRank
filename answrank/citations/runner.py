"""Multi-LLM Citation Runner across every engine in MODELS (single source).

All 5 providers have real live-query implementations (16 Eyl 2026):
1. OpenAI ChatGPT (chat completions)
2. Perplexity Sonar (search-grounded chat completions)
3. Google Gemini (generativelanguage REST API)
4. Anthropic Claude (messages API)
5. Mistral Le Chat (api.mistral.ai chat completions)

When a provider's API key is missing or the call fails, the runner degrades
DETERMINISTICALLY and labels the item as simulated (`was_simulated=True`),
so downstream consumers never mistake synthetic responses for live citations.
All live traffic is routed through HybridKeyManager.execute_query for unified
telemetry (latency, cost, fallback counts).
"""

import os
import uuid
import logging
from typing import TYPE_CHECKING, List, Dict, Optional

if TYPE_CHECKING:
    from answrank.db import Database

import httpx
from answrank.models import CitationQueryItem, CitationRunResult, utc_now
from answrank.citations.questions import get_sector_questions
from answrank.citations.evaluator import CitationEvaluator
from answrank.citations.key_manager import HybridKeyManager, LLMProvider

logger = logging.getLogger("answrank.runner")

MODELS = [
    "ChatGPT-4o",
    "Perplexity-Sonar",
    "Gemini-Pro",
    "Claude-3.5",
    "Mistral-Large",
]

# Responses-API yanıt bloklarından metin ve url_citation kaynaklarını ayıklar.
# Saf fonksiyon: sağlayıcı çağrısından ayrı test edilebilir, yan etkisi yok.
def parse_live_response(data: dict) -> tuple:
    """Canlı Responses-API yanıtından metin ve (başlık, url) kaynak listesi döndürür.

    web_search_call ve message olmayan bloklar atlanır; output_text olmayan
    içerikler yok sayılır. Bozuk/eksik yapı boş sonuç verir, istisna fırlatmaz."""
    texts: list = []
    sources: list = []
    try:
        for block in (data or {}).get("output", []):
            if not isinstance(block, dict) or block.get("type") != "message":
                continue
            for c in block.get("content", []) or []:
                if not isinstance(c, dict) or c.get("type") != "output_text":
                    continue
                texts.append(c.get("text", ""))
                for a in c.get("annotations", []) or []:
                    uc = (a or {}).get("url_citation") or {}
                    if uc.get("url"):
                        sources.append((uc.get("title") or uc["url"], uc["url"]))
    except (AttributeError, TypeError):
        return "", []
    return "\n".join(t for t in texts if t).strip(), sources

# Map internal model display names to their provider + query method.
MODEL_PROVIDER_MAP = {
    "ChatGPT-4o": LLMProvider.OPENAI,
    "Perplexity-Sonar": LLMProvider.PERPLEXITY,
    "Gemini-Pro": LLMProvider.GEMINI,
    "Claude-3.5": LLMProvider.ANTHROPIC,
    "Mistral-Large": LLMProvider.MISTRAL,
}

DEFAULT_SIM_BASELINE = 10  # deterministic baseline used when simulating


class MultiLLMCitationRunner:
    """Orchestrates QUESTION_COUNT×len(MODELS) runs (20×5=100 at present) with live API bridge and telemetry."""

    # E10: motorların ölçüm modalitesi (ilk başarılı sorgudan sonra yazılır)
    GROUNDING_DISABLED = os.getenv("ANSWRANK_GROUNDING", "1") == "0"

    def __init__(self, key_manager: Optional[HybridKeyManager] = None,
                 db: Optional["Database"] = None):
        self.evaluator = CitationEvaluator()
        self.key_manager = key_manager or HybridKeyManager()
        self.grounding_status: Dict[str, str] = {}
        # veritabanı opsiyonel: yoksa ölçüm okuma (visibility_for) None döner
        self.db = db

    # ------------------------------------------------------------------
    # Live provider query methods (one per provider, all real HTTP)
    # ------------------------------------------------------------------


    def _mark_grounding(self, model: str, status: str) -> None:
        """İlk ölçülen modalite kalır; uydurulmaz, sadece gözlemlenir."""
        self.grounding_status.setdefault(model, status)

    @staticmethod
    def _provider_base(default_url: str, env_var: str) -> str:
        """Gateway base URL'ini normalize eder: kullanici URL ' /v1' ile
        bitiyorsa tekrar ekleme (cift /v1/v1/... 404'su — 16 Eyl canli
        testte atriia-asi gateway'inde bulundu)."""
        raw = os.getenv(env_var, default_url).strip().rstrip("/")
        if raw.lower().endswith("/v1"):
            raw = raw[:-3]
        return raw

    @staticmethod
    def _append_sources(text: str, sources: List[tuple]) -> str:
        if not sources:
            return text
        seen, lines = set(), []
        for title, url in sources:
            if url in seen:
                continue
            seen.add(url)
            lines.append(f"- [{title}]({url})")
        return text + "\n\nKaynaklar (canlı aramadan):\n" + "\n".join(lines)

    async def _grounded_or_recall(self, model: str, grounded, plain) -> Optional[str]:
        """Önce search-grounded çağrı; başarısızsa plain recall. Modalite dürüstçe
        etiketlenir. Her iki yol da ağ hatasında None döner (asla uydurulmaz)."""
        if not MultiLLMCitationRunner.GROUNDING_DISABLED:
            try:
                out = await grounded()
                if out:
                    self._mark_grounding(model, "search-grounded")
                    return out
            except Exception as exc:
                logger.debug("%s grounding denemesi başarısız (recall'e düşülecek): %s", model, exc)
        try:
            out = await plain()
            if out:
                self._mark_grounding(model, "model-recall")
            else:
                # Anahtar var ama API reddetti (401/403 vb.) ya da boş yanıt:
                # ölçüm OLMADI — 'model-recall' denmez, dürüst etiket yazılır.
                self._mark_grounding(model, "ölçülemedi")
            return out
        except Exception as exc:
            logger.debug("%s canlı sorgu başarısız (modalite belirsiz): %s", model, exc)
            self.grounding_status.setdefault(model, "ölçülemedi")
            return None

    def _live_timeout(self) -> float:
        """Canlı sağlayıcı HTTP zaman aşımı (sn) — uzun reasoning'li
        sorgularda 15 sn yetişmiyordu (16 Eyl canlı test)."""
        try:
            return float(os.getenv("ANSWRANK_LLM_TIMEOUT", "45.0"))
        except ValueError:
            return 45.0

    async def query_perplexity_live(self, query: str, timeout: Optional[float] = None) -> Optional[str]:
        """Queries Perplexity Sonar API for real-time web citations."""
        key = self.key_manager.get_key(LLMProvider.PERPLEXITY)
        if not key:
            self._mark_grounding("Perplexity-Sonar", "anahtar yok")
            return None
        # DİKKAT: 'search-grounded' etiketi sorgudan ÖNCE KONMAZ — API reddederse
        # veya ağ hatası olursa None döner; o zaman ölçüm OLMAMIŞTIR ve önceden
        # işaretlemek uydurma etiket olurdu (16 Eyl canlı test: 429 + None).
        # Sonar, Agent API'ye tasindi: /chat/completions 403 verdi (16 Eyl 2026
        # canli test); yeni uc nokta /v1/responses + model 'perplexity/sonar'.
        base = self._provider_base("https://api.perplexity.ai", "ANSWRANK_PERPLEXITY_BASE_URL")
        url = f"{base}/v1/responses"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        model = os.getenv("ANSWRANK_PERPLEXITY_MODEL", "perplexity/sonar")
        payload = {
            "model": model,
            "input": query,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    combined, sources = parse_live_response(resp.json())
                    if combined:
                        # Etiket ANCAK basarili yanita konur (kanitla, varsayim degil)
                        self._mark_grounding("Perplexity-Sonar", "search-grounded")
                        return self._append_sources(combined, sources)
                else:
                    logger.debug("Perplexity API returned %s for query: %s", resp.status_code, query[:60])
        except Exception as exc:
            logger.debug("Perplexity live query failed: %s", exc)
        self.grounding_status.setdefault("Perplexity-Sonar", "ölçülemedi")
        return None

    async def query_openai_live(self, query: str, timeout: Optional[float] = None) -> Optional[str]:
        """OpenAI: önce Responses API + web_search aracı (gerçek arama kaynaklı atıf),
        ardından eski chat completions (model recall) geri düşüşü."""
        key = self.key_manager.get_key(LLMProvider.OPENAI)
        if not key:
            self._mark_grounding("ChatGPT-4o", "anahtar yok")
            return None
        model = os.getenv("ANSWRANK_OPENAI_MODEL", "gpt-4o-mini")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        sys_msg = ("You are an AI search engine answering local queries with "
                   "authoritative domain sources.")

        base = self._provider_base("https://api.openai.com", "ANSWRANK_OPENAI_BASE_URL")

        async def grounded() -> Optional[str]:
            """Canlı sağlayıcı yanıtını value/grounding ile ayrıştırır."""
            url = f"{base}/v1/responses"
            payload = {
                "model": model,
                "instructions": sys_msg,
                "input": [{"role": "user", "content": query}],
                "tools": [{"type": "web_search"}],
            }
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.debug("OpenAI Responses API %s: %s", resp.status_code, resp.text[:120])
                    return None
                data = resp.json()
                combined, sources = parse_live_response(data)
                return self._append_sources(combined, sources) if combined else None

        async def plain() -> Optional[str]:
            """Metni düz metne çevirir."""
            url = f"{base}/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "system", "content": sys_msg},
                             {"role": "user", "content": query}],
                "temperature": 0.2,
            }
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.debug("OpenAI API returned %s for query: %s", resp.status_code, query[:60])
                    return None
                choices = resp.json().get("choices", [])
                return choices[0].get("message", {}).get("content", "") if choices else None

        return await self._grounded_or_recall("ChatGPT-4o", grounded, plain)

    async def query_gemini_live(self, query: str, timeout: Optional[float] = None) -> Optional[str]:
        """Google Gemini: generateContent + google_search grounding aracı (gerçek
        arama kaynaklı atıf); grounding yoksa model recall olarak etiketlenir."""
        key = self.key_manager.get_key(LLMProvider.GEMINI)
        if not key:
            self._mark_grounding("Gemini-Pro", "anahtar yok")
            return None
        model = os.getenv("ANSWRANK_GEMINI_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}

        async def grounded() -> Optional[str]:
            """Canlı sağlayıcı yanıtını value/grounding ile ayrıştırır."""
            payload = {
                "contents": [{"parts": [{"text": query}]}],
                "systemInstruction": {"parts": [{"text":
                    "You are an AI search engine answering local business queries. "
                    "Cite authoritative domains in your answer."}]},
                "generationConfig": {"temperature": 0.2},
                "tools": [{"google_search": {}}],  # E10: gerçek arama kaynaklı atıf
            }
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.debug("Gemini grounding API %s: %s", resp.status_code, resp.text[:120])
                    return None
                data = resp.json()
                cand = (data.get("candidates") or [{}])[0]
                parts = cand.get("content", {}).get("parts", [])
                texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
                combined = "\n".join(t for t in texts if t).strip()
                if not combined:
                    return None
                # grounding kanıtı: webSearchQueries / groundingMetadata yoksa recall'dur
                gm = cand.get("groundingMetadata") or {}
                if not (gm.get("webSearchQueries") or gm.get("citations")):
                    return None
                sources = []
                for c in gm.get("citations") or []:
                    uri = c.get("uri") or c.get("url")
                    if uri:
                        sources.append((c.get("title") or uri, uri))
                return self._append_sources(combined, sources)

        async def plain() -> Optional[str]:
            """Metni düz metne çevirir."""
            payload = {
                "contents": [{"parts": [{"text": query}]}],
                "systemInstruction": {"parts": [{"text":
                    "You are an AI search engine answering local business queries. "
                    "Cite authoritative domains in your answer."}]},
                "generationConfig": {"temperature": 0.2},
            }
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.debug("Gemini API returned %s for query: %s", resp.status_code, query[:60])
                    return None
                cand = (resp.json().get("candidates") or [{}])[0]
                parts = cand.get("content", {}).get("parts", [])
                texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
                combined = "\n".join(t for t in texts if t)
                return combined if combined.strip() else None

        return await self._grounded_or_recall("Gemini-Pro", grounded, plain)

    async def query_claude_live(self, query: str, timeout: Optional[float] = None) -> Optional[str]:
        """Anthropic Claude: messages API + web_search sunucu aracı (gerçek arama
        kaynaklı atıf); araç desteklenmezse model recall olarak etiketlenir."""
        key = self.key_manager.get_key(LLMProvider.ANTHROPIC)
        if not key:
            self._mark_grounding("Claude-3.5", "anahtar yok")
            return None
        model = os.getenv("ANSWRANK_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        base = self._provider_base("https://api.anthropic.com", "ANSWRANK_ANTHROPIC_BASE_URL")
        url = f"{base}/v1/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        sys_msg = ("You are an AI search engine answering local business queries. "
                   "Cite authoritative domains in your answer.")

        async def grounded() -> Optional[str]:
            """Canlı sağlayıcı yanıtını value/grounding ile ayrıştırır."""
            payload = {
                "model": model, "max_tokens": 1024, "system": sys_msg,
                "messages": [{"role": "user", "content": query}],
                # E10: Anthropic sunucu taraflı web_search aracı
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            }
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.debug("Claude web_search API %s: %s", resp.status_code, resp.text[:120])
                    return None
                data = resp.json()
                blocks = data.get("content", [])
                texts, sources = [], []
                saw_search = False
                for b in blocks:
                    if isinstance(b, dict) and b.get("type") == "text":
                        texts.append(b.get("text", ""))
                        for c in b.get("citations") or []:
                            uri = c.get("url")
                            if uri:
                                sources.append((c.get("title") or uri, uri))
                    elif isinstance(b, dict) and b.get("type") == "web_search_tool_result":
                        saw_search = True
                combined = "\n".join(t for t in texts if t).strip()
                if not combined or not saw_search:
                    return None
                return self._append_sources(combined, sources)

        async def plain() -> Optional[str]:
            """Metni düz metne çevirir."""
            payload = {
                "model": model, "max_tokens": 1024, "system": sys_msg,
                "messages": [{"role": "user", "content": query}],
            }
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.debug("Anthropic API returned %s for query: %s", resp.status_code, query[:60])
                    return None
                blocks = resp.json().get("content", [])
                texts = [b.get("text", "") for b in blocks
                         if isinstance(b, dict) and b.get("type") == "text"]
                combined = "\n".join(t for t in texts if t)
                return combined if combined.strip() else None

        return await self._grounded_or_recall("Claude-3.5", grounded, plain)

    async def query_mistral_live(self, query: str, timeout: Optional[float] = None) -> Optional[str]:
        """Queries Mistral chat completions API (OpenAI-compatible schema)."""
        key = self.key_manager.get_key(LLMProvider.MISTRAL)
        if not key:
            self._mark_grounding("Mistral-Large", "anahtar yok")
            return None
        # Mistral'in grounding aracı yoktur — ölçüm model recall'dur (E10 dürüst etiket)
        self._mark_grounding("Mistral-Large", "model-recall")
        base = self._provider_base("https://api.mistral.ai", "ANSWRANK_MISTRAL_BASE_URL")
        url = f"{base}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": os.getenv("ANSWRANK_MISTRAL_MODEL", "mistral-large-latest"),
            "messages": [
                {"role": "system", "content": "You are an AI search engine answering local queries with authoritative domain sources."},
                {"role": "user", "content": query},
            ],
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout or self._live_timeout(), verify=True) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                else:
                    logger.debug("Mistral API returned %s for query: %s", resp.status_code, query[:60])
        except Exception as exc:
            logger.debug("Mistral live query failed: %s", exc)
        return None

    PROVIDER_QUERY_METHODS = {
        LLMProvider.OPENAI: query_openai_live,
        LLMProvider.PERPLEXITY: query_perplexity_live,
        LLMProvider.GEMINI: query_gemini_live,
        LLMProvider.ANTHROPIC: query_claude_live,
        LLMProvider.MISTRAL: query_mistral_live,
    }

    async def _query_provider(self, model_name: str, query: str) -> Optional[str]:
        """Routes a single query to its provider's live method through the telemetry manager."""
        provider = MODEL_PROVIDER_MAP.get(model_name)
        if provider is None:
            return None

        method = self.PROVIDER_QUERY_METHODS[provider]

        async def _live():
            # Bind the bound method correctly: method is an unbound function at class level,
            # so call it with self explicitly to support both class and instance access.
            return await method(self, query)

        async def _fallback():
            return None  # caller handles simulation when None is returned

        return await self.key_manager.execute_query(
            provider=provider,
            live_callable=_live,
            fallback_callable=_fallback,
        )

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def _simulate_response(
        self,
        brand_name: str,
        domain: str,
        city: str,
        primary_competitor: str,
        secondary_competitor: Optional[str],
        q_id: int,
        simulate_score_baseline: Optional[int],
        lang: str = "tr",
    ) -> str:
        """Deterministic synthetic response generator (clearly labelled downstream as simulated).

        Yalnızca çağıranın verdiği rakip listesini kullanır; kurgusal sabit
        rakip metne enjekte edilmez (ölçüm yanıtında yapay-zeka izi bırakmaz)."""
        sim_score = simulate_score_baseline if simulate_score_baseline is not None else DEFAULT_SIM_BASELINE
        is_cited_sim = (sim_score >= 70) or (q_id in (7, 8) and sim_score >= 30)

        if is_cited_sim:
            return (
                f"1. [{brand_name}](https://{domain}): {city} bölgesinde uzman hekimleri ve şeffaf fiyatlarıyla öne çıkmaktadır.\n"
                f"2. [{primary_competitor}](https://{primary_competitor}): Diğer popüler alternatif."
            )
        second = secondary_competitor or primary_competitor
        return (
            f"1. [{primary_competitor}](https://{primary_competitor}): {city} bölgesinde en çok tercih edilen referans merkezdir.\n"
            f"2. [{second}](https://{second}): {city} bölgesinde alternatif bir referans merkezdir."
        )

    def visibility_for(self, domain: str) -> Optional[dict]:
        """E12: bir domain için ÖLÇÜLMÜŞ AI-görünürlük sonucu varsa döner;
        ölçüm yoksa None — DM'de uydurulmaz. En son citations kaydından okur."""
        if self.db is None:
            return None
        try:
            return self.db.get_dm_visibility(domain)
        except Exception:
            return None

    async def run_citations(
        self,
        brand_name: str,
        domain: str,
        sector: str = "dental",
        city: str = "İstanbul",
        competitors: Optional[List[str]] = None,
        simulate_score_baseline: Optional[int] = None,
        live: bool = True,
        lang: str = "tr",
    ) -> CitationRunResult:
        """Runs the sector question bank across every engine in MODELS.

        `live=True` (default) attempts real API queries for all providers when keys
        are configured; any provider without a key or failing network call falls back
        to the deterministic simulation and the item is marked `was_simulated=True`.
        """
        run_id = uuid.uuid4().hex[:10]
        # E10: her run kendi modalite haritasını taşır (UI/rapor dürüst sunar)
        self.grounding_status = {}
        # Rakip listesi yalnızca çağırandan gelir; ürün içine gömülü kurgusal
        # rakip yoktur (varsayılan listeyi bile çağıran sağlamalıdır).
        comp_list = list(competitors or [])
        primary_competitor = comp_list[0] if comp_list else (
            "Competitor Business" if lang == "en" else "Rakip İşletme")
        secondary_competitor = comp_list[1] if len(comp_list) > 1 else None

        questions = get_sector_questions(
            sector=sector,
            sehir=city,
            marka=brand_name,
            rakip=primary_competitor,
            lang=lang,
        )

        items: List[CitationQueryItem] = []
        brand_citations_count = 0
        live_items_count = 0
        competitor_stats: Dict[str, int] = {}

        # QUESTION_COUNT x len(MODELS) = 20 x 5 = 100 total items
        for q in questions:
            q_id = int(q["id"])
            q_text = q["question"]

            for model_name in MODELS:
                raw_response_text: Optional[str] = None
                was_simulated = True

                if live:
                    raw_response_text = await self._query_provider(model_name, q_text)

                if raw_response_text:
                    was_simulated = False
                    live_items_count += 1
                else:
                    # Deterministic simulation fallback
                    raw_response_text = self._simulate_response(
                        brand_name=brand_name,
                        domain=domain,
                        city=city,
                        primary_competitor=primary_competitor,
                        secondary_competitor=secondary_competitor,
                        q_id=q_id,
                        simulate_score_baseline=simulate_score_baseline,
                        lang=lang,
                    )

                brand_mentioned, domain_cited, rank, comps_found = self.evaluator.evaluate(
                    raw_response=raw_response_text,
                    brand_name=brand_name,
                    domain=domain,
                    known_competitors=comp_list,
                )

                if brand_mentioned or domain_cited:
                    brand_citations_count += 1

                for c in comps_found:
                    competitor_stats[c] = competitor_stats.get(c, 0) + 1

                items.append(
                    CitationQueryItem(
                        question_id=q_id,
                        question=q_text,
                        model=model_name,
                        brand_mentioned=brand_mentioned,
                        domain_cited=domain_cited,
                        cited_rank=rank,
                        competitors_cited=comps_found,
                        raw_snippet=raw_response_text[:180],
                        was_simulated=was_simulated,
                    )
                )

        citation_rate = round((brand_citations_count / len(items)) * 100, 1) if items else 0.0
        live_rate = round((live_items_count / len(items)) * 100, 1) if items else 0.0

        # E10: ölçülmemiş motorlar 'anahtar yok' olarak etiketlenir — boş kalmasın
        for _m in MODELS:
            self.grounding_status.setdefault(_m, "anahtar yok")  # denenenmedi

        return CitationRunResult(
            run_id=run_id,
            brand_name=brand_name,
            domain=domain,
            sector=sector,
            city=city,
            lang=lang,
            timestamp=utc_now(),
            total_runs=len(items),
            brand_citations_found=brand_citations_count,
            citation_rate_percentage=citation_rate,
            live_items_count=live_items_count,
            live_response_rate_percentage=live_rate,
            is_fully_live=live_items_count == len(items),
            items=items,
            top_competitors=competitor_stats,
            grounding_status=dict(self.grounding_status),
        )

    def get_telemetry(self) -> Dict[str, object]:
        """Returns provider performance and token cost telemetry."""
        return self.key_manager.get_telemetry_report()
