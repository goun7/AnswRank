"""Knowledge Graph & Wikidata Entity Grounding Engine for AnswRank.

Verifies whether a brand/physician is an acknowledged real-world entity
with a Wikidata QID or Google Knowledge Graph grounding, preventing LLM hallucination
and ensuring the brand is retrieved as a permanent grounded authority.
"""

import httpx
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GroundingTier(str, Enum):
    GROUNDED_AUTHORITY = "GROUNDED_AUTHORITY"      # Wikidata QID + Knowledge Graph verified
    PARTIALLY_GROUNDED = "PARTIALLY_GROUNDED"      # Verified business listings & schema presence
    UNGROUNDED_STRING = "UNGROUNDED_STRING"        # LLM sees brand as an ungrounded arbitrary string


class EntityGroundingResult(BaseModel):
    brand_name: str
    domain: str
    grounding_score: float  # 0 to 100
    tier: GroundingTier
    wikidata_qid: Optional[str] = None
    wikidata_description: Optional[str] = None
    wikidata_url: Optional[str] = None
    has_wikidata: bool = False
    wikidata_probe_status: str = "unknown"  # found | not_found | unreachable — a failed
    # query must never be phrased as "the brand lacks a QID" (false accusation guard)
    p856_verified: Optional[bool] = None  # True/False after P856 cross-check; None = not determinable
    qid_confidence: str = "unknown"      # verified | exact_name_no_conflict | unverified | rejected
    has_google_maps_cid: bool = False
    has_linkedin_entity: bool = False
    grounding_signals: List[str] = Field(default_factory=list)
    missing_foundations: List[str] = Field(default_factory=list)
    action_roadmap: List[str] = Field(default_factory=list)


class EntityGroundingEngine:
    """Probes Wikidata API and evaluates global Knowledge Graph entity presence."""

    WIKIDATA_SEARCH_API = "https://www.wikidata.org/w/api.php"

    @staticmethod
    def _netloc_of(url: str) -> Optional[str]:
        from answrank.textnorm import netloc as _tn
        return _tn(url) or None

    @classmethod
    def _p856_matches_domain(cls, urls: List[str], domain: str) -> bool:
        """True when ANY P856 official-website value resolves to the target
        domain (or a sub/super-domain of it). Pure containment on netlocs only —
        never fuzzy text similarity."""
        d = (domain or "").lower().strip()
        if d.startswith("www."):
            d = d[4:]
        if not d:
            return False
        for u in urls:
            n = cls._netloc_of(u)
            if not n:
                continue
            if n == d or n.endswith("." + d) or d.endswith("." + n):
                return True
        return False

    @classmethod
    async def probe_official_websites(
        cls, qid: str, timeout_sec: float = 5.0
    ) -> Dict[str, object]:
        """Fetch P856 (official website) statements for a QID via wbgetclaims.

        Returns {"status": "ok"|"unreachable", "urls": [...]}. A name search hit
        alone must NEVER grant grounding credit: `wbsearchentities` fuzzy-matches,
        so a generic brand can land on an unrelated entity (observed live: brand
        "Example" → Q114424786). Cross-checking the entity's registered official
        site against the audited domain turns the match into evidence — or rejects it.
        """
        params = {"action": "wbgetclaims", "entity": qid, "property": "P856", "format": "json"}
        headers = {"User-Agent": "AnswRank-EntityGrounder/1.0 (https://answrank.ai; info@answrank.ai)"}
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.get(cls.WIKIDATA_SEARCH_API, params=params, headers=headers)
                if resp.status_code != 200:
                    return {"status": "unreachable", "urls": []}
                claims = resp.json().get("claims") or {}
                urls: List[str] = []
                for stmt in claims.get("P856") or []:
                    value = (((stmt or {}).get("mainsnak") or {}).get("datavalue") or {}).get("value")
                    if isinstance(value, str) and value.strip():
                        urls.append(value.strip())
                return {"status": "ok", "urls": urls}
        except Exception:
            # Same honesty rule as the search probe: a failed verification is
            # "not determinable", never a verdict for or against the entity.
            return {"status": "unreachable", "urls": []}

    @classmethod
    async def probe_wikidata(
        cls,
        brand_name: str,
        timeout_sec: float = 5.0,
        language: str = "en",
        uselang: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """Query Wikidata search API for candidate entity match.

        `language` controls the search/label language (defaults to English for
        global brands; pass "tr" for Turkish-only local entities). `uselang`
        optionally controls the display language of descriptions.
        """
        params = {
            "action": "wbsearchentities",
            "search": brand_name,
            "language": language,
            "uselang": uselang or language,
            "format": "json",
            "limit": 3,
        }
        headers = {
            "User-Agent": "AnswRank-EntityGrounder/1.0 (https://answrank.ai; info@answrank.ai)",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.get(cls.WIKIDATA_SEARCH_API, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("search", [])
                    if results:
                        best = results[0]
                        return {
                            "qid": best.get("id"),
                            "label": best.get("label"),
                            "description": best.get("description"),
                            "url": best.get("concepturi"),
                            "status": "found",
                        }
                    # Live 200 with zero matches -> genuinely not in Wikidata
                    return {"qid": None, "label": None, "description": None, "url": None, "status": "not_found"}
                # API answered but with an error status -> inconclusive, not "missing"
                return {"qid": None, "label": None, "description": None, "url": None, "status": "unreachable"}
        except Exception:
            # Network/timeout -> never claim the brand lacks an entity it may well have
            return {"qid": None, "label": None, "description": None, "url": None, "status": "unreachable"}

    @classmethod
    async def evaluate_grounding(
        cls,
        brand_name: str,
        domain: str,
        html_content: Optional[str] = None,
        timeout_sec: float = 5.0,
        language: str = "en",
    ) -> EntityGroundingResult:
        """Evaluate complete Knowledge Graph entity grounding."""
        signals: List[str] = []
        missing: List[str] = []
        score = 0.0

        # 1. Wikidata Live API Query (tri-state: found / not_found / unreachable)
        wiki_match = await cls.probe_wikidata(brand_name, timeout_sec=timeout_sec, language=language)
        wiki_status = str(wiki_match.get("status", "not_found"))
        has_wiki = bool(wiki_match.get("qid"))

        p856_verified: Optional[bool] = None
        qid_confidence = "unknown"
        if has_wiki:
            p856 = await cls.probe_official_websites(str(wiki_match["qid"]), timeout_sec=timeout_sec)
            p856_urls = list(p856.get("urls") or [])
            if p856.get("status") == "ok":
                if p856_urls and cls._p856_matches_domain(p856_urls, domain):
                    p856_verified = True
                    qid_confidence = "verified"
                    score += 45.0
                    signals.append(
                        f"Wikidata Varlık Kaydı Mevcut ve P856 (resmî site) çapraz-doğrulamasıyla TEYİTLİ: "
                        f"{wiki_match['qid']} ({wiki_match['description'] or wiki_match['label']})"
                    )
                elif p856_urls:
                    # Registered official site of the matched entity CONTRADICTS the
                    # audited domain -> same-name, different organization. No credit.
                    p856_verified = False
                    qid_confidence = "rejected"
                    missing.append(
                        f"Arama eşleşmesi REDDEDİLDİ: {wiki_match['qid']} varlığının resmî sitesi "
                        f"({p856_urls[0]}) hedef domain '{domain}' ile çelişiyor — aynı ada sahip başka "
                        f"bir kuruluşla eşleşildi; zeminleme kredisi verilmedi."
                    )
                else:
                    # Entity exists but registers no official website: fall back to
                    # label precision — exact normalized name match earns partial,
                    # fuzzy match only cautious credit.
                    label = (wiki_match.get("label") or "").strip().lower().rstrip(".")
                    brand_norm = (brand_name or "").strip().lower().rstrip(".")
                    if label and label == brand_norm:
                        qid_confidence = "exact_name_no_conflict"
                        score += 35.0
                        signals.append(
                            f"Wikidata Varlık Kaydı: {wiki_match['qid']} — ad birebir eşleşiyor, "
                            f"P856 çelişkisi yok (kısmi kanıt: resmî site kaydı bulunmuyor)."
                        )
                    else:
                        qid_confidence = "unverified"
                        score += 15.0
                        signals.append(
                            f"Wikidata arama eşleşmesi: {wiki_match['qid']} — yalnız bulanık ad eşleşmesi, "
                            f"P856 kaydı da yok; yanlış-varlık riskine karşı DÜŞÜK kredi verildi."
                        )
            else:
                # P856 could not be fetched: withhold judgment, conservative partial credit.
                qid_confidence = "unverified"
                score += 25.0
                signals.append(f"Wikidata Varlık Kaydı Mevcut: {wiki_match['qid']} ({wiki_match['description'] or wiki_match['label']})")
                missing.append(
                    "P856 resmî-site çapraz-doğrulaması yapılamadı (ağ/API hatası) — QID eşleşmesi "
                    "DOĞRULANAMADI; puan muhafazakâr tutuldu, lütfen yeniden deneyin."
                )
        elif wiki_status == "unreachable":
            missing.append("Wikidata sorgusu tamamlanamadı (ağ/API hatası) — QID durumu DOĞRULANAMADI; bu bir eksiklik hükmü değildir, yeniden test edin.")
        else:
            missing.append("Wikidata Varlık Kaydı (QID) eksik. Küresel bilgi grafiğinde bağımsız kimlik yok.")

        # 2. HTML Schema / sameAs Signals
        has_maps = False
        has_linkedin = False

        if html_content:
            lower_html = html_content.lower()
            if "maps.google.com" in lower_html or "google.com/maps" in lower_html or "cid=" in lower_html:
                has_maps = True
                signals.append("Google Maps / Yerel İşletme CID Doğrulaması mevcut.")
                score += 25.0
            else:
                missing.append("Google Maps / CID varlık bağıntısı (sameAs) bulunamadı.")

            if "linkedin.com/company" in lower_html:
                has_linkedin = True
                signals.append("Kurumsal LinkedIn Şirket Kimliği (Organization Entity) tanımlı.")
                score += 15.0
            else:
                missing.append("Resmi LinkedIn Şirket Sayfası varlık grafiğine bağlanmamış.")

            if "@type" in lower_html and ("medicalclinic" in lower_html or "dentist" in lower_html or "accountingservice" in lower_html):
                signals.append("Dikey Sektör JSON-LD Şema Varlığı tanımlı.")
                score += 15.0
            else:
                missing.append("Dikey Sektör Varlık Şeması (JSON-LD Organization/Clinic) eksik.")
        else:
            # No HTML was supplied: we cannot test the on-page entity signals, so we
            # award NO points for them (fabricated credit would inflate the score) and
            # say so explicitly instead of pretending they are absent.
            missing.append("HTML içeriği sağlanmadı — Maps/LinkedIn/JSON-LD sinyalleri DEĞERLENDİRİLEMEDİ; puan yalnızca Wikidata kanıtına dayanır.")

        score = min(100.0, round(score, 1))

        if score >= 75.0:
            tier = GroundingTier.GROUNDED_AUTHORITY
            roadmap = [
                "Varlık kimliği güçlü. llms.txt dosyasına Wikidata QID URI'sini referans olarak ekleyin.",
                "Wikipedia ve sektörel derneklerdeki kurumsal atıfları güncel tutun.",
            ]
        elif score >= 40.0:
            tier = GroundingTier.PARTIALLY_GROUNDED
            roadmap = [
                "Wikidata üzerinde tescilli sağlık/hizmet kuruluşu varlığı oluşturun (P31: Q16917).",
                "JSON-LD 'sameAs' dizisine Google Maps, LinkedIn ve Wikidata URI'lerini ekleyin.",
                "Hekim ve başhekimler için TDB / hekim sicil profillerini semantik olarak bağlayın.",
            ]
        else:
            tier = GroundingTier.UNGROUNDED_STRING
            roadmap = [
                "ACİL: Marka yapay zeka tarafından 'bilinen bir varlık' (Entity) olarak tanınmamaktadır.",
                "Google İşletme Profili (Maps CID) ve Wikidata varlık kaydını ivedilikle açın.",
                "AnswRank'in ürettiği tam JSON-LD şemasını ana sayfaya yerleştirin.",
            ]

        return EntityGroundingResult(
            brand_name=brand_name,
            domain=domain,
            grounding_score=score,
            tier=tier,
            wikidata_qid=wiki_match.get("qid"),
            wikidata_description=wiki_match.get("description"),
            wikidata_url=wiki_match.get("url"),
            has_wikidata=has_wiki,
            wikidata_probe_status=wiki_status,
            p856_verified=p856_verified,
            qid_confidence=qid_confidence,
            has_google_maps_cid=has_maps,
            has_linkedin_entity=has_linkedin,
            grounding_signals=signals,
            missing_foundations=missing,
            action_roadmap=roadmap,
        )
