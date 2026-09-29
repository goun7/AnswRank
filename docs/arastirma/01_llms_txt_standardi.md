# llms.txt Standardı — Format, Benimseme ve Denetim Gereksinimleri

**Derleme tarihi:** 2026-09-28
**Zero-trust protokolü:** Aşağıdaki her bilgi kaynaktan bizzat okunmuştur. Okunamayan hiçbir şey
"yaygın olarak biliniyor" diye yumuşatılmamıştır; **"DOĞRULANAMADI"** olarak işaretlenmiştir.

---

## 1. Standart nedir?

Jeremy Howard (Answer.AI) tarafından 3 Eylül 2024'de önerilmiş, **10 Ağustos 2026'da v2'ye
güncellenmiş** bir standart. Amaç: bir web sitesinin LLM'ler ve agent'lar için anlaşılır
bilgisini tek, erişilebilir bir markdown dosyasında toplamak.

Kaynak: [llmstxt.org — The /llms.txt file, v2](https://llmstxt.org/) (HTTP 200, 2026-09-28'de okundu)

**v2'de belirtilen benimseme durumu (kaynağın kendi ifadesi):**
> "thousands of sites publish an llms.txt file, documentation platforms generate one
> automatically, and Chrome's Lighthouse audits sites for one as part of its agentic browsing
> checks. The AI labs themselves publish llms.txt files for their own developer docs: OpenAI,
> Anthropic, and Gemini."

**Önemli not:** "thousands of sites" ifadesi kaynağın kendi iddiasıdır; bağımsız bir
yüzde/kabul-oranı ölçümü bu standart için **DOĞRULANAMAMIŞTIR** (mevcut `GEO_LITERATUR_TARAMA`
dosyasının 1. bölümündeki "llms.txt kabul oranları" araştırması da aynı sonucu vermiştir:
arXiv'de 2 ilgili çalışma var, hiçbirinde benimseme yüzdesi yok).

---

## 2. Format kuralları (v2 spesifikasyonundan birebir)

Spesifikasyon "files named `llms.txt`, at the root path `/llms.txt` of a website or at any
subpath (e.g. `/docs/llms.txt`)" der. Bir dosya **kendi yolunun altındaki URL'leri** kapsar;
birden fazla dosya uygulanıyorsa agent **en spesifik olanı** kullanmalıdır.

Bileşenler, **bu sırada**:

| # | Bileşen | Zorunlu mu? | Açıklama |
|---|---|---|---|
| 1 | Opsiyonel BOM (byte-order mark) | Hayır | UTF-8 BOM olabilir |
| 2 | **H1** — proje/site adı | **EVET (tek zorunlu bölüm)** | `# Site Adı` |
| 3 | Blockquote — kısa özet | Hayır (ama önerilir) | `>` ile başlar; dosyanın geri kalanını anlamak için gerekli anahtar bilgileri içerir |
| 4 | Markdown bölümleri (paragraf, liste vb.) | Hayır | **Başlık (heading) içeremez** — sadece H1'den sonra detay |
| 5 | Başlık + link bölümleri | Hayır | `## Docs` gibi başlıkların altında markdown link listeleri |

**Link notasyonu:** linkler "LLM-friendly content"e (markdown sürümleri) işaret etmeli.
Spesifikasyon ayrıca her sayfanın `.md` sürümünü önerir: `page.html.md` veya `page.md`;
uzantısız URL'ler için `index.html.md` / `index.md`.

**Keşif ilişkileri (v2 yeniliği):**
- `rel="alternate" type="text/markdown"` → sayfanın markdown sürümü
- `rel="describedby"` → o yolu kapsayan llms.txt dosyası
- HTML `<link>` elemanı **veya** HTTP `Link:` response header olarak verilebilir:
  ```
  Link: </docs/page.html.md>; rel="alternate"; type="text/markdown", </docs/llms.txt>; rel="describedby"
  ```

**Tasarım felsefesi:** "The file itself stays small enough to fit in context. The detail lives
behind the links, and is fetched only when needed." Yani llms.txt **bir dizindir, ansiklopedi değil.**

---

## 3. Gerçek örnek (llmstxt.org'un kendi llms.txt'si — birebir)

Kaynak: [llmstxt.org/llms.txt](https://llmstxt.org/llms.txt) (HTTP 200, 2026-09-28'de okundu)

```markdown
# llms.txt

> A proposal that those interested in providing LLM-friendly content add a /llms.txt file to
> their site. This is a markdown file that provides brief background information and guidance,
> along with links to markdown files providing more detailed information.

## Docs

- [llms.txt proposal](https://llmstxt.org/index.md): The proposal for llms.txt
- [Python library docs](https://llmstxt.org/intro.html.md): Docs for `llms-txt` python lib
- [ed demo](https://llmstxt.org/ed.md): Tongue-in-cheek example of how llms.txt could be used
  in the classic `ed` editor, used to show how editors could incorporate llms.txt in general.
```

Bu örnek tüm zorunlu ve önerilen bölümleri içerir: H1, blockquote özet, `##` başlık + link listesi.

---

## 4. llms.txt vs robots.txt vs AGENTS.md

| Belge | Kim okur | Ne kontrol eder | Format |
|---|---|---|---|
| **robots.txt** | Klasik + AI tarayıcıları | Erişim izni (Allow/Disallow) | Kendi RFC9309 formatı |
| **llms.txt** | LLM'ler / agent'lar | **İçerik keşfi** — site ne hakkında, detay nerede | Markdown |
| **AGENTS.md** | AI kod-ajanları | Repo/dizin seviyesinde agent davranış talimatları | Markdown |

llms.txt **izin kontrolü yapmaz** — erişim hâlâ robots.txt'in işi. llms.txt izin verildikten
sonra "izin verilen içeriğin en verimli özetidir". Bu ayrım denetimde şart: ikisi ayrı kontrol edilir.

---

## 5. Yaygın hatalar (denetimde aranmalı)

1. **Dosya yok** — `/llms.txt` 404 döner (en yaygın durum).
2. **Yanlış yerde** — `https://site.com/pages/llms.txt` gibi kök-dışı, spesifikasyonun
   "kendi yolunun altını kapsar" kuralına göre ancak o alt-yolu kapsar; kök için kökte olmalı.
3. **H1 yok** — zorunlu tek bölüm eksik → standarta aykırı.
4. **Boş dosya** veya içerikten kopuk "coming soon" metni.
5. **HTML döndüren llms.txt** — bazı sunucular yol yeniden yazımı (rewrite) ile HTML sayfası döner.
6. **Markdown link formatı hatalı** — `## Docs` başlığı var ama altında `[...](url)` listesi yok.
7. **`llms-full.txt` yok** — tam içeriğin ayrı dosyası standartta opsiyoneldir ama derin denetimde
   değerli bir sinyaldir.
8. **Boyut kontrolü yok** — spesifikasyon "context'e sığacak kadar küçük" der; 200 KB'lık
   llms.txt felsefeye aykırıdır.

---

## 6. KOD GEREKSİNİMLERİ — `llms_txt_kontrol.py` için

Bir `llms_txt_kontrol(domain)` fonksiyonu aşağıdaki denetimleri **test edilebilir kurallar** olarak
yapmalıdır. Her biri bir test case'e dönüşebilmeli:

### 6.1. Varlık denetimi
- `https://{domain}/llms.txt` GET isteği → durum kodu
- Kural: HTTP 200 → "var"; 404/410 → "yok"; 3xx → takip edilince 200 mü
- `https://www.{domain}/llms.txt` www varyantı da denenmeli (fallback)

### 6.2. Format denetimi (içerik geldikten sonra)
- `var_h1`: regex `^#\s+.+` (MULTILINE) → en az 1 H1 olmalı
- `var_blockquote`: regex `^>\s*.+` (MULTILINE) → önerilir (bilgi uyarısı)
- `markdown_link_sayisi`: `[...](...)` desenleri sayılır
- `bolum_sayisi`: `^##\s+` (H2) başlık sayısı
- `icerik_tipi`: `text/plain` veya `text/markdown` olmalı; HTML döndürülüyorsa uyarı
  (`<html` veya `<!DOCTYPE` imzası aranır)

### 6.3. Boyut denetimi
- `boyut_byte`: len(content)
- Kural: `0` → bozuk; `> 100_000` → "felsefeye aykırı, çok büyük" uyarısı
- Önerilen band: 100 byte – 50 KB

### 6.4. Link geçerlilik denetimi
- Her markdown link'in URL'i `http(s)://` ile başlamalı
- İlk link site dışına çıkıyor ve `llms-full.txt` değilse uyarı (kolay bozulan işaret)
- `llms-full.txt` işaretı var mı (opsiyyonel pozitif sinyal)

### 6.5. `llms-full.txt` varlığı
- `https://{domain}/llms-full.txt` → 200 mü (opsiyonel, pozitif sinyal)

### 6.6. HTML keşif linkleri (v2 önerisi)
- Ana sayfa HTML'inde `rel="describedby"` veya `rel="alternate" type="text/markdown"`
  `link` etiketi var mı (zayıf pozitif sinyal; yoksa uyarı değil)

### 6.7. Skor
- 0-3 arası: `0` (yok) / `1` (var ama format bozuk) / `2` (var + H1) /
  `3` (var + H1 + blockquote + link bölümü)
- **llms.txt skoru asla ana AI-görünürlük puanına yüksek ağırlıkta katılmamalı** —
  akademik olarak atıf üzerindeki ölçülmüş etkisi DOĞRULANMAMIŞTIR. Sadece bilgilendirici
  bir " hazır olma" (readiness) göstergesi olarak raporlanmalıdır.

---

## 7. Kaynaklar

- [llmstxt.org — The /llms.txt file, v2](https://llmstxt.org/) — DOĞRULANDI (HTTP 200, 2026-09-28)
- [llmstxt.org/llms.txt](https://llmstxt.org/llms.txt) — DOĞRULANDI (gerçek örnek dosya)
- Mevcut `GEO_LITERATUR_TARAMA_2026-BAHAR.md` bölüm E — llms.txt akademik değerlendirmesi
  (benimseme yüzdesi DOĞRULANAMADI; Volpini 2026: llms.txt-ruhu içeren entity sayfası
  RAG doğruluğunu **+%29,6** artırmış — ama bu llms.txt'nin kendisinin değil, ondan
  esinlenen sayfa mimarisinin etkisidir)
