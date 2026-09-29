"""E3 mini-probe kırmızı-tasdik testleri (D-16.09-M kararı, 16 Eyl).

Herkese-açık ücretsiz yüzeyin üç anayasası test edilir:
1. SSRF/şema koruması — iç ağa tek bir bayt gitmez.
2. Ölçüm-kapısı — ulaşılamaz hedef suçlanamaz, her satır ÖLÇÜLEMEDİ kalır.
3. Sayı-fabrikası yasağı — mini kartta hiçbir skor/hakediş yüzdesi YOKTUR.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from answrank.audit.waf_probe import WAFProbeResult, BotProbeStatus
from answrank.probe.miniprobe import MiniProbe, MiniProbeResult
from answrank.api.app import app


def _clean_probe(host: str, n: int = 3) -> WAFProbeResult:
    return WAFProbeResult(
        target_url=f"https://{host}", overall_risk="LOW", is_silently_blocked=False,
        accessible_bots_count=n, blocked_bots_count=0, total_probed=n,
        unreachable_bots_count=0, baseline_reachable=True, remediation_recommendation="fixture",
        bot_statuses=[BotProbeStatus(bot_name=b, user_agent="ua", status_code=200, is_accessible=True,
                                     is_cloudflare_challenge=False, is_waf_blocked=False)
                      for b in ("GPTBot", "PerplexityBot", "ClaudeBot")[:n]],
    )


def _blocked_probe(host: str) -> WAFProbeResult:
    return WAFProbeResult(
        target_url=f"https://{host}", overall_risk="CRITICAL", is_silently_blocked=True,
        accessible_bots_count=2, blocked_bots_count=1, total_probed=3,
        unreachable_bots_count=0, baseline_reachable=True, remediation_recommendation="fixture",
        bot_statuses=[
            BotProbeStatus(bot_name="GPTBot", user_agent="ua", status_code=403, is_accessible=False,
                           is_cloudflare_challenge=False, is_waf_blocked=True),
            BotProbeStatus(bot_name="PerplexityBot", user_agent="ua", status_code=200, is_accessible=True,
                           is_cloudflare_challenge=False, is_waf_blocked=False),
            BotProbeStatus(bot_name="ClaudeBot", user_agent="ua", status_code=200, is_accessible=True,
                           is_cloudflare_challenge=False, is_waf_blocked=False),
        ],
    )


def _unverifiable_probe(host: str) -> WAFProbeResult:
    return WAFProbeResult(
        target_url=f"https://{host}", overall_risk="UNVERIFIED", is_silently_blocked=False,
        accessible_bots_count=0, blocked_bots_count=0, total_probed=3,
        unreachable_bots_count=3, baseline_reachable=False, remediation_recommendation="fixture",
    )


def _fetch_map(mapping):
    async def fake(url, client=None):
        return mapping.get(url, (None, None))
    return fake


# ---------------------------------------------------------------- koruma testleri

@pytest.mark.parametrize("bad", [
    "file:///etc/passwd",
    "ftp://example.com",
    "gopher://10.0.0.1:11211",
    "javascript:alert(1)",
])
def test_miniprobe_rejects_non_http_scheme(bad):
    with patch.object(MiniProbe, "_fetch_text", new=AsyncMock()) as f, \
         patch.object(MiniProbe, "probe", new=AsyncMock()) as p:
        r = asyncio.run(MiniProbe.run(bad))
    assert r.verdict == "GİRİŞ REDDEDİLDİ"
    assert r.measured is False
    f.assert_not_awaited()
    p.assert_not_awaited()


@pytest.mark.parametrize("host", [
    "localhost", "127.0.0.1", "10.1.2.3", "192.168.0.55", "169.254.169.254", "0.0.0.0", "::1",
])
def test_miniprobe_rejects_internal_addresses(host):
    with patch.object(MiniProbe, "_fetch_text", new=AsyncMock()) as f, \
         patch.object(MiniProbe, "probe", new=AsyncMock()) as p:
        r = asyncio.run(MiniProbe.run(host))
    assert r.verdict == "GİRİŞ REDDEDİLDİ"
    assert "İÇ AĞ" in r.bots_line or "genel internet" in r.bots_line
    f.assert_not_awaited()
    p.assert_not_awaited()


# ------------------------------------------------------------- ölçüm-kapısı testleri

def test_miniprobe_happy_path_clean():
    host = "ornek-klinik.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (200, "User-agent: *\nDisallow: /private\n"),
            f"https://{host}/llms.txt": (404, None)})), \
         patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_clean_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    assert r.verdict == "TEMİZ" and r.measured is True
    assert "İZİNLİ" in r.robots_line
    assert r.llms_line == "YOK"
    assert r.bots_line == "3/3 örnek bot erişebiliyor"
    assert r.probed == 3


def test_miniprobe_unreachable_never_accuses():
    host = "yok-boyle-alan-adi.test"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({})), \
         patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_unverifiable_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    assert r.measured is False
    assert r.verdict == "ÖLÇÜLEMEDİ"
    assert "HÜKÜM VERİLEMEDİ" in r.bots_line
    assert "ENGELLİ" not in r.robots_line and "YOK" not in r.robots_line
    assert "ÖLÇÜLEMEDİ" in r.robots_line and "ÖLÇÜLEMEDİ" in r.llms_line


def test_miniprobe_blocked_bots_named():
    host = "wapo-gibi.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (200, "User-agent: *\nAllow: /\n"),
            f"https://{host}/llms.txt": (200, "# llms"),
         })), patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_blocked_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    assert r.verdict == "BOT ERİŞİMİ ENGELLİ"
    assert r.blocked_bots == ["GPTBot"]
    assert r.llms_line == "VAR"


def test_miniprobe_no_invented_numbers():
    """Mini kart bir SKOR kartı değildir: sayı alanı yalnız n/n sayaçlarıdır."""
    host = "ornek.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (200, "User-agent: *\nAllow: /\n"),
         })), patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_clean_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    blob = " ".join([r.robots_line, r.llms_line, r.bots_line, r.verdict])
    for banned in ("puan", "skor", "₺", "%"):
        assert banned not in blob


# ------------------------------------------------------------------ API yüzeyi

def test_api_miniprobe_honest_shape():
    host = "klinik-ornerk.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (404, None),
         })), patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_clean_probe(host))):
        client = TestClient(app)
        resp = client.post("/api/miniprobe", json={"domain": host})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"domain", "robots_line", "llms_line", "bots_line",
                         "blocked_bots", "probed", "verdict", "measured",
                         "robots_status", "llms_status", "bot_statuses"}


def test_api_miniprobe_rejects_empty_domain():
    client = TestClient(app)
    assert client.post("/api/miniprobe", json={"domain": ""}).status_code == 422


def test_api_miniprobe_rate_limited():
    host = "limit-test.example"
    ok = MiniProbeResult(domain=host, robots_line="x", llms_line="x", bots_line="x",
                         blocked_bots=[], probed=0, verdict="TEMİZ", measured=True)
    with patch("answrank.config.settings.mini_probe_daily_limit_per_ip", 2), \
         patch.object(MiniProbe, "run", new=AsyncMock(return_value=ok)), \
         patch("answrank.api.app._miniprobe_hits", {}):
        client = TestClient(app)
        assert client.post("/api/miniprobe", json={"domain": host}).status_code == 200
        assert client.post("/api/miniprobe", json={"domain": host}).status_code == 200
        third = client.post("/api/miniprobe", json={"domain": host})
        assert third.status_code == 429
        assert "mini-probe" in third.json()["detail"]


def test_waf_probe_subset_parameter():
    """Mini-probe 9 botluk tam roosterı yaktırmaz — probe_url'a bots= kesme parametresi."""
    import inspect
    from answrank.audit.waf_probe import WAFProbeEngine
    assert "bots" in inspect.signature(WAFProbeEngine.probe_url).parameters


# ------------------------------------------------------------- kapsam tamamlama

def test_miniprobe_empty_host_rejected():
    r = asyncio.run(MiniProbe.run("https://"))
    assert r.verdict == "GİRİŞ REDDEDİLDİ"


def test_miniprobe_robots_parse_error_and_odd_status():
    host = "bozuk-robots.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (200, "User-agent: *\nDisallow: /x\n"),
            f"https://{host}/llms.txt": (503, None)})), \
         patch("answrank.probe.miniprobe.RobotsAnalyzer", side_effect=RuntimeError("boom")), \
         patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_clean_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    assert "ÖLÇÜLEMEDİ" in r.robots_line and "HTTP 503" in r.llms_line
    assert r.verdict == "TEMİZ" or r.verdict == "KISMÎ ÖLÇÜM"  # robots düşerse KISMÎ


def test_fetch_text_success_and_http_error(monkeypatch):
    import httpx
    class _Resp:
        status_code = 200
        text = "User-agent: *\nAllow: /\n"
    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            if "fail" in url:
                raise httpx.ConnectError("nope")
            return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    assert asyncio.run(MiniProbe._fetch_text("https://ok.example/robots.txt")) == (200, "User-agent: *\nAllow: /\n")
    assert asyncio.run(MiniProbe._fetch_text("https://fail.example/robots.txt")) == (None, None)


def test_is_internal_dns_paths(monkeypatch):
    import socket
    def fake_public(*a):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]
    def fake_private(*a):
        return [(2, 1, 6, "", ("10.20.30.40", 0))]
    def fake_none(*a):
        raise socket.gaierror("no dns")
    monkeypatch.setattr(socket, "getaddrinfo", fake_public)
    assert asyncio.run(MiniProbe._is_internal("example.com")) is False
    monkeypatch.setattr(socket, "getaddrinfo", fake_private)
    assert asyncio.run(MiniProbe._is_internal("corp.internal")) is True
    monkeypatch.setattr(socket, "getaddrinfo", fake_none)
    assert asyncio.run(MiniProbe._is_internal("cozuemsuz.test")) is False


def test_api_miniprobe_500_sanitized():
    from answrank.probe.miniprobe import MiniProbe as MP
    with patch.object(MP, "run", new=AsyncMock(side_effect=RuntimeError("internal boom"))):
        client = TestClient(app)
        resp = client.post("/api/miniprobe", json={"domain": "patlar.example"})
    assert resp.status_code == 500
    assert "iç hata" in resp.json()["detail"] and "boom" not in resp.json()["detail"]


def test_landing_miniprobe_honest_defaults():
    import re
    tpl = open("answrank/api/templates/landing.html", encoding="utf-8").read()
    for sid in ("mp-domain", "mp-run", "mp-robots", "mp-llms", "mp-bots", "mp-verdict"):
        assert f'id="{sid}"' in tpl, sid
    for sid in ("mp-robots", "mp-llms", "mp-bots", "mp-verdict"):
        assert re.search(rf'id="{sid}">—</span>', tpl), f"{sid} varsayılanı — olmalı"
    assert 'aria-label="Denenecek alan adı"' in tpl
    # E4 (D-16.09-M): EN bankalar açıldı → bölüm tüm pazarlara açık; gizleme kararnamesi kalktı.
    # Yeni dürüstlük kilidi: çeviri, hüküm sözlüğünü çoğaltmaz — ÖLÇÜLEMEDİ token'ı üç dilde de aynı.
    assert "mpSec.style.display" not in tpl
    for mp_sub in [ln for ln in tpl.splitlines() if ln.strip().startswith("mp_sub:")]:  # comp_sub ⊅ karışmasın
        assert "ÖLÇÜLEMEDİ" in mp_sub
    assert sum(1 for ln in tpl.splitlines() if ln.strip().startswith("mp_title:")) == 3  # markup-hedef 3 sözlük (UK/US/DE) + data-i18n hedefi TR statik


def test_miniprobe_robots_blocked_line():
    host = "dusman-robots.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (200, "User-agent: *\nDisallow: /\n"),
            f"https://{host}/llms.txt": (404, None)})), \
         patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_clean_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    assert "ENGELLİ" in r.robots_line and r.verdict == "KISMÎ ÖLÇÜM"


def test_miniprobe_robots_odd_http_status():
    host = "robots-403.example"
    with patch.object(MiniProbe, "_fetch_text", new=_fetch_map({
            f"https://{host}/robots.txt": (403, None),
            f"https://{host}/llms.txt": (404, None)})), \
         patch.object(MiniProbe, "probe", new=AsyncMock(return_value=_clean_probe(host))):
        r = asyncio.run(MiniProbe.run(host))
    assert "HTTP 403" in r.robots_line


def test_bots_line_probe_none_guard():
    line, ok, blocked = MiniProbe._bots_line(None)
    assert line.startswith("HÜKÜM VERİLEMEDİ") and ok is False and blocked == []


def test_probe_wrapper_uses_micro_subset():
    from answrank.audit.waf_probe import WAFProbeEngine
    with patch.object(WAFProbeEngine, "probe_url", new=AsyncMock(return_value=_clean_probe("x.example"))) as pu:
        asyncio.run(MiniProbe.probe("https://x.example"))
    assert pu.await_args.kwargs["bots"] == MiniProbe.MICRO_BOTS


def test_is_internal_garbage_addr_and_fetch_non200(monkeypatch):
    import httpx, socket
    def fake_garbage(*a):
        return [(2, 1, 6, "", ("not-an-ip", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_garbage)
    assert asyncio.run(MiniProbe._is_internal("tuhaf.test")) is True

    class _Warn:
        status_code = 503
        text = ""
    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None): return _Warn()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    assert asyncio.run(MiniProbe._fetch_text("https://x.example/llms.txt")) == (503, None)
