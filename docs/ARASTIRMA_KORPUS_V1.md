# AnswRank Kamusal Erişilebilirlik Korpüsü

**Gözlem sayısı:** n=49 · **Tamamen ölçülemeyen satır:** 8

## Yöntem
Örneklem çerçevesi: tüm etiketler; kamuya açık web sitelerinin yalnız robots.txt/llms.txt/bot-yüzeyi yoklaması (içerik sayfası çekilmez).

Araç: `answrank corpus` (mini-probe arşivi). Her satır canlı HTTP tanığıdır;
hiçbir alan tahminle doldurulmamıştır. Paydasız oran üretilmez.

## Bulgular

| Gösterge | Sonuç |
|---|---|
| robots.txt'te AI aramasına izin | %89.5 (34/38 ölçümlü satır) |
| llms.txt bulunurluğu | %45.9 (17/37 ölçümlü satır) |
| 3 örnek botun tamamına açık | %79.6 (39/49 ölçümlü satır) |
| GPTBot engelleme payı | %20.4 engelli (10/49) |
| PerplexityBot engelleme payı | %18.4 engelli (9/49) |
| ClaudeBot engelleme payı | %18.4 engelli (9/49) |

## Hüküm dağılımı

- TEMİZ: 24
- BOT ERİŞİMİ ENGELLİ: 10
- ÖLÇÜLEMEDİ: 8
- KISMÎ ÖLÇÜM: 7

Kaynak etiketleri: cerceve-a-tr, cerceve-b-global
