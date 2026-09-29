"""Rich CLI Interface for AnswRank."""

import os
import asyncio
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from answrank.audit.engine import AuditEngine
from answrank.citations.runner import MultiLLMCitationRunner, MODELS as _MODELS
from answrank.citations.questions import QUESTION_COUNT as _QC, SECTOR_QUESTIONS
from answrank.economics import PricingTier as _PricingTier

_SECTOR_CHOICES = sorted(SECTOR_QUESTIONS.keys())
_TIER_CHOICES = sorted(t.value for t in _PricingTier)
from answrank.reporting.generator import ReportGenerator
from answrank.reporting.fix_generator import FixGenerator
from answrank.db import Database

console = Console()

def run_audit_command(args):
    """Executes 'answrank audit <url>' command with optional --deep 360 mode."""
    engine = AuditEngine()
    rep_gen = ReportGenerator()
    db = Database()

    is_deep = getattr(args, "deep", False)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        if is_deep:
            progress.add_task(description=f"[cyan]{args.url} 360° Derin Denetimden (WAF, RAG, Adversarial, Entity) geçiriliyor...", total=None)
            deep_res = asyncio.run(engine.audit_url_deep(args.url, sector=args.sector, brand_name=getattr(args, "brand", None)))
            audit_res = deep_res.base_audit
        else:
            progress.add_task(description=f"[cyan]{args.url} taranıyor ve 8 kategoride analiz ediliyor...", total=None)
            audit_res = asyncio.run(engine.audit_url(args.url, sector=args.sector))
            deep_res = None
        asyncio.run(db.save_audit(audit_res))

    # Console display
    score_style = "bold green" if audit_res.overall_score >= 80 else ("bold yellow" if audit_res.overall_score >= 50 else "bold red")

    if audit_res.lost_revenue_estimate_monthly_try is not None:
        _lost_line = (f"[dim]Tahmini Aylık Kaçan Ciro:[/dim] [bold red]"
                      f"{audit_res.lost_revenue_estimate_monthly_try:,.0f} TL[/bold red]\n")
    else:
        _lost_line = ("[dim]Tahmini Aylık Kaçan Ciro:[/dim] [bold yellow]ÖLÇÜLEMEDİ "
                      "(denetim yapılamadı; sayı uydurulmaz)[/bold yellow]\n")
    console.print()
    console.print(
        Panel.fit(
            f"[bold white]{audit_res.domain}[/bold white] — AEO Görünürlük Skoru: [{score_style}]{audit_res.overall_score}/100[/{score_style}] ([italic]{audit_res.score_band}[/italic])\n"
            + _lost_line,
            title="[bold green]AnswRank Denetim Sonucu[/bold green]",
            border_style="green",
        )
    )

    # Category breakdown table
    table = Table(title="8 Puanlama Kategorisi Kırılımı", show_header=True, header_style="bold cyan")
    table.add_column("Kategori", style="white", width=30)
    table.add_column("Puan", justify="center", width=12)
    table.add_column("Maks", justify="center", width=8)
    table.add_column("Özet Durum", style="dim")

    cats = audit_res.categories
    cat_items = [
        ("Robots.txt AI Erişimi", cats.robots.score, 18, cats.robots.details[0] if cats.robots.details else ""),
        ("llms.txt Standartları", cats.llms_txt.score, 18, cats.llms_txt.details[0] if cats.llms_txt.details else ""),
        ("JSON-LD Semantik Şema", cats.schema_jsonld.score, 16, cats.schema_jsonld.details[0] if cats.schema_jsonld.details else ""),
        ("Meta & Başlık Mimarisi", cats.meta_architecture.score, 14, cats.meta_architecture.details[0] if cats.meta_architecture.details else ""),
        ("İçerik Alıntılanabilirliği", cats.citability_rag.score, 12, cats.citability_rag.details[0] if cats.citability_rag.details else ""),
        ("Marka Varlığı & KG", cats.entity_coherence.score, 10, cats.entity_coherence.details[0] if cats.entity_coherence.details else ""),
        ("Güven ve E-E-A-T", cats.trust_stack.score, 6, cats.trust_stack.details[0] if cats.trust_stack.details else ""),
        ("Manipülasyon Filtresi", cats.negative_signals.score, 6, cats.negative_signals.details[0] if cats.negative_signals.details else ""),
    ]

    for name, score, max_s, summary in cat_items:
        color = "green" if score >= (max_s * 0.75) else ("yellow" if score >= (max_s * 0.4) else "red")
        table.add_row(name, f"[{color}]{score}[/{color}]", str(max_s), summary)

    console.print(table)

    # If deep audit was run, display the 360° subsystems
    if deep_res:
        deep_style = "bold green" if deep_res.deep_tier == "ENTERPRISE_READY" else ("bold yellow" if deep_res.deep_tier == "STABLE" else "bold red")
        wp = deep_res.waf_probe
        if not wp:
            waf_status = "WAF: PROBE EDİLMEDİ"
        elif wp.get("overall_risk") == "UNVERIFIED" or wp.get("baseline_reachable") is False:
            waf_status = f"WAF: HÜKÜM VERİLEMEDİ ({wp.get('unreachable_bots_count', 0)}/{wp.get('total_probed', '?')} ağ hatası)"
        elif wp.get("blocked_bots_count", 0) > 0:
            waf_status = f"{wp.get('blocked_bots_count')} Bot Engelli!"
        else:
            waf_status = f"Temiz ({wp.get('accessible_bots_count', '?')}/{wp.get('total_probed', '?')} bot erişebiliyor)"
        adv_status = deep_res.adversarial.get("threat_level") if deep_res.adversarial else "TARANMADI"
        g = deep_res.entity_grounding or {}
        _conf = g.get("qid_confidence", "unknown")
        _qid = g.get("wikidata_qid") or "QID?"
        if g.get("wikidata_probe_status") == "unreachable":
            ent_status = "Wikidata: SORGULANAMADI"
        elif not g.get("has_wikidata"):
            ent_status = "Wikidata: KAYIT YOK"
        elif _conf == "verified":
            ent_status = f"Wikidata: {_qid} TEYİTLİ (P856 ✓)"
        elif _conf == "rejected":
            ent_status = f"Wikidata: {_qid} REDDEDİLDİ (resmî site çelişkisi)"
        elif _conf == "exact_name_no_conflict":
            ent_status = f"Wikidata: {_qid} birebir etiket (P856 yok)"
        elif _conf == "unverified":
            ent_status = f"Wikidata: {_qid} — resmî site teyidi eksik"
        else:
            ent_status = f"Wikidata: {_qid} (teyitsiz/eski kayıt)"
        rag_pct = deep_res.rag_analysis.get("rag_retrieval_score", 0) if deep_res.rag_analysis else 0

        console.print()
        console.print(
            Panel.fit(
                f"[bold]Kompozit 360° GEO Skoru:[/bold] [{deep_style}]{deep_res.composite_deep_score}/100[/{deep_style}] "
                f"([bold underline]{deep_res.deep_tier}[/bold underline])\n"
                f"• WAF Probu: [white]{waf_status}[/white]\n"
                f"• Adversarial Tehdit: [white]{adv_status}[/white]\n"
                f"• Entity Grounding: [white]{ent_status}[/white]\n"
                f"• RAG Hazırlığı: [white]%{rag_pct:.0f} Uygunluk[/white]",
                title="[bold magenta]360° Derin Kurumsal GEO Denetimi[/bold magenta]",
                border_style="magenta",
            )
        )

    # Export formats
    if args.format == "html":
        html_out = rep_gen.to_html(audit_res)
        out_path = args.out or f"report_{audit_res.domain.replace('.', '_')}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        console.print(f"[bold green]✓[/bold green] İnteraktif HTML rapor kaydedildi: [underline]{out_path}[/underline]")
    elif args.format == "md":
        md_out = rep_gen.to_markdown(audit_res)
        out_path = args.out or f"report_{audit_res.domain.replace('.', '_')}.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_out)
        console.print(f"[bold green]✓[/bold green] Markdown rapor kaydedildi: [underline]{out_path}[/underline]")
    elif args.format == "json":
        json_out = rep_gen.to_json(audit_res)
        out_path = args.out or f"report_{audit_res.domain.replace('.', '_')}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_out)
        console.print(f"[bold green]✓[/bold green] JSON rapor kaydedildi: [underline]{out_path}[/underline]")

def run_citations_command(args):
    """Executes 'answrank citations <brand> <domain>' command."""
    runner = MultiLLMCitationRunner()
    db = Database()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        is_live = getattr(args, "live", False)
        from answrank.citations.questions import get_sector_questions as _gq
        _nq = len(_gq(args.sector))
        progress.add_task(description=f"[cyan]{_nq} soru × {len(_MODELS)} LLM ({'Canlı API Modu' if is_live else f'{_nq * len(_MODELS)} Simüle Koşum'}) koşturuluyor...", total=None)
        res = asyncio.run(runner.run_citations(
            brand_name=args.brand,
            domain=args.domain,
            sector=args.sector,
            city=args.city,
            live=is_live,
            lang=args.lang,
            competitors=getattr(args, "competitors", None),
        ))
        asyncio.run(db.save_citations(res))

    console.print()
    _live_n = res.live_items_count
    _gs = res.grounding_status or {}
    if _gs:
        _gt = Table(title="Ölçüm Modalitesi (E10 — dürüst motor etiketi)")
        for _c in ("Motor", "Modalite", "Açıklama"):
            _gt.add_column(_c)
        _explain = {
            "search-grounded": "Gerçek canlı aramadan kaynaklanan atıflar",
            "model-recall": "Modelin hatırladığı linkler — CANLI ATIF ölçümü değildir",
            "anahtar yok": "API anahtarı yok — bu motor ölçülmedi",
        }
        for _m, _st in sorted(_gs.items()):
            _gt.add_row(_m, _st, _explain.get(_st, _st))
        console.print(_gt)
    _sim_n = res.total_runs - _live_n
    if _live_n == 0:
        _validity = "[bold red on white]⚠ TAM SİMÜLASYON — API anahtarı yok; oran model çıktısıdır, gerçek ölçüm değildir[/bold red on white]"
    elif _sim_n:
        _validity = f"[bold yellow]Canlılık: {_live_n}/{res.total_runs} canlı API — kalanı simülasyon; SoV-iddiası yalnızca canlı alt-küme için kurulabilir[/bold yellow]"
    else:
        _validity = f"[bold green]Tamamı canlı API ölçümü: {_live_n}/{res.total_runs}[/bold green]"
    console.print(
        Panel.fit(
            f"[bold white]{args.brand}[/bold white] — Alıntı Payı (Citation Share): [bold cyan]%{res.citation_rate_percentage:g}[/bold cyan] "
            f"({res.brand_citations_found}/{res.total_runs} soru×motor) · [dim]{len(_MODELS)} motor[/dim]\n"
            f"{_validity}\n"
            f"[dim]En Çok Çıkan Rakipler:[/dim] {', '.join(list(res.top_competitors.keys())[:3]) or '—'}",
            title="[bold blue]Çoklu-LLM Atıf Testi Sonucu[/bold blue]",
            border_style="blue",
        )
    )

def run_fix_command(args):
    """Executes 'answrank fix <domain>' command."""
    gen = FixGenerator()
    out_dir = args.out_dir or "./answrank_fixes"
    os.makedirs(out_dir, exist_ok=True)

    robots = gen.generate_robots_txt(args.domain)
    llms = gen.generate_llms_txt(args.brand or args.domain, args.domain, sector=args.sector, city=args.city)
    llms_full = gen.generate_llms_full_txt(args.brand or args.domain, args.domain, sector=args.sector, city=args.city)
    schema = gen.generate_json_ld(args.brand or args.domain, args.domain, sector=args.sector, city=args.city)

    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots)
    with open(os.path.join(out_dir, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(llms)
    with open(os.path.join(out_dir, "llms-full.txt"), "w", encoding="utf-8") as f:
        f.write(llms_full)
    with open(os.path.join(out_dir, "schema.html"), "w", encoding="utf-8") as f:
        f.write(schema)

    console.print(f"[bold green]✓[/bold green] Hazır AEO düzeltme paketleri [bold]{out_dir}/[/bold] dizinine yazıldı:")
    from answrank.config import settings as _st
    from answrank.reporting.fix_generator import FixGenerator as _FG
    _n_open = _st.ai_bots_total - len(_FG.BLOCKED_BY_DEFAULT)
    console.print(f"  • {out_dir}/robots.txt ({_n_open} AI botuna açık, {len(_FG.BLOCKED_BY_DEFAULT)} kazıyıcı engelli)")
    console.print(f"  • {out_dir}/llms.txt (Standart bilgi dizini)")
    console.print(f"  • {out_dir}/llms-full.txt (Derin klinik/kurumsal bilgi bankası)")
    console.print(f"  • {out_dir}/schema.html (JSON-LD + FAQPage şeması)")


def run_sitemap_command(args):
    """Executes 'answrank sitemap <url>' command."""
    from answrank.audit.sitemap import SitemapAuditor
    auditor = SitemapAuditor()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"[cyan]{args.url} site haritası taranıyor ve sayfalar denetleniyor...", total=None)
        results = asyncio.run(auditor.batch_audit(args.url, sector=args.sector, max_urls=args.max_urls))

    table = Table(title=f"Site Haritası Denetimi (En Zayıf Sayfalar Önce) — {len(results)} Sayfa", show_header=True, header_style="bold cyan")
    table.add_column("URL", style="white")
    table.add_column("Skor", justify="center", width=10)
    table.add_column("Düzey", justify="center", width=14)

    for r in results:
        color = "green" if r.overall_score >= 80 else ("yellow" if r.overall_score >= 50 else "red")
        table.add_row(r.url, f"[{color}]{r.overall_score}/100[/{color}]", r.score_band)
    console.print(table)

def run_delta_command(args):
    """Executes 'answrank delta <domain>' command."""
    from answrank.audit.delta import DeltaEngine
    from answrank.audit.engine import AuditEngine
    from answrank.audit.crawler import CrawlData

    engine = AuditEngine()
    delta_engine = DeltaEngine()

    crawl1 = CrawlData(url=f"https://{args.domain}", domain=args.domain, html_content="", status_code=200, headers={})
    audit_base = engine.audit_crawl_data(crawl1)
    audit_base.overall_score = args.baseline

    audit_curr = engine.audit_crawl_data(crawl1)
    audit_curr.overall_score = args.current

    d_log = delta_engine.calculate_delta(audit_base, audit_curr, prospect_id=args.domain, days_elapsed=args.days)
    asyncio.run(delta_engine.record_delta(d_log))

    status_str = "[bold green]BAŞARILI (GÜVENCE TUTTU)[/bold green]" if d_log.is_guarantee_met else "[bold red]GÜVENCE SAĞLANAMADI (Ücretsiz Ay Tetiği)[/bold red]"

    console.print(
        Panel.fit(
            f"İşletme: [bold white]{args.domain}[/bold white]\n"
            f"Temel Skor: {d_log.baseline_score}/100 → Güncel Skor: {d_log.current_score}/100\n"
            f"Net Delta: [bold cyan]+{d_log.score_delta} Puan[/bold cyan] (%{d_log.percentage_change})\n"
            f"Sözleşmeli Güvence Durumu: {status_str}",
            title="[bold green]Madde 7.3 Performans Güvencesi Hesabı[/bold green] (girdi: kullanıcı-bildirimi skorlar; otomatik ölçüm değildir)",
            border_style="green",
        )
    )

def _leads_via_db(crm):
    """crm sinkron lead erişimi (Database sahipli)."""
    from answrank.db import Database
    return Database().list_miniprobe_leads()


def run_crm_command(args):
    """Executes 'answrank crm' command."""
    from answrank.crm.sync import CRMSync
    from answrank.crm.outreach import OutreachGenerator
    from answrank.audit.engine import AuditEngine

    crm = CRMSync()
    if args.crm_action == "sync":
        cnt = asyncio.run(crm.import_csv_to_db())
        console.print(f"[bold green]✓[/bold green] {cnt} potansiyel müşteri takip_tablosu.csv dosyasından veritabanına aktarıldı.")
    elif args.crm_action == "list":
        leads = asyncio.run(crm.list_prospects())
        table = Table(title=f"Aday Takip Tablosu ({len(leads)} Kayıt)", show_header=True)
        table.add_column("ID")
        table.add_column("İşletme Adı", style="bold white")
        table.add_column("Sektör")
        table.add_column("Platform")
        table.add_column("Durum", style="cyan")
        for l in leads:
            table.add_row(l["id"], l["brand_name"], l["sector"], l["platform"] or "", l["status"])
        console.print(table)
    elif args.crm_action == "leads":
        rows = _leads_via_db(crm)
        if not rows:
            console.print("[yellow]Mini-probe lead'i yok — huni boş, liste uydurulmaz.[/yellow]")
            return
        for r in rows:
            console.print(f"{r['created_at'][:16]}  {r['domain']:<34} {r['verdict']:<22} {r['bots_line']}")
    elif args.crm_action == "draft":
        if args.from_lead:
            from answrank.db import Database as _DB
            lead = _DB().latest_measured_lead(args.from_lead)
            if not lead:
                console.print("[bold red]✗ Bu domain için ÖLÇÜMLÜ mini-probe lead'i yok — "
                              "yeniden ölçmeyen DM de uydurulmaz; önce halka-açık probe koşmalı.[/bold red]")
                return
            # E12: bu domain için gerçek çoklu-LLM görünürlük ölçümü varsa
            # DM'e kanıt olarak eklenir; yoksa uydurulmaz (opsiyonel bayrak).
            vis = None
            if getattr(args, "with_visibility", False):
                from answrank.citations.runner import MultiLLMCitationRunner as _R
                vis = _R(db=_DB()).visibility_for(lead["domain"])
                if vis is None:
                    console.print("[bold red]Geçerli son AI-görünürlük kanıtı yok — "
                                  "taslak üretilmedi. Önce geçerli ölçüm gerekir.[/bold red]")
                    return
            dm = OutreachGenerator.lead_dm(lead["domain"], lead["robots_line"],
                                           lead["llms_line"], lead["bots_line"],
                                           lead["verdict"], ai_visibility=vis)
            console.print(Panel(dm, title=f"[bold]E7 Lead DM'i — {lead['domain']}[/bold]"))
            return
        engine = AuditEngine()
        outreach = OutreachGenerator()
        # Real audit against the live domain — synthetic placeholder HTML must never
        # score a prospect (16 Eyl derin-tarama C3). Citation stats only if the DB
        # actually holds a measured run for the domain.
        try:
            audit_res = asyncio.run(engine.audit_url(f"https://{args.domain}", sector=args.sector))
        except Exception as exc:
            console.print(f"[bold red]✗ Alan adı denetlenemedi ({exc})[/bold red] — "
                          "ölçülemeyen müşteriye taslak DM üretilmez.")
            return
        from answrank.db import Database
        citation = asyncio.run(Database().get_latest_citations_for_domain(args.domain))
        variants = outreach.generate_all_variants(audit_res, contact_name=args.contact, citation=citation)

        stamp = "[dim]TASLAK — gönderim öncesi insan onayı zorunlu; tüm sayılar denetim/alıntı kaydından gelir[/dim]"
        console.print(Panel(variants["variant_1_pain_numbers"], title=f"[bold green]Varyant 1: Teknik Tespit[/bold green] {stamp}"))
        console.print(Panel(variants["variant_2_lost_revenue"], title="[bold yellow]Varyant 2: Gelir Modeli + Görünürlük[/bold yellow]"))
        console.print(Panel(variants["variant_3_case_study"], title="[bold blue]Varyant 3: Denetim Durumu[/bold blue]"))

    elif args.crm_action == "send":
        # Onaylı kuyruk maddesini kontrol et — onaysız gönderim olmaz
        from answrank.db import Database as _DB
        db = _DB()
        row = None
        try:
            with db._get_connection() as conn:
                row = conn.execute(
                    "SELECT id FROM approval_queue WHERE status='APPROVED' AND kind='DM' AND ref_id LIKE ?",
                    (f"%{args.domain}%",)).fetchone()
        except Exception:
            pass
        if not row:
            console.print(f"[bold red]✗ {args.domain} için APPROVED kuyruk maddesi YOK — "
                          "onaysız DM gönderilmez. Önce: answrank queue scan + approve[/bold red]")
            return
        from answrank.crm.dm_sender import DMSender
        s = DMSender()
        govde = args.body or (f"Merhaba Klinik Ekibi, {args.domain} için AI görünürlük "
                              "tespiti hazırladım — ücretsiz raporu iletebilirim.")
        res = s.send(queue_id=row[0], domain=args.domain, subject=args.subject,
                     body=govde, variant_key=args.variant)
        renk = {"GÖNDERİLDİ": "bold green", "YAPILANDIRILMAMIŞ": "bold yellow",
                "HEDEF_YOK": "bold red", "HATA": "bold red", "TEKRAR": "dim"}[res.status]
        console.print(f"[{renk}]{res.status}[/{renk}] {res.domain} → {res.note}")

    elif args.crm_action == "followups":
        from answrank.crm.dm_sender import DMSender
        s = DMSender()
        due = s.followups_due()
        if not due:
            console.print("[dim]Vadesi gelen takip yok (3/7 gün geçen gönderim yok) — uydurulmaz.[/dim]")
            return
        console.print(f"[bold]{len(due)} vadesi-gelen takip:[/bold]")
        for f in due:
            console.print(f"  {f['domain']:<26} {f['gun']}. gün ({f['key']})")
        sonuclar = s.generate_followups()
        hazir = sum(1 for r in sonuclar if r.status == "YAPILANDIRILMAMIŞ")
        console.print(f"[bold green]✓ {hazir} takip .eml olarak hazır (outbox/)[/bold green]")

    elif args.crm_action == "outbox":
        from answrank.crm.dm_sender import OUTBOX_DIR
        dosyalar = sorted(OUTBOX_DIR.glob("*.eml"))
        if not dosyalar:
            console.print("[dim]outbox/ boş — hazırlanmış .eml yok.[/dim]")
            return
        console.print(f"[bold]outbox/ — {len(dosyalar)} hazır .eml:[/bold]")
        for d in dosyalar:
            console.print(f"  {d.name}")

def run_qualify_command(args):
    """Executes 'answrank qualify' command."""
    from answrank.crm.qualifier import CandidateQualifier, CandidateProfile
    candidate = CandidateProfile(
        company_name=args.company,
        sector=args.sector,
        domain=args.domain,
        has_custom_domain=bool(args.domain and not args.domain.endswith("instagram.com")),
        estimated_ticket_size=args.ticket,
        estimated_annual_revenue=args.revenue,
        has_ad_spend=args.has_ads,
        direct_decision_maker_access=args.dm_access,
        ai_missing_in_top5=args.missing_ai,
        has_competitor_cited=args.competitor_cited,
    )
    res = CandidateQualifier.qualify_candidate(candidate)
    status_style = "bold green" if res.is_qualified else "bold red"
    verdict = "UYGUN (QUALIFIED)" if res.is_qualified else "ELENDİ (DISQUALIFIED)"

    console.print()
    console.print(Panel(f"Aday: [bold white]{args.company}[/bold white] | Skor: [{status_style}]{res.score}/5 - {verdict}[/{status_style}]\n\n"
                        f"[dim]{res.reason}[/dim]",
                        title="[bold cyan]AnswRank 5-Adımlı Aday Eleme Filtresi (Bölüm 6.1)[/bold cyan]"))

    table = Table(title="Kriter Değerlendirme Listesi", show_header=True, header_style="bold cyan")
    table.add_column("Durum", justify="center", width=8)
    table.add_column("Kriter Tanımı", style="white")

    for p in res.passed_criteria:
        table.add_row("[bold green]GEÇTİ[/bold green]", p)
    for f in res.failed_criteria:
        table.add_row("[bold red]KALDI[/bold red]", f)
    console.print(table)

def run_objections_command(args):
    """Executes 'answrank objections' command."""
    from answrank.crm.objection import ObjectionHandler
    res = ObjectionHandler.generate_rebuttal(
        text=args.text,
        company_name=args.company,
        sector=args.sector,
        competitor_name=args.competitor,
    )
    console.print()
    console.print(Panel(f"[bold yellow]Müşteri İtirazı:[/bold yellow] \"{args.text}\"\n"
                        f"[dim]Tespit Edilen Kategori:[/dim] [bold cyan]{res.matched_code}[/bold cyan] "
                        f"(Güven: %{res.confidence * 100:.0f})\n\n"
                        f"[bold green]Önerilen Karşı Yanıt (Rebuttal):[/bold green]\n{res.rebuttal_text}",
                        title="[bold green]AnswRank İtiraz Karşılama Motoru (Bölüm 6.3)[/bold green]"))

    table = Table(title="Önemli Konuşma Maddeleri (Talking Points)", show_header=False)
    table.add_column("Madde", style="white")
    for pt in res.recommended_talking_points:
        table.add_row(f"• {pt}")
    console.print(table)

def run_contract_command(args):
    """Executes 'answrank contract' command."""
    from answrank.legal.contract_generator import ContractGenerator, ClientLegalDetails, ContractMetadata
    from answrank.economics import PricingTier

    tier_enum = PricingTier(args.tier)
    client = ClientLegalDetails(
        client_name=args.contact,
        company_title=args.company,
        tax_number=args.tax_no,
        tax_office=args.tax_office,
        address=args.address,
        authorized_person=args.contact,
        email=args.email,
        phone=args.phone,
        domain=args.domain,
        sector=args.sector,
    )
    meta = ContractMetadata(
        contract_number=args.contract_no,
        service_tier=tier_enum,
        monthly_fee_try=args.fee,
        start_date=args.date,
        duration_months=args.months,
    )
    res = ContractGenerator.generate_contract(client, meta)
    out_file = args.out or f"sozlesme_{args.domain.replace('.', '_')}.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(res.contract_text)

    console.print(f"[bold green]✓[/bold green] Madde 7 Performans Güvenceli Hizmet Sözleşmesi üretildi: [underline]{out_file}[/underline]")
    console.print(Panel(res.madde_7_guarantee_text, title="[bold yellow]Madde 7: Performans ve Delta Güvencesi Protokolü[/bold yellow]"))

def run_economics_command(args):
    """Executes 'answrank economics' command."""
    from answrank.economics import EconomicsEngine, PricingTier
    tier_enum = PricingTier(args.tier)
    metrics = EconomicsEngine.evaluate_unit_economics(tier_enum, custom_cac_try=args.cac, retention_months=args.retention)
    proj = EconomicsEngine.project_portfolio(client_count=args.clients, primary_tier=tier_enum)

    console.print()
    table = Table(title=f"Birim Ekonomisi ve Fiyatlandırma ({tier_enum.value})", show_header=True, header_style="bold cyan")
    table.add_column("Metrik", style="white")
    table.add_column("Değer", justify="right", style="bold green")

    table.add_row("Paket Satış Fiyatı", f"₺{metrics.price_try:,.2f}")
    table.add_row("Marjinal Maliyet (COGS)", f"₺{metrics.cogs_try:,.2f}")
    table.add_row("Brüt Kar / İşlem", f"₺{metrics.gross_profit_try:,.2f}")
    table.add_row("Brüt Kar Marjı", f"%{metrics.gross_margin_pct:.1f}")
    table.add_row("Müşteri Edinme Maliyeti (CAC)", f"₺{metrics.estimated_cac_try:,.2f}")
    table.add_row("Ortalama Kalış Süresi", f"{metrics.average_retention_months:.1f} Ay")
    table.add_row("Müşteri Yaşam Boyu Değeri (LTV)", f"₺{metrics.ltv_try:,.2f}")
    table.add_row("LTV / CAC Oranı", f"{metrics.ltv_to_cac_ratio:.1f}x")
    console.print(table)

    proj_table = Table(title=f"Portföy Gelir Projeksiyonu ({args.clients} Müşteri)", show_header=True, header_style="bold cyan")
    proj_table.add_column("Metrik", style="white")
    proj_table.add_column("Tutar", justify="right", style="bold yellow")
    proj_table.add_row("Aylık Tekrarlayan Gelir (MRR)", f"₺{proj.mrr_try:,.2f}")
    proj_table.add_row("Yıllıklandırılmış Gelir (ARR)", f"₺{proj.arr_try:,.2f}")
    proj_table.add_row("Aylık Toplam COGS", f"₺{proj.monthly_cogs_try:,.2f}")
    proj_table.add_row("Aylık Net Brüt Kar", f"₺{proj.monthly_gross_profit_try:,.2f}")
    console.print(proj_table)

def run_scenarios_command(args):
    """Executes 'answrank scenarios' command."""
    from answrank.audit.scenarios import ScenarioRouter
    res = ScenarioRouter.evaluate(
        baseline_score=args.baseline,
        current_score=args.current,
        baseline_citations=args.baseline_cit,
        current_citations=args.current_cit,
        client_cooperation_ok=not args.inaction,
    )
    color = "green" if res.scenario == "S1_SUCCESS" else ("yellow" if res.scenario == "S2_PARTIAL_SUCCESS" else "red")
    console.print()
    console.print(Panel(f"Karar: [{color}]{res.name}[/{color}]\n\n"
                        f"[bold]Açıklama:[/bold] {res.description}\n"
                        f"[bold]Hedef Aksiyon:[/bold] {res.target_action}\n"
                        f"[bold]Madde 7.3 Ücretsiz Ay:[/bold] {'EVET (Aktif)' if res.trigger_free_month else 'HAYIR'}",
                        title="[bold cyan]AnswRank Gün 30/60 Operasyonel Karar Ağacı (EK G)[/bold cyan]"))

    table = Table(title="Uygulanacak Eylem Adımları (Playbook)", show_header=False)
    table.add_column("Adım", style="white")
    for step in res.recommended_playbook:
        table.add_row(f"• {step}")
    console.print(table)

def run_milestones_command(args):
    """Executes 'answrank milestones' command."""
    from answrank.crm.milestones import MilestonesEngine
    res = MilestonesEngine.evaluate_progress(
        current_day=args.day,
        active_clients=args.clients,
        current_mrr_try=args.mrr,
    )
    console.print()
    console.print(Panel(f"[bold cyan]Durum:[/bold cyan] {res.status_summary}\n"
                        f"[bold yellow]Aktif Faz:[/bold yellow] {res.active_phase_details.name} ({res.active_phase_details.day_range})\n"
                        f"[bold green]Faz KPI Hedefi:[/bold green] {res.active_phase_details.target_kpi}",
                        title="[bold green]AnswRank 90 Günlük Eylem Planı ve KPI Takibi (Bölüm 11)[/bold green]"))

    table = Table(title="Aktif Faz Görevleri", show_header=False)
    table.add_column("Görev", style="white")
    for t in res.active_phase_details.tasks:
        table.add_row(f"✓ {t}")
    console.print(table)

def run_probe_waf_command(args):
    """Executes 'answrank probe-waf <url>' command."""
    from answrank.audit.waf_probe import WAFProbeEngine, WAFRiskLevel
    roster_n = len(WAFProbeEngine.AI_CRAWLER_USER_AGENTS)
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description=f"[cyan]{args.url} {roster_n} AI Bot User-Agent başlığı + tarayıcı baseline'ı ile taranıyor...", total=None)
        res = asyncio.run(WAFProbeEngine.probe_url(args.url))

    if res.overall_risk == WAFRiskLevel.LOW:
        risk_style = "bold green"
    elif res.overall_risk == WAFRiskLevel.MEDIUM:
        risk_style = "bold yellow"
    elif res.overall_risk == WAFRiskLevel.UNVERIFIED:
        risk_style = "bright_black"
    else:
        risk_style = "bold red"
    total_n = res.total_probed or roster_n
    console.print()
    console.print(Panel(f"Hedef: [bold white]{res.target_url}[/bold white] | WAF Blokaj Riski: [{risk_style}]{res.overall_risk.value}[/{risk_style}]\n"
                        f"Erişilebilir Botlar: [bold green]{res.accessible_bots_count}/{total_n}[/bold green] | Engellenen: [bold red]{res.blocked_bots_count}/{total_n}[/bold red] | Ağ hatası: [bright_black]{res.unreachable_bots_count}/{total_n}[/bright_black]\n\n"
                        f"[dim]{res.remediation_recommendation}[/dim]",
                        title="[bold red]AnswRank WAF & Sessiz Bot Blokajı Sondası (Silent Blocking Probe)[/bold red]"))

    table = Table(title="AI Bot Ağ Katmanı Erişim Durumu", show_header=True, header_style="bold cyan")
    table.add_column("AI Bot Adı", style="white")
    table.add_column("HTTP Kodu", justify="center", width=10)
    table.add_column("Durum", justify="center", width=14)
    table.add_column("Yanıt Süresi", justify="right", width=12)
    table.add_column("Açıklama / İhlal İmzası", style="dim")

    for s in res.bot_statuses:
        if s.is_accessible:
            status_txt = "[bold green]ERİŞİLEBİLİR[/bold green]"
        elif s.status_code == 0 and res.overall_risk == WAFRiskLevel.UNVERIFIED:
            status_txt = "[bright_black]ULAŞILAMADI[/bright_black]"
        else:
            status_txt = "[bold red]ENGELLENDİ[/bold red]"
        table.add_row(s.bot_name, str(s.status_code), status_txt, f"{s.response_time_ms} ms", s.blocking_signature or "Temiz (200 OK)")
    console.print(table)

def run_rag_command(args):
    """Executes 'answrank rag <url>' command."""
    from answrank.audit.crawler import WebCrawler
    from answrank.audit.rag_engine import RAGEngine
    from answrank.citations.questions import SectorQuestionsBank

    crawler = WebCrawler()
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description=f"[cyan]{args.url} indiriliyor ve semantik RAG chunk analizi yapılıyor...", total=None)
        crawl = asyncio.run(crawler.fetch(args.url))
        questions = SectorQuestionsBank.get_questions(args.sector, city=args.city)
        res = RAGEngine.evaluate_content_rag(args.url, crawl.html_content, questions)

    score_style = "bold green" if res.rag_retrieval_score >= 75 else ("bold yellow" if res.rag_retrieval_score >= 50 else "bold red")
    console.print()
    console.print(Panel(f"Hedef URL: [bold white]{res.url}[/bold white]\n"
                        f"RAG Top-K Çekilme Skoru: [{score_style}]{res.rag_retrieval_score}/100[/{score_style}] | "
                        f"Kabul Oranı: [bold cyan]%{res.retrieval_pass_rate_pct}[/bold cyan] | "
                        f"Çıkarılan Anlamsal Parça (Chunk): [bold]{res.total_chunks_extracted}[/bold]\n\n"
                        f"[dim]{res.remedy_advice}[/dim]",
                        title="[bold green]AnswRank AutoGEO / Dinamik RAG Vektör Benzerlik Analizi[/bold green]"))

    table = Table(title="Sektörel Soru Semantik Yakınlık Eşleşmesi (Örnek İlk 8 Soru)", show_header=True, header_style="bold cyan")
    table.add_column("Soru", style="white", width=38)
    table.add_column("Benzerlik", justify="center", width=12)
    table.add_column("RAG Durumu", justify="center", width=14)
    table.add_column("Eşleşen Parça Önizlemesi", style="dim")

    for m in res.matches[:8]:
        st = "[bold green]TOP-K İÇİNDE[/bold green]" if m.will_be_retrieved_in_top_k else "[bold red]ELENDİ[/bold red]"
        sim_color = "green" if m.similarity_score >= 0.55 else ("yellow" if m.similarity_score >= 0.40 else "red")
        table.add_row(m.question, f"[{sim_color}]{m.similarity_score:.3f}[/{sim_color}]", st, m.best_chunk_preview[:60] + "...")
    console.print(table)

def run_monte_carlo_command(args):
    """Executes 'answrank monte-carlo <brand> <domain>' command."""
    from answrank.citations.monte_carlo import MonteCarloEngine
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description=f"[cyan]{args.brand} için {args.iterations} stokastik Monte Carlo koşumu icra ediliyor...", total=None)
        res = asyncio.run(MonteCarloEngine.evaluate_stochastic_stability(
            brand_name=args.brand,
            domain=args.domain,
            sector=args.sector,
            city=args.city,
            iterations=args.iterations,
        ))

    grade_style = "bold green" if res.stability_grade in ["ROCK_SOLID", "STABLE"] else ("bold yellow" if res.stability_grade == "SIMULATION_MODE" else "bold red")
    validity_line = ""
    if not res.is_statistically_valid:
        validity_line = "\n[bold red on white]⚠ SİMÜLASYON MODU — istatistiksel olarak geçersiz (API anahtarı yok)[/bold red on white]"
    console.print()
    console.print(Panel(f"Marka: [bold white]{res.brand_name}[/bold white] ({res.domain})\n"
                        f"Ölçüm Modu: [bold cyan]{res.measurement_mode}[/bold cyan]\n"
                        f"Ortalama Atıf Oranı: [bold green]%{res.mean_citation_rate_pct}[/bold green] | "
                        f"Güven Aralığı (CI 95): [bold cyan]{res.confidence_interval_95_str}[/bold cyan]\n"
                        f"Atıf Kararlılık Endeksi: [{grade_style}]{res.stability_index}/100 ({res.stability_grade})[/{grade_style}]{validity_line}\n\n"
                        f"[dim]{res.summary_report}[/dim]",
                        title="[bold yellow]AnswRank Monte Carlo Stokastik Atıf Kararlılık Endeksi[/bold yellow]"))

    table = Table(title=f"İterasyon Bazlı Dağılım ({res.iterations_count} Koşum)", show_header=True, header_style="bold cyan")
    table.add_column("İterasyon", justify="center", width=12)
    table.add_column("Atıf Oranı (%)", justify="center", width=15)
    table.add_column("Atıf Sayısı", justify="center", width=15)
    table.add_column("Sıcaklık", justify="center", width=10)
    table.add_column("Canlı Yanıt", justify="center", width=12)
    for it in res.iterations:
        table.add_row(f"Koşum #{it.iteration_index}", f"%{it.citation_rate_pct:.1f}", f"{it.citations_count}/{it.total_runs}", f"{it.temperature}", f"{it.live_items}/{it.total_runs}")
    console.print(table)

def run_ground_command(args):
    """Executes 'answrank ground <brand> <domain>' command."""
    from answrank.audit.crawler import WebCrawler
    from answrank.audit.entity_grounding import EntityGroundingEngine
    crawler = WebCrawler()
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description=f"[cyan]Wikidata API ve Google Knowledge Graph üzerinde {args.brand} sorgulanıyor...", total=None)
        crawl = asyncio.run(crawler.fetch(args.domain))
        res = asyncio.run(EntityGroundingEngine.evaluate_grounding(args.brand, args.domain, html_content=crawl.html_content))

    score_style = "bold green" if res.grounding_score >= 70 else ("bold yellow" if res.grounding_score >= 40 else "bold red")
    console.print()
    console.print(Panel(f"Marka: [bold white]{res.brand_name}[/bold white] | Varlık Statüsü: [{score_style}]{res.tier.value} ({res.grounding_score}/100)[/{score_style}]\n"
                        f"Wikidata Kaydı: [bold cyan]{res.wikidata_qid or 'YOK'}[/bold cyan] "
                        f"({res.wikidata_description or 'Tanımsız'})\n"
                        f"Google Maps CID: {'[bold green]VAR[/bold green]' if res.has_google_maps_cid else '[bold red]YOK[/bold red]'} | "
                        f"LinkedIn Şirket Varlığı: {'[bold green]VAR[/bold green]' if res.has_linkedin_entity else '[bold red]YOK[/bold red]'}",
                        title="[bold magenta]AnswRank Google Knowledge Graph & Wikidata Varlık Doğrulaması[/bold magenta]"))

    table = Table(title="Uygulanacak Bilgi Grafiği Yol Haritası", show_header=False)
    table.add_column("Eylem", style="white")
    for act in res.action_roadmap:
        table.add_row(f"• {act}")
    console.print(table)

def run_adversarial_command(args):
    """Executes 'answrank adversarial <url>' command."""
    from answrank.audit.crawler import WebCrawler
    from answrank.audit.adversarial import AdversarialAnalyzer
    from bs4 import BeautifulSoup
    crawler = WebCrawler()
    analyzer = AdversarialAnalyzer()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"[cyan]{args.url} dolaylı prompt enjeksiyonu ve gizli CSS için taranıyor...", total=None)
        crawl_data = asyncio.run(crawler.fetch(args.url))
        soup = BeautifulSoup(crawl_data.html_content, "html.parser")
        res = analyzer.analyze(soup, raw_html=crawl_data.html_content)

    badge_color = "green" if res.is_clean else ("yellow" if res.threat_level in ("LOW", "MEDIUM") else "red")
    console.print()
    console.print(
        Panel.fit(
            f"Hedef: [bold white]{crawl_data.domain}[/bold white] | Risk Skoru: [{badge_color}]{res.risk_score}/100[/{badge_color}]\n"
            f"Tehdit Seviyesi: [{badge_color} bold]{res.threat_level}[/{badge_color} bold] | "
            f"Gizli Öğeler: {res.cloaked_elements_count} | Görünmez Karakterler: {res.invisible_unicode_count}",
            title="[bold magenta]Dolaylı Prompt Enjeksiyonu ve Adversarial Savunma Taraması[/bold magenta]",
            border_style=badge_color,
        )
    )
    if res.threats:
        table = Table(title="Tespit Edilen Güvenlik Tehditleri", show_header=True)
        table.add_column("Tip", style="bold")
        table.add_column("Önem", justify="center")
        table.add_column("Açıklama")
        table.add_column("Kod Kesiti", style="dim")
        for t in res.threats:
            s_color = "red" if t.severity == "CRITICAL" else ("yellow" if t.severity in ("HIGH", "MEDIUM") else "white")
            table.add_row(t.threat_type, f"[{s_color}]{t.severity}[/{s_color}]", t.description, t.snippet[:60])
        console.print(table)
    else:
        console.print("[bold green]✓ Tebrikler: Sayfada hiçbir adversarial manipülasyon veya gizlenmiş metin tespit edilmedi.[/bold green]")

def run_swarm_command(args):
    """Executes 'answrank swarm' to run the 5-agent closed loop pipeline."""
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()
    cand = orch.seed_target(
        brand_name=args.brand,
        domain=args.domain,
        sector=args.sector,
        city=args.city,
        country=args.country,
        currency=args.currency,
        ticket_size=args.ticket,
        agency_domain=args.agency,
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"[cyan]5 Ajanlı Sürü devrede: {cand.brand_name} ({cand.city}, {cand.country}) taranıyor...", total=None)
        res = asyncio.run(orch.run_full_pipeline_sync(cand))

    console.print()
    lost_rev_display = (
        f"{res.currency} {res.lost_revenue_monthly:,.0f}/ay"
        if res.lost_revenue_monthly is not None
        else "Hesaplanmadı"
    )
    console.print(
        Panel.fit(
            f"Hedef: [bold white]{res.brand_name}[/bold white] ({res.city}, {res.country})\n"
            f"Durum: [bold green]{res.stage.value}[/bold green] | 360° Skor: [bold cyan]{res.deep_score or 0}/100[/bold cyan]\n"
            f"Tahmini Kaçan Ciro: [bold red]{lost_rev_display}[/bold red]\n"
            f"Son Ajan Eylemi: [italic]{res.last_action or '—'}[/italic]",
            title="[bold magenta]AnswRank 5-Ajanlı Kapalı Döngü Sürü İcrası[/bold magenta]",
            border_style="magenta",
        )
    )
    if res.outreach_pitch:
        console.print(Panel(res.outreach_pitch, title="[bold yellow]Agent 03 (Hunter) Hazırlanan Soğuk Temas Metni[/bold yellow]"))
    if res.fixes_generated:
        console.print(f"[bold green]✓ Agent 04 (Maker):[/bold green] {len(res.fixes_generated)} adet üretim hazırlandı (robots.txt, llms.txt, llms-full.txt, schema.jsonld)")
    if res.territory_locked:
        console.print(f"[bold cyan]🔒 Bölge Münhasırlığı:[/bold cyan] {res.city}, {res.country} ({res.sector}) kilitlendi. Yamyamlaşma engellendi.")
    if res.fiscal_invoice_id:
        console.print(f"[bold yellow]💰 Mali Defter:[/bold yellow] Fatura {res.fiscal_invoice_id} işlendi (%80 KVK 10/1-ğ İstisnası: TRY {res.fiscal_tax_exempt_try:,.0f}).")

def run_sentiment_command(args):
    """Executes 'answrank sentiment <brand>' command."""
    from answrank.citations.sentiment import SentimentAnalyzer, SentimentPolarity
    analyzer = SentimentAnalyzer()
    res = analyzer.analyze(raw_response=args.text, brand_name=args.brand, sector=args.sector)
    color = "bold green" if res.polarity == SentimentPolarity.POSITIVE_RECOMMENDATION else ("bold yellow" if res.polarity == SentimentPolarity.NEUTRAL_MENTION else "bold red")
    console.print()
    console.print(
        Panel(
            f"Marka: [bold white]{args.brand}[/bold white] | Sektör: [cyan]{args.sector}[/cyan]\n"
            f"Duyarlılık Polaritesi: [{color}]{res.polarity.value}[/{color}]\n"
            f"Duyarlılık Skoru: [bold]{res.sentiment_score:+0.2f}[/bold] (-1.0 ile +1.0)\n"
            f"Marka Güvenliği: [{'green' if res.is_brand_safe else 'bold red'}]{'GÜVENLİ' if res.is_brand_safe else 'RİSKLİ'}[/]\n"
            f"Kırmızı Bayraklar: {', '.join([f.value for f in res.detected_flags]) if res.detected_flags else 'YOK'}\n\n"
            f"[dim]Bağlam:[/dim] {res.context_snippet}\n"
            + (f"\n[bold red]Acil Karşı-Atıf Stratejisi:[/bold red]\n{res.counter_citation_strategy}" if res.counter_citation_strategy else ""),
            title="[bold cyan]AnswRank Zero-Click Citation Sentiment & Brand Safety[/bold cyan]",
        )
    )

def run_deploy_command(args):
    """Executes 'answrank deploy' command."""
    from answrank.integrations.deployer import CMSDeployer
    from answrank.reporting.fix_generator import FixGenerator
    fix_gen = FixGenerator()
    fixes = {
        "robots.txt": fix_gen.generate_robots_txt(args.domain),
        "llms.txt": fix_gen.generate_llms_txt(args.brand, args.domain, sector=args.sector, city=args.city),
        "schema.jsonld": fix_gen.generate_json_ld(args.brand, args.domain, sector=args.sector, city=args.city),
    }
    if args.target == "local":
        out_dir = args.out or "./dist_aeo"
        res = CMSDeployer.export_local_bundle(out_dir, fixes)
        console.print(f"[bold green]✓[/bold green] {res.message}")
    elif args.target == "webhook":
        if not args.webhook_url or not args.secret:
            console.print("[bold red]Hata:[/bold red] Webhook hedefi için --webhook-url ve --secret zorunludur.")
            return
        res = asyncio.run(CMSDeployer.deploy_webhook(args.webhook_url, args.secret, {"brand": args.brand, "fixes": fixes}))
        console.print(f"[{'bold green' if res.success else 'bold red'}]{res.message}[/]")
    elif args.target == "wordpress":
        if not args.wp_url or not args.wp_user or not args.wp_pass:
            console.print("[bold red]Hata:[/bold red] WordPress için --wp-url, --wp-user ve --wp-pass zorunludur.")
            return
        res = asyncio.run(CMSDeployer.deploy_wordpress(args.wp_url, args.wp_user, args.wp_pass, fixes))
        console.print(f"[{'bold green' if res.success else 'bold red'}]{res.message}[/]")
    elif args.target == "github":
        if not args.gh_repo or not args.gh_token:
            console.print("[bold red]Hata:[/bold red] GitHub için --gh-repo (owner/name) ve --gh-token zorunludur.")
            return
        owner, _, name = args.gh_repo.partition("/")
        if not name:
            console.print("[bold red]Hata:[/bold red] --gh-repo 'owner/repository' biçiminde olmalıdır.")
            return
        branch = args.gh_branch or "main"
        res = asyncio.run(CMSDeployer.deploy_github(
            repo_owner=owner,
            repo_name=name,
            branch=branch,
            github_token=args.gh_token,
            fixes=fixes,
        ))
        console.print(f"[{'bold green' if res.success else 'bold red'}]{res.message}[/]")

def run_serve_command(args):
    """Executes 'answrank serve' — runs the FastAPI REST API & dashboard via uvicorn."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[bold red]Hata:[/bold red] 'serve' komutu için [bold]uvicorn[/bold] kuruludur; "
            "eksikse şu komutla yükleyin: [bold]pip install 'answrank[serve]'[/bold]"
        )
        return
    console.print(
        Panel.fit(
            f"[bold white]AnswRank REST API & Dashboard[/bold white]\n"
            f"Adres: [bold cyan]http://{args.host}:{args.port}[/bold cyan]\n"
            f"Doküman: [underline]http://{args.host}:{args.port}/docs[/underline]",
            title="[bold green]Sunucu Başlatılıyor[/bold green]",
            border_style="green",
        )
    )
    # 'answrank.api.app:app' import string keeps uvicorn's reloader/importer paths valid.
    uvicorn.run("answrank.api.app:app", host=args.host, port=args.port)

def run_payments_command(args):
    """E11 — ödeme/tahsilat. PSP anlaşmamız YOK: yalnız MANUAL havale kanalı
    insan-onaylı çalışir; PSP'li kanal 'yapilandirilmamis' der, asla sahte
    basarili odeme uretmez."""
    from answrank.finance.payments import (PaymentProvider, PaymentRequest,
                                           PaymentService)
    from answrank.finance.tax_ledger import TaxLedger
    svc = PaymentService(ledger=TaxLedger(load_persisted=False))

    if args.pay_cmd == "status":
        table = Table(title="Tahsilat Kanallari (E11 — dürüst durum)", show_header=True)
        for col in ("Kanal", "Durum"):
            table.add_column(col)
        for p in PaymentProvider:
            table.add_row(p.value, svc.provider_status(p))
        console.print(table)
        console.print("[dim]PSP anlasmasi olmadan yalniz MANUAL (havale) kanali para "
                      "kabul eder — bankada para görülüp dekont girilince fatura "
                      "dogar; asla otomatik 'ödendi' yok.[/dim]")
        return

    if args.pay_cmd == "collect":
        for need, val in (("--brand", args.brand), ("--country", args.country),
                          ("--amount", args.amount)):
            if not val:
                console.print(f"[bold red]✗ {need} gerekli — niyet uydurulmaz.[/bold red]")
                return
        req = PaymentRequest(contract_ref=args.contract_ref, brand=args.brand,
                             country=args.country, currency=args.currency,
                             amount=args.amount)
        try:
            res = svc.create_intent(req, PaymentProvider.MANUAL)
        except Exception as exc:
            console.print(f"[bold red]✗ {exc}[/bold red]")
            return
        console.print(f"[bold green]✓[/bold green] Tahsilat niyeti: {res.intent_id} "
                      f"({args.amount} {args.currency} → {args.country})")
        console.print(f"[dim]{res.note}. Bankaya para yattiktan sonra:[/dim]")
        console.print(f"[cyan]answrank payments confirm --intent {res.intent_id}"
                      " --proof <dekont-ref>[/cyan]")
        return

    if args.pay_cmd == "confirm":
        if not args.intent_id or not args.proof:
            console.print("[bold red]✗ --intent ve --proof (banka dekontu) gerekli — "
                          "kanitsiz 'ödendi' yok.[/bold red]")
            return
        try:
            res = svc.confirm_manual(args.intent_id, args.proof)
        except Exception as exc:
            console.print(f"[bold red]✗ {exc}[/bold red]")
            return
        console.print(f"[bold green]✓[/bold green] {res.intent_id}: {res.note}")
        if res.invoice_id:
            console.print(f"[dim]Fatura: {res.invoice_id} · Rejim: "
                          f"{res.regime.value if res.regime else '—'}[/dim]")
        return

    if args.pay_cmd == "webhook":
        # Gercek imza dogrulama yolu; anahtarsiz PSP reddeder, olay islenmez.
        if not args.file or not args.signature or not args.event_id:
            console.print("[bold red]✗ --file --signature --event-id gerekli.[/bold red]")
            return
        with open(args.file, "rb") as f:
            body = f.read()
        try:
            res = svc.handle_webhook(PaymentProvider.PAYTR, body,
                                     args.signature, args.event_id)
        except Exception as exc:
            console.print(f"[bold red]✗ {exc}[/bold red]")
            return
        console.print(f"[bold green]✓[/bold green] {res.intent_id}: {res.note}")
        return

    if args.pay_cmd == "refund":
        if not args.intent_id or not args.reason:
            console.print("[bold red]✗ --intent ve --reason gerekli — iade sebebi "
                          "denetim izidir.[/bold red]")
            return
        try:
            res = svc.refund(args.intent_id, args.reason)
        except Exception as exc:
            console.print(f"[bold red]✗ {exc}[/bold red]")
            return
        console.print(f"[bold green]✓[/bold green] {res.intent_id}: {res.note} "
                      "(fatura silinmedi, credit note ile ters kayit)")


def run_prospect_command(args):
    """E9 — otonom lead doğrulama: hiçbir aday uydurulmaz, robots saygılanır."""
    import json as _json
    from answrank.crm.prospector import LeadProspector
    with open(args.file, "r", encoding="utf-8") as f:
        cands = _json.load(f)
    if not isinstance(cands, list) or not cands:
        console.print("[bold red]✗ Liste boş/geçersiz — uydurma aday üretilmez.[/bold red]")
        return
    for c in cands:
        c.setdefault("country", args.country)
        c.setdefault("sector", args.sector)
    from answrank.db import Database
    p = LeadProspector(db=None if args.dry_run else Database(),
                       politeness=args.politeness)
    table = Table(title=f"Lead Doğrulama ({len(cands[:args.limit])} aday)", show_header=True)
    for col in ("Domain", "HTTP", "Robots", "İletişim", "Sonuç"):
        table.add_column(col)
    import asyncio as _aio

    async def _verify_and_stage():
        verified = await p.run_verify(cands)
        staged = rejected = 0
        for v in verified:
            ok = v.reachable or v.robots_disallowed
            if ok:
                if not args.dry_run:
                    await p.stage(v)  # yazma YALNIZ burada, gerçek kanıtla
                staged += 1
            else:
                rejected += 1
            contact = " / ".join(x for x in (v.phone, v.email) if x) or "DOĞRULANAMADI"
            table.add_row(v.domain, str(v.http_status or "—"),
                          "ENGELLİ" if v.robots_disallowed else str(v.robots_status or "—"),
                          contact, "STAGED" if ok else "RET — " + (v.notes or "ulaşılamadı"))
        return staged, rejected

    staged, rejected = _aio.run(_verify_and_stage())
    console.print(table)
    if args.dry_run:
        console.print("[dim]DRY-RUN — CRM'e yazılmadı.[/dim]")
    else:
        console.print(f"[bold green]✓[/bold green] {staged} lead stage edildi, {rejected} "
                      "ret (DOĞRULANAMADI). DM maddeleri için: answrank queue scan")


def run_queue_command(args):
    """E-ops CLI — tek bakışta karar yüzeyi; hiçbir şeyi kendiliğinden göndermez."""
    from answrank.queue import ApprovalQueue
    q = ApprovalQueue()
    if args.queue_cmd == "scan":
        n = q.scan()
        console.print(f"[bold green]✓[/bold green] Tarama: {n} yeni karar maddesi sıraya girdi "
                      "(yinelnen maddeler duplicates-yok). Toplam bekleyen: " + str(len(q.pending())))
    elif args.queue_cmd == "list":
        items = q.pending()
        if not items:
            console.print("[dim]Kuyruk boş — iş uydurulmaz. (Türetmek için: queue scan)[/dim]")
            return
        table = Table(title=f"İnsan-Onay Kuyruğu ({len(items)} bekleyen)", show_header=True)
        table.add_column("#"); table.add_column("Tür", style="cyan")
        table.add_column("Referans"); table.add_column("Karar özeti")
        for i in items:
            table.add_row(str(i["id"]), i["kind"], i["ref_id"], i["summary"])
        console.print(table)
        console.print('[dim]Karar: answrank queue approve|reject <#> --note "..." — ' 
                      "onaysız hiçbir madde dışarı çıkmaz.[/dim]")
    elif args.queue_cmd == "send":
        from answrank.dm_dispatch import DmDispatcher
        out = DmDispatcher(db=Database()).send_approved(args.item_id,
                                                        dry_run=args.dry_run)
        console.print(f"[bold]#{out['item_id']} → {out['result']}[/bold]")
        if out.get("to"):
            console.print(f"  alıcı: [cyan]{out['to']}[/cyan]")
        if out.get("why"):
            console.print(f"  [dim]{out['why']}[/dim]")
        console.print("[dim]Onaysız/hedef-yok gönderim olmaz — her sonuç dm_send_log'da.[/dim]")
    elif args.queue_cmd == "audit":
        # E13: çok-kapılı denetim — DM gönderiminin riskli yarısı.
        # AUTO_APPROVED, insan APPROVED'undan AYRI: gönderim yine ayrı kanaldır.
        from answrank.queue_gates import DmGateAuditor
        auditor = DmGateAuditor(db=Database())
        if args.auto_approve:
            res = auditor.auto_approve(dry_run=not args.apply)
            console.print(f"[bold]Otomatik onay ({'dry-run' if res['dry_run'] else 'UYGULANDI'}):[/bold]")
            for a in res["auto_approved"]:
                console.print(f"  [green]✓[/green] #{a['id']} {a['domain']} — 6/6 kapı")
            for b in res["still_pending"]:
                why = b.get("why") or "; ".join(
                    g["gate"] for g in b.get("gates", []) if not g["passed"]) or "?"
                console.print(f"  [yellow]…[/yellow] #{b['id']} {b['domain']} — {why}")
            for c in res["conflicts"]:
                console.print(f"  [red]⚠[/red] #{c['id']} {c['domain']} — {c['why']}")
            apply_label = ("uygulandı" if not res["dry_run"]
                           else "uygulanabilir (dry-run — hiçbir karar değişmedi)")
            console.print(f"[dim]{len(res['auto_approved'])} onay {apply_label}, "
                          f"{len(res['still_pending'])} insanı bekler, "
                          f"{len(res['conflicts'])} karar çakışması.[/dim]")
            return
        items = auditor.audit_pending()
        if not items:
            console.print("[dim]PENDING DM maddesi yok — denetilecek bir şey yok.[/dim]")
            return
        for item in items:
            mark = "[green]✓ GEÇTİ[/green]" if item["all_passed"] else "[red]✗ KAPALI[/red]"
            console.print(f"[bold]#{item['id']} {item['domain']}[/bold] {mark}")
            for g in item["gates"]:
                ok = "[green]✓[/green]" if g["passed"] else "[red]✗[/red]"
                console.print(f"    {ok} {g['gate']}: {g['reason']}")
        console.print("[dim]Otomatik onay için: queue audit --auto-approve --apply[/dim]")
    else:
        try:
            row = q.decide(args.item_id, approve=(args.queue_cmd == "approve"), note=args.note)
        except KeyError:
            console.print("[bold red]✗ Madde yok — uydurma karar yazılmaz.[/bold red]")
            return
        except ValueError as e:
            console.print(f"[bold red]✗ {e}[/bold red]")
            return
        console.print(f"[bold]{row['status']}[/bold] #{row['id']} {row['kind']}:{row['ref_id']}"
                      + (f" — not: {row['decision_note']}" if row["decision_note"] else ""))


def run_corpus_command(args):
    """E5 CLI — korpüs probe/stats/list; istatistik ölçümlü paydadan gelir."""
    import asyncio
    from answrank.corpus import CorpusStore, render_report_md
    from answrank.db import Database
    store = CorpusStore(db=Database())
    if args.corpus_cmd == "probe":
        with open(args.file, "r", encoding="utf-8") as f:
            domains = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        if not domains:
            console.print("[bold red]✗ Domain listesi boş — ölçüm yapılmaz, veri uydurulmaz.[/bold red]")
            return
        n = asyncio.run(store.collect(domains, politeness_sec=args.politeness, source=args.tag))
        console.print(f"[bold green]✓[/bold green] {n} gözlem arşivlendi (etiket: {args.tag})."
                      " Ölçülemeyenler ÖLÇÜLEMEDİ satırıdır — sayıya dönüştürülmez.")
    elif args.corpus_cmd == "stats":
        st = store.stats(source=args.tag)
        if st["n"] == 0:
            console.print("[yellow]Korpüs boş — istatistik uydurulmaz. Önce: answrank corpus probe --file ...[/yellow]")
            return
        md = render_report_md(st, method=f"Örneklem çerçevesi: {args.tag or 'tüm etiketler'}; "
                                         "kamuya açık web sitelerinin yalnız robots.txt/llms.txt/bot-yüzeyi "
                                         "yoklaması (içerik sayfası çekilmez).")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(md)
            console.print(f"[bold green]✓ Rapor yazıldı:[/bold green] {args.out}")
        else:
            console.print(Panel(md, title="[bold]GEO Korpüs İstatistiği[/bold]"))
    elif args.corpus_cmd == "list":
        rows = store.list_observations(source=args.tag)
        if not rows:
            console.print("[yellow]Kayıtlı gözlem yok.[/yellow]")
            return
        for r in rows:
            print_date = r['observed_at'][:19]
            console.print(f"{print_date}  {r['domain']:<36} {r['verdict']:<22} {r['robots_line']}")
def run_monitor_command(args):
    """E1 CLI — izleme CRUD + zamanlı ölçüm + ölçüm-kapılı digest."""
    import asyncio
    from answrank.db import Database
    from answrank.monitor import service as _ms
    svc = _ms.MonitorService(db=Database())
    if args.monitor_cmd == "add":
        mid = svc.add(domain=args.domain, brand=args.brand, sector=args.sector,
                      cadence_days=args.cadence, contract_id=args.contract)
        console.print(f"[bold green]✓ İzleme kaydı açıldı:[/bold green] {mid} "
                      f"({args.domain}, {args.cadence} gün kadans)")
        console.print("[dim]İlk ölçüm için:[/dim] answrank monitor run")
    elif args.monitor_cmd == "list":
        rows = svc.list()
        if not rows:
            console.print("[yellow]Kayıtlı izleme yok.[/yellow]")
            return
        for m in rows:
            console.print(f"{m['id']}  {m['domain']:<30} {m['sector']:<10} "
                          f"cadence={m['cadence_days']}g next_due={m['next_due_at'] or '—'}")
    elif args.monitor_cmd == "run":
        due = svc.due()
        if not due:
            console.print("[dim]Vadesi gelmiş izleme yok — ölçüm zamanı henüz gelmedi.[/dim]")
            return
        run_ids = asyncio.run(svc.run_due(executor=_ms.live_executor))
        for m, rid in zip(due, run_ids):
            last = svc.db.monitor_runs(m["id"])[-1]
            extra = (f"skor {last['score_base']}" if last["score_base"] is not None
                     else "sayı uydurulmaz")
            console.print(f"{m['domain']}: {last['status']} (run {rid}; {extra})")
    elif args.monitor_cmd == "fulfillment":
        from answrank.monitor.fulfillment import FulfillmentEvaluator
        ev = FulfillmentEvaluator(db=svc.db)
        targets = [args.monitor_id] if args.monitor_id else [m["id"] for m in svc.list()]
        for t in targets:
            try:
                r = ev.evaluate(t)
            except KeyError:
                console.print("[bold red]✗ İzleme kaydı yok — uydurma hüküm verilmez.[/bold red]")
                continue
            console.print(f"{t} [{r['kind']}] delta={r['delta'] if r['delta'] is not None else '—'} — {r['reason']}")
    elif args.monitor_cmd == "digest":
        try:
            d = svc.digest(args.monitor_id)
        except KeyError:
            console.print("[bold red]✗ İzleme kaydı bulunamadı — uydurma digest üretilmez.[/bold red]")
            return
        console.print(Panel(d["text"], title=f"[bold]GEO İzleme Digesti — {d['domain']} "
                                             f"({d['status']})[/bold]"))


def main():
    """CLI giriş noktası; komutları parse edip yürütür."""
    parser = argparse.ArgumentParser(prog="answrank", description="AnswRank AEO/GEO Audit & Optimization Engine")
    subparsers = parser.add_subparsers(dest="command", help="Komutlar")

    # Audit subcommand
    audit_p = subparsers.add_parser("audit", help="Web sitesini 8 kategoride denetle")
    audit_p.add_argument("url", help="Denetlenecek hedef web sitesi URL'si")
    audit_p.add_argument("--sector", default="general", choices=_SECTOR_CHOICES, help="İşletme sektörü")
    audit_p.add_argument("--format", default="text", choices=["text", "html", "md", "json"], help="Rapor formatı")
    audit_p.add_argument("--out", help="Çıktı dosya yolu")
    audit_p.add_argument("--deep", action="store_true", help="360° derin kurumsal denetim (WAF, RAG, Adversarial, Entity)")
    audit_p.add_argument("--brand", help="İşletme marka adı")

    # Citations subcommand
    cite_p = subparsers.add_parser("citations", help=f"{len(_MODELS)} LLM motorunda {_QC} soruluk atıf testi yap")
    cite_p.add_argument("brand", help="İşletme marka adı")
    cite_p.add_argument("domain", help="İşletme alan adı")
    cite_p.add_argument("--sector", default="dental", choices=_SECTOR_CHOICES, help="Sektör")
    cite_p.add_argument("--city", default="İstanbul", help="Şehir")
    cite_p.add_argument("--lang", default="tr", choices=["tr", "en"],
                        help="Ölçüm dil-bankası — EN bankalar E4'te açıldı (ihracat pazarları); "
                             "bankasız dil argparse'te reddedilir ki ölçüm sessizce Türkçe'ye düşmesin")
    cite_p.add_argument("--competitors", nargs="*", default=None,
                        help="Gerçek rakip domain listesi; verilmezse kurgusal rakip enjekte edilmez")
    cite_p.add_argument("--live", action="store_true", help=f"Canlı API köprüsü: {len(_MODELS)} sağlayıcı (anahtarı olan koşar, olmayan simülasyona düşer)")

    # Fix subcommand
    fix_p = subparsers.add_parser("fix", help="Hazır robots.txt, llms.txt ve JSON-LD üret")
    fix_p.add_argument("domain", help="Hedef alan adı")
    fix_p.add_argument("--brand", help="Marka adı")
    fix_p.add_argument("--sector", default="dental", help="Sektör")
    fix_p.add_argument("--city", default="İstanbul", help="Şehir")
    fix_p.add_argument("--out-dir", default="./answrank_fixes", help="Hedef çıktı klasörü")

    # Sitemap subcommand
    sm_p = subparsers.add_parser("sitemap", help="Site haritasını tara ve en zayıf sayfaları sırala")
    sm_p.add_argument("url", help="Site haritası veya kök domain URL'si")
    sm_p.add_argument("--sector", default="general", help="Sektör")
    sm_p.add_argument("--max-urls", type=int, default=10, help="Taranacak azami sayfa sayısı")

    # Delta subcommand
    delta_p = subparsers.add_parser("delta", help="İki denetim arasındaki delta farkını ve sözleşme güvencesini ölç")
    delta_p.add_argument("domain", help="İşletme alan adı")
    delta_p.add_argument("--baseline", type=int, required=True, help="Temel skor (0-100)")
    delta_p.add_argument("--current", type=int, required=True, help="Güncel skor (0-100)")
    delta_p.add_argument("--days", type=int, default=30, help="Geçen gün sayısı")

    # Qualify subcommand
    qual_p = subparsers.add_parser("qualify", help="Aday işletmeyi 5 adımlı eleme filtresinden geçir")
    qual_p.add_argument("company", help="İşletme adı")
    qual_p.add_argument("--sector", default="dental", help="Sektör")
    qual_p.add_argument("--domain", default=None, help="Web sitesi domaini")
    qual_p.add_argument("--ticket", type=float, default=5000.0, help="Ortalama işlem/bilet tutarı (TL)")
    qual_p.add_argument("--revenue", type=float, default=2000000.0, help="Yıllık ciro tahmini (TL)")
    qual_p.add_argument("--has-ads", action="store_true", default=True, help="Aktif reklam harcaması var mı")
    qual_p.add_argument("--dm-access", action="store_true", default=True, help="Karar vericiye doğrudan erişim var mı")
    qual_p.add_argument("--missing-ai", action="store_true", default=True, help="İlk 5 sektör sorusunda AI'da yok mu")
    qual_p.add_argument("--competitor-cited", action="store_true", default=True, help="En az 1 rakip AI'da var mı")

    # Objections subcommand
    obj_p = subparsers.add_parser("objections", help="Müşteri itirazını analiz et ve karşı yanıt üret")
    obj_p.add_argument("text", help="Müşterinin dile getirdiği itiraz cümlesi")
    obj_p.add_argument("--company", default="Klinik Adı", help="Müşteri işletme adı")
    obj_p.add_argument("--sector", default="dental", help="Sektör")
    obj_p.add_argument("--competitor", default="Rakip Klinik", help="Rakip işletme adı")

    # Contract subcommand
    con_p = subparsers.add_parser("contract", help="Madde 7 güvenceli hizmet sözleşmesi üret")
    con_p.add_argument("company", help="Müşteri şirket ünvanı")
    con_p.add_argument("domain", help="Müşteri domaini")
    con_p.add_argument("--contact", default="Yetkili Kişi", help="Yetkili kişi")
    con_p.add_argument("--tax-no", default="1234567890", help="Vergi kimlik numarası")
    con_p.add_argument("--tax-office", default="Kadıköy", help="Vergi dairesi")
    con_p.add_argument("--address", default="İstanbul, Türkiye", help="Şirket adresi")
    con_p.add_argument("--phone", default="+905550000000", help="Telefon")
    con_p.add_argument("--email", default="info@domain.com", help="E-posta")
    con_p.add_argument("--sector", default="dental", help="Sektör")
    con_p.add_argument("--tier", default="MONTHLY_RETAINER", choices=_TIER_CHOICES, help="Paket")
    con_p.add_argument("--fee", type=float, default=6000.0, help="Aylık hizmet bedeli (TL)")
    con_p.add_argument("--contract-no", default="ANSW-2026-001", help="Sözleşme numarası")
    con_p.add_argument("--date", default="2026-09-14", help="Başlangıç tarihi")
    con_p.add_argument("--months", type=int, default=6, help="Sözleşme süresi (ay)")
    con_p.add_argument("--out", help="Çıktı dosya yolu (.md)")

    # Economics subcommand
    econ_p = subparsers.add_parser("economics", help="Birim ekonomisi, LTV/CAC ve MRR projeksiyonlarını görüntüle")
    econ_p.add_argument("--tier", default="MONTHLY_RETAINER", choices=["QUICK_AUDIT", "CORE_FIX", "MONTHLY_RETAINER", "ENTERPRISE"], help="Hedef paket")
    econ_p.add_argument("--clients", type=int, default=10, help="Hedef aktif müşteri sayısı")
    econ_p.add_argument("--cac", type=float, default=1000.0, help="Müşteri edinme maliyeti tahmini (TL)")
    econ_p.add_argument("--retention", type=float, default=6.0, help="Ortalama kalış süresi (ay)")

    # Scenarios subcommand
    scen_p = subparsers.add_parser("scenarios", help="Gün 30/60 denetim sonrası S1-S4 karar ağacını çalıştır")
    scen_p.add_argument("--baseline", type=float, required=True, help="Başlangıç skoru (0-100)")
    scen_p.add_argument("--current", type=float, required=True, help="Güncel skor (0-100)")
    scen_p.add_argument("--baseline-cit", type=int, default=0, help="Başlangıç atıf sayısı")
    scen_p.add_argument("--current-cit", type=int, default=5, help="Güncel atıf sayısı")
    scen_p.add_argument("--inaction", action="store_true", default=False, help="Müşteri teknik eylemsizlikte bulundu mu")

    # Milestones subcommand
    mile_p = subparsers.add_parser("milestones", help="90 günlük 4 fazlı eylem planı durumunu görüntüle")
    mile_p.add_argument("--day", type=int, default=14, help="Projedeki mevcut gün (1-90)")
    mile_p.add_argument("--clients", type=int, default=3, help="Mevcut aktif müşteri sayısı")
    mile_p.add_argument("--mrr", type=float, default=18000.0, help="Mevcut MRR (TL)")

    # CRM subcommand
    crm_p = subparsers.add_parser("crm", help="Aday takip tablosu ve outreach yönetimi")
    crm_sub = crm_p.add_subparsers(dest="crm_action", help="CRM aksiyonları")
    crm_sub.add_parser("sync", help="takip_tablosu.csv dosyasını veritabanına aktar")
    crm_sub.add_parser("list", help="Kayıtlı adayları listele")
    crm_sub.add_parser("leads", help="E7: mini-probe lead hunisi (son 50; IP tutulmaz)")
    draft_p = crm_sub.add_parser("draft", help="Kişiselleştirilmiş soğuk DM taslağı üret")
    draft_p.add_argument("domain", nargs="?", default=None, help="Hedef işletme domaini")
    draft_p.add_argument("--from-lead", default=None,
                         help="E7: son halka-açık mini-probe ölçümünden yeniden-ölçmeyen DM üret")
    draft_p.add_argument("--sector", default="dental", help="Sektör")
    draft_p.add_argument("--with-visibility", action="store_true",
        help="E12: bu domain için ölçülmüş AI-görünürlük varsa DM'e kanıt olarak ekle")
    draft_p.add_argument("--contact", default="Doktorum", help="Muhatap adı")
    send_p = crm_sub.add_parser("send", help="Onaylı DM'yi alıcıya ulaştır (.eml/SMTP) — onaysız gönderim olmaz")
    send_p.add_argument("domain", help="Hedef domain (DB'deki onaylı kuyruk maddesi)")
    send_p.add_argument("--variant", default="variant_1", help="Varyat anahtarı (variant_1/2/3, followup_day_3/7)")
    send_p.add_argument("--subject", default="AI gorunurlugu tespiti — ucretsiz rapor")
    send_p.add_argument("--body", default=None, help="Govde metni (verilmezse kuyruk ozetinden uretilir)")
    crm_sub.add_parser("followups", help="Vadesi gelen 3/7 gunluk takipleri .eml olarak hazirla")
    crm_sub.add_parser("outbox", help="outbox/ dizinindeki hazir .eml dosyalarini listele")

    # Probe-WAF subcommand
    from answrank.audit.waf_probe import WAFProbeEngine as _WPE  # roster-count honesty: never hardcode
    prospect_p = subparsers.add_parser("prospect", help="E9 otonom lead: ajansan keşif listesini doğrula+stage et (robots saygılı)")
    prospect_p.add_argument("--file", required=True, help="Aday JSON: [{brand,domain,city,source_url,...}]")
    prospect_p.add_argument("--country", default=None)
    prospect_p.add_argument("--sector", default="dental")
    prospect_p.add_argument("--limit", type=int, default=50)
    prospect_p.add_argument("--politeness", type=float, default=1.5)
    pay_p = subparsers.add_parser("payments",
        help="E11 tahsilat: PSP anlaşması yoksa MANUAL havale kanalı (insan-onaylı)")
    pay_p.add_argument("pay_cmd", choices=["status", "collect", "confirm", "webhook", "refund"])
    pay_p.add_argument("--brand", help="Müşteri markası")
    pay_p.add_argument("--country", help="ISO ülke kodu (rejim: TR ise %%20 KDV, diğerleri %%0 ihracat)")
    pay_p.add_argument("--currency", default="TRY")
    pay_p.add_argument("--amount", type=float, required=False)
    pay_p.add_argument("--contract-ref", dest="contract_ref", default="MANUAL")
    pay_p.add_argument("--intent", dest="intent_id", help="PAY-##### tahsilat niyeti")
    pay_p.add_argument("--proof", help="Banka dekontu referansı (kanıt olmadan onay yok)")
    pay_p.add_argument("--reason", help="İade sebebi (denetim izi)")
    pay_p.add_argument("--file", help="Webhook olay dosyası (ham gövde)")
    pay_p.add_argument("--signature", help="Webhook HMAC imzası")
    pay_p.add_argument("--event-id", dest="event_id", help="PSP olay kimliği (idempotens)")
    prospect_p.add_argument("--dry-run", action="store_true", help="Doğrula ama CRM'e yazma")

    queue_p = subparsers.add_parser("queue", help="Tek insan-onay kuyruğu: DM/sözleşme/FREE-CYCLE/izleme müdahalesi")
    q_sub = queue_p.add_subparsers(dest="queue_cmd", required=True)
    q_sub.add_parser("list", help="Bekleyen kararlar (boşsa boş yazar)")
    q_sub.add_parser("scan", help="Türetilmiş maddeleri kuyruğa toplar (lead/sözleşme/izleme)")
    for act in ("approve", "reject"):
        qa_p = q_sub.add_parser(act, help=f"{act}: maddeye nihai insan kararı işler")
        qa_p.add_argument("item_id", type=int)
        qa_p.add_argument("--note", default="", help="Karar gerekçesi (denetim izi)")
    qs_p = q_sub.add_parser("send", help="E13b: ONAYLI DM maddesini gönder (SMTP gerekir)")
    qs_p.add_argument("item_id", type=int)
    qs_p.add_argument("--dry-run", action="store_true",
                      help="Göndermeden ne olacağını göster (log yazmaz)")
    qg_p = q_sub.add_parser("audit", help="E13: PENDING DM maddelerini 6 kapıdan denetle")
    qg_p.add_argument("--auto-approve", action="store_true",
                      help="Tüm kapıları geçenleri AUTO_APPROVED işaretle (gönderim ayrı)")
    qg_p.add_argument("--apply", action="store_true",
                      help="Yalnız gösterme — gerçekten işaretle (dry-run değil)")

    corp_p = subparsers.add_parser("corpus", help="E5 araştırma korpüsü: kamusal mini-probe gözlem arşivi + ölçüm-kapılı istatistik")
    corp_sub = corp_p.add_subparsers(dest="corpus_cmd", required=True)
    cpp_p = corp_sub.add_parser("probe", help="Domain listesini korpüse işle (nazik gecikmeli canlı yoklama)")
    cpp_p.add_argument("--file", required=True, help="Satır başına bir domain/URL dosyası")
    cpp_p.add_argument("--politeness", type=float, default=2.0, help="Domain arası bekleme (sn)")
    cpp_p.add_argument("--tag", default="corpus-v1", help="Örneklem çerçevesi etiketi")
    cps_p = corp_sub.add_parser("stats", help="Korpüs istatistiği — paydasız oran üretilmez")
    cps_p.add_argument("--tag", default=None)
    cps_p.add_argument("--out", default=None, help="Markdown raporu yazılacak dosya (yoksa ekrana basılır)")
    cpl_p = corp_sub.add_parser("list", help="Ham gözlem satırları")
    cpl_p.add_argument("--tag", default=None)

    mon_p = subparsers.add_parser("monitor", help="E1 GEO İzleme: aylık otomatik ölçüm koşuları ve dürüst delta digest'i")
    mon_sub = mon_p.add_subparsers(dest="monitor_cmd", required=True)
    ma_p = mon_sub.add_parser("add", help="İzleme kaydı aç")
    ma_p.add_argument("--domain", required=True)
    ma_p.add_argument("--brand", required=True)
    ma_p.add_argument("--sector", default="general", choices=_SECTOR_CHOICES)
    ma_p.add_argument("--cadence", type=int, default=30, help="Koşu aralığı (gün)")
    ma_p.add_argument("--contract", default=None, help="Bağlı sözleşme no (Madde-7 fulfillment)")
    mon_sub.add_parser("list", help="İzleme kayıtları")
    mon_sub.add_parser("run", help="Vadesi gelen tüm izlemeleri ölç (canlı/SİM etiketli)")
    md_p = mon_sub.add_parser("digest", help="İzleme deltasını ölçümlü kaynaklardan yazdır")
    md_p.add_argument("monitor_id")
    mf_p = mon_sub.add_parser("fulfillment", help="E6: Madde-7.3 garanti icra hükmü (yalnız ölçümlü delta ile)")
    mf_p.add_argument("monitor_id", nargs="?", default=None)

    waf_p = subparsers.add_parser("probe-waf", help=f"{len(_WPE.AI_CRAWLER_USER_AGENTS)} gerçek AI bot UA'sı ile Cloudflare/WAF sessiz blokaj testi yap")
    waf_p.add_argument("url", help="Hedef URL veya domain")

    # RAG subcommand
    rag_p = subparsers.add_parser("rag", help="Sayfa içeriğinin anlamsal RAG embedding ve top-k skorunu hesapla")
    rag_p.add_argument("url", help="Hedef web sitesi URL'si")
    rag_p.add_argument("--sector", default="dental", help="Sektör")
    rag_p.add_argument("--city", default="İstanbul", help="Şehir")

    # Monte-Carlo subcommand
    mc_p = subparsers.add_parser("monte-carlo", help="LLM stokastik atıf kararlılık endeksini (Confidence Interval) ölç")
    mc_p.add_argument("brand", help="Marka adı")
    mc_p.add_argument("domain", help="Alan adı")
    mc_p.add_argument("--sector", default="dental", help="Sektör")
    mc_p.add_argument("--city", default="İstanbul", help="Şehir")
    mc_p.add_argument("--iterations", type=int, default=5, help="Simülasyon koşum sayısı")

    # Ground subcommand
    grnd_p = subparsers.add_parser("ground", help="Wikidata ve Google Knowledge Graph varlık doğrulamasını yap")
    grnd_p.add_argument("brand", help="Marka adı")
    grnd_p.add_argument("domain", help="Alan adı")

    # Adversarial subcommand
    adv_p = subparsers.add_parser("adversarial", help="Web sitesinde gizli CSS, prompt enjeksiyonu ve LLM zehirlemesini tara")
    adv_p.add_argument("url", help="Hedef web sitesi URL'si")

    # Swarm subcommand
    swarm_p = subparsers.add_parser("swarm", help="5 ajanlı otonom satış ve icra sürüsünü koştur")
    swarm_p.add_argument("brand", help="Hedef marka adı")
    swarm_p.add_argument("domain", help="Hedef alan adı")
    swarm_p.add_argument("--sector", default="dental", help="Sektör")
    swarm_p.add_argument("--city", default="London", help="Şehir")
    swarm_p.add_argument("--country", default="UK", choices=["TR", "UK", "US", "DE", "UAE"], help="Hedef pazar")
    swarm_p.add_argument("--currency", default="GBP", help="Para birimi")
    swarm_p.add_argument("--agency", default=None, help="E2 beyaz-etiket: kilidi/sözleşmeyi taşıyan ajans domaini (sektör kotası uygulaması)")
    swarm_p.add_argument("--ticket", type=float, default=2500.0, help="Ortalama bilet boyutu")

    # Sentiment subcommand
    snt_p = subparsers.add_parser("sentiment", help="LLM atıf metninde Zero-Click duyarlılık ve marka güvenliğini ölç")
    snt_p.add_argument("brand", help="Marka adı")
    snt_p.add_argument("--text", required=True, help="LLM yanıt metni")
    snt_p.add_argument("--sector", default="dental", help="Sektör")

    # Deploy subcommand
    dep_p = subparsers.add_parser("deploy", help="Üretilen AEO/GEO varlıklarını CMS, Webhook veya dizine dağıt")
    dep_p.add_argument("brand", help="Marka adı")
    dep_p.add_argument("domain", help="Alan adı")
    dep_p.add_argument("--target", default="local", choices=["local", "webhook", "wordpress", "github"], help="Dağıtım hedefi")
    dep_p.add_argument("--sector", default="dental", help="Sektör")
    dep_p.add_argument("--city", default="London", help="Şehir")
    dep_p.add_argument("--out", default="./dist_aeo", help="Yerel çıktı dizini")
    dep_p.add_argument("--webhook-url", help="Webhook uç noktası")
    dep_p.add_argument("--secret", default="answrank-secret", help="HMAC secret")
    dep_p.add_argument("--wp-url", help="WordPress site URL")
    dep_p.add_argument("--wp-user", help="WordPress kullanıcı adı")
    dep_p.add_argument("--wp-pass", help="WordPress uygulama parolası")
    dep_p.add_argument("--gh-repo", help="GitHub deposu (owner/name)")
    dep_p.add_argument("--gh-token", help="GitHub personal access token")
    dep_p.add_argument("--gh-branch", default="main", help="GitHub dalı (varsayılan: main)")

    # Serve subcommand
    serve_p = subparsers.add_parser("serve", help="AnswRank REST API ve Dashboard'u çalıştır")
    serve_p.add_argument("--host", default="127.0.0.1", help="Host IP")
    serve_p.add_argument("--port", type=int, default=8000, help="Port numarası")

    args = parser.parse_args()

    if args.command == "audit":
        run_audit_command(args)
    elif args.command == "swarm":
        run_swarm_command(args)
    elif args.command == "sentiment":
        run_sentiment_command(args)
    elif args.command == "deploy":
        run_deploy_command(args)
    elif args.command == "adversarial":
        run_adversarial_command(args)
    elif args.command == "citations":
        run_citations_command(args)
    elif args.command == "fix":
        run_fix_command(args)
    elif args.command == "sitemap":
        run_sitemap_command(args)
    elif args.command == "delta":
        run_delta_command(args)
    elif args.command == "qualify":
        run_qualify_command(args)
    elif args.command == "objections":
        run_objections_command(args)
    elif args.command == "contract":
        run_contract_command(args)
    elif args.command == "economics":
        run_economics_command(args)
    elif args.command == "scenarios":
        run_scenarios_command(args)
    elif args.command == "milestones":
        run_milestones_command(args)
    elif args.command == "prospect":
        run_prospect_command(args)
    elif args.command == "payments":
        run_payments_command(args)
    elif args.command == "queue":
        run_queue_command(args)
    elif args.command == "corpus":
        run_corpus_command(args)
    elif args.command == "monitor":
        run_monitor_command(args)
    elif args.command == "probe-waf":
        run_probe_waf_command(args)
    elif args.command == "rag":
        run_rag_command(args)
    elif args.command == "monte-carlo":
        run_monte_carlo_command(args)
    elif args.command == "ground":
        run_ground_command(args)
    elif args.command == "crm":
        run_crm_command(args)
    elif args.command == "serve":
        run_serve_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()


