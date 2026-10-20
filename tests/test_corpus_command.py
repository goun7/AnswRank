"""run_corpus_command E5 CLI korpüs testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: monkeypatch CorpusStore.collect + sahte Database.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")
# G47: sester SDK PyPI-de ( sester==0.7.5, CI-de-kurulu);
# yalnizca-yerel-gelistirme-icin yedek-yol ( CI-de-YOK).
sys.path.insert(0, os.environ.get(
    "MESH_SESTER_ROOT", "../../01_unicorn/63-Sester"))

import answrank.cli as cli  # noqa: E402
import answrank.corpus as corpus_mod  # noqa: E402
import answrank.db as db_mod  # noqa: E402


def _args(**over):
    base = dict(corpus_cmd="probe", file=None, tag="test", politeness=1,
                out=None)
    base.update(over)
    return SimpleNamespace(**base)


def _domains_file(tmp_path, lines):
    p = tmp_path / "domains.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


class _FakeStore:
    def __init__(self, n=5, stats=None, rows=None):
        self.n = n
        self._stats = stats or {"n": 5, "ai_visible": 2, "partial": 1,
                                "none": 2}
        self._rows = rows or []
        self.collect_calls = []

    async def collect(self, domains, politeness_sec=1, source=None):
        self.collect_calls.append((domains, politeness_sec, source))
        return self.n

    def stats(self, source=None):
        return self._stats

    def list_observations(self, source=None):
        return self._rows


@pytest.fixture
def store(monkeypatch):
    s = _FakeStore()
    monkeypatch.setattr(corpus_mod, "CorpusStore", lambda db=None: s)
    monkeypatch.setattr(db_mod, "Database", lambda: None)
    monkeypatch.setattr(corpus_mod, "render_report_md",
                        lambda st, method="": f"RAPOR n={st['n']} {method}")
    return s


@pytest.fixture
def caprich(monkeypatch):
    """Rich Panel/console çıktısını yakala."""
    panels = []
    monkeypatch.setattr(cli, "Panel", lambda t, title="": panels.append(str(t)))
    return panels


# -- probe ---------------------------------------------------------------------------

def test_probe_reads_domains(store, tmp_path):
    f = _domains_file(tmp_path, ["a.com", "b.com"])
    cli.run_corpus_command(_args(file=f))
    assert store.collect_calls[0][0] == ["a.com", "b.com"]


def test_probe_reports_count(store, capsys, tmp_path):
    f = _domains_file(tmp_path, ["a.com"])
    cli.run_corpus_command(_args(file=f))
    assert "5 gözlem" in capsys.readouterr().out


def test_probe_reports_tag(store, capsys, tmp_path):
    f = _domains_file(tmp_path, ["a.com"])
    cli.run_corpus_command(_args(file=f, tag="etiket-1"))
    assert "etiket-1" in capsys.readouterr().out


def test_probe_passes_politeness(store, tmp_path):
    f = _domains_file(tmp_path, ["a.com"])
    cli.run_corpus_command(_args(file=f, politeness=7))
    assert store.collect_calls[0][1] == 7


def test_probe_passes_source(store, tmp_path):
    f = _domains_file(tmp_path, ["a.com"])
    cli.run_corpus_command(_args(file=f, tag="src-1"))
    assert store.collect_calls[0][2] == "src-1"


def test_probe_skips_blank_lines(store, tmp_path):
    f = _domains_file(tmp_path, ["a.com", "", "  ", "b.com"])
    cli.run_corpus_command(_args(file=f))
    assert store.collect_calls[0][0] == ["a.com", "b.com"]


def test_probe_skips_comments(store, tmp_path):
    f = _domains_file(tmp_path, ["# yorum", "a.com", "# diğerr"])
    cli.run_corpus_command(_args(file=f))
    assert store.collect_calls[0][0] == ["a.com"]


def test_probe_strips_whitespace(store, tmp_path):
    f = _domains_file(tmp_path, ["  a.com  "])
    cli.run_corpus_command(_args(file=f))
    assert store.collect_calls[0][0] == ["a.com"]


def test_probe_empty_list_no_call(store, capsys, tmp_path):
    f = _domains_file(tmp_path, ["# sadece yorum", ""])
    cli.run_corpus_command(_args(file=f))
    assert store.collect_calls == []
    assert "boş" in capsys.readouterr().out


def test_probe_only_whitespace_no_call(store, tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("   \n\t\n", encoding="utf-8")
    cli.run_corpus_command(_args(file=str(p)))
    assert store.collect_calls == []


def test_probe_missing_file_raises(store, tmp_path):
    with pytest.raises(FileNotFoundError):
        cli.run_corpus_command(_args(file=str(tmp_path / "yok.txt")))


def test_probe_async_collects(store, tmp_path):
    """collect coroutine asyncio.run ile çalışır."""
    f = _domains_file(tmp_path, ["x.com"])
    cli.run_corpus_command(_args(file=f))
    assert store.collect_calls[0][0] == ["x.com"]


# -- stats ---------------------------------------------------------------------------

def test_stats_writes_out_file(store, tmp_path):
    out = tmp_path / "report.md"
    cli.run_corpus_command(_args(corpus_cmd="stats", out=str(out)))
    assert out.exists()
    assert len(out.read_text()) > 0


def test_stats_out_contains_count(store, tmp_path):
    out = tmp_path / "r.md"
    cli.run_corpus_command(_args(corpus_cmd="stats", out=str(out)))
    assert "n=5" in out.read_text()


def test_stats_prints_panel_when_no_out(store, caprich, capsys):
    cli.run_corpus_command(_args(corpus_cmd="stats"))
    assert len(caprich) >= 1


def test_stats_method_string_in_report(store, tmp_path):
    out = tmp_path / "r.md"
    cli.run_corpus_command(_args(corpus_cmd="stats", out=str(out),
                                 tag="deneme"))
    md = out.read_text()
    assert "deneme" in md  # method string tag'i içerir


def test_stats_all_tags_when_no_tag(store, tmp_path):
    out = tmp_path / "r.md"
    cli.run_corpus_command(_args(corpus_cmd="stats", out=str(out), tag=None))
    assert "tüm etiketler" in out.read_text()


def test_stats_empty_corpus_warns(store, caprich, capsys, monkeypatch):
    monkeypatch.setattr(corpus_mod, "CorpusStore",
                        lambda db=None: _FakeStore(stats={"n": 0}))
    cli.run_corpus_command(_args(corpus_cmd="stats"))
    assert "Korpüs boş" in capsys.readouterr().out


def test_stats_empty_no_report(store, tmp_path, monkeypatch):
    monkeypatch.setattr(corpus_mod, "CorpusStore",
                        lambda db=None: _FakeStore(stats={"n": 0}))
    cli.run_corpus_command(_args(corpus_cmd="stats", out=str(tmp_path / "r.md")))
    assert not (tmp_path / "r.md").exists()


# -- list ---------------------------------------------------------------------------

def test_list_prints_rows(store, caprich, capsys):
    store._rows = [{"observed_at": "2026-10-08T12:00:00Z", "domain": "a.com",
                    "verdict": "AI_VISIBLE", "robots_line": "Allow: /"}]
    cli.run_corpus_command(_args(corpus_cmd="list"))
    assert "a.com" in capsys.readouterr().out


def test_list_truncates_timestamp(store, capsys):
    store._rows = [{"observed_at": "2026-10-08T12:00:00.123456+00:00",
                    "domain": "b.com", "verdict": "NONE",
                    "robots_line": "-"}]
    cli.run_corpus_command(_args(corpus_cmd="list"))
    assert "2026-10-08T12:00:00" in capsys.readouterr().out


def test_list_empty_warns(store, capsys):
    cli.run_corpus_command(_args(corpus_cmd="list"))
    assert "Kayıtlı gözlem yok" in capsys.readouterr().out


def test_list_filters_by_tag(store, capsys):
    store._rows = [{"observed_at": "2026-10-08T12:00:00Z", "domain": "c.com",
                    "verdict": "PARTIAL", "robots_line": "-"}]
    cli.run_corpus_command(_args(corpus_cmd="list", tag="filitre"))
    assert store.list_observations(source="filitre") == store._rows


# -- bilinmeyen komut ---------------------------------------------------------------------------

def test_unknown_command_noop(store):
    cli.run_corpus_command(_args(corpus_cmd="yok"))
    assert store.collect_calls == []
