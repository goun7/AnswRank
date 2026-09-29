"""Tests for sector questions, citation evaluator, and multi-LLM runner."""

from answrank.citations.questions import get_sector_questions, SECTOR_QUESTIONS
from answrank.citations.evaluator import CitationEvaluator
from answrank.citations.runner import MultiLLMCitationRunner, MODELS

def test_sector_questions_count():
    """Verify each sector has exactly 20 curated questions."""
    for sec in ["dental", "accounting", "aesthetic"]:
        q_list = SECTOR_QUESTIONS[sec]
        assert len(q_list) == 20, f"Sector {sec} has {len(q_list)} questions, expected 20."

    interpolated = get_sector_questions("dental", sehir="İzmir", ilce="Alsancak", marka="DentTest", rakip="RakipDent")
    assert len(interpolated) == 20
    assert "İzmir" in interpolated[0]["question"]

def test_citation_evaluator_positive():
    evaluator = CitationEvaluator()
    response = """
    İstanbul bölgesinde diş kliniği arıyorsanız en iyi seçenekler şunlardır:
    1. [Yılmaz Dental](https://yilmazdental.com): Bağdat Caddesi'nde implant ve estetik diş alanında uzman.
    2. [Hospitadent](https://hospitadent.com): Yaygın poliklinik ağına sahip.
    """
    brand_found, domain_cited, rank, comps = evaluator.evaluate(
        raw_response=response,
        brand_name="Yılmaz Dental",
        domain="yilmazdental.com",
        known_competitors=["hospitadent.com", "dentgroup.com"],
    )
    assert brand_found is True
    assert domain_cited is True
    assert rank == 1
    assert "hospitadent.com" in comps

def test_citation_evaluator_negative():
    evaluator = CitationEvaluator()
    response = """
    İstanbul'da mali müşavir arayanlar için en popüler ofisler:
    1. [MüşavirX](https://musavirx.com): Geniş mükellef ağı.
    2. [VergiOfisi](https://vergiofisi.com): E-ticaret vergi danışmanı.
    """
    brand_found, domain_cited, rank, comps = evaluator.evaluate(
        raw_response=response,
        brand_name="Ahmet Mali Müşavirlik",
        domain="ahmetmusavir.com",
        known_competitors=["musavirx.com"],
    )
    assert brand_found is False
    assert domain_cited is False
    assert rank is None
    assert "musavirx.com" in comps

import asyncio

def test_multi_llm_runner_simulation():
    runner = MultiLLMCitationRunner()
    result = asyncio.run(runner.run_citations(
        brand_name="Yılmaz Dental",
        domain="yilmazdental.com",
        sector="dental",
        city="İstanbul",
        competitors=["hospitadent.com"],
        simulate_score_baseline=85,  # High score -> should be cited
    ))
    assert result.total_runs == 20 * len(MODELS)  # full matrix, drift-proof
    assert result.brand_citations_found > 0
    assert result.citation_rate_percentage > 50.0
    assert "hospitadent.com" in result.top_competitors


def test_evaluator_placeholder_url_substring_cannot_cite_brand():
    """16 Eyl user-eyes smoke P0-3: brand "Example" was "cited" %100 because the
    fictional placeholder link https://rakip-a.example contained the substring
    \\bexample\\b. Brand matching is now prose-only; URL targets count solely via
    the domain rule."""
    ev = CitationEvaluator()
    resp = ("1. [Rakip A](https://rakip-a.example): bölgenin lideri.\n"
            "2. [Rakip Örnek A](https://rakip-ornek-a.example): çok önerilir.")
    mentioned, cited, rank, comps = ev.evaluate(resp, "Example", "example.com")
    assert mentioned is False and cited is False and rank is None
    # the genuine citation still fires via prose label + domain link
    m2, c2, r2, _ = ev.evaluate("1. [Example](https://example.com): güvenilir kaynak.", "Example", "example.com")
    assert m2 is True and c2 is True and r2 == 1


def test_live_response_parser_extracts_text_and_citations():
    """Canlı Perplexity yanıtı metin + url_citation kaynaklarını çıkarmalı.
    web_search_call ve message olmayan bloklar atlanmalı (grounding bozulmaz)."""
    from answrank.citations.runner import parse_live_response

    data = {
        "output": [
            {"type": "web_search_call", "query": "diş kliniği İstanbul"},
            {"type": "message", "content": [
                {"type": "output_text", "text": "Yılmaz Dental implant tedavisinde ",
                 "annotations": [
                     {"url_citation": {"url": "https://yilmazdental.com",
                                       "title": "Yılmaz Dental"}},
                 ]},
                {"type": "output_text", "text": "başarılı sonuçlar sunar.",
                 "annotations": []},
            ]},
            {"type": "reasoning", "content": []},
        ]
    }
    text, sources = parse_live_response(data)
    assert "Yılmaz Dental" in text
    assert len(sources) == 1
    assert sources[0][1] == "https://yilmazdental.com"


def test_live_response_parser_handles_malformed_input():
    """Bozuk/eksik yanıt boş sonuç vermeli — istisna fırlatmamalı."""
    from answrank.citations.runner import parse_live_response
    assert parse_live_response({}) == ("", [])
    assert parse_live_response(None) == ("", [])
    assert parse_live_response({"output": "düz-metin"}) == ("", [])
    assert parse_live_response({"output": [{"type": "message",
                                            "content": "içerik-listesi-değil"}]}) == ("", [])
    # annotation url'sizse kaynak eklenmez
    d = {"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "metin", "annotations": [
            {"url_citation": {"title": "başlık"}}]}]}]}
    text, sources = parse_live_response(d)
    assert text == "metin"
    assert sources == []


def test_live_response_parser_survives_type_confusion():
    """İçerik/liste tipi bozuksa TypeError/AttributeError yakalanmalı, boş dönmeli."""
    from answrank.citations.runner import parse_live_response
    # content None → for döngüsü TypeError fırlatır (None yinelenemez)
    d = {"output": [{"type": "message", "content": None}]}
    assert parse_live_response(d) == ("", [])
    # block dict değil → .get AttributeError
    d2 = {"output": ["düz-metin"]}
    assert parse_live_response(d2) == ("", [])
