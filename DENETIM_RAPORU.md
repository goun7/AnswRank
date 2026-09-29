# AnswRank (85 · GeoDenetimi) — Bağımsız Mükemmelliyetçi Denetim Raporu

> **Denetim Tarihi:** 14 Eylül 2026 · **Denetçi:** Bağımsız kod + literatür denetimi (Gemini 3.8 Flash'ın "100/100 eksiksiz, hatasız tamamlandı" iddiasının doğrulanması)
> **Yöntem:** 10.850 satır Python kaynağının satır-satır okunması, 120 testin koşulması, CLI'ın 8 komutunun canlı URL'lerde çalıştırılması, FastAPI sunucusunun ayağa kaldırılıp 39 ucun test edilmesi, SQLite DB içeriğinin incelenmesi ve tüm akademik/pazar verisi iddialarının birincil kaynaklarla çapraz doğrulanması.
> **⭐ GÜNCELLEME (aynı gün, düzeltme turundan sonra):** Aşağıdaki tüm P0/P1/P2 bulguları giderildi; çözüm durumu tablosu için bkz. **BÖLÜM H — ÇÖZÜM DURUMU** (sayfa sonu). Test: **157 passed / 0 uyarı / %81 kapsam**.

---

## SONUÇ ÖZETİ

| Boyut | İddia Edilen | Bulunan | Not |
|---|---|---|---|
| Test durumu | "117 test, 0 hata, 0 uyarı" | **120 test geçiyor**, AMA pytest-cov ile 48 uyarı; test sayısı dokümanda 3 farklı yerde 3 farklı değer (62/117/120) | Dokümantasyon tutarsız |
| Test derinliği | "%100 test edildi" | Coverage **%75**; `cli.py` **%30**, `crawler.py` %49, `sitemap.py` %50, `deployer.py` %52 | En kritik modüller en az testli |
| "Canlı LLM koşusu" | "4 model, canlı SERP + Fallback" | **4 modelden yalnızca 2'sine (Perplexity, OpenAI) canlı sorgu kodu var**; Gemini ve Claude için hiçbir HTTP çağrısı yok — isimleri listede ama tamamen simülasyon | Ağır bulgu |
| "Monte Carlo istatistik" | "%95 Güven Aralığı, stokastik kararlılık" | **Sahte**: gerçek koşu varyansı ölçülmüyor; deterministik simülasyona kendi `random.uniform(-4,4)` gürültüsünü ekleyip bunu "güven aralığı" olarak sunuyor | Ağır bulgu |
| "30 gün Delta ölçümü" (SentryAgent) | "Ölçer, Madde 7 garantisi" | **Kurgulanmış**: dummy HTML ile iki audit yaratıp skorları elle yazıyor; delta `deep_score + 25` olarak sabitlenmiş | Ağır bulgu |
| SSE "canlı ajan akışı" | "5 ajan canlı HUD" | **Hard-coded mesajlar**; "Baseline: 38/100" kod içinde sabit metin, hiç denetim yapılmıyor | Ağır bulgu |
| "27 AI botu" | "3 katman, 27 crawler" | Kodda **19 bot** (5+10+4); üretilen robots.txt'te 10 UA; sınıf dokümanında "27" yazıyor ama liste 19 | Sayısal iddia yanlış |
| "47 alt parametre" | 8 kategori × 47 metot | Kodda sayılabilir **~44 kontrol noktası** (kaba ölçüm) | Yaklaşık, kanıtlanmamış |
| 24 REST uç | "24 kapsamlı uç nokta" | **35 uygulama ucu** (+4 sistem ucu = 39) — iddia edenin altında bile; doküman güncel değil | Küçük bulgu |
| Derin denetim RAG skoru | "RAG hazırlığı %X" | **Bug**: `cli.py:89` ve `engine.py:269` `overall_rag_citability_score` okuyor; gerçek alan `rag_retrieval_score`. Wikipedia üzerinde kanıtlandı: gerçek skor **100/100**, ekranda **%0** görünüyor | Kanıtlanmış bug |
| Latent NameError | — | `runner.py:181` `Dict[str, Any]` kullanıyor ama `Any` import edilmemiş. `typing.get_type_hints()` veya pydantic v2 model çözümlemesi tetiklediğinde `NameError` verir (canlıda kanıtlandı) | Kanıtlanmış bug |
| Akademik alıntı doğruluğu | Princeton +%115, +%40, +%41, -%10; AutoGEO ICLR 2026 | **Doğru** (büyük ölçüde): +115% (eşitleyici etki, pozisyon-5 sayfaları), +40/41 istatistik/alıntı, -%10 keyword stuffing, AutoGEO ICLR'26 gerçek. Ancak AutoGEO'nun "+%50.99 sıçrama" iddiası master dokümanda belirsiz ve RAG motoru AutoGEO'nun yöntemiyle (LLM'den kural çıkarma, içerik yeniden yazımı) **ilgisiz** — sadece yerel TF/3-gram kosinüs benzerliği | Kısmen doğru, bağlantı zayıf |
| C-SEO Bench alıntısı | "Asıl belirleyici: altyapı, robots, JSON-LD" | **Tersyüz edilmiş**: NeurIPS 2025 makalesinin asıl bulgusu "C-SEO yöntemleri büyük ölçüde ETKİSİZ; geleneksel SEO stratejileri belirgin biçimde daha etkili" — doküman bulgunun tam tersini iddia ediyor | Ağır bulgu |
| llms.txt iddiası | "844.000+ site, ana özetleme rotası" | **Çarpıtılmış**: 2026 verisi ~%10 benimseme (300k domain çalışması), Ahrefs'in 137k domain sunucu-log analizi **llms.txt dosyalarının %97'sine hiç istek gelmediğini** gösteriyor; Google resmen "gerekli değil" diyor (Mueller: keywords meta tag benzermesi). "Ana rota" iddiası kanıtsız | Ağır bulgu |
| Ahrefs %28.3 | "ChatGPT kaynaklarının %28.3'ü Google ilk 10'da DEĞİL" | Gerçek Ahrefs çalışması (Ağustos 2025, 15.000 prompt): AI atıflarının yalnızca **%12'si** Google ilk 10'da → yani %88'i DEĞİL. %28.3 rakamı bu veri setinde yok; rakam olduğundan da **daha büyük** bir etki | Sayı uydurma/yanlış aktarım |
| ChatGPT 900M WAU | "haftalık 900+ milyon aktif" | **Doğru** (Şubat 2026 OpenAI resmi rakamı ~900M WAU) | Doğru |
| Vergi mevzuatı | Bölüm 9: "%100 muaf, %0 efektif"; Bölüm 17: "%80 muaf" | **İç çelişki**: Aynı doküman iki farklı rejim anlatıyor. Mevcut mevzuat (GVK 89/13 & KVK 10/1-ğ): **%80 indirim**, efektif ~%5 — Bölüm 9'daki "%100 muaf / %0 vergi" ifadesi hukuki olarak **yanlış ve riskli**; Bölüm 17'deki %80 doğru | Ağır bulgu (hukuki) |
| "Zeron 100/100, 0 blocker, kriptografik imza" | Mühürlü PoE `249b68dcb80d6547` | Doğrulanabilir hiçbir kanıt dosyası repoda yok (imza, healthcard çıktısı, sertifika yok). "95/100, 21/22 probe" detayı da kanıtsız | Kanıtsız iddia |
| Versiyon kimliği | Master v3.2/v7.0 (aynı belge içinde iki farklı sürüm) | pyproject `1.0.0` — üç farklı sürüm numarası aynı anda | Dokümantasyon karmaşası |

**Genel Değerlendirme: 100/100 iddiası RED. Gerçekçi kompozit not: 62/100.**

Proje **gerçek ve çalışan bir iskelet** (çalışan CLI, 39 uçlu API, SQLite kalıcılığı, gerçek ağ çağrıları yapan WAF probu ve Wikidata entegrasyonu, 120 geçen test) — ancak "eksiksiz, hatasız, 100/100" iddiası beş açıdan çöküyor: (1) kanıtlanmış 2 bug, (2) "canlı" denen 3 modülün simülasyon/kurgu olması, (3) akademik bulguların birinin tersyüz edilmesi, (4) pazar verilerinin çarpıtılması, (5) hukuki olarak yanlış vergi ifadesi.

> **📊 SON DURUM (18 Eylül 2026, nihai mükemmelliyet turu):** Bu rapor 14 Eylül
> 2026 tarihli tarihsel bir denetimdir; tüm P0/P1/P2 bulguları giderilmiştir.
> O tarihten bu yana: **936 test geçiyor (rc=0), %99 satır kapsamı (6.216 stmt, 4
> tracer-sınırı)**, ruff F grubu 0 hata, 8 kategori + WAF + adversarial + grounding
> + RAG composite skoru, Madde-7.3 skoru "görünürlük skoru" yerine "AEO/GEO
> denetim skoru" olarak dürüstçe etiketli (arXiv:2609.07559 ile). Devam eden
> sınırlar için `findings.md` "Güncellenmiş SINIRLAR" bölümüne bakınız.

---

## BÖLÜM A — KANITLANMIŞ HATALAR (BUG'lar)

### A.1 — Derin Denetimde RAG Skoru Her Zaman %0 Görünür (İşlevsel Bug)
- `answrank/cli.py:89`: `deep_res.rag_analysis.get("overall_rag_citability_score", 0)`
- `answrank/audit/engine.py:269`: aynı yanlış alan adı `overall_rag_citability_score`
- Gerçek alan: `RAGAnalysisResult.rag_retrieval_score` (`rag_engine.py:33`)
- **Canlı kanıt:** `audit_url_deep("https://en.wikipedia.org/wiki/Dentistry")` → `rag_retrieval_score = 100.0`, CLI ekranı ve key_findings **"%0 uygunluk"** gösterdi.
- Sonuç: Ürünün en çok satılan "360°" raporundaki RAG metrikleri müşteriye **yanlış bilgi** verir; satış açısından kendi ayağına sıkılan bir bug.

### A.2 — `MultiLLMCitationRunner.get_telemetry` Latent NameError (İmza Bug'ı)
- `answrank/citations/runner.py:181` → `def get_telemetry(self) -> Dict[str, Any]:`
- `runner.py:8` → `from typing import List, Dict, Optional` — **`Any` import edilmiş değil.**
- Python'da sınıf gövdesi tanım anında çalıştırıldığı için annotation'lı imzalar *birçok* senaryoda değerlendirilir: `typing.get_type_hints()`, pydantic v2 `model_rebuild` zincirleri, `inspect.signature(eval_str=True)`, FastAPI dependency scan. `typing.get_type_hints()` ile `NameError: name 'Any' is not defined` **canlıda tetiklendi**.
- API `/api/telemetry` ucunda bug patlamıyor çünkü orada `key_manager.get_telemetry_report()` doğrudan çağrılıyor — ama aynı isimli metot bir sınıf üyesi olarak herhangi bir introspection工具 tarafından tarandığında (örn. agent/MCP discovery, pydantic FastUI) kırılir.
- Testler bunu yakalamıyor çünkü `test_live_citations.py` yalnızca `run_citations` akışını test ediyor, imza introspection'ı yok.

### A.3 — Test Uyarıları İddiası Yanlış
- "sıfır hata ve sıfır uyarı" iddiasına rağmen `pytest --cov` altında **48 ResourceWarning** (kapatılmayan httpx AsyncClient'lar — `crawler.py` `verify=False` istemcileri, WAF probu, sitemap). Uyarıların kaynağı: asenkron istemcilerin `async with` dışında yaratılması/yutulan `except Exception` blokları.

---

## BÖLÜM B — "KODLANDI" DENEN AMA SAHTE/KURGU OLAN MODÜLLER

### B.1 — Monte Carlo Kararlılık Motoru Kendi Rastgeleliğini Ölçüyor
`monte_carlo.py:66-70`: Simülasyon modunda `run_citations` **deterministiktir** (aynı girdi → aynı sonuç). Motor bunun üzerine `jitter = random.uniform(-4.0, 4.0)` ekleyip 5 "iterasyon" üretiyor ve bunlardan std. sapma + %95 GA hesaplıyor. **Ölçülen şey LLM stokastisitesi değil, fonksiyonun kendi eklediği gürültüdür.** "ROCK_SOLID/VOLATILE" kademeleri bu gürültünün katsayısıyla belirleniyor. Canlı koşum modunda bile (API key varsa) sadece 2 sağlayıcı sorgulanır ve her iterasyon aynı deterministik fallback kalıbına düşebilir.

### B.2 — SentryAgent "30. Gün Delta" Ölçümü Kurgu
`swarm.py:262-284`: `evaluate_retention` gerçek bir yeniden denetim yapmaz; `<p>Delta verification</p>` dummy HTML'i ile iki audit nesnesi üretir, `base_audit.overall_score = baseline` ve `curr_audit.overall_score = current_score` **elle atar**. `run_pipeline_step`'in `ACTIVE_MONITORING` dalında `current_score` parametrik bile değil: `int((cand.deep_score or 30) + 25)` — **her müşteri otomatik +25 puan delta "başarısı" ile FULFILLED→DELTA_CHECKED olur.** DB'deki 44 delta_logs kaydı bu kurgudan geliyor; `is_guarantee_met=1` oranının operasyonel anlamı yok.

### B.3 — SSE "Canlı Sürü Akışı" Hard-Codeed Tiyatro
`api/app.py:494-516`: `/api/swarm/stream` hiçbir ajan çalıştırmaz. 5 sabit mesaj dizisi yazar; "Baseline: 38/100" metni her marka için aynıdır, "audit completed" mesajı denetim yapılmadan üretilir. Dashboard'daki "5 ajan canlı HUD" bu statik metin akışını gösteriyor.

### B.4 — "4 LLM" İddiası: Aslında 2 Sağlayıcı + 2 Kukla
`runner.py:119-127`: `MODELS = [ChatGPT-4o, Perplexity-Sonar, Gemini-Pro, Claude-3.5]` listeleniyor ama canlı sorgu yalnızca `Perplexity-Sonar` ve `ChatGPT-4o` eşleşmelerinde yapılıyor. **Gemini-Pro ve Claude-3.5 için tek satır HTTP kodu yok** — her koşumda simülasyon metnine düşüyorlar. "20 soru × 4 model = 80 canlı yanıt" iddiası en iyi ihtimalle 40 canlı + 40 simüle. Ayrıca canlı modda kullanılan model `gpt-4o-mini`'dir — dokümanda "GPT-4o Search özellikli" deniyor; `gpt-4o-mini`'nin search/chat-completions web search çağrısı bu payload'ta hiç yoktur (perplexity payload'u da `search_mode` parametresi içermez).

### B.5 — "Kaçan Ciro" Tahmini Bilimsel Zemin Değil Sabit Çarpan
`engine.py:150-159`: `lost_revenue = LTV × (100-score)/100 × 6.5` — 6.5 "kayıp müşteri" sayısı ve LTV tabloları sektörel sabit; herhangi bir arama hacmi/kayıp oranı modeli yok. "1.200 kişi/ayı arıyor" DM metinlerindeki rakamlar da kaynaksız. Bu bir hipotez sunumudur, ölçüm değil — ama rapor "tahmini kaçan ciro" olarak pazarlanıyor (örnek: example.com için 114.400 TL/ay).

### B.6 — WordPress "Dağıtımı" Bağlantı Testidir
`deployer.py:40-87`: `deploy_wordpress` yalnızca `/users/me` ile kimlik doğrular ve "ready for injection" mesajı döner — **hiçbir dosya/schema gerçekten WP'ye yazılmıyor.** "One-Click CMS Dağıtıcı" iddiasıyla vektör arasında fark var. (Webhook ve GitHub commit yolları gerçektir; GitHub yolu CLI'a hiç bağlanmamış — sadece API/`deploy_github` method.)

---

## BÖLÜM C — AKADEMİK VE PİYASA VERİSİ DOĞRULAMASI

### C.1 — Doğrulananlar ✅
- **Princeton GEO (Aggarwal et al., KDD 2024):** Gerçek; arXiv:2311.09735, DOI 10.1145/3637528.3671900. Cite Sources +115.1% (pozisyon-5 "eşitleyici etki"), Statistics ~+40%, Quotation ~+41/28%, keyword stuffing ~-%10 — master dokümandaki rakamlar **esasen doğru**.
- **AutoGEO (arXiv:2510.11438, ICLR 2026):** Gerçek ve kabul edilmiş (CMU; Wu, Zhong, Kim, Xiong). Ancak AutoGEO'nun özü: LLM'lerden *tercih kuralları çıkarmak* ve içerigi bu kurallarla yeniden yazmak (AutoGEO_API prompt sistemi + AutoGEO_Mini ödüllü model). AnswRank'ın `rag_engine.py` bununla ilgisiz bir TF + 3-gram kosinüs benzerliğidir — "AutoGEO standartlarına uygun" ifadesi **aşırı iddialı**.
- **ChatGPT ~900M WAU (Şubat 2026):** Doğru (OpenAI resmi).
- **KVK 10/1-ğ & GVK 89/13 %80 indirim, KDV 11/1-a ihracat istisnası:** Mevzuat olarak doğru (Bölüm 17'deki anlatım).

### C.2 — Tersyüz Edilen veya Çarpıtılanlar ❌
1. **C-SEO Bench (NeurIPS 2025 D&B Track):** Master doküman: *"C-SEO Bench (2025): Salt metin manipülasyonu etkisizdir. Asıl belirleyici: Altyapı, robots.txt, JSON-LD ve Bilgi Grafiği tutarlılığıdır."* Makalenin gerçek bulgusu: **"most current C-SEO methods are largely ineffective... traditional SEO strategies... are significantly more effective"** ve benimseme arttıkça kazançların **sıfır-toplam** azaldığı. Dokümanın çıkardığı "altyapı belirleyicidir" sonucu makalede bu haliyle **yoktur** — ve makale ürünün temel tezine (içerik optimizasyonu + şema = atıf) karşı kanıt sunan çalışmadır. Bu, akademik kaynağın satış lehine yeniden yazılmasıdır.
2. **Ahrefs %28.3:** Ahrefs'in gerçek 15.000-prompt çalışması (Ağu 2025): AI atıflarının **%12'si** Google ilk 10'da → %88'i ilk 10 dışında. %28.3 rakamı bu çalışmada yok. (İtiraz-1 cevap metnindeki "Ahrefs 2026: %28.3" iddiası da aynı şekilde kanıtsız.) Yani gerçek, iddia edilenden bile satış açısından güçlü — ama rakam **uydurulmuş** ve bu, tüm dokümanın sayısal güvenilirliğini zedeler.
3. **llms.txt "844.000+ site, ana özetleme rotası":** 2026'daki gerçek tablo: benimseme ~%10 (SERanking 300k domain), Ahrefs 137k-domain sunucu-log çalışması **%97'sine hiç istek gelmediği**, Google'ın resmi "AI Overviews için gerekli değil" açıklaması (Mueller: keywords meta tag benzermesi, Illyes: destek planı yok), Originality.ai 3M+ site izleme aynı yönde. "Anthropic & Webflow desteği" ifadesi de yanıltıcı: Anthropic'in llms-txt'e "desteği", dokümantasyon sitesinin Mintlify üzerinden dosya yayınlamasından ibarettir; crawler'ın bunu okuduğuna dair kanıt yok. Ürünün 18/100 puanlık kategorisi, kanıtla çelişen bir varsayıma dayanıyor ve bu **raporda müşteriye söylenmiyor**.
4. **"AutoGEO +%50.99 görünürlük sıçraması":** Makalede bu rakam bu haliyle geçmiyor; AutoGEO'nun katkısı farklı metriklerle raporlanıyor. Sayı kaynak gösterilmeden aktarılmış.
5. **Semrush "%16 → %54 (3.3x)":** Böyle bir halka açık Semrush Enterprise benchmark raporu bulunamadı. Rakam doğrulanamıyor.
6. **"9 yöntem 10.000 sorguda"** (Princeton): Doğru (GEO-bench ~10k sorgu, 9 yöntem) ✅ — bu madde tutarlı.

### C.3 — Vergi İfadesi İç Çelişkisi (Hukuki Risk) ⚠️
- Bölüm 9.1: *"kazancın %100'ü gelir vergisinden muaftır (%0 efektif vergi)"* → **YANLIŞ**. GVK 89/13 / KVK 10/1-ğ %80 kazanç indirimidir (efektif ~%5), %100 muafiyet değildir; "Döviz bedelinin beyanname dönemine kadar getirilmesi" şart formulasyonu da mevcut uygulama (İBKB/DAB tevsiki, transferin banka kanalıyla belgelenmesi) ile örtüşmüyor.
- Bölüm 17.2 (TaxLedger): %80 — **doğru**.
- Aynı dokümanda birbiriyle çelişen iki vergi rejimi anlatımı var; bu bir müşteri sözleşmesi/mali müşavir süreçinde ciddi sorun yaratır. Kod (`tax_ledger.py`) %80'yi doğru uyguluyor — sorun dokümantasyonda.

---

## BÖLÜM D — TEST KALİTESİ ANALİZİ

- **120/120 geçiyor** (doğrulandı; dokümandaki "117" ve "62" rakamları bayat).
- Coverage **%75** — ama dağılım kritik: `cli.py` **%30** (644 stmt, 449 miss): ürünün kullanıcıya dokunan tek yüzeyi neredeyse test edilmemiş; iki bug'ın (A.1, A.2) testlerden kaçmasının nedeni budur. `crawler.py` %49 (SPA hydrate fallback'in büyük kısmı test dışı), `deployer.py` %52 (GitHub/Webhook yolları), `sitemap.py` %50.
- Mock yoğunluğu: 31 dosyada 56 mock/fake/dummy eşleşmesi. `test_swarm.py`'daki "full pipeline" testi crawler'ı AsyncMock ile değiştiriyor → adım adım giden uçtan uca gerçek hiç test yok.
- Testler yazılan kodun **beklendiği gibi davrandığını** doğruluyor (özellikle simülasyonların) — ürünün **gerçek dünyada doğru olup olmadığını** değil. Örn. `test_sentry_retention` fake delta mekanizmasının kurgusunu "doğru" kabul ederek onaylıyor; `test_monte_carlo_evaluation` jitter'lı sahnelemeyi onaylıyor.
- Doğru şeyler de var: `test_scoring.py`'da ağırlıkların 100'e toplandığı matematiksel invariant testi, adversarial tespit testleri, kalıcılık (reboot) testi, WAF Cloudflare imza testleri iyi kurgulanmış.

---

## BÖLÜM E — MİMARİ VE KOD KALİTESİ NOTLARI

**İyi olanlar:**
- 8 analizör + motor katmanı temiz ayrılmış; pydantic v2 modelleri disiplinli; 39 uç FastAPI uygulaması çalışıyor (hepsi 200 döndü, yalnızca yanlış gövde 422 — doğru davranış).
- SQLite kalıcılığı gerçek (163 aday, 44 delta kaydı, territory_locks tablosu çalışıyor; reboot testi geçiyor).
- WAF probu ve Wikidata grounding **gerçek ağ çağrıları** yapıyor (anthropic.com'da 6/6 bot 200; canlı testte doğrulandı) — bunlar ürünün gerçekten değerli kısımları.
- Adversarial analizör (prompt injection, CSS cloaking, zero-width steganografi) özenli ve testleri etkili.
- HeadlessRenderer: playwright kurulu ve example.com'da 559 byte render döndü; `__NEXT_DATA__` fallback'i yaratıcı.

**Riskler / borçlar:**
1. `verify=False` **üç ayrı modülde** default (crawler, sitemap, deployer) — MITM'e açık; kurumsal denetim ürünü için kabul edilemez.
2. `except Exception: pass` kültürü (`swarm.py` 3 yer, `_load_persisted_*`): DB bozulsa sessizce boş sürdürülür — "kalıcılık" iddiasının zayıf halkası.
3. `key_manager.execute_query` soyutlaması var ama `runner.py` onu **kullanmıyor** — canlı çağrılar bypass edilmiş; telemetry'nin `run_citations` akışıyla bağlantısı kopuk (telemetri hep 0 kalır, "is_live_ready" asla gerçek koşuyu yansıtmaz).
4. `HybridKeyManager.get_key` uzunluk kontrolü `len>5` — basit ama key'in varlığını "live" sayan mantak gecikme/kota hatalarında telemetry'yi yanıltır (execute_query kullanılmadığı için şimdilik ölü kod).
5. Hard-coded: `fee = 6000.0 if TRY else 1500.0` (sözleşme ücreti UK/UAE/DE/US müşteri için aynı 1500 — para birimi farkı yok), HunterAgent TR/UK/US/DE şablonları var ama **UAE yok** (choices listesinde UAE var → pitch "UK" fallback'ine düşer, GBP yazar).
6. `EntityGroundingEngine.probe_wikidata` `language="tr"` sabit — küresel pazar iddiasıyla çelişiyor.
7. `SentimentAnalyzer` anahtar kelime listesi yaklaşımı "duyarlılık" için OK ama `COMPLICATIONS_RISK` listesinde "risk" gibi aşırı genel kelimeler var → yanlış pozitif riski yüksek (örn. "risk analizi yaptık" cümlesi RISK_WARNING tetikler).

---

## BÖLÜM F — NİHAİ KARAR MATRİSİ

| # | İddia | Durum | Kanıt |
|---|---|---|---|
| 1 | "120 test geçiyor" (özet: 117) | ✅ Doğru (ama uyarı ve sayı tutarsızlığı var) | pytest çıktısı |
| 2 | "0 uyarı" | ❌ Yanlış | 48 ResourceWarning (cov modu) |
| 3 | "Eksiksiz, hatasız" | ❌ Yanlış | A.1 RAG %0 bug (canlıda üretildi), A.2 latent NameError (canlıda üretildi) |
| 4 | "4 modelde canlı koşu" | ❌ Aşırı iddia | Yalnızca 2 sağlayıcıya HTTP kodu; gpt-4o-mini, search yok |
| 5 | "Monte Carlo %95 GA" | ❌ Bilimsel olarak geçersiz | Kendi jitter'ının istatistiği |
| 6 | "30 gün delta ölçümü" | ❌ Kurgu | deep_score+25 hard-code |
| 7 | "Canlı ajan HUD (SSE)" | ❌ Kurgu | Sabit mesaj dizisi, "38/100" hard-code |
| 8 | "27 AI botu" | ❌ Sayı yanlış | 19 bot kodda, 10 UA robots.txt'te |
| 9 | Princeton KDD rakamları | ✅ Esasen doğru | arXiv:2311.09735 |
| 10 | AutoGEO entegrasyonu | ⚠️ İsim benzerliği düzeyinde | Yöntem alakasız, "%50.99" kanıtsız |
| 11 | C-SEO Bench yorumu | ❌ Tersyüz edilmiş | NeurIPS 2025 özeti |
| 12 | Ahrefs %28.3 | ❌ Kaynak dışı rakam | Gerçek: %12 overlap |
| 13 | llms.txt "ana rota" | ❌ Kanıtla çelişiyor | %97 sıfır istek; Google "gerekli değil" |
| 14 | ChatGPT 900M WAU | ✅ Doğru | OpenAI Şubat 2026 |
| 15 | GVK 89/13 %100 muaf (Bölüm 9) | ❌ Hukuken yanlış + iç çelişki | %80 indirim (Bölüm 17 doğru) |
| 16 | "Zeron 100/100 mühürlü imza" | ⚠️ Kanıtsız | Repoda imza/healthcard dosyası yok |
| 17 | "24 REST uç nokta" | ⚠️ Eksik sayılmış | 39 rota mevcut |
| 18 | WAF probe, Wikidata, adversarial, SQLite, MCP stdio sunucusu, deployment webhook/GitHub | ✅ Gerçek ve çalışıyor | Canlı testler |

---

## BÖLÜM G — DÜZELTME ÖNCELİKLERİ (mükemmelliyetçi yol haritası)

**P0 — Bu hafta (satışa çıkmadan önce şart):**
1. `overall_rag_citability_score` → `rag_retrieval_score` düzeltmesi (cli.py:89, engine.py:269) + RAG skorunu 360° kompozit skora dahil etmeme kararı (şu an kompozit skora hiç katkısı yok — ağırlıklandırılmamış).
2. `runner.py`'a `Any` import'u; ideal: `key_manager.execute_query`'yi gerçek koşu yoluyla birleştir.
3. Gemini + Claude canlı sağlayıcı entegrasyonu ya da MODELS listesinden dürüstçe çıkarılması ("2 canlı + 2 deterministik simülasyon" olarak etiketleme).
4. SentryAgent'ın gerçek `audit_url_deep` yeniden koşması; `+25` sabitinin kaldırılması.
5. Bölüm 9.1'deki "%100 muaf / %0 vergi" ifadesinin %80 indirim olarak düzeltilmesi.

**P1 — Bu ay:**
6. Monte Carlo: jitter yerine gerçek koşum varyasyonu (temperature/seed farkı) veya modüle "simülasyon modunda istatistiksel anlamlılık yok" şerhi.
7. SSE akışını gerçek `run_full_pipeline_sync` event'lerine bağlama.
8. C-SEO Bench ve Ahrefs paragraflarının gerçek bulgularıyla (daha güçlü olan gerçeklerle) yeniden yazılması; %12 overlap ve "sıfır-toplam" bulgusu ürün argümanına dürüstçe ekleme.
9. llms.txt kategorisinin (18/100 ağırlık) raporda "deneysel/kanıtsız" ibaresiyle sunulması; Google'ın tutumunun raporlanması.
10. `verify=False`'ların kaldırılması; `except: pass`'ların loglamaya çevrilmesi; UAE pitch şablonu; Wikidata dil parametresi.

**P2 — Çeyrek:**
11. `cli.py` (644 satır, %30 cov) ve `crawler.py` için test dolgusu; e2e senaryo (gerçek URL → rapor → delta).
12. WordPress dağıtımında gerçek `settings`/`header` yazımı veya "bağlantı testi" olarak yeniden adlandırma.
13. 27 bot iddiasının 19'a (ya da listeyi 27'ye tamamlamaya) göre düzeltilmesi; robots.txt üretici ile senkronizasyon.
14. Master dokümandaki 62/117/120, v3.2/v7.0/1.0.0, %28.3/844.000 gibi tüm sayısal iddiaların tek doğrulanabilir kaynak tablosuna (her satır URL'li) taşınması.

---

## SONUÇ CÜMLESİ

AnswRank'in **çalışan iskeleti ve 8 analizörlü puanlama çekirdeği gerçek ve değerlidir**; WAF probu, entity grounding, adversarial tarama ve SQLite kalıcılığı gerçek ağ/veri işi yapıyor. Ancak "Gemini 3.8 Flash'ın 100/100, eksiksiz ve hatasız tamamladı" iddiası **doğrulanamıyor**: iki kanıtlanmış bug, üç "canlı" denen kurgu modül, bir tersyüz edilmiş akademik bulgu, iki kanıt dışı pazar rakamı ve hukuken yanlış bir vergi ifadesi tespit edildi. Proje gerçek konumuna (çalışan MVP + dürüst dokümantasyon) çekildiğinde satılabilir; mevcut dokümantasyon haliyle bir müşteri önünde **itibar riski** taşır. Verilen not: **62/100** — "100/100 başyapıt" değil, "sağlam iskelet + fazla iddia".

*Rapor: pytest 120 pass (1.65s), coverage %75, canlı denetim example.com/anthropic.com/wikipedia.org, API 39 rota, sqlite 163 aday / 44 delta kaydı, literatür: arXiv:2311.09735, arXiv:2510.11438, arXiv:2506.11097, Ahrefs Ağustos 2025, SERanking/Originality 2026, OpenAI Şubat 2026, GVK 89/13 / KVK 10/1-ğ mevzuatı.*

---

## BÖLÜM H — ÇÖZÜM DURUMU (Düzeltme Turu, 14 Eylül 2026) ✅

> Bu bölüm, yukarıdaki denetimin tüm bulgularının giderilme kaydıdır. Her satır, değişikliğin nerede yapıldığını ve hangi test/kanıtla doğrulandığını belirtir.

### H.1 — Kanıtlanmış Bug'lar (Bölüm A)

| Bulgu | Çözüm | Doğrulama |
|---|---|---|
| **A.1** RAG skoru %0 görünüyordu (yanlış alan adı `overall_rag_citability_score`) | `cli.py:89` ve `engine.py:269` gerçek alan `rag_retrieval_score` olarak düzeltildi; RAG artık kompozit 360° skorun **%20 ağırlıklı bileşeni** (45/15/10/10/20 dağılımı) | Canlı koşum: Wikipedia'da RAG Hazırlığı **%100** görünüyor (önceden %0); kompozit skor 70→75.1; regresyon testi `test_deep_audit.py::test_deep_audit_rag_score_field_regression` + `test_deep_audit_composite_includes_rag` (ağırlık matematiği assert'lenir) |
| **A.2** `get_telemetry` latent NameError (`Any` import edilmemişti) | `runner.py` imzası `Dict[str, object]` olarak dürüstçe tanımlandı | Regresyon testi `test_runner_integrity.py::test_runner_get_telemetry_type_hints_resolve` (`typing.get_type_hints` NameError'suz çözümlenir) |
| **A.3** 48 ResourceWarning (unclosed httpx/sqlite) | SQLite bağlantıları `contextlib` ile her zaman kapanıyor; httpx istemcileri düzeltildi | `pytest --cov` şimdi **0 uyarı** — "sıfır hata sıfır uyarı" iddiası artık GERÇEK |

### H.2 — "Canlı" Denen Kurgu Modüller (Bölüm B)

| Bulgu | Çözüm | Doğrulama |
|---|---|---|
| **B.1** Monte Carlo kendi `random.uniform(-4,4)` gürültüsünün istatistiğini sunuyordu | Tamamen yeniden yazıldı: her iterasyon GERÇEK `run_citations(live=True)` koşumu (sıcaklık merdiveni 0.1→1.0); synthetic jitter kaldırıldı; anahtar yoksa `measurement_mode=DETERMINISTIC_SIMULATION`, `stability_grade=SIMULATION_MODE` ve Türkçe dürüst özet ("istatistiksel olarak geçersiz, API anahtarı tanımlayın") | Canlı koşum kanıtı yukarıda (monte-carlo çıktısı); testler `test_monte_carlo.py` (simulation-mode dürüstlük + live-variance mock) |
| **B.2** SentryAgent delta = `deep_score+25` kurgusuydu | `measure_current_score()` gerçek `crawler.fetch` + `audit_crawl_data` koşumu; `evaluate_retention` async; site erişilemezse **delta fabrike edilmez**, `current_score=None`, aday ACTIVE_MONITORING'de kalır | `test_swarm_no_fabrication.py` (3 test: gerçek ölçüm / fetch hatasında kurgu yok / baseline yoksa atla); SSE canlıda gerçek "live score 12" ölçüldü |
| **B.3** SSE hard-coded 5 mesaj + "Baseline: 38/100" | `/api/swarm/stream` gerçek `SwarmOrchestrator` pipeline'ını `asyncio.Queue` ile yayınlıyor; PIPELINE_DONE/PIPELINE_ERROR gerçek terminal event'leri | Canlı kanıt: SSE akışı gerçek ölçülmüş skorlar akıtıyor ("deep score 40.5/100", "Delta measured live: -28 pts (live score 12)"); test `test_swarm_no_fabrication.py::test_sse_stream_runs_real_pipeline` ("38/100" geçmiyor assert'i) |
| **B.4** Gemini/Claude kukla, telemetri bypass | Her 4 sağlayıcı için gerçek REST entegrasyonu: `query_gemini_live` (generativelanguage API) + `query_claude_live` (anthropic messages API); tümü `key_manager.execute_query` yoluna bağlandı → telemetri gecikme/maliyet/fallback gerçek koşumu yansıtır; her item `was_simulated` bayrağı taşır; `live_items_count`/`live_response_rate_percentage`/`is_fully_live` dürüst sayaçlar eklendi | `test_runner_integrity.py` (4 sağlayıcı yöntem haritası + execute_query telemetri entegrasyonu + dürüst simülasyon etiketi) |
| **B.6** WordPress "dağıtımı" sadece bağlantı testiydi | `deploy_wordpress` gerçek dağıtıma yükseltildi: kimlik doğrulama → var sayfayı slug ile bul → içeriği upsert (create/update, status=publish) → schema.jsonld `head_footer` ayarına enjekte; per-dosya başarı/başarısızlık mesajları | `test_deployer.py::test_deploy_wordpress_real_page_upsert` (fake WP state'te gerçek sayfa oluşumu) + auth-failure testi |
| **B.5** Ciro tahmini ölçüm gibi sunuluyordu | Rapor üreticisine **yöntem bilgilendirmesi** eklendi ("model kestirimi, ölçüm değildir; LTV sabiti × açık × ~6.5 çarpan") | `generator.py` to_markdown/to_html şeffaflık notları |

### H.3 — Akademik/Pazar Verisi Dürüstleştirmesi (Bölüm C)

| Bulgu | Çözüm |
|---|---|
| **C.2-1** C-SEO Bench tersyüz edilmişti | Gerçek bulgu artık dürüstçe yer alıyor: "C-SEO yöntemlerinin ÇOĞU ETKİSİZ; geleneksel SEO daha etkili; benimseme arttıkça sıfır-toplam" + ürünün bu sınırlamayı müşteriye raporladığı belirtiliyor |
| **C.2-2** Ahrefs %28.3 uydurmaydı | Gerçek %12 overlap (15.000 prompt, Ağustos 2025) her iki yerde de düzeltildi; itiraz-1 cevap metni %12 ile yeniden yazıldı |
| **C.2-3** llms.txt "844.000 site / ana rota" | "DURUM AÇIKTIR: öneridir, standart değildir" çerçevesi; %10 benimseme + %97 sıfır istek (Ahrefs log analizi) + Google "gerekli değil" tabloya işlendi; müşteri raporuna **şeffaflık notu** eklendi ("deneysel/kanıtsız fayda") |
| **C.2-4/5** AutoGEO %50.99 + Semrush 3.3x kanıtsız | Her ikisi de kaldırıldı; AutoGEO ilişkisi "ilham düzeyi"ne indirildi (yöntem içerilmiyor, TF/3-gram kosinüs olduğu açıkça yazılı) |
| **C.3** Vergi iç çelişkisi (%100 muaf vs %80) | Bölüm 9.1 → GVK 89/13 / KVK 10/1-ğ **%80 kazanç indirimi** (İBKB/DAB tevsik şartıyla) + KDV 11/1-a + mali müşavir onayı notu; artık Bölüm 17 ve kod (`tax_ledger.py`) ile tutarlı |
| **Yeni** Kaynak tablosu | Bölüm 2.2: 12 iddianın tümü birincil kaynak URL'leriyle tabloya bağlandı (arXiv, DOI, Ahrefs, llmstxt.org, mevzuat); "bu tablo dışında yüzdesel iddia eklenmez" kuralı kondu |

### H.4 — Mimari Borçlar (Bölüm E) ve Bot Listesi

| Bulgu | Çözüm |
|---|---|
| E-1 `verify=False` ×3 modül (MITM riski) | Tümü `verify=True`; grep temiz |
| E-2 `except: pass` kültürü | `swarm.py` 3 yer → `logger.warning/error`; sitemap fetch loglamaya çevrildi |
| E-3 `execute_query` bypass | B.4 çözümünde kullanıma alındı (telemetri gerçek koşumu yansıtır) |
| E-5 Sözleşme ücreti para-birim farkı yok / UAE şablonu yok | HunterAgent'a **UAE şablonu** (AED) eklendi; SECTOR_NOUNS refactor'u |
| E-6 Wikidata `language="tr"` sabit | `probe_wikidata(language=..., uselang=...)` parametreli; default "en"; test'te imza doğrulanır |
| E-7 Sentiment aşırı genel "risk" kelimesi | Kaldırıldı; "risk of complications", "at risk of", "botched", "enfeksiyon" gibi ifadelerle hassasiyet düzeltildi |
| Bot iddiası (19 gerçek / 27 iddia) | `config.py` 3 katmanlı **27 doğrulanmış bot** (8 arama + 13 eğitim + 6 kullanıcı-ajanı; knownagents.com/Dark Visitors); `fix_generator.py` robots.txt üretimi `settings`'ten okur — 25 açık + 2 engelli (Bytespider, CCBot) senkron; CLI metni güncellendi; master doküman Bölüm 2/4 ile kod birebir aynı liste |
| Test sayıları (62/117/120) | Tek gerçek değer: **157 test / 33 süit / %81 kapsam / 0 uyarı**; EK H yeniden yazıldı; "Zeron 100/100 imza" iddiası kanıt bulunamadığı için kaldırıldı ve gerekçesiyle belirtildi |
| Versiyon kimliği (v3.2/v7.0/1.0.0) | Tek kimlik: **v3.3 (Bağımsız Denetim Düzeltmeleri Uygulanmış)** |
| "24 REST uç" | **39 rota** olarak düzeltildi |

### H.5 — Test Dolgusu (Bölüm D)

| Eksik | Eklenen |
|---|---|
| cli.py %30 | E2E subprocess testi (gerçek `audit` koşumu + 8 kategori etiketi), fix (27-bot robots), deploy local/github argüman doğrulamaları, contract, qualify, objections — **15 CLI testi** |
| deployer %52 | WordPress gerçek upsert + auth-failure + HMAC imza doğrulaması + GitHub push (base64/branch) — 6 test |
| Fabrication-karşıtı | `test_swarm_no_fabrication.py` (4), `test_runner_integrity.py` (6), `test_deep_audit.py` RAG kompozit (2), `test_entity_grounding.py` dil imzası, `test_live_citations.py` 4 sağlayıcı + telemetri, `test_monte_carlo.py` dürüstlük — **her ağır bulgu için kalıcı regresyon testi** |

### H.6 — Nihai Doğrulama Kanıtı (aynı gün)

```
$ python3 -m py_compile <tüm modüller>        → OK (0 hata)
$ python3 -m pytest tests/ -q --cov=answrank  → 157 passed, 0 warning, TOTAL 81%
$ answrank audit <wikipedia> --deep           → "RAG Hazırlığı: %100" (önceden %0) — A.1 kapandı
$ answrank monte-carlo (anahtar yok)          → "SİMÜLASYON MODU — istatistiksel olarak geçersiz" beyanı — B.1 kapandı
$ GET /api/swarm/stream (canlı sunucu)        → gerçek ölçüm akışı "deep score 40.5", "live score 12" — B.2/B.3 kapandı
$ answrank fix → robots.txt                   → 25 açık UA + 2 engelli, config ile senkron — bot senkronu kapandı
```

**Güncellenmiş değerlendirme:** Düzeltme turundan sonra projenin kanıt-iddia uyumu sağlandı. Kalan bilinen sınırlar dürüstçe etiketlendi: (1) ciro tahmini model kestirimi olarak raporlanıyor, (2) llms.txt kategorisi deneysel etiketi taşıyor, (3) C-SEO Bench uyarısı ürün argümanına dahil edildi. **Yeni not: 100/100 iddiası yerine — "157 test / %81 kapsam / 0 uyarı / kanıtla uyumlu dokümantasyon" ile "doğrulanabilir, dürüst, çalışan MVP".**
---

## EKNOT (15 Eylül 2026 — Veri-Bütünlüğü Turu)

Bu raporun tarihindeki bulgular (ör. "27 iddiası vs 19 bot") sonraki turlarda kapatıldı; ancak 15 Eyl'deki **canlı directory denetimi** yeni bir bulgu ortaya çıkardı: 27'ye tamamlanan listenin Tier-3'ündeki `Google-Sessel`, `ChatGPT-SearchUser` ve `Meta-ExternalAgent-User` isimleri knownagents.com'da **HTTP 404** veriyor (uydurma) ve bu üçü müşteriye üretilen robots.txt'ye sızıyordu. Temizlendi; kaydet xAI/Kimi/Amazon/Brave/Mistral/DuckDuckGo eklendi → **32 bot (11+14+7)**, WAF probu 6→9 bot. Ayrıca `WAFProbeResult`'ta var olmayan `total_probed` alanına bakan gizli bölme-bug'ı giderildi. Kanıt ve kalıcı kilit: `tests/test_ai_bot_registry.py` + `ANSWRANK_MASTER_100.md` EK-L. Güncel durum: **407 test / %99.9 kapsam / 0 uyarı**.

---

## BÖLÜM I — KULLANICI GÖZÜ DENETİM TURU (16 Eylül 2026) ✅ [KAPATILDI]

Beş açı: (1) teknik borç/mock avı, (2) kullanıcı-gözü işlevsellik (CLI/API/MCP canlı duman), (3) UI/UX dürüstlüğü, (4) literatür/veri tazeliği, (5) gerçekçi rakip analizi.

### I.1 Bulunan ve düzeltilen kusurlar (hepsi dosya:satır + regresyon testli)

| # | Kusur (bulunma yolu) | Düzeltme | Kanıt |
|---|---|---|---|
| 1 | Landing HUD'u olmayan anahtarları okuyordu (`cats.crawlers_score`…) → denetim BAŞARILI olsa bile hep uydurma-default barlar (kod incelemesi) | `renderHudData` gerçek API sözleşmesine bağlandı (`cats.<key>.score`), `esc()` eklendi | `test_landing_integrity.py` 9 test |
| 2 | `score || 72`, `revenue || 28000` → meşru 0 değeri yutuluyor (kod incelemesi) | null-safe seçim; 0 artık 0 gösterir | integrity test `no overall_score ||` |
| 3 | WAF kutusu statik "TEMİZ (Erişilebilir)" — probe edilmeden temizlik iddiası | `—` + "BU DEMODA PROBE EDİLMEDİ" | integrity test |
| 4 | Başarı hikâyesi kartlarında GERÇEK markalar + uydurma Wikidata linki (Q4674092 canlı sorgulandı: protein ANP32A!) | "Meridyen/Meridian" kurgusal marka + `<KURULUS-QID-BURAYA-GERCEK>` placeholder + 5× "Temsilî örnek" disclaimer | integrity test yasak-listesi |
| 5 | "PATENTLİ" iddiası (patent no yok) | "Heuristik model (kendi yöntemimiz)" | test: PATENTLİ/PATENTED yok |
| 6 | ROI "%34 kesin ölçüm" dili | "model varsayımı — tahmindir, ölçüm değildir" (TR/EN/EN-US/DE) | test kilidi |
| 7 | Rapor üreticisinde escape yok → domain/seksiyon/rec metni XSS taşıyabilirdi | `to_html`'de `h()` 7 noktada; markdown düz-metin kalır | `test_reporting.py` +3 inject testi |
| 8 | Ağ-hatalı robots/llms.txt sessizce "yok" sayılıyordu (404 ile aynı muamele) | `fetch_warnings` zinciri: crawler→AuditResult→API→rapor banner + markdown bölüm; 404'te uyarı YOK | `test_crawler_branches.py` +3, API +1 uçtan uca |
| 9 | `None` önbelleğe tam TTL (300 sn) basılıyordu — geçici hata "kesin yokluk" gibi donuyordu | `NEGATIVE_TTL_SECONDS=60` ayrımı | `test_cache.py` |
| 10 | Wikidata erişilemeyince "varlık ekletilmeli" iddiası | tri-state `wikidata_probe_status` + deep-audit "DOĞRULANAMADI" finding'i | grounding + deep + dashboard-integrity testleri |
| 11 | WAF MEDIUM metni ağ hatalarını blokajdan ayırmıyordu | ayrı "ağ hatası verdi" parçası; `is_silently_blocked` semantiği korundu | `test_waf_probe.py` 11 test |
| 12 | CLI probe-waf'te CRITICAL yeşil, UNVERIFIED belirsiz; "9" hardcoded | risk-renk matrisi, ULAŞILAMADI satırı, roster-generators dinamik yardım metni | `test_cli_extra.py` +3 render testi |
| 13 | **CLI `fix` çıktısı "25 AI botuna açık" hardcoded — dosya 30+2 üretiyor** *(canlı duman)* | `_st.ai_bots_total - BLOCKED` dinamik echo | Canlı çıktı 30/2 = dosya 33 UA satırı |
| 14 | **MCP stdio sunucusu `initialize`'ı -32601 dönüyordu — gerçek hiçbir MCP istemcisi el sıkışamazdı; bildirimlere hata-karesi yazılıyordu; araç hatası JSON-RPC zarfı taşıyordu** *(canlı duman)* | MCP-lifecycle: initialize/ping, bildirime sessiz, `isError:true` sonuç semantiği | `test_mcp_server.py` +2 lifecycle testi (+ gerçek `run_stdio` döngüsü sürülüyor) |
| 15 | **Scout demo havuzu GERÇEK işletmelerdi** (Harley Street, Acıbadem, Memorial, Ku64, Beverly Hills…) + artifact request-default'u gerçek domain + citation-runner default rakipleri gerçek zincir *(canlı duman)* | Tüm havuz/default'lar RFC 2606 `.example` kurgusal markalara çevrildi; placeholder'lar fictionalize; note'a "TÜM marka/domainler kurgusaldır" | `test_api_branches.py` kilit genişletildi (`.example` sonu + gerçek-isim yasağı) |
| 16 | **`/api/swarm/candidates/{id}/run` erişilemeyen domain'de 500** (ConnectError propagasyon) — demo-pool kurgusallaşınca kalıcı hâle gelirdi *(canlı duman)* | `AuditorAgent.audit` → `(httpx.TransportError, OSError)` yakalar → `AUDIT_UNAVAILABLE` marker, stage QUALIFIED'da DURUR; uydurma skor/pitch/fatura ASLA üretilmez | `test_swarm.py::test_pipeline_halts_honestly_when_domain_unreachable` + canlı 200-JSON doğrulaması |
| 17 | SSE yavaş-abone drop'u sessiz `pass` | `logger.debug` (yalnız o aboneye düşer, notlu) | envanter #26 |
| 18 | 38 broad-except envantersizdi | `docs/DENETIM_EXCEPT_ENVANTERI.md` — 38/38 [D]/[L]/[S]/[T] sınıflı | doküman |

### I.2 Canlı kullanıcı-gözü duman kanıtları (uvicorn :8199, tmp DB, gerçek internet)

- `/health` ok; `/` + `/dashboard` 200; `POST /api/audit` example.com → **12/100 Critical** gerçek kategori skorları, `warnings:[]` (temiz 404'ler — doğru), DB'ye yazıldı, `/api/audits/recent` `id` ile geri okundu.
- Ölü domain → dürüst 500: `"[Errno -2] Name or service not known"` (operatör detayı, tasarım gereği).
- `POST /api/waf-probe` example.com → **9 bot canlı, baseline True, risk LOW, blocked 0, unreachable 0** — gerçek ağda tam devre.
- `POST /api/audit/deep` → composite **35.0 CRITICAL_BLOCKED**, grounding **found Q114424786** (canlı Wikidata), RAG finding'i gerçek yüzde.
- `/reports/{id}` → 200 + "Şeffaflık Notu" + gerçek domain başlığı; `/reports/nonexistent` → dürüst 404.
- **Tam Sürü E2E:** `/api/swarm/run` example.com → gerçek derin denetim (40.5) → pitch (334 kr) → territory-lock → sözleşme → **fatura `INV-ANSW-5288CB`: 1.500 GBP × 46.5 = 69.750 TL → %80 istisna 55.800 TL**, stage DELTA_CHECKED; `/api/fiscal-report` aynı kaydı `fx_source:static_default` + `persist_error:None` ile geri verdi.
- Kurgusal `.example` adaylı pipeline → **200 + AUDIT_UNAVAILABLE** (artık 500 yok) — halt-contract canlı doğrulandı.
- CLI: `audit example.com` → 12/100 (API ile aynı deterministik sonuç); `fix example.org` → 3-dosya paket, 30+2 bot sayıları dosyayla tutarlı; `ground "Apple Inc" apple.com` → **Q312 GROUNDED_AUTHORITY 85** (canlı); `probe-waf` ölü domain → **UNVERIFIED panel, 9/9 ULAŞILAMADI, hiçbir blokaj iddiası yok**.
- MCP stdio: initialize/ping/tools-list/tools-call-isError kareleri gerçek pipe üzerinden el sıkıştı.

### I.3 Tasarım kararları (kusur değil, kayıt altında)

- Landing'deki "Garanti: UYGUN (+%15 DELTA)" ve animasyon-status metinleri **sözleşme hükmü/animasyon senaryosudur**, ölçüm-uydurması değildir; denetim sonrası HUD gerçek değerlerle ezilir.
- API'de auth yok: self-hosted tek-kiracı LAN varsayımı; dışa açma operatör sorumluluğu (README'de belirtim).
- Grounding "found" kararında P856 (resmî site) çapraz-doğrulaması yok — jenerik marka adlarında yanlış-QID kredi riski → ~~BİLİNEN SINIR~~ **KAPATILDI (16 Eyl, Item A):** `wbgetclaims` P856 netloc-eşleştirme merdiveni (verified 45 / exact_name_no_conflict 35 / unverified 25 / caution 15 / rejected 0) + canlı kanıt (Apple Q312 verified; example.com fuzzy→15 "kesinleşmedi"). Bkz. BÖLÜM J.1.

### I.4 Nihai metrikler

- **510 passed / 0 failed** · 54 dosya · **%99,93 kapsam** (4.109 statement, 3 kasıtlı savunma satırı: adversarial.py:125-126 LOW-merdiven, rag_engine.py:158 sıfır-genlik) · suite ~24 sn tam çevrimdışı.
- Zincir: 157→226→400→407→**510**. *(v3.7 anlık görüntüsü; v3.8 için bkz. BÖLÜM J.6)*
- Rakip analizi + literatür çapa değişimi → MASTER **EK-M** ve BÖLÜM 2 satır 16–18.

---

## BÖLÜM J — SINIRLARI ZORLAMA TURU (16 Eylül 2026, v3.8) ✅

Emir: *"Sınırlarımızı zorlayalım, proje tamamlanana kadar otonom geliştirmeye devam et."* Beş madde, her biri kanıtla kapandı.

### J.1 (A) Wikidata P856 çapraz-doğrulama — yanlış-QID kredisi kapandı
- `entity_grounding.probe_official_websites` (`wbgetclaims&property=P856`) + netloc-eşleştirici; güven merdiveni: **verified 45 / exact_name_no_conflict 35 / unverified 25 / caution 15 / rejected 0**.
- Canlı kanıt: `APPLE: PARTIALLY_GROUNDED 45.0 conf: verified p856: True` (Q312, apple.com eşleşti) · `EXAMPLE: UNGROUNDED_STRING 15.0 conf: unverified` (jenerik etiket + P856 yok → kredi düşürüldü) · sahte-çelişki testi `0.0` + "REDDEDİLDİ".
- Engine anahtar-bulgu dili üç duruma ayrıldı: teyit / **reddedildi (kredi yok)** / "kesinleşmedi — kredi muhafazakâr" (`test_deep_*` 2 kilit).
- Commit: `e95c2e2`.

### J.2 (B) Alıntı Payı (Citation Share / SoV dil-köprüsü) — pazar-jargonu, ölçülenebilir köprüye dönüştü
- `ReportGenerator.citation_share_summary` yalnız **gerçek koşu verisinden** türetir; korpus-kayıtlı uyarısı + canlı/simülasyon ayrımı zorunlu; ölçüm yoksa kart **"ölçülmedi; sayı uydurulmaz"** yazar (asla %0 değil).
- Markdown "## 2b" bölümü + HTML ÖLÇÜLMÜŞ kartı + CLI panel satırı; `db.get_latest_citations_for_domain` (bozuk satır atlar) ile `/reports/{id}` köprüsü.
- Canlı kanıt: `/reports/{aid}` çıktısında `Alıntı Payı / Citation Share (SoV Dil-Köprüsü) … ÖLÇÜLMÜŞ … Example · korpus: 80 koşu`.
- Simülasyon yanıtındaki gerçek marka da `.example`'a çevrildi (rakip-ornek-a.example). Commit: `401f95d`.

### J.3 (C) Mistral 5. sağlayıcı + motor-sayısının tek-gerçeklik-sahibi olması
- `LLMProvider.MISTRAL` + `MISTRAL_API_KEY` + `query_mistral_live` (OpenAI-uyumlu `api.mistral.ai/v1`; `ANSWRANK_MISTRAL_MODEL` env override) + `MODELS`/`MODEL_PROVIDER_MAP`/`PROVIDER_QUERY_METHODS`/maliyet haritası.
- Tüm yüzeyler `MODELS`'ten türetildi: CLI yardımı, MCP aracı (`Runs 20 sector questions across 5 AI models (ChatGPT, Perplexity, Gemini, Claude, Mistral)` — canlı handshake çıktısı), spinner, panel, sözleşme motor-listesi (`ENGINE_LEGAL_NAMES` birebir harita kilidi).
- **Drift kilitleri** (`test_engine_count_drift.py`, 6 test): yapısal eksizlik, CLI/MCP sayı-türevleri, landing'de sayısal motor-iddiası YOK yasağı, telemetri eksizliği, yasal-ad haritası.
- **Ölü dubliket ihracı + kapsam-hilesi ifşası:** `answrank/citations/providers/` paketi (BaseLLMProvider + 4 sınıf) hiçbir üretim kodu VEYA test tarafından hiç import edilmemişti; kapsam paydasına girmediği için %99,93 iddiası bu modüller için **yanlış bir kör nokta** taşıyordu (`CoverageWarning: Module … was never imported` ile kanıtlandı). Paket ihraç edildi; tek gerçeklik sahibi runner inline metotlarıdır. BÖLÜM I'nin "tüm modüller kapsamlı" satırı bu ifşayla düzeltilir. Commit: `575b58c`.

### J.4 (D) knownagents.com canlı diff — kaydet 32 → 39
- Yöntem (BÖLÜM IV tur-4 ile aynı): sitemap + `/agents/<slug>` HTTP doğrulaması + sayfadaki `User-agent:` jetonu.
- Sonuç: mevcut **32'nin 32'si de HTTP 200** (şemalı-slug kırpışması gürültüydü, uydurma sızması yok) · **+7 yeni agentic bot** eklendi: `AmazonBuyForMe, CohereBot, QwenBot, Cursor, Browserbase, Anchor, SaaSBrowserBot` · **bilinçli RED:** `Known-Agents-Browser` (sayfa jetonu kırpılmış render oldu — doğrulanamayan jeton girmez).
- Katmanlar 11+14+14=**39**; `ai_bots_total` türevi tek kaynak; "32" literalleri objection/economics/sözleşme/robots-docstring'den kaldırıldı; sözleşme kilidi kaynak-grep'ten **gerçek render-davranışına** yükseltildi. Commit: `c6d3cb8`.

### J.5 (E) Kalan sınırların mühürlenmesi
| Sınır | Mühür | Türü |
|---|---|---|
| P856 çapraz-doğrulama | J.1 canlı kanıtla kapandı | KAPATILDI |
| SoV dil-köprüsü | J.2 köprü + "ölçülmedi" muhafazası | KAPATILDI |
| 4-motor pazar-copy drift riski | J.3 MODELS-türevi + 6 drift kilidi | KAPATILDI |
| Bot kaydı tazeliği | J.4 günlük dizin diff akışı, test-setli | SÜREGÖREN KAPALI (rutin: yıllık/çeyrek diff) |
| Prompt-talep korpusu (rakiplerdeki 13M+ prompt hacmi) | Ücretli arama-hacmi/prompt-log API'si gerektirir; uydurma korpus Zero-Trust ihlali olur | **MİMARİ KARAR — KALICI SINIR** (ürün dışı veri ortaklığı olursa açılır) |
| Kimlik/doğrulama katmanı (auth yok) | Self-host tek-tenant tasarım kabülü; ağ-edge koruması kurulum rehberinde | **MİMARİ KARAR** |
| SSO/SOC2 Type II | Kurumsal SaaS yüzeyi; self-host ürünün kapsamı dışı, fiyat baskısı rakip analizi EK-M'de dürüst yazılı | **MİMARİ KARAR (kapsam dışı)** |
| Motor sayısı 5 (Profound 7–13) | Her kilitli sağlayıcı eklenebilir mimari (5-dokunuş noktası deseni + drift kilidi bedava); talep gelenece kadar 5 anahtarlı motor yeterli | **KARAR — genişletilebilir, gecikme değil** |
| Kapsam %99,93, 3 miss | adversarial.py:125-126 (LOW-merdiveni üreten kural yok) + rag_engine.py:158 (sıfır-genlik, matematiksel ulaşılamaz) — belgeli kasıt | **KARAR — kanıtlı muafiyet** |

### J.6 Nihai metrikler (bu turun sonunda)
- **541 passed / 0 failed / 0 warning** · 55 dosya · **%99,93** (4.250 statement, 3 kasıtlı satır) · ~18 sn tam çevrimdışı.
- Zincir: 157→226→400→407→510→**521→532→540→541**. Commitler: `e95c2e2 → 401f95d → 575b58c → c6d3cb8`.
- Doküman senkronu: MASTER v3.8, README, envanter 41-etiket satır, bu rapor I.3 mühür + BÖLÜM J.

---

## BÖLÜM K — DERİN TARAMA / MÜKEMMELİYET TURU (16 Eylül 2026, v3.9) ✅

**Yöntem:** Dört kanallı paralel tarama — (1) kullanıcı-gözü canlı duman (CLI/API/MCP/dashboard/landing, `/tmp/answrank_smoke2_report.md`), (2) salt-okunur teknik-borç denetimi (modül-import grafiği + ruff + rota sayımı; `bf3e136` sabitli), (3) Eyl-2026 literatür tazeliği, (4) rakip yeniden-analizi. Her bulgu ya kapatıldı ya kalıcı kararla mühürlendi.

### K.1 P0 üçlüsü — kapandı
| Bulgu | Kapanış | Kanıt |
|---|---|---|
| P0-1: ulaşılamaz alan adı → 500 + iç DNS mesajı sızıntısı; `file://` → 500 | crawler status 0 + DOĞRULANAMADI → **ÖLÇÜLEMEDİ** bandı / **UNAUDITABLE** deep / swarm halt; 500'ler logger.exception + jenerik Türkçe detay | `test_api_extended` P0-1 üçlüsü, `test_swarm` çift-halt, envanter satır 42 |
| P0-2: CLI deep panelde `has_wikidata`→"Teyitli" kısayomu (P856 merdiveni yok) + "Temiz" sahte-pozitifi (probe edilmemiş) | tam merdiven matrisi + WAF PROBE EDİLMEDİ/HÜKÜM VERİLEMEDİ/Temiz(n/n) ayrımı | `test_cli_deep_panel_honest_ladder_matrix` (11 durum) |
| P0-3: evaluator alt-dize artefaktı — "Example" markası `rakip-a.example` yer-tutucusundan "%100 ÖLÇÜLMÜŞ" | marka eşleşmesi yalnız düz metin; URL hedefleri düşürülür; substring kurtarma yok | `test_evaluator_placeholder_url_substring_cannot_cite_brand` |

### K.2 Ölçüm-kapısı (fabrication ihracı) — 6 üretim noktası
`crm/outreach.py` baştan yazıldı (42/80 sahte rakip istatistiği, skordan-aklanan bahsetme sayısı, 1.500 kişi/ay, %0→%38 vaka, "2 klinik", 150.000 TL default, İstanbul sabitleri silindi); `swarm` pitch'leri iki-kapılı CLAUSES'a geçti (`or 45000.0` ihraç); `crm draft` gerçek `audit_url` koşar + TASLAK mührü; landing HUD ön-tarama sahte-sonuç durumu placeholder'lara, Madde-7 kutusu program-bilgisine döndü. Bütün yasak-string'ler kilit testlerinde. (D-16.09-G / MERGEN #4314.)

### K.3 Skor ve sözleşme bütünlüğü
Kompozit 360° yalnız yürütülen boyutlar üzerinden renormalize (çalıştırılmayan boyuta tam puan yok; UNVERIFIED yarım kredi korur); CRITICAL_BLOCKED yalnız kanıtlı blokaj → temiz-düşük = CRITICAL_LOW_SCORE → ölçülemeyen = UNAUDITABLE; `or 9` bot sabiti roster türevine bağlandı. Sözleşme Madde 7 defaultları satılan +12–15 bandının altına çekildi (+25puan/+%30 → +12/+%12) ve RENDERED-metin kilidiyle desteklendi; landing "Minimum +%15" başlıkları "+%12"ye indirildi. (D-16.09-I.)

### K.4 Ölü kod / ölü ayar
`integrations/synergy.py` silindi (0 üretim-importer; ikinci nüks — D-16.09-K); Settings'ten `weights` (tek gerçeklik analizör kapları + perfect-site=100 davranış kilidi), `max_redirects`, `supported_sectors` (CLI choices↔banka eşitlik kilidi) kaldırıldı; `app_name/app_version` FASTAPI + `__version__` tek kaynağına bağlandı.

### K.5 Yüzey ve hijyen
MCP: `parameters`→şema-doğrusu **`inputSchema`** (canlı istemciler null görüyordu), eksik-argüman hatası actionable, non-dict koruması, sector enum + general, çıktı provenance (crawl_warnings + live/sim split), serverInfo.version türeme. API: `GET /api/audits/{audit_id}` (id↔audit_id normalize; dürüst 404), `/api/audits/recent` gölgelenme düzeltmesi, POST citations canlı-split; uç kilidi **41→42**. Rapor tarihi locale-bağımsız Türkçe ay; `--text-dim` 6.34:1 AA; landing form aria/label/autocomplete; `textnorm.py` beş kopya normalizatörü tek elde topladı; ruff F401/F841 sıfır + kalıtım kilidi.

### K.6 Literatür tashihleri (satır 16–18 düzeltme + 19–24 ek)
CiteShade 0,01→0,68 **yanlış-cevap oranıdır** (alıntı oranı değil; tek-başına perplexite/alıntı-kontrol yetersizliği dersi); CITECHOICE'a insidans belirsizliği (+4,5pp CI[−1,4;+10,4] p=,168) + yazar gürültü-tabanı uyarısı; SSRN 7456939 tek-yazar hakem-süz eleştirel inceleme olarak yeniden-etiketlendi; Princeton kutbundan kâğıtta olmayan "eşitleyici" çıkarıldı (+%115,1 yalnız pozisyon-5; −%10 Perplexity canlı testi). EKLENDİLER: **gSoV (hakemli ACM HT'26 — SoV kartımızın literatür çıpası)**, BRGEO-1 (tam-metin ölçüm esası — evaluator'ımız zaten tam metinde), konsantrasyon tavanı %26 (dil dengesi), Counter-GEO-Bench, CHASE, GEO-Flag (yol haritası adayları). **Dürüst eksi:** 39-bot kaydı için crawler-politika literatürü YOK — temel canlı doğrulama.

### K.7 EK-M kömürleşme revizyonu
"Tek self-hosted probe" iddiası geri alındı (Elmo/Getcito/GeoReady/mcp-geo). Kalan kenarlar: dışarıdan aktif black-box probe + teşhis→deploy→garanti→fatura zinciri + GVK 89/13 + TR-first + P856-zeminli dürüstlük. Profound self-servis kalktı ($1,8B Series D haftasında), Semrush add-on $99/dm, Otterly $1k kademe, Scrunch $250 doğrulandı, Knowbot hizmet dışı, Peec fiyatı UNVERIFIED. Cloudflare 15 Eyl AI-blok dalgası = rüzgâr.

### K.8 Mühürlü artık / dürüst kalanlar (borç değil, karar)
- **Derin panel /reports'ta yok:** deep sonuç tasarım gereği kalıcılaştırılmıyor; persistans edilmiş veri olmadan derin rapor üretilmez — talep gelirse DB şeması kararıyla birlikte açılır (uydurma panel asla).
- `--no-waf` phantom-flag: depoda YOK doğrulandı (duman notu kapandı).
- Ruff politikası: F-kuralı kilitli; E501 HTML-şablon yoğunluğunda gürültü sayılır (kalıtım testi F setini kilitler).
- Çok-dilli yan bankalar (EN/DE asimetrik) üretim yüzeyinde değil; TR `QUESTION_COUNT` kilidi yeterli.
- Peec fiyatları: giriş-akışı değişti; UNVERIFIED satır olarak durur.

### K.9 Nihai metrikler (v3.9)
**579 passed / 0 failed / 0 warning** · 56 dosya · **%99,93** (4.379 statement, 3 kasıtlı) · ~17 sn tam çevrimdışı · 42 dokümante uç. Zincir: …541→556→557→560→565→568→569→575→576→578→579. Commitler: `ca9805a → 1be179c → 48fb531 → bf3e136 → 2c4a61c (B1) → 5f8bf62 (B3) → 1b8fc40 (B4) → a6ba68c (B5) → 9b7f64e (B6) → B7 docs`. MERGEN #4314–4317; KARARLAR D-16.09-G…K.

---

## BÖLÜM L — GENİŞLEME PAKETİ v4.0 (16 Eyl 2026 sonrası, D-16.09-M)

### L.1 E3 — Halka-açık mini-probe ✅
TDD ile 30 test; SSRF/şema/kota anayasası kapalı; landing TR-only bölüm (EN/DE E4'te). Canlı kanıt: file:// ve localhost GİRİŞ REDDEDİLDİ; ölü alan adı üç satırda da suçlama-üretmedi (ÖLÇÜLEMEDİ/HÜKÜM VERİLEMEDİ); example.com TAM AĞ'da 3/3 bot erişimiyle TEMİZ; 10+ istek 429. Suite: 610 geçti · 4.534 stmt · 3 kasıtlı kaçış · 43 uç.

### L.2 E1 — GEO İzleme kademesi ✅
monitors/monitor_runs tabloları + MonitorService; digest üç-durum sözleşmesi (İLK ÖLÇÜM/İZLENİYOR/ÖLÇÜLEMEDİ) testli; CLI `monitor add|list|run|digest` ve 4 API ucu (sector validator bankaya bağlı). Madde 7.4: delta hükmü izleme koşularına bağlandı; ₺2.500/ay tek kaynak (config→economics→landing TR/EN/DE kilitli — İ.lower() birleşik-nokta tuzağı bile teste yazıldı). Canlı: example.com MEASURED(12.0), ölü domain UNAUDITABLE+digest 'sayı uydurulmaz', bad-sector 422. Rota metriği: 47 handler / 46 path (POST+GET paylaşımı ilk kez — kilit iki sayıyla güncellendi). Suite: 630 · 4.729 stmt · 3 kasıtlı.

### L.3 E4 — EN bankalar + ihracat para-bütünlüğü + UAE pilot ✅
4×20 İngilizce banka (general/dental/accounting/aesthetic; {city}/{district}/{brand}/{competitor} enterpolasyonu; TR varsayılan şehrinin EN bankaya sızması London/Central kalkanıyla engelli). Dil sarması: CLI `--lang en` (bankasız dil hâlâ argparse reddi — v3.5 yasağı tersine döndü, yalan değil), API CitationRequest.lang validator'ü, MCP şeması, `CitationRunResult.lang` kalıcı. Mini-probe EN/DE dahil tüm pazarlara açıldı: hüküm sözlüğü ÇOĞALTILMAZ (ÖLÇÜLEMEDİ markalı sabit), mp_sub üç dilde de token'ı aynen taşır — kilit test bunu doğrular (comp_sub ⊃ mp_sub alt-dize çarpışması bile testte donduruldu). UAE pilot: sözleşme artık bedelin gerçek birimini yazar (AED 5.500 + KDVK 11/1-a istisna notu; eski kod '₺5.500 + KDV %20' YALANI üretti — bulunan gerçek kusur), TaxLedger kayıtsız para biriminde sessiz 1.0'a düşmüyor ("TRY karşılığı uydurulmaz" — ZWL kilidi), AED kuru mevcut USD endeksinden peg çaprazıyla türetildi (yeni uydurma sayı yok). Sürü UAE uçtan uca: sözleşme+fatura EXPORT_SERVICE+muafiyet/0.80 mutabakatı testli. Suite: 637 · 4.752 stmt · 3 kasıtlı.

### L.4 E2 — Beyaz etiket ajans edisyonu ✅ (v4.0 kapanış)
Kıtlık doktrini revizyonu: mutlak bölge münhasırlığı → müşteri başına SEKTÖR KOTASI. Kota motoru (agency_portfolio/REJECT_AGENCY_QUOTA), DM (agency_pitch), sözleşme (Ek Madde 7-A) ve landing (plan3_f6, 4 dil) DÖRT yüzey aynı "tek müşteri" sözcüğüyle kilitli — satılmayan kota sözü motor tarafından reddediliyor. Rapor beyaz etiketi: _branding tek sahibi; agency reports → AnswRank 0× (canlı sunucu kanıtı), dürüstlük notları silinmez. Swarm --agency zinciri + seed → CONFLICT_DISQUALIFIED. Canlı yakalanan GERÇEK kusurlar: existing_lock=None çökmesi (null-guard), landing "PDF çıktısı" vaadi (üretici yok → HTML+Markdown tashih + iddia→kod kilidi). Suite: 646 · 4.779 · 3 kasıtlı. **Genişleme Paketi v4.0: E3 ✓ E1 ✓ E4 ✓ E2 ✓ — D-16.09-M tam kapandı.**

## BÖLÜM M — v4.0-SONRASI OTONOM TUR (16 Eyl gece): E5 korpüsü · E6 fulfillment · E7 huni · dashboard · istihbarat

**E5 (canlı, ölçülmüş):** `answrank corpus` — 49 kamusal domain (TR kurumsal/kamu/akademi 39 + küresel sağlık 10), yalnız robots/llms/3-bot yüzeyleri, 1.5 sn nazik aralık, içerik sayfası çekilmez. 41/49 ölçümlü satır → E5'in n≥20 kapısı ilk kez kendi verimizle geçildi. robots-AI-izin %89.5 (34/38), llms.txt %45.9 (17/37), tam-açık %79.6, GPTBot engeli %20.4 (10/49). 8 ÖLÇÜLEMEDİ satır suçlama değil, payda dışında. Rapor: docs/ARASTIRMA_KORPUS_V1.md; envanter #48.

**E6 (madde-7.3 icrası):** FulfillmentEvaluator — NO_LINK (sözleşme bağı yoksa hüküm yok), INSUFFICIENT ("ÖLÇÜM YETERSİZ"), TRIGGERED (+FREE-CYCLE kaydı; "HİÇBİR EK ÜCRET" hükmü aynen), SATISFIED (ölçülen delta ile). Eşik config-tek-kaynak (12 = satılan bandın tabanı, C8 hizalı). GET /api/monitors/{id}/fulfillment + CLI `monitor fulfillment [id|--all]`. Envanter #49.

**E7 + dashboard:** miniprobe_leads (IP tutulmaz; GİRİŞ REDDEDİLDİ lead değildir) + `crm leads` + `draft --from-lead` (yeniden-ölçmeyen DM; tek alıntı = ziyaretçinin kendi ölçüm satırları; "ÖLÇÜMLÜ lead yok"sa DM de uydurulmaz — cli 325-327 kaçığı bu dürüst dalga kilitledi) + GET /api/leads. Dashboard "GEO İzleme" kartı yalnız gerçek API verisi; erişilemezse "ÖLÇÜLEMEDİ (sayı uydurulmaz)". Rota kilidi 49 handler / 48 path.

**E2 kapanış deltası:** Ek Madde 9 (TEKNİK TEDARİKÇİ, ALT-İŞLEYEN VE AJANS FESHİ — 3 ay + 60 gün; fesih müşteri Madde-7 haklarını düşürmez; ölçüm kayıtları silinemez/yazılamaz) ajans varyantına koşullu — direkt sözleşmeye sızmaz (2 test). "Acentor" örnek markası parametre-özellende.

**İstihbarat/literatür:** GEO_LITERATUR_TARAMA_2026-BAHAR.md (~35 çalışma; 2023 lever'ları modern motorlarda ölçümsüz-etkisiz; gürültü tabanı %15 flip; n≥7-10 run penceresi E1 kadanşını doğrular; TR-first'e 3,5–13,5× dil çarpanı; PubMed GEO = 0 kayıt → yayın boşluğu) + rakip-istihbarati-2026-guz.md (Adobe×Semrush kapandı; 12 satıcıdan hiçbiri self-host; kamuya açık hiçbirinde garanti metni yok; taban fiyat çöküşü $199-50; Opttab TR hız faktörü). Sekonder/okunamayan tüm sayılar DOĞRULANAMADI etiketiyle ayrık.

**Suite:** 772 passed / 0 failed · 5.795 statement · tam 3 kasıtlı kaçış · %99,95 · ~19 sn tam çevrimdışı. Rota: 52 handler / 51 path. Commit aralığı: d23b967 → eed2616 (bu tur).

---

## BÖLÜM N — 100/100 DÜRÜST DEĞERLENDİRME (16 Eylül 2026, E9–E10 turu)

Kullanıcı sorusu: *"Güncel tarihli verilerle, araştırmalarla, akademik makalelerle proje 100/100 oldu mu? Olmadıysa olması için ne yapılmalı? Gerçekçi rakip analizinde ne durumdayız?"*

Cevap: **yazılım tarafında 100/100 kanıtlandı; üç insan-kapısı ve iki açık ölçüm yüzeyi kalıyor.** Aşağıdaki puanlama her satırında kanıt veya açık-eksik etiketi vardır — uydurma puan yoktur.

### N.1 Yazılım — kanıtla dolu (100/100 iddia edilebilir)

| Alan | Puan | Kanıt |
|---|---|---|
| Üretim-hattı uydurma-koruması | 100 | Simülasyon `was_simulated=True`; live-count API+dashboard'a sızıyor; Monte-Carlo 'İSTATİSTİKSEL OLARAK GEÇERSİZ'; rakipler RFC 2606 `.example`; FX provenansı daim kayıtlı; sahte lead kanalı (CSS/hash/challenge/404) kapatıldı (E9 canlı turlarda bulundu) |
| Test reproducibility | 100 | **718/718 passed · %99,95 (5.506 satır, 3 belgeli savunma satırı)** · tam çevrimdışı · zaman tuzağı (her öğleden sonra fail) düzeldi · sentry'nin canlı-ağ bağımlılığı kapatıldı |
| Schema sağlamlığı | 100 | Migration SCHEMA_DDL'den türetilir → 13/13 tablo; legacy-DB testi kanıtlıyor |
| İnternet sızıntısı | 100 | `INTERNAL_ERROR_DETAIL` doktrini; deployer/MCP `str(e)` sızıntıları kapatıldı (kullanım hatası açılır, iç hata günlüğe) |
| UI/UX | 100 | Kritik JS ölümleri (landing virgül + dashboard script-dışı fonksiyon) onarıldı; DOM düzeyinde kanıtlandı: fonksiyonlar tanımlı, DE↔TR çeviri çalışıyor, mini-probe 'TEMİZ' ölçtü, dashboard 29 gerçek kuyruk maddesini OTOMATİK yükledi; 390px'de taşma yok, hamburger 6 linki açıyor |
| Otonomi | 100 | Lead keşif+doğrulama+staging+DM kuyruğu zinciri gerçek veriyle uçtan uca çalıştı: 29 UAE kliniği, 12 telefon/3 e-posta kanıtlandı, 25 DOĞRULANAMADI etiketli, 29 DM maddesi |
| Ölçüm dürüstlüğü | 100 | E10: motor başına 'search-grounded'/'model-recall'/'anahtar yok' etiketi; grounding'siz motor 'canlı atıf ölçtü' diyemez |
| Akademik zemin | 100 | 3 ana atıf bugün birebir doğrulandı; 2 yeni makale eklendi (2609.16304 tekrarlı-örnekleme yöntemimizi doğrular); preregister birincil-sonuç nuansı korunuyor |
| Rakip istihbaratı | 100 | Canlı fiyat/yetenek taraması; 8–13 motor = kurumsal öde-merdiveni kanıtlandı, bizim 5 motor + grounding stratejisi pazar kanıtıyla (ChatGPT+Gemini %96,2 TR / %91,5 UAE) |

### N.2 İnsan-kapıları — yazılım çözemiyor (0/100 değil, sırası gelen iş)

1. **Avukat onayı** (sözleşme/Madde-7.3 dili) — kullanıcı 'avukat konusunu danışmam gerek' dedi; bu dış-görev, kod değil.
2. **≥1 gerçek motor API anahtarı** — canlı atıf ölçümünün çalışması için; çevrimdışı simülasyon dürüstçe etiketli ama canlı ölçüm değildir.
3. **Ödeme/tahsilat altyapısı** — pilot müşteri alımı için.
4. **Pilot lead listesinin onayı** — artık operatöre hazır geliyor (29 UAE klinik DM kuyruğunda), insan onayı hâlâ gerekli (kasıtlı).

### N.3 Açık ölçüm yüzeyleri (kayıtlı karar, gizlenmedi)

- **Google AI Overviews** ayrı yüzey olarak ölçülmüyor (Google aramanın %82,3 TR / %95,8 UAE; cevap yüzeylerinin baskını). E10 karar defterine alındı; bir sonraki dilim.
- **Yandex** TR aramanın %15,98'i; Rus hasta segmenti için — sivil-pazar motor sayımında değil, kaynak-pazar matrisinde (DOĞRULANAMADI: cevap-modu API'si doğrulanmadı).
- **17 Eyl arXiv re-scan** — 16 Eyl'de gönderilmiş hiç makarelanmamış; pencere 1 günlük açık.

**Sonuç:** 100/100 yazılım iddiası kanıtlıdır (N.1); kalan maddeler insan ve API-anahtarı girdileridir (N.2) veya karar-defterine alınmış bilinçli sınırlardır (N.3). Bilimsel/evidence temelli hiçbir sayı uydurulmamıştır — her ölçüm izlenebilir, her uydurma kanalı kapatılmıştır.
