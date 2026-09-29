"""llms.txt and llms-full.txt presence and standard compliance analyzer."""

import re
from typing import Optional
from answrank.models import LlmsTxtScore

class LlmsTxtAnalyzer:
    """Evaluates presence, syntax, and depth of llms.txt standard files."""

    def analyze(self, llms_txt: Optional[str], llms_full_txt: Optional[str]) -> LlmsTxtScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        if not llms_txt or not llms_txt.strip():
            return LlmsTxtScore(
                score=0,
                has_llms_txt=False,
                has_llms_full_txt=False,
                has_h1_title=False,
                has_blockquote_summary=False,
                has_structured_sections=False,
                word_count=0,
                details=["/llms.txt dosyası bulunamadı. AI modelleri için özet dizin eksik (0/18 puan)."],
            )

        score = 0
        details = []

        # 1. Existence (+6 pts)
        score += 6
        details.append("/llms.txt dosyası başarıyla bulundu (+6 puan).")

        # 2. H1 Title (+3 pts)
        lines = [l.strip() for l in llms_txt.splitlines() if l.strip()]
        has_h1 = any(l.startswith("# ") for l in lines)
        if has_h1:
            score += 3
            details.append("llms.txt standart H1 başlığı içeriyor (+3 puan).")
        else:
            details.append("llms.txt içinde H1 ('# Başlık') formatı eksik (0/3 puan).")

        # 3. Blockquote Summary (+3 pts)
        has_blockquote = any(l.startswith("> ") for l in lines)
        if has_blockquote:
            score += 3
            details.append("llms.txt blok alıntı (' > özet ') direktifi içeriyor (+3 puan).")
        else:
            details.append("llms.txt içinde LLM özet blok alıntısı eksik (0/3 puan).")

        # 4. Structured Sections (+3 pts)
        section_count = sum(1 for l in lines if l.startswith("## "))
        has_sections = section_count >= 2
        if has_sections:
            score += 3
            details.append(f"llms.txt {section_count} adet yapılandırılmış '##' alt bölüm içeriyor (+3 puan).")
        else:
            details.append("llms.txt alt bölümleri yetersiz veya eksik (0/3 puan).")

        # 5. llms-full.txt Companion or deep link (+3 pts)
        has_full = bool(llms_full_txt and len(llms_full_txt.strip()) > 50) or "llms-full.txt" in llms_txt
        if has_full:
            score += 3
            details.append("Derin dokümantasyon için /llms-full.txt bağlantısı mevcut (+3 puan).")
        else:
            details.append("/llms-full.txt derin dokümantasyon dosyası eksik (0/3 puan).")

        word_count = len(re.findall(r"\w+", llms_txt))

        return LlmsTxtScore(
            score=min(18, score),
            has_llms_txt=True,
            has_llms_full_txt=has_full,
            has_h1_title=has_h1,
            has_blockquote_summary=has_blockquote,
            has_structured_sections=has_sections,
            word_count=word_count,
            details=details,
        )
