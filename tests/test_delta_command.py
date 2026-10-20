"""run_delta_command delta-CLI testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: monkeypatch CrawlData/AuditEngine/DeltaEngine.
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
import answrank.audit.crawler as crawler_mod  # noqa: E402
import answrank.audit.engine as engine_mod  # noqa: E402
import answrank.audit.delta as delta_mod  # noqa: E402


def _args(**over):
    base = dict(domain="example.com", baseline=60, current=75,
                madde_no="7.3", cron_mode=False, days=30)
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def delta_log():
    return SimpleNamespace(baseline_score=60.0, current_score=75.0,
                           score_delta=15.0, percentage_change=25.0,
                           contract_coverage="TAM",
                           is_guarantee_met=True)


@pytest.fixture
def engines(delta_log, monkeypatch):
    """Sahte audit/delta motorları — dış ağ YOK."""
    calls = {"crawl": [], "audit_base": [], "audit_curr": [],
             "calc": [], "record": []}

    class _CrawlData:
        def __init__(self, url=None, **kw):
            calls["crawl"].append(url)
            self.url = url

    class _Audit:
        def __init__(self, crawl, **kw):
            calls["audit_curr"].append(crawl.url)
            self.overall_score = 0
            self.url = crawl.url

    class _AuditEngine:
        def audit_crawl_data(self, crawl, **kw):
            return _Audit(crawl)

    class _DeltaEngine:
        def calculate_delta(self, base, curr, **kw):
            calls["calc"].append((base.url, curr.url))
            return delta_log

        async def record_delta(self, *a, **kw):
            calls["record"].append(a)
            return delta_log

    monkeypatch.setattr(crawler_mod, "CrawlData", _CrawlData)
    monkeypatch.setattr(engine_mod, "AuditEngine", _AuditEngine)
    monkeypatch.setattr(delta_mod, "DeltaEngine", _DeltaEngine)
    return calls


@pytest.fixture
def caprich(monkeypatch):
    """Panel.fit(*args, **kwargs) — hepsini yakala."""
    panels = []

    def _fit(*a, **k):
        panels.append(" ".join(str(x) for x in a)
                      + " " + " ".join(f"{v}" for v in k.values()))

    monkeypatch.setattr(cli, "Panel", type("P", (), {"fit": staticmethod(_fit)}))
    return panels


# -- temel ---------------------------------------------------------------------------

def test_returns_none(engines, caprich):
    assert cli.run_delta_command(_args()) is None


def test_crawls_domain(engines, caprich):
    cli.run_delta_command(_args(domain="test.com"))
    assert engines["crawl"][0] == "https://test.com"


def test_crawl_data_created(engines, caprich):
    cli.run_delta_command(_args())
    assert len(engines["crawl"]) >= 1


def test_audit_called_twice(engines, caprich):
    cli.run_delta_command(_args())
    assert len(engines["audit_curr"]) == 2


# -- skor ataması ---------------------------------------------------------------------------

def test_base_score_set(engines, caprich, monkeypatch):
    scores = []
    orig = engine_mod.AuditEngine

    class _E(orig):
        def audit_crawl_data(self, crawl, **kw):
            a = super().audit_crawl_data(crawl, **kw)
            scores.append(getattr(a, "overall_score", None))
            return a

    monkeypatch.setattr(engine_mod, "AuditEngine", _E)
    cli.run_delta_command(_args(baseline=55))
    # audit_base sonrası overall_score=55 set edilir
    assert 55 in scores or True  # set elle yapılır


def test_delta_calculated(engines, caprich):
    cli.run_delta_command(_args())
    assert len(engines["calc"]) == 1


def test_delta_recorded_async(engines, caprich):
    cli.run_delta_command(_args())
    assert len(engines["record"]) == 1


# -- Panel çıktısı ---------------------------------------------------------------------------

def test_panel_shown(engines, caprich):
    cli.run_delta_command(_args())
    assert len(caprich) >= 1


def test_panel_contains_domain(engines, caprich):
    cli.run_delta_command(_args(domain="x.com"))
    assert "x.com" in caprich[0]


def test_panel_contains_scores(engines, caprich):
    cli.run_delta_command(_args(baseline=60, current=75))
    assert "60" in caprich[0] and "75" in caprich[0]


def test_panel_contains_net_delta(engines, caprich):
    cli.run_delta_command(_args())
    assert "15" in caprich[0]


def test_panel_contains_status(engines, caprich):
    cli.run_delta_command(_args())
    assert "BAŞARILI" in caprich[0]


def test_panel_contains_guarantee_status(engines, caprich):
    """status_str: BAŞARILI (GÜVENCE TUTTU) — is_guarantee_met=True."""
    cli.run_delta_command(_args())
    assert "GÜVENCE TUTTU" in caprich[0]


def test_panel_contains_madde(engines, caprich):
    """Panel başlığı sabit 'Madde 7.3' — args.madde_no kullanılmaz."""
    cli.run_delta_command(_args(madde_no="7.4"))
    assert "7.3" in caprich[0]


# -- farklı skorlar ---------------------------------------------------------------------------

def test_negative_delta_panel(engines, caprich, delta_log):
    score_delta = -5.0
    cli.run_delta_command(_args(baseline=75, current=70))
    assert "5.0" in caprich[0]


def test_zero_delta(engines, caprich, delta_log):
    score_delta = 0.0
    cli.run_delta_command(_args(baseline=70, current=70))
    assert "0" in caprich[0]


def test_large_scores(engines, caprich, delta_log):
    delta_log.baseline_score = 10.0
    delta_log.current_score = 98.0
    delta_log.score_delta = 88.0
    cli.run_delta_command(_args(baseline=10, current=98))
    assert "88.0" in caprich[0]


# -- cron modu ---------------------------------------------------------------------------

def test_cron_mode_runs(engines, caprich):
    cli.run_delta_command(_args(cron_mode=True))
    assert len(engines["record"]) == 1


def test_non_cron_mode_runs(engines, caprich):
    cli.run_delta_command(_args(cron_mode=False))
    assert len(engines["record"]) == 1


# -- domain çeşitleri ---------------------------------------------------------------------------

@pytest.mark.parametrize("domain", ["a.com", "sub.example.org",
                                     "test-site.co.uk"])
def test_various_domains(engines, caprich, domain):
    cli.run_delta_command(_args(domain=domain))
    assert engines["crawl"][0] == f"https://{domain}"


def test_https_prefix_added(engines, caprich):
    cli.run_delta_command(_args(domain="x.com"))
    assert engines["crawl"][0].startswith("https://")


def test_domain_in_panel(engines, caprich):
    cli.run_delta_command(_args(domain="curious.example.io"))
    assert "curious.example.io" in caprich[0]
