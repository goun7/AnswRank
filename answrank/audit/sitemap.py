"""Sitemap.xml Crawler & Batch Audit Module (Weakest Pages First)."""

import re
import logging
import xml.etree.ElementTree as ET
import httpx
import asyncio
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from answrank.audit.engine import AuditEngine
from answrank.audit.cache import asset_cache
from answrank.config import settings
from answrank.models import AuditResult

logger = logging.getLogger("answrank.sitemap")

class SitemapAuditor:
    """Fetches sitemap.xml, extracts internal URLs, and batch-audits pages."""

    def __init__(self, engine: Optional[AuditEngine] = None):
        self.engine = engine or AuditEngine()

    async def _fetch_doc(self, doc_url: str, cache_key: str) -> Optional[str]:
        """Fetch one sitemap/sitemapindex document through the shared TTL cache."""
        async def _do_fetch() -> Optional[str]:
            try:
                async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
                    resp = await client.get(doc_url)
                    if resp.status_code == 200:
                        return resp.text
            except Exception as exc:
                logger.warning("Sitemap fetch failed for %s: %s", doc_url, exc)
            return None

        return await asset_cache.get_or_fetch(
            cache_key, _do_fetch, ttl_seconds=settings.asset_cache_ttl_seconds
        )

    @staticmethod
    def _is_index(text: str) -> bool:
        """A sitemap index carries <sitemapindex> instead of <urlset>."""
        return "sitemapindex" in text[:600]

    @staticmethod
    def _extract_locs(text: str) -> List[str]:
        """Extract <loc> entries via XML parse with a regex fallback."""
        out: List[str] = []
        try:
            root = ET.fromstring(text)
            for elem in root.iter():
                if elem.tag.endswith("loc") and elem.text:
                    u = elem.text.strip()
                    if u.startswith("http") and u not in out:
                        out.append(u)
        except Exception:
            for u in re.findall(r"<loc>(https?://[^<]+)</loc>", text):
                if u not in out:
                    out.append(u)
        return out

    async def fetch_sitemap_urls(self, base_url: str, max_urls: int = 15) -> List[str]:
        """Parses sitemap.xml and returns up to max_urls page URLs.

        Handles both a flat <urlset> sitemap and a <sitemapindex> that points
        to child sitemaps (the index is expanded one level; children are
        fetched through the same TTL asset cache).
        """
        parsed = urlparse(base_url)
        sitemap_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/sitemap.xml")

        text = await self._fetch_doc(sitemap_url, f"sitemap:{parsed.netloc}")

        urls: List[str] = []
        if text:
            if self._is_index(text):
                # Index: expand each referenced child sitemap (bounded).
                child_urls = self._extract_locs(text)[:10]
                for child in child_urls:
                    child_parsed = urlparse(child)
                    child_text = await self._fetch_doc(
                        child, f"sitemap:{child_parsed.netloc}:{child}"
                    )
                    if child_text:
                        for u in self._extract_locs(child_text):
                            if u not in urls:
                                urls.append(u)
                    if len(urls) >= max_urls:
                        break
            else:
                urls = self._extract_locs(text)

        # If sitemap was not reachable or empty, fallback to base URL
        if not urls:
            urls = [base_url]

        return urls[:max_urls]

    async def batch_audit(
        self,
        base_url: str,
        sector: str = "general",
        max_urls: int = 10,
        concurrency: int = 3,
    ) -> List[AuditResult]:
        """Audits all pages in sitemap concurrently, sorted by score ascending (weakest first)."""
        urls = await self.fetch_sitemap_urls(base_url, max_urls=max_urls)
        results: List[AuditResult] = []
        semaphore = asyncio.Semaphore(concurrency)

        async def _audit_single(url: str):
            async with semaphore:
                try:
                    res = await self.engine.audit_url(url, sector=sector)
                    results.append(res)
                except Exception as exc:
                    logger.warning("Batch audit failed for %s: %s", url, exc)

        tasks = [_audit_single(u) for u in urls]
        await asyncio.gather(*tasks)

        # Sort weakest pages first (lowest score first)
        results.sort(key=lambda r: r.overall_score)
        return results
