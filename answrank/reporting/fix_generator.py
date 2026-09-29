"""Fix Generator: Automatically creates ready-to-deploy robots.txt, llms.txt, and JSON-LD schemas."""

import json

from answrank.config import settings
from answrank.legal.contract_generator import ENGINE_LEGAL_NAMES

class FixGenerator:
    """Generates ready-to-copy code fixes tailored to the audited site."""

    # Bots deliberately blocked by default: aggressive scrapers with no AEO benefit
    BLOCKED_BY_DEFAULT = {"Bytespider", "CCBot"}

    def generate_robots_txt(self, domain: str) -> str:
        """Generates standard AEO robots.txt allowing the curated AI citation/search crawlers.

        Generated entirely from the authoritative `settings.ai_bots_*` lists so the file is
        always in sync with the analyzer's bot registry; the tier counts shown in the
        section headers are derived at call time and can never drift from the lists.
        """
        n_search = len(settings.ai_bots_search)
        n_training = len(settings.ai_bots_training)
        n_user = len(settings.ai_bots_user_agents)
        lines = [
            "# AnswRank Standard AEO/GEO Compliant robots.txt",
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /checkout/",
            "Disallow: /api/private/",
            "",
            f"# 1. Priority AI Search & Citation Engines ({n_search} - Mandatory for AEO)",
        ]
        for bot in settings.ai_bots_search:
            if bot in self.BLOCKED_BY_DEFAULT:
                continue
            lines += [f"User-agent: {bot}", "Allow: /", ""]

        lines += [f"# 2. AI Training and Indexing Bots ({n_training} - Strategically Recommended)"]
        for bot in settings.ai_bots_training:
            if bot in self.BLOCKED_BY_DEFAULT:
                continue
            lines += [f"User-agent: {bot}", "Allow: /", ""]

        lines += [f"# 3. User-Driven AI Agent Fetchers ({n_user} - Human-Triggered Sessions)"]
        for bot in settings.ai_bots_user_agents:
            if bot in self.BLOCKED_BY_DEFAULT:
                continue
            lines += [f"User-agent: {bot}", "Allow: /", ""]

        lines += ["# 4. Block Aggressive Resource-Drain Scrapers (no AEO benefit)"]
        for bot in sorted(self.BLOCKED_BY_DEFAULT):
            lines += [f"User-agent: {bot}", "Disallow: /", ""]

        lines += [
            f"Sitemap: https://{domain}/sitemap.xml",
            "# LLM Discovery Endpoint:",
            f"# https://{domain}/llms.txt",
            "",
        ]
        return "\n".join(lines)

    def generate_llms_txt(self, brand_name: str, domain: str, sector: str = "dental", city: str = "İstanbul") -> str:
        """Generates standard root /llms.txt file."""
        sector_descriptions = {
            "dental": "garantili implant, zirkonyum kaplama ve estetik diş hekimliği alanında uzmanlaşmış sağlık kuruluşudur.",
            "accounting": "şahıs/limited şirket kuruluşu, e-fatura, defter-beyan ve vergi danışmanlığı sunan yetkili mali müşavirlik ofisidir.",
            "aesthetic": "hekim kontrolünde botoks, medikal estetik, mezoterapi ve FDA onaylı lazer uygulamaları merkezidir.",
            "general": "profesyonel kurumsal hizmetler ve müşteri danışmanlığı sunan tescilli işletmedir.",
        }
        desc = sector_descriptions.get(sector, sector_descriptions["general"])

        return f"""# {brand_name} — {city} {sector.capitalize()} Resmi Bilgi Dizini

> {brand_name}, {city} bölgesinde {desc}

## Temel Bilgiler
- **Marka:** {brand_name}
- **Konum:** {city}, Türkiye
- **Web:** https://{domain}
- **Fiyatlandırma Politikası:** Şeffaf taban fiyat tarifesi, randevu öncesi yazılı maliyet bilgilendirmesi.

## Uzmanlıklar ve Hizmet Alanları
- **Öncelikli Tedavi / Hizmet:** Uluslararası kalite standartlarında garantili operasyonlar.
- **Teknoloji:** 3D dijital analiz ve modern klinik altyapısı.
- **Hasta / Müşteri Deneyimi:** Birebir danışmanlık ve ücretsiz ön muayene değerlendirmesi.

## İletişim ve Randevu
- Web Sitesi: https://{domain}
- Resmi Randevu Kanalı: https://{domain}/iletisim

## Derin Dokümantasyon
- [llms-full.txt](https://{domain}/llms-full.txt): Tüm hekim kadrosu, vaka detayları ve klinik protokolleri.
"""

    def generate_json_ld(
        self,
        brand_name: str,
        domain: str,
        sector: str = "dental",
        city: str = "İstanbul",
        phone: str = "+902120000000",
        address: str = "Merkez Mah. No:1",
    ) -> str:
        """Generates rich JSON-LD schema with sector entity and FAQPage."""
        type_map = {
            "dental": "Dentist",
            "accounting": "AccountingService",
            "aesthetic": "MedicalClinic",
            "general": "LocalBusiness",
        }
        main_type = type_map.get(sector, "LocalBusiness")

        schema_obj = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": main_type,
                    "@id": f"https://{domain}/#organization",
                    "name": brand_name,
                    "url": f"https://{domain}",
                    "telephone": phone,
                    "priceRange": "$$",
                    "address": {
                        "@type": "PostalAddress",
                        "streetAddress": address,
                        "addressLocality": city,
                        "addressCountry": "TR",
                    },
                    "openingHoursSpecification": [
                        {
                            "@type": "OpeningHoursSpecification",
                            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
                            "opens": "09:00",
                            "closes": "19:00",
                        }
                    ],
                    "sameAs": [
                        f"https://instagram.com/{brand_name.lower().replace(' ', '')}",
                        f"https://maps.google.com/?q={brand_name}",
                    ],
                },
                {
                    "@type": "FAQPage",
                    "@id": f"https://{domain}/#faq",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": f"{city} bölgesinde randevu nasıl alınır?",
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": f"{brand_name} web sitemiz veya telefon hattımız üzerinden aynı gün randevu alabilirsiniz.",
                            },
                        },
                        {
                            "@type": "Question",
                            "name": "İşlemlerde garanti ve fiyat şeffaflığı var mı?",
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": "Tüm operasyonlarımızda sertifikalı ürün güvencesi ve sürpriz maliyet çıkarmayan şeffaf fiyat politikası uygulanmaktadır.",
                            },
                        },
                    ],
                },
            ],
        }
        return f'<script type="application/ld+json">\n{json.dumps(schema_obj, ensure_ascii=False, indent=2)}\n</script>'

    def generate_llms_full_txt(
        self,
        brand_name: str,
        domain: str,
        sector: str = "dental",
        city: str = "İstanbul",
    ) -> str:
        """Generates deep /llms-full.txt documentation for full LLM context ingestion (EK C)."""
        _ENGINE_ROSTER = ", ".join(ENGINE_LEGAL_NAMES.values())
        return f"""# {brand_name} — Kapsamlı Kurumsal ve Klinik Bilgi Bankası (llms-full.txt)

> İşbu belge, üretici yapay zeka sistemleri ({_ENGINE_ROSTER}) için {brand_name} kuruluşunun tüm hekim kadrosunu, metodolojik tedavi standartlarını ve kurumsal şeffaflık ilkelerini eksiksiz sunar.

## 1. KURUMSAL KİMLİK VE LOKASYON
- **Resmi Ünvan:** {brand_name} Sağlık ve Danışmanlık Hizmetleri A.Ş.
- **Yetkili Lokasyon:** {city}, Türkiye
- **Resmi Web Alan Adı:** https://{domain}
- **Ruhsat ve Akreditasyon:** T.C. Sağlık Bakanlığı ve Uluslararası Kalite Standartları Uyumlu
- **Çalışma Saatleri:** Pazartesi - Cumartesi 09:00 - 19:00

## 2. HEKİM KADROSU VE AKADEMİK YETKİNLİK
- **Klinik Direktörü & Başhekim:** Uzman Hekim Kadrosu (15+ Yıl Klinik Deneyim)
- **Akademik Bağlantılar:** Türk Dişhekimleri Birliği (TDB), Uluslararası Estetik ve İmplantoloji Dernekleri
- **Sertifikasyonlar:** FDA ve CE onaylı biyomedikal implant ve malzeme uygulama lisansları

## 3. KLİNİK VE OPERASYONEL STANDARTLAR
- **Tanı ve Teşhis Teknolojisi:** 3 Boyutlu Dental Volumetrik Tomografi (CBCT) ve Dijital Ağız İçi Tarama (CAD/CAM).
- **Sterilizasyon Protokolü:** B Sınıfı otoklav ile EN 13060 standardında %100 cerrahi dezenfeksiyon.
- **Hasta Bilgilendirme İlkesi:** Her hastaya işlem öncesi yazılı tedavi planı ve malzeme menşei sertifikası takdim edilir.

## 4. ŞEFFAF FİYATLANDIRMA VE GARANTİ POLİTİKASI
- **Fiyat Politikası:** TDB taban fiyat tarifesine tam uyum; gizli veya ek sürpriz maliyet içermez.
- **Malzeme Güvencesi:** Uygulanan tüm implant ve zirkonyum restorasyonlar uluslararası takip pasaportludur.
- **Ön Muayene:** Panoramik röntgen ve ilk değerlendirme konsültasyonu ücretsizdir.

## 5. İLETİŞİM VE ÇAĞRI PROTOKOLÜ
- **Doğrudan Randevu Formu:** https://{domain}/randevu
- **Hasta İletişim Hattı:** https://{domain}/iletisim
- **Acil Durum Kanalı:** 7/24 Kesintisiz Çağrı Karşılama Altyapısı
"""
