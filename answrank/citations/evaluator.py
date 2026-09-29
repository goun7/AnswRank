"""Evaluator for extracting brand citations, rankings, and competitor mentions from LLM responses."""

import re

from answrank.textnorm import netloc
from typing import List, Optional, Tuple

class CitationEvaluator:
    """Evaluates raw LLM responses to determine brand visibility and citation rankings."""

    def evaluate(
        self,
        raw_response: str,
        brand_name: str,
        domain: str,
        known_competitors: Optional[List[str]] = None,
    ) -> Tuple[bool, bool, Optional[int], List[str]]:
        """
        Returns:
            (brand_mentioned, domain_cited, cited_rank, competitors_cited)
        """
        if not raw_response:
            return False, False, None, []

        norm_response = raw_response.lower()
        norm_brand = brand_name.lower()
        clean_domain = netloc(domain)

        # 1. Brand name mentioned — PROSE ONLY, word-boundary only.
        # Link targets are scored by the domain rule below; matching the brand in
        # raw text (incl. URLs) let a fictional placeholder like
        # "rakip-a.example" count as a citation for a brand literally named
        # "Example" (BRGEO-class substring artifact, found in 16 Eyl user-eyes smoke).
        prose = re.sub(r"\(https?://[^\s)]+\)|https?://\S+", " ", raw_response).lower()
        brand_pattern = rf"\b{re.escape(norm_brand)}\b"
        brand_mentioned = bool(re.search(brand_pattern, prose))

        # 2. Domain cited as source link or markdown link
        domain_pattern = rf"\b{re.escape(clean_domain)}\b"
        domain_cited = bool(re.search(domain_pattern, norm_response))

        # 3. Citation rank detection
        # Look for markdown citation brackets like [1], [2] or numbered list items
        cited_rank = None
        if brand_mentioned or domain_cited:
            lines = raw_response.splitlines()
            for idx, line in enumerate(lines, 1):
                if norm_brand in line.lower() or clean_domain in line.lower():
                    # Check for numbered list prefix like "1. ", "2) "
                    match = re.match(r"^\s*(\d+)[\.\)]\s+", line)
                    if match:
                        cited_rank = int(match.group(1))
                    else:
                        cited_rank = min(idx, 5)
                    break

        # 4. Competitor citations
        competitors_found = []
        if known_competitors:
            for comp in known_competitors:
                clean_comp = comp.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/").lower()
                if clean_comp in norm_response:
                    competitors_found.append(comp)

        # Also extract any other domain patterns in markdown links: [Title](https://...)
        urls = re.findall(r"https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})", raw_response)
        for u in urls:
            u_lower = u.lower()
            if clean_domain not in u_lower and u_lower not in ["google.com", "bing.com", "openai.com", "perplexity.ai"]:
                if u_lower not in competitors_found:
                    competitors_found.append(u_lower)

        return brand_mentioned, domain_cited, cited_rank, competitors_found[:5]

    def evaluate_with_sentiment(
        self,
        raw_response: str,
        brand_name: str,
        domain: str,
        sector: str = "general",
        known_competitors: Optional[List[str]] = None,
    ):
        """Extended evaluation returning citation metrics plus brand safety sentiment analysis."""
        from answrank.citations.sentiment import SentimentAnalyzer
        brand_mentioned, domain_cited, cited_rank, competitors = self.evaluate(
            raw_response=raw_response,
            brand_name=brand_name,
            domain=domain,
            known_competitors=known_competitors,
        )
        analyzer = SentimentAnalyzer()
        sentiment = analyzer.analyze(
            raw_response=raw_response,
            brand_name=brand_name,
            domain=domain,
            sector=sector,
        )
        return brand_mentioned, domain_cited, cited_rank, competitors, sentiment
