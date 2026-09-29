"""JSON-LD Semantic Schema Analyzer for Rich AI Answer Extraction."""

import json
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Set
from answrank.models import SchemaScore

import logging

logger = logging.getLogger("answrank.schema")

class SchemaAnalyzer:
    """Extracts and evaluates JSON-LD structured data for LLM entity recognition."""

    def analyze(self, soup: BeautifulSoup, sector: str = "general") -> SchemaScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        scripts = soup.find_all("script", type="application/ld+json")
        if not scripts:
            return SchemaScore(
                score=0,
                has_json_ld=False,
                schema_types=[],
                has_sector_entity=False,
                has_faq_page=False,
                attribute_count=0,
                details=["Sayfada hiçbir JSON-LD yapılandırılmış verisi bulunamadı (0/16 puan)."],
            )

        score = 0
        details = []
        parsed_schemas: List[Dict[str, Any]] = []
        all_types: Set[str] = set()
        total_attributes = 0

        for script in scripts:
            content = script.string
            if not content or not content.strip():
                continue
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    parsed_schemas.extend(data)
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        parsed_schemas.extend(data["@graph"])
                    else:
                        parsed_schemas.append(data)
            except Exception as exc:
                logger.debug("JSON-LD bloğu ayrışmadı, atlandı: %s", exc.__class__.__name__)
                continue

        if parsed_schemas:
            score += 4
            details.append(f"Geçerli JSON-LD şemaları ayrıştırıldı ({len(parsed_schemas)} blok, +4 puan).")
        else:
            return SchemaScore(
                score=0,
                has_json_ld=False,
                schema_types=[],
                has_sector_entity=False,
                has_faq_page=False,
                attribute_count=0,
                details=["JSON-LD scriptleri bulundu ancak sözdizimi hatalı, ayrıştırılamadı (0/16 puan)."],
            )

        for item in parsed_schemas:
            stype = item.get("@type")
            if isinstance(stype, list):
                all_types.update(stype)
            elif isinstance(stype, str):
                all_types.add(stype)
            total_attributes += len(item.keys())

        # Sector specific target types
        sector_entity_keywords = {
            "dental": ["Dentist", "DentalClinic", "MedicalBusiness", "LocalBusiness"],
            "accounting": ["AccountingService", "FinancialService", "LocalBusiness", "ProfessionalService"],
            "aesthetic": ["MedicalClinic", "BeautySalon", "HealthAndBeautyBusiness", "LocalBusiness"],
            "general": ["LocalBusiness", "Organization", "Corporation", "ProfessionalService"],
        }
        targets = sector_entity_keywords.get(sector, sector_entity_keywords["general"])

        has_sector = any(t in all_types for t in targets)
        if has_sector:
            score += 4
            found_t = [t for t in targets if t in all_types]
            details.append(f"Sektöre özel işletme şeması mevcut: {', '.join(found_t)} (+4 puan).")
        else:
            score += 1
            details.append(f"Sektöre özel şema türü ({'/'.join(targets)}) bulunamadı (+1/4 puan).")

        # FAQPage check (crucial for Direct Answer RAG)
        has_faq = "FAQPage" in all_types or "QAPage" in all_types
        if has_faq:
            score += 4
            details.append("FAQPage şeması mevcut; yapay zeka soru-cevap bloklarına doğrudan erişebilir (+4 puan).")
        else:
            details.append("FAQPage şeması eksik; soru-cevap alıntıları zayıflıyor (0/4 puan).")

        # Richness (5+ attributes like geo, address, telephone, openingHours, priceRange, sameAs)
        rich_keys = {"address", "geo", "telephone", "openingHours", "openingHoursSpecification", "priceRange", "sameAs", "hasOfferCatalog"}
        found_rich = set()
        for item in parsed_schemas:
            for k in rich_keys:
                if k in item:
                    found_rich.add(k)

        if len(found_rich) >= 4:
            score += 4
            details.append(f"Şema zenginliği yüksek: {', '.join(found_rich)} nitelikleri tanımlı (+4 puan).")
        elif len(found_rich) >= 2:
            score += 2
            details.append(f"Şema zenginliği orta düzeyde: {', '.join(found_rich)} (+2/4 puan).")
        else:
            details.append("Şemada geo, adres, çalışma saatleri gibi zengin nitelikler eksik (0/4 puan).")

        return SchemaScore(
            score=min(16, score),
            has_json_ld=True,
            schema_types=sorted(list(all_types)),
            has_sector_entity=has_sector,
            has_faq_page=has_faq,
            attribute_count=total_attributes,
            details=details,
        )
