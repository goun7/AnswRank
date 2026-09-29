# Zeron'a Geri Bildirim — AnswRank (Python) Denetiminden Gelen Bulgular

Tarih: 2026-09-18 · Proje: AnswRank (FastAPI + Python 3.14, tek-kiracılı self-host)
Yöntem: `zeron audit`, `zeron scan`, `zeron quality`, `zeron dead-modules`,
`zeron cognitive`, `zeron i18n-audit`, `zeron status-audit` (canlı OpenAPI
JSON'ı üzerinden), `zeron sign-proof` + `verify-proof`.

## 1) KRİTİK: Boş tarama 100/100 üretiyor (güven sorununu)

`zeron audit .` bir **Python** projesinde **100/100, 0 Critical Blocker** verdi.
Ama kod sondalarının hepsi 0 döndü:

- `scan` → "Toplam Taranan Buton: 0" — "No buttons or clickable components found"
- `quality` → "Profillenen Fonksiyon: 0" (karmaşıklık/magic-number/yorum yoğunluğu hepsi 0)
- `dead-modules` → "Toplam Dosya: 0"
- `cognitive` → "Taranan Buton/Eylem: 0" → ama yine de "%100 uyumlu" hükmü verdi
- `i18n-audit` → "Yerel Diller: bulunamadı"

Kök neden: `src/cli/commands.ts:788`
`const SCRIPT_EXTENSIONS = new Set(['.ts', '.tsx', '.jsx', '.vue']);`

Python (`.py`), Go, Ruby, Java taramıyor. **Sorun şu:** taranan hiçbir şey
yokken "100/100" raporlamak, boş bir tarayıcının sonucunu bir kalite
belgesine dönüştürür. Gerçek dünyada bu, bir projenin "Zeron ile 100/100
doğrulandı" şeklinde pazarlanmasına izin verir — tıpkı bizim geçmişte
yaşadığımız "Zeron 100/100 mühürlü imza" iddiasının bir denetimde çökmesi gibi.

**Öneri:** taranan dosya/fonksiyon 0 ise sağlık skorunu **100/100 değil**,
`N/A — desteklenmeyen dil` veya `SKIP (dil kapsamı yok)` olarak ver; ve
"0 buton tarandı" durumunda `%100 uyumlu` hükmü yerine "karar verilemedi"
de. `doctor`'da bunu bir PASS değil **SKIP** (Mobile bridge'de zaten yapıyorsun:
"No iOS/Android devices attached — skipped (no fabricated devices)") olarak
işaretle. Aynı kendilik-farkındalığı kod sondalarına taşı.

## 2) Yanlış pozitif: R-NO-4XX / R-4XX-AND-5XX HTML sayfa route'larında

`/`, `/dashboard`, `/health` gibi HTML-serving route'lar için "4xx
dokümante edilmemiş" dedi. FastAPI'de bu route'ların yanıtları framework
tarafından otomatik üretilir; her sayfa route'una 404/500 açıklaması eklemek
gerçek bir kalite göstergesi değil, gürültüdür.

**Öneri:** `response_class=HTMLResponse` (veya benzeri HTML işaretçisi) taşıyan
işlemlerde R-NO-4XX/R-4XX-AND-5XX kurallarını atla; ya da en azından
"HTML sayfa route'u — framework yanıtları üretir" notuyla P2'den düşük
önceliğe (bilgilendirme) indir.

## 3) Yanlış pozitif: R-MUTATING-401 ve R-429-ON-LIMITED (28+28 = 56 bulgu)

**56 bulgunun tamamı** tek-kiracılı self-host mimarisinde yanlış:
kimlik-doğrulama katmanı bilerek yok (ürün müşterinin kendi altyapısında
çalışıyor, dış ağ geçidi arkasında) ve rate-limit dış ağ geçidine ait.

**Öneri:** proje kökünde bir opt-out/yapılandırma imkanı:
`.zeronrc` (veya `zeron.config.json`) ile
`{ "singleTenant": true, "auth": "external-gateway" }` → R-MUTATING-401 ve
R-429-ON-LIMITED sessize alınır veya "bilinçli tasarım" etiketiyle raporlanır.
Bu, bulguların gerçek sinyali boğmasını engeller (87 bulgunun 78'i
bizde yanlış pozitifti — %90 gürültü).

## Ne işe yaradı (açıkça belirt)

`status-audit` **dilden bağımsız** olduğu için (canlı OpenAPI JSON'unu tarıyor)
Python projemizde tek gerçek sinyali o üretti: **9 parametreli path
runtime'da 404 fırlatıyor ama spec'te beyan etmiyordu** (R-WILDCARD-PATH-404).
Gerçek bir kusurdu, düzeltildi ve testle kilitlendi. Zeron bulguları
87 → 78'e düştü; kalan 78'in tamamı yukarıdaki 2/3. maddelerdeki
yanlış pozitifler.

`sign-proof` + `verify-proof` zinciri de gerçek çalışıyor: imza gerçek bir
test koşumundan (950 passed, rc=0) üretildi ve kriptografik olarak
doğrulandı.

## Özetle sıralama

1. **Boş taramada 100/100 vermeme** (en kritik — güven/ciddiyet)
2. HTML route'larında 4xx kuralını atlama
3. Tek-kiracılı/no-auth projeler için auth/rate-limit kurallarını opt-out

İyi ürün, özellikle doctor sondalarındaki kendilik-farkındalık (mobile
bridge'i atlamayı dürüstçe belirtmesi) çok doğru. Aynı disiplin kod
sondalarına yayılırsa Python projelerinde de güvenilir olur.
