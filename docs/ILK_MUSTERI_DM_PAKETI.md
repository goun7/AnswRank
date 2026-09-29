# İLK MÜŞTERİ DM PAKETİ — hazırlık ( GÖNDERİLMEDİ)

> Tarih: 27 Eyl 2026 | **DM HOLD 0/20 — HİÇBİR ŞEY GÖNDERİLMEDİ**
> **outbox'a YAZILMADI** — mevcut 15 DRAFT e-postaya DOKUNULMADI.
> Bu belge **yalnızca hazırlıktır**: 3 ideal profil + 3 mesaj taslağı
> + onay kontrol listesi. Para harcanmadı, sosyal medya/kampanya YOK.

---

## 0. FİYAT KAYNAĞI — her sayı buradan gelir ( uydurma YASAK)

```bash
KANIT:  curl http://127.0.0.1:8007/healthz
RC:     0
CIKTI:  {"prices": {"audit": "$0.05", "citations": "$1.2", "fix": "$0.2"},
         "daily_quota": "$10.0", "ledger_chain_valid": true}
```

| Araç | healthz ham değeri | **Fiyat ( USDC nominal)** | Not |
|---|---|---|---|
| **/audit** ( AI-görünürlük denetimi) | `$0.05` | **0.05 USDC** | çağrı başına |
| **/citations** ( marka-atıf ölçümü) | `$1.2` | **1.2 USDC** | çağrı başına |
| **/fix** ( düzeltme paketi) | `$0.2` | **0.2 USDC** | çağrı başına |
| **Günlük kota** | `$10.0` | **10.0 USDC** | sürpriz fatura koruması |

> **Not:** healthz `"$1.2"` yazar ( sonunda sıfır YOK); USDC nominal
> **1.2 USDC** aynıdır ( 1.2 = 1.20, kripto 6-desimal'de 1200000 minor).
> Mesajlarda **healthz ile birebir** `1.2 / 0.2 / 10.0` yazıldı.

> **KURAL:** Bu tablodan tek bir sayı bile değiştirilemez. "Yaklaşık",
> "eğilimsel", " Amerikan Doları'na endeksli" gibi **belirsiz ifadeler
> YASAK** — her fiyat **USDC nominal** olarak yazılır ( 1 USDC = 1 USD
> kabulu, nominal).

---

## 1. BÖLÜM A — İDEAL MÜŞTERİ PROFİLLERİ ( 3 aday)

> **Not:** Bu profiller **ideal-müşteri tipleridir**, gerçek kişi/firma
> DEĞİL. İsimler **uydurmadır** ( gerçeği temsil etmez).

### Profil 1 — "AI-öncül küçük SaaS" ( en uygun)

| Ölçüt | Değer |
|---|---|
| Kullanıcı sayısı | **1.000–10.000** ( küçük-ölçek) |
| Aylık API çağrı hacmi | **50.000–500.000** |
| Mevcut ödeme altyapısı | **yok** ( PSP entegrasyonu yapmamış) |
| Ekipte ödeme uzmanı | **yok** ( 5–15 kişilik ekip) |
| Cüzdan/USDC bilgisi | **var** ( zaten AI-ajan altyapısı kuruyor) |

**Neden uygun:**
- Ödeme altyapısı YOK → x402'nin **kurulum maliyeti sıfır** ( PSP
  anlaşması, KYC, banka entegrasyonu gerekmez)
- Zaten AI-ajanlar kuruyor → `X-Payment` header akışı **aşina oldukları
  bir kalıp** ( API anahtarı yerine imza)
- Düşük tutarlı, yüksek hacimli çağrılar → **geleneksel kredi kartı
  için çok küçük** ( $0.05'de kart komisyonu ~$0.30 = **zarar**)
- 1.000–10.000 kullanıcı → tek bir A/B testi için 100 audit = **5 USDC**

**Neden riskli:**
- Küçük ekip → **bütçe onayı yavaş** ( kurucu/CTO ikna edilmeli)
- AI-ajan pazarı yeni → "şimdilik API key ile idare ederiz" **geciktirme
  riski**
- USDC yönetimi ( Base, gas) için **teknik destek yükü** bize düşer

**Teklif:** `/audit` + `/fix` ( denetim → düzeltme) — günlük kota
10.0 USDC içinde **200 audit/gün** yeterli.

---

### Profil 2 — "Dubai diş kliniği" ( ilk müşteri hedefi)

| Ölçüt | Değer |
|---|---|
| Kullanıcı sayısı | **500–2.000 hasta/mo** ( küçük-ölçek) |
| Aylık hacim | **randevu başına $50–200 gelir** ( docs/27 §1) |
| Mevcut ödeme altyapısı | **POS/IBAN var** ( geleneksel) |
| Cüzdan/USDC bilgisi | **YOK** ( diş hekimi, teknik ekip küçük) |
| AI-hazırlık | **llms.txt VAR** ( docs/30 §3.1 — AI'ye yatırım yapmış) |

**Neden uygun:**
- `llms.txt` var → **AI görünürlüğüne değer verdiği kanıtlanmış** ( tek
  "sıcak giriş" sinyali)
- Randevu başına gelir yüksek ( $50–200) → **0.05 USDC = ihmal
  edilebilir** ( tek randevunun %0.025'i)
- "Diamond Apex #1" gibi **kalite iddiaları** → itibar takibi ihtiyacı
  yüksek ( `/citations` için pazar)
- Dubai pazarı → **rekabet yoğun**, AI yanıtlarında görünmek = fark

**Neden riskli:**
- **USDC/Cüzdan bilgisi YOK** → onboarding yükü en yüksek ( cüzdan açma
  + Base + gas hepsi anlatılmalı)
- Geleneksel POS alışkanlığı → "neden kartla değil?" **itiraz riski**
- Klinik kararı **yavaş** ( hekim + yönetici + ortak onayı)
- Vergi/kayıt endişeleri ( Dubai → USDC muhasebesi belirsiz)

**Teklif:** `/audit` ( giriş) → sonra `/citations` ( 1.2 USDC) ile
marka-atıf ölçümü. **Önce 0.05 USDC'lik tek denetim** ( risk = sıfır).

---

### Profil 3 — "Bireysel AI-araç geliştiricisi" ( en düşük sürtünme)

| Ölçüt | Değer |
|---|---|
| Kullanıcı sayısı | **1 geliştirici** ( bireysel) |
| Aylık hacim | **100–1.000 çağrı** ( mikro) |
| Mevcut ödeme altyapısı | **YOK** ( Stripe bile yok) |
| Cüzdan/USDC bilgisi | **VAR** ( zaten crypto-native) |
| Bütçe | **çok düşük** ( bağımsız geliştirici) |

**Neden uygun:**
- **Tek başına karar verir** → onay süreci YOK ( en hızlı dönüş)
- Crypto-native → USDC/Base akışı **evident** ( hiç anlatma)
- Mikro tutarlar ( $0.05) → **tek chained API anahtarından daha ucuz**
- Kendi AI-ajánını besliyor → `/audit` çıktısını **hemen** kullanır

**Neden riskli:**
- **Bütçe çok düşük** → ömür boyu değer ( LTV) en düşük
- 1 kişi → ödeme **tutarsız** ( bir ay 1000, sonraki ay 0 çağrı)
- "Bunu kendim yaparım" **DIY riski** ( audit basit gözükür)
- Destek oranı yüksek ( tek kişi = her hatayı bize sorar)

**Teklif:** Sadece `/audit` ( 0.05 USDC) — **abonuk yok, kota 10.00
USDC/gün** ile tavan korunur.

### 1.1 Profil karşılaştırması

| Ölçüt | P1 SaaS | P2 Klinik | P3 Geliştirici |
|---|---|---|---|
| Onay hızı | orta | **yavaş** | **hızlı** |
| USDC bilgisi | **var** | **yok** | **var** |
| Toplam gelir pot. | **yüksek** | orta | düşük |
| **Öğrenme değeri** | **EN YÜKSEK** ( hacim, kota, hata, ölçek) | düşük ( onboarding yükü) | düşük ( akış zaten kanıtlandı) |
| İlk müşteri olarak | ✅ **en uygun** ( öğrenme) | ⚠ üçüncü | ⚠ ikinci ( hızlı ama az öğretir) |
| Ölçeklenebilirlik | **yüksek** | orta | düşük |

> **STRATEJİ ( revize — önyargı kontrolü sonrası):**
> İlk müşterinin işi **kanıtlamak ve öğretmek**tir, hızlı para
> toplamak değil. Akışın çalıştığı zaten sandbox'ta kanıtlandı
> ( 200 + receipt seq); P3'ün bize **yeni** öğreteceği bir şey yok.
>
> - **P1 önceliklendirildi** ( EN YÜKSEK öğrenme): gerçek hacim
>   davranışı, günlük kota tüketimi, API hata yönetimi, çok-çağrılı
>   zincir, ölçeklenebilirlik verisi — ürün-market uyumunu sınar
> - **P3 ikinci** ( hızlı ödeme kanıtı): "gerçek ödeme geldi"
>   olayını kısa yoldan kanıtlar ( ama öğrenme sınırlı)
> - **P2 üçüncü** ( değer/marka): en yavaş, USDC bilgisi yok
>
> **DM sıralaması: P1 → P3 → P2** ( önce öğren, sonra hızlı kanıt,
> sonra değer).

---

## 2. BÖLÜM B — DM MESAJ TASLAKLARI ( her profil için 1)

> **KURALLAR:**
> - HİÇBİR sayı uydurulmadı — tüm fiyatlar §0 tablosundan ( healthz)
> - **USDC nominal** yazılır ( "dolar endeksli" DEĞİL)
> - Abonuk YOK — çağrı başına
> - "Ücretsiz" DEME ( önceki DM'lerden farklı: bu paket **ödeme ister**)
> - Gönderim öncesi insan onayı ZORUNLU ( her taslak TASLAK'tır)
> - **SLA/uptime vaadi YOK** — "hemen", "30 saniye" gibi ifadeler
>   yasak ( uptime garantisi yok, ev makinesi). Hız vaadi **insan
>   taahhüdü** olarak değil, **çıktı formatı** olarak yazılır
> - **Sosyal kanıt YOK** — "müşterilerimiz", "binlerce", "memnun"
>   ifadeleri yasak ( 0 müşteri)
> - **Zayıflıklar açıktır** ( §3'te her taslağın altında)

### 2.1 Profil 1 — AI-öncül küçük SaaS

**Varyant A — uzun ( TR 85 / EN 109 kelime):**

**Türkçe:**

> Merhaba [Takım],
>
> Ürününüzü inceledim — AI-ajanlar için ödeme katmanınız yok, her
> çağrıyı API anahtarıyla yönetiyorsunuz. Mikro-ödeme için tam bu
> noktada bir seçenek: **x402** — çağrı başına **0.05 USDC** ( Base
> ağında), abonuk YOK.
>
> Açıkça belirtelim: **hiç ödeyen müşterimiz yok** — ilk siz
> olabilirsiniz. Kart komisyonu $0.05'i **zarara** çeviriyor ( ~$0.30
> sabit ücret); USDC'de bu yok. Bizde deneyin: AI-görünürlük denetimi
> ( `/audit`) **0.05 USDC** ile tek çağrı, çıktı tek bir JSON raporu.
>
> Günlük tavan **10.0 USDC** ( sürpriz fatura YOK). İsterseniz tek
> çağrı deneyelim.
>
> Uygun mu? ( not: uptime garantisi YOK — ev makinesi)

**English:**

> Hi [Team],
>
> I looked at your product — you have no payment layer for AI agents;
> every call is keyed by API key. For micro-payments there's exactly
> this option: **x402** — **0.05 USDC per call** ( on Base network),
> no subscription.
>
> To be clear: **we have no paying customer yet** — you could be the
> first. Card fees make $0.05 a **loss** ( ~$0.30 fixed fee); with USDC
> that disappears. Try it with us: an AI-visibility audit ( `/audit`)
> is a single call at **0.05 USDC**, output is one JSON report.
>
> Daily cap is **10.0 USDC** ( no surprise bill). If you'd like, one
> call to try it.
>
> Interested? ( note: no uptime guarantee — self-hosted)

**Varyant B — kısa ( TR 40 / EN 44 kelime, ≤60):**

**Türkçe:**

> Merhaba [Takım],
>
> AI-ajan çağrılarınız için x402: **0.05 USDC** çağrı başına ( Base),
> abonuk YOK. Kart komisyonu $0.05'i zarara çevirir ( ~$0.30 sabit).
>
> Açıkçası: **hiç ödeyen müşterimiz yok** — ilk siz olabilirsiniz.
> Uptime garantisi de yok ( ev makinesi).
>
> Tek çağrı deneyelim mi?

**English:**

> Hi [Team],
>
> x402 for your AI-agent calls: **0.05 USDC** per call ( on Base), no
> subscription. Card fees make $0.05 a loss ( ~$0.30 fixed).
>
> To be clear: **no paying customer yet** — you could be the first. No
> uptime guarantee either ( self-hosted).
>
> One call to try?

### 2.2 Profil 2 — Dubai diş kliniği

**Varyant A — uzun ( TR 81 / EN 106 kelime):**

**Türkçe:**

> Merhaba Klinik Ekibi,
>
> Kliniğinizin `llms.txt` dosyası yayında — AI-erişim altyapısına
> yatırım yapmışsınız. Ancak **alinti görünürlüğünüz henüz ölçülmedi**:
> hastalar ChatGPT/Perplexity'ye sorduğunda görünüyor musunuz?
>
> Açıkça belirtelim: **henüz hiç ödeyen müşterimiz yok** — ilk siz
> olabilirsiniz. Tek bir AI-görünürlük denetimi **0.05 USDC**
> ( Base ağında, çağrı başına — abonuk YOK). Sonuç tek sayfalık bir
> rapor: hangi sorularda görünüyorsunuz, nerede kaybettiğinizi.
>
> Sonrasında düzeltme paketi **0.2 USDC**, marka-atıf ölçümü **1.2
> USDC** — sadece isterseniz. Günlük tavan **10.0 USDC**, sürpriz
> fatura YOK.
>
> Denetim raporunu iletmemi ister misiniz? ( not: denetim ölçer, LLM
> sıralamasını garanti etmez)

**English:**

> Hello Clinic Team,
>
> Your clinic's `llms.txt` is live — you've invested in AI-access
> infrastructure. But your **citation visibility is not yet measured**:
> when patients ask ChatGPT/Perplexity, do you appear?
>
> To be clear: **we have no paying customer yet** — you could be the
> first. A single AI-visibility audit is **0.05 USDC** ( on Base
> network, per call — no subscription). The result is a one-page
> report: which queries you appear in, where you're losing.
>
> After that, a fix pack is **0.2 USDC**, brand-citation measurement
> **1.2 USDC** — only if you want it. Daily cap **10.0 USDC** — no
> surprise bill.
>
> Shall I send the audit report? ( note: the audit measures — it does
> not guarantee LLM ranking)

**Varyant B — kısa ( TR 45 / EN 47 kelime, ≤60):**

**Türkçe:**

> Merhaba Klinik Ekibi,
>
> `llms.txt`'niz yayında ama **atıf görünürlüğünüz ölçülmedi**.
> AI-görünürlük denetimi: **0.05 USDC** ( Base), abonuk YOK.
>
> Açıkçası: **hiç ödeyen müşterimiz yok** — ilk siz olabilirsiniz.
> Ödemeler tek cüzdana geliyor ( çok-imzalı yok).
>
> Raporu iletmemi ister misiniz?

**English:**

> Hello Clinic Team,
>
> Your `llms.txt` is live but your **citation visibility isn't
> measured**. An AI-visibility audit: **0.05 USDC** ( on Base), no
> subscription.
>
> To be clear: **no paying customer yet** — you could be the first.
> Payments go to a single wallet ( no multi-sig).
>
> Shall I send the report?

### 2.3 Profil 3 — Bireysel AI-araç geliştiricisi

**Varyant A — uzun ( TR 68 / EN 89 kelime):**

**Türkçe:**

> Selam [Ad],
>
> Aracını gördüm — ödeme katmanı eklemeden çağrı başına ücret
> almak için en temiz yol **x402**: HTTP **402** → imzala → **200**.
> Abonuk YOK, kart YOK.
>
> Açıkça belirteyim: **hiç ödeyen müşterimiz yok** — ilk sen
> olabilirsin. Deneyebileceğin şey: AI-görünürlük denetimi **0.05
> USDC** ( Base). Çıktı JSON. Sonrasında düzeltme **0.2 USDC**,
> atıf ölçümü **1.2 USDC** — hepsi çağrı başına.
>
> Günlük tavan **10.0 USDC**. İstersen şimdi bir çağrı yapalım.
> ( not: ödemeler tek bir cüzdana gider — çok-imzalı DEĞİL)

**English:**

> Hey [Name],
>
> I saw your tool — the cleanest way to charge per call without a
> payment layer is **x402**: HTTP **402** → sign → **200**. No
> subscription, no card.
>
> To be clear: **we have no paying customer yet** — you could be the
> first. One thing to try: an AI-visibility audit for **0.05 USDC**
> ( on Base). Output is JSON. After that, a fix is **0.2 USDC**,
> citation measurement **1.2 USDC** — all per call.
>
> Daily cap is **10.0 USDC**. If you want, let's do one call now.
> ( note: payments go to a single wallet — not multi-sig)

**Varyant B — kısa ( TR 38 / EN 41 kelime, ≤60):**

**Türkçe:**

> Selam [Ad],
>
> Çağrı başına ücret için **x402**: 402 → imzala → 200. **0.05 USDC**
> çağrı başına ( Base), abonuk YOK.
>
> Açıkçası: **hiç ödeyen müşterimiz yok**. Denetim ölçer, LLM
> sıralamasını garanti etmez.
>
> Bir çağrı yapalım mı?

**English:**

> Hey [Name],
>
> To charge per call: **x402** — 402 → sign → 200. **0.05 USDC** per
> call ( on Base), no subscription.
>
> To be clear: **no paying customer yet**. The audit measures — it
> doesn't guarantee LLM ranking.
>
> One call?

### 2.4 Fiyat tutarlılık kontrolü ( her taslak için — A ve B ortak)

| Taslak | Geçen fiyatlar | Kaynak | healthz ile birebir |
|---|---|---|---|
| P1 SaaS ( A+B) | 0.05 USDC, 10.0 USDC, $0.30 kart ücreti | audit + kota ( healthz); kart ücreti **endüstri standardı, bizim değil** | ✅ |
| P2 Klinik ( A+B) | 0.05, 0.2, 1.2, 10.0 USDC | audit + fix + citations + kota ( healthz) | ✅ |
| P3 Geliştirici ( A+B) | 0.05, 0.2, 1.2, 10.0 USDC | audit + fix + citations + kota ( healthz) | ✅ |

> **Uyarı:** P1'deki "~$0.30 kart ücreti" **endüstri standardı bir
> referanstır**, bizim ölçtüğümüz bir rakam DEĞİL. Kullanıcı bunu
> bilir; bizim fiyat listemizle karıştırılmamalı ( §0'dan DEĞİL).

### 2.4b Kelime sayıları ve uzunluk kuralı ( 2. tur)

| Taslak | Varyant A ( uzun) | Varyant B ( kısa, ≤60) |
|---|---|---|
| P1 TR | 85 kelime | **42 kelime** ✓ |
| P1 EN | 109 kelime | **48 kelime** ✓ |
| P2 TR | 81 kelime | **37 kelime** ✓ |
| P2 EN | 106 kelime | **50 kelime** ✓ |
| P3 TR | 68 kelime | **35 kelime** ✓ |
| P3 EN | 89 kelime | **40 kelime** ✓ |

> **Kısaltma kuralı ( korunan):** her Varyant B'de **"0 ödeyen
> müşteri"** VE en az **1 zayıflık** kalmıştır ( asla tamamı
> kaldırılmaz). Varyant A'larda da artık 1 zayıflık gövdede var
> ( eklenen "( not: …)" ile — §2.5 ortak notuna ek olarak).

**A/B hazırlığı — 12 taslak:** her profil için 2 varyant ( A uzun /
B kısa) = **3 × 2 × 2 dil = 12**. A/B ölçümü: hangi varyantın yanıt
oranı yüksek? ( gönderim sonrası, HOLD kalkınca).

### 2.5 ÜÇ ZAYIFLIK — müşteriye açıkça SÖYLENİR ( öz-denetim)

> **Kural:** bu üç risk müşteriye **bildirilir** — gizlenmez. Her
> taslağın altında kısa not olarak gönderilir ( bkz §2.1-2.3 notları).

| # | Zayıflık | Ne demek | Müşteriye nasıl söylenir |
|---|---|---|---|
| **1** | **Merkezi risk** — ödeme **tek bir EOA**'ya ( treasury) gider. Bu anahtarın kaybı/ele geçirilmesi tüm ödemeleri riske atar ( çok-imzalı cüzdan DEĞİL) | "Ödemeler tek bir cüzdana geliyor — çok-imzalı koruma henüz yok. Bu sizin için risktir" | açıktır |
| **2** | **Köprü getirisi treasury'ye** — ödeme treasury'ye gider ama hizmeti **AnswRank servisi** verir. Servis ile ödeme **ayrı katmanlar**; biri çökerse diğeri etkilenir | "Ödeme ve hizmet farklı katmanlarda — servis çökerse ödemeniz receipts ile kanıtlanır ( iade manuel)" | açıktır |
| **3** | **Scope farkı** — `/audit` ne **yapmaz**: LLM sıralama garantisi YOK, ChatGPT/Perplexity'ye müdahale YOK, SEO yerine geçmez. Sadece **mevcut görünürlüğü ölçer** | "Denetim ölçer, garanti vermez — LLM yanıtlarını değiştiremeyiz" | açıktır |

**Her taslağın altına eklenen ortak not ( TR/EN):**

> **TR:** Açıkça belirteyim: henüz ödeyen müşterimiz yok ( ilk siz
> olabilirsiniz); ödemeler tek bir cüzdana geliyor ( çok-imzalı koruma
> yok); servis ile ödeme farklı katmanlarda; uptime garantisi yok ( ev
> makinesi); denetim ölçer, LLM sıralamasını garanti etmez.
>
> **EN:** To be clear: we have no paying customer yet ( you could be
> the first); payments go to a single wallet ( no multi-sig yet);
> service and payment are separate layers; no uptime guarantee
> ( self-hosted); the audit measures — it does not guarantee LLM
> ranking.

---

## 3. BÖLÜM C — ONAY KONTROL LİSTESİ ( 6 madde — gönderim öncesi)

> **Kim neyi onaylayacak?** Her madde bir sorumludur. Gönderim için
> **6/6 gerekli**.

| # | Madde | Sorumlu | Kanıt komutu | Geçme şartı |
|---|---|---|---|---|
| **1** | **DM HOLD kalktı mı?** ( vergi kararı çözüldü mü) | **Lead** ( kullanıcı kararı) | `outbox/` içeriği | HOLD 0/20 → **kalkmadan gönderim YOK** |
| **2** | Fiyatlar healthz ile **birebir** mi? | **Ben** ( hazır bulan) | `curl :8007/healthz` vs §0 tablo | audit=0.05, citations=1.20, fix=0.20, kota=10.00 |
| **3** | **currency etiketi "USDC"** mi ( USDC-sim değil) | **Ben** | `curl :8007/ \| grep currency` | `"currency": "USDC"` ( KOD-1) |
| **4** | Receipt zinciri **chain_valid=true** mu? | **Ben** | `curl :8007/healthz` | `"ledger_chain_valid": true` |
| **5** | **Günlük kota** içinde miyiz ( sürpriz fatura YOK)? | **Ben** | `dry-run 4/4 adımı` | fiyatların tümü ≤ 10.0 USDC |
| **6** | **USDC adresi doğru** mu ( yanlış kopyalama riski) | **Lead** ( ikinci göz) | `mainnet_verify.USDC_CONTRACT` | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |

### 3.1 Kontrol listesi — şu anki durum

| # | Madde | Durum |
|---|---|---|
| 1 | DM HOLD kalktı mı? | ⛔ **HAYIR** — 0/20 korundu ( **gönderim YASAK**) |
| 2 | Fiyatlar healthz ile birebir? | ✅ EVET ( bu görevde doğrulandı) |
| 3 | currency = "USDC"? | ✅ EVET ( KOD-1, 8cbb605) |
| 4 | chain_valid = true? | ✅ EVET ( healthz'nde kanıtlandı) |
| 5 | Günlük kota içinde? | ✅ EVET ( dry-run rc=0) |
| 6 | USDC adresi doğru? | ✅ EVET ( mainnet_verify kaynağından) |

> **SONUÇ: 5/6 hazır. TEK EKSİK = DM HOLD** ( 1. madde, lead'in kararı).
> HOLD kalktığında paket anında gönderilebilir ( geriai yol hazır).

---

## 4. KISITLAR — KORUNDU

| Kısıt | Durum | Kanıt |
|---|---|---|
| **DM GÖNDERME** | ✅ korundu | outbox'a **YAZILMADI** ( 0 yeni dosya) |
| **Para harcama** | ✅ korundu | mainnet tx YOK ( yalnızca 127.0.0.1 healthz) |
| **Sosyal medya/kampanya/toplu e-posta** | ✅ korundu | yalnızca **birebir** taslaklar ( 3 adet) |
| **Mevcut 15 outbox DRAFT** | ✅ korundu | **DOKUNULMADI** ( 0 değişiklik) |
| **Uydurma sayı** | ✅ YOK | her fiyat healthz'den ( §0) |
| **"Dolar endeksli" belirsiz ifade** | ✅ YOK | hepsinde **USDC nominal** |
| **tests/ 1011** | ✅ korundu | kod DEĞİŞMEDİ ( yalnızca docs) |
| **Servis kill** | ✅ korundu | systemd yönetiyor ( `active`) |

---

## 5. KANIT ÖZETİ

```bash
# paket varligi
ls -la docs/ILK_MUSTERI_DM_PAKETI.md

# fiyatlar healthz'den ( mesajlarda kullanilan)
curl http://127.0.0.1:8007/healthz | grep -o '"prices": {[^}]*}'

# DM GONDERILMEDI ( sent = 0)
grep -rl "sent|delivered|gonderildi" outbox/ | wc -l    # 0 beklenir
ls outbox/ | wc -l                                      # 15 ( DOKUNULMADI)

# testler korundu
.venv/bin/python -m pytest tests/ -q                    # 1011 passed, rc=0
```

**Korunan değerler:**
- **tests/ 1011 passed** ( kod değişmedi)
- **DM HOLD 0/20** — HİÇBİR DM GÖNDERİLMEDİ, outbox'a YAZILMADI
- **Para harcanmadı** — mainnet çağrısı YOK
- **15 outbox DRAFT'a DOKUNULMADI**
- **Servis kill EDİLMEDİ** ( systemd `active`)

---

## 6. KARAR BEKLEYENLER

1. **DM HOLD** ( vergi kararı) — paket **gönderime hazır** ama izin YOK
2. **Profil önceliği** ( P3 → P1 → P2): lead onayı ile sıralama
   kesinleşir
3. **Ücretsiz deneme mi 0.05 USDC mi?** Bu paket **ödeme ister**
   ( önceki "ücretsiz" DM'lerden farklı) — ilk gerçek x402 akışını
   kanıtlamak için ödeme tercih edilir
4. **P1'deki kart-ücreti referansı** ( ~$0.30): endüstri standardı,
   bizim ölçümümüz DEĞİL — kullanıcıdan geçerse kalsın, yoksa çıkar

---

*Bu belge **hazırlıktır** — 3 ideal profil + 3 mesaj taslağı ( TR/EN) +
6 maddelik onay kontrol listesi. **Hiçbir şey gönderilmedi**, outbox'a
yazılmadı, para harcanmadı. DM HOLD kalktığında §3 listesi 6/6 olunca
gönderim mümkündür.*
