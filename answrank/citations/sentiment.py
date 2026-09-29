"""Zero-Click Sentiment & Brand Safety Scoring Engine for LLM Citations.

Evaluates whether an LLM recommendation is positive, neutral, or poses a brand safety risk.
Generates authoritative counter-citation strategies if LLM hallucinations or defamatory warnings are detected.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SentimentPolarity(str, Enum):
    POSITIVE_RECOMMENDATION = "POSITIVE_RECOMMENDATION"
    NEUTRAL_MENTION = "NEUTRAL_MENTION"
    RISK_WARNING = "RISK_WARNING"


class BrandSafetyFlag(str, Enum):
    HIDDEN_COSTS = "HIDDEN_COSTS"
    COMPLICATIONS_RISK = "COMPLICATIONS_RISK"
    UNLICENSED_PRACTICE = "UNLICENSED_PRACTICE"
    POOR_HYGIENE = "POOR_HYGIENE"
    MALPRACTICE_ALLEGATION = "MALPRACTICE_ALLEGATION"
    NEGATIVE_REVIEWS = "NEGATIVE_REVIEWS"


class SentimentAnalysisResult(BaseModel):
    """Result of citation sentiment and brand safety evaluation."""
    polarity: SentimentPolarity
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)  # -1.0 (Critical Risk) to +1.0 (Top Endorsement)
    is_brand_safe: bool
    detected_flags: List[BrandSafetyFlag] = Field(default_factory=list)
    context_snippet: Optional[str] = None
    counter_citation_strategy: Optional[str] = None


class SentimentAnalyzer:
    """Analyzes raw LLM output surrounding brand mentions for sentiment and brand risks."""

    POSITIVE_KEYWORDS = [
        "best", "top", "leading", "recommended", "premier", "expert", "specialist",
        "accredited", "award-winning", "trusted", "reputable", "high-success",
        "en iyi", "önerilen", "lider", "uzman", "başarılı", "güvenilir", "kaliteli",
        "beste", "führende", "empfohlen", "spezialist", "renommiert",
    ]

    RISK_KEYWORDS = {
        BrandSafetyFlag.HIDDEN_COSTS: [
            "hidden cost", "hidden fee", "expensive", "overpriced", "overcharging",
            "gizli ücret", "pahalı", "fiyat şeffaf değil", "fahiş", "teuer", "versteckte kosten",
        ],
        BrandSafetyFlag.COMPLICATIONS_RISK: [
            # NOTE: bare "risk" / "risiko" deliberately excluded — too generic,
            # caused false positives on neutral phrases like "risk analizi yaptık".
            "complication", "failure rate", "risk of complications", "at risk of",
            "painful", "implant failure", "botched",
            "komplikasyon", "başarısızlık", "riskli", "iltihap", "enfeksiyon",
            "misserfolg", "komplikationen", "fehlgeschlagen",
        ],
        BrandSafetyFlag.MALPRACTICE_ALLEGATION: [
            "lawsuit", "complaint", "malpractice", "negligence", "scam", "fraud",
            "dava", "şikayet", "ihmal", "dolandırıcı", "sahtekar", "klage", "beschwerde",
        ],
        BrandSafetyFlag.NEGATIVE_REVIEWS: [
            "poor review", "bad experience", "avoid", "unprofessional",
            "kötü yorum", "tavsiye etmem", "uzak durun", "profesyonel değil", "schlechte erfahrung",
        ],
    }

    def analyze(
        self,
        raw_response: str,
        brand_name: str,
        domain: str = "",
        sector: str = "general",
    ) -> SentimentAnalysisResult:
        """Evaluate sentiment polarity and safety flags surrounding brand mentions."""
        if not raw_response or not brand_name:
            return SentimentAnalysisResult(
                polarity=SentimentPolarity.NEUTRAL_MENTION,
                sentiment_score=0.0,
                is_brand_safe=True,
                detected_flags=[],
            )

        norm_resp = raw_response.lower()
        norm_brand = brand_name.lower()

        # Extract context window around brand mention (+- 250 characters)
        brand_pos = norm_resp.find(norm_brand)
        if brand_pos != -1:
            start_pos = max(0, brand_pos - 200)
            end_pos = min(len(norm_resp), brand_pos + len(norm_brand) + 200)
            context = norm_resp[start_pos:end_pos]
            raw_context = raw_response[start_pos:end_pos].strip()
        else:
            context = norm_resp
            raw_context = raw_response[:300].strip()

        # Check for Risk Flags
        flags: List[BrandSafetyFlag] = []
        for flag, keywords in self.RISK_KEYWORDS.items():
            for kw in keywords:
                if kw in context:
                    flags.append(flag)
                    break

        # Calculate positive keyword matches in context
        pos_matches = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in context)

        # Compute polarity and score
        if flags:
            polarity = SentimentPolarity.RISK_WARNING
            sentiment_score = max(-1.0, -0.3 - (0.2 * len(flags)))
            is_safe = False
            counter_strategy = self.generate_counter_strategy(brand_name, sector, flags)
        elif pos_matches >= 2:
            polarity = SentimentPolarity.POSITIVE_RECOMMENDATION
            sentiment_score = min(1.0, 0.4 + (0.15 * pos_matches))
            is_safe = True
            counter_strategy = None
        else:
            polarity = SentimentPolarity.NEUTRAL_MENTION
            sentiment_score = 0.1 if pos_matches == 1 else 0.0
            is_safe = True
            counter_strategy = None

        return SentimentAnalysisResult(
            polarity=polarity,
            sentiment_score=round(sentiment_score, 2),
            is_brand_safe=is_safe,
            detected_flags=flags,
            context_snippet=raw_context[:250],
            counter_citation_strategy=counter_strategy,
        )

    def generate_counter_strategy(
        self,
        brand_name: str,
        sector: str,
        flags: List[BrandSafetyFlag],
    ) -> str:
        """Formulates an immediate AEO factual anchor injection strategy to reverse negative LLM bias."""
        flag_names = ", ".join(f.value for f in flags)
        return (
            f"CRITICAL AEO ALERT for {brand_name} ({sector}): LLM outputs exhibit negative brand bias ({flag_names}). "
            f"Action Required: Inject verified clinical statistics, transparent pricing schema (MedicalWebPage / PriceSpecification), "
            f"and third-party accreditation citations directly into llms-full.txt and JSON-LD schema to neutralize model hallucinations."
        )
