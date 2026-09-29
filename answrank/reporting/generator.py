"""Report Generator: Produces 1-Page Markdown and Interactive Standalone HTML reports."""

from html import escape as h
from answrank.legal.contract_generator import ENGINE_LEGAL_NAMES
from answrank.models import AuditResult

_ENGINE_ROSTER_LINE = (
    '<p style="font-size:14px; color:#cbd5e1;">Bu denetim; web sitenizin '
    + '; '.join(ENGINE_LEGAL_NAMES.values())
    + ' motorlarında taranabilirlik, RAG parçalanabilirliği ve alıntılanabilirlik (citability) parametrelerini'
    + ' ölçer; yöntem envanteri docs/DENETIM_EXCEPT_ENVANTERI.md\'dedir.</p>'
)

# Logo 1 Inline SVG Mark
LOGO_SVG = """<svg width="40" height="40" viewBox="0 0 800 800" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="800" height="800" fill="#08090d" rx="90"/>
  <g transform="translate(400, 360)">
    <path d="M -90,140 L -90,-20 C -90,-80 -40,-130 20,-130 L 20,-75 C -10,-75 -35,-50 -35,-20 L -35,140 Z" fill="#ffffff"/>
    <path d="M 35,140 L 35,-40 L 90,15 L 90,-90 L 0,-180 L -30,-150 L 35,-85 Z" fill="#10b981"/>
    <circle cx="-5" cy="50" r="16" fill="#10b981"/>
    <rect x="-35" y="44" width="70" height="12" rx="6" fill="#10b981" opacity="0.8"/>
  </g>
</svg>"""

class ReportGenerator:
    """Generates Markdown, JSON, and Self-Contained HTML reports."""

    @staticmethod
    def citation_share_summary(citation) -> dict:
        """Derive the SoV-language bridge numbers from a genuine CitationRunResult.

        Every figure is computed from stored run items — no market-wide claim, no
        invented denominator. The returned dict is rendered by both report formats.
        """
        per_model: dict = {}
        for it in citation.items:
            slot = per_model.setdefault(it.model, {"total": 0, "cited": 0, "live": 0})
            slot["total"] += 1
            if it.brand_mentioned:
                slot["cited"] += 1
            if not it.was_simulated:
                slot["live"] += 1
        return {
            "brand": citation.brand_name,
            "total": citation.total_runs,
            "cited": citation.brand_citations_found,
            "rate": citation.citation_rate_percentage,
            "live_items": citation.live_items_count,
            "sim_items": citation.total_runs - citation.live_items_count,
            "per_model": per_model,
        }

    def _citation_share_md(self, citation) -> str:
        if citation is None:
            return (
                "## 2b. Alıntı Payı / Citation Share (SoV Dil-Köprüsü)\n"
                "Bu domain için kayıtlı bir atıf koşusu bulunamadı — **ölçülmedi**; "
                "bu alana sayı uydurulmaz. Ölçüm için `/api/citations` koşusunu çalıştırın.\n\n---\n\n"
            )
        s = self.citation_share_summary(citation)
        models = " · ".join(
            f"{m}: {d['cited']}/{d['total']}" for m, d in sorted(s["per_model"].items())
        ) or "motor kırılımı yok"
        sim_note = (
            f"**Canlılık:** {s['live_items']}/{s['total']} yanıt CANLİ API, {s['sim_items']} yanıt "
            f"deterministik SİMÜLASYON — SoV eşdeğerliği yalnızca canlı alt-küme için iddia edilebilir."
            if s["sim_items"] else
            f"**Canlılık:** {s['total']}/{s['total']} yanıt canlı API ölçümüdür."
        )
        return (
            "## 2b. Alıntı Payı / Citation Share (SoV Dil-Köprüsü)\n"
            f"- **Ölçülen alıntı payı:** {s['cited']}/{s['total']} = **%{s['rate']:g}** — "
            f"'{s['brand']}' markasının tanımlı soru korpusunda AI cevaplarında kaynak gösterilme oranı.\n"
            f"- **Motor bazında:** {models}\n"
            f"- {sim_note}\n"
            f"- Endüstri dilindeki \"Share of Voice\" karşılığıdır; ticari SoV panellerinden "
            f"farkı **korpus-kayıtlı** olmasıdır (pazar-geneli değildir — tanımlı soru setine görelidir).\n\n---\n\n"
        )

    @staticmethod
    def _branding(white_label=None):
        """E2: kelime işaretinin TEK sahibi — beyaz etikette AnswRank görünmez."""
        name = (white_label or {}).get("name") or "AnswRank"
        logo = (white_label or {}).get("logo_url")
        return name, logo

    def to_markdown(self, audit: AuditResult, citation=None, white_label=None) -> str:
        """Generates 1-Page Markdown Audit Report (Ek A format)."""
        date_str = audit.timestamp.strftime("%d.%m.%Y")
        lost_rev = f"{audit.lost_revenue_estimate_monthly_try:,.0f} TL" if audit.lost_revenue_estimate_monthly_try else "Hesaplanmadı"

        recs_md = ""
        for idx, r in enumerate(audit.recommendations[:5], 1):
            recs_md += f"{idx}. **[{r.priority}] {r.title}:** {r.action} *(+{r.impact_points} Puan)*\n"

        cats = audit.categories
        _wlb = (white_label or {}).get("name") or "AnswRank"
        _wl = white_label

        warnings_md = ""
        if getattr(audit, "crawl_warnings", None):
            items = "\n".join(f"- {w}" for w in audit.crawl_warnings)
            warnings_md = (
                "## ⚠ Bu Denetimde Doğrulanamayan Varlıklar\n"
                f"{items}\n"
                "*(Bu maddeler \"YOK\" değil \"DOĞRULANAMADI\" durumudur — geçici ağ "
                "hatası olabilir; ilgili skorlar muhafazakâr davranır ve denetimin "
                "yeniden çalıştırılması önerilir.)*\n\n---\n\n"
            )
        return f"""# AI Görünürlük Denetimi (AEO/GEO Raporu) — {audit.domain}
**Tarih:** {date_str} · **Sektör:** {audit.sector.capitalize()} · **ID:** `{audit.audit_id}`  
**Genel Skor:** **{audit.overall_score}/100** ({audit.score_band})

---

## 1. Skor Kartı ve 8 Kategori Kırılımı
- **Robots.txt AI Erişimi:** {cats.robots.score}/18 Puan
- **llms.txt / llms-full.txt:** {cats.llms_txt.score}/18 Puan
- **JSON-LD Semantik Şema:** {cats.schema_jsonld.score}/16 Puan
- **Meta ve Başlık Mimarisi:** {cats.meta_architecture.score}/14 Puan
- **İçerik Alıntılanabilirliği & RAG:** {cats.citability_rag.score}/12 Puan
- **Marka Varlığı & Bilgi Grafiği:** {cats.entity_coherence.score}/10 Puan
- **Güven Katmanı (Trust Stack):** {cats.trust_stack.score}/6 Puan
- **Negatif / Manipülasyon Filtresi:** {cats.negative_signals.score}/6 Puan

---

## 2. Kaçan Müşteri ve Ciro Simülasyonu
- **Mevcut Görünürlük Açığı:** %{100 - audit.overall_score}
- **Tahmini Aylık Kaçan Potansiyel Ciro:** **~{lost_rev}**
*(YÖNTEM BİLGİLENDİRMESİ: Bu rakam, sektörel LTV sabiti × (100-skor)/100 × ~6.5 potansiyel müşteri çarpanı modeliyle üretilen KESTİRİMDİR; gerçek arama hacmi verisine dayalı ölçüm değildir. Satış sunumunda "tahmin" olarak etiketlenmelidir.)*

---

{self._citation_share_md(citation)}## 3. Öncelikli Düzeltme Reçetesi (İlk 14 Gün)
{recs_md if recs_md else "Kritik bir eksiklik bulunamadı; mükemmel AEO sinyalleri."}

{warnings_md if warnings_md else ""}---

## 4. Ölçüm Şeffaflık Notu
- llms.txt kategorisi (18 puan) mevcut akademik kanıtlarda deneysel bir uygulamadır: Google, AI Overviews için llms.txt'nin gerekli olmadığını resmen bildirmiştir (John Mueller, 2026); Ahrefs'in 137.000-domain sunucu-log analizi, yayımlanan dosyaların %97'sine hiç istek gelmediğini göstermektedir. Dosyanın üretilmesi önerilir ancak atıf üzerindeki doğrudan etkisi kanıtlanmamıştır.
- Ciro tahmini bir model çıktısıdır, ölçüm değildir.

---
*{('AnswRank Engine v1.0' if not _wl else _wlb + ' lisanslı raporu')} ile üretilmiştir. Resmi denetim kaydıdır.*
"""

    def to_json(self, audit: AuditResult, indent: int = 2) -> str:
        """Returns machine-readable JSON."""
        return audit.model_dump_json(indent=indent)

    def to_html(self, audit: AuditResult, citation=None, white_label=None) -> str:
        """Generates a standalone, dark-themed, ultra-clean HTML dashboard report."""
        _TR_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                      "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
        date_str = (f"{audit.timestamp.day:02d} {_TR_MONTHS[audit.timestamp.month - 1]} "
                    f"{audit.timestamp.year}, {audit.timestamp:%H:%M}")
        cats = audit.categories
        _brand, _logo = self._branding(white_label)
        _brand_line = (f'<img src="{h(_logo)}" alt="{h(_brand)} logosu" style="height:22px;vertical-align:middle;"> '
                       if _logo else "") + (
            f"{h(_brand)} · Denetim-Raporlama Lisansı · Otomatik Üretilmiştir." if white_label else
            "AnswRank Engine v1.0 · Generative Engine Optimization & Answer Engine Optimization Standardı · Otomatik Üretilmiştir.")

        lost_rev = f"{audit.lost_revenue_estimate_monthly_try:,.0f} ₺" if audit.lost_revenue_estimate_monthly_try else "ÖLÇÜLEMEDİ"

        # Color based on score
        if audit.overall_score >= 86:
            score_color = "#10b981"
            badge_class = "badge-excellent"
        elif audit.overall_score >= 68:
            score_color = "#38bdf8"
            badge_class = "badge-good"
        elif audit.overall_score >= 36:
            score_color = "#f59e0b"
            badge_class = "badge-foundation"
        else:
            score_color = "#ef4444"
            badge_class = "badge-critical"

        # Radial progress offset (circumference ~ 283)
        dashoffset = 283 - (283 * audit.overall_score / 100)

        # Recommendation items HTML
        recs_html = ""
        for r in audit.recommendations:
            p_color = "#ef4444" if r.priority == "CRITICAL" else ("#f59e0b" if r.priority == "HIGH" else "#3b82f6")
            recs_html += f"""
            <div class="rec-card">
              <div class="rec-header">
                <span class="rec-priority" style="background:{p_color}20; color:{p_color}; border:1px solid {p_color}40;">{r.priority}</span>
                <span class="rec-cat">{h(r.category)}</span>
                <span class="rec-points">+{r.impact_points} Puan</span>
              </div>
              <h4 class="rec-title">{h(r.title)}</h4>
              <p class="rec-action">{h(r.action)}</p>
            </div>
            """

        cat_cards = [
            ("Robots.txt & AI Botlar", cats.robots.score, 18, "OAI-SearchBot, Perplexity, Claude izinleri", cats.robots.details[:2]),
            ("llms.txt Standartları", cats.llms_txt.score, 18, "/llms.txt & /llms-full.txt özet dizini", cats.llms_txt.details[:2]),
            ("JSON-LD Şema Zenginliği", cats.schema_jsonld.score, 16, "Sektörel varlık ve FAQPage işaretlemesi", cats.schema_jsonld.details[:2]),
            ("Meta & Başlık Mimarisi", cats.meta_architecture.score, 14, "Doğrudan cevap veren title, OG, H1", cats.meta_architecture.details[:2]),
            ("İçerik Alıntılanabilirliği", cats.citability_rag.score, 12, "İstatistik yoğunluğu ve RAG chunking", cats.citability_rag.details[:2]),
            ("Marka & Bilgi Grafiği", cats.entity_coherence.score, 10, "NAP tutarlılığı ve sameAs profilleri", cats.entity_coherence.details[:2]),
            ("Güven Katmanı (Trust)", cats.trust_stack.score, 6, "HTTPS, dateModified ve SSR erişimi", cats.trust_stack.details[:2]),
            ("Manipülasyon Filtresi", cats.negative_signals.score, 6, "Sıfır ceza puanı, temiz içerik", cats.negative_signals.details[:2]),
        ]

        cats_html = ""
        for name, score, max_score, subtitle, details_list in cat_cards:
            pct = int((score / max_score) * 100)
            bar_color = "#10b981" if pct >= 80 else ("#38bdf8" if pct >= 50 else "#ef4444")
            details_li = "".join(f"<li>{h(d)}</li>" for d in details_list)
            cats_html += f"""
            <div class="cat-card">
              <div class="cat-header">
                <span class="cat-name">{name}</span>
                <span class="cat-score">{score} <small>/ {max_score}</small></span>
              </div>
              <div class="bar-bg"><div class="bar-fill" style="width:{pct}%; background:{bar_color};"></div></div>
              <p class="cat-sub">{subtitle}</p>
              <ul class="cat-details">{details_li}</ul>
            </div>
            """

        warnings_html = ""
        if getattr(audit, "crawl_warnings", None):
            w_items = "".join(f"<li>{h(w)}</li>" for w in audit.crawl_warnings)
            warnings_html = (
                '<div class="rec-card" style="border-color:rgba(245,158,11,0.4); margin-bottom:16px;">'
                '<h4 class="rec-title" style="color:#f59e0b;">⚠ Bu Denetimde Doğrulanamayan Varlıklar</h4>'
                f'<ul class="cat-details">{w_items}</ul>'
                '<p class="rec-action">Bu maddeler "YOK" değil "DOĞRULANAMADI" durumudur (geçici ağ '
                'hatası olabilir); ilgili skorlar muhafazakâr davranır — denetimin yeniden '
                'çalıştırılması önerilir.</p></div>'
            )

        # --- 2b. Citation-Share (SoV dil-köprüsü): rendered ONLY from a stored run ---
        if citation is None:
            share_html = (
                '<h3 class="section-title">Alıntı Payı / Citation Share (SoV Dil-Köprüsü)</h3>'
                '<div class="rec-card"><p class="rec-action">Bu domain için kayıtlı bir atıf koşusu '
                'bulunamadı — <strong>ölçülmedi</strong>; bu alana sayı uydurulmaz. Ölçüm için '
                '<code>POST /api/citations</code> koşusunu çalıştırın.</p></div>'
            )
        else:
            s = self.citation_share_summary(citation)
            model_rows = "".join(
                f'<li>{h(m)}: {d["cited"]}/{d["total"]}'
                + (f' <span style="color:#10b981;">(canlı {d["live"]})</span>' if d["live"] else ' <span style="color:#f59e0b;">(tamamı simülasyon)</span>')
                + "</li>"
                for m, d in sorted(s["per_model"].items())
            ) or "<li>Motor kırılımı kayıtlı değil</li>"
            sim_line = (
                f"Canlılık: {s['live_items']}/{s['total']} CANLİ API, {s['sim_items']} deterministik SİMÜLASYON "
                f"— SoV eşdeğerliği yalnızca canlı alt-küme için iddia edilebilir."
                if s["sim_items"] else
                f"Canlılık: {s['total']}/{s['total']} yanıt canlı API ölçümüdür."
            )
            share_html = f'''
            <h3 class="section-title">Alıntı Payı / Citation Share (SoV Dil-Köprüsü)</h3>
            <div class="rec-card" style="border-color:rgba(56,189,248,0.35);">
              <div class="rec-header">
                <span class="rec-priority" style="background:#38bdf820; color:#38bdf8; border:1px solid #38bdf840;">ÖLÇÜLMÜŞ</span>
                <span class="rec-cat">{h(s["brand"])} · korpus: {s["total"]} koşu</span>
                <span class="rec-points">%{s["rate"]:g} ({s["cited"]}/{s["total"]})</span>
              </div>
              <ul class="cat-details">{model_rows}</ul>
              <p class="rec-action">{h(sim_line)} Endüstri "Share of Voice" dilinin karşılığıdır; farkı
              <strong>korpus-kayıtlı</strong> olmasıdır (pazar-geneli değildir).</p>
            </div>
            '''

        return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_brand} Denetim Raporu — {h(audit.domain)}</title>
  <style>
    :root {{
      --bg: #090a0f;
      --card-bg: #11131c;
      --border: #1e2233;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent-emerald: #10b981;
      --accent-blue: #38bdf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      padding: 40px 20px;
    }}
    .container {{ max-width: 1040px; margin: 0 auto; }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 32px;
    }}
    .brand {{ display: flex; align-items: center; gap: 14px; }}
    .brand-title {{ font-size: 24px; font-weight: 800; letter-spacing: 2px; }}
    .brand-sub {{ font-size: 11px; font-weight: 600; color: var(--text-muted); letter-spacing: 3px; }}
    .meta-badge {{
      background: #1e2233;
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 13px;
      color: var(--text-muted);
    }}
    .hero {{
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 24px;
      margin-bottom: 32px;
    }}
    .score-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 32px;
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }}
    .circle-wrap {{ position: relative; width: 140px; height: 140px; margin-bottom: 16px; }}
    .circle-wrap svg {{ transform: rotate(-90deg); }}
    .score-number {{
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 38px;
      font-weight: 900;
      color: #fff;
    }}
    .score-label {{ font-size: 12px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: var(--text-muted); }}
    .badge-pill {{
      display: inline-block;
      margin-top: 12px;
      padding: 4px 14px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 700;
    }}
    .badge-excellent {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
    .badge-good {{ background: #38bdf820; color: #38bdf8; border: 1px solid #38bdf840; }}
    .badge-foundation {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
    .badge-critical {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
    .summary-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 32px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .target-domain {{ font-size: 28px; font-weight: 800; color: #fff; margin-bottom: 6px; }}
    .target-sector {{ font-size: 14px; color: var(--accent-emerald); font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 20px; }}
    .rev-box {{
      background: #ef444415;
      border: 1px solid #ef444430;
      padding: 16px 20px;
      border-radius: 14px;
      margin-top: 16px;
    }}
    .rev-val {{ font-size: 24px; font-weight: 800; color: #f87171; }}
    .rev-desc {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
    .section-title {{ font-size: 18px; font-weight: 700; margin: 36px 0 20px; letter-spacing: 0.5px; }}
    .cats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
    }}
    .cat-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px;
    }}
    .cat-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }}
    .cat-name {{ font-size: 14px; font-weight: 700; color: #fff; }}
    .cat-score {{ font-size: 16px; font-weight: 800; }}
    .cat-score small {{ font-size: 11px; color: var(--text-muted); }}
    .bar-bg {{ height: 6px; background: #1e2233; border-radius: 3px; overflow: hidden; margin-bottom: 12px; }}
    .bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.5s ease; }}
    .cat-sub {{ font-size: 11px; color: var(--text-muted); margin-bottom: 10px; }}
    .cat-details {{ list-style: none; font-size: 11px; color: #cbd5e1; }}
    .cat-details li {{ margin-bottom: 4px; position: relative; padding-left: 12px; }}
    .cat-details li::before {{ content: '•'; position: absolute; left: 0; color: var(--accent-emerald); }}
    .recs-list {{ display: flex; flex-direction: column; gap: 14px; }}
    .rec-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px 24px;
    }}
    .rec-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
    .rec-priority {{ font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 8px; letter-spacing: 1px; }}
    .rec-cat {{ font-size: 12px; color: var(--text-muted); }}
    .rec-points {{ margin-left: auto; font-size: 12px; font-weight: 700; color: var(--accent-emerald); }}
    .rec-title {{ font-size: 16px; font-weight: 700; color: #fff; margin-bottom: 6px; }}
    .rec-action {{ font-size: 13px; color: #cbd5e1; }}
    .footer {{
      margin-top: 48px;
      padding-top: 24px;
      border-top: 1px solid var(--border);
      text-align: center;
      font-size: 12px;
      color: var(--text-muted);
    }}
    @media (max-width: 768px) {{
      .hero {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">
        {LOGO_SVG}
        <div>
          <div class="brand-title">ANSW<span style="color:#10b981;">RANK</span></div>
          <div class="brand-sub">GENERATIVE ENGINE AUDIT</div>
        </div>
      </div>
      <div class="meta-badge">{date_str} · Rapor ID: {audit.audit_id}</div>
    </div>

    <div class="hero">
      <div class="score-card">
        <div class="circle-wrap">
          <svg width="140" height="140">
            <circle cx="70" cy="70" r="45" stroke="#1e2233" stroke-width="8" fill="none"/>
            <circle cx="70" cy="70" r="45" stroke="{score_color}" stroke-width="8" stroke-dasharray="283" stroke-dashoffset="{dashoffset}" stroke-linecap="round" fill="none"/>
          </svg>
          <div class="score-number">{audit.overall_score}</div>
        </div>
        <div class="score-label">AEO Görünürlük Skoru</div>
        <div class="badge-pill {badge_class}">{audit.score_band} Düzey</div>
      </div>

      <div class="summary-card">
        <div>
          <h2 class="target-domain">{h(audit.domain)}</h2>
          <div class="target-sector">Sektör: {h(audit.sector.capitalize())}</div>
          {_ENGINE_ROSTER_LINE}
        </div>

        <div class="rev-box">
          <div class="rev-val">~{lost_rev} / ay</div>
          <div class="rev-desc">Yapay zeka tavsiyelerinde rakiplere yönlendirilen tahmini kayıp potansiyel ciro.</div>
        </div>
      </div>
    </div>

    <h3 class="section-title">8 Ağırlıklı Puanlama Kategorisi</h3>
    <div class="cats-grid">
      {cats_html}
    </div>

    {warnings_html}
    {share_html}
    <h3 class="section-title">Öncelikli İyileştirme Reçetesi (14 Günlük Eylem Planı)</h3>
    <div class="recs-list">
      {recs_html if recs_html else '<div class="rec-card"><p style="color:#10b981;">Kritik düzeltme ihtiyacı tespit edilmedi.</p></div>'}
    </div>

    <div class="footer">
      <p style="margin-bottom:10px; font-size:11px; opacity:0.85;">Şeffaflık Notu: llms.txt kategorisi deneysel bir uygulamadır (Google: AI Overviews için gerekli değildir; Ahrefs 137k-domain log analizi: dosyaların %97'sine istek gelmiyor). Ciro rakamı model kestirimidir, ölçüm değildir.</p>
      {_brand_line}
    </div>
  </div>
</body>
</html>
"""
