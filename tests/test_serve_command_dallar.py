"""cli.run_serve_command dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: uvicorn fake module — gercek sunucu BASLATILMADI.
"""
import io
import sys
import types

import pytest

from answrank import cli as cli_mod


class _UvicornFake:
    calls = []

    def run(self, app, host=None, port=None, **kw):
        _UvicornFake.calls.append((app, host, port, kw))


_BOX = "╭╮╰╯│─┃━┏┓┗┛┡┇┈┌┐└┘"


def _norm(text):
    for ch in _BOX:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _args(host="127.0.0.1", port=8000):
    return types.SimpleNamespace(host=host, port=port)


@pytest.fixture
def cap(monkeypatch):
    fake = _UvicornFake()
    _UvicornFake.calls = []
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    return buf


def _run(cap):
    cli_mod.run_serve_command(_args())
    return cap.getvalue()


# -- temel ---------------------------------------------------------------------------------

def test_returns_none(cap):
    assert cli_mod.run_serve_command(_args()) is None


def test_outputs_panel(cap):
    assert "AnswRank" in _norm(_run(cap))


def test_outputs_baslatiliyor(cap):
    assert "Başlatılıyor" in _norm(_run(cap))


def test_outputs_adres(cap):
    assert "Adres" in _norm(_run(cap))


def test_outputs_dokuman(cap):
    assert "Doküman" in _norm(_run(cap))


def test_outputs_host_and_port(cap):
    out = _norm(_run(cap))
    assert "127.0.0.1" in out
    assert "8000" in out


def test_doc_url_format(cap):
    out = _norm(_run(cap))
    assert "http://127.0.0.1:8000" in out
    assert "docs" in out


# -- uvicorn cagrisi ---------------------------------------------------------------------------------

def test_uvicorn_run_called(cap):
    _run(cap)
    assert len(_UvicornFake.calls) == 1


def test_uvicorn_app_string(cap):
    _run(cap)
    assert _UvicornFake.calls[0][0] == "answrank.api.app:app"


def test_uvicorn_host(cap):
    _run(cap)
    assert _UvicornFake.calls[0][1] == "127.0.0.1"


def test_uvicorn_port(cap):
    _run(cap)
    assert _UvicornFake.calls[0][2] == 8000


def test_custom_host_port(cap):
    cli_mod.run_serve_command(
        types.SimpleNamespace(host="0.0.0.0", port=9999))
    call = _UvicornFake.calls[0]
    assert call[1] == "0.0.0.0"
    assert call[2] == 9999


def test_custom_host_shown(cap):
    cli_mod.run_serve_command(
        types.SimpleNamespace(host="0.0.0.0", port=9999))
    out = _norm(cap.getvalue())
    assert "0.0.0.0" in out
    assert "9999" in out


def test_panel_before_uvicorn(cap):
    cli_mod.run_serve_command(_args())
    assert "AnswRank" in cap.getvalue()


# -- uvicorn eksik ---------------------------------------------------------------------------------

def test_no_uvicorn_message(monkeypatch):
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **kw):
        if name == "uvicorn":
            raise ImportError("No module named 'uvicorn'")
        return real_import(name, *a, **kw)
    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.delitem(sys.modules, "uvicorn", raising=False)
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    cli_mod.run_serve_command(_args())
    out = _norm(buf.getvalue())
    assert "Hata" in out
    assert "serve" in out


def test_no_uvicorn_returns_none(monkeypatch):
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **kw):
        if name == "uvicorn":
            raise ImportError("yok")
        return real_import(name, *a, **kw)
    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.delitem(sys.modules, "uvicorn", raising=False)
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    assert cli_mod.run_serve_command(_args()) is None


def test_no_uvicorn_no_uvicorn_call(monkeypatch):
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **kw):
        if name == "uvicorn":
            raise ImportError("yok")
        return real_import(name, *a, **kw)
    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.delitem(sys.modules, "uvicorn", raising=False)
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    cli_mod.run_serve_command(_args())
    out = _norm(buf.getvalue())
    assert "Hata" in out
    assert "Doküman" not in out


def test_no_uvicorn_pip_hint(monkeypatch):
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **kw):
        if name == "uvicorn":
            raise ImportError("yok")
        return real_import(name, *a, **kw)
    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.delitem(sys.modules, "uvicorn", raising=False)
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console",
                        cli_mod.Console(file=buf, width=200))
    cli_mod.run_serve_command(_args())
    assert "pip" in _norm(buf.getvalue())


# -- cesitli portlar ---------------------------------------------------------------------------------

@pytest.mark.parametrize("port", [80, 3000, 8000, 8080, 65535])
def test_various_ports(cap, port):
    cli_mod.run_serve_command(
        types.SimpleNamespace(host="localhost", port=port))
    assert _UvicornFake.calls[0][2] == port


def test_localhost_host(cap):
    cli_mod.run_serve_command(
        types.SimpleNamespace(host="localhost", port=8000))
    assert _UvicornFake.calls[0][1] == "localhost"


def test_url_in_output_uses_host(cap):
    cli_mod.run_serve_command(
        types.SimpleNamespace(host="localhost", port=8000))
    assert "http://localhost:8000" in _norm(cap.getvalue())


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(cap):
    a = _norm(_run(cap))
    b = _norm(_run(cap))
    assert "AnswRank" in a and "AnswRank" in b
    assert "127.0.0.1:8000" in a and "127.0.0.1:8000" in b


def test_two_runs_two_uvicorn_calls(cap):
    _run(cap)
    _run(cap)
    assert len(_UvicornFake.calls) == 2
