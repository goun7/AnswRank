"""run_probe_waf_command WAF sondası testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Dış çağrı YOK: WAFProbeEngine.probe_url sahte sonuç ile monkeypatch'lendi.
"""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "answrank")

from answrank.audit.waf_probe import WAFProbeEngine, WAFRiskLevel  # noqa: E402
from answrank.cli import run_probe_waf_command  # noqa: E402


class _Args:
    def __init__(self, url="https://example.com"):
        self.url = url


def _bot(name, code=200, ok=True, sig=None, t=120):
    return SimpleNamespace(
        bot_name=name, user_agent="test-ua", status_code=code,
        is_accessible=ok, is_cloudflare_challenge=code == 403,
        is_waf_blocked=not ok, blocking_signature=sig,
        response_time_ms=t)


def _result(risk=WAFRiskLevel.LOW, bots=None, total=10):
    bots = bots or [_bot("GPTBot"), _bot("PerplexityBot")]
    acc = sum(1 for b in bots if b.is_accessible)
    blk = sum(1 for b in bots if b.is_waf_blocked)
    unr = sum(1 for b in bots if b.status_code == 0)
    return SimpleNamespace(
        target_url="https://example.com", overall_risk=risk,
        is_silently_blocked=risk == WAFRiskLevel.CRITICAL,
        accessible_bots_count=acc, blocked_bots_count=blk,
        total_probed=total, unreachable_bots_count=unr,
        baseline_reachable=True, detected_waf_provider=None,
        bot_statuses=bots,
        remediation_recommendation="Öneri: robots.txt kontrol edin.")


@pytest.fixture
def patch_probe(monkeypatch):
    """probe_url'i sahte senkron-coroutine ile değiştir."""

    def _make(result):
        async def _fake(url):
            _fake.url = url
            return result
        monkeypatch.setattr(WAFProbeEngine, "probe_url", staticmethod(_fake))
        return _fake

    return _make


# -- temel çalışma ---------------------------------------------------------------------------

def test_low_risk_renders(capsys, patch_probe):
    patch_probe(_result(WAFRiskLevel.LOW))
    rc = run_probe_waf_command(_Args())
    out = capsys.readouterr().out
    assert "example.com" in out
    assert rc is None  # hata yok


def test_medium_risk_renders(capsys, patch_probe):
    patch_probe(_result(WAFRiskLevel.MEDIUM))
    run_probe_waf_command(_Args())
    assert "MEDIUM" in capsys.readouterr().out


def test_critical_risk_renders(capsys, patch_probe):
    patch_probe(_result(WAFRiskLevel.CRITICAL))
    run_probe_waf_command(_Args())
    assert "CRITICAL" in capsys.readouterr().out


def test_unverified_risk_renders(capsys, patch_probe):
    patch_probe(_result(WAFRiskLevel.UNVERIFIED))
    run_probe_waf_command(_Args())
    assert "UNVERIFIED" in capsys.readouterr().out


def test_target_url_displayed(capsys, patch_probe):
    r = _result()
    r.target_url = "https://hedef.site"
    patch_probe(r)
    run_probe_waf_command(_Args())
    assert "hedef.site" in capsys.readouterr().out


# -- bot durumları ---------------------------------------------------------------------------

def test_accessible_bot_shown(capsys, patch_probe):
    patch_probe(_result(bots=[_bot("GPTBot", 200, True)]))
    run_probe_waf_command(_Args())
    assert "GPTBot" in capsys.readouterr().out


def test_blocked_bot_shown(capsys, patch_probe):
    patch_probe(_result(bots=[_bot("GPTBot", 403, False)]))
    run_probe_waf_command(_Args())
    assert "GPTBot" in capsys.readouterr().out


def test_blocking_signature_shown(capsys, patch_probe):
    sig = "SIG-XYZ-987"
    patch_probe(_result(bots=[_bot("GPTBot", 403, False, sig)]))
    run_probe_waf_command(_Args())
    assert sig in capsys.readouterr().out


def test_clean_signature_shown(capsys, patch_probe):
    patch_probe(_result(bots=[_bot("GPTBot", 200, True)]))
    run_probe_waf_command(_Args())
    assert "Temiz" in capsys.readouterr().out


def test_unreachable_bot_shown(capsys, patch_probe):
    r = _result(WAFRiskLevel.UNVERIFIED, bots=[_bot("GPTBot", 0, False)])
    patch_probe(r)
    run_probe_waf_command(_Args())
    assert "GPTBot" in capsys.readouterr().out


def test_counts_displayed(capsys, patch_probe):
    r = _result(bots=[_bot("A", 200, True), _bot("B", 403, False)], total=2)
    patch_probe(r)
    run_probe_waf_command(_Args())
    out = capsys.readouterr().out
    # panel: erişilebilir/engellenen sayıları + hedef URL görünür
    assert "example.com" in out
    assert str(r.accessible_bots_count) in out


# -- remediation ---------------------------------------------------------------------------

def test_remediation_shown(capsys, patch_probe):
    r = _result()
    r.remediation_recommendation = "ÖNERİ-XYZ-123"
    patch_probe(r)
    run_probe_waf_command(_Args())
    assert "ÖNERİ-XYZ-123" in capsys.readouterr().out


def test_remediation_empty_ok(capsys, patch_probe):
    r = _result()
    r.remediation_recommendation = ""
    patch_probe(r)
    run_probe_waf_command(_Args())
    assert "example.com" in capsys.readouterr().out


# -- roster ----------------------------------------------------------------------------------

def test_roster_size_used(patch_probe):
    """Roster okunur — progress görev açıklamasında kullanılır."""
    import answrank.cli as cli
    captured = []
    orig = cli.Progress

    class _P:
        def __init__(self, *a, **k):
            self.tasks = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def add_task(self, description="", total=None):
            captured.append(description)

    cli.Progress = _P
    try:
        patch_probe(_result())
        run_probe_waf_command(_Args())
        assert any("AI Bot User-Agent" in d for d in captured)
    finally:
        cli.Progress = orig


def test_total_probed_fallback(capsys, patch_probe):
    """total_probed=0 → roster_n kullanılır."""
    r = _result(total=0)
    patch_probe(r)
    run_probe_waf_command(_Args())
    n = len(WAFProbeEngine.AI_CRAWLER_USER_AGENTS)
    assert str(n) in capsys.readouterr().out


# -- URL doğrulama ---------------------------------------------------------------------------

def test_url_passed_to_engine(capsys, patch_probe):
    fake = patch_probe(_result())
    run_probe_waf_command(_Args("https://probe-hedef.com"))
    assert fake.url == "https://probe-hedef.com"


def test_http_url_ok(capsys, patch_probe):
    r = _result()
    r.target_url = "http://insecure.site"
    patch_probe(r)
    run_probe_waf_command(_Args())
    assert "insecure.site" in capsys.readouterr().out


def test_localhost_ok(capsys, patch_probe):
    r = _result()
    r.target_url = "http://localhost:8000"
    patch_probe(r)
    run_probe_waf_command(_Args())
    assert "localhost" in capsys.readouterr().out


# -- sağlamlık ---------------------------------------------------------------------------

def test_empty_bot_list_ok(capsys, patch_probe):
    patch_probe(_result(bots=[]))
    run_probe_waf_command(_Args())
    assert "example.com" in capsys.readouterr().out


def test_many_bots_ok(capsys, patch_probe):
    bots = [_bot(f"Bot{i}", 200, True) for i in range(20)]
    patch_probe(_result(bots=bots, total=20))
    run_probe_waf_command(_Args())
    assert "example.com" in capsys.readouterr().out


def test_probe_error_propagates(monkeypatch):
    async def _bad(url):
        raise RuntimeError("ağ hatası")
    monkeypatch.setattr(WAFProbeEngine, "probe_url", staticmethod(_bad))
    with pytest.raises(RuntimeError):
        run_probe_waf_command(_Args())


def test_risk_style_mapping_complete(capsys, patch_probe):
    """Tüm 4 risk seviyesi render edilebilmeli."""
    for risk in WAFRiskLevel:
        patch_probe(_result(risk))
        run_probe_waf_command(_Args())
        assert risk.value in capsys.readouterr().out
