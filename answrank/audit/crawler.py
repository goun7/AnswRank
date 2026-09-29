"""Crawler module for fetching web pages, robots.txt, llms.txt, with Headless SPA & Playwright Fallback."""

import re
import json
import logging
import httpx
from urllib.parse import urlparse, urljoin
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
from answrank.config import settings
from answrank.audit.cache import asset_cache

logger = logging.getLogger("answrank.crawler")


class CrawlData:
    """Holds fetched web assets for analysis."""
    def __init__(
        self,
        url: str,
        domain: str,
        html_content: str,
        status_code: int,
        headers: Dict[str, str],
        robots_txt: Optional[str] = None,
        llms_txt: Optional[str] = None,
        llms_full_txt: Optional[str] = None,
        is_https: bool = True,
        response_time_ms: float = 0.0,
        is_spa_hydrated: bool = False,
        headless_rendered: bool = False,
        fetch_warnings: Optional[List[str]] = None,
    ):
        self.url = url
        self.domain = domain
        self.html_content = html_content
        self.status_code = status_code
        self.headers = headers
        self.robots_txt = robots_txt
        self.llms_txt = llms_txt
        self.llms_full_txt = llms_full_txt
        self.is_https = is_https
        self.response_time_ms = response_time_ms
        self.is_spa_hydrated = is_spa_hydrated
        self.headless_rendered = headless_rendered
        # Non-fatal collection issues (e.g. transient network errors) recorded so
        # a failed fetch is never silently reported downstream as "asset absent".
        self.fetch_warnings: List[str] = fetch_warnings or []


class HeadlessRenderer:
    """Intelligently detects Single Page Applications (React, Next.js, Vue, Wix) and executes headless DOM hydration."""

    SPA_INDICATORS = [
        r'<div\s+id=["\']root["\']\s*>\s*</div>',
        r'<div\s+id=["\']__next["\']\s*>\s*</div>',
        r'<app-root\b[^>]*>\s*</app-root>',
        r'<noscript>[^<]*?(?:enable\s+javascript|javascript\s+is\s+required)[^<]*?</noscript>',
    ]

    @classmethod
    def is_spa_stub(cls, html_content: str) -> bool:
        """Determines if HTML is an empty or minimally rendered client-side SPA stub."""
        if not html_content:
            return True

        # Check for explicit empty root containers
        for pattern in cls.SPA_INDICATORS:
            if re.search(pattern, html_content, re.IGNORECASE):
                return True

        # Check body text length
        soup = BeautifulSoup(html_content, "html.parser")
        body = soup.find("body")
        if body:
            text = body.get_text(strip=True)
            if len(text) < 150:
                # If scripts exist but visible text is sparse, it's a client-rendered stub
                scripts = soup.find_all("script", src=True)
                if len(scripts) >= 2:
                    return True

        return False

    @classmethod
    async def render_playwright(cls, url: str, timeout_ms: int = 5000) -> Optional[str]:
        """Runs headless Chromium via Playwright to fetch the hydrated DOM."""
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    user_agent=settings.user_agent,
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                content = await page.content()
                await browser.close()
                return content
        except Exception as exc:
            # Graceful degradation (no Playwright / render timeout) — but recorded,
            # never swallowed silently: operators can diagnose via logs.
            logger.debug("Headless render failed for %s: %s", url, exc)
            return None

    @classmethod
    def hydrate_ssr_fallback(cls, html_content: str) -> str:
        """Extracts JSON blobs from __NEXT_DATA__ or state script tags to hydrate missing DOM text."""
        soup = BeautifulSoup(html_content, "html.parser")
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                # Walk JSON to gather all textual strings
                extracted_texts = []
                def _walk(obj):
                    if isinstance(obj, str) and len(obj) > 20:
                        extracted_texts.append(obj)
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            _walk(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _walk(item)
                _walk(data)

                if extracted_texts:
                    synthetic_div = soup.new_tag("div")
                    synthetic_div["id"] = "answrank-hydrated-content"
                    for t in extracted_texts[:30]:
                        p = soup.new_tag("p")
                        p.string = t
                        synthetic_div.append(p)
                    if soup.body:
                        soup.body.append(synthetic_div)
                    return str(soup)
            except Exception as exc:
                # Sessiz yutma borcu kapandı: davranış aynı, kanıt log'da.
                logger.debug("asset cache embed başarısız, özgün html döner: %s", exc)
        return html_content


class WebCrawler:
    """Async web crawler with intelligent AI-bot discovery and Headless JS rendering fallback."""

    def __init__(self, timeout: Optional[float] = None, enable_headless: bool = True):
        self.timeout = timeout or settings.timeout_seconds
        self.enable_headless = enable_headless
        self.headers = {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def fetch(self, url: str) -> CrawlData:
        """Fetches page HTML, robots.txt, and llms.txt with headless fallback for SPAs."""
        parsed = urlparse(url)
        if not parsed.scheme:
            url = f"https://{url}"
            parsed = urlparse(url)

        domain = parsed.netloc
        base_url = f"{parsed.scheme}://{domain}"
        is_https = parsed.scheme == "https"
        warnings: List[str] = []  # transient collection issues, surfaced on CrawlData

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
            verify=True,
        ) as client:
            # 1. Fetch main page via HTTP.
            # P0-1 (16 Eyl user-eyes): unreachable / unsupported-scheme targets are
            # degraded HONESTLY (status_code=0 + DOĞRULANAMADI warning) instead of
            # exploding as HTTP 500 or being scored as an empty — hence "worst" — site.
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                return CrawlData(
                    url=url, domain=domain or (urlparse(url).netloc or url),
                    html_content="", status_code=0, headers={}, is_https=is_https,
                    fetch_warnings=[
                        f"DOĞRULANAMADI: Hedefe ulaşılamadı ({type(exc).__name__}). "
                        "Bu bir ağ/erişim koşuludur; hedef sitenin kusuru ya da ölçülmüş "
                        "düşük skor YANLIŞLAMASI değildir. Skor hesaplanmadı."],
                )
            html_content = response.text
            status_code = response.status_code
            resp_headers = dict(response.headers)
            resp_time = response.elapsed.total_seconds() * 1000

            # 2. Check for SPA stub or Cloudflare challenge and trigger headless fallback
            headless_used = False
            is_hydrated = False

            if self.enable_headless and (HeadlessRenderer.is_spa_stub(html_content) or status_code in (403, 503)):
                # Attempt Playwright headless rendering
                rendered = await HeadlessRenderer.render_playwright(url)
                if rendered and len(rendered) > len(html_content):
                    html_content = rendered
                    headless_used = True
                    is_hydrated = True
                    status_code = 200
                else:
                    # Fallback to SSR state extraction
                    hydrated = HeadlessRenderer.hydrate_ssr_fallback(html_content)
                    if hydrated != html_content:
                        html_content = hydrated
                        is_hydrated = True
                    if not is_hydrated:
                        warnings.append(
                            "Sayfa SPA-iskeleti/koruma duvarı izlenimi verdi; hem headless "
                            "render hem SSR hidrasyon başarısız — puanlama kısmi HTML'ye dayanır."
                        )

            # 3. Fetch robots.txt (cached per domain+path, TTL'd — batch audits
            # of N pages on one domain trigger at most one HTTP request)
            async def _fetch_robots() -> Optional[str]:
                try:
                    robots_resp = await client.get(urljoin(base_url, "/robots.txt"))
                    if robots_resp.status_code == 200 and "text" in robots_resp.headers.get("content-type", ""):
                        return robots_resp.text
                except Exception as exc:
                    warnings.append(f"robots.txt ağ hatası nedeniyle doğrulanamadı: {str(exc)[:80]}")
                return None

            robots_txt = await asset_cache.get_or_fetch(
                f"robots:{domain}", _fetch_robots, ttl_seconds=settings.asset_cache_ttl_seconds
            )

            # 4. Fetch llms.txt (cached)
            async def _fetch_llms() -> Optional[str]:
                try:
                    llms_resp = await client.get(urljoin(base_url, "/llms.txt"))
                    if llms_resp.status_code == 200:
                        return llms_resp.text
                except Exception as exc:
                    warnings.append(f"llms.txt ağ hatası nedeniyle doğrulanamadı: {str(exc)[:80]}")
                return None

            llms_txt = await asset_cache.get_or_fetch(
                f"llms:{domain}", _fetch_llms, ttl_seconds=settings.asset_cache_ttl_seconds
            )

            # 5. Fetch llms-full.txt (cached)
            async def _fetch_llms_full() -> Optional[str]:
                try:
                    llms_full_resp = await client.get(urljoin(base_url, "/llms-full.txt"))
                    if llms_full_resp.status_code == 200:
                        return llms_full_resp.text
                except Exception as exc:
                    warnings.append(f"llms-full.txt ağ hatası nedeniyle doğrulanamadı: {str(exc)[:80]}")
                return None

            llms_full_txt = await asset_cache.get_or_fetch(
                f"llmsfull:{domain}", _fetch_llms_full, ttl_seconds=settings.asset_cache_ttl_seconds
            )

            return CrawlData(
                url=url,
                domain=domain,
                html_content=html_content,
                status_code=status_code,
                headers=resp_headers,
                robots_txt=robots_txt,
                llms_txt=llms_txt,
                llms_full_txt=llms_full_txt,
                is_https=is_https,
                response_time_ms=resp_time,
                is_spa_hydrated=is_hydrated,
                headless_rendered=headless_used,
                fetch_warnings=warnings,
            )
