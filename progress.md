# İlerleme — nihai mükemmelliyet taraması (2026-09-18, tamamlandı)

## GÜNCEL DURUM (2026-09-18)
- Tam paket: **936 passed x2 (~25 sn), rc=0**; **6.216 stmt / 4 miss (%99)**.
- Kalan 4 miss: 2'si `asyncio.to_thread` içine gömülü satırlar (coverage tracer
  sınırlaması, manuel doğrulandı), 2'si manuel doğrulanmış hata-yolu guard'ı.
- Ruff F grubu: **0 hata** (F821 ×3 ve F541 ×8 düzeltildi).
- Madde-7.3 skoru artık "görünürlük skoru" değil "AEO/GEO denetim skoru"
  olarak etiketli (TR/EN/DE + dashboard gauge altyazısı + delta docstring).
- UI gerçek tarayıcıda (agent-browser) uçtan uca doğrulandı: landing + dashboard
  + 360° derin denetim akışı (example.com → 30 / CRITICAL_LOW_SCORE, canlı WAF probu).
- Aşağıdaki tur kayıtları tarihçe için aynen korunur.

---

# İlerleme — denetim turu 5/12 (devam: gönderim-anı tazelik)

## Tur 5 devam — gönderim-anı tazelik dilimi
- P1'in gönderim-anı kısmı: onay taze ölçümle alınıp gönderim anında bayatladıysa DM artık çıkmaz. `send_approved` gövdeyi üreten doğrulanmış kaydın yaşını denetler (`_stale_reason`, `FRESH_DAYS`) → `evidence-blocked`, 0 SMTP, 0 log.
- RED: doğrulayıcının geçerli saydığı kaydı satır + `raw_json` timestamp tutarlı 30 gün bayatlatınca 1 SMTP çağrısı (gerçek kusur). İlk denemede yalnızız satırı bayatlatmak kaydı geçersiz kıldı (doğrulayıcı timestamp tutarlılığı) — RED doğru kuruldu.
- GREEN: 22 dispatch testi yeşil; tam paket **864 passed (47.97s, 31.60s), 6149 stmts / 31 misses, rc=0**; ruff F401 temiz. Yeni kapanmayan satırlar defansif/yarış yolları (doğrulayıcı tarih damgasını garanti ettiği için erişilemez dal dahil).
- Tasarım kararı (docs/send-time-audit-design.md): 6-kapı birebir koşturulmuyor; `tekerrür-yok` onay-anı kapısı olarak kaldı (gönderim anında kendi taahhüdümüzü yanlış sayıyor), tekrarın sahibi `_claim_send`. İletişim → `recipient_for`, izlenebilirlik → yapısal.
- Açık: onay-anı run kimliği–gövde birebir bağlama (farklı geçerli koşu gönderimi değiştirir); eski DB göçü ve 7b (kalıcı DRY_RUN satırı); `_gate_fresh` ayrı sorgu; alıcı kanıtı alanları; UI/UX; akademik/rakip kanıt. Dış mesaj gönderilmedi.

## Tur 5 — denetim izi dürüstlüğü ve log idempotence dilimi
- Başlangıç: HEAD 6742047, temiz ağaç. Bağlama hipotezi (onay→kanıt değişikliği→gövde) tanısal akışla test edildi: onay sonrası kanıt değişse de gönderim `already-attempted`, 1 SMTP çağrısı, 1 log satırı — ek üretim kusuru yok; hipotez kapatıldı (speculative test iz bırakmadan geri alındı).
- Bulgu A (RED): `audit_pending` boş dm_text ile denetliyordu → tam-geçerli madde için sahte 'DM metni boş' içerik-red izi. `test_audit_pending_audits_real_draft_text` RED ('DM metni boş') → GREEN: gerçek gövde metniyle denetim.
- Bulgu B (RED, yan etkiyle yakalandı): `auto_approve` ikinci denetim yapıyordu; audit_pending metinli denetime geçince insan-reddi yarış testi ValueError ile kırdı — ikinci audit, kararı değişmiş maddeyi yeniden denetliyordu. `test_auto_approve_audits_each_item_once_with_text` RED (12 satır) → onarım: auto_approve audit_pending sonuçlarını kullanır, ikinci audit yok; yarış koruması koşullu UPDATE rowcount'unda. GREEN: 6 satır.
- Bulgu C (RED): no-op gönderim tekrar çağrısı `sqlite3.IntegrityError` (UNIQUE queue_id,recipient) → `ON CONFLICT DO UPDATE ... WHERE` yalnız HEDEF_YOK/YAPILANDIRILMAMIŞ/DRY_RUN statülerini yeniler; GÖNDERİLDİ/HATA dokunulmaz. `test_noop_results_are_log_idempotent` RED→GREEN.
- Doğrulama: odaklı 57 test 3x yeşil; tam paket **862 passed in 25.98s ve 25.51s, 6126 stmts / 25 misses, rc=0**. Ruff F401 kapı testi yeşil.
- Reviewer `d14836c1` (statik, tamamlanamadan kapandı): yeni engelleyici kusur bulmadı; iki düzeltme — (i) `_claim_send:133-135` yalnız `YAPILANDIRILMAMIŞ` yükseltir, kalıcı `DRY_RUN` satırı sonraki gerçek gönderimi engeller (önceden var, fail-closed, 7b olarak kaydedildi); (ii) `test_gate_audit_log_persists_reasons` probe ekleyip 'DOĞRULANAMADI' denetliyordu, 'DM metni boş' iddia etmiyordu — koordinatör tanımı yanlıştı, belgede böyle iddia yok. Diagnozlar: CLI audit yolu 6 gerçek-metin satırı; dry-run→gerçek gönderim 'GÖNDERİLDİ' 1 SMTP; HEDEF_YOK sonrası alıcı bulununca yeni satır, 1 SMTP (alıcı yükselme, çift gönderim değil).
- Açık: onay–kanıt–gövde/alıcı atomik bağlama (tanısal olarak bugün görülen: onay sonrası kanıt değişikliği gönderimi engellemiyor — P1 olarak kalıyor); recipient provenance; tazelik/ham-alan/sıralama; lead-dışı taslak yolu; eski DB göçü; UI/UX; akademik/rakip kanıt. Dış mesaj gönderilmedi.

## Önceki tur kaydı (tarihsel)
- Tur-2 güvenlik dilimi `a91bbb9` ile commit edildi; başlangıç doğrulaması 23 passed.
- Dispatcher: eksik/bozuk/simüle/yeni-geçersiz görünürlük veya ölçümsüz lead SMTP'ye ulaşmaz. `_body` None döndürür; gönderim rezervasyonu ayrılmadan `evidence-blocked`. Kesik cümle fallback'i kaldırıldı.
- CLI: `crm draft --from-lead --with-visibility` geçersiz son koşuda taslak paneli üretmeden durur. Bayraksız mini-probe taslağı ve lead-dışı yol bu dilimde değiştirilmedi.
- RED: dispatcher 5 senaryo gerçek sahte-SMTP sınırında başarısız; CLI 2 başarısız / 1 geçerli kontrol geçti. Ölçümsüz testin ilk önkoşulu yanlıştı; düzeltilip SMTP assertion'ında yeniden RED görüldü. Bu test hatası üretim kusuru kanıtı sayılmadı.
- İnceleme yaşam-döngüsü kanıtı eklendi: AUTO_APPROVED geçersiz kanıtta `evidence-blocked`; kanıt onarımı sonrası aynı onay tam bir kez gönderilir (2 test, üretim kodu değişikliği olmadan).
- GREEN: 82 odaklı test geçti; ayrıca 3 ardışık tekrar (82/82 her biri). Tam paket önce 856 passed / 1 eski uyarı beklentisi failed; sözleşme beklentisi güncellenince 857 passed in 26.17s; yaşam-döngüsü testleriyle son iki tam koşu **859 passed in 23.62s ve 22.73s, 6124 stmts / 25 misses, rc=0**.
- Pozitif dispatcher fixture'ı öğe bazında canlı test kanıtıyla güncellendi. Bu yalnız geçici test DB'sidir; üretim ölçümü değildir.
- Salt-okunur reviewer `3600ac5d` yeni engelleyici kusur bulmadı; test çalıştırmadı, dosya değiştirmedi. Tasarım/planın STOP sınırı netleştirildi. Doğrudan AUTO_APPROVED geçersiz-kanıt testi ve kanıt onarımı sonrası tek-girişim yaşam döngüsü testleri ek kanıt olarak açık; ortak dal nedeniyle kanıtlanmış kusur sayılmadı.
- Açık: onay–kanıt–gövde/alıcı atomik bağlama; kanıt okunduktan sonra değişiklik yarışı; recipient provenance; no-op log idempotence; eski DB göçü; tazelik/ham-alan/sıralama; UI/UX ve akademik/rakip kanıtları. Dry-run gönderim uygunluğu kanıtı değildir. Dış mesaj gönderilmedi.

## Önceki tur kaydı (tarihsel)


- Tur 3 odak tamamlandı: simülasyon aggregate'lerinin DM'de gerçek organik ölçüm gibi sunulması (inceleme maddesi 4). Commit'ler: e446aea (tasarım sınırı), a5c23ee (ortak doğrulayıcı + tüketici bağlama), 369d869 (içerik kapısı token bağlaması — tarih alt-dizgisiyle nondeterministik uydurma-sayı geçişi kapatıldı; 10x tekrarla doğrulandı).
- Kullanıcı sözleşmeleri: "son koşu geçersizse durdur, eski koşuya sessiz dönüş yok" + yazılı tasarım onayı (`docs/visibility-evidence-design.md`, `docs/visibility-evidence-plan.md`).
- Kanıt zinciri: domain karışması RED→GREEN (`test_visibility_for_does_not_borrow_another_domains_measurement`); 38-sözleşme dosyası RED (37F, stash ile yeniden doğrulandı)→GREEN; içerik kapısı deterministik RED (`test_stamp_digits_cannot_whitelist_invented_numbers` 5x kırmızı)→GREEN (10x 61-test yeşil).
- Taze tam kanıt (HEAD 369d869): **848 passed in 24.10s**, 6119 stmts / 27 misses, rc=0. Ruff F401 kapısı temiz.
- DM dili: `lead_dm` organik/altyapı iddialarını kaldırdı; yanıt-örneği provenance, koşu kimliği, tarih ve modalite yazıyor.
- Tur-2'de tamamlanan: insan-kararı yarışı, alıcı değişimi tek girişim, birleşik tekerrür kapısı (kullanıcı "İkisini birleştir" seçimi), CLI çakışma raporu. Bu dilim (cli.py/dm_dispatch.py/queue.py + testleri) hâlâ commit edilmemiş; tur-3 commit'leri buna dokunmadı.
- Bağımsız salt-okunur inceleme (82774aa1) tamamlandı: okuyucu seviyesindeki kontrolleri doğruladı; P1/P2 açık bulgular `findings.md` "Tur 3 bağımsız inceleme" bölümünde statik kanıtla. İnceleme dosya değiştirmedi; 38 yeşil testi "fixes verified" saymadı.

## Sıradaki tek adım
P1: onay–kanıt–gövde **kimlik** bağlama — gönderim-anı tazelik kapandı (bu tur), geriye run kimliği ile gönderilen gövdenin birebir bağlanması kaldı (snapshot/şema alanı gerekir, eski DB göçü ile birlikte). Sonraki adaylar: eski DB göçü + 7b, alıcı kanıtı kaynak alanları, `_gate_fresh` ortak kayda taşıma, UI/UX, akademik/rakip kanıt.

## Açık kabul ölçütleri
P1 gönderim-anı durdurma, onay/kanıt/gövde bağlama, alıcı kanıtı kaynak alanları, ölçümsüz lead gövdesi, no-op log idempotence, eski CHECK göçü, evidence ham-alan strict doğrulama, tazelik ortak kaydı, sıralama garantisi, audit_pending çift denetim, rapor sayfası okuyucusu, UI/UX+dil, akademik/rakip kanıt tazelemesi, doküman/commit kapanışı.

## Tur 3 kapanış kanıtı
- HEAD e617990; commit zinciri: e446aea → a5c23ee → 369d869 → c9629d4 → afe7c39 → e617990.
- Taze tam suite: **849 passed in 23.39s**, 6120 stmts / 26 misses, rc=0.
- Dry-run dürüstlük etiketi: RED (yeni test 'onay uygulandı' iddiasını yakaladı) → GREEN; --apply testi etkilenmedi.
- Tur-2 güvenlik dilimi (queue.py/dm_dispatch.py + testleri) hâlâ commit edilmemiş; bir sonraki dilim başında commit edilecek.

## Tur 4-7 kapanış kanıtı (güncel)
HEAD `4416d4e`. Commit zinciri (en yeni →):
- `4416d4e` kesin-sonuç landing iddialarını "olası" çerçeveye (UI/UX)
- `9a0dc34` landing Madde-7 garantisini motorun +12 puan eşiğine hizaladı (UI/UX)
- `9cb1562` tur-6 açık sınırları kapattı + akademik/rakip kanıt
- `3cb3e2e` eski-DB göçü + CHECK enforcement test kapsamı (kalıcılık)
- `0dfc405` DM gövdesine tek-ölçüm run-to-run belirsizlik etiketi (akademik)
- `9542f65` koşulsuz "%100 money-back" garantisi 5 dilde kaldırıldı (dürüstlük)
- `37ad7a5` DM kanıtında ham alan zorunluluğu (dürüstlük)
- `d05653c` kanıtsız alıcıyı reddetme (güvenlik)
- `532f6c6` no-fallback kanıt okuyucuları + DRY_RUN tekrar + gelecek-tarih (kalıcılık/güvenlik)
- `99fa222` onay–kanıt kimlik bağlaması (güvenlik)
- `d7b3549` gönderim-anı tazelik blokajı (güvenlik)
- `298f0f5` denetim izi doğruluğu + no-op idempotans (kalıcılık)
- `6742047` geçersiz kanıtta gönderim/taslak durağı (güvenlik)
- `a91bbb9` gönderim sınırı fail-closed (güvenlik)

Taze tam suite: **884 passed ×2** (20.65s / 18.51s), 6187 stmts / 36 misses,
rc=0; ruff F401 temiz. İletilen 5 P0 iddiasının tamamı kanıtlarıyla çürütüldü
(findings.md); "%100 muaf" isimlendirmesi yanlıştı ama aynı sınıfın GERÇEK
kusuru swarm + landing garanti metinlerinde bulundu ve düzeltildi.
Tüm boyutlar kapandı; kalan açık sınırlar findings.md "Kalan SINIRLAR"
başlığında kabul-edilmiş risk olarak listelendi. Dış mesaj gönderilmedi.
