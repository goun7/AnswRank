"""Meta tags, canonical, Open Graph, and heading architecture analyzer."""

from bs4 import BeautifulSoup
from answrank.models import MetaScore

class MetaAnalyzer:
    """Evaluates meta tags, canonical URL, and HTML heading hierarchy."""

    def analyze(self, soup: BeautifulSoup) -> MetaScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        score = 0
        details = []

        # 1. Title tag (+3 pts)
        title_tag = soup.find("title")
        title_text = title_tag.get_text().strip() if title_tag else ""
        has_title = bool(title_text)
        title_len = len(title_text)

        if has_title and 15 <= title_len <= 75:
            score += 3
            details.append(f"Title etiketi ideal uzunlukta ({title_len} karakter, +3 puan).")
        elif has_title:
            score += 1
            details.append(f"Title etiketi mevcut fakat uzunluğu optimize değil ({title_len} karakter, +1/3 puan).")
        else:
            details.append("Title etiketi bulunamadı (0/3 puan).")

        # 2. Meta description (+3 pts)
        desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "description"})
        desc_text = desc_tag.get("content", "").strip() if desc_tag else ""
        has_desc = bool(desc_text)
        desc_len = len(desc_text)

        if has_desc and 50 <= desc_len <= 200:
            score += 3
            details.append(f"Meta description doğrudan cevap veriyor ({desc_len} karakter, +3 puan).")
        elif has_desc:
            score += 1
            details.append(f"Meta description mevcut fakat çok kısa/uzun ({desc_len} karakter, +1/3 puan).")
        else:
            details.append("Meta description etiketi bulunamadı (0/3 puan).")

        # 3. Canonical (+2 pts)
        canonical_tag = soup.find("link", rel=lambda val: val and "canonical" in val.lower())
        has_canonical = bool(canonical_tag and canonical_tag.get("href"))
        if has_canonical:
            score += 2
            details.append("Kanonik URL tanımlanmış (+2 puan).")
        else:
            details.append("Canonical URL eksik (0/2 puan).")

        # 4. Open Graph (+2 pts)
        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")
        has_og = bool(og_title or og_image)
        if has_og:
            score += 2
            details.append("Open Graph etiketleri mevcut (+2 puan).")
        else:
            details.append("Open Graph etiketleri eksik (0/2 puan).")

        # 5. Heading Architecture (+4 pts)
        h1_tags = soup.find_all("h1")
        h1_count = len(h1_tags)
        has_h1 = h1_count >= 1

        if h1_count == 1:
            score += 2
            details.append("Sayfada tam 1 adet net H1 başlığı mevcut (+2 puan).")
        elif h1_count > 1:
            score += 1
            details.append(f"Sayfada birden fazla ({h1_count}) H1 var (+1/2 puan).")
        else:
            details.append("Sayfada H1 başlığı bulunamadı (0/2 puan).")

        h2_tags = soup.find_all("h2")
        h3_tags = soup.find_all("h3")
        has_hierarchy = bool(h2_tags) and bool(h3_tags)
        if has_hierarchy:
            score += 2
            details.append(f"Hiyerarşik başlık düzeni mevcut ({len(h2_tags)} H2, {len(h3_tags)} H3, +2 puan).")
        elif h2_tags:
            score += 1
            details.append("H2 başlıkları mevcut fakat H3 derinliği eksik (+1/2 puan).")
        else:
            details.append("Başlık hiyerarşisi zayıf (0/2 puan).")

        return MetaScore(
            score=min(14, score),
            has_title=has_title,
            title_length=title_len,
            has_meta_description=has_desc,
            description_length=desc_len,
            has_canonical=has_canonical,
            has_open_graph=has_og,
            has_h1=has_h1,
            h1_count=h1_count,
            has_heading_hierarchy=has_hierarchy,
            details=details,
        )
