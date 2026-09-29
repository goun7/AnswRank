# DM ÖLÇÜM ALTYAPISI — tasarım + etik değerlendirme

> Tarih: 27 Eyl 2026 | **DM HOLD 0/20 — GÖNDERİLMEDİ**
> **Bu doküman TASARIMDIR.** Kod YAZILMADI — yalnızca tasarım +
> etik değerlendirme + gereken kodların **listesi** ( uygulama
> için lead onayı gerekir).

---

## 0. SORUN — ölçüm YOK ( kör gönderim riski)

```bash
KANIT:  curl http://127.0.0.1:8007/healthz | python3 -m json.tool
RC:     0
CIKTI:  { status, sester, ledger_chain_valid, healthz_call_count,
          prices, daily_quota }       <-- HIC izleme alani YOK
```

```bash
KANIT:  grep -rn "referral|campaign|utm_" answrank/finance/ x402_servis.py
RC:     0
CIKTI:  ( bos — yalnizca fx_source = kur-fiyati kaynagi, IS ile alakasiz)
```

> **GERÇEK:** DM gönderilse bile **hangi DM'in** yanıt getirdiğini
> söyleyecek mekanizma YOK. `healthz_call_count` global bir sayaçtır
> ( 491) — DM'e atfedilemez. **A/B ölçümü imkansız.**
>
> **Sonuç:** DM HOLD kalkarsa **kör gönderim** olur — 12 taslak
> arasından hangisinin çalıştığını asla öğrenemeyiz.

---

## 1. ÖLÇÜM MEKANİZMASI — tasarım

### 1.1 İzleme kimliği ( tracking code) — yapısı

**Biçim:** `unpump-<profil><varyant>-<dil>-<sira>`

| Örnek | Anlamı |
|---|---|
| `unpump-p1a-tr-01` | Profil 1, Varyant A, Türkçe, 1. gönderim |
| `unpump-p3b-en-07` | Profil 3, Varyant B, İngilizce, 7. gönderim |

> **Neden bu yapı:** profilden yanıt oranı kırılımı ( segment) ve
> A/B karşılaştırması ( varyant) aynı kodda taşınır — tek alan yeter.

### 1.2 Taşıma yolu — DM'den servise ( 3 seçenek)

| # | Seçenek | Nasıl | Artı | Eksi | Değerlendirme |
|---|---|---|---|---|---|
| **1** | **`?ref=` URL parametresi** | DM'de `https://...?ref=unpump-p1a-tr-01` | basit, standart, açıktır | müşteri URL'yi silebilir | **ÖNERİLEN ( öncelik)** |
| **2** | **X-Referral header** | ödeme anında `X-Referral: unpump-...` | URL'den bağımsız | müşteri header eklemeli (sürtünme) | yedek |
| **3** | **`/audit` JSON alanı** | `{"url": "...", "ref": "..."}` | en doğal akış | API değişikliği gerekir | ana |

**Önerilen birleşim:** **1 + 3** — URL'de `ref` ( insanların görebileceği
ama HTTP'de doğal) + `/audit` JSON'ında `ref` ( programatik erişim).

### 1.3 Servis tarafı — nereye kaydedilir

```
DM -> ?ref=unpump-p1a-tr-01 -> /audit ( ref JSON'a alinir)
                                |
                                v
                     receipt kaydina ref EKLENIR
                                |
                                v
                     /healthz veya /olcum -> { ref, sayi, son_tarih }
```

**En küçük değişiklik ( 2 nokta):**
1. **receipt/ledger kaydına `ref` alanı** — ödeme kanıtı ile DM'i
   ilişkilendirir ( en değerli sinyal: **para getiren** DM)
2. **`/olcum` read-only endpoint** ( önerilen) — DM başına
   gösterim/yanıt/ödeme sayısını döner; `ref` ile sorgulanır

> **A/B karşılaştırması:** `GET /olcum?ref=unpump-p1a-tr-01` vs
> `...p1b-tr-01` → yanıt oranı = ödeme / gösterim.

### 1.4 Ölçülecek metrikler

| Metrik | Tanım | Kaynak |
|---|---|---|
| **gösterim** | DM gönderildi ( okundu mu bilinmez) | outbox kaydı |
| **tıklama** | müşteri `?ref` URL'sine tıkladı | servis tarafı log |
| **deneme** | `/audit` çağrısı yapıldı ( 402 veya 200) | receipt sayacı |
| **ödeme** | 200 + gerçek USDC transferi | mainnet_verify |
| **gelir** | ödeme miktarı ( USDC nominal) | receipt |

> **Birincil metrik:** **ödeme / gösterim** ( dönüşüm). İkincil:
> **deneme / tıklama** ( ilgi sinyali).

---

## 2. ETİK DEĞERLENDİRME — izleme SÖYLENMELİ mi?

> **KARARIM: SÖYLENMELİDİR — ama kısa ve doğal bir dille.**

### 2.1 Gerekçe

| Açı | Gizli izleme | Açık izleme |
|---|---|---|
| **Etik** | ❌ izlenmediğini bilmez — rızası yok | ✅ bilir, rıza verebilir |
| **Güven ( ilk müşteri!)** | ❌ keşfedilirse tüm itibar gider | ✅ keşfedilecek bir şey YOK |
| **Dönüşüm** | ✅ biraz yüksek ( kısa vade) | ⚠ biraz düşük ( uzun vade) |
| **Marka ( "ilk siz")** | ❌ "ilk müşteriniz" vaadi ile **çelişir** | ✅ tutarlı |
| **Yasal ( UAE/GDPR)** | ❌ izleme açıklama zorunluğu riski | ✅ açık |

**Belirleyici argüman:** DM paketinin temel vaadi **dürüstlüktür** —
"hiç ödeyen müşterimiz yok", "uptime garantisi yok", "tek cüzdana
geliyor". Aynı mesajda **gizli izleme** yapmak doğrudan
**çelişkidir**. İlk müşteriyi **etik bir ikilemle** başlatmak, 0.05
USDC'nin getireceği her şeyi yok eder.

> **Ayrıca:** "ilk siz olabilirsiniz" müşterisi geleceğin
> **referansıdır** ( vaka çalışması). Gizli izleme keşfedilirse
> referans da gider.

### 2.2 Açık ifadenin biçimi ( önerilen)

**TR ( tek cümle, 8 kelime):**
> Yazışmamız için bir bağlantı kullanıyorum — yanıtımı ölçmek amaçlı.

**EN ( tek cümle):**
> I use a link in this chat — to measure my reply rate.

**Neden bu kadar kısa:** uzun bir izleme açıklaması **DM'i uzatır**
( 60-kelime kuralını bozar) ve dikkatleri teknik detaya çeker.
Kısa, doğal, **gizlemeyen** bir cümle yeter.

### 2.3 Gizlilik kuralı ( bağlayıcı)

- ❌ **Gizli takip YOK** ( piksel, görüntü, gizli yönlendirme)
- ❌ **Kişisel veri toplanmaz** ( isim, e-posta, konum — `ref` dışında)
- ✅ **`ref` kodu kişiye özgü DEĞİL** — varyanta özgüdür ( kişisel
  tanımlayıcı içermez)
- ✅ **Açık olma** — kullanılan bağlantı `?ref=` parametresini taşır
  ( URL'de görülebilir, gizli yönlendirme DEĞİL)
- ✅ **Kişi sorarsa** tam açıklama: "hangi mesajın yanıt getirdiğini
  öğrenmek için her mesaja ayrı bir bağlantı koydum"

> **ÖLÇÜM-OPTİMİZASYON dengesi:** dönüşüm biraz düşse de, **ilk
> müşteri için güven dönüşümden değerlidir** — çünkü ilk müşteri
> vakayı oluşturur, geri dönüşü getiren **referans** olur.

---

## 3. GEREKEN KODLAR — LİSTE ( YAZILMADI, onay bekliyor)

> **Sadece listedir.** Her madde için lead onayı + ayrı görev gerekir.

| # | Bileşen | Dosya ( önerilen) | İş | Efor |
|---|---|---|---|---|
| **K1** | `ref` parametre ayrıştırma | `x402_servis.py` ( `/audit`) | `?ref=` ve JSON `ref` alanını al | küçük |
| **K2** | receipt'e `ref` ekleme | `answrank/finance/receipt_ledger.py` | her receipt'e `ref` ( nullable) | küçük |
| **K3** | `/olcum` read-only endpoint | `x402_servis.py` | `ref` → {gösterim, deneme, ödeme, gelir} | orta |
| **K4** | DM gönderim kaydı | `scripts/dm_gonderim_kaydet.sh` | outbox'a `ref` yazma ( gönderim anında) | küçük |
| **K5** | gösterim/deneme sayaçları | `x402_servis.py` | 402 çağrısını `ref` altında say | küçük |
| **K6** | A/B karşılaştırma raporu | `scripts/ab_karsilastir.py` | iki `ref` arası dönüşüm farkı | küçük |
| **K7** | **kişisel-veri-filtresi** | `x402_servis.py` | `ref` dışında kişisel alanları reddet | küçük |
| **K8** | test: `ref` akışı | `tests/test_dm_olcum.py` | K1+K2+K5'i doğrula ( DUMMY) | orta |

> **Öncelik:** K1+K2+K5+K8 ( ölçüm çekirdeği) → sonra K3+K6 ( rapor)
> → en son K4 ( gönderim, HOLD kalkınca). **K7 etik kapıdır —
> baştan yazılmalı.**

**Yapılmayanlar ( bu görevde):** hiçbiri. **Tasarım + liste only.**

---

## 4. GÖNDERİM ÖNCESİ SON KONTROL — 12/12

> Her taslak için 4 kriter. **Kimlik bilgisi kuralı:** isim/ünvan
> YOK — genel hitap ( "Merhaba Klinik Ekibi" gibi yer tutucu).

| # | Taslak | 0 ödeyen müşteri | ≥1 zayıflık | fiyat healthz birebir | kimlik YOK (genel hitap) | Sonuç |
|---|---|---|---|---|---|---|
| 1 | P1 A TR | ✅ | ✅ uptime | ✅ 0.05/10.0 | ✅ [Takım] | **GEÇTİ** |
| 2 | P1 A EN | ✅ | ✅ uptime | ✅ | ✅ [Team] | **GEÇTİ** |
| 3 | P1 B TR | ✅ | ✅ uptime | ✅ | ✅ [Takım] | **GEÇTİ** |
| 4 | P1 B EN | ✅ | ✅ uptime | ✅ | ✅ [Team] | **GEÇTİ** |
| 5 | P2 A TR | ✅ | ✅ scope | ✅ 0.05/0.2/1.2/10.0 | ✅ Klinik Ekibi | **GEÇTİ** |
| 6 | P2 A EN | ✅ | ✅ scope | ✅ | ✅ Clinic Team | **GEÇTİ** |
| 7 | P2 B TR | ✅ | ✅ tek-cüzdan | ✅ | ✅ Klinik Ekibi | **GEÇTİ** |
| 8 | P2 B EN | ✅ | ✅ multi-sig | ✅ | ✅ Clinic Team | **GEÇTİ** |
| 9 | P3 A TR | ✅ | ✅ tek-cüzdan | ✅ | ✅ [Ad] | **GEÇTİ** |
| 10 | P3 A EN | ✅ | ✅ single-wallet | ✅ | ✅ [Name] | **GEÇTİ** |
| 11 | P3 B TR | ✅ | ✅ scope | ✅ | ✅ [Ad] | **GEÇTİ** |
| 12 | P3 B EN | ✅ | ✅ scope | ✅ | ✅ [Name] | **GEÇTİ** |

**Sonuç: 12/12 GEÇTİ.**

### 4.1 Kanıt komutu ( otomatik kontrol)

```bash
KANIT:  python3 - <<'PY'
        # 12 taslagin hepsini 4 kritere gore tarar ( bkz ekteki cikti)
        #   0-musteri: "öd[ei]yen müşterimiz yok|paying customer yet"
        #   zayiflik:  çok-imzalı|multi-sig|uptime|garanti|sıralamayı|
        #              sıralamasını|guarantee
        #   fiyat:     0.05 USDC ( healthz ile birebir)
        #   kimlik:    [Takım]/[Team]/[Ad]/[Name]/Klinik Ekibi/Team/Name
        PY
RC:     0
CIKTI:  12/12 GEÇTI ( hata=0)
```

### 4.2 Kimlik bilgisi kuralı — detay

| Doğru ( genel) | Yanlış ( kişiye özgü) |
|---|---|
| "Merhaba [Takım]" | "Merhaba Ahmet" |
| "Merhaba Klinik Ekibi" | "Merhaba Dr. Yılmaz" |
| "Selam [Ad]" | "Selam Elif" |
| "Hi [Team]" | "Hi John" |
| "Hello Clinic Team" | "Hello Dr. Smith" |

> **Neden:** DM paketi **şablonlardır** — kişiye özgü isimler
> **yer tutucudan** gelir ( gönderim anında doldurulur), metne
> **gömülü olamaz** ( uydurma kişi = tehlikeli). Ayrıca hitap
> dışında **başka kimlik bilgisi YOK** ( unvan, şirket, lokasyon).

---

## 5. ÖNYARGI TESTİ — "35 kelime çok kısa mı?" ( P3 B TR)

### 5.1 P3 B TR'nin tam metni ( 35 kelime)

> Selam [Ad],
>
> Çağrı başına ücret için **x402**: 402 → imzala → 200. **0.05 USDC**
> çağrı başına ( Base), abonuk YOK.
>
> Açıkçası: **hiç ödeyan müşterimiz yok**. Denetim ölçer, LLM
> sıralamasını garanti etmez.
>
> Bir çağrı yapalım mı?

### 5.2 Dürüst değerlendirme — TEHLİKELİ derecede kısa

| Kriter | Değerlendirme |
|---|---|
| **Spam izlenimi riski** | **YÜKSEK** — "selam + fiyat + 402→200" jargonu, **hiçbir bağlam** yok ( ürününden, neden bizden aldığından bahsetmiyor) |
| **"402 → imzala → 200"** | **jargon** — teknik müşteri anlamazsa ( P3 crypto-native olsa bile) soğuk mesajda **jargon = spam sinyali** |
| **Bağlam eksik** | Hangi ürün? Neden ihtiyaç var? 35 kelime **ancak fiyat** söylüyor |
| **Dürüst cümle oranı** | **2/35** kelime = "hiç ödeyan müşterimiz yok" — gerisi **satış+teknik**. Spam'de bu dengeyi yener |
| **CTE gücü** | "Bir çağrı yapalım mı?" — zayıf ( hangi çağrı? neden?) |

### 5.3 Karar — 35 kelime YETERSİZDİR

> **Dürüst sonuç:** P3 B ( 35 kelime) **çok kısa** — spam riski,
> bağlam eksikliği ve jargon yoğunluğu nedeniyle. 60-kelime
> **taban** sınırıdır, **hedef DEĞİL**. Kısaltmayı **bağlamı
> koruyarak** yapmak gerekir — dürüst cümleyi **korumalı**, jargonu
> **azaltmalı**.

### 5.4 Önerilen revizyon — P3 B TR ( ~55 kelime, hedef aralık)

> Selam [Ad],
>
> Aracını gördüm — çağrı başına ücret almanın en temiz yolu **x402**:
> ödeme HTTP'ye gömülür ( imza + 402 → 200), abonuk YOK.
>
> AI-görünürlük denetimi **0.05 USDC** çağrı başına ( Base).
>
> Açıkçası: **hiç ödeyan müşterimiz yok**. Denetim ölçer, LLM
> sıralamasını garanti etmez.
>
> Bir çağrı yapalım mı?

**Değişenler:**
- **bağlam eklendi** ( "Aracını gördüm… en temiz yol")
- **jargon hafifletildi** ( "402 → imzala → 200" → "ödeme HTTP'ye
  gömülür ( imza + 402 → 200)")
- **0-müşteri + scope zayıflığı KORUNDU** ( kural)
- **uzunluk ~55 kelime** ( ≤60 içinde, spam izlenimi düştü)

> **Sonuç:** 60-kelime kuralı **korunur**, ama **35 hedef olmaz** —
> bağlam + dürüstlük ile 50-60 aralığı hedeflenir.

### 5.5 Tüm kısa varyantların yeniden değerlendirilmesi

| Taslak | Şimdi | Bağlam yeterli? | Öneri |
|---|---|---|---|
| P1 B TR/EN | 42/48 | ✅ ( "ürününüzü inceledim" var) | olduğu gibi kalsın |
| P2 B TR/EN | 37/50 | ⚠ P2 TR 37 — "llms.txt'niz yayında" bağlamı **var** ( yeterli) | olduğu gibi kalsın |
| **P3 B TR/EN** | **35/40** | ❌ **bağlam YOK** | **~55'e çıkart** ( §5.4) |

> **Sadece P3 B** revizyon gerektirir ( bağlam eksiği). P1/P2
> kısa varyantları bağlamı içeriyor — 35-48 kelime yeterli.

---

## 6. ÖZET — bu turda yapılanlar

| Madde | Durum |
|---|---|
| Ölçüm altyapısı **tasarımı** | ✅ ( §1) — kod YOK |
| **Etik karar** ( izleme açık) | ✅ ( §2) — gerekçesiyle |
| Gereken kodların **listesi** | ✅ ( §3, K1–K8) — YAZILMADI |
| Gönderim öncesi kontrol **12/12** | ✅ ( §4) — hepsi GEÇTİ |
| **Önyargı testi** ( 35 kelime) | ✅ ( §5) — çok kısa, revizyon önerisi |

**Kod YAZİLMADI** — bu doküman yalnızca **tasarım + değerlendirme**.

---

## 7. KARAR BEKLEYENLER

1. **Etik karar onayı:** izleme **açık** olacak mı ( §2 ile)?
   ( lead onayı — DM metnine 8 kelimelik cümle ekler)
2. **K1–K8 onayı:** ölçüm kodunu **yazmaya** başlanabilir mi?
   Öncelik: K1+K2+K5+K8 ( çekirdek) → K3+K6 ( rapor) → K4 ( gönderim)
3. **P3 B revizyonu** ( §5.4): ~55 kelimeye bağım eklemek — onay?
4. **60-kelime kuralı yorumu:** taban mı hedef mi? ( önerim: **taban**,
   hedef 50-60 — spam izlenimi ile dürüstlük arasında denge)

---

## 8. KANIT ÖZETİ

```bash
ls -la docs/DM_OLCUM_ALTYAPISI.md           # tasarim dokumani

# 12/12 kontrol ( otomatik)
python3 - <<'PY'                            # 4 kritere gore tarama
PY

# izleme altyapisi YOK ( sorun kaniti)
curl :8007/healthz | python3 -m json.tool   # ref alani YOK
grep -rn "referral|campaign" answrank/      # bos
```

**Korunan değerler:**
- **tests/ 1011 passed** ( kod değişmedi)
- **DM HOLD 0/20** — outbox'a YAZILMADI ( 15 DRAFT)
- **Para harcanmadı** — mainnet çağrısı YOK
- **Kod YAZILMADI** — yalnızca tasarım + liste
- **Uydurma kaynak YOK** — §5 değerlendirmesi kendi analizi

---

*Bu doküman **tasarım + etik değerlendirmedir**. Kod yazılmadı,
DM gönderilmedi. Ölçüm altyapısı için K1–K8 listesi onay bekliyor.*
