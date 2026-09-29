"""Pydantic v2 data models for AnswRank."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

def utc_now() -> datetime:
    """Şu anki UTC zaman damgasını döndürür."""
    return datetime.now(timezone.utc)

class RobotsScore(BaseModel):
    """Robots.txt AI Crawlability scoring (Max 18 pts)."""
    score: int = Field(ge=0, le=18, description="Score between 0 and 18")
    exists: bool = False
    ai_search_allowed: bool = False
    ai_training_allowed: bool = False
    sitemap_declared: bool = False
    llms_txt_referenced: bool = False
    blocked_ai_bots: List[str] = Field(default_factory=list)
    allowed_ai_bots: List[str] = Field(default_factory=list)
    details: List[str] = Field(default_factory=list)

class LlmsTxtScore(BaseModel):
    """llms.txt & llms-full.txt presence and quality (Max 18 pts)."""
    score: int = Field(ge=0, le=18, description="Score between 0 and 18")
    has_llms_txt: bool = False
    has_llms_full_txt: bool = False
    has_h1_title: bool = False
    has_blockquote_summary: bool = False
    has_structured_sections: bool = False
    word_count: int = 0
    details: List[str] = Field(default_factory=list)

class SchemaScore(BaseModel):
    """Semantic JSON-LD schema richness (Max 16 pts)."""
    score: int = Field(ge=0, le=16, description="Score between 0 and 16")
    has_json_ld: bool = False
    schema_types: List[str] = Field(default_factory=list)
    has_sector_entity: bool = False  # Dentist, AccountingService, MedicalBusiness
    has_faq_page: bool = False
    attribute_count: int = 0
    details: List[str] = Field(default_factory=list)

class MetaScore(BaseModel):
    """Meta tags, canonical, heading architecture (Max 14 pts)."""
    score: int = Field(ge=0, le=14, description="Score between 0 and 14")
    has_title: bool = False
    title_length: int = 0
    has_meta_description: bool = False
    description_length: int = 0
    has_canonical: bool = False
    has_open_graph: bool = False
    has_h1: bool = False
    h1_count: int = 0
    has_heading_hierarchy: bool = False
    details: List[str] = Field(default_factory=list)

class CitabilityScore(BaseModel):
    """Content Citability & RAG chunking readiness (Max 12 pts)."""
    score: int = Field(ge=0, le=12, description="Score between 0 and 12")
    word_count: int = 0
    has_statistics: bool = False
    statistics_count: int = 0
    has_quotations: bool = False
    has_tables_or_lists: bool = False
    front_loading_direct_answer: bool = False
    rag_chunk_friendly: bool = False
    details: List[str] = Field(default_factory=list)

class EntityScore(BaseModel):
    """Brand Entity Coherence & Knowledge Graph links (Max 10 pts)."""
    score: int = Field(ge=0, le=10, description="Score between 0 and 10")
    brand_name_found: bool = False
    has_phone: bool = False
    has_address: bool = False
    has_same_as_links: bool = False
    same_as_links: List[str] = Field(default_factory=list)
    details: List[str] = Field(default_factory=list)

class TrustScore(BaseModel):
    """Trust Stack, SSL, freshness, E-E-A-T & accessibility (Max 6 pts)."""
    score: int = Field(ge=0, le=6, description="Score between 0 and 6")
    is_https: bool = False
    has_date_modified: bool = False
    has_privacy_policy: bool = False
    has_eeat_signals: bool = False
    is_ssr_accessible: bool = False
    details: List[str] = Field(default_factory=list)

class NegativeScore(BaseModel):
    """Anti-Citation signals & manipulation filters (Max 6 pts)."""
    score: int = Field(ge=0, le=6, description="Score between 0 and 6")
    no_intrusive_popups: bool = True
    no_keyword_stuffing: bool = True
    no_thin_content: bool = True
    no_prompt_injection_patterns: bool = True
    no_unsupported_authority_claims: bool = True
    has_unsupported_authority_claims: bool = False
    penalty_points: int = 0
    details: List[str] = Field(default_factory=list)

class CategoryScores(BaseModel):
    """Aggregated category breakdown."""
    robots: RobotsScore
    llms_txt: LlmsTxtScore
    schema_jsonld: SchemaScore
    meta_architecture: MetaScore
    citability_rag: CitabilityScore
    entity_coherence: EntityScore
    trust_stack: TrustScore
    negative_signals: NegativeScore

class Recommendation(BaseModel):
    """Prioritized technical recommendation."""
    category: str
    priority: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    title: str
    action: str
    impact_points: int

class AuditResult(BaseModel):
    """Complete AnswRank Audit Report Result."""
    audit_id: str
    url: str
    domain: str
    sector: str = "general"
    timestamp: datetime = Field(default_factory=utc_now)
    overall_score: int = Field(ge=0, le=100)
    score_band: str  # 'Critical' (0-35), 'Foundation' (36-67), 'Good' (68-85), 'Excellent' (86-100)
    categories: CategoryScores
    recommendations: List[Recommendation] = Field(default_factory=list)
    lost_revenue_estimate_monthly_try: Optional[float] = None
    fix_snippets: Dict[str, str] = Field(default_factory=dict)
    # Transient collection issues (e.g. robots.txt network error) that are NOT
    # confirmed absences — surfaced so an unverifiable asset is never reported as
    # definitively missing.
    crawl_warnings: List[str] = Field(default_factory=list)

class CitationQueryItem(BaseModel):
    """Single question test item in multi-LLM citation run."""
    question_id: int
    question: str
    model: str  # 'ChatGPT-4o', 'Perplexity-Sonar', 'Gemini-Pro', 'Claude-3.5'
    brand_mentioned: bool = False
    domain_cited: bool = False
    cited_rank: Optional[int] = None
    competitors_cited: List[str] = Field(default_factory=list)
    raw_snippet: Optional[str] = None
    was_simulated: bool = True  # True if the response came from deterministic simulation, not a live API

class CitationRunResult(BaseModel):
    """Full 80-run citation test matrix."""
    run_id: str
    brand_name: str
    domain: str
    sector: str
    city: str
    lang: str = "tr"  # E4: ölçümün koşulduğu soru-bankası dili (en yalnız EN bankalarla)
    timestamp: datetime = Field(default_factory=utc_now)
    total_runs: int = 80
    brand_citations_found: int = 0
    citation_rate_percentage: float = 0.0
    live_items_count: int = 0  # number of items answered by a real API call
    live_response_rate_percentage: float = 0.0  # % of items that were live
    is_fully_live: bool = False  # True only when every item came from a live API call
    items: List[CitationQueryItem] = Field(default_factory=list)
    top_competitors: Dict[str, int] = Field(default_factory=dict)
    # E10: motor başına ÖLÇÜM MODALİTESİ — 'search-grounded' (canlı aramayla
    # kaynaklanan atıflar) yoksa 'model-recall' (modelin hatırladığı linkler —
    # canlı atıf olarak eşdeğer DEĞİL) veya 'anahtar yok'. Hiçbir motor
    # grounding'siz 'canlı atıf ölçtü' olarak sunulamaz.
    grounding_status: Dict[str, str] = Field(default_factory=dict)

class Prospect(BaseModel):
    """Sales prospect data model."""
    id: str
    brand_name: str
    sector: str
    city: str
    website_url: Optional[str] = None
    contact_person: Optional[str] = None
    platform: Optional[str] = None
    status: str = "lead"
    # E9 otonom prospektör kanıtları (yoksa None — DOĞRULANAMADI, uydurulmaz)
    domain_ref: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source_url: Optional[str] = None
    verified_at: Optional[str] = None
    http_status: Optional[int] = None
    robots_status: Optional[int] = None
    contact_source: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

class DeltaLog(BaseModel):
    """Delta measurement between two audit runs."""
    prospect_id: str
    baseline_score: int
    current_score: int
    score_delta: int
    percentage_change: float
    is_guarantee_met: bool
    days_elapsed: int

class DeepAuditResult(BaseModel):
    """Unified 360° Deep Enterprise Audit Result combining all subsystems."""
    base_audit: AuditResult
    waf_probe: Optional[Dict[str, Any]] = None
    adversarial: Optional[Dict[str, Any]] = None
    entity_grounding: Optional[Dict[str, Any]] = None
    rag_analysis: Optional[Dict[str, Any]] = None
    composite_deep_score: float
    deep_tier: str  # 'ENTERPRISE_READY', 'STABLE', 'RISK_EXPOSED', 'CRITICAL_BLOCKED'
    key_findings: List[str] = Field(default_factory=list)
