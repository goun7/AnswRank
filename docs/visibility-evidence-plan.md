# DM kanıt okuyucusu uygulama planı

**Amaç:** Onaylanan visibility-evidence-design.md sınırını test-first tamamlamak.
**Mimari:** Database.get_dm_visibility(domain) -> Optional[dict] ortak okuma; gate ve runner delegasyonu. Saf kayıt doğrulaması citations/evidence.py içinde, DB dosyasına yeni karmaşık sorumluluk eklenmez.
**Teknoloji:** Python, SQLite, pytest. Dış ağ/SMTP yok; mevcut kayıtlar korunur.

## 1. Ortak kanıt doğrulaması
- [ ] tests/test_visibility_evidence.py: gerçek geçici DB, iki tüketici parametrizasyonu. Geçerli 2 öğeli canlı koşu; başka domain; simüle son koşu; bozuk JSON; string false; eksik öğe; aggregate uyuşmazlığı. Her geçersiz giriş için `assert visibility(domain) is None`.
- [ ] `python3 -m pytest tests/test_visibility_evidence.py -q -p no:cacheprovider` RED.
- [ ] `answrank/citations/evidence.py`: `visibility_from_row(row, domain) -> Optional[dict]`; JSON model doğrulaması, strict canlılık bayrakları ve count/rate/id/domain tutarlılığı. Modalite ve run_id/timestamp taşınır.
- [ ] `answrank/db.py`: `get_dm_visibility(domain)` en son satırı `ORDER BY created_at DESC, rowid DESC LIMIT 1` ile seçer; eski kayıt aramaz.
- [ ] runner.visibility_for ve gate.db_visibility ortak okuyucuya delegasyon. Gate None için eksik/simülasyon/tutarsız kanıt nedenini açıklar.
- [ ] Pozitif test fixture'ları item-level canlı kanıtla güncellenir; simülasyon testleri explicit false kalır.

## 2. Dürüst DM dili
- [ ] Test: gerçek valid dict ile lead_dm çıktısında `organik`, `altyapınız iyi`, `siteniz cevaplarda belirdi` bulunmaz; koşu kimliği, tarihi ve modalite bulunur. Geçersiz dict iddia üretmez.
- [ ] RED sonrası outreach şablonu soru bankası/LLM yanıtlarında marka veya domain eşleşmesi olarak anlatır. Arama kaynaklandırması ayrıca doğrulanmadığı açıkça belirtilir.
- [x] CLI `--from-lead --with-visibility` eksik/geçersiz son kanıtta taslağı durdurur; yapılandırılmış gerçek gönderim yolu ölçümlü lead + valid ortak dict olmadan SMTP rezervasyonu/çağrısına ulaşmaz (tur 4). Bayraksız mini-probe taslağı değişmedi; dry-run uygunluk kanıtı değildir.

## 3. Doğrulama ve kayıt
- [ ] Odaklı suite: `python3 -m pytest tests/test_visibility_evidence.py tests/test_queue_gates.py tests/test_live_citations.py tests/test_dm_dispatch.py -q -p no:cacheprovider`.
- [ ] Bağımsız salt okunur inceleme; düzeltme dışı riskler ayrı kaydedilir.
- [ ] Tam suite: `python3 -m pytest -q -p no:cacheprovider --cov=answrank --cov-report=term-missing`.
- [ ] progress/findings güncelleme ve changed-file teslimi. Rapor sayfası, provider grounding ve immutable snapshot çözülmüş sayılmaz.
