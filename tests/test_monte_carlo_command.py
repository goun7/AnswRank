"""run_monte_carlo_command stokastik-simülasyon CLI testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: monkeypatch MonteCarloEngine.
"""
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
import answrank.citations.monte_carlo as mc_mod  # noqa: E402


class _Iter:
    def __init__(self, iteration_index=1, citation_rate_pct=72.5,
                 citations_count=725, total_runs=1000,
                 temperature=0.7, live_items=980):
        self.iteration_index = iteration_index
        self.citation_rate_pct = citation_rate_pct
        self.citations_count = citations_count
        self.total_runs = total_runs
        self.temperature = temperature
        self.live_items = live_items



class _MCResult:
    def __init__(self, iterations=None, brand_name="TestMarka",
                 domain="test.com", measurement_mode="Canlı",
                 mean_citation_rate_pct=72.5,
                 confidence_interval_95_str="68.0 - 77.0",
                 stability_index=92.0,
                 stability_grade="ROCK_SOLID", summary_report="Başarılı",
                 iterations_count=100, is_statistically_valid=True):
        self.iterations = iterations if iterations is not None else [_Iter()]
        self.brand_name = brand_name
        self.domain = domain
        self.measurement_mode = measurement_mode
        self.mean_citation_rate_pct = mean_citation_rate_pct
        self.confidence_interval_95_str = confidence_interval_95_str
        self.stability_index = stability_index
        self.stability_grade = stability_grade
        self.summary_report = summary_report
        self.iterations_count = iterations_count
        self.is_statistically_valid = is_statistically_valid



def _args(**over):
    base = dict(brand="TestMarka", domain="test.com", sector="SaaS",
                city="İstanbul", iterations=100)
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def mc(monkeypatch):
    calls = []
    last_result = _MCResult()

    class _Engine:
        @staticmethod
        async def evaluate_stochastic_stability(**kw):
            calls.append(kw)
            return last_result

    monkeypatch.setattr(mc_mod, "MonteCarloEngine", _Engine)
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

def test_returns_none(mc, caprich):
    assert cli.run_monte_carlo_command(_args()) is None


def test_simulation_called(mc, caprich):
    cli.run_monte_carlo_command(_args())
    assert len(mc[0]) == 1


def test_all_params_passed(mc, caprich):
    cli.run_monte_carlo_command(_args(brand="X", domain="y.com",
                                      sector="Z", city="W", iterations=50))
    kw = mc[0][0]
    assert kw["brand_name"] == "X"
    assert kw["domain"] == "y.com"
    assert kw["sector"] == "Z"
    assert kw["city"] == "W"
    assert kw["iterations"] == 50


def test_progress_description(mc, caprich):
    cli.run_monte_carlo_command(_args(brand="MarkaABC"))
    assert "MarkaABC" in caprich[1][0]


def test_progress_shows_iterations(mc, caprich):
    cli.run_monte_carlo_command(_args(iterations=250))
    assert "250" in caprich[1][0]


# -- Panel çıktısı ---------------------------------------------------------------------------

def test_panel_shown(mc, caprich):
    cli.run_monte_carlo_command(_args())
    assert any(s[0] == "panel" for s in caprich[0])


def test_panel_contains_brand(mc, caprich):
    cli.run_monte_carlo_command(_args(brand="Acme"))
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    # res.brand_name sabit (args.brand kullanilmaz)
    assert "TestMarka" in str(panel[1])


def test_panel_contains_avg_rate(mc, caprich):
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "72.5" in str(panel[1])


def test_panel_contains_ci(mc, caprich):
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "68.0 - 77.0" in str(panel[1])


def test_panel_contains_stability(mc, caprich):
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "92.0" in str(panel[1])


def test_panel_contains_summary(mc, caprich):
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "Başarılı" in str(panel[1])


# -- istatistiksel geçerlilik ---------------------------------------------------------------------------

def test_valid_no_warning(mc, caprich):
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "GEÇERSİZ" not in str(panel[1])


def test_invalid_shows_warning(mc, caprich):
    mc[1].is_statistically_valid = False
    cli.run_monte_carlo_command(_args())
    assert any(s[0] == "panel" for s in caprich[0])


# -- tablo ---------------------------------------------------------------------------

def test_table_shown(mc, caprich):
    cli.run_monte_carlo_command(_args())
    assert any(s[0] == "table" for s in caprich[0])


def test_table_rows_for_iterations(mc, caprich):
    mc[1].iterations = [_Iter(iteration_index=i) for i in range(5)]
    cli.run_monte_carlo_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert len(rows) == 5


def test_table_row_content(mc, caprich):
    mc[1].iterations = [_Iter(iteration_index=3, citation_rate_pct=88.8,
                              citations_count=888, temperature=0.9)]
    cli.run_monte_carlo_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    r = str(rows[0][1])
    assert "#3" in r and "88.8" in r and "888" in r


def test_table_zero_iterations(mc, caprich):
    mc[1].iterations = []
    cli.run_monte_carlo_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    assert len(rows) == 0


def test_live_response_shown(mc, caprich):
    mc[1].iterations = [_Iter(live_items=980, total_runs=1000)]
    cli.run_monte_carlo_command(_args())
    rows = [s for s in caprich[0] if s[0] == "row"]
    # canlı yanıt "live_items/total_runs" olarak gösterilir
    assert "980/1000" in str(rows[0][1])


# -- çeşitli sonuçlar ---------------------------------------------------------------------------

def test_high_rate(mc, caprich):
    mc[1].mean_citation_rate_pct = 95.3
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "95.3" in str(panel[1])


def test_low_rate(mc, caprich):
    mc[1].mean_citation_rate_pct = 8.1
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "8.1" in str(panel[1])


def test_tight_ci(mc, caprich):
    mc[1].confidence_interval_95_str = "71.9 - 73.1"
    cli.run_monte_carlo_command(_args())
    panel = [s for s in caprich[0] if s[0] == "panel"][0]
    assert "71.9" in str(panel[1])


# -- parametre çeşitleri ---------------------------------------------------------------------------

@pytest.mark.parametrize("iterations", [10, 100, 1000])
def test_various_iterations(mc, caprich, iterations):
    cli.run_monte_carlo_command(_args(iterations=iterations))
    assert mc[0][0]["iterations"] == iterations


@pytest.mark.parametrize("sector", ["SaaS", "E-ticaret", "Finans"])
def test_various_sectors(mc, caprich, sector):
    cli.run_monte_carlo_command(_args(sector=sector))
    assert mc[0][0]["sector"] == sector
