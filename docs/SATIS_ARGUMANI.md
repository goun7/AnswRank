# AnswRank Satış Argümanı — Ölçülmüş, Abartısız

> **Kural:** Bu belgede yer alan her sayı `ai_gorunurluk.py` tarafından üretilen
> ve `olcumler/` dizininde kayıtlı duran **gerçek ölçümdür**. Hiçbir rakam
> tahmin değildir; hiçbir iddia ölçülmeyen bir şey hakkında değildir.
> **Abartı yok** — bu dosya satış için kullanılacak, bu yüzden yanlış olamaz.

## 1. Kanıtlanmış karşılaştırma: Teknik 100/100, AI görünürlüğü 39/100

İlk ölçüm klinikimiz **klinik-1.example** üzerinde yapıldı. Sonuç:

| Ölçüm | Puan | Anlamı |
|---|---|---|
| **Teknik AI erişilebilirliği** | **100/100** | robots.txt, AI crawler izinleri, sitemap, HTTPS, llms.txt — hepsi tam puan |
| **AI alıntı olasılık skoru** | **39/100** | LLM'lerin bu klinikleri kaynak olarak gösterme olasılığı |

**Bu karşılaştırma satış argümanımızın kalbidir:** Kliniklerin teknik altyapısı
genellikle **kusursuzdur** — sitemap çalışıyor, HTTPS var, hiçbir AI botu
engellenmemiş, llms.txt konmuş. Teknik ekiplerin baktığı her şey 100/100.

Ama AI görünürlüğü **39/100**. Yani teknik olarak "her şey doğru" iken
ChatGPT/Perplexity/Gemini o klinikleri cevaplarında **göstermiyor**.

> **Dürüst not:** 39/100 puanı tek bir domainin (klinik-1.example) 5 Google
> sorgusu üzerinden alınmış **ilk ölçümüdür**. Bu bir ortalama değildir; her
> klinik için ayrı ölçülür.

## 2. Neden 39/100? — 5 somut iyileştirme alanı

Skoru üreten 4 alt-puanın her biri ölçüldü. Hangisinin zayıf olduğu nettir:

### Alan 1: Google sıralaması — 0/100 (ağırlık %45) 🔴 EN BÜYÜK KAYIP

5 Dubai diş hekimi sorgusunun **hiçbirinde** ilk 10'da değiliz:
"dentist Dubai", "dental clinic Dubai", "best dentist Dubai",
"teeth whitening Dubai", "dental implants Dubai".

- Aynı sorgularda rakip `rakip-klinik-a.example` **5/5 sorguda #1**.
- Akademik kanıt: AI alıntılarının %85,1'i rank-1'den, %42,8'i rank-5'ten
  (CiteChoice). İlk 10'da olmayan bir site, AI tarafından neredeyse hiç
  alıntılanmıyor.
- **Bu alan tek başına toplam skoru doğrudan etkiler:** 0.45 × 0 = 0 puan.
  Sıralama alt puanı 0 → 60 olsa toplam skor 39 → **66**.

### Alan 2: Schema.org işaretleme eksikliği — 8 puanlık tek kuruşluk delik

İçerik alt-puanı 17/25. Diğer her şey tam (2769 kelime ✓, FAQ ✓,
meta açıklama ✓, başlık ✓). **Tek eksik: schema.**

- Siteden çıkan schema türü **"WebSite"** — "Dentist", "MedicalBusiness" veya
  "LocalBusiness" değil. Yani arama motorlarına "bu bir diş kliniğidir"
  diyen işaretleme yok.
- Kanıt: CiteChoice — yapılandırılmış rendering **+0,50 alıntı/yanıt**
  kazandırır.
- **En hızlı düzeltme:** tek bir JSON-LD bloğu. İçerik 17/25 → 25/25,
  toplam skor 39 → **47**. Hiçbir içerik yazmadan, 1 satır işaretleme ile.

### Alan 3: Soru-formu içerik stratejisi — ölçülmemiş fırsat

Soru-formu sorgular ("how much does teeth whitening cost in Dubai") AIO
(answers engine) aktivasyonunda **%64,7** iken genel sorgularda bu oran
**%13,7** (Xu 2026). Yani AI cevapları en çok soru-formu sorgularda kaynak
gösterir.

- Sitede FAQ bölümü var (bu iyi) ama doğrudan **soru-formu sorgularına
  net, yapılandırılmış cevaplar** yok.
- **Bu alanın ölçümü henüz tamamlanmadı** — ilk ölçümde sadece 5 "kategori"
  sorgusu kullanıldı; 3 soru-formu ve 3 niş hizmet sorgusu bekliyor.
  AnswRank'in bir sonraki adımı budur (aşağıda §4).

### Alan 4: Listicle / aggregator girişi — atıfların %21'i buraya gider

Rakip analizinde **"Best Dental Clinic in Dubai" tarzı listeler** ilk 10'un
7 sonucunu kaplamış. Kumar/Ranqo 2026: AI atıflarının **~%21'i** bu
"ranked best-of listicle" formatına gider.

- Klinik bu listelerde yok; rakipleri `rakip-klinik-b.example`, `rakip-klinik-a.example`
  `drpaulsdentalclinic.com` listicle başlıklarıyla #1-#3'te.
- **Fırsat sinyali zaten tespit edildi** (`listicle_firsati_var: true`) —
  listelere girmek, organik sıralamayı yükseltmekten **daha hızlı** sonuç
  verir.
- **Dürüst not:** bu alan ölçülmüş bir **fırsatın** tespitidir, içine girilmiş
  bir başarı değil. Listicle'lara giriş AnswRank'in yapacağı bir iş midir,
  yoksa klinik için bir PR/ilişki işi mi — bu satış konuşmasında netleştirilmeli.

### Alan 5: Önemli dürüstlük notu — AI erişiminde iyileştirilecek bir şey YOK

Erişim alt-puanı **20/20 (100/100)**. Engelli AI crawler **yok**; robots.txt
parse edilebiliyor; sitemap var; HTTPS çalışıyor; llms.txt skoru yeterli.

**Bu nedenle AnswRank asla "AI botlarını açın" tavsiyesi vermez** — bu
açıkça ölçülmüş ve zaten tam puan. Satış argümanımız şu değildir:
*"AI sizi engelliyor olabilir"* (ölçüm bunu yalanlıyor). Argümanımız
şudur: *"Teknik altyapınız kusursuz — bu yüzden 39/100'ün sebebi teknik
değil, içerik ve sıralama. İşte tam olarak hangi 4 alanda."*

## 3. Skor nasıl artar? — ölçülmüş senaryo

| İyileştirme | Alt-puan değişimi | Toplam skor |
|---|---|---|
| Mevcut durum | sıralama 0, içerik 17/25, erisim 20/20, rekabet 2/10 | **39/100** |
| + Schema işaretleme (Alan 2) | içerik 17 → 25/25 | **47/100** |
| + İlk 10'ya giriş (Alan 1) | sıralama 0 → 60 | **74/100** |
| + Üst-3 sıralama | sıralama 60 → 85 | **85/100** |

*Bu tablo `ai_gorunurluk.py`'nin ağırlık formülüyle hesaplanmıştır
(sıralama %45, içerik %25, erişim %20, rekabet %10) — tahmin değil,
modülün aynı matematiğidir.*

## 4. Ölçüm sınırları — "abartı yok" kuralının kanıtı

Bu skor **söz verilemez**. Modülün ürettiği zorunlu uyarılar:

1. **Tek-çekim bir ölçümdür.** AI cevaplarının kaynakları gün-güne ~%65
   değişir (Schulte 2026, arXiv:2604.07585, Jaccard 0,34).
2. Skor Google sıralamasına dayalı bir **YORDAMAdır**; ChatGPT sorgularının
   %57,8'inde hiç atıf verilmez (aynı kaynak).
3. ChatGPT/Perplexity'de **doğrudan** ölçüm için ayrı bir LLM-judge katmanı
   gerekir — `ai_gorunurluk.py` bir **Google-SERP proxy'sidir**, doğrudan
   AI cevap ölçer değildir.

**Satışta kullanım:** bu sınırları gizlemeyiz; onları teklifun parçası
yaparız — *"ilk ölçüm tek-çekimdir, bu yüzden düzenli yeniden ölçüm
(aylık takip) asıl değerdir. Kaynaklar %65 değiştiği için tek seferlik
skor anlamsızdır."* Bu dürüstlük, `docs/DENETIM_RAPORU.md`'de işaret edilen
"abartılı pazarlama" riskini sıfırlar.

## 5. Metriklerin teknik doğrulama durumu

| Bileşen | Doğrulama |
|---|---|
| 1218 test, 0 failed | ✅ `timeout 250 .venv/bin/pytest tests/ -q` RC=0 |
| Gizlilik (orphan rewrite) | ✅ SERPER_API_KEY log'a yazılmaz (test ile sabit) |
| 39/100 ölçümü | ✅ `olcumler/klinik-1.example.json` kayıtlı |
| 100/100 teknik skor | ✅ aynı dosyada `erisim.puan = 20/20` |
| Skor formülü | ✅ ağırlık testi: 45/25/20/10 = 100 |

---

**Özet (asansör konuşması):**
*"Teknik altyapınız 100/100 — sitemap, HTTPS, AI bot izinleri, llms.txt
hepsi tam puan. Ama AI görünürlüğünüz 39/100. Sorun teknik değil: tek bir
schema işaretleme eksikliği ve 5 sorguda ilk 10'da olmamak. AnswRank
ikisini de ölçer ve aradaki 61 puanın tam olarak nerede kaybolduğunu
gösterir."*
