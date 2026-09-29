# Denetim bulguları — 17 Eylül 2026

## Koordinatörün doğrudan kanıtı
- Devralınan D-001: SMTP'den önce kalıcı rezervasyon; önceki RED raporda `assert 2 == 1`.
- Yeni D-002: alıcı değişirken aynı kuyruk öğesi ikinci SMTP'ye ulaşıyor. `test_changed_recipient_during_send_cannot_send_twice` önce 1 failed (`2 == 1`), kuyruk-öğesi kapsamlı sorgu sonrası geçti. İnsan bu sözleşmeyi soru aracıyla açıkça onayladı.
- Sabit alıcıyla iki bağımsız SQLite bağlantısı/thread, barrier ile eşzamanlı çağrı: 1 sent + 1 already-attempted, SMTP sınırı 1 çağrı. Tanısal deney; kalıcı test henüz yok.
- Disk SQLite ile yapay SMTP sınırı kesintisi, DB yeniden açılışı ve alıcı değişimi: HATA kaydı aynı kaldı, yeni girişim olmadı. `test_hata_reservation_survives_disk_reopen_and_recipient_change` geçti; bu post-change regresyondur, ayrı RED iddiası yok.
- Güncel tam kanıt (tur 3, HEAD a5c23ee): 847 passed / 6117 statements / 27 uncovered, rc=0. Tur-2 kanıtı: 806 passed / 6099 stmts / 28 misses. "Tam 3 satır istisna" iddiası doğrulanmıyor; güncel savunma satırları adversarial.py:125-126, rag_engine.py:158, runner.py:161, cli.py:1010+, dm_dispatch.py:63,130-132,149, queue_gates.py:89,139,164.

## Bağımsız inceleme (danışman, yeniden doğrulama bekleyenler)
Reviewer `75a9a435-910c-44c6-9061-2fc0867f0892`, salt okunur, bellek-içi SQLite + SMTP double, dış ağ yok. Ayrıntılı sonuçlar denetim raporuna işlendi.
1. ÇÖZÜLDÜ (tur 2): insan REJECTED ezilmesi + eski PENDING üstüne yazma + CLI çakışma gizlemesi — koşullu UPDATE, tek damga, çakışma bildirimi.
2. ÇÖZÜLDÜ (tur 2): alıcı değişimi ikinci SMTP hakkı — kuyruk-öğesi tek girişim; disk reopen kanıtıyla.
3. ÇÖZÜLDÜ (tur 2, kullanıcı sözleşmesi "İkisini birleştir"): tekerrür kapısı `dm_send_log` + onay taahhüdü birleşimini okur; eşitlikte gerçek gönderim öncelikli; HATA fail-closed temas sayılır.
4. ÇÖZÜLDÜ (tur 3, commit a5c23ee): simülasyon aggregate'leri DM kanıtı olabiliyordu. Ortak doğrulayıcı `citations/evidence.py`: strict `is_fully_live`, öğe bazında `was_simulated`, domain/run/aggregate tutarlılığı; son koşu geçersizse None — eski koşuya sessiz dönüş yok (kullanıcı onaylı sözleşme). Kapı, runner ve içerik kapısı aynı okuyucuya bağlı; DM metni yanıt-örneği provenance'i taşıyor, organik/altyapı iddiası kaldırıldı. Kanıt: 38-sözleşme testi RED(37F)→GREEN; domain karışması RED→GREEN; tam suite 847 passed/6117 stmts/27 misses.
4b. ÇÖZÜLDÜ (tur 3, commit 369d869): içerik kapısı tarih alt-dizgisiyle uydurma sayıyı rastgele meşrulaştırıyordu (nondeterministik geçiş) ve kendi kanıt damgasını yanlış reddediyordu. Damga/koşu kimliği artık bütünüyle token olarak çıkarılıyor; kalan sayılar yalnız doğrulanmış koşudan. Determinizm: 10x 61-test koşusu yeşil; tam suite 848 passed/6119 stmts/27 misses, rc=0. Bağımsız red-kanıtı: üretim dosyası a5c23ee sürümüne geri alınınca aynı test 3x kırmızıya döndü, sonra restore edildi (git status temiz).

## Tur 3 bağımsız inceleme — açık bulgular (reviewer 82774aa1, statik kanıt)
- ÇÖZÜLDÜ (tur 4, dar kapsam): `crm draft --from-lead --with-visibility` geçersiz/eksik son kanıtta taslak üretmeden döner. Dispatcher `_body` ölçümlü lead veya geçerli son görünürlük yoksa None döner; `send_approved` SMTP rezervasyonu/çağrısı öncesi `evidence-blocked` döner. Dry-run/yapılandırmasız dalı kanıt denetimi yapmaz ve gönderim uygunluğunu kanıtlamaz. Kanıtın okunması ile SMTP arasındaki değişiklik yarışı çözülmüş değildir.
- P1: onay–kanıt–gönderilen metin bağlanmamış: `auto_approve` yalnız id/status bağlıyor; gönderim anında gövde yeniden üretiliyor; kanıt okunduktan sonra değişirse eski gövde gider.
- P2: `evidence.py` Pydantic model_validate eksik/default alanları normalleştiriyor; DM sınırında ham alan/tür zorunluluğu yok.
- P2: "son kayıt" seçimi metinsel created_at'e dayanıyor; offset/bozuk damga sıralamayı bozabilir.
- ÇÖZÜLDÜ (tur 5): `audit_pending` gerçek gövde metniyle denetliyor; 'DM metni boş' sahte izi yok. `auto_approve` ikinci denetim yapmaz (çift iz 12→6 satır); insan-kararı yarışı koşullu UPDATE rowcount'unda korunur.
- Kapsam notu: lead-dışı CLI taslak yolu (`cli.py:367-368`) `get_latest_citations_for_domain` okur; tur 6'da okuyucu ortak doğrulayıcıya bağlandı (bozuk son kayıtta dönüş yok).
5. ÇÖZÜLDÜ (tur 6, d05653c): recipient doğrulaması artık @ kontrolü değil —
   verified_at + başarılı HTTP + contact_source + geçerli adres biçimi şart.
6. ÇÖZÜLDÜ (tur 4): ölçümsüz `_body` kesik cümle fallback'i kaldırıldı; ölçümlü lead yoksa None, SMTP çağrısı yok. Ölçümsüz test RED→GREEN.
7. ÇÖZÜLDÜ (tur 5): no-op sonuçlar (HEDEF_YOK/YAPILANDIRILMAMIŞ) idempotent yazılır — `ON CONFLICT DO UPDATE ... WHERE` yalnız no-op statülerinde yeniler; GÖNDERİLDİ/HATA dokunulmaz. RED: sqlite3.IntegrityError (UNIQUE queue_id,recipient) → GREEN.
7b. ÇÖZÜLDÜ (tur 6, 532f6c6): kalıcı DRY_RUN satırı artık sonraki gerçek gönderimi
   engellemez (SMTP çağrılmamış sayılır).

## Tur 5 devam — gönderim-anı tazelik dilimi (hedef turu 5)
- ÇÖZÜLDÜ (tur 6): onay taze ölçümle alınıp gönderim anında bayatladıysa DM artık gönderilmez. `send_approved`, gövdeyi üreten **aynı doğrulanmış kaydın** yaşını denetler (`_stale_reason` + `FRESH_DAYS`); bayatsa `evidence-blocked`, 0 SMTP çağrısı, 0 log satırı. RED: 30 günlük tutarlı bayatlama ile 1 SMTP çağrısı → GREEN. Aynı zamanda gönderim yolundaki tazelik P2'sini ortak kayda bağladı.
- Tasarım notu: 6-kapı birebir koşturulmaz — `tekerrür-yok` onay-anı kapısıdır, gönderim anında kendi APPROVED taahhüdünü "zaten onaylandı" sayıp yanlış blokaj yapar (deneylerle gözlendi); tekrarın yetkili sahibi `_claim_send`. `already-attempted` etiketi için "denendi" önkoşulu eklendi (sıralama görevi, atomik karar `_claim_send`'de).
- KAPANDI: global kuyruk-çapında gönderim korumasının kalıcı testi zaten var
  (`test_changed_recipient_during_send_cannot_send_twice` — ThreadPoolExecutor
  + Event + bağımsız DB bağlantısı; alıcı değişse de 1 SMTP çağrısı) ve
  `test_hata_reservation_survives_disk_reopen_and_recipient_change`.
  Tur 6'nın tüm açık maddeleri kapandı.

## İletilen P0 iddialarının doğrulanması (tur 5 devam, hepsi ÇÜRÜTÜLDÜ)
Dış bir ajandan beş P0 iletildi; hiçbiri kanıtlanamadı, hiçbirine düzeltme yapılmadı
(yalnızca doğrulanmış kusurlar düzeltilir):
1. "RAG skoru 0 görünen bug (cli.py:89)" — cli.py:89 bir tablo yazdırma satırı; RAG
   kategorisi :79'da `cats.citability_rag.score` ile bağlı. 0 gösterme durumu
   engine.py:60-63'te **bilinçli güvenli mod** ve açık uyarı
   ("Kategoriler 0 puan GÖSTERİYOR ama puanlamadı: ölçüm yapılamadı") — gizli
   kusur değil, dürüst etiket.
2. "runner.py eksik Any importu → canlıda NameError" — runner.py'de "Any"
   geçmiyor (grep sayısı 0); derleme temiz; AST analizinde tanımsız isim yok.
3. "Gemini/Claude için HTTP kodu yok (sadece 2/4 model gerçek)" — 5 sağlayıcının
   da canlı HTTP uygulaması ve dağıtım haritası mevcut (runner.py:128/181/241/
   305/368 ve 405-409; key_manager 19-59).
4. "delta +25 sabit" — delta.py'de "25" geçmiyor; `score_delta = c_score -
   b_score` gerekli --baseline/--current argümanlarından hesaplanır.
5. "%100 muaf yanlış" — dizin kod tabanında yoktu, AMA inceleme sırasında aynı
   sınıfın **gerçek** bir kusuru bulundu: swarm pitch'lerinde koşulsuz
   "%100 money-back" garantisi (9542f65 ile düzeltildi, yukarıda).

## Tur 6 — kimlik bağlama, kanıt okuyucuları, alıcı kanıtı (99fa222, 532f6c6, d05653c)
- ÇÖZÜLDÜ (99fa222): onay–kanıt **kimlik bağlaması**. `approval_queue.evidence_run_id`
  (eski DB'ler `_ensure_columns` ile otomatik göçer); `decide`/`auto_approve`
  karar anındaki son geçerli koşuyu bağlar; `send_approved` gönderilen gövdenin
  aynı koşudan geldiğini zorunlu kılar. Uyuşmazlık veya göç-öncesi onay
  `evidence-blocked` döner; madde `decision_note`'u koruyarak PENDING'e geri açılır
  (karar ezme değil; insan yeniden onaylar). Kanıt: RED (değişen koşu SMTP'ye
  ulaştı; eksik sütun) → GREEN; 37 dispatch+queue testi; tam suite 868 passed.
- ÇÖZÜLDÜ (532f6c6): üç kanıt dürüstlüğü kusuru. (a) rapor okuyucusu artık
  son kaydı **ortak doğrulayıcıdan** geçer; geçersizse None — eski koşuya dönüş
  yok (test_..._skips_malformed_rows → stops_on_malformed_newest_row olarak
  sözleşmeye göre güncellendi). (b) 7b kapandı: kalıcı DRY_RUN satırı SMTP
  çağırmamış sayılır, artık gerçek gönderimi engellemez. (c) tazelik kapısı
  aynı doğrulanmış kaydı okur (ayrı sorgu yok) ve **gelecek tarihli** ölçümü
  anormal kanıt sayar. Kanıt: 3 RED → GREEN; 872 passed ×2.
- ÇÖZÜLDÜ (d05653c): alıcı "doğrulandı" zayıf tanımı (reviewer issue 5).
  `recipient_for` artık sadece `@` değil; `verified_at` + başarılı HTTP (<400)
  + `contact_source` + geçerli adres biçimi (dolu yerel kısım, noktalı host)
  şart; `bilgi@` yer-tutucusu reddedilir. Kanıt: 3 RED → GREEN; 876 passed ×2.
- ÇÖZÜLDÜ (37ad7a5): DM sınırında ham alan zorunluluğu. Pydantic'in
  varsayılanla doldurabildiği alanlar (domain_cited, grounding_status, ...)
  eksikse kanıt artık reddedilir; uydurulmuş bütünlük değil.
- Kanıtlandı (dokunulmadı): `_gate_traceable` docstring'i ile kod uyuşuyor —
  run_id/tarih tam token olarak çıkarılır, kalan sayılar doğrulanmış koşudan
  denetlenir (`test_traceable_content_rejects_invented_numbers`,
  `test_stamp_digits_cannot_whitelist_invented_numbers` her iki yönü kapsar).

## Tur 6 devam — satış vaadi dürüstlüğü (9542f65)
- ÇÖZÜLDÜ: iletilen "%100 muaf yanlış" iddiası isimlendirme yanlıştı ama KUSUR
  GERÇEKTİ: UK/UAE pitch şablonları **koşulsuz** "100% money-back Performance
  Guarantee" veriyordu; Madde 7.3 ise koşulludur (`delta >= 12 puan` →
  `is_guarantee_met`). TR/DE/US de koşulsuz "taahhüt"/"garantierte Steigerung"
  kullanıyordu. 5 dilin tamamı artık performans eşiğini (+12 puan, Madde 7
  şartları) açıkça belirtiyor. Kanıt: RED (UK/UAE metni içeriyo) → GREEN;
  880 passed ×2.

## Akademik ve rakip kanıt tazeliği (tur 6, 18 Eylül 2026)
Birincil akademik kaynak okundu (web_fetch): **arXiv:2607.14035**, "Optimizing
Visibility in Generative Engines: A Critical Survey of GEO (2023-2026)",
Olivier Martinez, 15 Temmuz 2026, 45 çalışma. Anahtar sonuçlar:
- "GEO tek bir sıralama görevi değil; stokastik, kısmen gözlemlenebilir bir
  boru hattı" (search activation → crawl/index → retrieval → rerank → context
  → citation → prominence → absorption → fidelity → user behavior).
- **Kritik**: "hiçbir incelenen teknik organik keşfedilebilirlik veya davranış
  üzerinde kararlı, boylamsal, platformlar-arası nedensel etki göstermiyor";
  temel GEO kazanımları yalnızca "kaynak zaten sabit bir bağlam içindeyse"
  geçerli; "organik keşfedilebilirlik veya kalıcı trafik etkisi kurmaz."
- Ticari denetimlerde "düşük kaynak örtüşmesi, önemli run-to-run değişkenlik
  ve kalıcı doğruluk (fidelity) boşlukları" raporlanıyor.

AnswRank ile hizalama (kanıtlı, kod okunarak):
- Organik trafik / kalıcılık iddiası **yok** (grep: swarm + reporting +
  fix_generator'da "organik"/"long-term"/"kalıcı" eşleşmesi yok).lead_dm'de
  organik/teknik-sağlık iddiası daha önce kaldırılmıştı (tur 3).
- run-to-run değişkenliği **açıkça ölçülüyor ve etiketleniyor**:
  `monte_carlo.py` `measurement_mode` = `LIVE_VARIANCE` |
  `DETERMINISTIC_SIMULATION`, `is_statistically_valid` simülasyonda False,
  `stability_grade` (ROCK_SOLID…CRITICAL_FRAGILITY) ile doğruluk boşluğu
  sayısal olarak gösteriliyor.
- Açık kalıyor: grounding etiketi sağlayıcı beyanına dayanır (anketin
  "fidelity gaps" bulgusuyla aynı sınırlar); tek-ölçüm garantisi anketin
  "tekrarlanan ölçüm + örnekleme + insan doğrulaması" protokolüne göre
  zayıf — bu, MonteCarlo itersayonlarıyla kısmen karşılanır ancak tek bir
  CitationRunResult DM kanıtı olarak kullanıldığında belirsizlik tam
  aktarılmaz. Bu bir **sınır** (kusur değil): DM metni ölçümün örnekleme
  büyüklüğünü ve modunu taşımıyor olabilir — kontrol edilecek.

Rakip kanıt (ikincil, omnibound.ai 7 Mayıs 2026 derlemesi): sektörde 20×5=100
soru-motor ölçümü makul bir numune; ConvertMate 2026 benchmark'ı 12.500
sorgu/8.000 domain, AirOps 45.000 atıf — AnswRank daha küçük numuneyle
çalışıyor, bu "hızlı tarama" konumlandırmasıyla tutarlı ama puanın güven
aralığı rakip araçlardan daha geniştir. Kaynaklar harici ve doğrulanmamış
(ikincil derleme); yalnızca yöntem karşılaştırması için kullanıldı.
## Tur 7 — UI/UX ve satış yüzeyi denetimi (9a0dc34, 4416d4e)
- ÇÖZÜLDÜ (9a0dc34): landing'in Madde-7 garantisi 4 dilde **+%12 ila +%15
  alıntı artışı** aralığı vaat ediyordu; motor (`delta.py:35`) tek bir **+12
  puan** (360° skoru) eşiği uygular — aralık yok, yüzde değil. Ayrıca
  `roi_card_guar` "Minimum +%12 Alıntı Artışı" diyordu. Tüm varyantlar artık
  gerçek eşiği (+12 puan, koşu öncesi/sonrası denetimle kanıt, organik trafik/
  satış taahhüt yok) söylüyor. Kanıt: RED → GREEN; 884 passed.
- ÇÖZÜLDÜ (4416d4e): before/after karşılaştırma bloğu **kesin-sonuç** satıyor
  ("%100 doğrudan hasta yönlendirmesi ve sıfır reklam maliyetli…", 3 yerde:
  HTML gövdesi + i18n JS + dinamik JS). "Temsili örnektir" yasal uyarısı yan
  olsa da %100 ifadesi ölçülmemiş sonucu garanti gibi sunuyordu. Üçü de artık
  "olası… sonuç garantisi değildir" çerçevesinde.
- Kanıtlandı (dokunulmadı, sağlam): `runMiniProbe` tam — 429/4xx/ağ hataları
  Türkçe Mesajlar, 3-karakter istemci kalkanı, `textContent` ile XSS'e kapalı;
  `runAudit` finally ile butonu geri yüklüyor; `renderHudData` "skor 0 meşru
  bir ölçümdür" (null = ölçülemedi) ve WAF için dürüst "BU DEMODA PROBE
  EDİLMEDİ" (Zero-Trust); `esc()` HTML kaçışçısı; iki şablon da HTML olarak
  geçerli (yapısal doğrulama yapıldı). Dashboard tamamen teknik yüzey — satış
  vaadi yok.

## Tur 7 — kapsam özeti (tüm boyutlar)
| Boyut | Durum | Kanıt |
|---|---|---|
| Üretim dürüstlüğü | kapandı | simülasyon kanıtı ayrımı (tur 3), ham alan zorunluluğu (37ad7a5), koşulsuz garanti kaldırıldı (9542f65), landing eşik/kesinlik (9a0dc34, 4416d4e) |
| Gönderim/onay güvenliği | kapandı | kimlik bağlaması (99fa222), tazelik (d7b3549), kanıtsız alıcı reddi (d05653c), tekrar/atomik rezervasyon (a91bbb9), eski-DB göçü + CHECK (3cb3e2e) |
| Kalıcılık | kapandı | no-op idempotans (298f0f5), HATA disk-reopen, DRY_RUN kalıntı (532f6c6) |
| UI/UX | kapandı | yukarıdaki tur-7 maddeleri |
| Akademik/rakip kanıt | kapandı | arXiv:2607.14035 (15 Tem 2026) birincil okuma + omnibound derlemesi; belirsizlik etiketi DM'ye (0dfc405) |
| Dil kalitesi | kapandı | Türkçe kullanıcı yüzeyleri, İngilizce DB anahtarları (sözleşme); locale tuzağı belgelendi |

## Kalan SINIRLAR (kanıtlanmış kusur değil, kabul edilmiş risk)
Bu sınırlar denetim boyunca kanıtlandı ve bilinçli kabul edildi; düzeltme
gerektirmezler ama dürüstçe bildirilmeliler:
- Fiziksel teslim kanıtı yok (SMTP kabul = teslim değil); gerçek SMTP, süreç
  kill/power-loss hiç test edilmedi (çift-fake + disk SQLite sınırları).
- Whole-DB writer provenance'i sahte yazabilir (tek-kiracılı SQLite güven
  sınırı).
- grounding etiketi sağlayıcı beyanıdır; bağımsız doğrulanmaz.
- live ≠ search-sourced ≠ organik: yapay-zeka yanıtı ölçümü organik trafik
  ölçümü değildir (DM'de ve landing'de açıkça etiketli).
- DB anlık-görüntüleri satır-tutarlı; artık risk tüketim zamanları arasındadır
  (onay ↔ gönderim); kimlik bağlaması bu aralığı daraltır.
- Dış mesaj bu oturumda gönderilmedi (sözleşme).
- Önceki HITL yüzdeleri ve 100/100 iddiaları geçerli kabul edilmiyor.

## DERİN MÜKEMMELİYET TARAMASI — Tur 8+ (2026-09-17)

Bu turda kullanıcı gözünden yapılan derin taramada dört kanıtlanmış kusur
bulundu ve test-first düzeltildi. Hepsi commit'lendi.

### 1. Ölçüme kurgusal rakip enjekte edilmesi (AI izi) — düzeltildi
`runner.py:_simulate_response` her simüle yanıta sabit kurgusal ikinci rakip
("Rakip Örnek A" / "competitor-sample-a") enjekte ediyordu; çağıran gerçek
rakip listesi verse bile. Üstelik `run_citations` çağıran vermezse varsayılan
olarak `rakip-a.example` kurgu domainleri üretiyordu. Müşteri raporu, var
olmayan bir rakibi adlandırabiliyordu.

Düzeltme: simülasyon yalnızca çağıranın verdiği rakipleri kullanıyor;
liste yoksa kurgusal rakip enjekte etmiyor. API isteği ve CLI artık
`competitors` parametresi kabul ediyor.

### 2. Doğrulama hatalarının İngilizce sızması (dil kalitesi) — düzeltildi
`/api/miniprobe` gibi herkese-açık endpoint'ler ham Pydantic 422 mesajı
("String should have at least 3 characters") döndürüyordu; oysa landing JS
aynı durum için Türkçe uyarı gösteriyordu. `RequestValidationError`
işleyicisi eklendi; 422 artık "domain: en az 3 karakter olmalı" biçiminde.

### 3. E-E-A-T ölçülmemesi (güncel kanıtla karşılaştırma) — düzeltildi
Trust kategorisi 6 puanını HTTPS + tazelik + legal + SSR'dan veriyordu;
yazar/uzmanlık sinyali hiç ölçülmüyordu. 2026 kanıtına göre AI Overview
atıflarının ~%96'sı güçlü E-E-A-T sinyali olan kaynaklardan geliyor ve
E-E-A-T ikili bir kapı (Wellows, 2.400 atıf / Bowen GEO Index 2026).
Bir site yüksek skor alıp en güçlü atıf kapıcısını kaçırabiliyordu.

Düzeltme: Trust için 1 puan E-E-A-T'ye ayrıldı (author meta, itemprop/rel=
author, uzmanlık kelimeleri; Türkçe I/i case-fold düzeltildi); eksikse
rapor açıkça "atıf kapısı riski" olarak uyarıyor. Kategori ağırlıkları
toplamı hâlâ 100.

### 4. Mini-probe Enter tuşu ve erişilebilirlik (UI/UX) — düzeltildi
Mini-probe input'u bir `<form>` içinde değildi; Enter tuşu sayfayı
yeniden yükleyip probe'ı çalıştırmıyordu. Form + `enterkeyhint="send"`
eklendi. Ayrıca 23 butonun hiçbiri `type` belirtmiyordu (implict submit
riski); hepsi açık tipli yapıldı. Ekran okuyucular için skip-link ve
`#main-content` landmark eklendi (öncesi yoktu).

### Kalan SINIRLAR (kanıtsız 100/100 değil)
- Web arama servisleri bu oturumda geçici olarak kullanılamadı (401/boş);
  akademik kanıt olarak önceden okunmuş arXiv:2607.14035 ve Bowen GEO
  Index 2026 kullanıldı. Daha fazla birincil 2026 makalesi doğrulanmadı.
- E-E-A-T ölçümü sayfa yüzeyindeki sinyallerle sınırlıdır; gerçek
  uzmanlık doğrulaması (lisans, akredite veritabanı) dış kaynak gerektirir,
  ölçülmedi.
- "Ski-ramp" kuralı citability analizöründe zaten front-loading metrik
  olarak ölçülüyor (ilk <p> doğrudan cevap testi); sadece "ilk %30'luk
  pencere" olarak değil, ilk paragraf olarak. Önemli bir ölçüm boşluğu
  KANITLANAMADI.
- AI Mode ile AI Overviews farklı yüzeyler (URL örtüşmesi %13, Ahrefs 2026);
  AnswRank her ikisini tek "görünürlük" skorunda birleştirir — bu sınırlama
  kullanıcıya gösterilmedi.
- Canlı tarayıcı (Playwright) render testi bu oturumda çalıştırılmadı;
  UI/UX doğrulaması statik HTML analizi ve API düzeyinde yapıldı.


### 5. EN/DE örnek panellerinde kanıtsız %100 vaat — düzeltildi
EN ve DE i18n blokları "Outcome: 100% direct patient acquisition at zero
cost-per-click ad spend" derken TR sürük "temsili senaryo — sonuç garantisi
değildir" diyordu. İhracat pazarında kanıtlanmamış %100 vaat veriliyordu.
Her iki panel de "potential ... (illustrative sample — not a guaranteed
outcome)" biçimine çevrildi.

### 6. Dashboard'da simülasyon modunun gizlenmesi — düzeltildi
Citation probu "0/N canlı"yı sarı renkle gösteriyor ama nedenini
belirtmiyordu; kullanıcı API anahtarı olmamasından kaynaklanan simülasyon
modunu ölçüm hatası sanabilirdi. Artık "0/N canlı (simülasyon modu — API
anahtarı yok)" olarak nedeni ile birlikte gösteriliyor.

### 7. Lead inquiry formunun UK varsayılanı — düzeltildi
Herkese-açık `/api/inquiry` modeli city="London"/country="UK" varsayılanı
ile Türk müşteriyi yanlış pazara yazdırabiliyordu. İstanbul/TR olarak
düzeltildi. Swarm pipeline modelleri bilinçli olarak London/UK/GBP
koruyor (EN ihracat senaryosu, ayrı test ile örtülü).

### 8. API HTTP hatalarının İngilizce olması — düzeltildi
Altı kullanıcı yüzeyli HTTPException mesajı İngilizceydi ("Audit report
not found", "Job not found", "Either url or html_content must be
provided", "Candidate not found" ve iki deploy doğrulama metni).
Hepsi Türkçeye çevrildi; Türkçe 422 doğrulama işleyicisi önceki dilimde
eklenmişti.

### 9. Bilgi bozucu GEO iddialarının işaretlenmemesi (güncel kanıtla) — düzeltildi
Counter-GEO-Bench (EMNLP 2026 Main, arXiv:2609.02316, 2 Eyl 2026'da
gönderildi) bilgi bozucu GEO'yu ölçen ilk ölçütü bildiriyor; standart
güvenlik katmanları saldırı başarı oranını göreli olarak yalnızca ≤%5.7
azaltırken C-GEO Guard %47.6 azaltıyor. AnswRank'in negative analizörü
"en iyi", "lider", "tek uzman", "bir numara" gibi desteklenmemiş otorite
iddialarını penalize etmiyordu. Dört desen grubu eklendi; iki veya daha
fazla eşleşme -2 puan düşürüyor ve `has_unsupported_authority_claims`
alanı modele eklendi. Yanlış-pozitif koruması: ölçümlü, nötür dil
cezalandırılmıyor.

### 10. 126 herkese açık fonksiyonda docstring olmaması (teknik borç) — düzeltildi
AST taraması 126 public fonksiyonun docstring'siz olduğunu gösterdi. Hepsi
davranışını özetleyen tek cümle Türkçe docstring aldı; isminden türetilen
şablon değil, her fonksiyonun yaptığı işe göre elden yazıldı. Kalan
docstring'siz public fonksiyon sayısı sıfır (AST kontrolü).

### 11. Adversarial risk skorlamasında ölü LOW dalı — düzeltildi
Risk merdiveninin LOW dalı (adversarial.py:126-127) hiçbir desenle
ulaşılamıyordu: tüm INJECTION_PATTERNS girdileri MEDIUM veya üstü
şiddetteydi. Bu, var olmayan bir puanlama yeteneği sunuyordu. Türkçe
"AI Overview için optimize" GEO stuffing deseni eklendi; gerçek bir
düşük-şiddetli manipülasyon sinyali artık CLEAN yerine LOW kovasına
düşüyor (risk_score=5, is_clean=False).

### 12. Eşzamanlı karar değişiminde gönderimin çökmesi (gönderim güvenliği) — düzeltildi
`_reopen_stale_approval`, UPDATE 0 satır eşittiğinde RuntimeError
fırlatıyordu — bu, başka bir sürecin onayı APPROVED/AUTO_APPROVED'dan
taşıdığı her durumda meydana geliyordu. Gönderme yolu sonuç raporlamak
yerine ortada çöküyor ve kanıt izini kaybediyordu. Artık günlüğe yazıyor
ve çağıranın gözlemlediği durumu raporlamasına izin veriyor. Yarış uçtan
uca test ediliyor.

### 13. Bayat kanıt ile "denendi" etiketinin karıştırılması (gönderim güvenliği) — düzeltildi
`_attempted` ve `_claim_send` birebir aynı "denendi" SQL sorgusunu
çalıştırıyordu (kaynak karşılaştırmasıyla kelimesi kelimesine
kanıtlandı), bu yüzden `_attempted` her zaman önce ateşleniyor ve
`_claim_send`'in dalı ölü kod oluyordu. Daha kötüsü, sıralama bayat
kanıtlı bir maddede "already-attempted" etiketlenmesine yol açıyordu —
gönderilmeyeceği kanıtla denemiş gibi işaretlemek. Fazlalık okuyucu
kaldırıldı; tazelik denetimi artık gönderim claim'inden ÖNCE koşuluyor,
yetkili atomik karar BEGIN IMMEDIATE altında _claim_send'de kalıyor.

### Çürütülen aday kusurlar (kanıtla araştırıldı, kusur yok)
- "Ski-ramp" kuralının citability analizöründe eksik olduğu iddiası:
  çürütüldü — analizör front-loading'i tespit ediyor ve cevap dolgu
  metninden sonraysa doğru şekilde "front-loaded değil" işaretliyor.
- `payment_channels` fonksiyonunun ölü kod olduğu: çürütüldü — FastAPI
  route olarak kullanılıyor.
- Swarm modellerindeki London/UK/GBP varsayılanları: bilinçli EN ihracat
  senaryosu, kusur değil.
- `ArtifactPreviewRequest`'in kurgusal marka varsayılanı: API önizleme
  için RFC 2606 güvenli varsayılan; kullanıcı değerleri geçersiz kılıyor.

### 14. Sözleşmesel skora "görünürlük" etiketi (akademik kanıtla) — düzeltildi
arXiv:2609.07559 (Bajemon & Rochet, 7 Eyl 2026) sorgu-bağımsız deterministik
içerik skorlarının atıf sinyaliyle within-query Spearman'\u0131n\u0131n yaln\u0131zca
0.11 oldu\u011funu ölçtü \u2014 bu sınıf skor "citation predictor" değil
"quality filter"tir. Madde-7.3'\u00fcn ölçtüğü overall_score tam bu sınıf;
landing (TR/EN/DE) onu "360° görünürlük skoru" olarak etiketliyordu.
Üç dilde de "360° AEO/GEO denetim skoru" olarak düzeltildi, dashboard gauge'ine
dürüst altyazı eklendi, DeltaEngine docstring'i düzeltildi. Test-kilitli:
test_guarantee_score_not_labelled_visibility (3 etiket × şablon).

### 15. Ruff F821 tanımsız isimler + 8 F541 (teknik borç) — düzeltildi
3 isim (WAFProbeResult, RAGAnalysisResult, EntityGroundingResult, + Database)
yalnız string annotation olarak kullanılıyordu \u2014 runtime NameError vermez
ama statik analizde tanımsız. Üst-scope import / TYPE_CHECKING guard ile
çözüldü. 8 f-string placeholder içermiyordu (F541) \u2014 otomatik düzeltme.
Ruff F grubu: 12 hata \u2192 0.

### 16. README/progress.md'de eski ölçüler (yapay zeka izi) — düzeltildi
README "772 test / %99,95 kapsam / 5.795 satır, 3 eksik" diyordu;
gerçek: 936 test / 6.216 satır / 4 miss. Eski tur kayıtları tarihçe
korundu, üste gerçekçi durum başlığı eklendi.

### 17. Territory check'te kurgusal domain varsay\u0131l\u0131 (mock kal\u0131nt\u0131s\u0131) — d\u00fczeltildi
`TerritoryCheckRequest.domain` varsay\u0131lan\u0131 "example.com" idi; alan bo\u015f b\u0131rak\u0131l\u0131nca
sessizce kurgusal bir domain i\u00e7in b\u00f6lge kilidi sorgulan\u0131yordu. Aday domain
\u00f6l\u00e7\u00fcm\00fcn girdisidir, sabit olamaz. Art\u0131k eksik/bo\u015f domain 422 ile
T\u00fcrk\u00e7e a\u00e7\u0131klamayla reddediliyor (test-kilitli).

### 18. Kan\u0131ts\u0131z \u00fcst\u00fcnl\u00fck vaadleri (pazarlama d\u00fcr\u00fcstl\u00fc\u011f\u00fc) — d\u00fczeltildi
Landing meta description "markan\u0131z\u0131 1 numaral\u0131 \u00f6nerilen otoriteye
d\u00f6n\u00fc\u015ft\u00fcr\u00fcn" diyordu. SSRN 7366498 AI cevaplar\u0131nda ilk-3 markan\u0131n
en fazla ~%26 SoV tuttu\u011funu \u00f6l\e7t\u00fc \u2014 "1 numara" teslim edilebilir bir vaat
de\u011fil. \u00dcl\u00e7\u00fclebilir \u00e7er\u00e7eveyle de\u011fi\u015ftirildi ("al\u0131nt\u0131lanan kaynaklar
aras\u0131nda yer almak"); showcase "en yetkin" iddialar\u0131 "referans g\u00f6sterilen"
yap\u0131ld\u0131. Kullan\u0131c\u0131-sorgusu al\u0131nt\u0131lar\u0131 me\u015fru, kilit d\u0131\u015f\u0131 tutuldu.

### 19. tests/'de 97 kullan\u0131lmayan import + 9 birebir ayn\u0131 test (teknik bor\u00e7) — d\u00fczeltildi
Ruff F kap\u0131s\u0131 yaln\u0131zca `answrank/` i\u00e7in \u00e7al\u0131\u015f\u0131yordu; `tests/` 97 F401 ve
9 F811 (birebir ayn\u0131 tan\u0131ml\u0131 \u00e7ift test) i\u00e7eriyordu. pytest yaln\u0131zca ikinci
tan\u0131m\u0131 toplad\u0131\u011f\u0131 i\u00e7in ilk kopyalar \u00f6l\u00fc a\u011f\u0131rl\u0131kt\u0131. Heps'i kald\u0131r\u0131ld\u0131;
test say\u0131s\u0131 ve kapsamda d\u00fc\u015f\u00fc\u015f yok (941 passed, analyzers 100%). Kalan
blind-except'ler (BLE001) bilin\u00e7li fail-closed'dur \u2014 hepsi log'lan\u0131r, hi\u00e7biri
sessizce yutulmaz.

### 20. Zeron ile denetim: OpenAPI 404 belgeleri eksik (dış araç bulgusu) — d\u00fczeltildi
Zeron'un status-audit sondas\u0131 (arXiv:2609.12770 kural seti, 30 kural) canl\u0131
OpenAPI spec'ini tarad\u0131: **87 P2 bulgu**. \u00d6nemli olan\u0131 R-WILDCARD-PATH-404'idi:
9 parametreli path runtime'da HTTPException(404) f\u0131rlat\u0131yordu ama spec'te
beyan etmiyordu, yani istemci bulunamayan-kaynak s\u00f6zle\u015fmesini \u00f6ng\u00f6remiyordu
(/api/audits/{id}, /api/jobs/{id} x2, /api/swarm/candidates/{id}/run,
/api/queue/{id}/decision, 3x /api/monitors/{id}, /reports/{audit_id}).
Dokuzuna da `responses={404: ...}` eklendi; app.openapi()'y\u0131 do\u011frudan okuyan
parametreli testle kilitlendi. **Zeron bulgular\u0131 87 → 78**; kalan 78'in
tamam\u0131 tek-kirac\u0131l\u0131 self-host tasar\u0131m i\u00e7in bilinen yanl\u0131\u015f-pozitifler
(R-MUTATING-401/R-429-ON-LIMITED: kimlik-do\u011frulama ve rate-limit katman\u0131
d\u0131\u015f a\u011f ge\u00e7idine aittir; HTML sayfa route'lar\u0131nda FastAPI yan\u0131tlar\u0131
kendisi \u00fcret\u00fcr).

**Zeron s\u0131n\u0131r\u0131 (d\u00fcr\00fcstl\fck notu):** Zeron'un kod sondalar\u0131 (scan, quality,
dead-modules, cognitive, i18n-audit) yaln\u0131zca .ts/.tsx/.jsx/.vue ayr\u0131\u015ft\u0131r\u0131r
(`SCRIPT_EXTENSIONS`, zeron/src/cli/commands.ts:788) — Python projesinde
0 fonksiyon/0 buton d\u00f6nd\u00fcr\fcr ve "100/100" skorunu bo\u015f taray\u0131c\u0131 \u00fczerinden
\u00fcretir. Bu, ge\u00e7mi\u015fteki "Zeron 100/100 imza" iddias\u0131n\u0131n neden ge\u00e7ersiz
oldu\u011funu a\u00e7\u0131klar. Zeron'un bu projede \u00fcretken tek ger\u00e7ek sinyal
status-audit oldu (dilden ba\u011f\u0131ms\u0131z: OpenAPI JSON'unu tar\u0131yor).

### Güncellenmiş SINIRLAR (kanıtsız 100/100 değil)
- Test kapsamı %99 (6213 ifade / 4 kaçıran). Kalan 4 satır:
  `parse_live_response` ve `get_latest_citations_for_domain`'in
  hata-yolu guard'larıdır; her ikisi de doğrudan çağrılıp sonuç
  doğrulandı, fakat coverage tracer'ı `asyncio.to_thread`
  içine yerleştirilmiş satırları sayamıyor (ölçüm sınırı,
  ölçülemeyen özellik değil).
- Web arama servisleri bu oturumda büyük ölçüde kullanılamadı (401/boş);
  kanıt olarak önceden okunmuş arXiv:2607.14035 ve Bowen GEO Index 2026
  kullanıldı. Eylül 2026'dan daha yeni birincil makale doğrulanamadı.
- E-E-A-T ölçümü sayfa yüzeyindeki sinyallerle sınırlı; gerçek lisans/
  akreditasyon doğrulaması dış kaynak gerektirir, ölçülmedi.
- AI Mode ile AI Overviews farklı yüzeyler (URL örtüşmesi %13, Ahrefs
  2026); AnswRank ikisini tek görünürlük skorunda birleştirir — bu
  sınırlama kullanıcıya gösterilmedi.
- Canlı tarayıcı (Playwright) render testi çalıştırılmadı; UI/UX
  doğrulaması statik HTML analizi + API düzeyinde yapıldı.
- Bu turlarda bulunan ve düzeltilen kusurlar test ile kanıtlandı; ancak
  "kullanıcı gözünden 100/100" ifadesi kanıtlanamaz — her düzeltme yeni
  bir inceleme döngüsü gerektirir ve kalan sınırlar yukarıda listelidir.
