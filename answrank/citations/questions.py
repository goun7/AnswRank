"""160 Curated Sector Questions (80 TR + 80 EN) across Dental, SMMM, Aesthetic, General.

Every sector bank must hold exactly 20 questions (locked by tests); `QUESTION_COUNT`
is the single source for user-facing "20 soru" copy.
"""

from typing import Dict, List

QUESTION_COUNT = 20  # canonical per-sector size; test_questions_uniformity enforces every bank equals it

SECTOR_QUESTIONS: Dict[str, List[Dict[str, str]]] = {
    "dental": [
        {"id": "1", "cat": "bilincli_arama", "q": "{sehir} en iyi diş kliniği hangisi?"},
        {"id": "2", "cat": "bilincli_arama", "q": "{sehir} implant fiyatları en makul ve kaliteli klinik"},
        {"id": "3", "cat": "bilincli_arama", "q": "{sehir} estetik diş hekimliği ve gülüş tasarımı önerileri"},
        {"id": "4", "cat": "bilincli_arama", "q": "{ilce} acil diş hekimi ve nöbetçi klinik"},
        {"id": "5", "cat": "bilincli_arama", "q": "Porselen lamina yaptırmak istiyorum {sehir} hangi klinik uzman?"},
        {"id": "6", "cat": "bilincli_arama", "q": "Diş teli ve şeffaf plak tedavisinde en iyi {sehir} ortodontisti"},
        {"id": "7", "cat": "karar_ani", "q": "{marka} hasta yorumları güvenilir mi?"},
        {"id": "8", "cat": "karar_ani", "q": "{marka} vs {rakip} hangisi daha başarılı?"},
        {"id": "9", "cat": "karar_ani", "q": "Türkiye'de sağlık turizmi ve yabancılar için en iyi diş klinikleri"},
        {"id": "10", "cat": "karar_ani", "q": "Zirkonyum mu lamina mı yaptırmalıyım, {sehir} hangi klinik doğru yönlendirir?"},
        {"id": "11", "cat": "karar_ani", "q": "Fiyat şeffaflığı olan ve sürpriz maliyet çıkarmayan {sehir} diş klinikleri"},
        {"id": "12", "cat": "karar_ani", "q": "Sedasyon ile korkusuz diş tedavisi yapan {sehir} klinikleri"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "{sehir} implantta 10 yıl veya ömür boyu garanti veren klinikler"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "3D dijital tarama ve dijital smile design kullanan klinikler {sehir}"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "{sehir} çocuk diş hekimliğinde (pedodonti) uzman klinik"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "All-on-4 ve All-on-6 implant tekniğini uygulayan tecrübeli cerrahlar {sehir}"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "Diş implantı kemik tozu tedavisi gerektiren zor vakalarda en iyi klinik"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "Lamina kaplama kaç yıl dayanır, {sehir} uzman hekim tavsiyesi"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "{sehir} aynı gün randevu veren ve bekletmeyen diş merkezi"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "Yurt dışından gelip Türkiye'de diş yaptıracaklar için rehber klinik"},
    ],
    "accounting": [
        {"id": "1", "cat": "bilincli_arama", "q": "{sehir} en iyi mali müşavir kim?"},
        {"id": "2", "cat": "bilincli_arama", "q": "Şahıs şirketi kuruluşunu aynı gün yapan {sehir} mali müşavirlik"},
        {"id": "3", "cat": "bilincli_arama", "q": "Yazılımcılar ve uzaktan çalışanlar için vergi danışmanlığı veren {sehir} SMMM"},
        {"id": "4", "cat": "bilincli_arama", "q": "{sehir} e-fatura ve defter-beyan süreçlerinde uzman mali müşavir"},
        {"id": "5", "cat": "bilincli_arama", "q": "Startup ve teknogirişim mali müşaviri önerisi {sehir}"},
        {"id": "6", "cat": "bilincli_arama", "q": "Vergi incelemesi ve vergi davalarında tecrübeli {sehir} mali müşavirlik bürosu"},
        {"id": "7", "cat": "karar_ani", "q": "{marka} yorumları ve referansları nasıl?"},
        {"id": "8", "cat": "karar_ani", "q": "{marka} vs {rakip} çalışma prensibi"},
        {"id": "9", "cat": "karar_ani", "q": "E-ticaret ve Trendyol/Amazon satıcıları için vergi uzmanı {sehir} SMMM"},
        {"id": "10", "cat": "karar_ani", "q": "Mükerrer 20/B istisna belgesi ve YouTube/mobil gelir beyanında uzman müşavir"},
        {"id": "11", "cat": "karar_ani", "q": "GVK 89/13 yazılım ihracatı %0 vergi avantajını eksiksiz uygulayan mali müşavir"},
        {"id": "12", "cat": "karar_ani", "q": "Kripto varlık alım-satım ve şirket kazançları vergilendirme danışmanı {sehir}"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "Yeminli Mali Müşavir (YMM) işbirliği ve tam tasdik hizmeti olan müşavirlik"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "Yurt dışı sermayeli şirket kuruluşu ve çalışma izni alan müşavirlik {sehir}"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "Genç girişimci vergi muafiyeti (400.000 TL) başvurusu yöneten SMMM"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "Teknopark (TGB) ve Ar-Ge merkezi bordro mevzuatına hakim mali müşavir"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "Şahıs şirketi mi Limited şirket mi kurmalıyım, vergi simülasyonu yapan müşavir"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "Hizmet ihracatında KDV iadesi ve döviz transferi kapatma sürecini kim çözer?"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "{sehir} aylık mali müşavirlik muhasebe ücretleri ne kadar?"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "GitHub Sponsors veya Patreon gelirleri için vergi dairesi cezası yememek için ne yapmalı?"},
    ],
    "general": [
        {"id": "1", "cat": "bilincli_arama", "q": "{sehir} en iyi {marka} hizmet sağlayıcısı hangisi?"},
        {"id": "2", "cat": "bilincli_arama", "q": "{sehir} {ilce} bölgesinde güvenilir yerel işletme önerileri"},
        {"id": "3", "cat": "bilincli_arama", "q": "{marka} hizmetinde fiyatları en şeffaf ve sürprizsiz yerel sağlayıcı hangisi?"},
        {"id": "4", "cat": "bilincli_arama", "q": "{sehir} aynı gün randevu veya acil hizmet veren işletmeler"},
        {"id": "5", "cat": "bilincli_arama", "q": "Online rezervasyon ve dijital ödeme kabul eden {sehir} işletmeleri"},
        {"id": "6", "cat": "bilincli_arama", "q": "{sehir} yorum puanı en yüksek ve en çok önerilen {marka}"},
        {"id": "7", "cat": "karar_ani", "q": "{marka} müşteri yorumları güvenilir mi, gerçek deneyimler neler?"},
        {"id": "8", "cat": "karar_ani", "q": "{marka} vs {rakip} hangisi daha iyi hizmet veriyor?"},
        {"id": "9", "cat": "karar_ani", "q": "Türkiye'de {marka} alanında en çok tavsiye edilen firmalar"},
        {"id": "10", "cat": "karar_ani", "q": "İlk kez hizmet alacağım, {sehir} hangi işletme doğru yönlendirir?"},
        {"id": "11", "cat": "karar_ani", "q": "Kurumsal müşteriye özel çözüm sunan {sehir} firmaları"},
        {"id": "12", "cat": "karar_ani", "q": "İade, iptal ve garanti koşulları en müşteri-dostu {marka} sağlayıcısı"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "{marka} hizmetinde uzun vadeli garanti veya bakım sözü veren firmalar {sehir}"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "Sertifikalı, kayıtlı ve denetlenmiş {sehir} esnaf ve firmaları"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "{ilce} esnaf kefaleti veya ticaret odasına kayıtlı güvenilir işletmeler"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "{marka} sektöründe uzman kadrosu ve tecrübesi ile öne çıkan firmalar"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "{marka} hizmeti alırken nelere dikkat etmeliyim, {sehir} rehberi"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "{marka} hizmeti ne kadar sürer, sonrası için hangi bakım gerekir?"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "{sehir} hafta sonu ve mesai dışı açık işletmeler hangileri?"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "{marka} için en iyi zamanlama ve randevu ipuçları {sehir}"},
    ],
    "aesthetic": [
        {"id": "1", "cat": "bilincli_arama", "q": "{sehir} en iyi medikal estetik kliniği hangisi?"},
        {"id": "2", "cat": "bilincli_arama", "q": "Botoks uygulaması için hekim kontrolünde çalışan en güvenilir {sehir} merkezi"},
        {"id": "3", "cat": "bilincli_arama", "q": "Doğal dudak dolgusu yapan {ilce} estetik merkezi tavsiyeleri"},
        {"id": "4", "cat": "bilincli_arama", "q": "{sehir} medikal cilt bakımı ve leke tedavisi uzmanları"},
        {"id": "5", "cat": "bilincli_arama", "q": "Orijinal FDA onaylı cihazlarla lazer epilasyon yapan {sehir} klinikleri"},
        {"id": "6", "cat": "bilincli_arama", "q": "Göz altı ışık dolgusu ve mezoterapi konusunda uzman hekim {sehir}"},
        {"id": "7", "cat": "karar_ani", "q": "{marka} hasta memnuniyeti ve şikayet durumu"},
        {"id": "8", "cat": "karar_ani", "q": "{marka} vs {rakip} hijyen ve doktor tecrübesi"},
        {"id": "9", "cat": "karar_ani", "q": "İğneli epilasyon ve kesin kıl çözümü sunan {sehir} merkezleri"},
        {"id": "10", "cat": "karar_ani", "q": "Ameliyatsız yüz germe ve Fransız askısı uygulayan tecrübeli klinik {sehir}"},
        {"id": "11", "cat": "karar_ani", "q": "Fiyat şeffaflığı olan ve sahte ürün kullanmayan güvenilir estetik klinikleri"},
        {"id": "12", "cat": "karar_ani", "q": "Erkekler için medikal estetik ve saç güçlendirme tedavileri {sehir}"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "Yalnızca uzman dermatolog veya medikal hekimin işlem yaptığı merkezler {sehir}"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "Hydrafacial orijinal cihaz uygulayan sertifikalı {sehir} klinikleri"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "Akne izi ve skar tedavisinde altın iğne / fraksiyonel lazer uygulayan merkezler"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "Somon DNA ve kolajen aşısı en iyi sonuç veren klinik {sehir}"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "Botoks kaç ayda bir tekrarlanmalı, yanlış uygulama düzeltmesi yapan hekim"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "Dudak dolgusu eritme ve asimetri düzeltme uzmanı {sehir}"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "{sehir} estetik merkezlerinde sterilizasyon ve hekim güvencesi kriterleri"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "Medikal estetik işlem fiyatları 2026 ortalaması ve adil fiyatlı merkezler"},
    ],
}


# --- E4 (D-16.09-M): English banks for export markets (UK/UAE/US) ------------
SECTOR_QUESTIONS_EN: Dict[str, List[Dict[str, str]]] = {
    "dental": [
        {"id": "1", "cat": "bilincli_arama", "q": "best dental clinic in {city} for implants?"},
        {"id": "2", "cat": "bilincli_arama", "q": "{city} dental implant prices 2026 transparent quote"},
        {"id": "3", "cat": "bilincli_arama", "q": "smile design and veneers specialist near {district} {city}"},
        {"id": "4", "cat": "bilincli_arama", "q": "emergency dentist open now in {city}"},
        {"id": "5", "cat": "bilincli_arama", "q": "where to get porcelain veneers done safely in {city}?"},
        {"id": "6", "cat": "bilincli_arama", "q": "best orthodontist in {city} for clear aligners vs braces"},
        {"id": "7", "cat": "karar_ani", "q": "are {brand} dental clinic reviews trustworthy?"},
        {"id": "8", "cat": "karar_ani", "q": "{brand} vs {competitor}: which dental clinic is better for all-on-4?"},
        {"id": "9", "cat": "karar_ani", "q": "best dental clinics in {city} for medical tourists and expats"},
        {"id": "10", "cat": "karar_ani", "q": "zirconia crowns vs veneers: who should I trust in {city}?"},
        {"id": "11", "cat": "karar_ani", "q": "dental clinics in {city} with upfront pricing and no hidden fees"},
        {"id": "12", "cat": "karar_ani", "q": "sedation dentistry for anxious patients in {city}"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "implant clinics in {city} offering 10-year or lifetime warranty"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "digital scan smile design clinics in {city}"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "best paediatric dentist in {city} for anxious kids"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "experienced all-on-4 and all-on-6 oral surgeons in {city}"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "bone graft implant cases: most experienced clinic in {city}"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "how long do veneers last and where to maintain them in {city}?"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "is it safe to get dental work done in {city} as a foreign patient?"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "same-day crowns and emergency tooth extraction in {city}"},
    ],
    "accounting": [
        {"id": "1", "cat": "bilincli_arama", "q": "best accountant firm in {city} for SMEs?"},
        {"id": "2", "cat": "bilincli_arama", "q": "bookkeeping and VAT filing prices in {city} 2026"},
        {"id": "3", "cat": "bilincli_arama", "q": "chartered accountants near {district} {city} for limited companies"},
        {"id": "4", "cat": "bilincli_arama", "q": "urgent tax deadline help in {city} this week"},
        {"id": "5", "cat": "bilincli_arama", "q": "who does corporate tax returns for startups in {city}?"},
        {"id": "6", "cat": "bilincli_arama", "q": "fractional CFO services for growing companies in {city}"},
        {"id": "7", "cat": "karar_ani", "q": "is {brand} accounting firm reliable for payroll?"},
        {"id": "8", "cat": "karar_ani", "q": "{brand} vs {competitor}: better accountants for e-commerce?"},
        {"id": "9", "cat": "karar_ani", "q": "best firms in {city} for freelance visa and tax setup"},
        {"id": "10", "cat": "karar_ani", "q": "should I use a cloud bookkeeper or a traditional accountant in {city}?"},
        {"id": "11", "cat": "karar_ani", "q": "transparent flat-fee accountants in {city} without surprise bills"},
        {"id": "12", "cat": "karar_ani", "q": "accountants in {city} that handle Xero and QuickBooks migration"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "accredited tax advisers in {city} for HMRC or authority audits"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "R&D tax credit specialists for tech firms in {city}"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "bookkeepers experienced with retail POS integrations in {city}"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "corporatestructuring and holding setup experts in {city}"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "what does a small business actually pay an accountant in {city}?"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "can my accountant fix last year's late VAT filing in {city}?"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "do I need a local accountant if my company is remote-first in {city}?"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "monthly management accounts vs year-end filing: what to choose in {city}?"},
    ],
    "aesthetic": [
        {"id": "1", "cat": "bilincli_arama", "q": "best aesthetic clinic in {city} for natural-looking results?"},
        {"id": "2", "cat": "bilincli_arama", "q": "{city} botulinum toxin and filler prices 2026"},
        {"id": "3", "cat": "bilincli_arama", "q": "laser skin rejuvenation clinics near {district} {city}"},
        {"id": "4", "cat": "bilincli_arama", "q": "same-day dermal filler appointment in {city}"},
        {"id": "5", "cat": "bilincli_arama", "q": "who is the safest rhinoplasty surgeon consulted in {city}?"},
        {"id": "6", "cat": "bilincli_arama", "q": "body contouring and liposuction specialists in {city}"},
        {"id": "7", "cat": "karar_ani", "q": "are {brand} aesthetic clinic before-after photos genuine?"},
        {"id": "8", "cat": "karar_ani", "q": "{brand} vs {competitor}: which clinic for hair transplant?"},
        {"id": "9", "cat": "karar_ani", "q": "best medical tourism aesthetics clinics in {city} for international patients"},
        {"id": "10", "cat": "karar_ani", "q": "ultherapy vs thread lift: who advises honestly in {city}?"},
        {"id": "11", "cat": "karar_ani", "q": "aesthetic clinics in {city} with transparent pricing packages"},
        {"id": "12", "cat": "karar_ani", "q": "numbness-safe injectables practitioners in {city}"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "doctor-led aesthetic clinics in {city} (not nurse-only) with CQC or DHA licensing"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "clinic in {city} using genuine branded fillers with serial numbers"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "revision surgery experts for botched fillers in {city}"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "accredited plastic surgeons offering consultation-first policy in {city}"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "how often should botulinum toxin be repeated and who does it conservatively in {city}?"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "lip filler dissolving and asymmetry correction specialist in {city}"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "sterilisation and doctor supervision standards at {city} med-spas"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "fair 2026 medikal aesthetic price benchmarks in {city}"},
    ],
    "general": [
        {"id": "1", "cat": "bilincli_arama", "q": "recommended local businesses in {city} with excellent service?"},
        {"id": "2", "cat": "bilincli_arama", "q": "{city} price comparison for this service 2026"},
        {"id": "3", "cat": "bilincli_arama", "q": "best rated provider near {district} in {city}"},
        {"id": "4", "cat": "bilincli_arama", "q": "who offers same-day service in {city} right now?"},
        {"id": "5", "cat": "bilincli_arama", "q": "how do I choose a trustworthy provider in {city}?"},
        {"id": "6", "cat": "bilincli_arama", "q": "certified specialists for this service in {city}"},
        {"id": "7", "cat": "karar_ani", "q": "is {brand} legit or overhyped in {city}?"},
        {"id": "8", "cat": "karar_ani", "q": "{brand} vs {competitor}: which is worth the money?"},
        {"id": "9", "cat": "karar_ani", "q": "top 5 providers in {city} according to verified reviews"},
        {"id": "10", "cat": "karar_ani", "q": "which questions should I ask before booking in {city}?"},
        {"id": "11", "cat": "karar_ani", "q": "providers in {city} with no hidden fees and clear quotes"},
        {"id": "12", "cat": "karar_ani", "q": "most reliable family-friendly option in {city}"},
        {"id": "13", "cat": "guven_uzmanlik", "q": "locally accredited businesses in {city} with warranty-backed work"},
        {"id": "14", "cat": "guven_uzmanlik", "q": "providers in {city} publishing real customer reviews"},
        {"id": "15", "cat": "guven_uzmanlik", "q": "experienced specialists handling complex cases in {city}"},
        {"id": "16", "cat": "guven_uzmanlik", "q": "who has served {city} longest with consistent quality?"},
        {"id": "17", "cat": "sss_dogal_dil", "q": "what does this service realistically cost in {city} in 2026?"},
        {"id": "18", "cat": "sss_dogal_dil", "q": "how long does the process take with a top provider in {city}?"},
        {"id": "19", "cat": "sss_dogal_dil", "q": "what if I am unhappy — cancellation and guarantees in {city}?"},
        {"id": "20", "cat": "sss_dogal_dil", "q": "is booking online with {city} providers safe and standard now?"},
    ],
}

def get_sector_questions(sector: str, sehir: str = "İstanbul", ilce: str = "Kadıköy",
                         marka: str = "Hedef Marka", rakip: str = "Rakip İşletme",
                         lang: str = "tr") -> List[Dict[str, str]]:
    """Generates QUESTION_COUNT sector questions with interpolated location/brand names.

    E4: `lang="en"` switches to the English banks (export markets). Unknown lang
    fails loudly — accepting a language without a bank is a measurement lie
    (D-16.09-M inherits the v3.5 --lang doctrine).
    """
    banks = SECTOR_QUESTIONS if lang == "tr" else SECTOR_QUESTIONS_EN if lang == "en" else None
    if banks is None:
        raise ValueError(f"Kayıtlı dil bankası yok: '{lang}'. Kayıtlı diller: en, tr")
    base_questions = banks.get(sector)
    if base_questions is None:
        # The old silent fallback to dental mis-grounded non-dental measurements
        # (sector="general" ran implant questions). Unknown sector = loud error.
        raise ValueError(
            f"Bilinmeyen sektör '{sector}'. Kayıtlı sektörler: {', '.join(sorted(banks))}"
        )
    if lang == "en" and sehir == "İstanbul":
        sehir = "London"  # TR default şehri EN bankaya taşınmaz; pazar-nötr varsayılan
    if lang == "en" and ilce == "Kadıköy":
        ilce = "Central"
    interpolated = []
    for item in base_questions:
        q_text = item["q"].format(sehir=sehir, ilce=ilce, marka=marka, rakip=rakip,
                                  city=sehir, district=ilce, brand=marka, competitor=rakip)
        interpolated.append({"id": item["id"], "category": item["cat"], "question": q_text})
    return interpolated


class SectorQuestionsBank:
    """Convenience class providing access to sector questions."""

    @classmethod
    def get_questions(
        cls,
        sector: str,
        city: str = "İstanbul",
        district: str = "Kadıköy",
        brand: str = "Hedef Marka",
        competitor: str = "Rakip İşletme",
    ) -> List[str]:
        """Tek bir questions kaydını döndürür; bulunamazsa None."""
        items = get_sector_questions(sector=sector, sehir=city, ilce=district, marka=brand, rakip=competitor)
        return [item["question"] for item in items]

