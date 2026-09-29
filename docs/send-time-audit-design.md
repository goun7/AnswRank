# Gönderim-anı denetim sınırı — tasarım ve plan

## Amaç ve mevcut durum
Onay ile gönderim arasında kanıt değişebilir. `DmDispatcher._body` en son
görünürlük kaydından gövdeyi yeniden üretir; `get_dm_visibility` tazelik
denetimi yapmaz (tasarım kararı: doğrulayıcı kayıt tutarlılığına bakar).
Sonuç: insan taze ölçümle onaylamış olsa bile ölçüm bayatladığında veya
iletişim/alıcı durumu değiştiğinde DM gönderilebilir.

Bu dilim **onay–kanıt–gövde kimlik bağlamasını** yapmaz (ayrı açık iş,
aşağıda). Yalnızca gönderilecek metnin o anki kanıtla hâlâ tüm kapılardan
geçtiğini doğrular; geçmezse durdurur.

## En dar onarım sınırı
- Sahip: `DmDispatcher.send_approved`. Gövde üretildikten ve "denendi"
  önkoşulundan sonra, SMTP rezervasyonundan önce gövdeyi üreten **aynı
  doğrulanmış kaydın** yaşı denetlenir (`_stale_reason`, `FRESH_DAYS`).
- Bayatsa sonuç `evidence-blocked` döner; neden olarak tazelik metni taşınır.
  SMTP çağrısı ve rezervasyon gerçekleşmez; `dm_send_log` satırı açılmaz.
- Neden 6-kapı birebir koşturulmuyor: `tekerrür-yok` onay-anı kapısıdır —
  gönderim anında kendi APPROVED taahhüdümüzü "zaten onaylandı" sayıp yanlış
  blokaj yapar; gönderim tekrarının yetkili sahibi `_claim_send`'dir
  (atomik `BEGIN IMMEDIATE` + kuyruk-öğesi denendi kontrolü). İletişim
  kapısının gönderim-anı karşılığı `recipient_for`'da (DOĞRULANAMADI
  e-posta karanlık gönderim yapmaz). İçerik-izlenebilirlik yapısal olarak
  sağlanır: gövde doğrulanmış kaynaktan üretilir.
- "Denendi" önkoşulu yalnız sıralama görevi görür: tekrar çağrı
  `already-attempted` etiketini alır, kanıt hatası değil. Yetkili atomik
  kontrol `_claim_send` içinde kalır.
- Dry-run ve SMTP-yok dalı değiştirilmez: dry-run gönderim uygunluğu kanıtı
  değildir (tur-4 sözleşmesi). Yeni doğrulayıcı veya şema alanı eklenmez.

## Kabul ölçütleri (test-first)
1. Kırmızı: taze geçerli kanıtla onay → ölçüm tutarlı biçimde 30 gün
   bayatlatılır (satır `created_at` ve `raw_json` timestamp birlikte) →
   gönderim hâlâ `sent` oluyordu (SMTP sınırında 1 çağrı).
2. Yeşil: aynı senaryo `evidence-blocked` döner; 0 SMTP çağrısı, 0
   `dm_send_log` satırı; nedeninde tazelik belirtilir. Kanıt onarılınca
   gönderim normal akışta çalışır.
3. Regresyon: taze geçerli kanıtla gönderim `sent` kalır; mevcut
   tek-girişim, insan-kararı ve HATA sözleşmeleri dokunulmaz.

## Açık kalan (bu dilimde çözülmez)
Onay-anı kanıt/run kimliği ile gönderilen gövde birebir bağlanmamıştır.
Aynı geçerlilikte farklı bir koşu onay sonrası gönderimi değiştirebilir
(gövde her gönderimde en son kanıtla yeniden üretilir). Kimlik bağlama için
gönderim-anı snapshot veya şema alanı gerekir — eski DB göçü ile birlikte
ayrı dilim. Kapının kendi tazelik sorgusu (`_gate_fresh`) hâlâ ayrı
sorgudan okur (P2); bu dilim yalnız gönderim yolundaki tazeliği ortak
kayıttan hesapladı. `evidence.py` ham-alan strict doğrulama, sıralama
garantisi, alıcı kanıtı kaynak alanları ayrı açık işlerdir.
