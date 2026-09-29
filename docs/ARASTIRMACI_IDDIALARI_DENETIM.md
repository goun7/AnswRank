# Araştırmacı İddiaları Denetimi — kod karşısında doğrulama

> Tarih: 28 Eyl 2026 | **DİSİPLİN:** her iddia KOD OKUNARAK doğrulandı —
> varsayım YAPILMADI. Araştırmacının "2 FAIL" ve "Türkçe bug" iddiaları
> Lead tarafından zaten **çürütüldü** ( 1069 passed, 0 FAIL; `grep "klinik"`
> arıyor, unicode bug yok).

---

## İDDİA 1 — "iş kuyruğu süreç-içi bellekte → ilk eşzamanlı 2 müşteride darboğaz"

### Araştırmacının söylediği
> `README.md:107`'de iş kuyruğu süreç-içi bellektedir; ilk eşzamanlı iki
> müşteride darboğaz.

### Koddaki gerçek

```bash
KANIT:  grep -n "self._jobs" answrank/api/jobs.py
RC:     0
CIKTI:  65:        self._jobs: Dict[str, Job] = {}
        62:    """In-memory background job registry with progress callbacks and SSE support."""
```

```bash
KANIT:  grep -n "import queue\|redis\|sqlite" answrank/api/jobs.py
RC:     1 ( bulunamadi)
CIKTI:  ( bos — Redis/SQLite/sqlite3 YOK, yalnizca Dict + asyncio.Queue)
```

**Süreç-içi bellek = DOĞRU.** Ama araştırmacının okuduğu **satır yanlış**:
`README.md:107` ChargeShield over-claim kuralıdır; iş kuyruğu satırı
**README.md:131**'dedir ( README zaten bunu dürüstçe itiraf ediyordu).

### "Darboğaz" iddiası — ÇÜRÜTÜLDÜ

Araştırmacı "ilk eşzamanlı 2 müşteride darboğaz" varsayımını koddan
TÜRETMEDİ. Kod okundü:

```bash
KANIT:  grep -n "asyncio.create_task" answrank/api/jobs.py
RC:     0
CIKTI:  96:        job._task = asyncio.create_task(_runner())  # her iş kendi task'i
```

```bash
KANIT:  grep -n "httpx.AsyncClient\|await client.get" answrank/audit/crawler.py
RC:     0
CIKTI:  171:  async with httpx.AsyncClient(...
        182:  response = await client.get(url)   # GERÇEK async I/O
```

**Ampirik test** ( JobManager + 2 eşzamanlı async iş):

```
2 eszamanli async is: 0.51 sn ( paralelse ~0.5, seri ise ~1.0)
```

> **SONUÇ: 0.51 sn** — 2 iş **PARALEL** koştu ( seri olsa 1.0 sn).
> "Darboğaz" iddiası **ÇÜRÜTÜLDÜ**. Araştırmacı sync kuyruk varsaymış,
> oysa `asyncio.create_task` + `httpx.AsyncClient` gerçek async.

### GERÇEK sınırlama ( farklı şey!)

```bash
KANIT:  grep -c "treasury-required\|secret-required" service.log
RC:     0
CIKTI:  0 ( SystemExit hiç atılmadı — env.production set ediyor)
```

Süreç-içi olmanın **asıl bedeli eşzamanlılık DEĞİL, kalıcılıktır**:
- `JobManager._jobs` bir `Dict`'tir — **süreç ölünce kaybolur**
- watchdog `Restart=always` olduğundan, restart = devam eden işler KAYBOLUR
- yatay ölçek ( çok süreç) imkansız

**Senkron CPU parçası** ( ölçüldü):

```
audit_crawl_data ortalama: 54.2 ms ( orta olcekli sayfa)
```

`audit_crawl_data` ( `engine.py:50`) **senkron** ve event loop'u ~54 ms
bloklar — I/O async olmakla birlikte. 2 müşteri için ihmal edilebilir
( denetim ~1-2 sn), ama CPU-ağır sayfalarda istifleşebilir.

---

## İDDİA 2 — "SystemExit import-zamanı fail-closed — gizli crash riski mi?"

### Araştırmacının söylediği
> `SystemExit` import-zamanı fail-closed — bu doğru davranış mı, yoksa
> gizli bir crash riski mi?

### Koddaki gerçek

```bash
KANIT:  grep -rn "raise SystemExit" x402_servis.py mainnet_guard.py
RC:     0
CIKTI:  x402_servis.py:56     raise SystemExit("secret-required: ...")
        mainnet_guard.py:63   raise SystemExit("treasury-invalid: ...")
        mainnet_guard.py:71   raise SystemExit("treasury-invalid: ...")
        mainnet_guard.py:76   raise SystemExit("treasury-required: ...")
```

**Belge:** `mainnet_guard.py:56-58` docstring'i **kasıtlı** diyor:

> "Bu fonksiyon x402_servis.py'lerin MODÜL-BAŞINDA çağrılır; import-anında
> patlar → uvicorn başlamaz → systemd Restart=always döngüsü bile
> ödeme-hedefisiz servis kurmaz ( rc≠0)."

**Bu bir BUG DEĞİL — tasarımdır.** Açıklama: ödeme-hedefi boş bir servis
ücretsiz hizmet sunar ( fail-open); bunu engellemek için **fail-closed**
kasıtlı olarak import-anına konmuş.

### Crash riski var mı? — YOK ( temiz exit code 1)

```bash
KANIT:  temiz env ile import denerse
RC:     1
CIKTI:  exit code: 1
        SystemExit mesajı: treasury-required: UNPUMP_TREASURY_EOA-ZORUNLU — ...
```

- **exit code 1** — `SystemExit` ile **temiz çıkış**; backtrace/segfault DEĞİL
- mesaj operatöre **tam olarak neyi set edeceğini** söylüyor
- normal işletmede **ATESLENMEZ** ( `.env.production` 2/2 env set ediyor)

### TEK GERÇEK BOŞLUK ( lead için öneri)

```bash
KANIT:  grep -n "StartLimit" unpump-agents.service
RC:     1 ( bulunamadi)
CIKTI:  ( bos — StartLimitBurst/StartLimitInterval YOK)
```

- `Restart=always` + **StartLimit YOK** → env kaybolursa **sonsuz yeniden
  başlatma döngüsü** ( 15 sn arayla)
- **ÖNERI:** unit'e `StartLimitBurst=5` + `StartLimitIntervalSec=120` eklenirse
  yanlış-config durumunda systemd durur ve alarm verir ( sessiz döngü YERINE)
- **ACİL DEĞİL** — env.production env'i set ettiği için bu yalnızca
  yanlış yapılandırma senaryosunda ortaya çıkar

### ✅ UYGULANDI ( 28 Eyl 2026 — Lead onayı ile)

```diff
--- /home/gokun/.config/systemd/user/unpump-agents.service ( once)
+++ /home/gokun/.config/systemd/user/unpump-agents.service ( sonra)
 [Unit]
 Description=Unpump gateway + 6 x402 ajan servisi (API gateway :8000)
 After=network-online.target
 Wants=network-online.target
+# Yanlış-config'te ( env kaybolursa) sonsuz restart döngüsünü önle:
+# 120 sn içinde 5 başarısız başlangıç → systemd DURUR ve alarm verir
+# ( fail-closed SystemExit rc≠0 ile tetiklenir; sessiz döngü YERİNE)
+StartLimitIntervalSec=120
+StartLimitBurst=5
```

```bash
KANIT:  systemctl --user show unpump-agents.service | grep StartLimit
RC:     0
CIKTI:  StartLimitIntervalUSec=2min
        StartLimitBurst=5
        StartLimitAction=none
        Restart=always
```

```bash
KANIT:  systemctl --user status unpump-agents.service
RC:     0
CIKTI:  Active: active (running) since Mon 2026-09-28 09:54:26 +03; 1h 7min ago
        Main PID: 3859668 (python)   <-- RESTART YAPILMADI ( uptime korundu)
```

> **KISIT KORUNDU:** `systemctl --user daemon-reload` yapıldı ( unit
> yeniden okundu) ama servis **RESTART EDİLMEDİ** — daemon-reload çalışan
> servisleri DURDURMAZ, yalnızca bir sonraki başlangıçta uygulanır.
> Healthz :8007 → **200** kesintisiz.

---

## ÖZET

| # | İddia | Doğrulama | Karar |
|---|---|---|---|
| 1a | İş kuyruğu süreç-içi bellek | `jobs.py:65` `Dict[str, Job]` | **DOĞRU** ( README zaten itiraf ediyordu, satır 131) |
| 1b | "İlk 2 eşzamanlı müşteride darboğaz" | 2 iş 0.51 sn ( seri=1.0) | **ÇÜRÜTÜLDÜ** — gerçek async, paralel |
| 1c | ( bulgu) kalıcılıksızlık | süreç ölünce işler kaybolur | **GERÇEK sınırlama** — README'ye eklendi |
| 2a | SystemExit import-zamanı | `mainnet_guard.py:56-58` belgeli | **DOĞRU ve KASITLI** ( fail-closed tasarım) |
| 2b | "Gizli crash riski" | exit code 1, backtrace YOK | **ÇÜRÜTÜLDÜ** — temiz çıkış, crash DEĞİL |
| 2c | ( bulgu) StartLimit YOK | `Restart=always` sonsuz döngü riski | **DÜZELTİLDİ** ✅ — `StartLimitBurst=5` eklendi ( 28 Eyl) |

> **DİSİPLİN NOTU:** araştırmacının 5 iddiasından 3'ü çürütüldü ( 2 FAIL,
> Türkçe bug, 2-müşteri darboğazı), 2'si doğru ama **eksik okundu** (
> süreç-içi = doğru ama satır yanlış; SystemExit = doğru ama "gizli crash"
> yorumu yanlış). Bu nedenle dış raporlar **koda karşı doğrulanmadan
> alıntılanmamalı** — bu README politikasıdır ( bkz `readme_stats.py`).
