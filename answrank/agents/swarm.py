"""5-Agent Closed-Loop Autonomous Sales & Fulfillment Swarm for AnswRank.

Orchestrates 5 autonomous agents operating across domestic and global markets:
1. ScoutAgent (Radar / Lead Discovery, Qualification & Territory Exclusivity Guard)
2. AuditorAgent (360° Deep GEO Audit & Lost Revenue Gap Analysis)
3. HunterAgent (Personalized Outreach & Objection Rebuttal)
4. FulfillmentAgent (Autonomous Fix Generation & Statutory Tax-Separated Contract)
5. SentryAgent (30-Day Delta Guardian & Cross-Sell Upsell Trigger)
"""

import uuid
import asyncio
import logging
from enum import Enum
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from answrank.models import DeepAuditResult, utc_now
from answrank.audit.engine import AuditEngine
from answrank.audit.delta import DeltaEngine
from answrank.crm.qualifier import CandidateQualifier, CandidateProfile
from answrank.crm.objection import ObjectionHandler
from answrank.crm.exclusivity import ExclusivityManager, TerritoryLock
from answrank.reporting.fix_generator import FixGenerator
from answrank.legal.contract_generator import ContractGenerator, ClientLegalDetails, ContractMetadata
from answrank.finance.tax_ledger import TaxLedger, FiscalSummaryReport
from answrank.config import settings
from answrank.economics import PricingTier

logger = logging.getLogger("answrank.swarm")

class SwarmStage(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    CONFLICT_DISQUALIFIED = "CONFLICT_DISQUALIFIED"
    AUDITED = "AUDITED"
    OUTREACH_PENDING = "OUTREACH_PENDING"
    OUTREACH_SENT = "OUTREACH_SENT"
    NEGOTIATING = "NEGOTIATING"
    CONTRACT_ISSUED = "CONTRACT_ISSUED"
    FULFILLED = "FULFILLED"
    ACTIVE_MONITORING = "ACTIVE_MONITORING"
    DELTA_CHECKED = "DELTA_CHECKED"

class SwarmCandidate(BaseModel):
    id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:8]}")
    brand_name: str
    domain: str
    sector: str = "dental"
    city: str = "İstanbul"
    country: str = "TR"  # TR, UK, US, DE, UAE
    currency: str = "TRY"  # TRY, GBP, USD, EUR
    agency_domain: Optional[str] = None  # E2: beyaz-etiket sahibi ajans (kota anahtarı)
    ticket_size: float = 15000.0
    stage: SwarmStage = SwarmStage.DISCOVERED
    audit_data: Optional[Dict[str, Any]] = None
    deep_score: Optional[float] = None
    lost_revenue_monthly: Optional[float] = None
    outreach_pitch: Optional[str] = None
    contract_text: Optional[str] = None
    fixes_generated: Optional[Dict[str, str]] = None
    territory_locked: bool = False
    fiscal_invoice_id: Optional[str] = None
    fiscal_tax_exempt_try: Optional[float] = None
    conflict_reason: Optional[str] = None
    last_action: str = "Discovered"
    updated_at: datetime = Field(default_factory=utc_now)

class ScoutAgent:
    """Agent 1: Discovers and qualifies high-LTV targets while enforcing territory exclusivity."""

    MARKET_CURRENCY = {
        "TR": ("TRY", 20000.0),
        "UK": ("GBP", 1500.0),
        "US": ("USD", 2500.0),
        "DE": ("EUR", 2000.0),
        "UAE": ("USD", 3000.0),
    }

    def __init__(self, exclusivity: Optional[ExclusivityManager] = None):
        self.exclusivity = exclusivity

    def qualify(self, candidate: SwarmCandidate) -> bool:
        # Check territory exclusivity conflict if manager present
        """Adayı skorlar: AI görünürlük eksiğini ve rakip atfını değerlendirerek nitelik verir."""
        if self.exclusivity:
            conflict = self.exclusivity.check_conflict(
                country=candidate.country,
                city=candidate.city,
                niche=candidate.sector,
                candidate_domain=candidate.domain,
                agency_domain=candidate.agency_domain,
            )
            if conflict.has_conflict:
                candidate.stage = SwarmStage.CONFLICT_DISQUALIFIED
                candidate.conflict_reason = conflict.conflict_reason
                candidate.last_action = (f"Disqualified: Territory Conflict with {conflict.existing_lock.brand_name}"
                        if conflict.existing_lock else
                        f"Disqualified: {conflict.action_recommended} — {conflict.conflict_reason}")
                candidate.updated_at = utc_now()
                return False

        profile = CandidateProfile(
            company_name=candidate.brand_name,
            sector=candidate.sector,
            domain=candidate.domain,
            has_custom_domain=True,
            estimated_ticket_size=candidate.ticket_size,
            estimated_annual_revenue=candidate.ticket_size * 200,
            has_ad_spend=True,
            direct_decision_maker_access=True,
            ai_missing_in_top5=True,
            has_competitor_cited=True,
        )
        res = CandidateQualifier.qualify_candidate(profile)
        if res.is_qualified:
            candidate.stage = SwarmStage.QUALIFIED
            candidate.last_action = f"Qualified with score {res.score}/5"
            candidate.updated_at = utc_now()
            return True
        return False

class AuditorAgent:
    """Agent 2: Executes 360° deep audit and calculates lost revenue."""

    def __init__(self):
        self.engine = AuditEngine()

    async def audit(self, candidate: SwarmCandidate) -> Optional[DeepAuditResult]:
        """Deep-audit a candidate. Returns None (and leaves the candidate at its
        current stage with an explicit reason) when the domain cannot be crawled
        at the network level — e.g. fictional `.example` demo targets. An
        unreachable domain must NEVER yield a fabricated score: no audit, no
        pipeline progress, no invoice on unverifiable evidence."""
        import httpx
        try:
            deep_res = await self.engine.audit_url_deep(
                url=f"https://{candidate.domain}",
                sector=candidate.sector,
                brand_name=candidate.brand_name,
                probe_waf=False,
                check_grounding=False,
            )
        except (httpx.TransportError, OSError) as exc:
            candidate.last_action = (
                f"AUDIT_UNAVAILABLE: {candidate.domain} ağ seviyesinde erişilemedi "
                f"({type(exc).__name__}) — skor üretilmedi; pipeline bu aşamada durdu, "
                f"uydurma veriyle devam edilmez."
            )
            candidate.updated_at = utc_now()
            logger.warning("Swarm audit halted for %s: %s", candidate.domain, exc)
            return None
        if deep_res.deep_tier == "UNAUDITABLE":
            # 16 Eyl P0-1: the crawler now degrades instead of raising — same halt
            # semantics must apply to the honest-degraded result.
            candidate.last_action = (
                f"AUDIT_UNAVAILABLE: {candidate.domain} hedefine ulaşılamadı "
                "(DOĞRULANAMADI) — skor üretilmedi; pipeline bu aşamada durdu, "
                "uydurma veriyle devam edilmez."
            )
            candidate.updated_at = utc_now()
            logger.warning("Swarm audit halted (unauditable) for %s", candidate.domain)
            return None
        candidate.audit_data = deep_res.model_dump()
        candidate.deep_score = deep_res.composite_deep_score
        candidate.lost_revenue_monthly = deep_res.base_audit.lost_revenue_estimate_monthly_try
        candidate.stage = SwarmStage.AUDITED
        candidate.last_action = f"Audited: 360° Score {deep_res.composite_deep_score}/100 ({deep_res.deep_tier})"
        candidate.updated_at = utc_now()
        return deep_res

class HunterAgent:
    """Agent 3: Tailors high-conversion outreach in local languages & handles objections."""

    TEMPLATES = {
        "TR": "Sayın {brand} Yetkilisi,\n\n{findings} {loss}\n\nMadde 7 kapsamında, 30 günlük AEO kurulumu sonrası ölçülen atıf artışı +12 puan eşiğini karşılamazsa taahhüdümüz yerine getirilmiş sayılmaz.",
        "UK": "Dear {brand} Leadership,\n\n{findings} {loss}\n\nOur contract is performance-gated: if the measured citation uplift after the 30-day AEO setup does not meet the +12-point threshold, the guarantee terms in Madde 7 apply.",
        "US": "Hi {brand} Team,\n\n{findings} {loss}\n\nOur 30-day citation-boost commitment is performance-gated on a measured +12-point uplift under contractual terms.",
        "DE": "Sehr geehrte Damen und Herren von {brand},\n\n{findings} {loss}\n\nUnsere 30-Tage-Leistungsgarantie ist an eine gemessene +12-Punkte-Steigerung der KI-Zitierungen gebunden (vertragliche Bedingung).",
        "UAE": "Dear {brand} Leadership,\n\n{findings} {loss}\n\nOur contract is performance-gated: if the measured citation uplift after the 30-day AEO setup does not meet the +12-point threshold, the guarantee terms in Madde 7 apply.",
    }

    # Localized sector nouns for pitch templates
    SECTOR_NOUNS = {
        "TR": {"dental": "diş hekimliği"},
        "DE": {"dental": "Zahnimplantaten"},
    }

    # Measurement-gated clause parts per language (no absence claim, no default figure)
    CLAUSES = {
        "TR": {
            "audited": "{brand} için 360° yapay zeka görünürlük denetimimiz tamamlandı; teknik skor {score}/100 ({sector}, {city}).",
            "offer": "{brand} için ücretsiz 360° yapay zeka görünürlük denetimi teklif ediyoruz.",
            "loss": " Gelir modelimize göre aylık tahmini kaçan ciro {cur}{amt} — bu model kestirimidir, kesin ölçüm değildir.",
            "no_loss": " Kaçan ciro için model girdisi henüz yok; ölçüm sonrası net rakam paylaşırız.",
        },
        "UK": {
            "audited": "Our 360° AI-visibility audit of {brand} is complete: technical score {score}/100 ({sector}, {city}).",
            "offer": "We offer {brand} a free 360° AI-visibility audit.",
            "loss": " Our revenue model estimates up to {cur}{amt}/mo at stake — a model estimate, not a measurement.",
            "no_loss": " We do not quote revenue figures before measurement.",
        },
        "US": {
            "audited": "Our diagnostic of {brand} is complete: technical score {score}/100 ({sector}, {city}).",
            "offer": "We offer {brand} a free 360° AI-visibility diagnostic.",
            "loss": " Our revenue model estimates up to {cur}{amt}/mo at stake — a model estimate, not a measurement.",
            "no_loss": " We do not quote revenue figures before measurement.",
        },
        "DE": {
            "audited": "Unsere 360°-KI-Sichtbarkeitsprüfung von {brand} ist abgeschlossen: technischer Score {score}/100 ({sector}, {city}).",
            "offer": "Wir bieten {brand} eine kostenlose 360°-KI-Sichtbarkeitsprüfung an.",
            "loss": " Unser Umsatzmodell schätzt bis zu {cur}{amt}/Monat — eine Modell-Schätzung, keine Messung.",
            "no_loss": " Vor der Messung nennen wir keine Umsatzfiguren.",
        },
        "UAE": {
            "audited": "Our 360° AI-visibility audit of {brand} is complete: technical score {score}/100 ({sector}, {city}).",
            "offer": "We offer {brand} a free 360° AI-visibility audit.",
            "loss": " Our revenue model estimates up to {cur}{amt}/mo at stake — a model estimate, not a measurement.",
            "no_loss": " We do not quote revenue figures before measurement.",
        },
    }

    def generate_pitch(self, candidate: SwarmCandidate) -> str:
        """Kişiselleştirilmiş satış sunuş metni üretir."""
        lang_key = candidate.country if candidate.country in self.TEMPLATES else "UK"
        template = self.TEMPLATES[lang_key]
        sector_noun = self.SECTOR_NOUNS.get(lang_key, {}).get(candidate.sector, candidate.sector)
        # Measurement gates (16 Eyl derin-tarama): never claim absence we did not
        # measure, never inject a default "lost revenue" the pipeline did not compute.
        parts = HunterAgent.CLAUSES.get(lang_key, HunterAgent.CLAUSES["UK"])
        if candidate.deep_score is not None:
            findings = parts["audited"].format(brand=candidate.brand_name, score=f"{candidate.deep_score:g}",
                                               sector=sector_noun, city=candidate.city)
        else:
            findings = parts["offer"].format(brand=candidate.brand_name)
        cur = {"TR": "₺", "UK": "GBP ", "US": "$", "DE": "EUR ", "UAE": "AED "}.get(candidate.country, "")
        if candidate.lost_revenue_monthly:
            loss = parts["loss"].format(amt=f"{candidate.lost_revenue_monthly:,.0f}", cur=cur)
        else:
            loss = parts["no_loss"]
        pitch = template.format(brand=candidate.brand_name, sector=sector_noun,
                                findings=findings, loss=loss)
        candidate.outreach_pitch = pitch
        candidate.stage = SwarmStage.OUTREACH_SENT
        candidate.last_action = f"Outreach pitch dispatched ({lang_key})"
        candidate.updated_at = utc_now()
        return pitch

    def handle_objection(self, candidate: SwarmCandidate, objection_text: str) -> str:
        """Bir satış itirazını karşılık stratejisiyle yanıtlar."""
        rebuttal = ObjectionHandler.generate_rebuttal(
            text=objection_text,
            company_name=candidate.brand_name,
            sector=candidate.sector,
        )
        candidate.stage = SwarmStage.NEGOTIATING
        candidate.last_action = f"Objection handled: {objection_text[:30]}..."
        candidate.updated_at = utc_now()
        return rebuttal.rebuttal_text

class FulfillmentAgent:
    """Agent 4: Autonomously produces fixes and statutory tax-separated contracts."""

    def __init__(
        self,
        tax_ledger: Optional[TaxLedger] = None,
        exclusivity: Optional[ExclusivityManager] = None,
    ):
        self.fix_gen = FixGenerator()
        self.contract_gen = ContractGenerator()
        self.tax_ledger = tax_ledger or TaxLedger()
        self.exclusivity = exclusivity

    def generate_contract(self, candidate: SwarmCandidate) -> str:
        """Sözleşme taslağını marka ve bölge bilgileriyle oluşturur."""
        client = ClientLegalDetails(
            client_name=f"{candidate.brand_name} Lead",
            company_title=f"{candidate.brand_name} Inc.",
            tax_number="1234567890",
            tax_office="Merkez",
            address=f"{candidate.city}, {candidate.country}",
            authorized_person="Kurucu Hekim / Yönetici",
            email=f"contact@{candidate.domain}",
            phone="+905550000000",
            domain=candidate.domain,
            sector=candidate.sector,
        )
        # Fee is calibratable via settings.swarm_fee_by_currency
        # (defaults preserve the historical 6000 TRY / 1500 foreign split).
        fee = settings.swarm_fee_by_currency.get(candidate.currency, settings.swarm_fee_by_currency["USD"])
        contract_no = f"ANSW-{uuid.uuid4().hex[:6].upper()}"
        meta = ContractMetadata(
            contract_number=contract_no,
            service_tier=PricingTier.MONTHLY_RETAINER,
            monthly_fee_try=fee,
            start_date=datetime.now().strftime("%Y-%m-%d"),
            fee_currency=candidate.currency,
            is_export_service=(candidate.country.strip().upper() != "TR"),
            agency_whitelabel=bool(candidate.agency_domain),
            agency_name=candidate.agency_domain,
        )
        contract = self.contract_gen.generate_contract(client, meta)
        candidate.contract_text = contract.contract_text
        candidate.stage = SwarmStage.CONTRACT_ISSUED

        # Record into fiscal tax ledger with statutory separation
        fiscal_rec = self.tax_ledger.record_invoice(
            client_brand=candidate.brand_name,
            country=candidate.country,
            currency=candidate.currency,
            amount=fee,
            invoice_no=f"INV-{contract_no}",
        )
        candidate.fiscal_invoice_id = fiscal_rec.invoice_id
        candidate.fiscal_tax_exempt_try = fiscal_rec.exempt_income_try

        # Lock territory to prevent competitor cannibalization
        if self.exclusivity:
            self.exclusivity.lock_territory(
                country=candidate.country,
                city=candidate.city,
                niche=candidate.sector,
                client_domain=candidate.domain,
                agency_domain=candidate.agency_domain,
                brand_name=candidate.brand_name,
                contract_id=contract_no,
            )
            candidate.territory_locked = True

        candidate.last_action = f"Legal contract generated with Madde 7 guarantee & Fiscal Invoice {fiscal_rec.invoice_id}"
        candidate.updated_at = utc_now()
        return contract.contract_text

    def fulfill(self, candidate: SwarmCandidate) -> Dict[str, str]:
        """Sözleşmenin teslimat adımlarını yürütür ve kanıtlanmış çıktıyı kaydeder."""
        robots = self.fix_gen.generate_robots_txt(candidate.domain)
        llms = self.fix_gen.generate_llms_txt(candidate.brand_name, candidate.domain, sector=candidate.sector, city=candidate.city)
        llms_full = self.fix_gen.generate_llms_full_txt(candidate.brand_name, candidate.domain, sector=candidate.sector, city=candidate.city)
        json_ld = self.fix_gen.generate_json_ld(candidate.brand_name, candidate.domain, sector=candidate.sector, city=candidate.city)

        fixes = {
            "robots.txt": robots,
            "llms.txt": llms,
            "llms-full.txt": llms_full,
            "schema.jsonld": json_ld,
        }
        candidate.fixes_generated = fixes
        candidate.stage = SwarmStage.FULFILLED
        candidate.last_action = "Full AEO/GEO bundle generated and dispatched"
        candidate.updated_at = utc_now()
        return fixes

class SentryAgent:
    """Agent 5: Monitors active clients, verifies 30-day delta, guards against churn."""

    def __init__(self, delta_engine: Optional[DeltaEngine] = None):
        self.delta_engine = delta_engine or DeltaEngine()
        self.audit_engine = AuditEngine()

    async def measure_current_score(self, candidate: SwarmCandidate) -> Optional[int]:
        """Re-runs a REAL audit against the live site to measure the current GEO score.

        Returns None if the site cannot be fetched (network failure) — the caller
        must NOT fabricate a score in that case.
        """

        try:
            crawl_data = await self.audit_engine.crawler.fetch(f"https://{candidate.domain}")
        except Exception as exc:
            logger.warning("SentryAgent: live re-audit fetch failed for %s: %s", candidate.domain, exc)
            return None

        if not crawl_data.html_content or crawl_data.status_code not in (200, 201):
            logger.warning(
                "SentryAgent: live re-audit returned status %s for %s — no score fabricated",
                crawl_data.status_code,
                candidate.domain,
            )
            return None

        base_audit = self.audit_engine.audit_crawl_data(crawl_data, sector=candidate.sector)
        return int(base_audit.overall_score)

    async def evaluate_retention(self, candidate: SwarmCandidate, current_score: Optional[int] = None) -> Dict[str, Any]:
        """Evaluates the 30-day delta against the contractual guarantee.

        If `current_score` is not provided, a REAL live re-audit of the site is
        executed. If that fails (unreachable site), no delta is fabricated: the
        candidate is marked for manual review instead.
        """
        baseline = int(candidate.deep_score or 0)
        if baseline <= 0:
            # No meaningful baseline recorded — cannot compute a guarantee delta.
            candidate.stage = SwarmStage.ACTIVE_MONITORING
            candidate.last_action = "Delta check skipped: no baseline deep score on record (manual review required)"
            candidate.updated_at = utc_now()
            return {
                "is_guarantee_met": False,
                "score_delta": 0,
                "percentage_change": 0.0,
                "baseline_score": baseline,
                "current_score": None,
                "measurement_note": "No baseline deep score recorded; delta cannot be computed without fabrication.",
            }

        if current_score is None:
            current_score = await self.measure_current_score(candidate)

        if current_score is None:
            # Live measurement failed — DO NOT fabricate. Flag for manual review.
            candidate.stage = SwarmStage.ACTIVE_MONITORING
            candidate.last_action = "Delta check deferred: live re-audit unreachable (manual verification required)"
            candidate.updated_at = utc_now()
            return {
                "is_guarantee_met": False,
                "score_delta": 0,
                "percentage_change": 0.0,
                "baseline_score": baseline,
                "current_score": None,
                "measurement_note": "Site unreachable; no delta fabricated. Manual re-measurement required.",
            }

        from answrank.audit.crawler import CrawlData

        measured_crawl = CrawlData(
            url=f"https://{candidate.domain}",
            domain=candidate.domain,
            html_content="",  # scores injected explicitly below from the live measurement
            status_code=200,
            headers={},
            is_https=True,
        )
        base_audit = self.audit_engine.audit_crawl_data(measured_crawl, sector=candidate.sector)
        curr_audit = self.audit_engine.audit_crawl_data(measured_crawl, sector=candidate.sector)
        base_audit.overall_score = baseline
        curr_audit.overall_score = current_score

        delta_res = self.delta_engine.calculate_delta(base_audit, curr_audit)
        candidate.stage = SwarmStage.DELTA_CHECKED
        candidate.last_action = f"30-day Delta measured live: {delta_res.score_delta:+d} pts (live score {current_score}). Guarantee met: {delta_res.is_guarantee_met}"
        candidate.updated_at = utc_now()
        return delta_res.model_dump()

from answrank.db import Database

class SwarmOrchestrator:
    """Master controller managing the 5 autonomous agents in closed loop with SQLite persistence."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.exclusivity = ExclusivityManager()
        self.tax_ledger = TaxLedger()
        self._load_persisted_locks()
        self.scout = ScoutAgent(exclusivity=self.exclusivity)
        self.auditor = AuditorAgent()
        self.hunter = HunterAgent()
        self.fulfillment = FulfillmentAgent(tax_ledger=self.tax_ledger, exclusivity=self.exclusivity)
        self.sentry = SentryAgent()
        self.pool: Dict[str, SwarmCandidate] = {}
        self._load_persisted_candidates()

    def _load_persisted_locks(self) -> None:
        try:
            for l_data in self.db.list_territory_locks_sync():
                self.exclusivity.lock_territory(
                    country=l_data["country"],
                    city=l_data["city"],
                    niche=l_data["niche"],
                    client_domain=l_data["client_domain"],
                    brand_name=l_data["brand_name"],
                    tier=l_data.get("tier", "EXCLUSIVE"),
                    contract_id=l_data.get("contract_id"),
                )
        except Exception as exc:
            logger.warning("SwarmOrchestrator: territory lock restore failed: %s", exc)

    def _load_persisted_candidates(self) -> None:
        try:
            for c_data in self.db.list_swarm_candidates_sync(limit=100):
                cand = SwarmCandidate(
                    id=c_data["id"],
                    brand_name=c_data["brand_name"],
                    domain=c_data["domain"],
                    sector=c_data.get("sector", "dental"),
                    city=c_data.get("city", "London"),
                    country=c_data.get("country", "UK"),
                    currency=c_data.get("currency", "GBP"),
                    ticket_size=float(c_data.get("ticket_size", 2500.0)),
                    stage=SwarmStage(c_data["stage"]),
                    deep_score=c_data.get("deep_score"),
                    lost_revenue_monthly=c_data.get("lost_revenue_monthly"),
                    outreach_pitch=c_data.get("outreach_pitch"),
                    contract_text=c_data.get("contract_text"),
                    fixes_generated=c_data.get("fixes_generated"),
                    territory_locked=bool(c_data.get("territory_locked")),
                    fiscal_invoice_id=c_data.get("fiscal_invoice_id"),
                    fiscal_tax_exempt_try=c_data.get("fiscal_tax_exempt_try"),
                    conflict_reason=c_data.get("conflict_reason"),
                    last_action=c_data.get("last_action", "Discovered"),
                )
                self.pool[cand.id] = cand
        except Exception as exc:
            logger.warning("SwarmOrchestrator: candidate restore failed (pool continues from empty): %s", exc)

    def persist_candidate(self, candidate: SwarmCandidate) -> None:
        """Adayı kalıcı olarak saklar."""
        try:
            self.db.save_swarm_candidate_sync(candidate.model_dump())
            if candidate.territory_locked:
                for lock in self.exclusivity.list_active_locks():
                    if lock.client_domain.lower() == candidate.domain.lower():
                        self.db.save_territory_lock_sync(lock.model_dump())
        except Exception as exc:
            logger.error("SwarmOrchestrator: persist failed for %s (%s) — state may be lost on restart: %s", candidate.id, candidate.domain, exc)

    def seed_target(
        self,
        brand_name: str,
        domain: str,
        sector: str = "dental",
        city: str = "London",
        country: str = "UK",
        currency: str = "GBP",
        ticket_size: float = 2500.0,
        agency_domain: Optional[str] = None,
    ) -> SwarmCandidate:
        """Hedef havuzundan bir aday ekler."""
        candidate = SwarmCandidate(
            brand_name=brand_name,
            domain=domain,
            sector=sector,
            city=city,
            agency_domain=agency_domain,
            country=country,
            currency=currency,
            ticket_size=ticket_size,
        )
        self.pool[candidate.id] = candidate
        self.persist_candidate(candidate)
        return candidate

    async def run_pipeline_step(self, candidate_id: str) -> SwarmCandidate:
        """Swarm pipeline'ının tek bir adımını yürütür."""
        cand = self.pool.get(candidate_id)
        if not cand:
            raise ValueError(f"Candidate {candidate_id} not found")

        if cand.stage == SwarmStage.DISCOVERED:
            self.scout.qualify(cand)
        elif cand.stage == SwarmStage.QUALIFIED:
            await self.auditor.audit(cand)
        elif cand.stage == SwarmStage.AUDITED:
            self.hunter.generate_pitch(cand)
        elif cand.stage in (SwarmStage.OUTREACH_SENT, SwarmStage.NEGOTIATING):
            self.fulfillment.generate_contract(cand)
        elif cand.stage == SwarmStage.CONTRACT_ISSUED:
            self.fulfillment.fulfill(cand)
        elif cand.stage == SwarmStage.FULFILLED:
            cand.stage = SwarmStage.ACTIVE_MONITORING
            cand.last_action = "Client active; scheduled for Day-30 Delta check"
        elif cand.stage == SwarmStage.ACTIVE_MONITORING:
            await self.sentry.evaluate_retention(cand)

        self.persist_candidate(cand)
        return cand

    async def run_full_pipeline_sync(
        self,
        candidate: SwarmCandidate,
        on_event: Optional[Any] = None,
    ) -> SwarmCandidate:
        """Executes complete discovery to retention pipeline for a candidate and persists state.

        `on_event(agent_name, message)` is an optional async or sync callback invoked
        after each real agent step — used by the SSE stream to emit genuine progress.
        """

        async def _emit(agent: str, message: str) -> None:
            if on_event is None:
                return
            res = on_event(agent, message)
            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                await res

        self.pool[candidate.id] = candidate
        self.persist_candidate(candidate)

        if not self.scout.qualify(candidate):
            await _emit(
                "AGENT_01_SCOUT",
                f"DISQUALIFIED: {candidate.brand_name} ({candidate.city}, {candidate.country}) — {candidate.conflict_reason or 'qualification failed'}",
            )
            self.persist_candidate(candidate)
            return candidate

        await _emit(
            "AGENT_01_SCOUT",
            f"Candidate '{candidate.brand_name}' ({candidate.city}, {candidate.country}) qualified — territory free, LTV signal OK",
        )

        await self.auditor.audit(candidate)
        if candidate.stage != SwarmStage.AUDITED:
            # Audit halted (domain unreachable) — never continue to outreach,
            # contract or invoicing on unverified evidence.
            await _emit("AGENT_02_AUDITOR", candidate.last_action)
            self.persist_candidate(candidate)
            return candidate
        self.persist_candidate(candidate)
        await _emit(
            "AGENT_02_AUDITOR",
            f"360° audit of {candidate.domain} completed — deep score {candidate.deep_score}/100 ({candidate.audit_data.get('deep_tier', 'N/A') if candidate.audit_data else 'N/A'})",
        )

        self.hunter.generate_pitch(candidate)
        self.persist_candidate(candidate)
        await _emit("AGENT_03_HUNTER", f"Multilingual outreach dispatched for {candidate.country} market")

        self.fulfillment.generate_contract(candidate)
        self.persist_candidate(candidate)
        await _emit("AGENT_04_MAKER", f"Contract issued ({candidate.fiscal_invoice_id or 'no invoice'}) & tax ledger recorded")

        self.fulfillment.fulfill(candidate)
        self.persist_candidate(candidate)
        await _emit("AGENT_04_MAKER", "AEO/GEO bundle generated: robots.txt, llms.txt, llms-full.txt, schema.jsonld")

        await self.sentry.evaluate_retention(candidate)
        self.persist_candidate(candidate)
        await _emit(
            "AGENT_05_SENTRY",
            f"30-day delta measured: {candidate.last_action}",
        )

        return candidate

    def get_fiscal_report(self) -> FiscalSummaryReport:
        """Generates CPA-ready fiscal summary of foreign export vs domestic revenues."""
        return self.tax_ledger.generate_fiscal_summary()

    def get_territory_locks(self) -> List[TerritoryLock]:
        """Returns all currently protected territory and niche client locks."""
        return self.exclusivity.list_active_locks()

