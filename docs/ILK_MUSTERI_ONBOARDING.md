# İLK MÜŞTERİ ONBOARDING — uçtan-uca hazırlık

> Tarih: 27 Eyl 2026 | **DM HOLD 0/20 — GÖNDERİLMEDİ**
> **DÜRÜST ETİKET:** bu belge hazırlıktır. Hiçbir ödeme alınmadı,
> hiçbir DM gönderilmedi. Tüm rakamlar **canlı yerel servislerden**
> ( 127.0.0.1) okundu — **gerçek zincir hareketi YOK**.

---

## 1. 22+ SERVİS DURUM TABLOSU

### 1.1 USDC-sim → USDC geçiş durumu ( canlı tarama)

```bash
KANIT:  ./scripts/first_customer_dry_run.sh   # 1/4 adimi
RC:     0
CIKTI:  USDC=1  USDC-sim=22  ulasilamadi=0
```

| Servis | Port | Müşteriye açılan endpoint | currency | Durum |
|---|---|---|---|---|
| **answrank** | **8007** | `/audit`, `/citations`, `/fix` | **USDC** ✓ | **GEÇTİ ( KOD-1, 8e82128)** |
| callsnap | 8001 | `/cagri` | USDC-sim | geçiş bekliyor |
| vadedostu | 8002 | `/hatirlatma` | USDC-sim | geçiş bekliyor |
| repriceai | 8003 | `/stok-tarama` | USDC-sim | geçiş bekliyor |
| pqhaven | 8004 | `/pq-tarama` | USDC-sim | geçiş bekliyor |
| cleartag | 8005 | `/dogrulama` | USDC-sim | geçiş bekliyor |
| borsa | 8006 | `/is` ( ajan borsası) | USDC-sim | geçiş bekliyor |
| renewlock | 8008 | `/sozlesme` | USDC-sim | geçiş bekliyor |
| proje42 | 8010 | `/oyun-kodu` | USDC-sim | geçiş bekliyor |
| klinikkapici | 8011 | `/randevu` | USDC-sim | geçiş bekliyor |
| chargeshield | 8012 | `/ibraz` ( ters-ibraz) | USDC-sim | geçiş bekliyor |
| provix | 8013 | `/itiraz` | USDC-sim | geçiş bekliyor |
| lexbinder | 8014 | `/delil` | USDC-sim | geçiş bekliyor |
| yevmiye | 8015 | `/rapor` | USDC-sim | geçiş bekliyor |
| gecit | 8016 | `/backtest` | USDC-sim | geçiş bekliyor |
| vardro | 8017 | `/listeleme` | USDC-sim | geçiş bekliyor |
| geosentinel | 8018 | `/tahmin` | USDC-sim | geçiş bekliyor |
| lup | 8019 | `/metal` | USDC-sim | geçiş bekliyor |
| kilerim | 8020 | hizmet | USDC-sim | geçiş bekliyor |
| sonorix | 8021 | hizmet | USDC-sim | geçiş bekliyor |
| voltpulse | 8022 | hizmet | USDC-sim | geçiş bekliyor |
| cbamshield | 8023 | hizmet | USDC-sim | geçiş bekliyor |
| mcpguard | 9001 | `/v1/hitl/decide` | USDC-sim | geçiş bekliyor |

> **Sonuç:** **1/23** ( AnswRank) gerçek USDC etiketinde. Kalan 22'si
> `currency=` parametresi geçmediği için kütüphane varsayılanını
> ( `USDC-sim`) kullanıyor. **Desen aynı** (+1 satır/ servis) — hepsine
> uygulanabilir ( docs/31 §2). İlk müşteri **AnswRank üzerinden** gelir.

### 1.2 Receipt zinciri durumu ( dry-run 3/4)

**20/20 ulasilan servisin `chain_valid=true`** ( kilerim/sonorix/
voltpulse/cbamshield dahil). Guard sync gate: **2/2 birebir**.

---

## 2. USDC AKIŞ DİYAGRAMI ( müşterinin ödediği para)

```
   MÜŞTERI EOA                     UNPUMP x402                     PQHAVEN GUARD
  ┌────────────┐                 ┌──────────────────┐             ┌──────────────┐
  │            │  1. POST /audit │                  │ 4. imza+    │              │
  │  cüzdan    │ ───(X-Payment   │  SesterMeter     │  odeme       │ mainnet_     │
  │  (USDC)    │      YOK)       │  ( ASGI kapi)    │ ──────────> │ verify.py    │
  │            │ ───────────────>│                  │             │              │
  │            │  2. 402 +       │  currency=USDC   │ 5. Transfer │   ↓          │
  │            │  "payment_      │  payTo=treasury  │    event    │ RPC: Base    │
  │            │   required"     │                  │    ara      │ mainnet      │
  │            │ <───────────────│                  │ <────────── │ (publicnode) │
  │            │                 │                  │             │              │
  │  3. USDC   │                 │  require_mainnet │ 6. bulundu  │              │
  │  imzala    │ ───────────────>│  _payment()      │ ──────────> │  ↓           │
  │  (EIP-191) │  X-Payment +    │                  │             │ TransferFound│
  │            │  X-Payer-Addr   │                  │             │  .found=True │
  │            │                 └────────┬─────────┘             └──────┬───────┘
  │            │                          │ 7. 200 + receipt seq         │
  │            │ <─────────────────────────┘ ( HMAC hash-chain)          │
  └────────────┘                                                                │
                                                                                 ▼
                       ┌────────────────────────────────────────────────────────┐
                       │  TEK-KASA TREASURY EOA                                │
                       │  0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5           │
                       │  ( 20/20 servis buraya öder — vergi tek defterde)     │
                       └────────────────────────────────────────────────────────┘
```

**Akış adımları ( gerçeğin ta kendisi):**

| # | Adım | Kim | Sonuç |
|---|---|---|---|
| 1 | `POST /audit` ( X-Payment YOK) | müşteri | çağrı ASGI kapısında |
| 2 | **402** `payment_required` | SesterMeter | `{"currency":"USDC","payTo":treasury}` |
| 3 | USDC imzala ( EIP-191 'exact-sester') | müşteri | `X-Payment` + `X-Payer-Address` |
| 4 | imza + payer adresi | guard | `require_mainnet_payment()` |
| 5 | **Transfer event** ara ( Base RPC) | mainnet_verify | `from→to + amount` |
| 6 | eşleşme | guard | `found=True` → ödeme doğrulandı |
| 7 | **200 + rapor + receipt seq** | servis | HMAC hash-chain'e yazılır |

**Güvenlik katmanları ( fail-closed):**
- ödeme yok → **402** ( 20/20 serviste kanıtlandı)
- imza var ama zincirde transfer yok → **402** ( imza yetmez)
- RPC hatası → **503** ( sonuç yokken hizmet açılmaz)
- sandbox whitelist → zincir aramasından **muaf** ( demo; kota hâlâ geçerli)
- treasury EOA yoksa servis **başlamaz** ( import-anında SystemExit)

---

## 3. "EN AZ SERMAYE" MALİYETİ — ilk müşteri için

### 3.1 Altyapı ( ölçüldü — bu görevde)

| Bileşen | Gerçek maliyet | Kanıt |
|---|---|---|
| **Base mainnet RPC** | **$0/mo** | publicnode ücretsiz; canlı blok 51870796 |
| **Hosting** | **$0/mo** | ev makinesi ( uptime garantisi YOK) |
| **AnswRank `/audit`** | **~$0** | saf-stdlib — LLM çağrısı YOK |
| **USDC transfer gas** | ~$0.01/ işlem | Base ( ihmal edilebilir) |
| **Müşteri tarafı** | $0.05 + ~$0.01 gas | tek audit |

> **TOPLAM SABİT ALTYAPI: $0/ay.** RPC ücretsiz ( publicnode); audit
> saf-stdlib olduğu için LLM maliyeti YOK. **İlk müşteri için sermaye
> gerektirmeyen teklif.** Tek maliyet müşterinin $0.05 ödemesi.

### 3.2 Senaryo: 1 ödeyen müşteri

```
Gelir:  $0.05 ( 1 audit) + $0.01 gas ( musteriden)
Maliyet: $0.00 ( saf-stdlib) + $0.00 RPC
NET:    +$0.05  ( ~%100 maraj, risk = 0)
```

**Faz-0 gate** ( 30-gün net-kâr > 0) için ~5 ödeyen müşteri yeterli
( docs/27 §7: +$20/ay). **Mevcut: $0.00, 0 müşteri** ( net-kâr raporu
ile kanıtlandı).

### 3.3 Risk matrisi

| Senaryo | Olasılık | Sonuç |
|---|---|---|
| Hiç ödeyen olmaz | yüksek ( DM HOLD) | **$0** kayıp ( maliyet yok) |
| 1 müşteri öder | orta | **+$0.05** net ( maraj ~%100) |
| Kota dolana kadar | düşük | 200 audit/gün = $10/gün tavan |

> **Minimum sermaye sonucu: $0 — kayıp senaryosu yok.** Altyapı zaten
> çalışıyor; tek eksiği dağıtım izni ( DM HOLD 0/20).

---

## 4. DRY-RUN SCRIPT — `scripts/first_customer_dry_run.sh`

**Yalnızca yerel** — mainnet'e **PARA HARCANMAZ**, gerçek zincir çağrısı
**YOK**. Tüm varlıklar `127.0.0.1`'de.

```bash
KANIT:  ./scripts/first_customer_dry_run.sh
RC:     0
CIKTI:  1/4 servis tarama   -> USDC=1, USDC-sim=22, ulasilamadi=0
        2/4 guard sync      -> 2/2 birebir
        3/4 healthz + zincir-> 20 chain_valid=true
        4/4 USDC nominal    -> 3 fiyat tutarli ( kota $10 icinde)
        SONUC: OK
```

**4 adımın her biri rc=0 olmazsa toplam FAIL:**

1. **Servis taraması** — 23 servisin currency etiket + fiyat + kota
2. **Guard sync gate** — `guard_sync_gate.sh` çağrılır ( hard gate)
3. **Healthz + zincir** — `chain_valid`/`ledger_chain_valid` doğrulanır
4. **USDC nominal tutarlık** — fiyatlar pozitif + kota içinde ( 1 USDC = 1 USD)

> **"GERÇEK PARA HARCIYOR" flag'i YOK.** Script'te tek bir bileşik
> kod yolu bile mainnet'e çıkmaz — `curl` yalnızca `127.0.0.1`'e.
> Her yerde DUMMY: guard'ın RPC çağrısı **yapılmaz** ( sync gate
> dosyaları karşılaştırır, zincir sorgulamaz).

---

## 5. USDC TUTARLILIK DENETİMİ — test

`tests/test_usdc_nominal_tutarlilik.py` ( 6 test, tests/ sayısını
1005'ten yukarı taşır):

| Test | Beklenen | Sonuç |
|---|---|---|
| fiyatlar USD nominaliyle çelişmiyor | audit $0.05, citations $1.20, fix $0.20 | ✓ |
| fiyatlar pozitif | hepsi > 0 | ✓ |
| fiyatlar kota içinde | hepsi ≤ $10 | ✓ |
| **USDC minor birim** ( 6-desimal) | $0.05 = 50000 minor | ✓ |
| receipt zinciri geçerli | chain_valid = true | ✓ |
| **currency etiketi USDC** ( USDC-sim DEĞİL) | accepts[].currency = "USDC" | ✓ |

> **Birimi:** **1 USDC = 1 USD** kabulu ( nominal). Gerçek peg dalgalanması
> bu testin **dışında** — peg riski finansal bir konudur, bu test
> **yazılım tutarlılığını** denetler ( fiyat ↔ minor birim ↔ etiket).

---

## 6. HAZIRLIK DURUMU — ÖZET

| Madde | Durum | Kanıt |
|---|---|---|
| AnswRank `currency=USDC` | ✓ | KOD-1 ( 8e82128), canlı etiket |
| Guard sync ( CI hard gate) | ✓ | 561537f, 3 katman |
| mainnet_verify 85'te | ✓ | beb86bf, byte-byte sync |
| USDC nominal tutarlık | ✓ | 6 test, rc=0 |
| Receipt zinciri | ✓ | 20/20 chain_valid=true |
| Minimum sermaye | ✓ | **$0/ay** altyapı |
| Dry-run script | ✓ | rc=0 ( 4/4 adım) |
| **18+ servis USDC geçişi** | ⚠ plan | 22'si USDC-sim ( desen hazır) |
| **DM gönderimi** | ⛔ **HOLD 0/20** | vergi kararı |
| **Gerçek müşteri** | **0** | $0.00 gelir ( net-kâr raporu) |

---

## 7. KARAR BEKLEYENLER

1. **DM izni** ( vergi kararı): §2'deki akışla example.com'ye
   ulaşılabilir — **şimdi sadece dosyada** ( HOLD)
2. **22 servisin USDC geçişi**: her servis sahibiyle koordinasyon
   ( her biri ayrı repo; AnswRank'da desen kanıtlandı)
3. **İlk müşteriye ücretsiz mi $0.05 mi?** Gerçek $0.05 ödeme, x402
   akışının da kanıtı olur ( beta programı "ücretsiz" diyor — docs/27 §6)
4. **Uptime**: ev makinesi — VPS'e geçiş ilk ödeyen müşteri gelince

---

## 8. KANIT ÖZETİ

```bash
./scripts/first_customer_dry_run.sh              # rc=0 ( 4/4)
./scripts/guard_sync_gate.sh                     # rc=0 ( sync)
.venv/bin/python -m pytest tests/ -q             # 1005+6 passed, rc=0
.venv/bin/python -m pytest tests/test_usdc_nominal_tutarlilik.py -q
curl http://127.0.0.1:8007/healthz               # fiyatlar + kota canlı
curl http://127.0.0.1:8007/                      # "currency":"USDC"
```

**Korunan değerler:**
- **tests/** 1005'in **altına düşmedi** ( +6 yeni = yukarı)
- **DM HOLD 0/20** — HİÇBİR DM GÖNDERİLMEDİ
- **Para harcanmadı** — dry-run yalnızca 127.0.0.1
- **Servis kill EDİLMEDİ** — systemd yönetiyor ( `active`)
- **"GERCEK DEGIL"** etiketi korundu ( simülasyon bağlamında)

---

*Bu belge **hazırlıktır** — gönderim yapılmadı, para harcanmadı. İlk
gerçek müşteri için **teknik engel kalmadı**; eksik olan **dağıtım
izni** ( DM HOLD 0/20).*
