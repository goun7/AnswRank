# Changelog

## [Unreleased]

### [Fix-2026-10-05] — AnswRank ↔ Sester x402 mesh code bond
- **MCP sunucusu Sester x402 ödeme rayına bağlandı** (mesh reçetesi:
  "85-AnswRank — MCP server'a SADECE Sester sarması gerekiyor",
  `orkestrasyon/PORTFOJ_SINERJI_HARITASI_2026-09-24.md` §7.0.2).
- Yeni `answrank/x402_gate.py`: fail-closed ödeme kapısı — makbuz
  doğrulama (Sester hash-zincir) + mainnet modunda zincirde USDC
  transferi arama; zayıf/boş secret ile ücretli mod açılmaz.
- Üç ücretli MCP aracı (`answrank_audit` / `_citations` /
  `_generate_fixes`) artık ödemeyi çalışmadan ÖNCE doğrülüyor; her ödenen
  çağrının çıktısının SHA-256 anchor hash'i receipt ledger'a yazılıyor
  (machine-checkable teslimat kanıtı).
- Ücretsiz mod korunur (yanıt `mode: "free"` ile etiketlenir); mevcut
  davranış ve testler değişmedi.
- Test izolasyonu: x402 ödeme env'i test başına izole edildi (bazı x402
  testleri import seviyesinde `ANSWRANK_SELLER_SECRET` sızdırıyordu).
- Testler: 1250 → **1261 passed**, 5 skipped, rc=0.

## [0.1.0] — 2026-09-29
- İlk genel sürüm: AnswRank
- **Audit your website the way AI search engines see it.**

## Sürümleme

- [SemVer](https://semver.org/lang/tr/) uyumludur.
