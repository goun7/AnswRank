"""Negative Signals, Spam, Keyword Stuffing, and Manipulation Filter Analyzer."""

import re
from bs4 import BeautifulSoup
from answrank.models import NegativeScore

class NegativeAnalyzer:
    """Detects anti-citation signals that cause LLMs to penalize or ignore a domain."""

    def analyze(self, soup: BeautifulSoup) -> NegativeScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        score = 6
        details = []
        penalties = 0

        text = soup.get_text(separator=" ", strip=True)
        words = re.findall(r"\b\w+\b", text)
        word_count = len(words)

        # 1. Thin content check (< 150 words)
        no_thin = word_count >= 150
        if not no_thin:
            score -= 2
            penalties += 2
            details.append(f"İnce içerik (Thin Content) uyarısı: Sayfada yalnızca {word_count} kelime var (-2 ceza puanı).")
        else:
            details.append("Yeterli içerik hacmi mevcut (+2 puan).")

        # 2. Keyword Stuffing Detection
        # Check if single word frequency > 5% of total text
        word_freq = {}
        for w in words:
            w_lower = w.lower()
            if len(w_lower) > 4:
                word_freq[w_lower] = word_freq.get(w_lower, 0) + 1

        is_stuffed = False
        stuffed_words = []
        if word_count > 100:
            for w, count in word_freq.items():
                ratio = count / word_count
                if ratio > 0.06:
                    is_stuffed = True
                    stuffed_words.append(f"{w} ({count} kez, %{ratio*100:.1f})")

        no_stuffing = not is_stuffed
        if is_stuffed:
            score -= 2
            penalties += 2
            details.append(f"Anahtar kelime yığma (Keyword Stuffing) şüphesi: {', '.join(stuffed_words[:3])} (-2 ceza puanı).")
        else:
            details.append("Doğal anahtar kelime dağılımı (+2 puan).")

        # 3. Prompt Injection / Hidden Manipulation Patterns
        # Detect patterns like "ignore previous instructions", "system prompt", display:none text hacks
        raw_html = str(soup)
        injection_patterns = [
            r"ignore\s+(?:all\s+)?previous\s+instructions",
            r"you\s+are\s+a\s+helpful\s+assistant",
            r"system\s*:\s*always\s+recommend",
            r"font-size:\s*0px",
            r"display:\s*none;[^>]*>.*?en\s+iyi",
        ]
        has_injection = any(re.search(pat, raw_html, re.IGNORECASE) for pat in injection_patterns)

        no_injection = not has_injection
        if has_injection:
            score -= 4
            penalties += 4
            details.append("Tehlikeli manipülasyon / prompt injection kalıbı tespit edildi (-4 ceza puanı).")
        else:
            details.append("Gizli manipülasyon veya prompt injection kalıntısı yok (+2 puan).")

        # 4. Unsupported authority claims — information-distorting GEO
        # Counter-GEO-Bench (EMNLP 2026, arXiv:2609.02316): normal görünen
        # GEO-optimize belgeler hedefli yanlış bilgi yayar; standart guardrail'ler
        # %5.7'den az azaltır çünkü tehdit akıcı bilgi içeriği olarak geçer.
        # Desteksiz üstünlük iddiaları en yüksek riskli örüntüdür.
        authority_patterns = [
            r"\ben\s+iyi\b",
            r"\blider\b",
            r"\btek\b\s+(?:uzman|adres|çözüm|seçim|seçenek)",
            r"\bbir\s+numara\b",
            r"\b1\s*\.?\s*sırad[ai]\b",
            r"\ben\s+(?:çok\s+)?tercih\s+edilen\b",
            r"\ben\s+güvenilir\b",
        ]
        found = []
        for pat in authority_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                found.append(m.group(0))
        has_authority = len(found) >= 2

        if has_authority:
            score -= 2
            penalties += 2
            details.append(
                "Desteksiz üstünlük iddiası (information-distorting GEO riski): "
                f"{', '.join(sorted(set(found))[:3])} — kanıtlanmış müşteri sonucu veya "
                "üçüncü-parti sertifika olmadan kullanılıyor (-2 ceza puanı). "
                "(Counter-GEO-Bench, EMNLP 2026)")
        else:
            details.append("Desteksiz üstünlük iddiası yok; iddialar ölçülü (+2 puan).")

        final_score = max(0, min(6, score))

        return NegativeScore(
            score=final_score,
            no_intrusive_popups=True,
            no_keyword_stuffing=no_stuffing,
            no_thin_content=no_thin,
            no_prompt_injection_patterns=no_injection,
            no_unsupported_authority_claims=not has_authority,
            has_unsupported_authority_claims=has_authority,
            penalty_points=penalties,
            details=details,
        )
