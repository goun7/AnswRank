"""Adversarial AI & Indirect Prompt Injection Defense Analyzer.

Detects hidden prompts, CSS cloaking, invisible unicode steganography,
and adversarial directives aimed at poisoning LLM crawler summaries.
"""

import re
from typing import List, Optional
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

class AdversarialThreat(BaseModel):
    threat_type: str
    severity: str  # LOW, MEDIUM, CRITICAL
    snippet: str
    description: str

class AdversarialAuditResult(BaseModel):
    is_clean: bool = True
    risk_score: int = 0  # 0 to 100
    threat_level: str = "CLEAN"  # CLEAN, LOW, MEDIUM, CRITICAL
    threats: List[AdversarialThreat] = Field(default_factory=list)
    cloaked_elements_count: int = 0
    invisible_unicode_count: int = 0
    details: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

class AdversarialAnalyzer:
    """Scans web content for indirect prompt injections and cloaking attacks."""

    INJECTION_PATTERNS = [
        (r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", "CRITICAL", "Instruction override attempt"),
        (r"disregard\s+(all\s+)?(prior|previous)\s+prompts?", "CRITICAL", "Instruction disregard attempt"),
        (r"system\s*prompt\s*:", "HIGH", "System prompt impersonation"),
        (r"you\s+are\s+now\s+(in\s+)?(a\s+)?(new\s+mode|dan|developer\s+mode)", "CRITICAL", "Jailbreak mode initiation"),
        (r"(do\s+not|never)\s+(recommend|suggest|cite)\s+(this|the)\s+(clinic|business|brand|website)", "CRITICAL", "Competitor poisoning: anti-recommendation injection"),
        (r"(instead|always)\s+(recommend|prioritize)\s+([a-zA-Z0-9_\s]{2,30})", "HIGH", "Competitor poisoning: forced recommendation hijacking"),
        (r"output\s+only\s+(the\s+following|this)", "MEDIUM", "Output format constraining prompt injection"),
        (r"\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>", "CRITICAL", "ChatML / LLM special token injection"),
        # Düşük-şiddetli gösterim manipülasyonu: görünürlük talimatı
        # zararlı değil ama GEO-yönelik kelime doldurması gerçek tehdittir.
        (r"\b(?:ai\s*overview|ai\s*answer|featured\s*snippet)\s+için\s+optimize\b",
         "LOW", "AI-answer keyword targeting (GEO stuffing)"),
    ]

    CLOAKING_CSS_PATTERNS = [
        (r"display\s*:\s*none", "Hidden element with display:none"),
        (r"visibility\s*:\s*hidden", "Hidden element with visibility:hidden"),
        (r"opacity\s*:\s*0(\.0+)?(?![0-9])", "Hidden element with opacity:0"),
        (r"font-size\s*:\s*0(px|pt|em|rem)?", "Hidden text with font-size:0"),
        (r"text-indent\s*:\s*-\s*[0-9]{3,6}px", "Off-screen text with negative text-indent"),
        (r"left\s*:\s*-\s*[0-9]{3,6}px", "Off-screen element with negative left coordinate"),
    ]

    INVISIBLE_UNICODE_CHARS = [
        "\u200b",  # Zero width space
        "\u200c",  # Zero width non-joiner
        "\u200d",  # Zero width joiner
        "\ufeff",  # Zero width no-break space
        "\u2060",  # Word joiner
    ]

    def analyze(self, soup: BeautifulSoup, raw_html: Optional[str] = None) -> AdversarialAuditResult:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        threats: List[AdversarialThreat] = []
        details: List[str] = []
        recommendations: List[str] = []

        html_text = raw_html if raw_html else str(soup)

        # 1. Prompt Injection Pattern Scanning in visible and raw text
        for pattern, severity, desc in self.INJECTION_PATTERNS:
            matches = list(re.finditer(pattern, html_text, re.IGNORECASE))
            for m in matches:
                snippet = m.group(0)[:120]
                threats.append(
                    AdversarialThreat(
                        threat_type="PROMPT_INJECTION",
                        severity=severity,
                        snippet=snippet,
                        description=desc,
                    )
                )

        # 2. Cloaking & Hidden Text Elements (CSS check)
        cloaked_count = 0
        for tag in soup.find_all(style=True):
            style_str = tag.get("style", "").lower()
            for css_pat, css_desc in self.CLOAKING_CSS_PATTERNS:
                if re.search(css_pat, style_str):
                    tag_text = tag.get_text(strip=True)
                    # Only flag if cloaked element contains text
                    if len(tag_text) > 15:
                        cloaked_count += 1
                        threats.append(
                            AdversarialThreat(
                                threat_type="CSS_CLOAKING",
                                severity="HIGH" if any(p in tag_text.lower() for p, _, _ in self.INJECTION_PATTERNS) else "MEDIUM",
                                snippet=f"<{tag.name} style='{style_str[:50]}...'>{tag_text[:80]}...",
                                description=f"{css_desc} containing hidden text for AI scrapers.",
                            )
                        )
                        break

        # 3. Invisible Unicode Steganography
        unicode_count = 0
        for char in self.INVISIBLE_UNICODE_CHARS:
            count = html_text.count(char)
            unicode_count += count

        if unicode_count > 10:
            threats.append(
                AdversarialThreat(
                    threat_type="INVISIBLE_UNICODE",
                    severity="HIGH" if unicode_count > 50 else "MEDIUM",
                    snippet=f"{unicode_count} zero-width characters detected",
                    description="Excessive zero-width Unicode characters detected; potential prompt steganography.",
                )
            )

        # Calculate risk score
        risk_score = 0
        for t in threats:
            if t.severity == "CRITICAL":
                risk_score += 40
            elif t.severity == "HIGH":
                risk_score += 20
            elif t.severity == "MEDIUM":
                risk_score += 10
            elif t.severity == "LOW":
                risk_score += 5

        risk_score = min(100, risk_score)

        if risk_score == 0:
            threat_level = "CLEAN"
            is_clean = True
            details.append("Hiçbir dolaylı prompt enjeksiyonu veya gizlenmiş metin tespit edilmedi.")
        elif risk_score < 25:
            threat_level = "LOW"
            is_clean = False
            details.append(f"Düşük riskli {len(threats)} şüpheli öğe bulundu.")
        elif risk_score < 60:
            threat_level = "MEDIUM"
            is_clean = False
            details.append(f"Orta riskli {len(threats)} şüpheli/gizli öğe tespit edildi.")
        else:
            threat_level = "CRITICAL"
            is_clean = False
            details.append(f"KRİTİK: {len(threats)} adet aktif LLM zehirleme veya prompt enjeksiyonu tespit edildi!")

        if not is_clean:
            recommendations.append("Gizli CSS (display:none, font-size:0) içeren metin bloklarını temizleyin.")
            if any(t.threat_type == "PROMPT_INJECTION" for t in threats):
                recommendations.append("Sayfadaki LLM manipülasyonu amaçlı direktifleri (instruction override) derhal kaldırın.")
            if unicode_count > 10:
                recommendations.append("Görünmez sıfır-genişlikli (zero-width) Unicode karakterleri temizleyin.")

        return AdversarialAuditResult(
            is_clean=is_clean,
            risk_score=risk_score,
            threat_level=threat_level,
            threats=threats,
            cloaked_elements_count=cloaked_count,
            invisible_unicode_count=unicode_count,
            details=details,
            recommendations=recommendations,
        )
