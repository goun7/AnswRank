"""Operational Decision Tree & Review Scenarios (S1-S4) for AnswRank.

Implements the Day 30/60 post-audit review scenarios specified in
EK G of ANSWRANK_MASTER_100.md.
"""

from enum import Enum
from typing import List
from pydantic import BaseModel


class ScenarioCode(str, Enum):
    S1_SUCCESS = "S1_SUCCESS"
    S2_PARTIAL_SUCCESS = "S2_PARTIAL_SUCCESS"
    S3_ZERO_DELTA = "S3_ZERO_DELTA"
    S4_CLIENT_INACTION = "S4_CLIENT_INACTION"


class ScenarioEvaluation(BaseModel):
    scenario: ScenarioCode
    name: str
    description: str
    target_action: str
    trigger_free_month: bool  # Madde 7.3 enforcement
    recommended_playbook: List[str]


class ScenarioRouter:
    """Evaluates audit outcomes against operational decision tree (EK G)."""

    @classmethod
    def evaluate(
        cls,
        baseline_score: float,
        current_score: float,
        baseline_citations: int,
        current_citations: int,
        client_cooperation_ok: bool = True,
    ) -> ScenarioEvaluation:
        """Route outcome to S1, S2, S3, or S4 scenario."""
        if not client_cooperation_ok:
            return ScenarioEvaluation(
                scenario=ScenarioCode.S4_CLIENT_INACTION,
                name="S4: Müşteri İletişimsizliği / Teknik Eylemsizlik",
                description=(
                    "Müşteri hazırlanan robots.txt, llms.txt veya şema dosyalarını web sitesine "
                    "yüklemedi veya teknik entegrasyonu tamamlamadı."
                ),
                target_action="Resmi askıya alma bildirimi gönderilir, Madde 7.4 uyarınca güvence dondurulur.",
                trigger_free_month=False,
                recommended_playbook=[
                    "WhatsApp ve e-posta üzerinden 'Eksik Entegrasyon Hatırlatması' gönder.",
                    "Gerekirse müşterinin ajansıyla 15 dakikalık teknik ekran paylaşımı organize et.",
                    "14 günlük ek entegrasyon süresi tanımla; süre bitiminde durumu güncelle.",
                ],
            )

        score_delta = current_score - baseline_score
        citation_growth_pct = (
            ((current_citations - baseline_citations) / baseline_citations) * 100.0
            if baseline_citations > 0
            else (100.0 if current_citations > 0 else 0.0)
        )

        # S1: Başarılı (Skor >= +25 veya Atıf >= +30%)
        if score_delta >= 25 or citation_growth_pct >= 30.0:
            return ScenarioEvaluation(
                scenario=ScenarioCode.S1_SUCCESS,
                name="S1: Başarılı Delta & Hedefe Ulaşma",
                description=(
                    f"Belirlenen performans taahhüdü aşıldı (Skor Deltası: +{score_delta:.1f} puan, "
                    f"Atıf Büyümesi: +%{citation_growth_pct:.1f})."
                ),
                target_action="Başarı vaka analizi (case study) hazırlanır ve 6 aylık Retainer / Enterprise sözleşmesi yenilenir.",
                trigger_free_month=False,
                recommended_playbook=[
                    "Önce/Sonra karşılaştırmalı 1 sayfalık Delta Başarı Raporunu müşteriye sun.",
                    "Yerel hekim/işletme sahibinden 30 saniyelik referans videosu/yorumu talep et.",
                    "Çoklu şube veya ek sektör soruları için Retainer paketini yenile.",
                ],
            )

        # S2: Kısmi Başarı (Skor > 0 veya Atıf > 0 ama hedefin altında)
        if score_delta > 0 or current_citations > baseline_citations:
            return ScenarioEvaluation(
                scenario=ScenarioCode.S2_PARTIAL_SUCCESS,
                name="S2: Kısmi Başarı / Hedef Altı Delta",
                description=(
                    f"Pozitif ilerleme var fakat sözleşme hedefinin altında kaldı (Skor Deltası: +{score_delta:.1f}, "
                    f"Atıf Büyümesi: +%{citation_growth_pct:.1f})."
                ),
                target_action="Madde 7.3 gereği takip eden ay ₺0 (ücretsiz) optimizasyon ve derin RAG analizi icra edilir.",
                trigger_free_month=True,
                recommended_playbook=[
                    "Müşteriye Madde 7.3 uyarınca ücretsiz ek ay taahhüdünü proaktif olarak bildir.",
                    "llms-full.txt dosyasını klinik vaka ve hekim uzmanlık detaylarıyla derinleştir.",
                    "Perplexity ve ChatGPT'nin kaynak seçim modelleri için semantik JSON-LD varlık bağlarını güçlendir.",
                ],
            )

        # S3: Sıfır Delta / Negatif Durum
        return ScenarioEvaluation(
            scenario=ScenarioCode.S3_ZERO_DELTA,
            name="S3: Sıfır Delta / Yapay Zeka Atfı Alınamadı",
            description=(
                f"30 gün sonunda yapay zeka atfı veya skor artışı sağlanamadı (Skor Deltası: {score_delta:.1f}, "
                f"Atıf: {baseline_citations} -> {current_citations})."
            ),
            target_action="Acil Kök Neden Denetimi başlatılır; Madde 7.3 işletilir ve ücretsiz servis sunulur.",
            trigger_free_month=True,
            recommended_playbook=[
                "Cloudflare / WAF / CDN loglarını incele: AI botları 403/429 alıyor mu?",
                "Client-side JavaScript rendering kontrolü yap: Botlar boş HTML mi görüyor?",
                "48 saat içinde 'Teknik Kök Neden ve Düzeltme Raporu'nu müşteriye ulaştır.",
            ],
        )
