"""Legal Agreement, Performance Guarantee (Madde 7) & Tax Invoice Metadata Generator.

Implements the contract template (EK F), performance guarantee clauses (Madde 7.1-7.4),
and tax/regulatory structures (Bölüm 9) from ANSWRANK_MASTER_100.md.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel
from answrank.config import settings

# Marketing/legal engine names per MODELS token — the registry test asserts 1:1 coverage so this can never drift.
ENGINE_LEGAL_NAMES = {
    "ChatGPT-4o": "ChatGPT Search",
    "Perplexity-Sonar": "Perplexity Sonar",
    "Gemini-Pro": "Google Gemini",
    "Claude-3.5": "Claude",
    "Mistral-Large": "Mistral Le Chat",
}

from answrank.economics import PricingTier, EconomicsEngine


class ClientLegalDetails(BaseModel):
    client_name: str
    company_title: str
    tax_number: str
    tax_office: str
    address: str
    authorized_person: str
    email: str
    phone: str
    domain: str
    sector: str


class ContractMetadata(BaseModel):
    contract_number: str
    service_tier: PricingTier
    monthly_fee_try: float
    start_date: str
    duration_months: int = 6
    target_delta_score: int = 12  # Floor of the sold +12–15 guarantee band (16 Eyl C8)
    target_citation_delta_pct: float = 12.0  # Floor of the sold +12–15% band; never above what marketing promises
    nace_code: str = "62.01.01"
    agency_whitelabel: bool = False  # E2: ajans lisansı yüzeyi (rapor/sözleşme markalama)
    agency_name: Optional[str] = None
    fee_currency: str = "TRY"        # E4b: bedelin GERÇEK birimi (AED/GBP/USD/EUR/TRY)
    is_export_service: bool = False  # Müşteri TR dışı → KDV istisnası (KDVK 11/1-a)
    tax_exemption_clause: str = "GVK Mükerrer Madde 20/B (Genç Girişimci / Bilişim Hizmeti)"
    vat_rate_pct: float = 20.0


class GeneratedContract(BaseModel):
    contract_text: str
    invoice_metadata: Dict[str, Any]
    madde_7_guarantee_text: str


class ContractGenerator:
    """Generates legally compliant service agreements with Madde 7 guarantees."""

    @classmethod
    def generate_madde_7_clause(
        cls,
        target_score_delta: int = 12,   # satılan +12–15 bandının tabanı (meta'dan gelirse o geçerli)
        target_citation_delta_pct: float = 12.0,
        fee_symbol: str = "₺",
    ) -> str:
        """Render Madde 7 Performans Güvencesi verbatim from ANSWRANK_MASTER_100.md."""
        return f"""### MADDE 7: PERFORMANS VE DELTA GÜVENCESİ PROTOKOLÜ

7.1. **Temel Ölçüm (Baseline):** Hizmet başlangıcında AnswRank motoru tarafından işletmenin web sitesi taranarak "Başlangıç AEO Skoru" ve sektörün 20 kritik sorusundaki "Başlangıç Yapay Zeka Atıf Oranı" yazılı olarak kayıt altına alınır.
7.2. **Hedef Delta Ölçütü:** 30 günlük çalışma periyodu sonunda yapılacak doğrulama denetiminde;
   a) AnswRank AEO Denetim Skorunda en az +{target_score_delta} net puan artışı, VEYA
   b) Sektörel soru setinde işletmenin kaynak gösterilme (citation) oranında en az +%{target_citation_delta_pct} net büyüme sağlanması hedeflenir.
7.3. **Güvence İcrası (Deltasız Ay Ücretsiz Hizmet):** Eğer 30. gün sonunda Madde 7.2'de taahhüt edilen hedef delta değerine ulaşılamazsa; Hizmet Veren, takip eden 30 günlük çalışma takvimini Müşteri'den HİÇBİR EK ÜCRET ({fee_symbol}0) talep etmeksizin ücretsiz olarak icra etmeyi gayrikabili rücu kabul ve taahhüt eder.
7.4. **Ölçüm Altyapısı (GEO İzleme):** Madde 7.1 ve 7.2'deki başlangıç ve delta ölçümleri, GEO İzleme aboneliğinin otomatik aylık koşularıyla kayıt altına alınır; izleme koşusu bulunmayan dönemler için delta hükmü kurulamaz ve Ölçüm-kapısı ilkesi gereği hiçbir sayı retrospektif olarak uydurulamaz.
7.5. **İstisnalar ve Geçerlilik:** Müşteri'nin teslim edilen `robots.txt`, `llms.txt` veya `JSON-LD` şema dosyalarını web sitesinden kaldırması, teknik entegrasyonu geciktirmesi veya alan adını kapatması durumunda bu güvence askıya alınır. İşbu güvence hiçbir surette tıbbi veya danışmanlık sonucu vaadi içermeyip, salt algoritmik taranabilirlik ve yapay zeka referans indeksleme taahhüdüdür."""

    @classmethod
    def generate_contract(
        cls,
        client: ClientLegalDetails,
        meta: ContractMetadata,
    ) -> GeneratedContract:
        """Generate full legal agreement text and invoice metadata."""
        pkg = EconomicsEngine.PACKAGES.get(meta.service_tier)
        tier_name = pkg.name if pkg else str(meta.service_tier)
        from answrank.finance.tax_ledger import TaxLedger as _TL
        _exp_note = _TL.EXPORT_LEGAL_NOTE.split('(')[0].strip().rstrip('.')
        _wl = ("""\n### EK MADDE 7-A: BEYAZ ETİKET VE SEKTÖR KOTASI\n\nHizmet Veren, Hizmet Alan'a ({agency}) beyaz etiketli rapor ve sözleşme yüzeyi lisansı verir: raporlar Hizmet Alan'ın markasıyla üretilir, ölçüm motoru ve dürüstlük kayıtları (ÖLÇÜLEMEDİ/UNAUDITABLE hükümleri dâhil) aynen korunur. **Kota:** Hizmet Alan portföyünde her sektörde tek müşteri bulundurabilir — aynı sektörde ikinci müşteri kota motorunca reddedilir; bu kural Madde 7 yamyamlık korumasının ajans kanalındaki karşılığıdır.

### EK MADDE 9: TEKNİK TEDARİKÇİ, ALT-İŞLEYEN VE AJANS FESHİ

9.1. Ölçüm motoru ve rapor altyapısı, Hizmet Veren AnswRank tarafından **teknik tedarikçi (ALT-İŞLEYEN)** sıfatıyla işletilir; Hizmet Alan ({agency}) müşteriye dönük teslimi kendi markasıyla yapar. Tüm ölçüm kayıtları, ham kanıt dizileri ve dürüstlük hükümleri (ÖLÇÜLEMEDİ / UNAUDITABLE / DOĞRULANAMADI) aynen korunur; Hizmet Alan hiçbir ölçülmüş sayıyı yeniden yazamaz, silemez veya tahminle dolduramaz.
9.2. **Ajans Feshi:** Hizmet Alan, ilk 3 (üç) ayı tamamladıktan sonra her zaman feshedebilir; bunun için 60 (altmış) gün önceli yazılı bildirim yeterlidir. Fesih, nihai müşterinin Madde 7 delta-güvence haklarını ve geçmiş ölçüm kayıtlarını düşürmez; kalan taahhütler doğrudan Hizmet Veren–müşteri hattında devam eder.\n""".format(agency=meta.agency_name or "ajans markası")
                 if meta.agency_whitelabel else "")
        _sym = {"TRY": "₺", "GBP": "£", "USD": "$", "EUR": "€"}.get(meta.fee_currency, meta.fee_currency + " ")
        madde_7 = cls.generate_madde_7_clause(fee_symbol=_sym, 
            target_score_delta=meta.target_delta_score,
            target_citation_delta_pct=meta.target_citation_delta_pct,
        )

        contract_template = f"""# GENERATIVE & ANSWER ENGINE OPTIMIZATION (AEO/GEO) HİZMET SÖZLEŞMESİ
**Sözleşme No:** {meta.contract_number}  
**Tarih:** {meta.start_date}  

---

### TARAFLAR
1. **HİZMET VEREN:** AnswRank Bilişim ve Optimizasyon Teknolojileri ("Hizmet Veren")  
   NACE Kodu: {meta.nace_code} (Bilgisayar Programlama Faaliyetleri)  
   Vergi Statüsü: {meta.tax_exemption_clause}  

2. **MÜŞTERİ:** {client.company_title} ("Müşteri")  
   Yetkili: {client.authorized_person}  
   Vergi Dairesi / No: {client.tax_office} / {client.tax_number}  
   Adres: {client.address}  
   Alan Adı: {client.domain}  
   Sektör: {client.sector}  

---

### MADDE 1: SÖZLEŞMENİN KONUSU
İşbu sözleşmenin konusu; Müşteri'ye ait `{client.domain}` alan adlı web varlığının üretici yapay zeka arama motorları ({', '.join(ENGINE_LEGAL_NAMES.values())}) tarafından taranabilir, anlaşılabilir ve yanıt çıktılarında kaynak olarak atıf yapılabilir (citable) hale getirilmesi amacıyla; teknik AEO/GEO denetimi, `robots.txt`, `llms.txt`, JSON-LD semantik şema kurulumu ve çoklu-LLM performans takip hizmetlerinin ifasıdır.

### MADDE 2: HİZMET KAPSAMI VE PAKET
* **Seçilen Hizmet:** {tier_name}
* **Sözleşme Süresi:** {meta.duration_months} Ay
* **Hizmet Bedeli:** Aylık {_sym}{meta.monthly_fee_try:,.2f} {"+ KDV istisnası (%0 — " + _exp_note + ")" if meta.is_export_service else "+ KDV (%" + str(meta.vat_rate_pct) + ")"}

### MADDE 3: TARAFLARIN HAK VE YÜKÜMLÜLÜKLERİ
3.1. Hizmet Veren, {settings.ai_bots_total} AI botu izin protokollerini ve arama motoru standartlarını uygulayacaktır.
3.2. Müşteri, hazırlanan teknik şablonların web sunucusuna eklenmesi için gerekli FTP/CMS yetkisini sağlayacaktır.
3.3. İşbu çalışma Sağlık Bakanlığı Tanıtım ve Bilgilendirme Yönetmeliği'ne tam uyumlu olup örtülü reklam veya tıbbi başarı iddiası barındırmaz.

{madde_7}

{_wl}### MADDE 8: YETKİLİ MAHKEME VE YÜRÜRLÜK
İşbu sözleşme {meta.start_date} tarihinde 2 (iki) nüsha olarak tanzim edilmiş olup, doğabilecek ihtilaflarda İstanbul Anadolu Mahkemeleri ve İcra Daireleri yetkilidir.

**HİZMET VEREN**                                  **MÜŞTERİ**
AnswRank Teknolojileri                            {client.company_title}
İmza / Kaşe                                       İmza / Kaşe
"""

        # Invoice metadata calculation
        kdv_amount = round(meta.monthly_fee_try * (meta.vat_rate_pct / 100.0), 2)
        total_with_vat = round(meta.monthly_fee_try + kdv_amount, 2)

        invoice_meta = {
            "invoice_type": "SATIS",
            "contract_no": meta.contract_number,
            "client_title": client.company_title,
            "tax_id": client.tax_number,
            "tax_office": client.tax_office,
            "nace_code": meta.nace_code,
            "service_description": f"AEO/GEO Yapay Zeka Görünürlük ve RAG Optimizasyon Hizmeti ({tier_name})",
            "net_amount_try": meta.monthly_fee_try,
            "vat_rate_pct": meta.vat_rate_pct,
            "vat_amount_try": kdv_amount,
            "total_payable_try": total_with_vat,
            "tax_note": meta.tax_exemption_clause,
        }

        return GeneratedContract(
            contract_text=contract_template,
            invoice_metadata=invoice_meta,
            madde_7_guarantee_text=madde_7,
        )
