"""run_rag_command RAG-değerlendirme CLI testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: monkeypatch WebCrawler/RAGEngine/SectorQuestionsBank.
"""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "../../01_unicorn/63-Sester")

import answrank.cli as cli  # noqa: E402
import answrank.audit.crawler as crawler_mod  # noqa: E402
import answrank.audit.rag_engine as rag_mod  # noqa: E402
import answrank.citations.questions as q_mod  # noqa: E402


class _Match:
    def __init__(self, question="Soru 1", similarity_score=0.85,
                 best_chunk_preview="Önizleme metni", weight=1.0,
                 will_be_retrieved_in_top_k=True):
        self.question = question
        self.similarity_score = similarity_score
        self.best_chunk_preview = best_chunk_preview
        self.weight = weight
        self.will_be_retrieved_in_top_k = will_be_retrieved_in_top_k



class _RagResult:
    def __init__(self, rag_retrieval_score=75.0, retrieval_pass_rate_pct=75,
                 total_chunks_extracted=3, stability_score=80.0,
                 remedy_advice="Daha derin içerik ekleyin",
                 matches=None, url="https://example.com"):
        self.rag_retrieval_score = rag_retrieval_score
        self.retrieval_pass_rate_pct = retrieval_pass_rate_pct
        self.total_chunks_extracted = total_chunks_extracted
        self.stability_score = stability_score
        self.remedy_advice = remedy_advice
        self.matches = matches if matches is not None else [_Match()]
        self.url = url



def _args(**over):
    base = dict(url="https://example.com", topk=5, sector="SaaS",
                city="İstanbul")
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def rag(monkeypatch):
    calls = {"fetch": [], "questions": [], "eval": []}
    last_result = _RagResult()

    class _Crawl:
        def __init__(self):
            self.url = None

    class _Crawler:
        async def fetch(self, url, **kw):
            calls["fetch"].append(url)
            return type("C", (),
                        {"html_content": "<html>içerik</html>", "url": url})

    class _Bank:
        @staticmethod
        def get_questions(sector, **kw):
            calls["questions"].append(sector)
            return ["Soru 1", "Soru 2"]

    class _Engine:
        @staticmethod
        def evaluate_content_rag(url, html_content, questions, **kw):
            calls["eval"].append((url, html_content, questions))
            return last_result

    monkeypatch.setattr(crawler_mod, "WebCrawler", _Crawler)
    monkeypatch.setattr(q_mod, "SectorQuestionsBank", _Bank)
    monkeypatch.setattr(rag_mod, "RAGEngine", _Engine)
    return calls, last_result


@pytest.fixture
def caprich(monkeypatch):
    shown = []
    desc = []

    class _Progress:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def add_task(self, description="", **kw):
            desc.append(description)

    monkeypatch.setattr(cli, "Progress", lambda *a, **k: _Progress())
    monkeypatch.setattr(cli, "Panel", lambda *a, **k: shown.append(("panel", a, k)))
    monkeypatch.setattr(cli, "Table", type("T", (), {
        "__init__": lambda self, *a, **k: shown.append(("table", a, k)),
        "add_column": lambda self, *a, **k: None,
        "add_row": lambda self, *a, **k: shown.append(("row", a)),
    }))
    return shown, desc


# -- temel ---------------------------------------------------------------------------

def test_returns_none(rag, caprich):
    assert cli.run_rag_command(_args()) is None


def test_fetch_url_called(rag, caprich):
    cli.run_rag_command(_args(url="https://test.com"))
    assert rag[0]["fetch"][0] == "https://test.com"


def test_questions_for_sector(rag, caprich):
    cli.run_rag_command(_args(sector="E-ticaret"))
    assert rag[0]["questions"][0] == "E-ticaret"


def test_evaluate_called(rag, caprich):
    cli.run_rag_command(_args())
    assert len(rag[0]["eval"]) == 1


def test_progress_description_shown(rag, caprich):
    cli.run_rag_command(_args())
    assert len(caprich[1]) >= 1
    assert "example.com" in caprich[1][0]


# -- Panel çıktısı ---------------------------------------------------------------------------

def test_panel_shown(rag, caprich):
    cli.run_rag_command(_args())
    assert any(s[0] == "panel" for s in caprich[0])


def test_panel_contains_url(rag, caprich):
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "example.com" in str(panel[1])  # res.url


def test_panel_contains_chunk_count(rag, caprich):
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "3" in str(panel[1])  # total_chunks_extracted


def test_panel_contains_acceptance(rag, caprich):
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "75" in str(panel[1])


def test_panel_contains_concepts(rag, caprich):
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "3" in str(panel[1])


def test_panel_contains_remark(rag, caprich):
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "Daha derin içerik" in str(panel[1])  # remedy_advice


# -- tablo ---------------------------------------------------------------------------

def test_table_shown(rag, caprich):
    cli.run_rag_command(_args())
    assert any(s[0] == "table" for s in caprich[0])


def test_table_rows_for_matches(rag, caprich):
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert len(rows) == 1


def test_table_max_8_rows(rag, caprich, monkeypatch):
    """matches[:8] — en fazla 8 satır."""
    rag[1].matches = [_Match(question=f"S{i}") for i in range(15)]
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert len(rows) == 8


def test_table_zero_matches(rag, caprich):
    rag[1].matches = []
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert len(rows) == 0


def test_match_question_in_row(rag, caprich):
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert "Soru 1" in str(rows[0][1])


# -- skor çeşitleri ---------------------------------------------------------------------------

def test_high_score(rag, caprich):
    rag[1].rag_retrieval_score = 92.5
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "92.5" in str(panel[1])


def test_low_score(rag, caprich):
    rag[1].rag_retrieval_score = 12.0
    cli.run_rag_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "12" in str(panel[1])


def test_zero_hits(rag, caprich):
    rag[1].topk_hits = 0
    rag[1].acceptance_rate = 0.0
    cli.run_rag_command(_args())
    assert any(s[0] == "panel" for s in caprich[0])


# -- URL çeşitleri ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["https://a.com", "https://b.org/tr",
                                 "https://sub.example.co.uk/x"])
def test_various_urls(rag, caprich, url):
    cli.run_rag_command(_args(url=url))
    assert rag[0]["fetch"][0] == url


# -- benzerlik renklendirmesi ---------------------------------------------------------------------------

def test_high_similarity_shown(rag, caprich):
    rag[1].matches = [_Match(similarity_score=0.95)]
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert "0.95" in str(rows[0][1])


def test_low_similarity_shown(rag, caprich):
    rag[1].matches = [_Match(similarity_score=0.12)]
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert "0.12" in str(rows[0][1])


def test_in_topk_status(rag, caprich):
    rag[1].matches = [_Match(will_be_retrieved_in_top_k=True)]
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert "TOP-K" in str(rows[0][1])


def test_not_in_topk_status(rag, caprich):
    rag[1].matches = [_Match(will_be_retrieved_in_top_k=False)]
    cli.run_rag_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert "ELEND" in str(rows[0][1])
