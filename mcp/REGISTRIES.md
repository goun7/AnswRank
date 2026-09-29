# MCP Registry Kayıt Rehberi — AnswRank

**Durum:** dosyalar HAZIR. **Kayıt YAPILMADI** — kullanıcı onayı bekleniyor.
Maliyet: **$0** (yalnızca ücretsiz tier'lar).

---

## 1. Smithery (öncelik)

Smithery, Arcade.dev'e katıldı (2026):
<https://arcade.dev/blog/smithery-joins-arcade>

**İki yayın yolu** (<https://smithery.ai/docs/build/publish>):

### A) Local — MCPB Bundle (bizim için uygun, stdio server)
```bash
npm install -g smithery@latest          # Node.js 20+
smithery auth login
smithery mcp publish ./answrank.mcpb -n <org>/answrank
```
- Yapılandırma hazırdır: [`smithery.yaml`](smithery.yaml)
- Manifest: [`mcp.json`](mcp.json)
- Giriş noktası: `python -m answrank.mcp.server`

### B) URL — Streamable HTTP + OAuth (kendi host'unuz)
```bash
# 1) AnswRank MCP'yi HTTP uç noktası olarak yayınla
# 2) https://smithery.ai/new → HTTPS URL gir → yayınlama akışını tamamla
```

**Yerel deneme (kayıtsız):**
```bash
smithery mcp add -m answrank.mcp.server --id answrank
smithery tool list answrank
smithery tool call answrank answrank_generate_fixes '{"domain":"example.com"}'
```

**Önemli:** `answrank_audit` ve `answrank_generate_fixes` **API anahtarı
istemez**. Yalnızca `answrank_citations` için LLM anahtarları gerekir
(aşağıda §5). Hızlı demo: `answrank_generate_fixes` — $0, anahtarsız.

### Smithery'de konum
En yakın analog Glama'da `Agent Ready` (AI readability scanner). AnswRank'in
farkı: **8-kategorili AEO/GEO audit + 5-model citation testi + hazır
robots/llms.txt/JSON-LD üretimi** birlikte. AEO/GEO MCP alanının derin
rakip taraması bu oturumda yapılmadı — **belirsiz**; yayın öncesi
`smithery mcp search geo` ile tamamlanmalı.

---

## 2. Glama.ai

- Directory: <https://glama.ai/mcp/servers> (**93,546 server**, 2026-09-28)
- **"Add Server"** formu ile GitHub repo URL'si; README taranır.
- Kategoriler (önerilen): `SEO & Marketing`, `Developer Tools`, `Analytics`

---

## 3. mcp.so

- Submit: <https://mcp.so/submit?type=server>
- **Ücretsiz tier:** form → review. **$39 ödeme YAPILMAYACAK** (opsiyonel
  hızlandırma).

---

## 4. Punkpeye awesome-mcp-servers

- Repo: <https://github.com/punkpeye/awesome-mcp-servers>
- Kayıt = **PR açmak** (ücretsiz):
  `- [AnswRank](https://github.com/goun7/AnswRank) - AEO/GEO audit, multi-model citation testing, and llms.txt/robots/JSON-LD generation.`

---

## 5. Manuel stdio config (yayın öncesi)

```json
{
  "mcpServers": {
    "answrank": {
      "command": "python",
      "args": ["-m", "answrank.mcp.server"],
      "env": {
        "PERPLEXITY_API_KEY": "...",
        "OPENAI_API_KEY": "...",
        "GEMINI_API_KEY": "...",
        "ANTHROPIC_API_KEY": "...",
        "MISTRAL_API_KEY": "..."
      }
    }
  }
}
```

**Anahtarlar:** `answrank_citations` için en az BİR LLM sağlayıcı anahtarı
yeter; beşi de zorunlu DEĞİL. `answrank_audit` / `answrank_generate_fixes`
için anahtar GEREKMEZ. Anahtarlar environment'te tutulur, asla
ekrana yazılmaz.

---

## 6. Kayıt Öncesi Checklist

- [x] MCP server stdio'da çalışıyor (initialize + tools/list + tools/call)
- [x] `mcp/smithery.yaml` hazır
- [x] `mcp/mcp.json` hazır
- [x] `mcp/README.md` var (kurulum + tool listesi + örnek)
- [x] README.md'de MCP bölümü var
- [ ] **Kullanıcı onayı** → Smithery publish
- [ ] **Kullanıcı onayı** → Glama "Add Server"
- [ ] **Kullanıcı onayı** → mcp.so submit (ücretsiz tier)
- [ ] **Kullanıcı onayı** → Punkpeye PR
- [ ] Yayın sonrası: README'lere registry linkleri ekle

**Not:** API anahtarları bu dokümanda YOK; tüm anahtarlar environment'te
tutulur ve asla ekrana yazılmaz.
