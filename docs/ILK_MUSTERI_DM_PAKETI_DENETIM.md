# İLK MÜŞTERİ DM PAKETİ — ÖZ-DENETİM ( dürüstlük kontrolü)

> Tarih: 27 Eyl 2026 | **DM HOLD 0/20 — GÖNDERİLMEDİ**
> Bu denetim, DM paketinin **kendisi tarafından** yapıldı ( kör
> noktaları yakalamak için). Tüm bulgular ve düzeltmeler aşağıda.
> **outbox'a dokunulmadı, para harcanmadı.**

---

## 0. DENETİM ÖZETİ

| Soru | Sonuç ( öncesi) | Düzeltme |
|---|---|---|
| 1. Her sayı healthz/kod ile birebir mi? | ❌ 2 uyumsuzluk | ✅ **düzeltildi** |
| 2. "Henüz kanıtlanmamış" belirgin mi? | ❌ hiçbir taslakta 0 müşteri yazmıyordu | ✅ **6 taslağa eklendi** |
| 3. 3 zayıflık müşteriye söyleniyor mu? | ❌ hiçbiri söylenmiyordu | ✅ **yeni §2.5 + her taslak** |
| 4. Sosyal kanıt ifadesi var mı? | ✅ YOK ( doğru) | korundu |
| 5. SLA/uptime vaadi var mı? | ❌ 3 uydurma hız vaadi | ✅ **düzeltildi** |

**Toplam düzeltme: 11 madde** ( 2 fiyat + 3 SLA + 6 dürüst-ifade +
3 zayıflık bildirimi + 1 öncelik revizyonu).

---

## 1. SORU 1 — Her sayı healthz/kod ile BİREBİR mi?

**Yöntem:** her taslaktaki her sayıyı `curl :8007/healthz` ile
**tek tek** karşılaştırdım.

### 1.1 Kanıt komutu

```bash
KANIT:  curl http://127.0.0.1:8007/healthz | python3 -c '
import json,sys
d=json.load(sys.stdin); p=d["prices"]
print(p, d["daily_quota"])'
RC:     0
CIKTI:  {'audit': '$0.05', 'citations': '$1.2', 'fix': '$0.2'} $10.0
```

### 1.2 Tek tek sayım — her taslak

| Taslak | Sayı | healthz | Durum ( öncesi) | Düzeltme |
|---|---|---|---|---|
| P1 TR | 0.05 USDC | audit $0.05 | ✅ uyumlu | korundu |
| P1 TR | 10.0 USDC | kota $10.0 | ✅ uyumlu | korundu |
| P1 TR | ~$0.30 kart | ( dış referans) | ⚠ işaretli | uyarı korundu |
| **P1 TR** | **"30 saniye"** | **YOK** | ❌ **UDYURMA** | ✅ **silindi** |
| P1 EN | 0.05 / 10.0 USDC | uyumlu | ✅ | korundu |
| **P1 EN** | **"30 seconds"** | **YOK** | ❌ **UYDURMA** | ✅ **silindi** |
| **P1 EN** | **"output immediately"** | **YOK** | ❌ **SLA vaadi** | ✅ **"one JSON report"** |
| P2 TR | 0.05 USDC | audit | ✅ | korundu |
| **P2 TR** | **1.20 USDC** | citations **$1.2** | ❌ **UYUMSUZ** | ✅ **1.2 USDC** |
| P2 TR | 0.2 USDC | fix $0.2 | ✅ | korundu |
| P2 TR | 10.0 USDC | kota | ✅ | korundu |
| P2 EN | 0.05 / 0.2 / 1.2 / 10.0 | hepsi uyumlu | ✅ | korundu |
| P3 TR | 0.05 / 0.2 / 1.2 / 10.0 | hepsi uyumlu | ✅ | korundu |
| **P3 TR** | **"marj ~%100"** | **iç hesap** | ❌ **müşteriye değil** | ✅ **silindi** |
| P3 EN | 0.05 / 0.2 / 1.2 / 10.0 | uyumlu | ✅ | korundu |
| **P3 EN** | **"margin ~100%"** | **iç hesap** | ❌ **müşteriye değil** | ✅ **silindi** |

### 1.3 Düzeltilen 2 fiyat uyumsuzluğu

**Bulgu 1 — P2 TR'de "1.20 USDC" kalmıştı:**
```
ONCEKI: marka-atıf ölçümü **1.20 USDC**
SONRASI: marka-atıf ölçümü **1.2 USDC**
```
> **Neden kaçtı:** `1.20` ile `USDC` **farklı satırlardaydı** ( satır
> kayması), replace_all yakalamadı. Bu denetimde yakalandı.

**Bulgu 2 — P1/P3 hız vaadi ( SLA altında):**
```
ONCEKI: çağrı deneyelim — 30 saniye.        ( P1 TR)
ONCEKI: call to try it — 30 seconds.        ( P1 EN)
ONCEKI: çıktı hemen / output immediately    ( P1 TR/EN, P3 TR)
SONRASI: çağrı deneyelim.                   ( süre silindi)
SONRASI: çıktı tek bir JSON raporu / one JSON report  ( format vaadi)
```
> **Neden düzeltildi:** "30 saniye" healthz'de YOK — uydurma süre.
> "hemen" bir **gecikme SLA'sı**; uptime garantisi olmadan verilemez.

### 1.4 Kontrol listesindeki eski format

```
ONCEKI: audit=0.05, citations=1.20, fix=0.20, kota=10.00
SONRASI: audit=0.05, citations=1.2,  fix=0.2,  kota=10.0
```
> healthz ham string'ine birebir ( sonunda sıfır YOK).

---

## 2. SORU 2 — "Henüz kanıtlanmamış" ifadeleri YETERLİ mi?

### 2.1 Gerçek durum ( kanıt)

```bash
KANIT:  .venv/bin/python net_kar_raporu.py
RC:     0
CIKTI:  tum 24 servis: 0.00 calls / 0.00 income / 0.00 net
        ( answrank receipt sayisi: 98 — hepsi SANDBOX, gercek odeme YOK)
```

> **GERÇEK:** **0 ödeyen müşteri, $0 gerçek gelir.** 98 receipt'in
> **tümü sandbox** ( demo anahtar). Mainnet'te **tek bir USDC transferi
> bile yok** ( mainnet_verify ile kanıtlandı).

### 2.2 Önceki durum — YETERSİZDİ

| Taslak | "0 müşteri" belirgin miydi? | Durum |
|---|---|---|
| P1 TR/EN | ❌ **HİÇ YAZMAMIYORDUM** | gizlenmiş izlenimi |
| P2 TR/EN | ❌ "henüz ölçülmedi" var ama **0 müşteri YOK** | yarım |
| P3 TR/EN | ❌ **HİÇ YAZMAMIYORDUM** | gizlenmiş izlenimi |

**Risk:** "Bizde denediniz" ( P1) sanki daha önce başkaları denemiş
gibi **örtük sosyal kanıt** yaratıyordu.

### 2.3 Düzeltme — 6 taslağa açık ifade eklendi

Her taslağın 2. paragrafı ( TR + EN):

```
TR: Açıkça belirtelim: **hiç ödeyen müşterimiz yok** — ilk siz
    olabilirsiniz.
EN: To be clear: **we have no paying customer yet** — you could be
    the first.
```

> **Sonuç:** artık 6/6 taslak **ilk cümleden** dürüst. "İlk müşteri"
> olduğunu saklamıyor — **özellik** olarak sunuyor ( "ilk siz
> olabilirsiniz").

---

## 3. SORU 3 — 3 zayıflıktan hangisi SÖYLENMİYORDU?

**Önceki durum: 3/3 de SÖYLENMİYORDU** ( en ciddi bulgu).

| # | Zayıflık | Önceki | Şimdi |
|---|---|---|---|
| **1** | **Merkezi risk** ( tek-kasa treasury EOA, çok-imzalı DEĞİL) | ❌ gizli | ✅ §2.5 + her taslak |
| **2** | **Köprü getirisi treasury'ye** ( ödeme treasury'de, hizmet AnswRank'te — ayrı katmanlar) | ❌ gizli | ✅ §2.5 + her taslak |
| **3** | **Scope farkı** ( `/audit` ölçer, LLM sıralama garantisi YOK) | ❌ gizli | ✅ §2.5 + her taslak |

### 3.1 Neden ciddi?

1. **Merkezi risk:** tüm ödemeler `0xF3F0...82c5` EOA'sına gider.
   Bu anahtar kaybolursa/ele geçerse **geçmiş ve gelecek tüm
   ödemeler** riske girer. Çok-imzalı ( multi-sig) cüzdan DEĞİL.
   Müşteri bunu bilmelidir — parası tek noktada duruyor.
2. **Köprü getirisi:** müşteri parasını treasury'ye gönderir ama
   hizmet `/audit`'ten gelir. Servis çökerse ödeme **zaten gitmiş**
   olur; iade **manuel** ( receipt kanıt olarak kullanılır). Bu
   "ödeme-hizmet ayrımı" x402'nin doğasıdır ama müşteri bilmez.
3. **Scope farkı:** müşteri "ChatGPT'de ilk sıraya çıkacağım"
   umabilir. `/audit` **sadece ölçer** — LLM'leri değiştirmez.
   Beklenti yönetimi olmadan "aldatılma" hissi riski.

### 3.2 Eklenen ortak not ( her taslağın altına — TR/EN)

```
TR: Açıkça belirteyim: henüz ödeyen müşterimiz yok ( ilk siz
    olabilirsiniz); ödemeler tek bir cüzdana geliyor ( çok-imzalı
    koruma yok); servis ile ödeme farklı katmanlarda; uptime garantisi
    yok ( ev makinesi); denetim ölçer, LLM sıralamasını garanti etmez.

EN: To be clear: we have no paying customer yet ( you could be the
    first); payments go to a single wallet ( no multi-sig yet);
    service and payment are separate layers; no uptime guarantee
    ( self-hosted); the audit measures — it does not guarantee LLM
    ranking.
```

> **Sonuç:** 3/3 zayıflık **her taslakta** açık. DM'ler uzadı ama
> **gerçekçe** — saklanacak bir şey kalmadı.

---

## 4. SORU 4 — Sosyal kanıt ifadesi var mı?

**Yöntem:** tüm paketi taradım ( regex: müşterilerimiz / customers /
binlerce / memnun / referans / testimonial / kullanan).

```bash
KANIT:  grep -niE "müşterilerimiz|customers|binlerce|memnun|referans|
        testimonial" docs/ILK_MUSTERI_DM_PAKETI.md | grep -vE "profil|Profil"
RC:     0
CIKTI:  ( bos) — tek eslesme "customers" kelimesi YOK
        ( yalnizca "paying customer" = 0-ifadesi, DOGRU kullanim)
```

### 4.1 Sonuç: TEMİZ ✅

| İfade | Geçiyor mu? | Durum |
|---|---|---|
| "müşterilerimiz" | HAYIR | ✅ |
| "binlerce müşteri" | HAYIR | ✅ |
| "memnun" | HAYIR | ✅ |
| "referans/ttestimonial" | HAYIR | ✅ |
| **"hiç ödeyen müşterimiz yok"** | **EVET ( 6 taslakta)** | ✅ **doğru** |

> **Not:** "paying customer" ifadesi **0 müşteriyi söylemek için**
> kullanılır — sosyal kanıt DEĞİL. **"Bizde denediniz"** ( P1)
> ifadesi **"Bizde deneyin"** olarak değiştirildi ( emir kipi —
> örtük geçmiş-iması kaldırıldı).

---

## 5. SORU 5 — SLA/uptime vaadi var mı?

### 5.1 Gerçek durum

```bash
KANIT:  systemctl --user is-active unpump-agents.service
RC:     0
CIKTI:  active    ( ancak Restart=always — uptime GARANTISI YOK)
```

> **GERÇEK:** ev makinesi, `Restart=always` ile **otomatik
> yeniden başlatma** var ama **SLA YOK** ( %99.9 gibi bir vaat
> verilemez). İzlenme süresi **ölçülmedi** ( ne kadar ayakta kaldığının
> kaydı YOK).

### 5.2 Bulunan 3 SLA/hız vaadi — düzeltildi

| Taslak | Önceki ( vaat) | Sorun | Sonraki |
|---|---|---|---|
| P1 TR | "çıktı hemen" | **gecikme SLA'sı** ( kanıtsız) | "çıktı tek bir JSON raporu" ( format) |
| P1 TR | "30 saniye" | **uydurma süre** ( healthz'de YOK) | **silindi** |
| P1 EN | "output immediately" | **gecikme SLA'sı** | "output is one JSON report" |
| P1 EN | "30 seconds" | **uydurma süre** | **silindi** |
| P3 TR | "hemen kullanırsın" | **gecikme iması** | "Çıktı JSON" ( sade) |
| P3 EN | "usable right away" | **gecikme iması** | "Output is JSON" ( sade) |

### 5.3 Kural ( §2 kurallarına eklendi)

> **SLA/uptime vaadi YOK** — "hemen", "30 saniye", "anında" gibi
> ifadeler yasak. Hız vaadi **insan taahhüdü** olarak değil, **çıktı
> formatı** olarak yazılır ( "tek bir JSON raporu" = format, süre
> DEĞİL).

> **İNSAN TAAHHÜDÜ NOTU:** servis tarafında otomatik SLA YOKTUR —
> herhangi bir hız/garanti **ancak insan tarafından** ( görüşmede)
> taahhüt edilebilir. Taslakta yazılı vaat VERİLEMEZ.

---

## 6. ÖNYARGI KONTROLÜ — P3→P1→P2 önceliği yeniden değerlendirildi

### 6.1 Eski önyargım

> "P3 ( bireysel geliştirici) en kolay ödeme → ilk gönder"

**Bu önyargının kökü:** hızlı kazanım = kanıt. Ama **neyi kanıtlar?**
Akışın çalıştığını — ki bu **zaten sandbox'ta kanıtlandı** ( 200 +
receipt seq 111). Yeni bir şey öğretmez.

### 6.2 İlk müşterinin gerçek işi — ÖĞRETMEK

| Ölçüt | P1 SaaS | P3 Geliştirici |
|---|---|---|
| **Öğrenme değeri** | **EN YÜKSEK** | **düşük** |
| Hacim davranışı ( kota tüketimi) | ✅ öğreniriz | ❌ tek kişi |
| API hata yönetimi ( çok çağrı) | ✅ öğreniriz | ❔ sınırlı |
| Çok-çağrılı zincir ( sync yarışları) | ✅ öğreniriz | ❌ |
| Ödeme akış uç durumları | ✅ öğreniriz | ❔ |
| Ürün-market uyumu sınama | ✅ **birincil** | ❔ |
| **Onay hızı** | orta ( ekip) | **hızlı ( tek kişi)** |
| **Gelir potansiyeli** | **yüksek** | düşük |

### 6.3 Karar — öncelik DEĞİŞTİ

```
ESKI: P3 → P1 → P2   ( once kolay para, sonra ogren)
YENI: P1 → P3 → P2   ( once OGRENN, sonra hizli kanit, sonra deger)
```

**Gerekçe:**
1. **İlk müşteri = öğrenme aracıdır.** P1 bize gerçek hacim, kota
   tüketimi, hata yönetimi, ölçek sınar — ürün-market uyumunu.
2. **Akış zaten kanıtlandı** ( sandbox + DUMMY testler). P3'ün ekstra
   kanıt değeri düşük.
3. **P3'ün LTV'si düşük** ( tek kişi, tutarsız çağrı) — ölçek için
   zaten P1 hedefleniyordu.
4. **P1'in "onay yavaş" dezavantajı** kabul edilir — öğrenme değerine
   değer.

> **Ancak:** DM'ler **aynı anda** gönderilirse ( HOLD kalkınca),
> sıralama **gönderim sırasını** değil **takip önceliğini** belirler.
> P1'den dönüş gelmezse P3 ile hızlı kanıt yoluna gidilir.

### 6.4 §1.1 tabloya yansıdı

```
| İlk müşteri olarak | ✅ en uygun ( öğrenme) | ⚠ üçüncü | ⚠ ikinci |
```
> "Öğrenme değeri" satırı **yeni eklendi** ( önyargı kontrolü öncesi
> bu ölçüt YOKTU — bu da bir kör noktaydı).

---

## 7. YAPILAN DÜZELTME ÖZETİ — 11 madde

| # | Düzeltme | Dosya | Tür |
|---|---|---|---|
| 1 | "1.20 USDC" → "1.2 USDC" ( P2 TR) | §2.2 | **fiyat uyumsuzluğu** |
| 2 | "30 saniye" silindi ( P1 TR) | §2.1 | **uydurma süre** |
| 3 | "30 seconds" silindi ( P1 EN) | §2.1 | **uydurma süre** |
| 4 | "çıktı hemen" → "tek bir JSON raporu" ( P1 TR) | §2.1 | **SLA vaadi** |
| 5 | "output immediately" → "one JSON report" ( P1 EN) | §2.1 | **SLA vaadi** |
| 6 | "hemen kullanırsın" → "Çıktı JSON" ( P3 TR) | §2.3 | **SLA iması** |
| 7 | "marj ~%100" silindi ( P3 TR) | §2.3 | **iç hesap** |
| 8 | "margin ~100%" silindi ( P3 EN) | §2.3 | **iç hesap** |
| 9 | "hiç ödeyen müşterimiz yok" — 6 taslağa eklendi | §2.1-2.3 | **dürüstlük** |
| 10 | 3 zayıflık bildirimi + ortak not ( TR/EN) | **yeni §2.5** | **dürüstlük** |
| 11 | Öncelik **P3→P1→P2 → P1→P3→P2** + "öğrenme değeri" satırı | §1.1 | **önyargı** |

**Ek olarak:**
- §2 kurallarına **SLA/uptime yasağı** + **sosyal kanıt yasağı** eklendi
- §2.4 "Bizde denediniz" → **"Bizde deneyin"** ( örtük geçmiş-iması
  kaldırıldı)
- Kontrol listesi değerleri healthz ham formatına birebir ( 1.2/0.2/10.0)

---

## 8. KALAN RİSKLER ( kabul edilmiş)

| Risk | Durum | İzah |
|---|---|---|
| **DM uzun** ( dürüst notlar nedeniyle) | kabul | kısa DM = az dürüst; uzun = açık |
| **P1 dönüşümü yavaş olabilir** | kabul | öğrenme değeri için göze alındı |
| **Kart ücreti referansı** ( ~$0.30) | kalıyor ( işaretli) | endüstri standardı, uyarı yeterli |
| **"İlk siz olabilirsiniz" satışa zarar verebilir** | kabul | **dürüstlük öncelikli** ( lead kuralı) |

---

## 9. KANIT ÖZETİ

```bash
# denetim dosyasi varligi
ls -la docs/ILK_MUSTERI_DM_PAKETI_DENETIM.md

# fiyat birebirlik ( duzeltilmis haliyle)
curl :8007/healthz | grep -o '"prices".*'    # $0.05/$1.2/$0.2, kota $10.0
grep -cE "0\.05 USDC|1\.2 USDC|0\.2 USDC|10\.0 USDC" docs/ILK_MUSTERI_DM_PAKETI.md

# uydurma ifade kalmadi mi
grep -nE "30 saniye|30 seconds|immediately|marj|~%100" docs/ILK_MUSTERI_DM_PAKETI.md | grep -vE "§|kural|Yasak"
#   ( bos = kalmadi)

# 0-musteri ifadesi 6 taslakta
grep -c "ödeyen müşterimiz yok\|paying customer yet" docs/ILK_MUSTERI_DM_PAKETI.md

# testler korundu
.venv/bin/python -m pytest tests/ -q    # 1011 passed, rc=0
```

**Korunan değerler:**
- **tests/ 1011 passed** ( kod değişmedi)
- **DM HOLD 0/20** — outbox'a **YAZILMADI** ( 15 DRAFT, dokunulmadı)
- **Para harcanmadı** — mainnet çağrısı YOK
- **Sosyal kanıt YOK** — hiçbir taslakta
- **SLA vaadi YOK** — hiçbir taslakta
- **3 zayıflık her taslakta** — merkezi risk, köprü, scope

---

## 10. SONUÇ

> **Öz-denetim 11 düzeltme yaptı.** En ciddisi: **3 zayıflığın 3'ü de
> müşteriye söylenmiyordu** ( merkezi risk, köprü getirisi, scope
> farkı) — artık her taslakta açık. Ayrıca **2 fiyat uyumsuzluğu** ve
> **3 uydurma hız/SLA vaadi** düzeltildi; **0 müşteri gerçeği 6
> taslağa da eklendi**. Öncelik **P1→P3→P2** olarak revize edildi
> ( öğrenme > hızlı para).
>
> **Paket artık gönderime hazır** — DM HOLD kalktığında. Tüm kısıtlar
> korundu ( 0 sent, 1011 test, outbox dokunulmadı).

---

*Bu denetim **öz-eleştiridir** — kör noktaları yakalamak için yazıldı.
DM paketinde 11 düzeltme yapıldı; hiçbir şey gizlenmedi, uydurulmadı.*
