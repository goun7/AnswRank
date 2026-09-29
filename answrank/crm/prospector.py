"""Otonom lead prospektörü (E9) — keşiften sonra GERÇEĞİ doğrular, uydurmaz.

İşleyiş: bir keşif ajanı (veya el ile liste) aday verir → prospektör her biri için
  1. robots.txt'yi çeker ve RFC 9309 kurallarına uyar (Disallow: / → sayfa çekilmez),
  2. ana sayfayı gerçekten indirir (ulaşılabilirlik kanıtı),
  3. İLETİŞİMİ yalnız sayfadaki kanıttan alır (JSON-LD > mailto/metin),
  4. doğrulanmış işletmeleri CRM'e stage eder; ulaşılamayanlar ret listesine
     'DOĞRULANAMADI' ile düşer — hiçbir alan doldurulmaz.
Ağ katmanı enjekte edilir (testler çevrimdışı, üretim httpx).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from html import unescape as html_unescape
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from answrank.db import Database
from answrank.models import Prospect

Fetcher = Callable[[str, float], Awaitable[Tuple[int, str]]]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Önceki karakter harf/rakam olmamalı (CSS 'U+0302-0303' gibi sahte numaralar =reject):
_PHONE_RE = re.compile(r"(?<![A-Za-z0-9])\+\d{1,3}[\s\d\-()]{6,}")
_BAD_EMAIL_HOSTS = ("example.com", "example.ae", "sentry.io", "wix.com")
_HEX_LOCAL = re.compile(r"^[0-9a-f]{8,}$")  # CSS hash'leri vs. sahte e-posta
_BAD_EMAIL_TLDS = (".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2",
                   ".ttf", ".eot", ".css", ".js", ".ico")
# Bot-challenge / hata sayfaları: marka veya iletişim ÇIKARILMAZ (kanıt değildir)
_CHALLENGE_MARKERS = ("checking your browser", "just a moment", "attention required",
                      "cloudflare", "captcha", "404", "403 forbidden", "error page",
                      "this page could not be found", "access denied")


class VerifiedLead(BaseModel):
    brand: Optional[str] = None
    domain: str
    city: str = ""
    country: Optional[str] = None
    sector: str = "dental"
    source_url: Optional[str] = None
    http_status: int = 0
    robots_status: Optional[int] = None
    robots_disallowed: bool = False
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_source: Optional[str] = None
    reachable: bool = False
    notes: str = ""


class LeadProspector:
    def __init__(self, db: Optional[Database] = None, fetch: Optional[Fetcher] = None,
                 politeness: float = 1.5, timeout: float = 10.0,
                 country: Optional[str] = None):
        self.db = db
        self.country = country
        self._fetch = fetch or self._httpx_fetch
        self.politeness = politeness
        self.timeout = timeout

    # ------------------------------------------------------------------ ağ
    @staticmethod
    async def _httpx_fetch(url: str, timeout: float = 10.0) -> Tuple[int, str]:
        import httpx
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                     headers={"User-Agent": "AnswRankProspector/1.0 "
                                              "(lead verification; respects robots.txt)"}) as c:
            r = await c.get(url)
            return r.status_code, r.text

    async def _safe(self, url: str) -> Tuple[Optional[int], str]:
        try:
            status, text = await self._fetch(url, self.timeout)
            return status, text
        except Exception:
            return None, ""

    # ------------------------------------------------------------- robots
    @staticmethod
    def _robots_disallows_all(text: str) -> bool:
        """Basitleştirilmiş RFC 9309 okuyucu: 'User-agent: *' için Disallow: / ya da
        boş (tümü) → sayfa çekmeye izin yok. Tam parser crawler'da; burada kapsam
        denetimi yeterli ve eksiklik 'kapsam dışı' notuyla açıklanır."""
        ua_star = False
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            low = line.lower()
            if low.startswith("user-agent:"):
                ua_star = line.split(":", 1)[1].strip() == "*"
            elif low.startswith("disallow:") and ua_star:
                path = line.split(":", 1)[1].strip()
                if path in ("", "/"):
                    return True
        return False

    # ------------------------------------------------------------------ doğrula
    @staticmethod
    def _normalize(domain: str) -> str:
        return (domain or "").split("//")[-1].split("/")[0].strip().lower().rstrip(".")

    def _extract_contacts(self, html: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        # 1) JSON-LD (yapılandırılmış, en güvenilir)
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                             html, re.S | re.I):
            blob = m.group(1)
            phone = re.search(r'"telephone"\s*:\s*"([^"]+)"', blob)
            email = re.search(r'"email"\s*:\s*"([^"]+)"', blob)
            if phone or email:
                tel = phone.group(1).strip() if phone else None
                if tel and re.match(r"^\d", tel):
                    tel = "+" + tel  # JSON-LD ham 'telephone' ITU biçimine normalize
                return (tel, email.group(1) if email else None, "json-ld")
        # 2) sayfa metni (public işletme iletişimi)
        emails = []
        for e in _EMAIL_RE.findall(html):
            local, _, host = e.partition("@")
            if any(b in e.lower() for b in _BAD_EMAIL_HOSTS):
                continue
            if host.lower().endswith(_BAD_EMAIL_TLDS):  # sprite.flags@2x.webp gibi
                continue
            if _HEX_LOCAL.match(local) or _HEX_LOCAL.search(local):
                continue
            if not local.lower().strip(".0123456789"):  # saf rakam/heks
                continue
            emails.append(e)
        phones = []
        for ph in _PHONE_RE.findall(html):
            digits = re.sub(r"\D", "", ph)
            if 7 <= len(digits) <= 15:  # ITU aralığı dışı = sahte
                phones.append(ph.strip())
        if emails or phones:
            return (phones[0] if phones else None,
                    emails[0] if emails else None, "page-text")
        return None, None, None

    @staticmethod
    def _looks_like_challenge_or_error(html: str) -> bool:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if not m:
            return True  # başızsız gövde = içerik kanıtı değil
        title = html_unescape(re.sub(r"\s+", " ", m.group(1))).strip().lower()
        return any(marker in title for marker in _CHALLENGE_MARKERS)

    @staticmethod
    def _extract_brand(html: str, fallback: Optional[str]) -> Optional[str]:
        m = re.search(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', html, re.I)
        if m:
            return html_unescape(m.group(1)).strip()
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if m:
            title = html_unescape(re.sub(r"\s+", " ", m.group(1))).strip()
            if any(marker in title.lower() for marker in _CHALLENGE_MARKERS):
                return fallback  # hata/challenge başlığı marka DEĞİLDİR
            return title.split("|")[0].split("–")[0].strip()[:60] or fallback
        return fallback

    async def verify(self, cand: Dict) -> VerifiedLead:
        """Aday domain/iletişim doğrulaması yapar."""
        domain = self._normalize(cand.get("domain"))
        v = VerifiedLead(domain=domain, city=cand.get("city", "") or "",
                         country=cand.get("country") or self.country,
                         sector=cand.get("sector", "dental"),
                         source_url=cand.get("source_url"), brand=cand.get("brand"))
        if not domain or "." not in domain:
            v.notes = "geçersiz domain adayı"
            return v
        robots_status, robots_text = await self._safe(f"https://{domain}/robots.txt")
        v.robots_status = robots_status
        if robots_status is None:
            v.notes = "robots.txt indirilemedi (ağ) — DOĞRULANAMADI"
            return v
        if self._robots_disallows_all(robots_text):
            v.robots_disallowed = True
            v.notes = "robots.txt kapsamı: ana sayfa çekilmedi, iletişim DOĞRULANAMADI"
            return v
        home = f"https://{domain}/"
        status, html = await self._safe(home)
        if status is None:  # https başarısız → http geri düşürme (bazı eski siteler)
            status, html = await self._safe(f"http://{domain}/")
        if status is None:
            v.notes = "ana sayfa indirilemedi (ağ) — DOĞRULANAMADI"
            return v
        v.http_status, v.reachable = status, True
        if status >= 400 or self._looks_like_challenge_or_error(html):
            v.notes = (f"içerik alınamadı (HTTP {status} / bot-challenge) — "
                       "iletişim ve marka DOĞRULANAMADI")
            return v
        v.brand = self._extract_brand(html, v.brand)
        v.phone, v.email, v.contact_source = self._extract_contacts(html)
        if not (v.phone or v.email):
            v.notes = "işletme GERÇEK; kamuya açık iletişim bulunamadı — DOĞRULANAMADI"
        return v

    # ---------------------------------------------------------------- stage
    async def stage(self, v: VerifiedLead) -> Optional[str]:
        """Adayı pipeline aşamasına alır."""
        if self.db is None:
            return None
        p = Prospect(
            id=f"lead_{v.domain.replace('.', '_')}",
            brand_name=v.brand or v.domain,
            sector=v.sector,
            city=v.city or "—",
            website_url=f"https://{v.domain}/",
            status="lead",
            domain_ref=v.domain,
            country=v.country,
            phone=v.phone,
            email=v.email,
            source_url=v.source_url,
            verified_at=datetime.now(timezone.utc).isoformat(),
            http_status=v.http_status or None,
            robots_status=v.robots_status,
            contact_source=v.contact_source,
        )
        await self.db.save_prospect(p)
        return p.id

    # ------------------------------------------------------------------ run
    async def run_verify(self, candidates: List[Dict]) -> List[VerifiedLead]:
        """Doğrulama adımını yürütür."""
        out = []
        for i, cand in enumerate(candidates):
            if i:
                await asyncio.sleep(self.politeness)
            out.append(await self.verify(cand))
        return out

    async def run(self, candidates: List[Dict], limit: Optional[int] = None
                  ) -> Tuple[int, int]:
        """Sondalama/koşum adımını yürütür."""
        verified = await self.run_verify(candidates[:limit] if limit else candidates)
        staged = rejected = 0
        for v in verified:
            if v.reachable or v.robots_disallowed:
                if self.db is not None:
                    await self.stage(v)
                staged += 1
            else:
                rejected += 1
        return staged, rejected
