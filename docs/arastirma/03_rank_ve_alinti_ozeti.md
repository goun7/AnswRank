# Sıralama → AI Alıntı Olasılığı: Kanıt Özeti ve Skor Tasarımı

**Derleme tarihi:** 2026-09-28
**Kaynak:** Bu dosyanın TÜM sayısal içerikleri
`/home/gokun/projects/02_sahis/85-AnswRank/GEO_LITERATUR_TARAMA_2026-BAHAR.md`
dosyasından alınmıştır; orada her sayı orijinal kaynaktan (arXiv tam metin / API özeti)
bizzat okunmuştur (zero-trust protokolü, 2026-09-15 derlemesi).

---

## 1. KANIT — Google sıralaması AI alıntısını güçlü biçimde yorduyor

### 1.1. CiteChoice nedensel deneyi (en güçlü tek kanıt)

**Kaynak:** Selvam & Ghosh (2026), "CITECHOICE: A Causal Audit of How Document Presentation
Redistributes Citation Credit in Agentic Search", arXiv:2609.15164v1
GPT-5.4 alıcısı + Exa araması; 129/130 sorgu transkripti, 1.490 belge, 113 eş, 452 deneme,
89 family; hash-doğrulamalı 2×2 karşı-faktürel replay.

**Birebir okunan sayılar:**

| Ölçüm | Sayı | Anlamı |
|---|---|---|
| Rank-1'de atıf oranı | **%85,1** | 1. sıradaki kaynak yanıtların ~%85'inde alıntılanıyor |
| Rank-5'te atıf oranı | **%42,8** | 5. sıraya düşüşte yarıya yakın düşüş |
| Gözlemsel fark | **42,3 pp** | Korelasyonel etki (bütün karışıklık dahil) |
| Kontrollü sıralama değiştirmede | **+7,9 pp** | Nedensel pay (daha küçük ama gerçek) |
| Holdout doğrulamada | **0,0 pp** | Sıralama etkisinin bir kısmı model-aşina kaynaklardan |
| Structured rendering | **+0,50 atıf/yanıt** | Nedensel (%95 CI [+0,20;+0,84]; Holm p=,033) |
| İkili karar tekrarında flip | **%15** | Aynı sorgu tekrarlanınca kararların %15'i değişiyor |
| Varyansın decoding kaynağı | **%45** | Gürültü tabanı |

**Çıkarım:** Sıralama ALINTIYI yordayan en güçlü tek gözlemsel sinyaldir (85,1% → 42,8%),
ama nedensel payı sınırlıdır. **Bu yüzden üst-3 sıralamayı skorda yüksek, ama tek başına
baskın olmayacak şekilde ağırlıklandırmalıyız.**

### 1.2. Tek-çekim ölçüm YASAK (Schulte et al.)

**Kaynak:** Schulte, Bleeker, Kaufmann (2026), "Don't Measure Once", arXiv:2604.07585v1
4 motor (ChatGPT, Gemini, Google AI Mode, Perplexity), 4 dikey, 8 prompt, 45–46 gün, 4.044
gün-çifti.

| Ölçüm | Sayı |
|---|---|
| Gün-güne kaynak Jaccard | **0,34–0,42** ("~%65 of all sources change from one day to the next") |
| Aynı gün ≤24s tekrarda kaynak Jaccard | **0,32–0,43** (ChatGPT 0,233, Perplexity 0,282, Gemini 0,505, AI Mode 0,318) |
| Marka Jaccard | 0,45–0,59 |
| Atıf konsantrasyonu Gini | **0,715** (AI Mode 0,782 en yüksek, Perplexity 0,671) |
| Marka için SE<0,10 gereken run | **n=7–8** |
| Kaynak için SE<0,10 / SE<0,05 | **d=10 / d=24** |
| ChatGPT run'larında sıfır atıf | **%57,8** |

**Çıkarım:** ChatGPT sorguların **%57,8'inde hiç atıf vermeden** dönüyor. Tek bir ölçümde
"alıntı alamadınız" demek yanlıştır. Bizim ürünümüz Google sıralamasını (Serper) ölçtüğü için
bu gürültüden kısmen korunur — ama raporda "bu tek-çekim bir ölçümdür, AI yanıtları
gün-güne %65 değişir" uyarısı ŞARTTIR.

### 1.3. Hangi içerik alıntılanıyor? (Vishwakarma + Kai)

**Vishwakarma et al. 2026** (Sprinklr), SIGIR '26, arXiv:2605.25517v1:
252.000 deneme, 6 LLM, 1.440 senaryo, mixed-effects odds-ratio.

| Faktör | Odds-ratio | Güç |
|---|---|---|
| Konu relevansı (On-Topic) | **>>10k** (GPT-5-Nano'da 221) | En güçlü |
| Sorgu terimleri sayfada | **5,99–40,0** | Çok güçlü |
| Fiyat bilgisi | **>>10k / 36,1** | Çok güçlü |
| Spesifikasyon içeriği | **8,63–243** | Güçlü |
| Kendinden-emîn vs hedged | 2,67–754 | Bağlı |
| **Structured-vs-Dense (sadece format)** | **0,78–1,68** | **ZAYIF — bazı modellerde <1** |

**Kritik:** "formatting-only edits have little impact". Yani salt "şık format" atıf getirmiyor;
**içerik derinliği ve sorgu terimlerine uygunluk** getiriyor.

**Kai, Xinyue, Jingang 2026**, arXiv:2604.25707v2 (geo-citation-lab):
602 prompt × 3 motor, 21.143 arama-katmanı atıfı, 23.745 atıf kaydı, 18.151 sayfada 72 özellik.

> "citation breadth and citation depth **diverge**. Perplexity and Google cite more sources on
> average, while ChatGPT cites fewer sources but shows substantially higher average citation
> influence among fetched pages"
> Yüksek-etkili sayfalar: "**longer, more structured, semantically aligned, and richer in
> extractable evidence**"

**Çıkarım:** Sayfa uzunluğu + yapı + çıkarılabilir kanıt zenginliği → alıntı etkisi.
Bunlar `uret_rapor.py`'nin mevcut HTML analizinden (H1, title, meta, schema) **içerik
derinliği** göstergesi olarak çıkarılabilir.

### 1.4. Küçük markaların şansı ve "listicle" kanalı (Kumar/Ranqo)

**Kaynak:** Kumar 2026 (Ranqo), arXiv:2606.20065v1 — 100K+ prompt-yanıtı, 100+ marka.

| Segment | İlk-run'da yanıtlarda görünme |
|---|---|
| Global markalar | **%73** |
| Orta segment | **%44** |
| **Niş/küçük markalar** | **%11** |

| Atıf formatı | Pay |
|---|---|
| **"Ranked best-of listicle"** | **~%21** (en çok atıf alan format) |
| Atıfların kurumsal sitelere | ~%78 |

**Çıkarım (Dubai diş kliniği için):** Kliniğimiz "%11'lik niş" katmanında. En kısal yol
sıralama yükseltmekten ziyade **"best dentist Dubai" listicle'larına girmektir** (toplam
atıfların ~%21'i bu formata gider). Bu yüzden rapor: "klinik domain'i sorgularda kaçıncı"
sorusuna ek olarak **"hangi listicle/rakip siteler üst sırada"** raporunu VERMELİDİR
(rakip analizi özelliğinin bilimsel gerekçesi budur).

### 1.5. AI Overview aktivasyonu ve birinci-sayfa dışı kaynaklar (Xu)

**Kaynak:** Xu, Iqbal, Montgomery 2026, arXiv:2605.14021v1 — 55.393 trend sorgu, 19 kategori.

| Ölçüm | Sayı |
|---|---|
| Genel AIO aktivasyonu | **%13,7** |
| **Soru-formu sorgularda** AIO aktivasyonu | **%64,7** |
| AIO'nun atıf verdiği domainlerin 1. sayfada OLMAYAN payı | **~%30** |
| Atomik claim'lerin atıflanan sayfada desteksiz olması | **%11,0** |

**Çıkarım:** "diş hekimi Dubai'de en iyisi kim" gibi **soru-formu sorgular %64,7 oranında AI
Overview üretir** — bizim sorgu kümemiz soru-formu + kategori karışımı olmalıdır. Ayrıca
1. sayfada olmayan ~%30'luk pencere, sayfa-2 sıralamaya rağmen AI alıntısı şansı olduğunu
gösterir (skor 0 demek için ilk-10 dışı kullanılmamalı).

### 1.6. Crawler izni (Grossman) + sağlık-dikeyi lokalizasyon (Zha)

**Grossman et al. 2026**, arXiv:2604.27790v1: temsilî sorguların **%51,5**'inde AIO üretiliyor;
sistemler arası kaynak örtüşmesi Jaccard **<0,2**; **"Google'ın AI crawler'ını engelleyen
siteler AIO'da anlamlı daha az alınıyor"**.

**Zha & Chang 2026**, arXiv:2609.06798: aynı sorgu ülkenin resmi dilinde sorulduğunda
yerli-kaynaklı atıf payı **3,5–13,5 kat** artıyor.

**Çıkarım:** (a) AI crawler engellemek bir risk sinyalidir (robots.txt denetimi skora girer);
(b) İngilizce sorgu kümesi Dubai için doğrudur (yerli dil = İngilizce, UAE).

---

## 2. TASARIM — AI Alıntı Olasılık Skoru (0-100)

Yukarıdaki kanıtlardan türetilmiş, **dört alt-pilli** bir skor. Her alt-pill kanıtlanmış bir
sinyal ailesini temsil eder.

### 2.1. Alt-pill 1: Sıralama Gücü (ağırlık: **45/100**)

Kanıt: CiteChoice rank-1 %85,1 → rank-5 %42,8 (§1.1); Xu §1.5.

Serper `organic[].position` ile klinik domain'i sorgu kümesinde bulunur. Her sorgu için
puanlama (position → puan):

| position | puan | gerekçe |
|---|---|---|
| 1 | 100 | CiteChoice rank-1 atıf %85,1 |
| 2–3 | 85 | Üst-3 "AI'lerin alıntıladığı bölge" |
| 4–10 | 60 | İlk sayfa; AIO atıflarının ~%70'i buradan |
| 11–20 | 30 | Sayfa-2; AIO atıflarının ~%30'u 1. sayfada değil (Xu) |
| 21+ | 10 | Zayıf |
| **bulunamadı** | 0 | Sorguda yok |

Sorgu-kümesi ortalaması alınır. **Üst-3 oranı** ek metrik olarak raporlanır.

### 2.2. Alt-pill 2: İçerik Derinliği (ağırlık: **25/100**)

Kanıt: Kai §1.3 ("longer, more structured, richer in extractable evidence"); Vishwakarma §1.3
(relevans OR >>10k, sorgu terimleri OR 5,99–40).

Sinyaller (her biri puanlanır, max 25):
- Schema.org Dentist/LocalBusiness var: **8** (structured rendering +0,50 atıf/yanıt, CiteChoice)
- Sayfa metin uzunluğu (kelime): >1000 kelime **6**, 500–1000 **4**, <500 **1** (Kai "longer")
- FAQ bölümü var (soru-formu içerik = AIO %64,7, Xu): **5**
- H1 + meta description + title uyumu (relevans proxy): **6**

### 2.3. Alt-pill 3: AI Erişilebilirliği (ağırlık: **20/100**)

Kanıt: Grossman §1.6 (crawler engeli AIO'yu azaltıyor); llms.txt standardı (zayıf sinyal).

- robots.txt var ve AI crawler'ları engellemiyor: **8** (her engelli önemli agent için −3)
- sitemap.xml var: **4** (keşif altyapısı)
- HTTPS + erişilebilir: **4** (taban teknik gereklilik)
- llms.txt var ve formatı doğru: **4** (opsiyonel; akademik etkisi DOĞRULANMADI — düşük ağırlık)

### 2.4. Alt-pill 4: Rekabet Bağlamı (ağırlık: **10/100**)

Kanıt: Kumar/Ranqo §1.4 (niş marka %11; listicle ~%21 atıf).

- Klinik kaç sorguda üst-10'da: oran × 5
- Üst sırada listicle/aggregator var mı (klinik için FTC/listicle fırsatı sinyali): **3**
- Rakip domain sayısının tekrarı (klinik ne kadar geçiş yapmış): **2**

### 2.5. Toplam ve raporlama

```
toplam = 0.45*sira + 0.25*icerik + 0.20*erisim + 0.10*rekabet
```

**Zorunlu rapor uyarıları (Schulte §1.2'den):**
1. "Bu tek-çekim bir ölçümdür; AI yanıtlarının kaynakları gün-güne ~%65 değişir (Jaccard 0,34)."
2. "Skor Google sıralamasına dayalı bir YORDAMAdır; ChatGPT sorguların %57,8'inde atıf vermez."
3. ChatGPT/Perplexity'de doğrudan ölçüm için ayrı bir LLM-judge katmanı gerekir (bu modül
   Google-SERP proxy'sidir).

Bu üç uyarı olmadan skor SUNULMAMALIDIR — aksi halde §1.2'nin "Don't Measure Once" eleştirisine
düşeriz.

---

## 3. KOD GEREKSİNİMLERİ — `ai_gorunurluk.py` için

### 3.1. Sorgu kümesi (Dubai diş kliniği)

Soru-formu (Xu §1.5: %64,7 AIO aktivasyonu) + kategori karışımı:

```python
SORGU_KUMESI = {
    "kategori": [
        "dentist Dubai", "dental clinic Dubai", "best dentist Dubai",
        "teeth whitening Dubai", "dental implants Dubai",
    ],
    "soru_formu": [
        "who is the best dentist in Dubai",
        "where can I get dental implants in Dubai",
        "how much does teeth whitening cost in Dubai",
    ],
    "hizmet": [
        "Invisalign Dubai", "root canal Dubai", "veneers Dubai",
    ],
}
```

Ücretsiz Serper kotasını korumak için: `--sorgu-sayisi N` ile küme kırpılır (varsayılan 5),
her sorgu **dosya-bazlı cache'lenir** (aynı sorgu+domain 24 saat tekrar istenmez).

### 3.2. Serper çağrısı

- POST `https://google.serper.dev/search` , header `X-API-KEY`
- `{"q": sorgu, "num": 10}` → `organic[]` içinde `position`, `title`, `link`, `snippet`
- Hata yönetimi: 429 (kota) → dur ve uyar; 401 → anahtar hatası; timeout → atla
- **API key ASLA ekrana yazılmaz, log'a yazılmaz** (sadece `${#KEY}` uzunluğu raporlanır)

### 3.3. Domain eşleştirme

```python
def domain_eslesir_mi(link, hedef_domain):
    """Serper'dan gelen link'in host'u hedef domain ile eşleşir mi.

    www., alt-subdomain (blog.x.com) ve yol derinliği normalizasyonu.
    """
    host = urlparse(link).netloc.lower()
    host = host.removeprefix("www.")
    return host == hedef_domain or host.endswith("." + hedef_domain)
```

### 3.4. Rakip analizi

Her sorguda üst-10 domain'ler toplanır; **sıklık tablosu** (kaç sorguda üst-10'da) çıkarılır.
Hedef kliniğin sırası bu tabloda gösterilir → "kimler öne çıkıyor, klinik kaçıncı" sorusunun
cevabı. Aggregator/listicle tespiti: `tripadvisor`, `whatclinic`, `doctoruna`, `hyaat`,
`top10`, `best-` gibi domain/ad desenleri.

### 3.5. Çıktı yapısı

```python
{
  "domain": "biolitedubai.com",
  "sorgu_sayisi": 5,
  "serper_credits_kullanildi": 5,
  "siralama": {"en_iyi_sira": 3, "ortalama_sira": 7.4, "ust3_orani": 0.4,
               "bulunulan_sorgular": [...], "bulunamayan_sorgular": [...]},
  "icerik": {...},        # uret_rapor.py'nin yapilandirma()'sinden
  "erisim": {...},        # robots/sitemap/llms.txt/crawler
  "rakip": [{"domain": "...", "ust10_sayisi": 5, "en_iyi_sira": 1}, ...],
  "ai_alinti_puani": 0-100,
  "uyarilar": [...],      # Schulte uyarıları
}
```

### 3.6. Kısıtlar (servis sağlamlığı)

- **Cache şart**: aynı sorgu 24h içinde tekrar Serper'a GİDEMEZ
- **Kota**: Her çalıştırma `credits_kullanildi` sayar; toplam <2500 kalmalı
- **Para yok**: Serper dışında hiçbir ücretli API çağrılmaz
- **Key yok ekranda**: maskeli raporlama

---

## 4. Kaynak listesi (tümü arXiv, GEO_LITERATUR dosyasında doğrulanmış)

- arXiv:2609.15164 — CiteChoice (rank-1 %85,1 / rank-5 %42,8; +0,50 structured; %15 flip)
- arXiv:2604.07585 — Schulte "Don't Measure Once" (Jaccard 0,34; Gini 0,715; %57,8 sıfır atıf)
- arXiv:2605.25517 — Vishwakarma/Sprinklr (relevans OR >>10k; format 0,78–1,68 zayıf)
- arXiv:2604.25707 — Kai (longer/structured/richer evidence; breadth≠depth)
- arXiv:2606.20065 — Kumar/Ranqo (niş %11; listicle ~%21)
- arXiv:2605.14021 — Xu (AIO %13,7 / soru-formu %64,7; ~%30 1. sayfa dışı)
- arXiv:2604.27790 — Grossman (AIO %51,5; crawler engeli azaltıyor)
- arXiv:2609.06798 — Zha (yerli dil 3,5–13,5 kat)
- llmstxt.org — llms.txt v2 (bu oturumda DOĞRULANDI)
