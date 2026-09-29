"""FastAPI Application for AnswRank Web API and Interactive Dashboards."""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Literal, Optional

from answrank.audit.engine import AuditEngine
from answrank.citations.runner import MultiLLMCitationRunner
from answrank.reporting.generator import ReportGenerator
from answrank.reporting.fix_generator import FixGenerator
from answrank.db import Database
from answrank.config import settings

import logging

logger = logging.getLogger("answrank.api")
# 16 Eyl P1: internal exception text must never leak to clients (may carry
# filesystem/DNS details); full trace stays in the server log via logger.exception.
INTERNAL_ERROR_DETAIL = "Sunucu tarafında beklenmeyen iç hata; ayrıntı sunucu günlüğünde." 
from answrank.models import AuditResult

app = FastAPI(
    title=f"{settings.app_name} API",
    description="Answer Engine Optimization (AEO) and Generative Engine Optimization (GEO) REST Service",
    version=settings.app_version,
)


@app.exception_handler(RequestValidationError)
async def _turkish_validation_handler(request: Request, exc: RequestValidationError):
    """Pydantic doğrulama hataları Türkçe döner — kullanıcı yüzeyi İngilizce
    makine mesajı göstermez (dil kalitesi sözleşmesi)."""
    from fastapi.responses import JSONResponse
    msgs = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        rule = err.get("type", "invalid")
        tr = {
            "string_too_short": "en az 3 karakter olmalı",
            "missing": "zorunlu alan eksik",
            "value_error": "geçersiz değer",
        }.get(rule, f"geçersiz değer ({rule})")
        msgs.append(f"{loc}: {tr}" if loc else tr)
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})

engine = AuditEngine()
runner = MultiLLMCitationRunner()
rep_gen = ReportGenerator()
fix_gen = FixGenerator()
db = Database()

class AuditRequest(BaseModel):
    url: str
    sector: str = "general"

class CitationRequest(BaseModel):
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "İstanbul"
    live: bool = False
    lang: str = "tr"
    competitors: List[str] = []  # gerçek rakip domain'leri; boşsa kurgusal rakip enjekte edilmez

    @field_validator("lang")
    @classmethod
    def _banked_lang(cls, v: str) -> str:
        # E4: yalnız bankalanmış diller ölçülebilir — sessiz Türkçe fallback yalan olurdu.
        if v not in ("tr", "en"):
            raise ValueError("Kayıtlı dil bankası: tr, en")
        return v

    @field_validator("sector")
    @classmethod
    def _known_sector(cls, v: str) -> str:
        # Unknown sector used to surface as a 500 after the questions bank made
        # fallback loud (ValueError). Reject at the edge with a clean 422 instead.
        from answrank.citations.questions import SECTOR_QUESTIONS
        if v not in SECTOR_QUESTIONS:
            raise ValueError(f"Bilinmeyen sektör '{v}'; kayıtlı: {', '.join(sorted(SECTOR_QUESTIONS))}")
        return v

class FixRequest(BaseModel):
    domain: str
    brand_name: Optional[str] = None
    sector: str = "dental"
    city: str = "İstanbul"

class DeepAuditRequest(BaseModel):
    url: str
    sector: str = "general"
    brand_name: Optional[str] = None
    probe_waf: bool = True
    check_adversarial: bool = True
    check_grounding: bool = True
    check_rag: bool = True

class AdversarialScanRequest(BaseModel):
    url: Optional[str] = None
    html_content: Optional[str] = None

import json
import os
from fastapi.staticfiles import StaticFiles

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets"))
if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

@app.get("/", response_class=HTMLResponse)
def get_landing_page():
    """Tek bir landing_page kaydını döndürür; bulunamazsa None."""
    landing_path = os.path.join(TEMPLATE_DIR, "landing.html")
    if os.path.exists(landing_path):
        with open(landing_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>AnswRank Global GEO Engine</h1>")

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Tek bir dashboard kaydını döndürür; bulunamazsa None."""
    dash_path = os.path.join(TEMPLATE_DIR, "dashboard.html")
    if os.path.exists(dash_path):
        with open(dash_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>AnswRank AEO Dashboard</h1>")

@app.get("/health")
def health_check():
    """Servis canlılık uç noktası."""
    return {"status": "ok", "service": "answrank", "version": "1.0.0"}

@app.post("/api/audit", response_model=Dict[str, Any])
async def run_audit(req: AuditRequest):
    """Bir domain için denetim yürütür ve sonucu saklar."""
    try:
        res = await engine.audit_url(req.url, sector=req.sector)
        await db.save_audit(res)
        return {
            "audit_id": res.audit_id,
            "domain": res.domain,
            "overall_score": res.overall_score,
            "score_band": res.score_band,
            "lost_revenue_monthly_try": res.lost_revenue_estimate_monthly_try,
            "categories": res.categories.model_dump(),
            "recommendations": [r.model_dump() for r in res.recommendations],
            "crawl_warnings": res.crawl_warnings,
            "report_html_url": f"/reports/{res.audit_id}",
        }
    except Exception:
        logger.exception("audit backend failure")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)

@app.get("/reports/{audit_id}", response_class=HTMLResponse,
            responses={404: {"description": "Denetim raporu bulunamadı"}})
async def get_html_report(audit_id: str, agency_name: str | None = None,
                          agency_logo: str | None = None):
    """Tek bir html_report kaydını döndürür; bulunamazsa None."""
    record = await db.get_audit(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail="Denetim raporu bulunamadı")
    audit_obj = AuditResult.model_validate_json(record["raw_json"])
    # SoV dil-köprüsü: only rendered when a genuine citation run is stored for
    # this domain — otherwise the report explicitly says "ölçülmedi".
    cit = await db.get_latest_citations_for_domain(audit_obj.domain)
    _wl = {"name": agency_name, "logo_url": agency_logo} if agency_name else None
    html_content = rep_gen.to_html(audit_obj, citation=cit, white_label=_wl)
    return HTMLResponse(content=html_content)

@app.get("/api/citations/latest")
async def latest_citations(domain: str):
    """Latest REAL citation run for a domain (DB-backed). No run -> null;
    the UI must render "ÖLÇÜLMEDİ", never a fabricated placeholder."""
    cit = await db.get_latest_citations_for_domain(domain)
    if cit is None:
        return None
    return {
        "run_id": cit.run_id,
        "brand_name": cit.brand_name,
        "citation_rate_percentage": cit.citation_rate_percentage,
        "brand_citations_found": cit.brand_citations_found,
        "total_runs": cit.total_runs,
        "live_items_count": cit.live_items_count,
        "is_fully_live": cit.is_fully_live,
    }

@app.post("/api/citations")
async def run_citations(req: CitationRequest):
    """Çoklu LLM atıf ölçümü yürütür ve sonucu saklar."""
    try:
        res = await runner.run_citations(
            brand_name=req.brand_name,
            domain=req.domain,
            sector=req.sector,
            city=req.city,
            lang=req.lang,
            live=req.live,
            competitors=req.competitors,
        )
        await db.save_citations(res)
        # 16 Eyl P1: live/sim split must be visible on the PRIMARY response too,
        # not only the /latest bridge — a percentage without it is misreadable.
        return {
            "run_id": res.run_id,
            "brand_name": res.brand_name,
            "domain": res.domain,
            "sector": res.sector,
            "citation_rate_percentage": res.citation_rate_percentage,
            "citations_found": res.brand_citations_found,
            "total_runs": res.total_runs,
            "live_items_count": res.live_items_count,
            "live_response_rate_percentage": res.live_response_rate_percentage,
            "is_fully_live": res.is_fully_live,
            "top_competitors": res.top_competitors,
        }
    except Exception:
        logger.exception("citations backend failure")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)

@app.post("/api/fix")
def generate_fixes(req: FixRequest):
    """robots.txt, llms.txt ve JSON-LD düzeltme metinleri üretir."""
    brand = req.brand_name or req.domain
    return {
        "robots_txt": fix_gen.generate_robots_txt(req.domain),
        "llms_txt": fix_gen.generate_llms_txt(brand, req.domain, sector=req.sector, city=req.city),
        "llms_full_txt": fix_gen.generate_llms_full_txt(brand, req.domain, sector=req.sector, city=req.city),
        "json_ld": fix_gen.generate_json_ld(brand, req.domain, sector=req.sector, city=req.city),
    }

@app.get("/api/audits/recent")
async def list_recent_audits(limit: int = Query(default=10, le=50)):
    """recent_audits kayıtlarını listeler."""
    return await db.list_recent_audits(limit=limit)

from answrank.crm.qualifier import CandidateQualifier, CandidateProfile, IntakeResponse
from answrank.crm.objection import ObjectionHandler
from answrank.economics import EconomicsEngine, PricingTier
from answrank.legal.contract_generator import ContractGenerator, ClientLegalDetails, ContractMetadata
from answrank.audit.scenarios import ScenarioRouter
from answrank.crm.milestones import MilestonesEngine

@app.get("/api/audits/{audit_id}", responses={404: {"description": "Denetim kaydı bulunamadı."}})
async def get_audit_record(audit_id: str):
    """Stored audit by id (P1-5): previously no retrieval route existed, callers
    hand-parsed the DB where the column is `id` but the domain object calls it
    `audit_id` — the response normalizes both names."""
    row = await db.get_audit(audit_id)
    if not row:
        raise HTTPException(status_code=404,
                            detail="Denetim kaydı bulunamadı — uydurma veri üretilmez.")
    raw = row.pop("raw_json", None)
    result = json.loads(raw) if raw else dict(row)
    result["audit_id"] = result.get("audit_id") or row.get("id")
    return result

@app.post("/api/qualify")
def qualify_candidate(profile: CandidateProfile):
    """Adayın nitelik durumunu değerlendirir."""
    return CandidateQualifier.qualify_candidate(profile)

@app.post("/api/intake/score")
def score_intake(intake: IntakeResponse):
    """Gelen başvuruyu puanlar."""
    return CandidateQualifier.score_intake(intake)

class ObjectionRequest(BaseModel):
    objection_text: str
    company_name: str = "İşletmeniz"
    sector: str = "sağlık/hizmet"
    competitor_name: str = "en yakın rakibiniz"

@app.post("/api/objections")
def handle_objection(req: ObjectionRequest):
    """Bir satış itirazını karşılık stratejisiyle yanıtlar."""
    return ObjectionHandler.generate_rebuttal(
        text=req.objection_text,
        company_name=req.company_name,
        sector=req.sector,
        competitor_name=req.competitor_name,
    )

class ContractRequest(BaseModel):
    client: ClientLegalDetails
    meta: ContractMetadata

@app.post("/api/contract")
def generate_contract(req: ContractRequest):
    """Sözleşme taslağını marka ve bölge bilgileriyle oluşturur."""
    return ContractGenerator.generate_contract(client=req.client, meta=req.meta)

@app.get("/api/economics")
def get_economics(tier: PricingTier = PricingTier.MONTHLY_RETAINER, clients: int = 10):
    """Tek bir economics kaydını döndürür; bulunamazsa None."""
    economics = EconomicsEngine.evaluate_unit_economics(tier)
    projection = EconomicsEngine.project_portfolio(client_count=clients, primary_tier=tier)
    return {
        "packages": EconomicsEngine.PACKAGES,
        "selected_tier_metrics": economics,
        "portfolio_projection": projection,
    }

class ScenarioRequest(BaseModel):
    baseline_score: float
    current_score: float
    baseline_citations: int
    current_citations: int
    client_cooperation_ok: bool = True

@app.post("/api/scenarios")
def evaluate_scenario(req: ScenarioRequest):
    """Senaryo analizini yürütür."""
    return ScenarioRouter.evaluate(
        baseline_score=req.baseline_score,
        current_score=req.current_score,
        baseline_citations=req.baseline_citations,
        current_citations=req.current_citations,
        client_cooperation_ok=req.client_cooperation_ok,
    )

@app.get("/api/milestones")
def get_milestones(current_day: int = 15, active_clients: int = 3, current_mrr: float = 18000.0):
    """Tek bir milestones kaydını döndürür; bulunamazsa None."""
    return MilestonesEngine.evaluate_progress(
        current_day=current_day,
        active_clients=active_clients,
        current_mrr_try=current_mrr,
    )

from answrank.audit.waf_probe import WAFProbeEngine
from answrank.audit.rag_engine import RAGEngine
from answrank.citations.monte_carlo import MonteCarloEngine
from answrank.citations.multilingual import MultilingualSectorBank
from answrank.audit.entity_grounding import EntityGroundingEngine

class WAFProbeRequest(BaseModel):
    url: str

@app.post("/api/waf-probe")
async def probe_waf(req: WAFProbeRequest):
    """WAF/bot engelleme durumunu sondalar."""
    return await WAFProbeEngine.probe_url(req.url)

class RAGScoreRequest(BaseModel):
    url: str
    html_content: str
    questions: Optional[List[str]] = None
    sector: str = "dental"
    city: str = "İstanbul"

@app.post("/api/rag-score")
def evaluate_rag(req: RAGScoreRequest):
    """RAG erişilebilirlik değerlendirmesi yürütür."""
    if not req.questions:
        from answrank.citations.questions import SectorQuestionsBank
        questions = SectorQuestionsBank.get_questions(req.sector, city=req.city)
    else:
        questions = req.questions
    return RAGEngine.evaluate_content_rag(req.url, req.html_content, questions)

class MonteCarloRequest(BaseModel):
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "İstanbul"
    iterations: int = 3

@app.post("/api/citations/monte-carlo")
async def evaluate_monte_carlo(req: MonteCarloRequest):
    """Monte Carlo varyans simülasyonunu yürütür."""
    return await MonteCarloEngine.evaluate_stochastic_stability(
        brand_name=req.brand_name,
        domain=req.domain,
        sector=req.sector,
        city=req.city,
        iterations=req.iterations,
    )

@app.get("/api/questions/multilingual")
def get_multilingual_questions(sector: str = "dental", language: str = "en", city: str = "Istanbul"):
    """Tek bir multilingual_questions kaydını döndürür; bulunamazsa None."""
    questions = MultilingualSectorBank.get_questions(sector=sector, language=language, city=city)
    return {"sector": sector, "language": language, "city": city, "count": len(questions), "questions": questions}

class EntityGroundRequest(BaseModel):
    brand_name: str
    domain: str
    html_content: Optional[str] = None

@app.post("/api/entity-ground")
async def evaluate_entity_grounding(req: EntityGroundRequest):
    """Varlık knowledge-grounding değerlendirmesi yürütür."""
    return await EntityGroundingEngine.evaluate_grounding(
        brand_name=req.brand_name,
        domain=req.domain,
        html_content=req.html_content,
    )

@app.post("/api/audit/deep")
async def run_deep_audit(req: DeepAuditRequest):
    """Derin denetim pipeline'ını başlatır."""
    try:
        deep_res = await engine.audit_url_deep(
            url=req.url,
            sector=req.sector,
            brand_name=req.brand_name,
            probe_waf=req.probe_waf,
            check_adversarial=req.check_adversarial,
            check_grounding=req.check_grounding,
            check_rag=req.check_rag,
        )
        await db.save_audit(deep_res.base_audit)
        return deep_res.model_dump()
    except Exception:
        logger.exception("audit backend failure")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# ---------------------------------------------------------------------------
# Background job API: long-running operations (deep audit, monte-carlo,
# swarm) submitted as async jobs with progress polling and SSE streaming.
# Complements the existing synchronous endpoints — no behavior change there.
# ---------------------------------------------------------------------------

from answrank.api.jobs import job_manager, Job
from fastapi.responses import StreamingResponse
import asyncio as _asyncio
import json as _json


@app.post("/api/jobs/deep-audit")
async def submit_deep_audit_job(req: DeepAuditRequest):
    """Runs a 360° deep audit in the background; returns job_id immediately."""

    async def _work(job: Job):
        job_manager.report_progress(job, 0.05, "Fetching page + auxiliary assets")
        deep_res = await engine.audit_url_deep(
            url=req.url,
            sector=req.sector,
            brand_name=req.brand_name,
            probe_waf=req.probe_waf,
            check_adversarial=req.check_adversarial,
            check_grounding=req.check_grounding,
            check_rag=req.check_rag,
        )
        job_manager.report_progress(job, 0.85, "Persisting audit")
        await db.save_audit(deep_res.base_audit)
        job_manager.report_progress(job, 0.95, "Finalizing")
        return deep_res.model_dump()

    job_id = await job_manager.submit("deep-audit", _work)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}", "stream_url": f"/api/jobs/{job_id}/stream"}


class MonteCarloJobRequest(BaseModel):
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "İstanbul"
    iterations: int = 5


@app.post("/api/jobs/monte-carlo")
async def submit_monte_carlo_job(req: MonteCarloJobRequest):
    """Runs stochastic citation-stability Monte Carlo in the background."""

    async def _work(job: Job):
        job_manager.report_progress(job, 0.1, "Warming citation runner")
        mc_engine = MonteCarloEngine()
        res = await mc_engine.evaluate_stochastic_stability(
            brand_name=req.brand_name,
            domain=req.domain,
            iterations=req.iterations,
        )
        job_manager.report_progress(job, 0.9, "Computing stability index")
        return res.model_dump()

    job_id = await job_manager.submit("monte-carlo", _work)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}", "stream_url": f"/api/jobs/{job_id}/stream"}


@app.get("/api/jobs/{job_id}", responses={404: {"description": "İş bulunamadı."}})
async def get_job_status(job_id: str):
    """Tek bir job_status kaydını döndürür; bulunamazsa None."""
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="İş bulunamadı")
    return job.public_view()


@app.get("/api/jobs")
async def list_jobs():
    """Lists recent jobs (bounded by the retention window), newest first."""
    jobs = sorted(job_manager._jobs.values(), key=lambda j: j.created_at, reverse=True)
    return [j.public_view() for j in jobs[:50]]


@app.get("/api/jobs/{job_id}/stream", responses={404: {"description": "İş bulunamadı."}})
async def stream_job(job_id: str):
    """SSE live progress stream for a background job."""
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="İş bulunamadı")

    queue = await job_manager.subscribe(job_id)

    async def event_generator():
        """Olay akışını üretilen JSON olayları olarak yayar."""
        try:
            # First, emit the current snapshot
            yield f"data: {_json.dumps(job.public_view(), ensure_ascii=False)}\n\n"
            while True:
                try:
                    payload = await _asyncio.wait_for(queue.get(), timeout=25.0)
                except _asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if payload.get("event") == "done":
                    final = job_manager.get(job_id)
                    if final:
                        yield f"data: {_json.dumps(final.public_view(), ensure_ascii=False)}\n\n"
                    break
                yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            job_manager.unsubscribe(job_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/audit/adversarial")
async def scan_adversarial(req: AdversarialScanRequest):
    """Düşmanca tarama (manipülasyon testi) yürütür."""
    from bs4 import BeautifulSoup
    from answrank.audit.adversarial import AdversarialAnalyzer
    analyzer = AdversarialAnalyzer()
    if req.html_content:
        soup = BeautifulSoup(req.html_content, "html.parser")
        return analyzer.analyze(soup, raw_html=req.html_content).model_dump()
    elif req.url:
        crawl_data = await engine.crawler.fetch(req.url)
        soup = BeautifulSoup(crawl_data.html_content, "html.parser")
        return analyzer.analyze(soup, raw_html=crawl_data.html_content).model_dump()
    else:
        raise HTTPException(status_code=400, detail="Url veya html_content sağlanmalı.")

class SwarmRunRequest(BaseModel):
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "London"
    country: str = "UK"
    currency: str = "GBP"
    ticket_size: float = 2500.0

@app.post("/api/swarm/run")
async def run_swarm_pipeline(req: SwarmRunRequest):
    """Swarm pipeline'ını uçtan uca yürütür."""
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()
    candidate = orch.seed_target(
        brand_name=req.brand_name,
        domain=req.domain,
        sector=req.sector,
        city=req.city,
        country=req.country,
        currency=req.currency,
        ticket_size=req.ticket_size,
    )
    result = await orch.run_full_pipeline_sync(candidate)
    return result.model_dump()

@app.get("/api/swarm/candidates")
async def list_swarm_candidates_api(limit: int = Query(default=20, le=50)):
    # Constructed per request so the DB path follows settings at request time,
    # matching the SwarmOrchestrator() instances that WRITE these rows.
    """swarm_candidates_api kayıtlarını listeler."""
    return await Database().list_swarm_candidates(limit=limit)

class ScoutRequest(BaseModel):
    sector: str = "dental"
    city: str = "London"
    country: str = "UK"

@app.post("/api/swarm/scout")
async def trigger_swarm_scout(req: ScoutRequest):
    """Agent 01 (Radar / Scout) seeds the pipeline from a CURATED demo target pool.

    HONEST SCOPE: this is NOT autonomous live lead discovery — it seeds a small,
    curated pool of well-known sector players with heuristic (not measured) ticket
    estimates so the operator can start the pipeline and audit it end-to-end. The
    response carries `source: "curated_demo_pool"` and the dashboard labels it the
    same way. Real directory discovery (Google Business / Maps APIs) is a separate,
    unimplemented integration. For genuine prospects, use the manual seed path
    (`/api/swarm/run`) which the DM campaign workflow feeds from.
    """
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()

    # CURATED DEMO POOL — all brands/domains below are FICTIONAL and use the
    # RFC 2606 reserved `.example` TLD so no pipeline step can ever probe,
    # pitch or invoice a real third-party business by accident.
    curated_seed_targets = {
        ("dental", "UK"): [
            ("Meridian Dental Studio", "meridian-dental.example", 2500.0, "GBP"),
            ("Northgate Smile Practice", "northgate-smile.example", 2200.0, "GBP"),
            ("Bayswater Bright Dental", "bayswater-bright.example", 3000.0, "GBP"),
        ],
        ("dental", "TR"): [
            ("Meridyen Diş Grubu Maslak", "meridyen-dental.example", 35000.0, "TRY"),
            ("Pervane Ağız Sağlığı Nişantaşı", "pervane-agiz.example", 28000.0, "TRY"),
            ("Lale Dental Akademi", "lale-dental.example", 32000.0, "TRY"),
        ],
        ("aesthetic", "TR"): [
            ("Vela Estetik Grubu", "vela-estetik.example", 45000.0, "TRY"),
            ("Cihan Saç & Estetik Merkezi", "cihan-estetik.example", 38000.0, "TRY"),
        ],
        ("dental", "DE"): [
            ("Elbtal Zahnklinik", "elbtal-zahn.example", 2800.0, "EUR"),
            ("Marienplatz Zahnpraxis", "marienplatz-zahn.example", 2400.0, "EUR"),
        ],
        ("dental", "US"): [
            ("Harbor Bluff Dental Center", "harborbluff-dental.example", 4500.0, "USD"),
            ("Empire Ridge Specialty Dental", "empireridge-dental.example", 3800.0, "USD"),
        ],
    }
    
    key = (req.sector, req.country)
    targets = curated_seed_targets.get(key, [
        (f"{req.city} Demo {req.sector.title()} Center", f"{req.city.lower().replace(' ', '-')}-demo-{req.sector}.example", 2500.0, "USD")
    ])
    
    discovered = []
    for brand, domain, ticket, curr in targets:
        cand = orch.seed_target(
            brand_name=brand,
            domain=domain,
            sector=req.sector,
            city=req.city,
            country=req.country,
            currency=curr,
            ticket_size=ticket,
        )
        orch.scout.qualify(cand)
        orch.persist_candidate(cand)
        discovered.append(cand.model_dump())
        
    return {
        "sector": req.sector, "city": req.city, "country": req.country,
        "count": len(discovered), "candidates": discovered,
        "source": "curated_demo_pool",
        "note": "Küratörlü demo hedef havuzu — TÜM marka/domainler kurgusaldır (.example). Canlı dizin keşfi (Google Business/Maps API) henüz entegre edilmedi; bilet değerleri heuristik tahmindir.",
    }

@app.post("/api/swarm/candidates/{cand_id}/run", responses={404: {"description": "Aday bulunamadı."}})
async def run_candidate_pipeline(cand_id: str):
    """Tek aday için pipeline adımlarını yürütür."""
    from answrank.agents.swarm import SwarmOrchestrator, SwarmCandidate
    orch = SwarmOrchestrator()
    cand_data = await Database().get_swarm_candidate(cand_id)
    if not cand_data:
        raise HTTPException(status_code=404, detail="Aday bulunamadı")
    
    cand = orch.pool.get(cand_id)
    if not cand:
        cand = SwarmCandidate(**cand_data)
        orch.pool[cand.id] = cand
        
    result = await orch.run_full_pipeline_sync(cand)
    return result.model_dump()

class SentimentApiRequest(BaseModel):
    brand_name: str
    raw_text: str
    sector: str = "dental"
    domain: str = ""

@app.post("/api/sentiment")
def evaluate_sentiment_api(req: SentimentApiRequest):
    """Marka sentiment değerlendirmesi yürütür."""
    from answrank.citations.sentiment import SentimentAnalyzer
    analyzer = SentimentAnalyzer()
    res = analyzer.analyze(
        raw_response=req.raw_text,
        brand_name=req.brand_name,
        domain=req.domain,
        sector=req.sector,
    )
    return res.model_dump()

class DeployApiRequest(BaseModel):
    brand_name: str
    domain: str
    target: str = "local"
    sector: str = "dental"
    city: str = "London"
    output_dir: Optional[str] = "./dist_aeo"
    webhook_url: Optional[str] = None
    secret: Optional[str] = "answrank-secret"
    wp_url: Optional[str] = None
    wp_user: Optional[str] = None
    wp_pass: Optional[str] = None

@app.post("/api/deploy")
async def deploy_assets_api(req: DeployApiRequest):
    """Dağıtım hedefine varlıkları gönderir."""
    from answrank.integrations.deployer import CMSDeployer
    from answrank.reporting.fix_generator import FixGenerator
    fix_gen = FixGenerator()
    fixes = {
        "robots.txt": fix_gen.generate_robots_txt(req.domain),
        "llms.txt": fix_gen.generate_llms_txt(req.brand_name, req.domain, sector=req.sector, city=req.city),
        "schema.jsonld": fix_gen.generate_json_ld(req.brand_name, req.domain, sector=req.sector, city=req.city),
    }
    if req.target == "local":
        res = CMSDeployer.export_local_bundle(req.output_dir or "./dist_aeo", fixes)
    elif req.target == "webhook":
        if not req.webhook_url:
            raise HTTPException(status_code=400, detail="Webhook dağıtımı için webhook_url zorunludur")
        res = await CMSDeployer.deploy_webhook(req.webhook_url, req.secret or "answrank-secret", {"brand": req.brand_name, "fixes": fixes})
    elif req.target == "wordpress":
        if not req.wp_url or not req.wp_user or not req.wp_pass:
            raise HTTPException(status_code=400, detail="WordPress dağıtımı için wp_url, wp_user ve wp_pass zorunludur")
        res = await CMSDeployer.deploy_wordpress(req.wp_url, req.wp_user, req.wp_pass, fixes)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported target {req.target}")

    return res.model_dump()

@app.get("/api/telemetry")
def get_llm_telemetry_api():
    """Tek bir llm_telemetry_api kaydını döndürür; bulunamazsa None."""
    from answrank.citations.key_manager import HybridKeyManager
    mgr = HybridKeyManager()
    return mgr.get_telemetry_report()

@app.get("/api/fiscal-report")
def get_fiscal_report_api():
    """Tek bir fiscal_report_api kaydını döndürür; bulunamazsa None."""
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()
    summary = orch.get_fiscal_report().model_dump()
    # The dashboard table binds to `records` + per-record `fx_source`; expose the
    # invoice lines and the rate provenance instead of silently returning an
    # empty table on every fresh process.
    summary["records"] = [r.model_dump() for r in orch.tax_ledger.records]
    summary["fx_source"] = orch.tax_ledger.fx_source
    summary["fx_rates"] = orch.tax_ledger.rates
    summary["persist_error"] = orch.tax_ledger.last_persist_error
    return summary

@app.get("/api/territory-locks")
def get_territory_locks_api():
    """Tek bir territory_locks_api kaydını döndürür; bulunamazsa None."""
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()
    return [l.model_dump() for l in orch.get_territory_locks()]

@app.get("/api/swarm/stream")
async def stream_swarm_execution(brand: str, domain: str, city: str = "London", country: str = "UK"):
    """Runs the REAL 5-agent pipeline and streams genuine progress events via SSE.

    Every message corresponds to an actually executed agent step — no fabricated
    baselines or canned messages.
    """
    from fastapi.responses import StreamingResponse
    import json
    import asyncio
    from datetime import datetime, timezone
    from answrank.agents.swarm import SwarmOrchestrator

    orch = SwarmOrchestrator()
    candidate = orch.seed_target(
        brand_name=brand,
        domain=domain,
        city=city,
        country=country,
    )

    async def event_generator():
        """Olay akışını üretilen JSON olayları olarak yayar."""
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(agent: str, message: str) -> None:
            """Gelen olayı işleyip abonelere dağıtır."""
            payload = json.dumps(
                {"agent": agent, "message": message, "timestamp": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
            )
            await queue.put(f"data: {payload}\n\n")

        async def run_pipeline() -> None:
            """Olay pipeline'ını adımlarıyla yürütür."""
            try:
                await orch.run_full_pipeline_sync(candidate, on_event=on_event)
                final = json.dumps(
                    {
                        "agent": "PIPELINE_DONE",
                        "message": f"Pipeline finished: {candidate.brand_name} -> {candidate.stage.value}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
                await queue.put(f"data: {final}\n\n")
            except Exception as exc:
                err = json.dumps(
                    {
                        "agent": "PIPELINE_ERROR",
                        "message": f"Pipeline failed: {type(exc).__name__}: {exc}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
                await queue.put(f"data: {err}\n\n")
            finally:
                await queue.put(None)  # sentinel

        runner_task = asyncio.create_task(run_pipeline())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

        await runner_task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class TerritoryCheckRequest(BaseModel):
    city: str
    niche: str = "dental"
    country: str = "UK"
    domain: Optional[str] = None

@app.post("/api/territory-locks/check")
def check_territory_lock_api(req: TerritoryCheckRequest):
    """Bölge münhasırlık kilidini sorgular.

    Aday domain sorgunun girdisidir; kurgusal bir varsayılanla doldurulmaz —
    yoksa boş istek 'example.com' adına bölge sorgular."""
    if not req.domain or not req.domain.strip():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail="Aday domain belirtilmelidir; bölge kilidi boş domain ile sorgulanamaz.",
        )
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()
    check = orch.exclusivity.check_conflict(
        country=req.country,
        city=req.city,
        niche=req.niche,
        candidate_domain=req.domain.strip(),
    )
    if check.has_conflict and check.existing_lock:
        return {
            "locked": True,
            "brand_name": check.existing_lock.brand_name,
            "client_domain": check.existing_lock.client_domain,
            "city": req.city,
            "niche": req.niche,
            "country": req.country,
            "message": check.conflict_reason or "Territory exclusively locked by active client."
        }
    return {
        "locked": False,
        "city": req.city,
        "niche": req.niche,
        "country": req.country,
        "message": "Territory is currently open for exclusive single-leader representation."
    }

class ArtifactPreviewRequest(BaseModel):
    brand_name: str = "Meridyen Diş Kliniği"  # fictional default (RFC 2606 .example — never a real business)
    domain: str = "meridyen-klinik.example"
    sector: str = "dental"
    city: str = "London"

@app.post("/api/artifacts/preview")
def preview_artifacts_api(req: ArtifactPreviewRequest):
    """robots.txt/llms.txt/JSON-LD önizlemesi üretir."""
    from answrank.reporting.fix_generator import FixGenerator
    fix_gen = FixGenerator()
    return {
        "robots_txt": fix_gen.generate_robots_txt(req.domain),
        "llms_txt": fix_gen.generate_llms_txt(req.brand_name, req.domain, sector=req.sector, city=req.city),
        "schema_jsonld": fix_gen.generate_json_ld(req.brand_name, req.domain, sector=req.sector, city=req.city),
    }

class LeadInquiryRequest(BaseModel):
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "İstanbul"
    country: str = "TR"
    email_or_phone: str
    notes: Optional[str] = ""

@app.post("/api/inquiry")
async def register_lead_inquiry_api(req: LeadInquiryRequest):
    """Gelen başvuruyu kaydeder ve bölgeyi geçici kilitler."""
    import hashlib, time
    from answrank.agents.swarm import SwarmOrchestrator
    orch = SwarmOrchestrator()
    cand = orch.seed_target(
        brand_name=req.brand_name,
        domain=req.domain,
        sector=req.sector,
        city=req.city,
        country=req.country,
    )
    orch.scout.qualify(cand)
    orch.persist_candidate(cand)
    ref_code = "ANSW-LK-" + hashlib.sha256(f"{req.domain}{time.time()}".encode()).hexdigest()[:4].upper()
    return {
        "status": "success",
        "reservation_code": ref_code,
        "brand_name": req.brand_name,
        "domain": req.domain,
        "city": req.city,
        "country": req.country,
        "message": "Territory reservation request received and priority audit queued."
    }






# ---------------------------------------------------------------------------
# E3 herkese-açık mini-probe (D-16.09-M) — ücretsiz 3 satırlık AI-erişim kartı.

_miniprobe_hits: dict = {}


class MiniProbeRequest(BaseModel):
    domain: str = Field(min_length=3)


@app.post("/api/miniprobe")
async def mini_probe_public(req: MiniProbeRequest, request: Request):
    """Herkese-açık mini-probe: robots + llms + 3-bot örnek probe.

    Bu bir SKOR değil, üç satırlık erişim kartıdır; ölçülemeyen hiçbir satır
    suçlamaya dönüşmez (P0-1 sözleşmesinin public yüzeydeki uygulaması).
    IP başına 24 saatlik kota `mini_probe_daily_limit_per_ip`'dir.
    """
    import time as _time
    from answrank.probe.miniprobe import MiniProbe
    ip = request.client.host if request.client else "anonymous"
    now = _time.time()
    bucket = [t for t in _miniprobe_hits.get(ip, []) if now - t < 86400]
    if len(bucket) >= settings.mini_probe_daily_limit_per_ip:
        raise HTTPException(status_code=429, detail=(
            "24 saatlik ücretsiz mini-probe limitiniz doldu — tam 360° denetim "
            "için formu doldurun; mini-probe kotası her gün yenilenir."))
    bucket.append(now)
    _miniprobe_hits[ip] = bucket
    try:
        result = await MiniProbe.run(req.domain)
    except Exception:
        logger.exception("miniprobe backend failure")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)
    # E7 huni: geçerli site yoklaması lead'se kaydedilir (GİRİŞ REDDEDİLDİ değil;
    # IP tutulmaz — tablo yalnız domain + ölçümlü üç satır taşır).
    await db.save_miniprobe_lead(result)
    return result.model_dump()


class QueueDecision(BaseModel):
    action: Literal["approve", "reject"]
    note: str = ""


@app.get("/api/queue")
async def queue_pending():
    """Onra bekleyen kuyruk maddelerini listeler."""
    from answrank.queue import ApprovalQueue
    return {"items": ApprovalQueue(db=db).pending()}


@app.post("/api/queue/{item_id}/decision", responses={404: {"description": "Kuyruk maddesi bulunamadı."}})
async def queue_decide(item_id: int, req: QueueDecision):
    """Bir kuyruk maddesine karar verir (approve/reject)."""
    from answrank.queue import ApprovalQueue
    try:
        return ApprovalQueue(db=db).decide(item_id, approve=req.action == "approve",
                                           note=req.note)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail="Kuyruk maddesi yok — uydurma karar işlenmez.")
    except ValueError:
        raise HTTPException(status_code=409,
                            detail="Bu maddeye karar zaten verilmiş — çift karar yok.")


@app.get("/api/payments/channels")
async def payment_channels():
    """E11 — tahsilat kanallarının dürüst durumu (PSP yoksa 'yapılandırılmamış')."""
    from answrank.finance.payments import PaymentProvider, PaymentService
    from answrank.finance.tax_ledger import TaxLedger
    svc = PaymentService(db=db, ledger=TaxLedger(load_persisted=False))
    return {"channels": {p.value: svc.provider_status(p) for p in PaymentProvider}}


@app.get("/api/leads")
async def list_probe_leads():
    """Tek-kiracılık admin yüzeyi: mini-probe lead'leri (en yeni 50)."""
    return {"leads": db.list_miniprobe_leads()}


# ---------------------------------------------------------------------------
# E1 GEO İzleme yüzeyi (D-16.09-M karar 4) — ayrı MRR kademesi + Madde-7 ölçüm altyapısı.

class MonitorCreate(BaseModel):
    domain: str = Field(min_length=3)
    brand: str = Field(min_length=2)
    sector: str = "general"
    cadence_days: int = Field(default=30, ge=1, le=90)
    contract_id: Optional[str] = None

    @field_validator("sector")
    @classmethod
    def _sector_in_banks(cls, v: str) -> str:
        from answrank.citations.questions import SECTOR_QUESTIONS
        if v not in SECTOR_QUESTIONS:
            raise ValueError(f"Kayıtlı sektör bankaları: {', '.join(sorted(SECTOR_QUESTIONS))}")
        return v


def _monitor_service():
    from answrank.monitor.service import MonitorService
    return MonitorService(db=db)


@app.post("/api/monitors")
async def create_monitor(req: MonitorCreate):
    """Yeni bir monitor kaydı oluşturur."""
    mid = _monitor_service().add(domain=req.domain, brand=req.brand, sector=req.sector,
                                 cadence_days=req.cadence_days, contract_id=req.contract_id)
    return {"monitor_id": mid, "domain": req.domain, "sector": req.sector,
            "message": "İzleme kaydı açıldı — ilk ölçüm için POST /api/monitors/%s/run" % mid}


@app.get("/api/monitors")
async def list_monitors():
    """monitors kayıtlarını listeler."""
    return {"monitors": _monitor_service().list()}


@app.post("/api/monitors/{monitor_id}/run", responses={404: {"description": "İzleme kaydı bulunamadı — uydurma ölçüm yapılmaz."}})
async def run_monitor(monitor_id: str):
    """İzleme ölçümü yürütür."""
    from answrank.monitor import service as _ms
    svc = _monitor_service()
    m = svc.db.get_monitor(monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="İzleme kaydı bulunamadı — uydurma ölçüm yapılmaz.")
    try:
        run_id = await svc.run_one(monitor_id, executor=_ms.live_executor)
    except Exception:
        logger.exception("monitor run failure")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)
    last = svc.db.monitor_runs(monitor_id)[-1]
    return {"run_id": run_id, "status": last["status"], "score_base": last["score_base"],
            "sov_pct": last["sov_pct"],
            "note": "score yalnız MEASURED koşulunda doludur; UNAUDITABLE satırı suçlama değil."}


@app.get("/api/monitors/{monitor_id}/fulfillment", responses={404: {"description": "İzleme kaydı bulunamadı — uydurma ölçüm yapılmaz."}})
async def monitor_fulfillment(monitor_id: str):
    """Madde-7 delta garantisi teslimat kanıtını değerlendirir."""
    from answrank.monitor.fulfillment import FulfillmentEvaluator
    try:
        return FulfillmentEvaluator(db=db).evaluate(monitor_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="İzleme kaydı yok — fulfillment hükmü uydurulmaz.")


@app.get("/api/monitors/{monitor_id}/digest", responses={404: {"description": "İzleme kaydı bulunamadı — uydurma ölçüm yapılmaz."}})
async def monitor_digest(monitor_id: str):
    """İzleme özet raporu üretir."""
    try:
        return _monitor_service().digest(monitor_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="İzleme kaydı bulunamadı — uydurma digest üretilmez.")
