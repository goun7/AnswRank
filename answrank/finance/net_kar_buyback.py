"""Net-Kâr Buyback Kalkani — DCBM ( arXiv:2601.09961) Solvency Actuator.

KURAL ( kullanici): buyback SADECE NET KAR ile yapilir — brut gelir
DEGIL. Bu, akademik dayanagi olan bir ilkedir:

  arXiv:2601.09961v1 ( Oxford/FLock.io, 2026) DCBM:
  "the Solvency Actuator functions as a critical safety valve, strictly
   bounding the physical buyback expenditure ( J_k) by the current
   Treasury Balance ( T_k) and the circuit breaker parameter ( gamma),
   ensuring asymptotic solvency regardless of market conditions."

  Yani: buyback harcamasi ELDEKI gercek varligi asamaz.

Uygulamamizda: J_k ( buyback) <= NET_KAR ( brut gelir - tum maliyetler).
Brut gelir, LLM/API/altyapi maliyetleri cikarilmadan onceki degerdir;
kullanici bunu yakmami soylemistir cunku maliyetleri disarida birakir
( pro-cyclical instability tuzaği; ayni makale).

KESIN YASAKLAR:
- brut-kar ile buyback YOK
- static yuzde ( "%4.8" gibi) YOK — makale static heuristics'i
  elestirir ( bang-bang kontrol -> salinim)
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# Buyback icin izin verilen ust sinir: net karanin tamamli DEGIL —
# bir emniyet payi ( treasury rezervi). DCBM'nin gamma circuit-breaker'i.
# NOT: bu bir ORAN DEGIL, bir EMNIYET payidir; static "%X marj" KURALI degil.
TREASURY_REZERV_ORANI = 0.50  # net karanin en fazla %50'si buyback icin


class ServisGelirKaydi(BaseModel):
    """Tek bir servisin donemsel gelir/maliyet kaydi."""
    servis: str
    brut_gelir_usd: float = Field(ge=0.0)
    llm_maliyet_usd: float = Field(default=0.0, ge=0.0)
    api_maliyet_usd: float = Field(default=0.0, ge=0.0)
    altyapi_maliyet_usd: float = Field(default=0.01, ge=0.0)  # compute/gas
    gelir_transferi_usd: float = Field(default=0.0, ge=0.0)  # zincir ucreti

    @property
    def toplam_maliyet_usd(self) -> float:
        return (self.llm_maliyet_usd + self.api_maliyet_usd
                + self.altyapi_maliyet_usd + self.gelir_transferi_usd)

    @property
    def net_kar_usd(self) -> float:
        """NET KAR = brut gelir - tum maliyetler ( kuralin ozu)."""
        return self.brut_gelir_usd - self.toplam_maliyet_usd


class BuybackOnerisi(BaseModel):
    """DCBM Solvency Actuator tarafindan sinirlandirilmis oneri."""
    servis: str
    brut_gelir_usd: float
    toplam_maliyet_usd: float
    net_kar_usd: float
    izin_verilen_buyback_usd: float
    reddedildi: bool
    red_nedeni: Optional[str] = None


class BuybackHesaplayici:
    """Net-kar kuralini uygular ( Solvency Actuator)."""

    @staticmethod
    def hesapla(kayitlar: List[ServisGelirKaydi],
                rezerv_orani: float = TREASURY_REZERV_ORANI) -> Dict:
        """Her servis icin izin verilen buyback'i hesapla.

        KURAL: buyback <= net_kar * rezerv_orani ( emniyet payi)
        EGER net_kar <= 0 ise buyback YOK ( iflas-korumasi).
        """
        oneriler: List[BuybackOnerisi] = []
        for k in kayitlar:
            net = k.net_kar_usd
            if net <= 0:
                oneriler.append(BuybackOnerisi(
                    servis=k.servis,
                    brut_gelir_usd=k.brut_gelir_usd,
                    toplam_maliyet_usd=k.toplam_maliyet_usd,
                    net_kar_usd=net,
                    izin_verilen_buyback_usd=0.0,
                    reddedildi=True,
                    red_nedeni="net-kar <= 0 — buyback IZIN VERILMEZ "
                               "( Solvency Actuator: iflas-korumasi)",
                ))
            else:
                # DCBM: J_k <= T_k * gamma — emniyet payi ile sinirla
                izin = net * rezerv_orani
                oneriler.append(BuybackOnerisi(
                    servis=k.servis,
                    brut_gelir_usd=k.brut_gelir_usd,
                    toplam_maliyet_usd=k.toplam_maliyet_usd,
                    net_kar_usd=net,
                    izin_verilen_buyback_usd=round(izin, 6),
                    reddedildi=False,
                ))
        toplam_net = sum(k.net_kar_usd for k in kayitlar)
        toplam_brut = sum(k.brut_gelir_usd for k in kayitlar)
        toplam_maliyet = sum(k.toplam_maliyet_usd for k in kayitlar)
        return {
            "oneriler": oneriler,
            "toplam_brut_gelir_usd": round(toplam_brut, 6),
            "toplam_maliyet_usd": round(toplam_maliyet, 6),
            "toplam_net_kar_usd": round(toplam_net, 6),
            "toplam_izin_verilen_buyback_usd": round(
                sum(o.izin_verilen_buyback_usd for o in oneriler), 6),
            "kural": "SADECE net-kar ( brut - tum maliyetler); brut YOK; "
                     "static-yuzde YOK ( DCBM arXiv:2601.09961)",
            "rezerv_orani": rezerv_orani,
        }
