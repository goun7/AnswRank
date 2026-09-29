# AnswRank bağımsız denetim planı

## Amaç ve sınırlar
Üretim dürüstlüğü, gönderim/onay güvenliği, kalıcılık, UI/UX, akademik/rakip kanıtı ve dil kalitesini doğrula. Doğrulanmış kusurları test-first düzelt; kanıtsız puan veya HITL yüzdesi verme. Dış mesaj gönderme. E8, tek-kiracı ve kapalı kaynak sınırlarını koru. Gerçek ölçüm yerine test verisi gösterme; çevrimdışı test doubles yalnız test sınırında kullanılır.

## Başlangıç anlık kaydı
- TaskStartSnapshot: `/home/gokun/projects/02_sahis/85-AnswRank`, branch `master`, HEAD `7e4c60f`.
- Devralınan değişiklikler: `answrank/dm_dispatch.py`, `tests/test_dm_dispatch.py`; izlenmeyen `docs/DENETIM_2026_09_17.md`. Korunacak; bu turda yazılmış gibi sunulmayacak.
- Okunan başlangıç kaynakları: README.md, denetim raporu, dispatcher/testleri, CLI audit/send blokları, DB gönderim şeması ve bağlantı sahibi.
- TDD Route: strict, kullanıcının açık test-first isteği. Devralınmış onarımın RED kanıtı raporda mevcut; bu turun çalıştırdığı kanıt ayrı kaydedilecek.
- Mimari inceleme: gönderim rezervasyonu `DmDispatcher` sorumluluğu, kalıcılık SQLite; existing DB korunmalı. Puan/kapsam metriği ürün güvenliğine eşit değil.

## Dilimler
1. [x] Güncel kaynak/çalışma ağacı/test başlangıcını doğrula.
2. [x] Gönderim: eşzamanlı çağrı, kesinti, alıcı değişikliği, onay geçişleri. Bağımsız read-only inceleme + gerçek SQLite/izole SMTP sınırı tanısal deneyler.
3. [x] Doğrulanmış kusurlar için en dar sahipte başarısız test → düzeltme → regresyon. Eski DB göçü ve kayıt korunumu ayrıca doğrulanacak.
4. [x] Ölçüm: domain-sorgu ilişkisi, kaynak/grounding, tazelik, izlenebilir sayıların gerçek ölçüm kaydına bağlanması.
5. [x] UI/UX ve dil: tarayıcıyla erişilebilir akışlar, boş/hata durumları, yanıltıcı kopya. Dış mesaj ve ödeme işlemi yok.
6. [x] Güncel akademik/rakip kanıtı: arama + asıl URL okuma, tarih ve belirsizlik kaydı. Kaynak iddiası doğrulanamazsa açıkça belirt.
7. [x] Tam regresyon, gerçek kapsam sayacı, doküman eşlemesi, bağımsız inceleme bulguları, teslim raporu ve kontrol noktası commit'i.

## Geçerli dilim
Tamamlandı (Tur 8+ sonrası mükemmelliyet taraması): onaylı gönderim ve `--from-lead --with-visibility` taslak sınırında geçersiz kanıtı durdurma. TDD Route: strict; 5 dispatcher + 2 CLI RED ardından düzeltme. Kanonik kanıt sahibi Database.get_dm_visibility korunur; dispatcher yerel gövde sorumluluğunda Optional dönüş, CLI yalnız wiring/return değişikliği. Yeni şema/owner yok; canlı veri değişikliği yok. Bağımsız inceleme danışman niteliğinde; tamamlanma onayı değildir.

## Doğrulama
- `python3 -m pytest -q -p no:cacheprovider tests/test_dm_dispatch.py tests/test_queue_gates.py`
- `python3 -m pytest -q -p no:cacheprovider --cov=answrank --cov-report=term-missing`
- Eşzamanlı/kesinti deneyleri geçici SQLite DB kullanmalı ve SMTP metodu ağsız gözlemleyiciyle değiştirilmelidir.
- Gönderim düzeltmesi için alıcı ve onay TOCTOU sınırı ayrıca gözden geçirilmeli; tam teslim için exactly-once iddiası yapılmamalı.

## Next Step
Tüm dilimler tamamlandı. 930 test x2 geçti, üretim paketi %99 kapsam,
4 satır asyncio.to_thread tracer sınırlaması (manuel doğrulandı). Üretim
onayı verilmedi — kalan SINIRLAR findings.md'de listelendi.
