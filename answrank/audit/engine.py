"""Audit Engine orchestrating all 8 analyzers and generating recommendations."""

import uuid
from bs4 import BeautifulSoup
from typing import Optional, List
from answrank.textnorm import brand_from_domain
from answrank.models import (
    AuditResult,
    CategoryScores,
    Recommendation,
    DeepAuditResult,
)
from answrank.audit.crawler import WebCrawler, CrawlData
from answrank.audit.analyzers import (
    RobotsAnalyzer,
    LlmsTxtAnalyzer,
    SchemaAnalyzer,
    MetaAnalyzer,
    CitabilityAnalyzer,
    EntityAnalyzer,
    TrustAnalyzer,
    NegativeAnalyzer,
)
from answrank.audit.adversarial import AdversarialAnalyzer
from answrank.audit.entity_grounding import EntityGroundingResult
from answrank.audit.rag_engine import RAGAnalysisResult
from answrank.audit.waf_probe import WAFProbeResult
from answrank.config import settings

class AuditEngine:
    """Core AEO/GEO audit evaluation engine."""

    def __init__(self):
        self.crawler = WebCrawler()
        self.robots_analyzer = RobotsAnalyzer()
        self.llms_analyzer = LlmsTxtAnalyzer()
        self.schema_analyzer = SchemaAnalyzer()
        self.meta_analyzer = MetaAnalyzer()
        self.citability_analyzer = CitabilityAnalyzer()
        self.entity_analyzer = EntityAnalyzer()
        self.trust_analyzer = TrustAnalyzer()
        self.negative_analyzer = NegativeAnalyzer()
        self.adversarial_analyzer = AdversarialAnalyzer()

    async def audit_url(self, url: str, sector: str = "general") -> AuditResult:
        """Fetches and runs full audit on a live URL."""
        crawl_data = await self.crawler.fetch(url)
        return self.audit_crawl_data(crawl_data, sector=sector)

    def audit_crawl_data(self, crawl: CrawlData, sector: str = "general") -> AuditResult:
        """Evaluates pre-fetched crawl data (offline or test fixture friendly)."""
        warnings = list(getattr(crawl, "fetch_warnings", []) or [])
        if crawl.status_code == 0 and any("DOĞRULANAMADI" in w for w in warnings):
            # Nothing was measured — every analyzer would score an empty string and
            # accuse the site of "missing robots.txt" it never got to check.
            zero = CategoryScores(**{
                name: field.annotation(score=0)
                for name, field in CategoryScores.model_fields.items()})
            return AuditResult(
                audit_id=f"audit_{uuid.uuid4().hex[:12]}",
                url=crawl.url, domain=crawl.domain, sector=sector,
                overall_score=0, score_band="ÖLÇÜLEMEDİ", categories=zero,
                recommendations=[],
                lost_revenue_estimate_monthly_try=None,
                crawl_warnings=warnings + [
                    "Kategoriler 0 puan GÖSTERİYOR ama puanlamadı: ölçüm yapılamadı."],
            )
        soup = BeautifulSoup(crawl.html_content, "html.parser")

        # Run 8 category analyzers
        robots_res = self.robots_analyzer.analyze(crawl.robots_txt)
        llms_res = self.llms_analyzer.analyze(crawl.llms_txt, crawl.llms_full_txt)
        schema_res = self.schema_analyzer.analyze(soup, sector=sector)
        meta_res = self.meta_analyzer.analyze(soup)
        citability_res = self.citability_analyzer.analyze(soup)
        entity_res = self.entity_analyzer.analyze(soup, domain=crawl.domain)
        trust_res = self.trust_analyzer.analyze(soup, is_https=crawl.is_https)
        negative_res = self.negative_analyzer.analyze(soup)

        categories = CategoryScores(
            robots=robots_res,
            llms_txt=llms_res,
            schema_jsonld=schema_res,
            meta_architecture=meta_res,
            citability_rag=citability_res,
            entity_coherence=entity_res,
            trust_stack=trust_res,
            negative_signals=negative_res,
        )

        overall_score = (
            robots_res.score
            + llms_res.score
            + schema_res.score
            + meta_res.score
            + citability_res.score
            + entity_res.score
            + trust_res.score
            + negative_res.score
        )
        overall_score = max(0, min(100, overall_score))

        # Score band
        if overall_score >= 86:
            score_band = "Excellent"
        elif overall_score >= 68:
            score_band = "Good"
        elif overall_score >= 36:
            score_band = "Foundation"
        else:
            score_band = "Critical"

        # Prioritized technical recommendations
        recommendations: List[Recommendation] = []

        if robots_res.score < 14:
            recommendations.append(
                Recommendation(
                    category="Robots.txt",
                    priority="CRITICAL",
                    title="AI Arama Botlarına İzin Verin",
                    action="robots.txt dosyasına OAI-SearchBot, PerplexityBot ve Claude-SearchBot için Allow: / direktiflerini ekleyin.",
                    impact_points=14 - robots_res.score,
                )
            )

        if not llms_res.has_llms_txt:
            recommendations.append(
                Recommendation(
                    category="llms.txt",
                    priority="CRITICAL",
                    title="/llms.txt Standart Özet Dizini Ekleyin",
                    action="Kök dizinde işletmenizin uzmanlıklarını ve resmi bilgilerini listeleyen standart bir llms.txt oluşturun.",
                    impact_points=12,
                )
            )

        if schema_res.score < 10:
            recommendations.append(
                Recommendation(
                    category="Schema JSON-LD",
                    priority="HIGH",
                    title="Zengin JSON-LD Şeması ve FAQPage Ekleyin",
                    action=f"Sitenize {sector.capitalize()} ve FAQPage şemalarını ekleyerek soru-cevap bloklarını semantik olarak işaretleyin.",
                    impact_points=10 - schema_res.score,
                )
            )

        if citability_res.score < 8:
            recommendations.append(
                Recommendation(
                    category="İçerik Alıntılanabilirliği",
                    priority="HIGH",
                    title="Ters Piramit ve Sayısal Veri Yoğunluğunu Artırın",
                    action="Hizmet sayfalarınızın ilk 50 kelimesinde sorulan soruya doğrudan ve net yanıt verin; vaka/sayısal veri ekleyin.",
                    impact_points=8 - citability_res.score,
                )
            )

        if not meta_res.has_canonical:
            recommendations.append(
                Recommendation(
                    category="Meta Mimari",
                    priority="MEDIUM",
                    title="Canonical URL Tanımlayın",
                    action="Her sayfaya standart rel='canonical' etiketi ekleyerek modellerin içerik duplikasyonunu önleyin.",
                    impact_points=2,
                )
            )

        # Monthly lost revenue estimate based on score gap.
        # LTV table and the potential-clients factor come from settings
        # (calibratable per deployment; defaults preserve historical behavior).
        ltv = settings.sector_ltv_try.get(sector, settings.sector_ltv_try["general"])
        gap_factor = (100 - overall_score) / 100.0
        lost_revenue_monthly = round(
            ltv * gap_factor * settings.lost_revenue_client_factor, 2
        )  # Conservative ~6.5 potential clients lost (model assumption, not a measurement)

        audit_id = f"audit_{uuid.uuid4().hex[:12]}"

        return AuditResult(
            audit_id=audit_id,
            url=crawl.url,
            domain=crawl.domain,
            sector=sector,
            overall_score=overall_score,
            score_band=score_band,
            categories=categories,
            recommendations=recommendations,
            lost_revenue_estimate_monthly_try=lost_revenue_monthly,
            crawl_warnings=list(getattr(crawl, "fetch_warnings", []) or []),
        )

    async def probe_waf(self, url: str) -> "WAFProbeResult":
        """Run network & WAF silent blocking check against the configured AI-bot roster.

        Returns overall_risk UNVERIFIED (not CRITICAL) when the target answers
        neither a browser nor bot requests — unreachable is never accused of blocking.
        """
        from answrank.audit.waf_probe import WAFProbeEngine
        return await WAFProbeEngine.probe_url(url)

    def evaluate_rag(self, url: str, html_content: str, questions: List[str]) -> "RAGAnalysisResult":
        """Run AutoGEO / dense semantic chunking and cosine similarity benchmark."""
        from answrank.audit.rag_engine import RAGEngine
        return RAGEngine.evaluate_content_rag(url, html_content, questions)

    async def evaluate_entity_grounding(
        self, brand_name: str, domain: str, html_content: Optional[str] = None
    ) -> "EntityGroundingResult":
        """Verify Wikidata QID and Google Knowledge Graph entity grounding."""
        from answrank.audit.entity_grounding import EntityGroundingEngine
        return await EntityGroundingEngine.evaluate_grounding(brand_name, domain, html_content=html_content)

    async def audit_url_deep(
        self,
        url: str,
        sector: str = "general",
        brand_name: Optional[str] = None,
        probe_waf: bool = True,
        check_adversarial: bool = True,
        check_grounding: bool = True,
        check_rag: bool = True,
    ) -> DeepAuditResult:
        """Executes full 360° deep audit orchestrating all 8 core analyzers + 4 advanced subsystems."""
        crawl_data = await self.crawler.fetch(url)
        base_audit = self.audit_crawl_data(crawl_data, sector=sector)
        if base_audit.score_band == "ÖLÇÜLEMEDİ":
            # Nothing was fetched: no probe, no grounding, no score — UNAUDITABLE.
            return DeepAuditResult(
                base_audit=base_audit, waf_probe=None, adversarial=None,
                entity_grounding=None, rag_analysis=None,
                composite_deep_score=0.0, deep_tier="UNAUDITABLE",
                key_findings=[
                    "Hedefe ulaşılamadı — 360° derin denetim YAPILAMADI. "
                    "Bu sonuç sitenin kusuru değildir; ölçüm koşulamadı (DOĞRULANAMADI)."],
            )
        soup = BeautifulSoup(crawl_data.html_content, "html.parser")
        derived_brand = brand_name or brand_from_domain(crawl_data.domain)

        waf_dict = None
        if probe_waf:
            waf_res = await self.probe_waf(url)
            waf_dict = waf_res.model_dump()

        adv_dict = None
        if check_adversarial:
            adv_res = self.adversarial_analyzer.analyze(soup, raw_html=crawl_data.html_content)
            adv_dict = adv_res.model_dump()

        ground_dict = None
        if check_grounding:
            ground_res = await self.evaluate_entity_grounding(derived_brand, crawl_data.domain, html_content=crawl_data.html_content)
            ground_dict = ground_res.model_dump()

        rag_dict = None
        if check_rag:
            from answrank.citations.questions import get_sector_questions
            q_list = [q["question"] for q in get_sector_questions(sector, sehir="İstanbul", marka=derived_brand, rakip="Rakip")[:5]]
            rag_res = self.evaluate_rag(url, crawl_data.html_content, q_list)
            rag_dict = rag_res.model_dump()

        # Calculate 360° Composite Deep Score
        # Weight caps: Base audit 45, WAF 15, Adversarial 10,
        # Entity Grounding 10, RAG readiness 20 — over EXECUTED dimensions only.
        # (RAG previously unweighted — now integrated as a first-class signal.)
        # Zero-Trust scoring (16 Eyl derin-tarama C9): a dimension that was NOT run
        # earns nothing and is EXCLUDED from the denominator — un-run must never
        # inflate the score with free full marks. UNVERIFIED (ran, inconclusive)
        # keeps half weight. Composite is renormalized over executed dimensions.
        dims = [("base", base_audit.overall_score * 0.45, 45.0, True)]
        if waf_dict is not None:
            if waf_dict.get("overall_risk") == "UNVERIFIED":
                dims.append(("waf", 7.5, 15.0, True))
            else:
                from answrank.audit.waf_probe import WAFProbeEngine
                total_probed = (waf_dict.get("total_probed")
                                or len(waf_dict.get("bot_statuses") or [])
                                or len(WAFProbeEngine.AI_CRAWLER_USER_AGENTS))
                blocked_pct = waf_dict.get("blocked_bots_count", 0) / max(1, total_probed)
                dims.append(("waf", max(0.0, 15.0 * (1.0 - blocked_pct)), 15.0, True))
        if adv_dict:
            risk = adv_dict.get("risk_score", 0)
            dims.append(("adv", max(0.0, 10.0 * (1.0 - (risk / 100.0))), 10.0, True))
        if ground_dict is not None:
            g_score = ground_dict.get("grounding_score", 50)
            dims.append(("ground", max(0.0, 10.0 * (g_score / 100.0)), 10.0, True))
        if rag_dict is not None:
            r_score = rag_dict.get("rag_retrieval_score", 0)
            dims.append(("rag", max(0.0, 20.0 * (r_score / 100.0)), 20.0, True))

        earned = sum(d[1] for d in dims)
        possible = sum(d[2] for d in dims)
        composite_score = round(100.0 * earned / possible, 1) if possible else 0.0
        ran = {d[0] for d in dims}
        skipped = [n for n in ("waf", "adv", "ground", "rag") if n not in ran]

        # Deep Tiering
        waf_conclusive = not waf_dict or waf_dict.get("overall_risk") != "UNVERIFIED"
        if composite_score >= 85 and waf_conclusive and (not waf_dict or waf_dict.get("blocked_bots_count", 0) == 0):
            deep_tier = "ENTERPRISE_READY"
        elif composite_score >= 65:
            deep_tier = "STABLE"
        elif composite_score >= 40:
            deep_tier = "RISK_EXPOSED"
        elif waf_dict and waf_dict.get("blocked_bots_count", 0) > 0:
            deep_tier = "CRITICAL_BLOCKED"
        else:
            # Low composite WITHOUT proven blockage must not borrow the blockage name.
            deep_tier = "CRITICAL_LOW_SCORE"

        key_findings = []
        if skipped:
            key_findings.append(
                f"Kompozit skor yalnız çalıştırılan {len(dims)}/5 boyut üzerinden renormalize edildi; "
                f"çalıştırılmayan: {', '.join(skipped)} (uydurma tam puan yok).")
        if waf_dict and waf_dict.get("overall_risk") == "UNVERIFIED":
            key_findings.append("WAF probe hüküm veremedi: hedef erişilemedi (site kapalı/DNS/timeout) — blokaj iddia edilmez, tekrar test edin.")
        if waf_dict and waf_dict.get("blocked_bots_count", 0) > 0:
            key_findings.append(f"WAF sessiz blokajı: {waf_dict['blocked_bots_count']} AI bot engelleniyor!")
        if adv_dict and not adv_dict.get("is_clean", True):
            key_findings.append(f"Adversarial risk: {adv_dict.get('threat_level')} seviyesinde ({len(adv_dict.get('threats', []))} tehdit).")
        if ground_dict and ground_dict.get("has_wikidata"):
            _conf = ground_dict.get("qid_confidence")
            if _conf in ("verified", "exact_name_no_conflict"):
                key_findings.append(f"Wikidata varlık zeminlemesi teyit edildi (QID: {ground_dict.get('wikidata_qid')}).")
            elif _conf == "rejected":
                key_findings.append(
                    f"Wikidata ad-eşleşmesi resmî-site (P856) çelişkisi nedeniyle reddedildi "
                    f"(QID: {ground_dict.get('wikidata_qid')}) — zeminleme kredisi yok."
                )
            else:
                key_findings.append(
                    f"Wikidata QID {ground_dict.get('wikidata_qid')} bulundu ama resmî-site "
                    f"çapraz-doğrulaması kesinleşmedi — kredi muhafazakâr verildi."
                )
        if ground_dict and (ground_dict.get("wikidata_probe_status") or "") == "unreachable":
            key_findings.append(
                "Wikidata zeminleme sorgusu tamamlanamadı (ağ/API hatası) — QID \"yok\" değil "
                "\"DOĞRULANAMADI\"; puan muhafazakâr kaldı, denetimi tekrar çalıştırın."
            )
        if rag_dict:
            key_findings.append(f"AutoGEO RAG parçalanma hazırlığı: %{rag_dict.get('rag_retrieval_score', 0):.0f} uygunluk.")

        return DeepAuditResult(
            base_audit=base_audit,
            waf_probe=waf_dict,
            adversarial=adv_dict,
            entity_grounding=ground_dict,
            rag_analysis=rag_dict,
            composite_deep_score=composite_score,
            deep_tier=deep_tier,
            key_findings=key_findings,
        )

