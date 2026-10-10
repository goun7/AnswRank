"""cli.run_sitemap_command dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: SitemapAuditor stub — gercek ag cagrisi YAPILMADI.
"""
import io
import types

import pytest

from answrank import cli as cli_mod


class _Result:
    def __init__(self, url, score):
        self.url = url
        self.overall_score = score
        self.severity = "high" if score < 50 else "medium"
        self.score_band = "guclu" if score >= 80 else (
            "orta" if score >= 50 else "zayif")


class _AuditorStub:
    results = []
    raises = None

    async def batch_audit(self, url, sector=None, max_urls=100):
        if _AuditorStub.raises:
            raise _AuditorStub.raises
        return _AuditorStub.results


@pytest.fixture
def cap(monkeypatch):
    import answrank.audit.sitemap as sm
    monkeypatch.setattr(sm, "SitemapAuditor", _AuditorStub)
    _AuditorStub.results = []
    _AuditorStub.raises = None
    buf = io.StringIO()
    cap_console = cli_mod.Console(file=buf, width=200)
    monkeypatch.setattr(cli_mod, "console", cap_console)
    return buf


def _args(url="https://x.example", sector=None, max_urls=100):
    return types.SimpleNamespace(url=url, sector=sector, max_urls=max_urls)


def _run(cap):
    cli_mod.run_sitemap_command(_args())
    return cap.getvalue()


# -- temel ---------------------------------------------------------------------------------

def test_returns_none(cap):
    assert cli_mod.run_sitemap_command(_args()) is None


def test_outputs_table(cap):
    _AuditorStub.results = [_Result("u1", 90)]
    out = _run(cap)
    assert "Site Haritası Denetimi" in out


def test_table_has_url_column(cap):
    _AuditorStub.results = [_Result("u1", 90)]
    assert "URL" in _run(cap)


def test_table_has_score_column(cap):
    assert "Skor" in _run(cap)


def test_table_has_level_column(cap):
    assert "Düzey" in _run(cap)


def test_title_contains_page_count(cap):
    _AuditorStub.results = [_Result("u1", 90)]
    out = _run(cap)
    assert "1 Sayfa" in out


def test_title_zero_pages(cap):
    _AuditorStub.results = []
    out = _run(cap)
    assert "0 Sayfa" in out


# -- sonuclar ---------------------------------------------------------------------------------

def test_row_url_shown(cap):
    _AuditorStub.results = [_Result("sayfa1", 90)]
    assert "sayfa1" in _run(cap)


def test_row_score_shown(cap):
    _AuditorStub.results = [_Result("u1", 73)]
    assert "73/100" in _run(cap)


def test_band_strong_95(cap):
    _AuditorStub.results = [_Result("u1", 95)]
    assert "guclu" in _run(cap)


def test_band_mid_60(cap):
    _AuditorStub.results = [_Result("u1", 60)]
    assert "orta" in _run(cap)


def test_band_weak_20(cap):
    _AuditorStub.results = [_Result("u1", 20)]
    assert "zayif" in _run(cap)


def test_boundary_80_strong(cap):
    _AuditorStub.results = [_Result("u1", 80)]
    assert "guclu" in _run(cap)


def test_boundary_79_orta(cap):
    _AuditorStub.results = [_Result("u1", 79)]
    assert "orta" in _run(cap)


def test_boundary_50_orta(cap):
    _AuditorStub.results = [_Result("u1", 50)]
    assert "orta" in _run(cap)


def test_boundary_49_zayif(cap):
    _AuditorStub.results = [_Result("u1", 49)]
    assert "zayif" in _run(cap)


def test_band_low_is_zayif(cap):
    _AuditorStub.results = [_Result("u1", 30)]
    assert "zayif" in _run(cap)


def test_two_distinct_bands(cap):
    _AuditorStub.results = [_Result("a", 90), _Result("b", 20)]
    out = _run(cap)
    assert "guclu" in out
    assert "zayif" in out


def test_three_rows(cap):
    _AuditorStub.results = [
        _Result("a", 90), _Result("b", 60), _Result("c", 20)]
    out = _run(cap)
    assert "a" in out and "b" in out and "c" in out


def test_empty_results_still_table(cap):
    _AuditorStub.results = []
    assert "Site Haritası Denetimi" in _run(cap)


# -- auditor cagrisi ---------------------------------------------------------------------------------

def test_batch_audit_called_with_url(cap):
    seen = []

    class _A(_AuditorStub):
        async def batch_audit(self, url, sector=None, max_urls=100):
            seen.append((url, sector))
            return []
    import answrank.audit.sitemap as sm
    sm.SitemapAuditor = _A
    _run(cap)
    assert seen[0][0] == "https://x.example"


def test_sector_passed(cap):
    seen = []

    class _A(_AuditorStub):
        async def batch_audit(self, url, sector=None, max_urls=100):
            seen.append(sector)
            return []
    import answrank.audit.sitemap as sm
    sm.SitemapAuditor = _A
    cli_mod.run_sitemap_command(
        types.SimpleNamespace(url="https://x", sector="dental",
                              max_urls=100))
    assert seen[0] == "dental"


def test_sector_default_none(cap):
    seen = []

    class _A(_AuditorStub):
        async def batch_audit(self, url, sector=None, max_urls=100):
            seen.append(sector)
            return []
    import answrank.audit.sitemap as sm
    sm.SitemapAuditor = _A
    _run(cap)
    assert seen[0] is None


def test_error_propagates(cap):
    _AuditorStub.raises = RuntimeError("ag hatasi")
    with pytest.raises(RuntimeError):
        _run(cap)


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(cap):
    _AuditorStub.results = [_Result("u1", 90)]
    a = _run(cap)
    b = _run(cap)
    assert "Skor" in a and "Skor" in b
    assert "90/100" in a and "90/100" in b
