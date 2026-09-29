# USDC-sim → USDC GEÇİŞ KANIT TABLOSU

> Tarih: 27 Eyl 2026 | **DM HOLD 0/20 — GÖNDERİLMEDİ**
> **Para HARCANMADI** — tüm değerler canlı `127.0.0.1` taramasından
> ( `curl /` ile currency etiketi) ve kaynak kod okumasından alındı.
> **Hiçbir dosya değiştirilmedi** — bu belge yalnızca kanıt tablosudur.

---

## 1. KAYNAK — USDC-sim NEREDE?

```python
# .venv/lib/python3.14/site-packages/sester/middleware.py:48
currency: str = "USDC-sim",      # kutuphane VARSAYILANI
```

`SesterMeter.__init__` bu değeri `self.currency` ( :62) tutar ve
402 yanıtına yazar ( :164, :175, :187). **Hiçbir servis override
etmediği için** hepsi `USDC-sim` yayın yaptı — ta ki AnswRank
KOD-1 ile geçene kadar ( commit 8e82128).

---

## 2. GEÇİŞ KANIT TABLOSU — 23 SERVİS

> **Durum sütunu açıklaması:**
> - `USDC` ✓ = geçiş **TAMAMLANDI** ( canlı etiketle kanıtlandı)
> - `USDC-sim` = geçiş **HAZIR** ( deseni uygulayabilir; sahibi onay bekliyor)
> - `ULAŞILAMAZ` = servis ayakta değil / etiket okunamadı

**Dosya:satır sütunu** = `SesterMeter,` satırı — geçiş parametresi
hemen sonrasına eklenir ( §4 desenine bak).

| # | Servis | Repo yolu ( kendi dizini) | `x402_servis.py` SesterMeter satırı | Canlı currency | Durum |
|---|---|---|---|---|---|
| 1 | **answrank** | `02_sahis/85-AnswRank` | L81 → currency **L85** | **USDC** | ✅ **TAMAMLANDI** ( KOD-1, 8e82128) |
| 2 | callsnap | `02_sahis/86-CallSnap` | L70 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 3 | vadedostu | `02_sahis/92-VadeDostu` | L61 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 4 | repriceai | `02_sahis/53-RepriceAI` | L57 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 5 | pqhaven | `01_unicorn/25-pqhaven-x402` | L61 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 6 | cleartag | `02_sahis/25-ClearTag` | L72 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 7 | borsa | `01_unicorn/24-ajan-borsasi` | L57 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 8 | renewlock | `02_sahis/10-RenewLock` | L58 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 9 | proje42 | `02_sahis/42-Zindan/proje42` | L66 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 10 | klinikkapici | `02_sahis/06-KlinikKapici` | L65 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 11 | chargeshield | `02_sahis/05-ChargeShield` | L62 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 12 | provix | `02_sahis/01-Provix` | L63 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 13 | lexbinder | `02_sahis/02-LexBinder` | L61 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 14 | yevmiye | `02_sahis/66-Fisclet` | L64 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 15 | gecit | `02_sahis/49-Deed` | L62 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 16 | vardro | `02_sahis/23-Vardro` | L61 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 17 | geosentinel | `02_sahis/14-GeoSentinel` | L66 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 18 | lup | `02_sahis/24-Lup` | L66 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 19 | kilerim | `02_sahis/Kilerim` | L65 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 20 | sonorix | `02_sahis/Sonorix` | L65 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 21 | voltpulse | `02_sahis/15-VoltPulse` | L63 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 22 | cbamshield | `02_sahis/16-CBAMShield` | L62 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |
| 23 | mcpguard | `02_sahis/04-MCPGuard` | L67 | USDC-sim | 🔵 geçiş hazır, sahibi onay bekliyor |

### 2.1 ÖZET

| Durum | Sayı | Oran |
|---|---|---|
| ✅ **TAMAMLANDI** ( AnswRank) | **1** | %4 |
| 🔵 geçiş hazır, onay bekliyor | **22** | %96 |
| ULAŞILAMAZ | **0** | %0 |
| **TOPLAM** | **23** | %100 |

> **Tüm 23 servis `x402_servis.py` kullanıyor** — hepsi aynı
> `SesterMeter` kütüphanesini çağırıyor. **Desen her birine birebir
> uygulanabilir** ( §4). Hiçbir servis "ulaşılamaz" değil — 23/23
> ayakta ve etiket okundu.

### 2.2 Kanıt komutu ( tabloyu yeniden üretmek için)

```bash
# canli currency taramasi
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8010 8011 8012 \
            8013 8014 8015 8016 8017 8018 8019 8020 8021 8022 8023 9001
do
  curl -s -m 4 "http://127.0.0.1:$port/" | grep -o '"currency": "[^"]*"'
done

# SesterMeter satir numaralari ( her repo icin)
grep -n "SesterMeter," x402_servis.py | head -1
```

---

## 3. SORUMLULUK SINIRI — DEĞİŞİKLİK YETKİSİ

> **KISIT ( lead'in 2. maddesi):** 23 servisin **hepsi ayrı repo**.
> **SADECE AnswRank üzerinde değişiklik yapabilirim.** Diğer 22'si
> için tablo "geçiş hazır, sahibi onay bekliyor" olarak işaretli —
> **onların dosyalarını DEĞİŞTİRMEDİM** ( sorumluluk sınırı).

| Repo havuzu | Servis sayısı | Benim yetkim | Yapılan |
|---|---|---|---|
| `02_sahis/85-AnswRank` | 1 ( answrank) | ✅ **TAM** | KOD-1 uygulandı ( 8e82128) |
| `02_sahis/*` ( diğer 19) | 19 | ❌ yok | yalnızca **okuma** ( bu tablo) |
| `01_unicorn/*` ( 2) | 2 ( pqhaven, borsa) | ❌ yok | yalnızca **okuma** |
| **TOPLAM** | **23** | 1 değişti | **22 dokunulmadı** |

> **DÜRÜST:** Diğer 22 servis için **kanıt ürettim** ( canlı etiket +
> kaynak kod satırı) ama **değişiklik yapmadım**. Her sahibi §4'teki
> deseni tek başına uygulayabilir.

---

## 4. GEÇİŞ DESENİ — her sahibin tek başına uygulayabileceği reçete

### 4.1 Komut ( her servis için — örn. callsnap)

```bash
# 1) repo'ya git
cd /home/gokun/projects/02_sahis/86-CallSnap

# 2) SesterMeter cagrisini bul ( satir numarasi yukaridaki tablodan)
grep -n "SesterMeter," x402_servis.py
#   -> 70:    SesterMeter,

# 3) currency parametresini ekle ( daily_quota= satirindan SONRA)
#    ONCEKI:
#        SesterMeter,
#        ledger=ledger,
#        price=PRICE,
#        daily_quota=DAILY_QUOTA,
#        secret=SELLER_SECRET,          <-- currency bunun ONCESINE
#    SONRASI:
#        SesterMeter,
#        ledger=ledger,
#        price=PRICE,
#        daily_quota=DAILY_QUOTA,
#        currency="USDC",               <-- EKLENEN TEK SATIR
#        secret=SELLER_SECRET,
```

**Tam dosya:satır örneği ( AnswRank, KOD-1 ile yapıldı):**

```python
# 02_sahis/85-AnswRank/x402_servis.py:81 ( SesterMeter,)
app.add_middleware(
    SesterMeter,                        # L81
    ledger=ledger,                      # L82
    price=PRICE,                        # L83
    daily_quota=DAILY_QUOTA,            # L84
    currency="USDC",                    # L85  <-- EKLENEN ( KOD-1)
    secret=SELLER_SECRET,               # L86
    pay_to=PAY_TO,                      # L87
    exempt_prefixes=(                   # L88
        ...
    ),
)
```

### 4.2 Doğrulama ( değişiklik sonrası)

```bash
# a) servisi yeniden baslat ( systemd ise)
systemctl --user restart unpump-agents.service   # veya ilgili unit

# b) etiketin degistigini kanitla
curl -s http://127.0.0.1:<port>/ | grep -o '"currency": "[^"]*"'
#   "currency": "USDC"     <-- olmali ( "USDC-sim" DEGIL)

# c) testler kirmadi mi
.venv/bin/python -m pytest tests/ -q   # mevcut sayidan az OLMAMALI
```

### 4.3 Risk analizi ( neden güvenli)

| Risk | Değerlendirme |
|---|---|
| **Receipt zinciri** | etkilenmez — HMAC + seq, currency'den bağımsız |
| **Sandbox shortcut** | çalışır — currency etiketinden bağımsız ( kanıtlandı) |
| **Fiyatlar** | değişmez — `price=`/`daily_quota=` dokunulmaz |
| **mainnet_verify** | zaten gerçek USDC ( 6-desimal) — etiket sadece bildirir |
| **Geri alma** | `currency="USDC"` satırını silmek yeter ( 1 satır) |
| **Kütüphane** | DEĞİŞTİRİLMEZ — `.venv` update'inde kaybolmaz |

> **AnswRank'ta kanıtlandı** ( 8e82128): KOD-1 sonrası canlı etiket
> `"currency":"USDC"`, sandbox çağrı → 200 ( seq 111), receipt zinciri
> `chain_valid: true`, fiyatlar aynı ( $0.05/$1.2/$0.2). **Testler
> kırılmadı** ( 1005 → 1005).

---

## 5. USDC ADRESİ — DOĞRU KAYNAK

> **⚠ DİKKAT — adres yanlış kopyalanamaz.** Geçiş yaparken ödeme adresi
> olarak **yalnızca** aşağıdaki kaynak kullanılmalı:

```bash
KANIT:  .venv/bin/python -c "import mainnet_verify as mv; print(mv.USDC_CONTRACT)"
RC:     0
CIKTI:  0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913   # GERCEK Base USDC
```

| Adres | Durum |
|---|---|
| `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | ✅ **GERÇEK** ( mainnet_verify.py kaynağı) |
| `0x833589fCD6e6D9a95819a6a7305d1c3a` | ❌ **YANLIŞ** ( eksik kopyalama — kullanılmaz) |

Ödeme hedefi ( treasury EOA, hepsi için tek-kasa):
```
0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5
```

---

## 6. KANIT ÖZETİ

```bash
# tablo olusturan tarama ( yukaridaki tablonun kaynagi)
for port in 8001..9001; curl :$port/ | grep currency      # 23 sonuc
for repo in .../86-CallSnap .../04-MCPGuard; grep -n SesterMeter, x402_servis.py

# mevcut testler korundu
.venv/bin/python -m pytest tests/ -q                        # 1011 passed, rc=0

# AnswRank KOD-1 kaniti
curl http://127.0.0.1:8007/ | grep currency                 # "USDC"
git -C 02_sahis/85-AnswRank show 8e82128 --stat             # KOD-1
```

**Korunan değerler:**
- **tests/ 1011 passed** ( altına düşmedi — bu görevde kod DEĞİŞMEDİ)
- **DM HOLD 0/20** — HİÇBİR DM GÖNDERİLMEDİ
- **Para harcanmadı** — yalnızca 127.0.0.1 taraması
- **Hiçbir dosya değiştirilmedi** — 22 servis dokunulmadı ( sorumluluk)
- **Servis kill EDİLMEDİ** — systemd yönetiyor ( `active`)

---

## 7. KARAR BEKLEYENLER

1. **22 servis sahibi onayı:** her biri §4 desenini uygulayabilir
   ( +1 satır, kütüphane değişmez). Tablo satır satım hazır.
2. **Öncelik sırası:** ilk müşteri AnswRank üzerinden geldiği için
   diğer 22'nin geçişi **acil değil** ( KOD-1 ile tek servis yeterli).
3. **Ortak paket:** 22 servisin ortak bir paketten mi yoksa her biri
   kendi `x402_servis.py`'inde mi değiştireceği ( lead'in açık kararı)

---

*Bu belge **kanıt tablosudur** — 23 servis tarandı, 22'si dokunulmadı.
Geçiş deseni AnswRank'ta kanıtlandı; her sahibi §4'ü tek başına
uygulayabilir.*
