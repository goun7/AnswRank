import pytest
from unittest.mock import AsyncMock, patch
from answrank.citations.runner import MultiLLMCitationRunner, MODELS
from answrank.citations.key_manager import HybridKeyManager, LLMProvider
from answrank.config import settings
from answrank.db import Database
from answrank.models import CitationQueryItem, CitationRunResult


def _responses_body(text="Yanıt ve kaynak.", urls=None):
    """Perplexity Agent API /v1/responses formatı (16 Eyl 2026: /chat/completions
    403 'Sonar is now the Agent API' verdi; eski chat-completions mock'ları öldü)."""
    annotations = [{"type": "url_citation",
                    "url_citation": {"title": t, "url": u}}
                   for t, u in (urls or [])]
    return {"output": [
        {"type": "web_search_call", "id": "ws1"},
        {"type": "message", "content": [
            {"type": "output_text", "text": text, "annotations": annotations}]},
    ]}


def _make_runner_with_keys(**providers):
    """Build a runner whose key manager is configured with the given provider keys."""
    km = HybridKeyManager(custom_keys=providers)
    return MultiLLMCitationRunner(key_manager=km)


@pytest.mark.anyio
async def test_live_citations_fallback():
    runner = MultiLLMCitationRunner()
    # Without keys, all 4 provider query methods return None safely
    assert await runner.query_perplexity_live("test query") is None
    assert await runner.query_openai_live("test query") is None
    assert await runner.query_gemini_live("test query") is None
    assert await runner.query_claude_live("test query") is None

    # run_citations with live=True falls back to deterministic engine gracefully
    res = await runner.run_citations(
        brand_name="Yılmaz Diş",
        domain="yilmazdental.com",
        sector="dental",
        city="İstanbul",
        live=True,
    )
    assert res.total_runs == 20 * len(MODELS)
    assert res.citation_rate_percentage >= 0.0
    # All items must be honestly labelled as simulated
    assert res.live_items_count == 0
    assert res.is_fully_live is False
    assert res.live_response_rate_percentage == 0.0
    assert all(item.was_simulated for item in res.items)


@pytest.mark.anyio
async def test_live_perplexity_query_with_mock():
    runner = _make_runner_with_keys(**{LLMProvider.PERPLEXITY: "fake_key_perplexity"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _resp(200, _responses_body(
            "1. [Yılmaz Diş](https://yilmazdental.com): En iyi klinik.",
            [("Yılmaz Diş", "https://yilmazdental.com")]))

        ans = await runner.query_perplexity_live("Kadıköy en iyi implant kliniği")
        assert ans is not None
        assert "Yılmaz Diş" in ans
        assert "https://yilmazdental.com" in ans  # kaynak listesi gövdeye eklendi


@pytest.mark.anyio
async def test_live_gemini_query_with_mock():
    runner = _make_runner_with_keys(**{LLMProvider.GEMINI: "fake_gemini_key"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "candidates": [
                {"content": {"parts": [{"text": "1. [Yılmaz Diş](https://yilmazdental.com): Önerilen klinik."}]}}
            ]
        }
        mock_post.return_value = mock_resp

        ans = await runner.query_gemini_live("İstanbul implant kliniği")
        assert ans is not None
        assert "Yılmaz Diş" in ans


@pytest.mark.anyio
async def test_live_claude_query_with_mock():
    runner = _make_runner_with_keys(**{LLMProvider.ANTHROPIC: "fake_anthropic_key"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "content": [{"type": "text", "text": "1. [Yılmaz Diş](https://yilmazdental.com): Güvenilir klinik."}]
        }
        mock_post.return_value = mock_resp

        ans = await runner.query_claude_live("İstanbul diş kliniği önerisi")
        assert ans is not None
        assert "Yılmaz Diş" in ans


@pytest.mark.anyio
async def test_live_openai_query_with_mock():
    runner = _make_runner_with_keys(**{LLMProvider.OPENAI: "fake_openai_key"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "choices": [{"message": {"content": "1. [Yılmaz Diş](https://yilmazdental.com): En iyi klinik."}}]
        }
        mock_post.return_value = mock_resp

        ans = await runner.query_openai_live("Kadıköy en iyi diş kliniği")
        assert ans is not None
        assert "Yılmaz Diş" in ans


@pytest.mark.anyio
async def test_live_mistral_query_with_mock():
    runner = _make_runner_with_keys(**{LLMProvider.MISTRAL: "fake_mistral_key"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "choices": [{"message": {"content": "1. [Ornek Klinik](https://ornek.example): Bolgenin referansi."}}]
        }
        mock_post.return_value = mock_resp

        ans = await runner.query_mistral_live("Kadikoy en iyi dis klinigi")
        assert ans is not None and "Ornek Klinik" in ans


@pytest.mark.anyio
async def test_live_mistral_without_key_returns_none():
    runner = _make_runner_with_keys()  # no mistral key
    assert await runner.query_mistral_live("soru") is None


@pytest.mark.anyio
async def test_telemetry_tracks_live_and_fallback():
    """execute_query integration: telemetry must reflect live calls vs fallbacks."""
    runner = _make_runner_with_keys(**{LLMProvider.PERPLEXITY: "fake_key_perplexity"})

    # Live path succeeds via mock (Agent API /v1/responses formatı)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _resp(200, _responses_body(
            "cevap", [("Kaynak", "https://ornek.com")]))

        res = await runner.run_citations(
            brand_name="Test",
            domain="test.com",
            sector="dental",
            city="İstanbul",
            live=True,
        )

    # 20 perplexity items should be live, remaining 60 simulated
    assert res.live_items_count == 20
    assert res.live_response_rate_percentage == round(100 * 20 / (20 * len(MODELS)), 1)
    assert res.is_fully_live is False
    perplexity_items = [i for i in res.items if i.model == "Perplexity-Sonar"]
    simulated_items = [i for i in res.items if i.model != "Perplexity-Sonar"]
    assert all(not i.was_simulated for i in perplexity_items)
    assert all(i.was_simulated for i in simulated_items)

    telemetry = runner.get_telemetry()
    assert telemetry["providers"]["PERPLEXITY"]["successful_calls"] == 20
    assert telemetry["providers"]["PERPLEXITY"]["fallback_calls"] == 0
    assert telemetry["total_live_calls"] == 20


@pytest.mark.anyio
async def test_live_mistral_non200_and_malformed_and_crash_return_none():
    runner = _make_runner_with_keys(**{LLMProvider.MISTRAL: "k"})

    bad = AsyncMock(); bad.status_code = 503; bad.json = lambda: {}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=bad)):
        assert await runner.query_mistral_live("q") is None

    empty = AsyncMock(); empty.status_code = 200; empty.json = lambda: {"choices": []}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=empty)):
        assert await runner.query_mistral_live("q") is None

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=ConnectionError("down"))):
        assert await runner.query_mistral_live("q") is None


# ---------------- E10: search-grounding modalitesi ----------------

def _resp(status=200, body=None):
    m = AsyncMock()
    m.status_code = status
    m.json = lambda: body
    m.text = ""
    return m


@pytest.mark.anyio
async def test_e10_openai_grounding_marked_with_real_sources():
    runner = _make_runner_with_keys(**{LLMProvider.OPENAI: "k"})
    body = {"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "En iyi klinik Yılmaz Diş'tir.",
         "annotations": [{"url_citation": {"title": "Yılmaz", "url": "https://yilmazdental.com"}}]}]}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, body)
        ans = await runner.query_openai_live("En iyi implant kliniği")
    assert "Yılmaz Diş" in ans and "https://yilmazdental.com" in ans
    assert runner.grounding_status.get("ChatGPT-4o") == "search-grounded"


@pytest.mark.anyio
async def test_e10_openai_recalls_when_responses_unsupported():
    """Responses API 404/4xx → chat completions geri düşüşü; etiket model-recall."""
    runner = _make_runner_with_keys(**{LLMProvider.OPENAI: "k"})
    chat = {"choices": [{"message": {"content": "Yılmaz Diş iyi bir klinik."}}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        # İlk istek (Responses) 404, ikincisi (chat) 200
        mp.side_effect = [_resp(404, {}), _resp(200, chat)]
        ans = await runner.query_openai_live("En iyi implant kliniği")
    assert "Yılmaz Diş" in ans
    assert runner.grounding_status.get("ChatGPT-4o") == "model-recall"


@pytest.mark.anyio
async def test_e10_gemini_grounding_marked_with_metadata():
    runner = _make_runner_with_keys(**{LLMProvider.GEMINI: "k"})
    body = {"candidates": [{
        "content": {"parts": [{"text": "Yılmaz Diş önerilir."}]},
        "groundingMetadata": {
            "webSearchQueries": ["en iyi implant kliniği"],
            "citations": [{"title": "Yılmaz", "uri": "https://yilmazdental.com"}]}}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, body)
        ans = await runner.query_gemini_live("En iyi implant kliniği")
    assert "Yılmaz Diş" in ans and "https://yilmazdental.com" in ans
    assert runner.grounding_status.get("Gemini-Pro") == "search-grounded"


@pytest.mark.anyio
async def test_e10_gemini_without_grounding_is_recall():
    runner = _make_runner_with_keys(**{LLMProvider.GEMINI: "k"})
    body = {"candidates": [{"content": {"parts": [{"text": "Yılmaz Diş."}]}}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, body)
        ans = await runner.query_gemini_live("klinik")
    assert "Yılmaz Diş" in ans
    assert runner.grounding_status.get("Gemini-Pro") == "model-recall"


@pytest.mark.anyio
async def test_e10_claude_grounding_marked_with_search_result():
    runner = _make_runner_with_keys(**{LLMProvider.ANTHROPIC: "k"})
    body = {"content": [
        {"type": "text", "text": "Yılmaz Diş öneririm.",
         "citations": [{"title": "Yılmaz", "url": "https://yilmazdental.com"}]},
        {"type": "web_search_tool_result", "tool_use_id": "x", "content": []}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, body)
        ans = await runner.query_claude_live("En iyi implant kliniği")
    assert "Yılmaz Diş" in ans and "https://yilmazdental.com" in ans
    assert runner.grounding_status.get("Claude-3.5") == "search-grounded"


@pytest.mark.anyio
async def test_e10_mistral_always_recall_and_labelled():
    runner = _make_runner_with_keys(**{LLMProvider.MISTRAL: "k"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, {"choices": [{"message": {"content": "Yılmaz Diş."}}]})
        ans = await runner.query_mistral_live("klinik")
    assert "Yılmaz Diş" in ans
    assert runner.grounding_status.get("Mistral-Large") == "model-recall"


@pytest.mark.anyio
async def test_e10_no_key_run_labels_all_engines_honestly():
    runner = MultiLLMCitationRunner()
    res = await runner.run_citations(brand_name="Yılmaz Diş", domain="yilmazdental.com",
                                     sector="dental", city="İstanbul", live=True)
    assert set(res.grounding_status.keys()) == set(MODELS)
    assert all(v == "anahtar yok" for v in res.grounding_status.values())


@pytest.mark.anyio
async def test_e10_append_sources_edge_cases():
    """Boş kaynak listesi metni korur; tekrarlanan URL'ler tekilir."""
    from answrank.citations.runner import MultiLLMCitationRunner as R
    assert R._append_sources("abc", []) == "abc"
    out = R._append_sources("abc", [("A", "https://x.ae"), ("B", "https://x.ae")])
    assert out.count("https://x.ae") == 1


@pytest.mark.anyio
async def test_e10_openai_annotation_without_url_skipped():
    runner = _make_runner_with_keys(**{LLMProvider.OPENAI: "k"})
    body = {"output": [
        {"type": "web_search_call", "status": "completed"},  # message degil -> atlanir
        {"type": "message", "content": [
        {"type": "output_text", "text": "Yılmaz Diş.",
         "annotations": [{"other": {}}, {"url_citation": {"url": "https://y.ae"}}]}]}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, body)
        ans = await runner.query_openai_live("q")
    assert "Yılmaz Diş" in ans and "https://y.ae" in ans
    assert runner.grounding_status.get("ChatGPT-4o") == "search-grounded"


@pytest.mark.anyio
async def test_e10_gemini_grounded_text_but_no_metadata_falls_back():
    runner = _make_runner_with_keys(**{LLMProvider.GEMINI: "k"})
    grounded_body = {"candidates": [{"content": {"parts": [{"text": "Yılmaz Diş."}]}}]}
    {"candidates": [{"content": {"parts": [{"text": "Yılmaz Diş."}]}}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.side_effect = [_resp(403, {}), _resp(200, grounded_body)]
        ans = await runner.query_gemini_live("q")
    assert "Yılmaz Diş" in ans
    assert runner.grounding_status.get("Gemini-Pro") == "model-recall"


@pytest.mark.anyio
async def test_e10_claude_text_without_search_result_falls_back():
    runner = _make_runner_with_keys(**{LLMProvider.ANTHROPIC: "k"})
    body = {"content": [{"type": "text", "text": "Claude yanıtı."}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        # grounded istek 404 (web_search desteklenmiyor) -> plain 200'e düşer
        mp.side_effect = [_resp(404, {}), _resp(200, body)]
        ans = await runner.query_claude_live("q")
    assert "Claude yanıtı" in ans
    assert runner.grounding_status.get("Claude-3.5") == "model-recall"


# --- anahtar var ama API reddetti (401/403): 'ölçülemedi' dürüst etiketi ---

@pytest.mark.anyio
async def test_invalid_key_marks_unmeasured_not_recall():
    """Anahtar var ama geçersiz: 'model-recall' DENMEZ — ölçüm olmadığı
    dürüstçe belirtilir. Bu olgu 16 Eyl canlı dumanında bulundu."""
    runner = _make_runner_with_keys(**{LLMProvider.OPENAI: "sk-invalid"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(401, {"error": "invalid_api_key"})
        ans = await runner.query_openai_live("q")
    assert ans is None
    assert runner.grounding_status.get("ChatGPT-4o") == "ölçülemedi"


# --- gateway base URL normalize + timeout yardımcısı (canlı test bulgusu) ---

def test_provider_base_strips_duplicate_v1():
    """Kullanıcı URL'i '/v1' ile bitiyorsa tekrar eklenmez (çift /v1/v1 404)."""
    assert MultiLLMCitationRunner._provider_base("https://api.openai.com", "NONE_SET") \
        == "https://api.openai.com"
    import os
    os.environ["ANSWRANK_TEST_BASE"] = "https://api.atria-asi.ai/v1"
    try:
        assert MultiLLMCitationRunner._provider_base("https://x", "ANSWRANK_TEST_BASE") \
            == "https://api.atria-asi.ai"
    finally:
        del os.environ["ANSWRANK_TEST_BASE"]


def test_provider_base_trailing_slash_normalized():
    import os
    os.environ["ANSWRANK_TEST_BASE"] = "https://gw.example.com/"
    try:
        assert MultiLLMCitationRunner._provider_base("https://x", "ANSWRANK_TEST_BASE") \
            == "https://gw.example.com"
    finally:
        del os.environ["ANSWRANK_TEST_BASE"]


def test_live_timeout_env_default_and_invalid():
    import os
    r = MultiLLMCitationRunner()
    os.environ["ANSWRANK_LLM_TIMEOUT"] = "90"
    try:
        assert r._live_timeout() == 90.0
    finally:
        del os.environ["ANSWRANK_LLM_TIMEOUT"]
    os.environ["ANSWRANK_LLM_TIMEOUT"] = "bozuk"
    try:
        assert r._live_timeout() == 45.0  # bozulursa varsayılana düşer
    finally:
        del os.environ["ANSWRANK_LLM_TIMEOUT"]


# --- Perplexity: etiket SADECE başarılı yanıttan sonra konur (16 Eyl bulgusu) ---

@pytest.mark.anyio
async def test_perplexity_failure_leaves_label_unmeasured():
    """Eskiden 'search-grounded' sorgudan ÖNCE işaretleniyordu; API
    reddedince yanıt None gelmiş ama etiket 'search-grounded' kalmıştı —
    UYDURMA etiketti. Artık ancak başarılı yanıttan sonra konur."""
    runner = _make_runner_with_keys(**{LLMProvider.PERPLEXITY: "pplx-fake"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(429, {"error": "quota"})
        ans = await runner.query_perplexity_live("q")
    assert ans is None
    # başarısız sorgu 'search-grounded' DEMEZ
    status = runner.grounding_status.get("Perplexity-Sonar")
    assert status != "search-grounded", \
        f"reddedilen sorgu '{status}' ile etiketlendi — uydurma etiket"
    assert status == "ölçülemedi"


@pytest.mark.anyio
async def test_perplexity_success_labels_search_grounded():
    runner = _make_runner_with_keys(**{LLMProvider.PERPLEXITY: "pplx-real"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, _responses_body(
            "Yanıt ve kaynak.", [("Kaynak", "https://ornek.com")]))
        ans = await runner.query_perplexity_live("q")
    assert ans is not None and "Yanıt ve kaynak." in ans
    assert "https://ornek.com" in ans
    assert runner.grounding_status.get("Perplexity-Sonar") == "search-grounded"


def test_web_search_call_block_skipped_in_output():
    """Agent API çıktısındaki web_search_call bloğu metne karışmamalı."""
    runner = _make_runner_with_keys(**{LLMProvider.PERPLEXITY: "k"})
    body = {"output": [
        {"type": "web_search_call", "id": "ws1", "status": "completed"},
        {"type": "message", "content": [
            {"type": "output_text", "text": "Temiz yanıt"}]}]}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
        mp.return_value = _resp(200, body)
        ans = runner._run_sync(runner.query_perplexity_live("q")) if hasattr(runner, "_run_sync") else None
    if ans is None:
        import asyncio
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mp:
            mp.return_value = _resp(200, body)
            ans = asyncio.run(runner.query_perplexity_live("q"))
    assert ans is not None and ans.startswith("Temiz yanıt")


# --- E12: DM için ölçümlü görünürlük kanıtı (uydurma yok) ------------------

def test_visibility_for_returns_measured_or_none(tmp_path, monkeypatch):
    """Ölçüm varsa kanıt döner; yoksa None — DM'de uydurulmaz."""
    monkeypatch.setenv("ANSWRANK_DB_PATH", str(tmp_path / "vis.db"))
    from answrank.db import Database
    runner = MultiLLMCitationRunner()
    # 1) boş DB -> None
    assert runner.visibility_for("ornek.com") is None
    # 2) ölçüm kaydı -> kanıt (aynı DB runner'a verilmeli)
    import asyncio
    db = Database()
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="r1", brand_name="X", domain="ornek.com", sector="dental",
        city="İstanbul", total_runs=100, brand_citations_found=12,
        citation_rate_percentage=12.0, is_fully_live=True,
        live_items_count=100, live_response_rate_percentage=100.0,
        grounding_status={"test-model": "model-recall"},
        items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                 model="test-model", was_simulated=False,
                                 brand_mentioned=i < 12) for i in range(100)])))
    out = MultiLLMCitationRunner(db=db).visibility_for("ornek.com")
    assert out is not None
    assert out["total"] == 100 and out["hits"] == 12
    assert out["rate"] == 12.0


def test_visibility_for_does_not_borrow_another_domains_measurement(tmp_path, monkeypatch):
    """Başka domain'in kaydı istenen domain için görünürlük kanıtı değildir."""
    import asyncio
    dbp = str(tmp_path / "domain-visibility.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp)
    monkeypatch.setattr(settings, "db_path", dbp)
    db = Database()
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="other-domain", brand_name="Other", domain="other.example",
        sector="dental", city="Dubai", total_runs=8,
        brand_citations_found=2, citation_rate_percentage=25.0)))
    runner = MultiLLMCitationRunner(db=db)
    assert runner.visibility_for("missing.example") is None


def test_visibility_for_no_db_returns_none():
    """db verilmezse None — uydurma görünürlük yok."""
    assert MultiLLMCitationRunner().visibility_for("x.com") is None


def test_visibility_for_query_error_returns_none(tmp_path, monkeypatch):
    """DB bozuksa None — hata olarak görünürlük uydurulmaz."""
    monkeypatch.setenv("ANSWRANK_DB_PATH", str(tmp_path / "vis2.db"))
    runner = MultiLLMCitationRunner(db=Database())
    # olmayan tabloyu sorgulayarak hatayı tetikle
    orig = runner.db._get_connection
    def _bad():
        raise RuntimeError("db yok")
    runner.db._get_connection = _bad
    try:
        assert runner.visibility_for("x.com") is None
    finally:
        runner.db._get_connection = orig


def test_visibility_cli_no_measurement_branch(monkeypatch, tmp_path):
    """--with-visibility ama ölçüm YOK: uydurma yok mesajı (cli 348)."""
    import sys, io, contextlib
    dbp = str(tmp_path / "nv.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp)
    monkeypatch.setattr(settings, "db_path", dbp)
    # ölçümlü mini-probe var ama citations ölçümü yok
    import asyncio
    from answrank.probe.miniprobe import MiniProbeResult
    from answrank.db import Database
    db = Database()
    asyncio.run(db.save_miniprobe_lead(MiniProbeResult(
        domain="yok.example", verdict="TEMİZ", robots_line="İZİNLİ",
        llms_line="VAR", bots_line="3/3", blocked_bots=[], probed=3,
        measured=True)))
    monkeypatch.setattr(sys, "argv", ["answrank", "crm", "draft",
                                      "--from-lead", "yok.example",
                                      "--with-visibility"])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        from answrank.cli import main
        main()
    assert "Geçerli son AI-görünürlük kanıtı yok" in out.getvalue()
    assert "taslak üretilmedi" in out.getvalue()
    assert "E7 Lead DM" not in out.getvalue()
    assert "görünürlüğünü" not in out.getvalue()


def test_visibility_for_zero_total_returns_none(tmp_path, monkeypatch):
    """total_runs=0 kaydı kanıt sayılmaz (henüz ölçüm yapılmamış)."""
    dbp = str(tmp_path / "z0.db")
    monkeypatch.setenv("ANSWRANK_DB_PATH", dbp)
    monkeypatch.setattr(settings, "db_path", dbp)
    import asyncio
    from answrank.models import CitationRunResult
    db = Database()
    asyncio.run(db.save_citations(CitationRunResult(
        run_id="z0", brand_name="Z", domain="z.example", sector="dental",
        city="İzmir", total_runs=0, brand_citations_found=0,
        citation_rate_percentage=0.0)))
    assert MultiLLMCitationRunner(db=db).visibility_for("z.example") is None
