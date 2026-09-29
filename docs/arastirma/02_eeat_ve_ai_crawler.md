# E-E-A-T ve AI Crawler Direktifleri — Denetim Gereksinimleri

**Derleme tarihi:** 2026-09-28
**Zero-trust protokolü:** Aşağıdaki her bilgi kaynaktan bizzat okunmuştur. OpenAI ve Google'ın
resmi doküman sayfaları bu oturumda JS-rendering + 404 yüzünden okunamamıştır; bu durum
açça belirtilmiş ve bu kısımlar **"DOĞRULANAMADI"** olarak işaretlenmiştir.

---

## BÖLÜM A — E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness)

### A.1. Çerçeve

E-E-A-T, Google'ın arama kalitesi değerlendirme çerçevesidir. İlk "E" (Experience) Aralık 2022'de
eklendi. İki türlü uygulanır:

1. **Algoritmik sinyal** — içerik kalitesi güncellemelerinde (helpful content system) ağırlıklı
2. **İnsan değerlendirici yönergesi** — Search Quality Rater Guidelines'da tanımlı

**Sağlık dikeyi (YMYL — Your Money or Your Life):** Tıbbi/diş içeriği en yüksek risk
sınıfındadır; değerlendiricilerden bu sayfalarda üst düzey E-E-A-T beklenir. Bir Dubai diş
kliniği sayfası bu sınıfa girer.

**Resmi Google dokümantasyonu bu oturumda DOĞRULANAMADI**
(`developers.google.com/search/docs/...` URL'leri 404 / JS-rendered). Aşağıdaki madde işaretleri
endüstrideki yerleşik yorumlama ve mevcut `GEO_LITERATUR_TARAMA` dosyasındaki **doğrulanmış**
sağlık-dikeyi araştırmalarına dayanır.

### A.2. Sağlık dikeyi için doğrulanmış akademik kanıt

Mevcut `GEO_LITERATUR_TARAMA_2026-BAHAR.md` dosyasından (hepsi orijinal kaynaktan okunmuş):

| Kaynak | Bulgu (kaynaktan birebir) | Diş kliniğine çıkarımı |
|---|---|---|
| Zha & Chang 2026, arXiv:2609.06798 | Aynı sorgu ülkenin resmi dilinde sorulduğunda yerli-kaynaklı atıf payı **3,5–13,5 kat** artıyor | Dubai'de İngilizce içerik gereki; dil lokalizasyonu E-E-A-T'in ön koşulu |
| Nguyen et al. 2026, arXiv:2609.00319 | İlk 10 domain İngilizce atıfların **%43,6**'sını alıyor; gov/commercial-health/academic ~%22'şer | Diş kliniği "commercial-health" sınıfında; devlet/akademik kaynaklarla rekabet ettiği için kurum-sinyali inşası şart |
| Hu et al. 2025/26, arXiv:2511.12920 | Tıbbi güvenlik uyarısı AI Overview yanıtlarının **%11**'inde, Featured Snippet'lerin **%7**'sinde | Açık güvenlik/disclaimer blokları hem etik hem sinyal — sağlık dikeyinde neredeyse standart beklenti |
| Grossman et al. 2026, arXiv:2604.27790 | Google'ın AI crawler'ını engelleyen siteler AI Overview'da **anlamlı daha az** alınıyor | E-E-A-T'ten önce "erişilebilir olma" gelir: AI crawler izni teknik ön koşul |

### A.3. Sayfadaki somut E-E-A-T sinyalleri (kodda aranacak)

Bir Dubai diş kliniği sayfasında denetlenecek sinyaller — her biri regex/parse ile tespit edilebilir:

**Experience (Deneyim)**
- Prosedür öncesi/sonrası görsel galerisi (`before`, `after`, `gallery`, `case` ipuçları)
- Hasta yorumları / testimonial bölümleri (`review`, `testimonial`, `patient`)
- Tedavi edilen vaka sayısı (`cases treated`, `patients`, `20 years` gibi sayısal deneyim)
- Yorum/lisans tarihi gösterimi (güncellik)

**Expertise (Uzmanlık)**
- Doktor/diş hekimi by-line'ı ve kısa biyografisi (sayfada isim + unvan geçiyor mu)
- Uzmanlık alanları listesi (implant, ortodonti, beyazlatma...)
- Eğitim/lisans/sertifika göstergeleri (`BDS`, `DDS`, `MDS`, `Fellowship`, `certified`)
- Klinik/dernek üyelikleri (`member of`, `association`, `society`)

**Authoritativeness (Otorite)**
- Schema.org `Dentist` / `LocalBusiness` / `MedicalBusiness` varlığı
- Basın refereansları / ödüller (`awarded`, `featured in`, medya logoları)
- Dış kaynaklardan alıntı/anıltım işaretleri

**Trustworthiness (Güven)**
- İletişim bilgileri: telefon, e-posta, fiziksel adres (NAP — Name, Address, Phone)
- Harita gömme (Google Maps embed) → yerel işaret
- Açık fiyatlandırma veya fiyat aralığı (`price`, `from AED`, `consultation fee`)
- Gizlilik politikası / hasta gizliliği (HIPAA/GDPR belirtileri)
- Sosyal kanıt bağlantıları (Instagram, Google Business linkleri)
- Güvenlik: HTTPS, geçerli sertifika

### A.4. KOD GEREKSİNİMLERİ — E-E-A-T için

HTML gövdesi üzerinde (uret_rapor.py'nin `yapilandirma()` fonksiyonunu genişleterek):

```python
# Denetlenecek signal listesi (her biri test edilebilir):
EEAT_SINYALLERI = {
    # Expertise
    "doktor_byline":      r"(?i)(dr\.?\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+|dentist\s+name|by\s+dr)",
    "uzmanlik_unvani":    r"(?i)\b(BDS|DDS|MDS|DMD|Fellowship|Specialist|Consultant)\b",
    "sertifika":          r"(?i)(certif|accredited|licensed|licens)",
    # Authoritativeness
    "schema_dentist":     r"(?i)application/ld\+json[^>]*>.*?[\"']@(type|context)[\"']",
    "odul_referansi":    r"(?i)(award|featured\s+in|as\s+seen\s+in|press)",
    # Trustworthiness
    "telefon":            r"(?i)(tel:|\+\d{1,4}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4})",
    "email_kontak":       r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}",
    "fiziksel_adres":     r"(?i)(street|road|avenue|building|tower|office|mall|floor)",
    "harita_embed":       r"(?i)(google\.com/maps|maps\.google|embed.*map|iframe.*maps)",
    "fiyat_bilgisi":      r"(?i)(aed|dirham|price|cost|fee|from\s+\d|consultation)",
    "gizlilik_politikasi": r"(?i)(privacy\s+policy|gdpr|hipaa|patient\s+privacy)",
    # Experience
    "hasta_yorumu":       r"(?i)(testimonial|patient\s+review|what\s+our\s+patients|reviews)",
    "before_after":       r"(?i)(before\s*&?\s*after|case\s+study|galer|gallery)",
    "deneyim_rakami":     r"(?i)(\d+\+?\s*(years|yıl|cases|patients|implants))",
}
```

Skorlama: her sinyal 1 puan, 4 kategoriden (E-E-A-T) her biri için alt puan; toplam 0-16.
Eksik kategori "engelleyici" (blocking) olarak raporlanır — örneğin "Trustworthiness 0/4"
kırmızı bayrak. Bu sinyaller **kesinlikçi** değildir (regex yanıltıcı pozitifler üretir);
raporda "sinyal tespit edildi" diye sunulmalı, "Google E-E-A-T puanınız X" DENMEMELİDİR.

---

## BÖLÜM B — AI Crawler Direktifleri

### B.1. Doğrulanmış crawler listesi

**Perplexity — DOĞRULANDI** ([docs.perplexity.ai/docs/resources/perplexity-crawlers](https://docs.perplexity.ai/docs/resources/perplexity-crawlers), HTTP 200, 2026-09-28):

| User-agent | Tam UA string (kaynaktan birebir) | Ne işe yarar | robots.txt'e saygı |
|---|---|---|---|
| **PerplexityBot** | `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)` | "designed to surface and link websites in search results on Perplexity. It is **not** used to crawl content for AI foundation models." | EVET — "To ensure your site appears in search results, we **recommend allowing PerplexityBot** in your site's robots.txt file" |
| **Perplexity-User** | `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)` | Kullanıcı sorusu olduğunda sayfayı ziyaret edip yanıta link ekler | HAYIR — "Since a user requested the fetch, this fetcher generally **ignores** robots.txt rules." |

**Kritik çıkarım:** PerplexityBot engellemek, Perplexity arama sonuçlarında **görünmemeye** yol
açar. Bu, AI görünürlük denetiminde doğrudan bir risk sinyalidir.

**OpenAI GPTBot / Google-Extended / CCBot / Bytespider / anthropic-ai / Applebot-Extended:**
Bu user-agent isimleri endüstride yaygın olarak bilinmektedir ancak **resmi dokümantasyon
sayfaları bu oturumda DOĞRULANAMAMIŞTIR**:
- `developers.openai.com/api/docs/bots` → HTTP 200 ama JS-rendered, sadece navigasyon menüsü dönüyor
- `developers.google.com/search/docs/crawling-indexing/google-extended` → HTTP 404

Bu yüzden kod bu isimleri **bilinen-endüstri-listesi** olarak işler ve raporda
"endüstri listesi, resmi kaynaktan bu oturumda doğrulanmadı" notuyla sunar.

### B.2. robots.txt'te AI crawler yönetimi — mantık

robots.txt (RFC9309) iki alan içerir: `User-agent:` grupları ve `Allow:`/`Disallow:` kuralları.
AI crawler denetimi için algoritma:

1. robots.txt'i `https://{domain}/robots.txt`'ten çek (yoksa "bilinmiyor" — varsayılan izin)
2. Tüm `User-agent:` gruplarını parse et
3. Her bilinen AI agent'ı için, **en spesifik eşleşen** grubu bul:
   - Önce tam isim (`PerplexityBot`), sonra `*` (genel) grubu
4. Grubun kurallarından yol eşleşmesiyle Allow/Disallow kararı ver:
   - `/` disallow → agent engelli
   - Spesifik yol (örn. `/private/`) → o yol engelli, genel erişim açık
5. **Çelişki kuralı (RFC9309, DOĞRULANDI — rfc-editor.org/rfc/rfc9309.txt satır 253-258):**
   > "The most specific match found MUST be used. The most specific match is the match that has
   > the most octets. ... If an 'allow' rule and a 'disallow' rule are equivalent, then the
   > **'allow' rule SHOULD be used**. If no match is found amongst the rules in a group for a
   > matching user-agent or there are no rules in the group, the URI is **allowed**."

   Yani: en uzun yol kazanır; **eşit uzunlukta ALLOW önceliklidir**; eşleşme yoksa varsayılan
   İZİNLİDİR.

### B.3. Örnek robots.txt desenleri (denetimde karşılaşılabilir)

```
# 1) AI crawler'ları tamamen engelleme (RİSKLİ)
User-agent: GPTBot
Disallow: /
User-agent: Google-Extended
Disallow: /

# 2) AI crawler'lara izin (önerilen)
User-agent: *
Allow: /
Disallow: /admin/
```

Grossman et al. 2026 (arXiv:2604.27790, DOĞRULANDI): "Google'ın AI crawler'ını engelleyen
siteler AIO'da anlamlı daha az alınıyor." Yani desen #1 AI görünürlüğünü azaltan bir risk
sinyalidir.

### B.4. KOD GEREKSİNİMLERİ — AI crawler denetimi için

```python
# Bilinen AI crawler user-agent'ları (resmi ad olarak; UA string değil)
AI_CRAWLERLARI = {
    "GPTBot":          {"sahip": "OpenAI (ChatGPT)",          "dogrulandi": False},
    "Google-Extended": {"sahip": "Google (AI Overview/Gemini)","dogrulandi": False},
    "PerplexityBot":   {"sahip": "Perplexity",                "dogrulandi": True},
    "Perplexity-User": {"sahip": "Perplexity (user fetch)",   "dogrulandi": True},
    "CCBot":           {"sahip": "Common Crawl",              "dogrulandi": False},
    "anthropic-ai":    {"sahip": "Anthropic (Claude)",        "dogrulandi": False},
    "Bytespider":      {"sahip": "ByteDance",                 "dogrulandi": False},
    "Applebot-Extended":{"sahip": "Apple (Apple Intelligence)","dogrulandi": False},
}

# robots.txt parser fonksiyonları:
#   robots_parse(metin) -> {user_agent: [( yol, allow_bool), ...]}
#   robots_engelli_mi(parse_edilmis, agent_adi, yol="/") -> bool
#   ai_crawler_izni(domain) -> {agent: {"engelli": bool, "neden": str}}
```

Test senaryoları:
- robots.txt yok → tüm agent'lar "belirsiz/izin varsay" durumunda
- `User-agent: * / Disallow: /` → tüm agent'lar engelli
- Sadece `GPTBot` disallow → sadece GPTBot engelli, diğerleri açık
- `Allow: /` ile `Disallow: /admin/` → genel açık, admin engelli
- Bozuk/HTML döndüren robots.txt → parse hatası sinyali

Raporlama: engelli AI crawler sayısı **negatif risk sinyali** olarak AI görünürlük skoruna
düşük ağırlıkla katılır; her engelli agent için insan-dilinde açıklama yazılır.

---

## Kaynaklar

- [Perplexity Crawlers](https://docs.perplexity.ai/docs/resources/perplexity-crawlers) —
  DOĞRULANDI (HTTP 200, 2026-09-28): PerplexityBot + Perplexity-User tam UA string ve davranış
- [llmstxt.org](https://llmstxt.org/) — DOĞRULANDI (HTTP 200)
- `GEO_LITERATUR_TARAMA_2026-BAHAR.md` — Zha 2026, Nguyen 2026, Hu 2025/26, Grossman 2026 (hepsi
  orijinal arXiv kaynağından okunmuş, DOĞRULANDI)
- OpenAI bots dokümanı + Google Search Essentials — **DOĞRULANAMADI** (JS-render / 404)
