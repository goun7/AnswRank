"""Brand Entity Coherence, NAP consistency, and Knowledge Graph Analyzer."""

import re
from bs4 import BeautifulSoup

from answrank.textnorm import core_label
from typing import List
from answrank.models import EntityScore

class EntityAnalyzer:
    """Evaluates brand identity, NAP (Name, Address, Phone), and Knowledge Graph sameAs links."""

    def analyze(self, soup: BeautifulSoup, domain: str) -> EntityScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        score = 0
        details = []

        raw_text = soup.get_text(separator=" ", strip=True)

        # 1. Brand Name Coherence (+3 pts)
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else ""
        domain_core = core_label(domain)

        # Normalize Turkish chars for matching
        def normalize_text(t: str) -> str:
            """Metni Türkçe-aware küçük harfe çevirir ve normalize eder."""
            tr_map = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iigguussoocc")
            return t.translate(tr_map).lower()

        norm_title = normalize_text(title_text)
        norm_domain = normalize_text(domain_core)
        
        # Check if domain tokens match title or vice versa
        brand_found = norm_domain in norm_title.replace(" ", "") or any(
            len(part) >= 4 and part in norm_domain for part in norm_title.split()
        )
        if brand_found:
            score += 3
            details.append(f"Marka adı başlık ve alan adıyla tutarlı ('{domain_core}', +3 puan).")
        else:
            score += 1
            details.append("Marka adı başlıkta belirgin değil (+1/3 puan).")

        # 2. Phone presence (+2 pts)
        phone_pattern = r"(?:\+90\s*|0)?\s*(?:\(?\d{3,4}\)?|\d{3,4})[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}"
        has_phone = bool(re.search(phone_pattern, raw_text)) or bool(soup.find("a", href=lambda h: h and h.startswith("tel:")))
        if has_phone:
            score += 2
            details.append("Doğrulanmış iletişim telefonu / tıkla-ara bağlantısı mevcut (+2 puan).")
        else:
            details.append("Doğrulanabilir telefon bilgisi tespit edilemedi (0/2 puan).")

        # 3. Address presence (+2 pts)
        address_keywords = ["cad.", "cadde", "sok.", "sokak", "mah.", "mahallesi", "no:", "kat:", "ilçe", "istanbul", "ankara", "izmir", "bursa", "antalya"]
        has_address = any(k in raw_text.lower() for k in address_keywords) or bool(soup.find("address"))
        if has_address:
            score += 2
            details.append("Fiziki adres / konum bilgisi sayfada mevcut (+2 puan).")
        else:
            details.append("Fiziki lokasyon ve adres bilgisi eksik (0/2 puan).")

        # 4. sameAs Knowledge Graph Links (+3 pts)
        kg_domains = [
            "wikipedia.org", "wikidata.org", "maps.google.com", "google.com/maps",
            "linkedin.com", "instagram.com", "crunchbase.com", "facebook.com", "youtube.com"
        ]
        found_links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            for kg in kg_domains:
                if kg in href and href not in found_links:
                    found_links.append(href)

        if len(found_links) >= 3:
            score += 3
            details.append(f"Zengin Bilgi Grafiği ve sosyal otorite bağlantıları ({len(found_links)} profil, +3 puan).")
        elif len(found_links) >= 1:
            score += 2
            details.append(f"Temel dış profil bağlantıları mevcut ({len(found_links)} link, +2/3 puan).")
        else:
            details.append("sameAs ve dış güven kaynağı bağlantıları eksik (0/3 puan).")

        return EntityScore(
            score=min(10, score),
            brand_name_found=brand_found,
            has_phone=has_phone,
            has_address=has_address,
            has_same_as_links=len(found_links) > 0,
            same_as_links=found_links,
            details=details,
        )
