# DM görünürlük kanıtı — onaylanan tasarım

## Amaç ve kullanıcı kararı
Son koşu simüle, bozuk veya tutarsızsa durdur. Eski geçerli koşuya sessiz dönüş yok. Dış mesaj gönderilmez. Kullanıcı bu seçeneği `visibility-evidence-policy` sorusunda onayladı.

## En dar onarım sınırı
- Database, istenen domain'in en son citations satırını deterministik olarak seçen ortak DM kanıt okuyucusudur.
- Gate ve CitationRunner ayrı aggregate sorguları yerine aynı okuyucuya bağlanır. Mevcut yöntem adları tüketici uyumluluğu için korunur.
- JSON, domain/koşu kimliği, canlılık, öğe sayısı, öğe bazında simülasyon bayrakları ve aggregate değerleri tutarlı olmalıdır. Eksik/eski kayıt silinmez; DM kanıtı sayılmaz.
- Tüm yanıtların canlı olması arama kaynaklandırması değildir. Modalite bilgisi kaybolmaz; model hatırlaması organik arama/atıf olarak adlandırılmaz. DM soru bankası yanıtlarından söz eder; kanıtsız 'altyapınız iyi' iddiası kaldırılır.
- Görünürlük kanıtı yoksa otomatik onay kapanır. `crm draft --from-lead --with-visibility` eksik/geçersiz son kanıtta taslak üretmeden durur; bayraksız manuel mini-probe taslağı görünürlük iddiası olmadan kalır.
- Yapılandırılmış SMTP ile gerçek gönderim yolunda, APPROVED veya AUTO_APPROVED olsa bile ölçümlü mini-probe veya geçerli son görünürlük kanıtı yoksa rezervasyon/SMTP öncesi `evidence-blocked` döner. Dry-run/yapılandırmasız yanıt gönderim uygunluğu denetimi değildir. Bu dilim manuel gönderimin tüm güvenlik kusurlarını kapatmaz.
- Rapor sayfasının ayrı get_latest_citations_for_domain yolu bu dilimde değiştirilmez; açık bulgu olarak korunur.

## Seçenekler ve gerekçe
1. Ortak son-koşu okuyucusu (seçildi): iki DM yolu aynı kanıtı kullanır, eski satıra gizli dönüş yok.
2. Eski geçerli koşuya açık dönüş: koşu seçimi ve tazelik bağlamı için daha geniş sözleşme gerekir; seçilmedi.
3. Yalnız gate kontrolü: CLI domain hatasını açık bırakır; yeterli değil.

## Test-first adımlar
1. Gerçek geçici disk SQLite üzerinde domain karışması, yeni geçersiz koşu, sahte canlılık/eksik öğe, aggregate tutarsızlığı için RED.
2. Ortak okuyucu + iki tüketici bağlantısı; aynı testlerde GREEN.
3. DM dili ve dispatch/CLI tüketici testi; SMTP ve ağ kullanılmaz.
4. Odaklı ve tam regresyon; bağımsız salt-okunur inceleme; kanıt/sınırların kaydı.

## Risk ve açık sınırlar
SQLite satırı sağlayıcının doğru kaynaklandırma beyanını ispatlamaz; provider grounding doğrulaması ayrı incelemedir. Koşu seçiminin farklı çağrılar arasındaki eşzamanlı değişimi ve immutable onay/gövde snapshot'ı bu dilimde çözülmüş sayılmaz. DB şeması ve var olan satırlar değiştirilmez.
