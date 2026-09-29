"""Content Citability, Statistics Density, and RAG Chunking Analyzer (Princeton GEO Framework)."""

import re
from bs4 import BeautifulSoup
from answrank.models import CitabilityScore

class CitabilityAnalyzer:
    """Evaluates content factors that trigger generative engine citations."""

    def analyze(self, soup: BeautifulSoup) -> CitabilityScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        score = 0
        details = []

        # Extract text body excluding scripts/styles
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        words = re.findall(r"\b\w+\b", text)
        word_count = len(words)

        # 1. Statistics and Quantitative Data (+3 pts)
        # Princeton KDD 2024: Statistics addition increases citation by +40%
        numbers_pattern = r"(?:\d+(?:[.,]\d+)?%|\b\d{1,3}(?:[.,]\d{3})*(?:\s*(?:TL|₺|\$|€|yıl|ay|gün|adet|hasta|vaka|oran))|\b\d{2,}\b)"
        stats_matches = re.findall(numbers_pattern, text, re.IGNORECASE)
        stats_count = len(stats_matches)
        has_stats = stats_count >= 5

        if stats_count >= 5:
            score += 3
            details.append(f"Zengin sayısal veri ve istatistik yoğunluğu ({stats_count} tespit, +3 puan - Princeton GEO faktörü).")
        elif stats_count >= 2:
            score += 2
            details.append(f"Orta düzeyde istatistiki veri mevcut ({stats_count} adet, +2/3 puan).")
        else:
            details.append("Sayısal veri ve istatistiki gösterge eksikliği (0/3 puan).")

        # 2. Quotations and Explicit Attribution (+3 pts)
        # Princeton KDD 2024: Quotation addition increases citation by +41%
        quotes_pattern = r'["“»].{10,120}["”«]|(?:göre|belirtmektedir|uzmanına göre|dr\.|hekim)'
        quote_matches = re.findall(quotes_pattern, text, re.IGNORECASE)
        has_quotes = len(quote_matches) >= 1

        if has_quotes:
            score += 3
            details.append("Doğrudan alıntı ve uzman referans ifadeleri mevcut (+3 puan).")
        else:
            details.append("Doğrudan alıntı veya uzman atfı bulunamadı (0/3 puan).")

        # 3. Tables or Bulleted Lists (+3 pts)
        # RAG retrievers preferentially chunk structured markdown/lists
        lists = soup.find_all(["ul", "ol", "table"])
        has_tables_lists = len(lists) >= 1

        if len(lists) >= 2:
            score += 3
            details.append(f"Yapılandırılmış liste ve tablolar mevcut ({len(lists)} adet, +3 puan).")
        elif len(lists) >= 1:
            score += 2
            details.append("Temel liste yapısı mevcut (+2/3 puan).")
        else:
            details.append("Maddeleme veya karşılaştırma tablosu yok (0/3 puan).")

        # 4. Front-Loading Direct Answer (First 50 words) (+3 pts)
        # Inverted pyramid rule: LLM extractors look at top chunk for direct answers
        first_p = soup.find("p")
        first_p_text = first_p.get_text(strip=True) if first_p else ""
        first_p_words = len(re.findall(r"\b\w+\b", first_p_text))
        is_front_loaded = (first_p_words >= 8) and any(w in first_p_text.lower() for w in ["için", "olan", "hizmet", "uzman", "tedavi", "kliniği", "danışmanlık"])

        if is_front_loaded:
            score += 3
            details.append("Ters piramit kuralı: İlk paragrafta doğrudan cevap ve tanım yer alıyor (+3 puan).")
        else:
            details.append("Ters piramit eksik: Giriş paragrafı doğrudan yanıt vermek yerine genel kalıyor (0/3 puan).")

        return CitabilityScore(
            score=min(12, score),
            word_count=word_count,
            has_statistics=has_stats,
            statistics_count=stats_count,
            has_quotations=has_quotes,
            has_tables_or_lists=has_tables_lists,
            front_loading_direct_answer=is_front_loaded,
            rag_chunk_friendly=has_tables_lists and has_stats,
            details=details,
        )
