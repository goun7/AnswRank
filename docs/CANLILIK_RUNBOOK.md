# AnswRank Canlılık Runbook'u (v4.0+ · 16 Eyl 2026)

Tek-kiracılık, kapalı-kaynak (LicenseRef-AnswRank-Proprietary, D-16.09-L) bir AnswRank
instance'ını ayakta tutmanın işletim kılavuzu. Doktrin: **ölçülemeyen hiçbir şey müşteriye
sayı olarak gitmez**; sistem sessizce karar vermez — dışa-dönen her fiil `answrank queue`
onayından geçer.

## 0) Kurulum bir kerelik

```bash
python3 -m answrank.cli serve --host 127.0.0.1 --port 8123     # landing + dashboard + API
```

- Port 8123: bu makinedeki DSH GUI 8123'ü kullanır — canlıda **başka port seçin** ve
  reverse-proxy'yi (Caddy/Nginx, TLS için `localhost:SEÇİLEN_PORT`a proxy) kendiniz kurun;
  AnswRank TLS sonlandırması SUNMAZ (iddia yok).
- Systemd unit örneği (ExecStart serve'i sarmalar) standarttır; örnek dosya vermiyoruz
  çünkü üretilmedi — üretilmeden "hazır" denmez.
- Ortam değişkenleri (hepsi gerçek, koddan):
  - `ANSWRANK_DB_PATH` — SQLite dosyası (varsayılana dokunmayın; YEDEK bu dosyadır).
  - LLM anahtarları: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
    `PERPLEXITY_API_KEY`, `MISTRAL_API_KEY` (+ `SERPAPI_API_KEY`). Anahtarsız sistem
    çalışır ama atıf ölçümü **TAM SİMÜLASYON bandarıyla** çalışır — Madde-7'li satış
    vaadi için en az BİR gerçek motor anahtarı şarttır.
  - `ANSWRANK_FX_RATES` — döviz kurları; verilmezse sabit-defter kurları kullanılır ve
    her fatura satırında `fx_source=static_default` olarak KAYITLI GEÇER (canlı kur
    iddiası yoktur).

## 1) Günlük operatör ritüeli (~10-15 dk, tek yüzey)

```bash
answrank queue scan     # lead/sözleşme/izleme maddelerini türet (boşsa 0 der, uydurmaz)
answrank queue list     # tek ekran: her PENDING madde + gerekçe
answrank queue approve 3 --note "DM gönderildi"    # ya da reject
```

Dashboard'daki **Onay Kuyruğu** kartı aynı kuyruğun tek-tık yüzeyidir. Kuyruk türleri ve
anlamları:

| Tür | Ne zaman türer | Sizin kararınız |
|---|---|---|
| DM | ölçümlü mini-probe lead'i **veya otonom prospektör'ün stage ettiği gerçek işletme** | gönder / gönderme (gönderim elle — sistem hiçbir e-posta atmaz) |
| CONTRACT | sürü hattı sözleşme üretti (`CONTRACT_ISSUED`) | teslim/imza sürecini başlat |
| FREE_CYCLE | Madde 7.3 tetiklendi (ölçülen delta < +12) | gelir-düşüren karar — muhasebe onayı sizde |
| MONITOR_INTERVENTION | 3+ ardışık izleme koşusu ölçülemedi | erişimi müşteriden iste ya da izlemeyi kapat |

Karar defteri çift-kararı reddeder (409): bir madde bir kez karara bağlanır.

## 1b) Tahsilat (E11 — ödeme altyapısı hazır, PSP anlaşması bekliyor)

```bash
answrank payments status                          # kanalların dürüst durumu
answrank payments collect --brand X --country AE --currency AED --amount 5500
answrank payments confirm --intent PAY-00001 --proof "DEKONT-2026-xxx"
answrank payments refund --intent PAY-00001 --reason "İptal — denetim izi"
```

- **PSP anlaşmamız yok** — PAYTR/IYZICO/PADDLE 'YAPILANDIRILMAMIŞ' der; sahte 'ödendi' üretmez.
- **MANUAL (havale)** bugün çalışır: bankada para görülüp dekont girilince fatura doğar.
  Para bankada gerçekten yoksa onaylamayın — sistem size güveniyor, kanıt dekont.
- **Rejim ülkeyle otomatik:** yurt dışı → %0 KDV + %100 indirim (11257 CBK 2026);
  TR iç pazar → %20 KDV. Yanlış ülke kodu vergiyi bozar — dikkat.
- **Webhook** (PSP anlaşınca): imza HMAC ile doğrulanır, aynı olay iki fatura kesmez.
- **İade** faturayı silmez, credit note ile ters kayıt atar (denetim izi için).

## 2) Haftalık/aylık nabız

```bash
answrank monitor run          # vadesi gelen TÜM izlemeleri ölç (cron'a uygun, argsız)
answrank monitor fulfillment  # tüm sözleşmeli izlemelerde 7.3 hükmü (yalnız ölçümlü delta)
answrank economics            # birim ekonomisi/MRR projeksiyonu (girdileri DB'den gerçek)
```

FREE_CYCLE maddeleri otomatik kuyruğa düşer — **kabul = gelecek 30 gün ücretsiz icra**;
reddetmezseniz müşteriye fatura kesmeyin (Madde 7.3 hukuku).

## 3) Yedek ve bütünlük

```bash
sqlite3 "$ANSWRANK_DB_PATH" ".backup /yedek/answrank-$(date +%F).db"
sqlite3 /yedek/answrank-$(date +%F).db "PRAGMA integrity_check;"   # 'ok' beklenir
```

Cron'lanmamış yedek = yedek değildir. DB tek gerçektir: izleme koşuları, fulfillment
olayları, kuyruk kararları, fatura defteri, korpüs gözlemleri hepsi orada.

## 4) İlk pilot kapıları (YAZILIMIN KENDİLİĞİNDEN YAPAMAYACAKLARI — dürüst liste)

1. **Gerçek lead listesi** — tahminî domain taraması yapılmaz (UAE turunda denendi,
   çözülen olmadı; kanıt sayılmadı). Hastane/klinik domainlerini siz verin.
2. **En az 1 canlı motor anahtarı** — "5 motorda ölçtük" cümlesinin ticari karşılığı.
3. **Avukat gözden geçirmesi** — sözleşme üretici (Madde 7/7.4/7-A/9) testli hukuki
   mantıktır, hukuki danışmanlık değildir; şablon imzaya çıkmadan önce avukat onaylıdır.
4. **Fiyat onayı** — ₺6.000 retainer + ₺2.500 izleme + AED 5.500 ihracat tek kaynaktır
   (`answrank/config.py`); landing/DM/sözleşme aynı kaynaktan beslenir, değişikliği
   orada yapın, kilit testler yakalar.
5. **Ödeme/tahsilat hattı** — AnswRank fatura KAYDI tutar (tax_invoices, rejimli), para
   TAHSİL ETMEZ; banka/POS entegrasyonu insan işidir.

## 5) Olay müdahalesi

- **Müşteri "neden ÖLÇÜLEMEDİ?" diye sorarsa:** bu başarısızlık değil sözleşmedir —
  site sizin botlarınıza kapalı olabilir (robots.txt/BotScore/WAF). Kanıt: `corpus list`
  / monitor run not satırı. Çözüm müşterinin erişim vermesi; biz sayı uydurmuyoruz.
- **429 (mini-probe kotası):** `mini_probe_daily_limit_per_ip` (varsayılan 10/gün) —
  ayar config'de tek kaynak.
- **500 detayları:** API ham exception metni İÇERMEZ ("iç hata" + log'da `logger.exception`
  kanıtı). Log dosyası sizde kalır; müşteriye asla sızdırılmaz (testli).
- **DB'ye elle sayı yazmak YASAKTIR** — tüm yüzeyler DB'yi okur; elle eklenen satır
  müştereye giden uydurma sayı olur ve tüm garanti mimarisini çökertir.

## 6) Kilitli kapılar (yazılımın yapmadığı şeyler — iddia edilmez)

E8 dondurulmuş; çok-kiracılı SaaS yok (tek instance = tek tenant); OSS dağıtım yok;
Deep-report kalıcı paneli yok (persistence'siz panoyla sayı satılmaz); screenshot audit
trail roadmap'te (rakip farkı olarak kayıtlı, henüz yok).
