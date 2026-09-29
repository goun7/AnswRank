# TaskIntentDraft — AnswRank 9 Saatlik Otonom Geliştirme

**Tarih:** 14 Eylül 2026, gece oturumu · **Yetki:** Kullanıcı tam yetki verdi ("9 saat burada yokum tam yetki veriyorum, 9 saat boyunca geliştirmeye devam et")

## İstenen Sonuç
Denetim sonrası temiz temelden (157 test / %81 kapsam / 0 uyarı) başlayarak AnswRank'ı satışa hazır bir sonraki seviyeye taşımak. 9 saat boyunca kesintisiz otonom geliştirme; her turda tüm testler + derleme + doküman senkronizasyonu yeşil.

## Kapsam (Goal nesnesiyle birebir)
1. Test kapsamını %95+ hedefine taşıyacak test dolgusu (öncelik: crawler.py %49, sitemap.py %50, api/app.py, mcp/server.py %0, rag_engine)
2. Denetlenmemiş modüllerin derin denetimi: mcp/server.py, rag_engine.py, waf/, sitemap.py, sentiment.py, generator.py (kısmen bakıldı)
3. Yeni özellikler:
   - robots/llms.txt fetch'inde bellek-içi önbellek (rate-limit dostu, TTL'li)
   - Uzun koşumlar için REST progress API'si (job-id job submit + poll)
   - LTV/skor parametrelerinin ayarlanabilir olması (hard-coded 6.5 çarpan, fee 6000/1500)
4. Gerçekçi test sitesi üzerinden tam e2e duman testi (ör. httpbin veya local test sunucusu ile)
5. README + master doküman senkronizasyonu

## Non-Goals
- llms.txt puanlama ağırlığını değiştirmek (mevzuat/pazar dürüstlüğü kararları sabit)
- Akademik iddiaları geri şişirmek
- Yeni veritabanı şeması (mevcut SQLite kalıcı veriyi bozma — answrank.db'de 163 aday var)
- API'ye breaking change (mevcut 39 rota korunur, sadece eklenir)

## Risk İpuçları
- Canlı internet gerekli modüllerde testler mock'lanmalı (CI-uyumlu)
- Uzun koşumlu (monte-carlo, swarm) kodlarda zaman aşımı riski
- pyproject'a yeni dependency EKLEME (httpx/pydantic/fastapi mevcut set sabit)

## Baseline Refs (okunacak)
- answrank/audit/crawler.py, sitemap.py, rag_engine.py, waf.py
- answrank/api/app.py (39 rota — progress API nereye eklenir)
- answrank/mcp/server.py (%0 kapsam)
- answrank/config.py (parametre ayarlanabilirliği nereden)
- pyproject.toml (dependency seti)

## Stop Koşulları
- done: 9 saatlik bütçe bitince VE tüm turlar yeşilken
- blocked: ağ altyapısı çökerse / test dışı bir regression tekrar çözülemezse (3 tur)
- needs-verification: belirsiz davranışta kullanıcı onayı gereken karar
- scope-exceeded: kullanıcı izni olmayan alana girilirse (ör. yeni DB şeması)

## Başlangıç Todo Haritası
1. [IN PROGRESS] Baseline oku: crawler/sitemap/rag/waf/mcp/config/app
2. Önbellek katmanı (crawler+sitemap, TTL'li) + testler
3. Progress/job API (arka planda audit/monte-carlo koşumu) + testler
4. Yapılandırılabilir LTV/fee parametreleri + testler
5. Test dolgusu (hedef %95)
6. E2E duman testi (local http server ile)
7. Doküman senkronizasyonu + final rapor
