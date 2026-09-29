"""E3 mini-probe — herkese-açık, ÜCRETSİZ, üç satırlık AI-erişim skor kartı.

Anayasası (D-16.09-M):
1. SSRF/şema kilidi: yalnız http(s) + İÇ AĞ/loopback/link-local reddi — hedef
   çözümlenmeden tek bir bayt dışarı gitmez.
2. Ölçüm-kapısı: ulaşılamayan satır suçlama ÜRETMEZ — "ÖLÇÜLEMEDİ"/"HÜKÜM
   VERİLEMEDİ" kalır;TEMİZ hükmü yalnız her satır ölçüldüğünde verilir.
3. Sayı-fabrikası yok: bu kart WAF/denetim skoru DEĞİLDİR; yalnız n/n sayaçları
   ve metin hükümler taşır (satış hunisi, mini denetim değil).
"""
from __future__ import annotations
import logging

import asyncio
import ipaddress
import re
import socket
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from answrank.audit.analyzers.robots import RobotsAnalyzer
from answrank.audit.waf_probe import WAFProbeEngine, WAFProbeResult

_UNMEASURED = "ÖLÇÜLEMEDİ"


logger = logging.getLogger("answrank.miniprobe")

class MiniProbeResult(BaseModel):
    domain: str
    robots_line: str
    llms_line: str
    bots_line: str
    blocked_bots: List[str]
    probed: int
    verdict: str
    measured: bool
    # E5 korpüsü: ham HTTP kanıtları (yüzey metinleri hüküm taşır; alan
    # istatistiği YALNIZ bu sayısal tanıklarla üretilir — None = ölçülmedi).
    robots_status: Optional[int] = None
    llms_status: Optional[int] = None
    bot_statuses: Dict[str, int] = Field(default_factory=dict)


class MiniProbe:
    """Three representative search/answer bots + robots/llms surface check."""

    MICRO_BOTS = ("GPTBot", "PerplexityBot", "ClaudeBot")
    _SCHEME_ALLOWED = ("http", "https")

    @classmethod
    async def run(cls, raw: str, timeout_sec: float = 6.0) -> MiniProbeResult:
        """Sondalama/koşum adımını yürütür."""
        s = (raw or "").strip().lower()
        m = re.match(r"^([a-z][a-z0-9+.-]*):", s)
        scheme = m.group(1) if m and ("://" in s or m.group(1) not in ("http", "https")) else (
            s.split("://", 1)[0] if "://" in s else "https")
        if scheme not in cls._SCHEME_ALLOWED:
            return cls._rejected(s or "?", "Yalnızca http/https adresleri taranır; bu şema reddedildi.")
        base = s if "://" in s else f"https://{s}"
        host = urlparse(base).hostname or base.split("://", 1)[-1].split("/")[0]
        if not host:
            return cls._rejected(s or "?", "Geçerli bir alan adı girin.")
        if await cls._is_internal(host):
            return cls._rejected(host, "Bu hedef genel bir internet adresi değil — İÇ AĞ/loopback adresleri taranmaz.")

        robots = await cls._fetch_text(f"https://{host}/robots.txt", timeout_sec)
        llms = await cls._fetch_text(f"https://{host}/llms.txt", timeout_sec)
        probe = await cls.probe(f"https://{host}", timeout_sec)

        robots_line, robots_ok, robots_clean = cls._robots_line(robots)
        llms_line, llms_ok = cls._llms_line(llms)
        bots_line, bots_ok, blocked = cls._bots_line(probe)
        probed = probe.total_probed if probe is not None else 0

        measured = robots_ok or llms_ok or bots_ok
        if blocked:
            verdict = "BOT ERİŞİMİ ENGELLİ"
        elif robots_ok and llms_ok and bots_ok and robots_clean:
            verdict = "TEMİZ"
        elif not measured:
            verdict = _UNMEASURED
        else:
            verdict = "KISMÎ ÖLÇÜM"
        return MiniProbeResult(domain=host, robots_line=robots_line, llms_line=llms_line,
                               bots_line=bots_line, blocked_bots=blocked, probed=probed,
                               verdict=verdict, measured=measured,
                               robots_status=robots[0], llms_status=llms[0],
                               bot_statuses=({b.bot_name: b.status_code for b in probe.bot_statuses}
                                              if probe is not None else {}))

    # ------------------------------------------------------------- satır hükümleri
    @staticmethod
    def _robots_line(r: Tuple[Optional[int], Optional[str]]):
        status, body = r
        if status is None:
            return f"{_UNMEASURED} (robots.txt indirilemedi)", False, False
        if status == 404:
            return "İZİNLİ (robots.txt yok — RFC 9309 varsayılanı açık)", True, True
        if status == 200 and body is not None:
            try:
                score = RobotsAnalyzer().analyze(body)
            except Exception:
                return f"{_UNMEASURED} (ayrıştırılamadı)", False, False
            if score.ai_search_allowed:
                return "İZİNLİ (AI araması açık)", True, True
            return "ENGELLİ (robots.txt AI aramasını kapatıyor)", True, False
        return f"{_UNMEASURED} (HTTP {status})", False, False

    @staticmethod
    def _llms_line(r: Tuple[Optional[int], Optional[str]]):
        status, body = r
        if status is None:
            return f"{_UNMEASURED} (llms.txt indirilemedi)", False
        if status == 200 and body and body.strip():
            return "VAR", True
        if status == 404:
            return "YOK", True
        return f"{_UNMEASURED} (HTTP {status})", False

    @staticmethod
    def _bots_line(probe: Optional[WAFProbeResult]):
        if probe is None:
            return "HÜKÜM VERİLEMEDİ (probe koşulmadı)", False, []
        if probe.baseline_reachable is False or probe.overall_risk.value == "UNVERIFIED":
            return "HÜKÜM VERİLEMEDİ — hedefe ulaşılamadı (ağ/erişim durumu; suçlama değil)", False, []
        blocked = [s.bot_name for s in probe.bot_statuses
                   if s.is_waf_blocked or s.is_cloudflare_challenge or not s.is_accessible]
        total = probe.total_probed or len(MiniProbe.MICRO_BOTS)
        acc = total - len(blocked)
        if blocked:
            return f"{len(blocked)}/{total} örnek bot ENGELLİ: " + ", ".join(blocked), True, blocked
        return f"{acc}/{total} örnek bot erişebiliyor", True, []

    # ------------------------------------------------------------- koruma + IO
    @classmethod
    def _rejected(cls, host: str, reason: str) -> MiniProbeResult:
        return MiniProbeResult(domain=host, robots_line=f"{_UNMEASURED} (taranmadı)",
                               llms_line=f"{_UNMEASURED} (taranmadı)", bots_line=reason,
                               blocked_bots=[], probed=0, verdict="GİRİŞ REDDEDİLDİ", measured=False)

    @staticmethod
    def _bad_ip(ip) -> bool:
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)

    @classmethod
    async def _is_internal(cls, host: str) -> bool:
        def check() -> bool:
            """robots/llms/bot erişimini denetler."""
            lit = host.strip("[]").rstrip(".")
            if lit == "localhost" or lit.endswith(".localhost") or lit.endswith(".local"):
                return True
            try:
                return cls._bad_ip(ipaddress.ip_address(lit))
            except ValueError:
                logger.debug("literal-IP ayrışmadı, domain yolunda değerlendiriliyor")
            try:
                infos = socket.getaddrinfo(lit, None)
            except OSError:
                return False  # çözümsüz DNS bir SSRF değildir; probe kendi dürüst hükmünü verecek
            for *_rest, addr in infos:
                try:
                    ip = ipaddress.ip_address(addr[0])
                except ValueError:
                    return True
                if cls._bad_ip(ip):
                    return True
            return False
        return await asyncio.to_thread(check)

    @classmethod
    async def _fetch_text(cls, url: str, timeout_sec: float = 6.0) -> Tuple[Optional[int], Optional[str]]:
        try:
            async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AnswRank-MiniProbe/1.0)"})
                if resp.status_code == 200:
                    return 200, resp.text
                return resp.status_code, None
        except httpx.HTTPError:
            return None, None

    @classmethod
    async def probe(cls, url: str, timeout_sec: float = 6.0) -> WAFProbeResult:
        """Bot erişim örnekleme sondası yürütür."""
        return await WAFProbeEngine.probe_url(url, timeout_sec=timeout_sec, bots=cls.MICRO_BOTS)
