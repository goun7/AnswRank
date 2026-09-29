"""Trust Stack, Security, Freshness, and Server-Side Rendering Accessibility Analyzer."""

from bs4 import BeautifulSoup
from answrank.models import TrustScore

class TrustAnalyzer:
    """Evaluates security, content freshness, legal compliance, E-E-A-T and SSR accessibility."""

    # 2026 kanıtı: AI Overview atıflarının ~%96'sı güçlü E-E-A-T sinyali olan
    # kaynaklardan gelir (Wellows 2.400 atıf incelemesi / Bowen GEO Index 2026);
    # E-E-A-T nudge değil ikili bir kapıdır. Yazar/uzmanlık işaretleri ölçülür.
    _EEAT_KEYWORDS = ("uzman", "docent", "profesor", "uzmani", "doktor",
                      "sertifik", "accredit", "deneyim", "klinik", "hekim")

    def analyze(self, soup: BeautifulSoup, is_https: bool) -> TrustScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        score = 0
        details = []

        # 1. HTTPS Security (+2 pts)
        if is_https:
            score += 2
            details.append("HTTPS SSL/TLS güvenliği aktif (+2 puan).")
        else:
            details.append("Güvensiz HTTP bağlantısı (0/2 puan).")

        # 2. Freshness & dateModified (+1 pt)
        date_meta = soup.find("meta", attrs={"property": lambda v: v and "modified_time" in v}) or \
                    soup.find("meta", attrs={"name": lambda v: v and "modified" in v}) or \
                    soup.find("time")
        has_date = bool(date_meta)
        if has_date:
            score += 1
            details.append("İçerik tazelik göstergesi (dateModified / time) tanımlı (+1 puan).")
        else:
            details.append("dateModified meta verisi eksik; modeller içeriğin eskidiğini düşünebilir (0/1 puan).")

        # 3. Privacy Policy / Legal Pages (+1 pt)
        legal_keywords = ["gizlilik", "kvkk", "aydinlatma", "privacy", "terms", "sozlesme", "kullanim"]
        has_legal = bool(soup.find("a", href=lambda h: h and any(k in h.lower() for k in legal_keywords)))
        if has_legal:
            score += 1
            details.append("Gizlilik / KVKK yasal metin bağlantısı mevcut (+1 puan).")
        else:
            details.append("KVKK / Gizlilik politikası bağlantısı eksik (0/1 puan).")

        # 4. SSR Accessibility (+1 pt)
        # Check if meaningful body text exists without requiring JS
        body = soup.find("body")
        body_text = body.get_text(strip=True) if body else ""
        is_ssr = len(body_text) > 300
        if is_ssr:
            score += 1
            details.append("Sayfa içeriği JavaScript gerektirmeksizin (SSR) taranabiliyor (+1 puan).")
        else:
            details.append("Sayfa metni zayıf veya tamamen Client-Side Render (CSR) bağımlı (0/1 puan).")

        # 5. E-E-A-T authorship & expertise signals (+1 pt)
        author_meta = soup.find("meta", attrs={"name": "author"})
        schema_author = soup.find("span", attrs={"itemprop": "author"}) or \
                        soup.find(rel="author")
        # Türkçe için lower() yetersiz (İ/ı); koşulsuz eşleştirme yapılır
        body_fold = body_text.replace("İ", "i").replace("I", "ı").lower()
        has_eeat = bool(author_meta) or bool(schema_author) or \
            any(k in body_fold for k in self._EEAT_KEYWORDS)
        if has_eeat:
            score += 1
            details.append("E-E-A-T yazar/uzmanlık sinyali mevcut (+1 puan).")
        else:
            details.append("E-E-A-T uyarısı: yazar/uzmanlık sinyali bulunamadı — 2026 "
                           "verilerine göre AI atıflarının ~%96'sı güçlü E-E-A-T sinyali "
                           "olan kaynaklardan gelir; bu eksiklik atıf kapısı riskidir (0/1 puan).")

        return TrustScore(
            score=min(6, score),
            is_https=is_https,
            has_date_modified=has_date,
            has_privacy_policy=has_legal,
            has_eeat_signals=has_eeat,
            is_ssr_accessible=is_ssr,
            details=details,
        )
