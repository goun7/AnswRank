"""cli.run_objections_command dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: ObjectionHandler stub — gercek AI/LLM cagrisi YAPILMADI.
"""
import io
import types

import pytest

from answrank import cli as cli_mod


class _Resp:
    CODE = "PRICE"
    CONF = 82
    TEXT = "karsi yanit"
    POINTS = ["a", "b"]

    def __init__(self):
        self.matched_code = _Resp.CODE
        self.confidence = _Resp.CONF
        self.rebuttal_text = _Resp.TEXT
        self.recommended_talking_points = _Resp.POINTS


class _HandlerStub:
    kwargs = None
    raises = None

    @classmethod
    def generate_rebuttal(cls, **kw):
        _HandlerStub.kwargs = kw
        if _HandlerStub.raises:
            raise _HandlerStub.raises
        return _Resp()


@pytest.fixture
def cap(monkeypatch):
    import answrank.crm.objection as ob
    monkeypatch.setattr(ob, "ObjectionHandler", _HandlerStub)
    _HandlerStub.kwargs = None
    _HandlerStub.raises = None
    _Resp.CODE = "PRICE"
    _Resp.CONF = 82
    _Resp.TEXT = "karsi yanit"
    _Resp.POINTS = ["a", "b"]
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    return buf


def _args(text="pahali", company="Co", sector="dental",
          competitor="Rakip"):
    return types.SimpleNamespace(
        text=text, company=company, sector=sector,
        competitor=competitor)


_BOX = '╭╮╰╯│─┃━┏┓┗┛┡┇┈╴┬┴┼'


def _norm(text):
    """Kutu-cizme karakterlerini ve satir kesmelerini duzlestir."""
    for ch in _BOX:
        text = text.replace(ch, ' ')
    return ' '.join(text.split())


def _run(cap):
    cli_mod.run_objections_command(_args())
    return cap.getvalue()


# -- temel ---------------------------------------------------------------------------------

def test_returns_none(cap):
    assert cli_mod.run_objections_command(_args()) is None


def test_outputs_panel(cap):
    assert "AnswRank" in _run(cap)


def test_outputs_itiraz_baslik(cap):
    assert "Müşteri İtiraz" in _run(cap)


def test_outputs_kategori(cap):
    assert "Kategori" in _run(cap)


def test_outputs_guven(cap):
    assert "Güven" in _run(cap)


def test_outputs_karsilik(cap):
    assert "Karşı Yanıt" in _norm(_run(cap))


def test_outputs_talking_points_table(cap):
    assert "Madde" in _run(cap)


# -- panel icerigi ---------------------------------------------------------------------------------

def test_matched_code_shown(cap):
    assert "PRICE" in _run(cap)


def test_confidence_shown(cap):
    assert "(Güven: %82" in _norm(_run(cap))


def test_rebuttal_text_shown(cap):
    assert "karsi yanit" in _norm(_run(cap))


def test_talking_points_shown(cap):
    _Resp.POINTS = ["x", "y"]
    out = _norm(_run(cap))
    assert "• x" in out
    assert "• y" in out


def test_bullet_prefix(cap):
    _Resp.POINTS = ["madde1"]
    assert "•" in _run(cap)


def test_no_points_empty_table(cap):
    _Resp.POINTS = []
    out = _run(cap)
    assert "Madde" in out
    assert "•" not in out


def test_unicode_text_preserved(cap):
    _Resp.TEXT = "Turkce"
    assert "Turkce" in _norm(_run(cap))


# -- argumanlar ---------------------------------------------------------------------------------

def test_text_passed(cap):
    _run(cap)
    assert _HandlerStub.kwargs["text"] == "pahali"


def test_company_passed(cap):
    _run(cap)
    assert _HandlerStub.kwargs["company_name"] == "Co"


def test_sector_passed(cap):
    _run(cap)
    assert _HandlerStub.kwargs["sector"] == "dental"


def test_competitor_passed(cap):
    _run(cap)
    assert _HandlerStub.kwargs["competitor_name"] == "Rakip"


def test_four_kwargs(cap):
    _run(cap)
    assert len(_HandlerStub.kwargs) == 4


def test_missing_arg_attribute(cap):
    with pytest.raises(AttributeError):
        cli_mod.run_objections_command(types.SimpleNamespace(text="x"))


# -- hata ---------------------------------------------------------------------------------

def test_error_propagates(cap):
    _HandlerStub.raises = RuntimeError("LLM erisilemiyor")
    with pytest.raises(RuntimeError):
        _run(cap)


def test_error_no_output(cap):
    _HandlerStub.raises = ValueError("boom")
    with pytest.raises(ValueError):
        _run(cap)
    assert cap.getvalue() == ""


# -- cesitli degerler ---------------------------------------------------------------------------------

def test_low_confidence_shown(cap):
    _Resp.CONF = 5
    assert "(Güven: %5" in _norm(_run(cap))


def test_hundred_confidence(cap):
    _Resp.CONF = 100
    assert "(Güven: %100" in _norm(_run(cap))


def test_many_points(cap):
    _Resp.POINTS = [chr(97+i) for i in range(8)]
    out = _norm(_run(cap))
    assert "• a" in out
    assert "• h" in out


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(cap):
    a = _norm(_run(cap))
    b = _norm(_run(cap))
    assert "PRICE" in a and "PRICE" in b
    assert "(Güven: %82" in a and "(Güven: %82" in b
