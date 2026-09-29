# EvidenceBundleDraft — Tur 2

## Komutlar ve çıktılar
- `python3 -m pytest tests/ -q --cov=answrank` → **181 passed, 0 warning, TOTAL 83%** (önceki tur: 157/%81)
- `python3 -c "from answrank.api.app import app; ..."` → **44 routes** (39 + 5 job)
- `python3 -m pytest tests/test_cache.py -q` → 12 passed
- `python3 -m pytest tests/test_jobs_api.py -q` → 6 passed
- `python3 -m pytest tests/test_mcp_server.py -q` → 6 passed

## Modül kapsamı hareketi (önce → sonra)
- crawler.py: 49% → 70% (önbellek entegrasyonu + aux-asset testleri)
- cli.py: 30% → 51% (önceki tur 15 CLI testi)
- mcp/server.py: 0% → 57%
- api/app.py: 77% (job uçları eklendi)
- db.py: 79%; engine.py 85%; swarm.py 87%

## Davranış koruma kanıtı
- test_lost_revenue_config_defaults_preserve_behavior: settings LTV/factor/fee varsayılanları eski hard-code değerlerle birebir (35000/25000/15000/20000, 6.5, 6000/1500/1500/5500)
- Full suite 157→181: sıfır regression (eski 157 testin tamamı hâlâ geçiyor)

## Bilinen sınırlar
- run_stdio gerçek pipe kurulumu test dışı (baggage: connect_read_pipe) — dispatch mantığı ayrı test edildi
- job_manager bellek-içi: çoklu süreç dağıtımı kapsam dışı (belgelendi)

---
# EvidenceBundle — Tur 3 (15 Eylül, çökme-kurtarma sonrası devam)

## Nihai komut çıktıları
- `python3 -m pytest tests/ -q --cov=answrank` → **400 passed, 0 uyarı, TOTAL %99.9 (3923 stmt / 3 miss)**, ~16 sn, tam çevrimdışı
- Kararlılık: aynı suite üst üste 3 koşumda aynı sonuç (flaky yok)
- `from answrank.api.app import app` → 44 method-rota doğrulandı
- `answrank serve` → gerçekte açıldı ("Application startup complete"); `--port` default 8000

## Bu turda düzeltilen GERÇEK üretim hataları
1. db.py:342 `timezone` NameError — territory-lock yazımı her seferinde çöküyordu
2. cli.py serve → tanımsız `run_serve_command` (NameError) — uvicorn sarmalayıcısı yazıldı
3. swarm.py:185 `rebuttal.recommended_response` AttributeError — doğru alan `rebuttal_text`
4. engine.py:272 + cli.py:88 olmayan anahtar `is_wikidata_grounded` → `has_wikidata` (Wikidata teyit satırı üretimde hiç görünmüyordu)
5. api/app.py swarm aday uçları singleton-db → istek-bazlı Database() (db-path sarmalayıcılarıyla tutarlılık)
6. sitemap.py `<sitemapindex>` genişletme eksikliği → tek seviye indeks açılımı, TTL cache'li (3 yeni test)

## Test altyapısı
- tests/conftest.py: oturum-bazlı db_path yönlendirme + test-bazı tmp DB + cache flush (gerçek answrank.db kirlenmesi kök-çözümü; kirlenme yedeği: answrank.db.testpollution-backup-20260915)
- Flaky kök nedeni: instance-seviyesi monkeypatch teardown'da bound-method çakıyor → sınıf-seviyesi patch'leri gölgeliyordu (test_api.py düzeltildi; canlı ağ sızıntısı yok oldu)
- Yeni dosyalar: test_db_repository, test_cli_commands, test_api_branches, test_deep_coverage_batch, test_provider_branches, test_final_gaps (+ mevcut 5 dosyaya eklemeler)

## Kapsam hareketi (bu tur)
%90 → %99.9; 100% olan modüller: db, cli, api/app*, jobs, mcp/server*, crawler, engine, sitemap, waf_probe, runner, key_manager, exclusivity, deployer...
(* = kalan 3 savunma satırı: adversarial LOW-merdiveni [üretici yok], rag_engine sıfır-genlik koruması [matematiksel erişilemez], bilinçli bırakıldı, belgelendi)

## Doküman senkron
- README.md İLK KEZ yazıldı (yetenek tablosu, hızlı başlangıç, kalibrasyon env'leri, dürüst sınırlar)
- ANSWRANK_MASTER_100.md: EK-K bölümü + footer v3.4→v3.5 (400/%99.9, sitemapindex, 6 hata düzeltmesi)

## EvidenceBundle — Tur 4: Veri-Bütünlüğü + Eyl-2026 Literatür (15 Eylül 2026)

**Soru:** "Güncel verilerle/araştırmalarla geliştirilecek bir şey kaldı mı?" → Canlı doğrulama kampanyası:

1. **Bot kaydı (knownagents.com, günlük güncellenen dizin):**
   - Sitemap çekildi: 1780 agent slug'ı (`/tmp/agents.txt`).
   - 27'lik kaydin tamamı slug-grep + 3 şüpheli isim HTTP HEAD ile test: `google-sessel`→404, `chatgpt-searchuser`→404, `meta-externalagent-user`→404. TÜM diğer isimler →200/VAR.
   - Eklenen yeni botlar tek tek sayfa-doğrulaması: `xai-searchbot`(AI Search Crawler), `kimi-searchbot`(AI Search Crawler), `amzn-searchbot`(AI Search Crawler), `bravebot`(UA token'lı), `kimi-user`, `mistralai-user`, `amzn-user`, `duckassistbot` (hepsi 200 + documented `User-agent:` token'ı).
   - Sonuç: 32 bot = 11 arama + 14 eğitim + 7 kullanıcı. Kod + tüm satış/hukuki/doküman metinleri senkron; `test_ai_bot_registry.py` (7 test) kalıcı kilit.
2. **Gizli üretim bug'ı:** `WAFProbeResult.total_probed` alanı HİÇ yoktu; `engine.py:237` `.get("total_probed", 6)` ile sessizce 6'ya düşüyordu (6-bot döneminde tesadüfen doğru). Alan eklendi, dolduruldu; WAF eşikleri/metinleri roster-boyutundan dinamik.
3. **Literatür (OpenAlex API, 15 Eyl 2026 çekimi):** 3 yeni çalışma DOI'leri ve tam özetleriyle belgelendi: arXiv:2609.07559 (deterministik-score + 2023-çapaların-modern-motorlarda-transfer-olmadığı BULGUSU → BÖLÜM 2'ye zaman-aşımı nuansı), arXiv:2609.06811 (prompt-korpusu bağımlılığı), Zenodo:10.5281/zenodo.22738860 (%69.5 run-to-run tutarlılık → Monte-Carlo gerekçesi).
   - Not: arXiv API ve DuckDuckGo bu makine tarafında 429/boş dönemli; kanıt OpenAlex + doğrudan site üzerinden alındı (kayıt altında).
4. **Doğrulama:** `pytest tests/ -q --cov=answrank` → **407 passed, 0 warning, TOTAL 3935 stmt / 3 miss (%99.9)**, ~14 sn, çevrimdışı. (3 miss = belgeli kasıtlı savunma satırları.)

**Kapsam hareketi:** 400→407 test (+7 bütünlük testi), kapsam %99.9 korundu. Dokümanlar: master-doc v3.6 (EK-L + §2.2 satır 13-15 + nuans), README, DENETIM_RAPORU EKNOT.
