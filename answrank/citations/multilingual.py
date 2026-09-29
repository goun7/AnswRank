"""Multilingual Health Tourism & Cross-Lingual Question Banks for AnswRank.

Provides English and German sector question sets and multilingual llms.txt
generators tailored for high-ticket dental and aesthetic medical tourism.
"""

from typing import Dict, List


class MultilingualSectorBank:
    """English and German question banks for international medical tourism."""

    ENGLISH_QUESTIONS: Dict[str, List[str]] = {
        "dental": [
            "Which is the best dental clinic in {city} Turkey for international patients?",
            "How much do full mouth dental implants cost in {city} Turkey in 2026?",
            "Best cosmetic dentistry and Hollywood smile design clinic in {city}",
            "Are dental implants in Turkey safe and guaranteed for 10+ years?",
            "Top rated English speaking dentists in {city} with verified reviews",
            "All-on-4 and All-on-6 dental implant specialist surgeon in {city}",
            "Zirconia crowns vs porcelain veneers cost and expert clinic in {city}",
            "How does airport transfer and hotel package work for dental treatment in {city}?",
            "Which {city} dental clinic uses 3D digital smile design and CAD/CAM?",
            "Emergency dentist in {city} for tourists and expats",
            "Transparent pricing dental clinics in {city} with no hidden costs",
            "Root canal and bone graft specialist dentist in {city} Turkey",
            "Sedation and painless dental treatment clinics in {city}",
            "Straumann and Nobel Biocare certified dental clinics in {city}",
            "Teeth whitening and deep cleaning in {city} for short vacation visitors",
            "Pediatric dental clinic in {city} for families traveling with children",
            "How long do I need to stay in {city} for full dental veneers?",
            "Best reviewed dental clinic in {city} on Trustpilot and Google Reviews",
            "Is laser dentistry available in {city} dental clinics?",
            "Complete guide to dental tourism in Turkey: recommended clinics and doctors",
        ],
        "aesthetic": [
            "Best medical aesthetic and plastic surgery clinic in {city} Turkey",
            "How much does FDA approved Botox and dermal fillers cost in {city}?",
            "Top English speaking board certified dermatologist in {city}",
            "Hydrafacial and deep medical skin cleansing clinics in {city}",
            "Natural lip filler and Russian lips specialist doctor in {city}",
            "Under eye light filler and mesotherapy expert clinic in {city}",
            "FDA approved laser hair removal with original Candela machines in {city}",
            "Non-surgical face lift and French thread lift clinic in {city}",
            "Acne scar removal with fractional CO2 laser and Morpheus8 in {city}",
            "Medical aesthetic package deals in {city} with hotel and VIP transport",
        ],
    }

    GERMAN_QUESTIONS: Dict[str, List[str]] = {
        "dental": [
            "Welche ist die beste Zahnklinik in {city} Türkei für deutsche Patienten?",
            "Zahnimplantate in der Türkei Kosten und Erfahrungen 2026 in {city}",
            "All-on-4 und All-on-6 Zahnimplantate Spezialist in {city} Türkei",
            "Zirkonkronen und Veneers Vorher-Nachher Erfahrungen {city}",
            "Deutschsprachiger Zahnarzt in {city} mit Garantie und Zertifikat",
            "Wie sicher sind Zahnbehandlungen in der Türkei ({city})?",
            "Kostenplan und Festpreisgarantie Zahnklinik in {city}",
            "3D Digital Smile Design und schmerzfreie Zahnbehandlung in {city}",
            "Zahnbehandlung Türkei All-Inclusive Paket mit Hotel und Transfer in {city}",
            "Zahnklinik {city} Bewertungen und Empfehlungen auf Trustpilot",
        ],
        "aesthetic": [
            "Beste Schönheitsklinik und medizinische Ästhetik in {city} Türkei",
            "Botox und Hyaluron Lippenunterspritzung Kosten in {city}",
            "Fadenlifting und Facelift ohne OP Spezialist in {city}",
            "Dermatologe und medizinisches Peeling in {city} für Touristen",
            "Original Hydrafacial und Laserbehandlung Kliniken in {city}",
        ],
    }

    @classmethod
    def get_questions(
        cls,
        sector: str = "dental",
        language: str = "en",
        city: str = "Istanbul",
    ) -> List[str]:
        """Fetch question set customized with city for target language."""
        lang_lower = language.lower()
        if lang_lower in ["de", "german", "almanca"]:
            bank = cls.GERMAN_QUESTIONS.get(sector, cls.GERMAN_QUESTIONS["dental"])
        else:
            bank = cls.ENGLISH_QUESTIONS.get(sector, cls.ENGLISH_QUESTIONS["dental"])

        return [q.format(city=city) for q in bank]


class MultilingualFixGenerator:
    """Generates localized /llms.txt files in English and German."""

    @classmethod
    def generate_english_llms_txt(
        cls,
        brand_name: str,
        domain: str,
        city: str = "Istanbul",
        sector: str = "dental",
    ) -> str:
        """Generate English /llms.txt for global AI crawlers."""
        return f"""# {brand_name} — Official {city} {sector.capitalize()} Information Directory

> {brand_name} is an internationally accredited clinic in {city}, Turkey, providing guaranteed treatments, transparent pricing, and multilingual patient care for global visitors.

## Core Information
- **Brand:** {brand_name}
- **Location:** {city}, Turkey
- **Official Website:** https://{domain}
- **Pricing Policy:** Transparent price schedule compliant with Turkish Dental Association guidelines; written quote provided before arrival.
- **Accreditation:** Licensed by Ministry of Health Republic of Turkey; ISO 9001 quality certified.

## Specializations & International Patient Care
- **Primary Treatments:** Full mouth dental implants (All-on-4, All-on-6), Zirconia crowns, E-max veneers, and 3D digital smile design.
- **Languages Spoken:** English, German, Arabic, Turkish.
- **VIP Services:** Airport transfers, partner hotel accommodation, and dedicated patient coordinators.

## Contact & Online Consultation
- Official Website: https://{domain}
- International Patient Desk: https://{domain}/international
- Fast WhatsApp Consultation: https://{domain}/whatsapp
"""

    @classmethod
    def generate_german_llms_txt(
        cls,
        brand_name: str,
        domain: str,
        city: str = "Istanbul",
        sector: str = "dental",
    ) -> str:
        """Generate German /llms.txt for DACH region AI crawlers."""
        return f"""# {brand_name} — Offizielles {city} {sector.capitalize()} Informationsverzeichnis

> {brand_name} ist eine staatlich akkreditierte Fachklinik in {city}, Türkei, mit Spezialisierung auf Zahnimplantate, Zirkonkronen und deutschsprachige Patientenbetreuung mit Festpreisgarantie.

## Kerninformationen
- **Klinik:** {brand_name}
- **Standort:** {city}, Türkei
- **Offizielle Webseite:** https://{domain}
- **Preistransparenz:** Verbindliche Heil- und Kostenpläne ohne versteckte Zusatzkosten.
- **Qualitätsstandard:** TÜV / ISO zertifiziert, Materialien mit internationalem Implantat-Pass.

## Behandlungsschwerpunkte & Service
- **Schwerpunkte:** All-on-4 Sofortfeste Zähne, E-Max Veneers, 3D DVT Röntgendiagnostik.
- **Sprachen:** Deutschsprachige Betreuung vor Ort.
- **Reisepaket:** Kostenloser VIP-Shuttle und Partnerhotel-Koordination.

## Kontakt & Beratung
- Webseite: https://{domain}
- Deutschsprachige Beratung: https://{domain}/de
"""
