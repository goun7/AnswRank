"""cli.run_ground_command dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: WebCrawler + EntityGroundingEngine stub — gercek ag YAPILMADI.
"""
import io
import types

import pytest

from answrank import cli as cli_mod


class _Tier:
    value = "strong"


class _Result:
    BRAND = "TestBrand"
    SCORE = 75.0
    QID = "Q123456"
    WIKI_DESC = "Turkce aciklama"
    HAS_MAPS = True
    HAS_LINKEDIN = True
    ROADMAP = ["wiki-ekle", "maps-ekle"]

    def __init__(self):
        self.brand_name = _Result.BRAND
        self.grounding_score = _Result.SCORE
        self.tier = _Tier()
        self.wikidata_qid = _Result.QID
        self.wikidata_description = _Result.WIKI_DESC
        self.has_google_maps_cid = _Result.HAS_MAPS
        self.has_linkedin_entity = _Result.HAS_LINKEDIN
        self.action_roadmap = _Result.ROADMAP


class _CrawlDoc:
    def __init__(self, html):
        self.html_content = html


class _CrawlerStub:
    fetched = None

    async def fetch(self, domain, **kw):
        _CrawlerStub.fetched = domain
        return _CrawlDoc("<html></html>")


class _EngineStub:
    kwargs = None
    raises = None

    @classmethod
    async def evaluate_grounding(cls, *args, **kw):
        _EngineStub.args = args
        _EngineStub.kwargs = kw
        if _EngineStub.raises:
            raise _EngineStub.raises
        return _Result()


@pytest.fixture
def cap(monkeypatch):
    import answrank.audit.crawler as cw
    import answrank.audit.entity_grounding as eg
    monkeypatch.setattr(cw, "WebCrawler", _CrawlerStub)
    monkeypatch.setattr(eg, "EntityGroundingEngine", _EngineStub)
    _EngineStub.args = ()
    _EngineStub.kwargs = {}
    _EngineStub.raises = None
    _CrawlerStub.fetched = None
    _Result.BRAND = "TestBrand"
    _Result.SCORE = 75.0
    _Result.QID = "Q123456"
    _Result.WIKI_DESC = "Turkce aciklama"
    _Result.HAS_MAPS = True
    _Result.HAS_LINKEDIN = True
    _Result.ROADMAP = ["wiki-ekle", "maps-ekle"]
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    return buf


_BOX = "╭╮╰╯│─┃━┏┓┗┛┡┇┈┌┐└┘"


def _norm(text):
    for ch in _BOX:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _args(brand="TestBrand", domain="test.example"):
    return types.SimpleNamespace(brand=brand, domain=domain)


def _run(cap):
    cli_mod.run_ground_command(_args())
    return cap.getvalue()


# -- temel ---------------------------------------------------------------------------------

def test_returns_none(cap):
    assert cli_mod.run_ground_command(_args()) is None


def test_outputs_panel_title(cap):
    assert "AnswRank" in _norm(_run(cap))


def test_outputs_brand(cap):
    assert "TestBrand" in _norm(_run(cap))


def test_outputs_wikidata_label(cap):
    assert "Wikidata" in _norm(_run(cap))


def test_outputs_maps_label(cap):
    assert "Google Maps CID" in _norm(_run(cap))


def test_outputs_linkedin_label(cap):
    assert "LinkedIn" in _norm(_run(cap))


def test_outputs_roadmap_table(cap):
    """show_header=False -> baslik gizli; tablo title kullanir."""
    assert "Yol Haritası" in _norm(_run(cap))


# -- degerler ---------------------------------------------------------------------------------

def test_score_shown(cap):
    assert "75" in _norm(_run(cap))


def test_wiki_desc_shown(cap):
    assert "Turkce aciklama" in _norm(_run(cap))


def test_qid_shown(cap):
    assert "Q123456" in _norm(_run(cap))


def test_roadmap_items_shown(cap):
    _Result.ROADMAP = ["a", "b"]
    out = _norm(_run(cap))
    assert "• a" in out
    assert "• b" in out


def test_bullet_used(cap):
    _Result.ROADMAP = ["z"]
    assert "•" in _run(cap)


def test_empty_roadmap(cap):
    _Result.ROADMAP = []
    out = _run(cap)
    assert "Yol Haritası" in _norm(out)
    assert "•" not in out


def test_many_roadmap_items(cap):
    _Result.ROADMAP = [chr(97 + i) for i in range(10)]
    out = _norm(_run(cap))
    assert "• a" in out
    assert "• j" in out


def test_no_maps_shown(cap):
    _Result.HAS_MAPS = False
    out = _norm(_run(cap))
    assert "VAR" not in out.split("Google Maps")[1][:12]


def test_linkedin_absent(cap):
    _Result.HAS_LINKEDIN = False
    out = _norm(_run(cap))
    assert "YOK" in out


# -- cagri argumanlari ---------------------------------------------------------------------------------

def test_crawler_domain_passed(cap):
    _run(cap)
    assert _CrawlerStub.fetched == "test.example"


def test_engine_brand_passed(cap):
    _run(cap)
    assert _EngineStub.args[0] == "TestBrand"


def test_engine_domain_passed(cap):
    _run(cap)
    assert _EngineStub.args[1] == "test.example"


def test_engine_html_passed(cap):
    _run(cap)
    assert _EngineStub.kwargs["html_content"] == "<html></html>"
    assert isinstance(_CrawlerStub.fetched, str)


def test_engine_args_count(cap):
    _run(cap)
    assert len(_EngineStub.args) == 2
    assert len(_EngineStub.kwargs) == 1


def test_missing_arg_raises(cap):
    with pytest.raises(AttributeError):
        cli_mod.run_ground_command(
            types.SimpleNamespace(brand="X"))


# -- hata ---------------------------------------------------------------------------------

def test_crawler_error_propagates(cap, monkeypatch):
    import answrank.audit.crawler as cw

    class _Bad:
        async def fetch(self, domain, **kw):
            raise RuntimeError("ag hatasi")
    monkeypatch.setattr(cw, "WebCrawler", _Bad)
    with pytest.raises(RuntimeError):
        _run(cap)


def test_engine_error_propagates(cap):
    _EngineStub.raises = ValueError("wiki erisilemiyor")
    with pytest.raises(ValueError):
        _run(cap)


def test_engine_error_no_output(cap):
    _EngineStub.raises = ValueError("boom")
    with pytest.raises(ValueError):
        _run(cap)
    assert cap.getvalue() == ""


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(cap):
    a = _norm(_run(cap))
    b = _norm(_run(cap))
    assert "TestBrand" in a and "TestBrand" in b
    assert "75" in a and "75" in b
