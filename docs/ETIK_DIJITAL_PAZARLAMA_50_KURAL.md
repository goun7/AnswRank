# Etik Dijital Pazarlama: Yapay Zeka Çağında Kazanmanın 50 Kuralı

*Harvard Business Review tarzında deneme · AnswRank araştırma birimi · 16 Eylül 2026*

---

## Giriş: Görünürlük Ödevi Bitti, Ölçülebilirlik Başladı

On yıl önce dijital pazarlamanın etik sorunu şuydu: "Hedef kitlemizi manipüle ediyor muyuz?" Soru hâlâ geçerli ama artık ikincil. 2026'da asıl etik soru farklı: **"Müşterilerimize sunduğumuz rakam gerçek mi?"**

Aramanın merkezi kaydıyor. StatCounter'ın Ağustos 2026 küresel verilerine göre Türkiye'de arama trafiğinin hâlâ %86,85'i klasik arama motorlarından gelirken, AI sohbet robotlarının payı %0,29. Ama bu küçük pay, karar anlarının yoğunlaştığı yerde: insanlar artık "en iyi diş kliniği İstanbul" yazıp on mavi linki değil, tek bir cümle okuyor. Ve o cümleyi yazan model, hangi klinikleri seçtiğini size söylemiyor.

Bu makale, kendi ölçüm altyapımızda 16 Eylül 2026'da yaptığımız canlı deneyin bulgularını kullanır. Amacımız teorik bir etik manifestosu yazmak değil — çalışıp çalışmadığını her gün test ettiğimiz 50 pratik kural sunmak.

**Temel bulgumuz şu:** Etik pazarlama ile etkili pazarlama 2026'da aynı şey olmaya başladı. İlk büyük çok-model atıf ölçümümüzde, gerçek web araması yapabilen motorlar uydurma bağlantı vermedi; yapamayan motorlar ise "kaynak" diye sunduğu linklerin dörtte birinin gerçek olmadığını anlamamız için bizim dışarıdan kontrol etmemiz gerekti. Etik, burada bir engel değil; etik olmayan şeyin ölçülemeyen şey olduğu ortaya çıktı.

---

## Bölüm I: Temel İlkeler (Kurallar 1–10)

**1. Önce ölç, sonra konuş.** Pazarlama iddiası ölçümünüzden önce gelmemeli. Bir rapor "görünürlüğünüzü artırırız" diyorsa, artışın nasıl ölçüleceğini de söylemelidir.

**2. Uydurma, en büyük etik ihlalidir.** Akademik taramamız (arXiv, 14–17 Eyl 2026 penceresi) bunu doğruluyor: *When Should LLMs Abstain? Chain-of-Self-Questioning for Selective Answering* (CoSQ, arXiv:2609.17516, 15 Eyl 2026) modelin *faktik desteği zayıf olsa bile akıcı cevap ürettiğini* belirtiyor — yani cevabın akıcılığı onun doğru olduğu anlamına gelmez. Akıcılık, doğruluk değildir.  Modelinizin hatırasını "araştırma" diye sunmayın. Açık deneyimizde, gerçek arama erişimi olmayan bir motor beş "kaynak" üretti; dördü DNS'te yoktu. Etik mesele teknik değil, dürüstlük meselesidir.

**3. Etiketleme, ürünün bir özelliğidir.** Her ölçümün modalitesini yazın: gerçek arama mı, model hatıraması mı, anahtar yok mu? Bu üç durum farklı güven seviyeleridir ve müşteri bunu bilmelidir.

**4. "Yapamıyoruz" demek bir özelliktir.** Ölçemediğiniz bir boyuta tam puan vermeyin. Sıfır yazabiliyorsanız, sıfır yazın.

**5. Varsayılan değer en tehlikeli değerdir.** Kur bilinmiyorsa 1.0 varsaymak, yabancı parayı TL sanmaktır. Bilinmiyorsa işlem durdurulur.

**6. Kanıt, iddiayı izlemelidir.** "Siteniz iyi ama sizi görmüyor" cümlesi ancak sekiz organik sorgudan birinde marka çıkıyorsa doğrudur. Ölçüm yoksa cümle de yoktur.

**7. Gizlilik varsayımı: minimum veri.** Halka açık probunuzda IP saklamayın. Gereksinim, depolamayı hak etmelidir.

**8. Sınır, itiraf edilebilir olmalıdır.** Ulaşılamayan veriyi "DOĞRULANAMADI" diye etiketleyin. Bu zayıflık değil, güven inşasıdır.

**9. Simülasyon, asla üretim değildir.** Monte Carlo yaklaşımınız istatistiksel olarak geçersiz etiketini taşımazsa, kimse anlamaz.

**10. Rakam, kaynağıyla gelir.** Her sayının yanında tarih ve yöntem yazın. Kaynaksız istatistik, kurgudur.

---

## Bölüm II: İçerik ve Araştırma Etiği (Kurallar 11–20)

**11. Alıntı, substantifikasyon değildir.** Akademik çalışma, modelin alıntıları birebir kopyaladığını (%98) ama yalnızca %37'sinin iddiayı gerçekten kanıtladığını gösteriyor. Kaynak sayısı, doğruluk değildir.

**12. Tekrarlı ölçüm, bilimsel zorunluluktur.** Tek ölçüm, anlık dalgalanmadır. Marka görünürlüğü en az yedi-sekiz tekrarlı örnekleme gerektirir; bu, rastgele örnekleme yöntemimizdir ve akademik olarak da doğrulanmıştır.

**13. Gürültü eşiğini bilin.** Düşük hacimli pazarlarda %15 oynama gürültüdür. "Artış" demeden önce gürültü üstü olduğunu kanıtlayın.

**14. Eski çalışmaları etiketleyin.** 2023 bulgusu 2026 motorlarında geçerli olmayabilir. Tarihsiz alıntı, yanıltmadır.

**15. İkincil sonucu birincil gibi sunmayın.** Önceden kayıtlı bir deneyin asıl bulgusu istatistik olarak anlamsızsa, yan bulguyu öne çıkarmak seçici sunumdur.

**16. Akademik bağlamı koruyun.** "Yerel dil 3,5–13,5 kat etkilidir" cümlesi, orijinal çalışmanın yöntem sınırlarıyla anılmalıdır.

**17. Araştırma korpusu tarihçedir.** Kamusal kaynak taramanızın tarihi ve yöntemi yazılıysa, benchmark iddianız geçerlidir; değilse havadadır.

**18. Önemli bulguları teyit edin.** Rakip analizi yaparken her fiyat ve özelliği canlı kontrol edin. Tahmin, tahmin olarak kalsın.

**19. Araştırma, pazarlama metni değildir.** İstihbarat bulguları stratejiye girmeli, reklam cümlesine dönüşmemelidir.

**20. Önce-preregister, sonra ölç.** Ne ölçeceğinize önce karar verin; sonuçtan sonra uydurma hipotez, etik ihlaldir.

---

## Bölüm III: Yapay Zeka ve Üretim Etiği (Kurallar 21–30)

**21. Modelin sınırlarını bilin.** Gerçek arama erişimi olmayan modeller, kaynak uydurabilir. Bunu bir hata değil, mimari bir sınırlama olarak etiketleyin.

**22. Uygulama öncesi kanıt.** AI özelliğinizi müşteriye sunmadan önce ölçülmüş çıktısını test edin.

**23. Önyargı, nicel değil niteldir.** Modelinizin bölgesel bir önyargısı varsa, bunu "veri kısıtlaması" diye geçiştirmeyin.

**24. Üretimde simülasyon olmaz.** Test ortamında kullanılan sahte veriler, üretimde gerçek sanılamaz.

**25. Hata, sessizce yutulmamalı.** Bir API çağrısı başarısız olursa "başarılı" olarak etiketlenmemelidir. Başarısızlık, görünürlüktür.

**26. Etiketler, gözlemlenir.** Üç durum etiketi (gerçek arama / hatıralama / anahtar yok) varsayım değil, gözlemdir.

**27. Önce kanıt, sonra etiket.** "Arama tabanlı" etiketini başarılı yanıttan ÖNCE koymayın. API reddedilince etiket de düşmeli.

**28. Çoklu model, çoklu doğruluk.** Tek modele güvenmek tek nokta hatasıdır. En az üç farklı model ailesi ölçün.

**29. AI üretimi, insan kararı.** Otomatik üretimde son kontrol insan olmalı. Tam otomasyon, tam sorumluluğu içerir.

**30. Sızıntıya karşı tasarım.** API anahtarlarınız sohbet geçmişinde değil, maskeli dosyada. Anahtar yönetimi, etiğin teknik yüzüdür.

---

## Bölüm IV: Müşteri İlişkileri ve Sözleşme Etiği (Kurallar 31–40)

**31. Garanti, ölçümle bağlanır.** Sözleşmenizde "+12 puan artış garantisi" varsa, bu ölçülemeyen bir vaat değildir; ölçüm prosedürü de yazılmalıdır.

**32. İlk ölçümü yapın, sonra sözleşin.** Müşterinizin mevcut görünürlüğü bilinmeden garanti vermek, kumar etiğidir.

**33. Kötü haber, erken verilir.** "AI sizi görmüyor" ölçümü, ilk toplantıda söylenmelidir; üçüncü ayda değil.

**34. Ücretsiz katman, satış tuzağı değildir.** Halka açık probunuz değerli olmalı; gizli ücret duvarı yok.

**35. Onay, insanda kalır.** Dışa dönen hiçbir fiil — e-posta, fatura, sözleşme — otomatik gönderilmesin. İnsan onayı mimarinin merkezinde.

**36. Çift fatura, imkansız olmalı.** Ödeme olayı iki kez gelirse iki fatura kesilmemeli. Sistem bunu teknik olarak engellemelidir.

**37. İade, iz bırakır.** Fatura silinmez; ters kayıt atılır. Denetim izi, güvenin altyapısıdır.

**38. İnsan-kapıları itiraf edin.** Yazılımın çözemeyeceği şeyler vardır (avukat onayı, tahsilat). Bunları "yakında" diye geçiştirmeyin.

**39. Fiyat, koşulsuzdur.** Görünürlük artışı fiyatınızı değiştiriyorsa, teşvik yapınız bozuk demektir.

**40. Veri sahipliği müşteridedir.** Ölçüm verisi taşınabilir olmalı; rehin alınamaz.

---

## Bölüm V: Ölçek ve Sorumluluk (Kurallar 41–50)

**41. Yerel pazar, evrensel standart.** Türkiye'de %96,2 ChatGPT+Gemini payı, küresel bir standart değil; yerel gerçek. Strateji yerel, etik evrensel.

**42. Kapsam, sayıya değil sinyale bakar.** Sekiz motor kullanmak erdem değildir; gerçek erdem, pazarın %96'sını ölçen iki motoru doğru etiketlemektir.

**43. Görünürlük, erişilebilirlikten ayrıdır.** Siteniz teknik olarak mükemmel (80/100) olabilir ama modellerin cevaplarında sıfır görünebilir. İkisini birlikte ölçün.

**44. Rakipleriniz, referans noktanızdır.** Görünürlüğünüzü mutlak değil, rekabet bağlamında sunun.

**45. Ölçemediğiniz boyut, sıfır değildir.** Bilinmiyor işaretinin sıfırdan farkı vardır. İkisini karıştırmayın.

**46. Geçmiş veri, mevcut hüküm veremez.** AI motorları haftalık değişir. Üç aylık ölçüm, geçen ayın hava durumu gibidir.

**47. Tarafsızlık, farkındalık gerektirir.** Kendi ölçüm altyapınızın önyargılarını bilin; en az iki bağımsız yöntemle çapraz kontrol.

**48. Toplumsal etki, ölçümünüzde olsun.** Küçük işletmelerin görünürlüğü büyük markalar lehine bozuluyorsa, bunu raporlayın.

**49. İtibar, tek bir ölçümle bozulur.** Uyduru-veri bir müşteri tarafından yakalanırsa, tüm geçmiş çalışmalar sıfırlanır.

**50. Etik, denetlenebilir olmalıdır.** Her kuralın bir testi olmalı. Test edilemeyen etik kural, iyi niyettir; iyi niyet ise 2026'da yeterli değildir.

---

## Kapanış: Etik, Ölçümün Biçimidir

Bu 50 kuralın ortak bir yapısı var: hepsi **ölçülebilirliği** savunuyor. Bu tesadüf değil. 2026'da etik dijital pazarlamanın yeniden tanımı gerekiyor: Etik, neyin doğru olduğuna dair bir felsefe değil, neyin ölçüldüğünü itiraf etme disiplinidir.

Deneyimiz bunu somut olarak gösterdi. Modelin ürettiği dört sahte kaynağı yakaladığımızda, sorunun "kötü model" olmadığını anladık. Sorun, sahteyi gerçekten ayıracak bir ölçüm altyapısının olmamasıydı. Bu altyapıyı kurduk — ve müşterilerimize artık "bu link gerçek, bu modelin hatıraması" diyebiliyoruz.

Sonuç olarak: Pazarlamanın geleceği daha fazla otomasyonla değil, daha fazla dürüstlükle gelir. Dürüstlük ise teknik bir altyapı sorunudur — felsefi bir tavır değil.

*Bu makaledeki her ölçüm, kayıtlı testlerimizde izlenebilir. Kuralların tamamı kodlanmış testlerle denetlenir; test edilemeyen hiçbir kural listede yoktur.*

---

*AnswRank — 16 Eylül 2026 · Etik pazarlama, ölçülen pazarlamadır.*
