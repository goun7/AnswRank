"""Database repository for AnswRank using SQLite with OpenGEO standard tables."""

import sqlite3
import json
import asyncio
import logging
import contextlib
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from answrank.config import settings

logger = logging.getLogger("answrank.db")

from answrank.models import Prospect, AuditResult, CitationRunResult, utc_now

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS prospects (
    id TEXT PRIMARY KEY,
    brand_name TEXT NOT NULL,
    sector TEXT NOT NULL,
    city TEXT NOT NULL,
    website_url TEXT,
    contact_person TEXT,
    platform TEXT,
    status TEXT DEFAULT 'lead',
    domain_ref TEXT,
    country TEXT,
    phone TEXT,
    email TEXT,
    source_url TEXT,
    verified_at TEXT,
    http_status INTEGER,
    robots_status INTEGER,
    contact_source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    prospect_id TEXT,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    sector TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    score_band TEXT NOT NULL,
    robots_score INTEGER NOT NULL,
    llms_txt_score INTEGER NOT NULL,
    schema_score INTEGER NOT NULL,
    meta_score INTEGER NOT NULL,
    citability_score INTEGER NOT NULL,
    entity_score INTEGER NOT NULL,
    trust_score INTEGER NOT NULL,
    negative_score INTEGER NOT NULL,
    lost_revenue_monthly REAL,
    raw_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    sector TEXT NOT NULL,
    city TEXT NOT NULL,
    total_runs INTEGER NOT NULL,
    citations_found INTEGER NOT NULL,
    citation_rate REAL NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delta_logs (
    id TEXT PRIMARY KEY,
    prospect_id TEXT NOT NULL,
    baseline_score INTEGER NOT NULL,
    current_score INTEGER NOT NULL,
    score_delta INTEGER NOT NULL,
    percentage_change REAL NOT NULL,
    is_guarantee_met BOOLEAN NOT NULL,
    days_elapsed INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS swarm_candidates (
    id TEXT PRIMARY KEY,
    brand_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    sector TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    currency TEXT NOT NULL,
    ticket_size REAL NOT NULL,
    stage TEXT NOT NULL,
    deep_score REAL,
    lost_revenue_monthly REAL,
    outreach_pitch TEXT,
    contract_text TEXT,
    fixes_json TEXT,
    territory_locked BOOLEAN DEFAULT 0,
    fiscal_invoice_id TEXT,
    fiscal_tax_exempt_try REAL,
    conflict_reason TEXT,
    last_action TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payment_intents (
    intent_id TEXT PRIMARY KEY,
    contract_ref TEXT NOT NULL,
    brand TEXT NOT NULL,
    country TEXT NOT NULL,
    currency TEXT NOT NULL,
    amount REAL NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    invoice_id TEXT,
    proof_ref TEXT,
    settled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    psp_event_id TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    intent_id TEXT,
    status TEXT NOT NULL,
    raw TEXT
);

CREATE TABLE IF NOT EXISTS payment_credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id TEXT NOT NULL,
    invoice_id TEXT,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS territory_locks (
    lock_id TEXT PRIMARY KEY,
    country TEXT NOT NULL,
    city TEXT NOT NULL,
    niche TEXT NOT NULL,
    client_domain TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    tier TEXT NOT NULL,
    contract_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tax_invoices (
    invoice_id TEXT PRIMARY KEY,
    client_brand TEXT NOT NULL,
    client_country TEXT NOT NULL,
    regime TEXT NOT NULL,
    currency TEXT NOT NULL,
    amount_foreign REAL NOT NULL,
    exchange_rate REAL NOT NULL,
    fx_source TEXT NOT NULL DEFAULT 'static_default',
    amount_try REAL NOT NULL,
    vat_rate_pct REAL NOT NULL,
    vat_amount_try REAL NOT NULL,
    gross_total_try REAL NOT NULL,
    exempt_income_try REAL NOT NULL,
    taxable_base_try REAL NOT NULL,
    legal_note TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitors (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    brand TEXT NOT NULL,
    sector TEXT NOT NULL DEFAULT 'general',
    cadence_days INTEGER NOT NULL DEFAULT 30,
    active INTEGER NOT NULL DEFAULT 1,
    contract_id TEXT,
    created_at TEXT NOT NULL,
    next_due_at TEXT
);

CREATE TABLE IF NOT EXISTS corpus_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    measured INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    robots_status INTEGER,
    llms_status INTEGER,
    bot_statuses TEXT NOT NULL,
    blocked_bots TEXT NOT NULL,
    robots_line TEXT NOT NULL,
    llms_line TEXT NOT NULL,
    bots_line TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS miniprobe_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    verdict TEXT NOT NULL,
    robots_line TEXT NOT NULL,
    llms_line TEXT NOT NULL,
    bots_line TEXT NOT NULL,
    measured INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('DM','CONTRACT','FREE_CYCLE','MONITOR_INTERVENTION')),
    ref_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','AUTO_APPROVED','REJECTED')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decision_note TEXT,
    evidence_run_id TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS approval_queue_open ON approval_queue(kind, ref_id)
    WHERE status = 'PENDING';

-- E13: çok-kapılı denetim kayıt defteri — her kapı sonucu nedeniyle yazılır;
-- AUTO_APPROVED kararlarının denetim izi (insan karardan ayrı, geri-döndürülemez)
CREATE TABLE IF NOT EXISTS gate_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    queue_id INTEGER,
    gate TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK(passed IN (0,1)),
    reason TEXT NOT NULL,
    all_passed INTEGER NOT NULL CHECK(all_passed IN (0,1)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS gate_audit_log_domain ON gate_audit_log(domain);

-- E13b: DM gönderim günlüğü — her gönderim sonucuyla yazılır (idempotent:
-- (queue_id, recipient) benzersiz; onaysız/hedef-yok asla 'GÖNDERİLDİ' olmaz)
CREATE TABLE IF NOT EXISTS dm_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    recipient TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('GÖNDERİLDİ','HATA','HEDEF_YOK','YAPILANDIRILMAMIŞ','DRY_RUN')),
    note TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    UNIQUE(queue_id, recipient)
);

CREATE TABLE IF NOT EXISTS fulfillment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    contract_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    delta REAL,
    free_cycle_id TEXT,
    reason TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    ran_at TEXT NOT NULL,
    status TEXT NOT NULL,
    score_base REAL,
    sov_pct REAL,
    audit_id TEXT,
    citation_run_id TEXT,
    note TEXT
);
"""

class Database:
    """SQLite Database wrapper for AnswRank."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.db_path
        self._init_db()

    def _get_connection(self):
        """Returns a context manager yielding a sqlite3 connection that is
        always closed on exit (unlike the bare sqlite3 context protocol,
        which only manages transactions and leaks the file handle)."""
        @contextlib.contextmanager
        def _cm():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
        return _cm()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(SCHEMA_DDL)
            self._ensure_columns(conn)
            conn.commit()

    # E9: mevcut kurulumlarda eksik sütunlar ALTER ile tamamlanır. Kaynak SCHEMA_DDL
    # olduğundan tüm tabloları mekanik olarak kapsar — elle bakım değil, tek sahipten
    # türetilir (CREATE IF NOT EXISTS yalnız YENI DB'ler içindir; eski DB bu olmadan
    # ilk yazışta 'no column named X' ile bozulurdu).
    def _ensure_columns(self, conn) -> None:
        import re as _re
        for m in _re.finditer(
                r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SCHEMA_DDL, _re.S):
            table, body = m.group(1), m.group(2)
            declared = []
            for line in body.split("\n"):
                line = line.strip().rstrip(",").strip()
                if not line or line.startswith(("--", "UNIQUE", "CHECK", "FOREIGN",
                                                "PRIMARY", "CONSTRAINT")):
                    continue
                col = line.split()[0]
                if col and col.isidentifier():
                    declared.append(col)
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for col in declared:
                if col not in existing:
                    ddl = next((l.strip().rstrip(",") for l in body.split("\n")
                                if l.strip().startswith(col + " ")), col)
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
                    logger.info("db migration: %s.%s eklendi", table, col)

    async def save_prospect(self, prospect: Prospect) -> None:
        """prospect kaydını kalıcı olarak saklar."""
        def _sync_save():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO prospects (id, brand_name, sector, city, website_url,
                        contact_person, platform, status, created_at, domain_ref, country,
                        phone, email, source_url, verified_at, http_status, robots_status,
                        contact_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prospect.id,
                        prospect.brand_name,
                        prospect.sector,
                        prospect.city,
                        prospect.website_url,
                        prospect.contact_person,
                        prospect.platform,
                        prospect.status,
                        prospect.created_at.isoformat(),
                        prospect.domain_ref,
                        prospect.country,
                        prospect.phone,
                        prospect.email,
                        prospect.source_url,
                        prospect.verified_at,
                        prospect.http_status,
                        prospect.robots_status,
                        prospect.contact_source,
                    ),
                )
                conn.commit()
        await asyncio.to_thread(_sync_save)

    async def get_prospect(self, prospect_id: str) -> Optional[Dict[str, Any]]:
        """Tek bir prospect kaydını döndürür; bulunamazsa None."""
        def _sync_get():
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_sync_get)

    async def save_audit(self, audit: AuditResult, prospect_id: Optional[str] = None) -> None:
        """audit kaydını kalıcı olarak saklar."""
        def _sync_save():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO audits (
                        id, prospect_id, url, domain, sector, overall_score, score_band,
                        robots_score, llms_txt_score, schema_score, meta_score,
                        citability_score, entity_score, trust_score, negative_score,
                        lost_revenue_monthly, raw_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        audit.audit_id,
                        prospect_id,
                        audit.url,
                        audit.domain,
                        audit.sector,
                        audit.overall_score,
                        audit.score_band,
                        audit.categories.robots.score,
                        audit.categories.llms_txt.score,
                        audit.categories.schema_jsonld.score,
                        audit.categories.meta_architecture.score,
                        audit.categories.citability_rag.score,
                        audit.categories.entity_coherence.score,
                        audit.categories.trust_stack.score,
                        audit.categories.negative_signals.score,
                        audit.lost_revenue_estimate_monthly_try,
                        audit.model_dump_json(),
                        audit.timestamp.isoformat(),
                    ),
                )
                conn.commit()
        await asyncio.to_thread(_sync_save)

    async def get_audit(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """Tek bir audit kaydını döndürür; bulunamazsa None."""
        def _sync_get():
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM audits WHERE id = ?", (audit_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_sync_get)

    # -------------------------------------------------- E1 GEO İzleme (D-16.09-M)
    def create_monitor(self, monitor_id: str, domain: str, brand: str, sector: str,
                       cadence_days: int, contract_id, now_iso: str) -> None:
        """Yeni bir monitor kaydı oluşturur."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO monitors (id, domain, brand, sector, cadence_days, active,"
                " contract_id, created_at, next_due_at) VALUES (?,?,?,?,?,1,?,?,?)",
                (monitor_id, domain, brand, sector, cadence_days, contract_id, now_iso, now_iso))
            conn.commit()

    def list_monitors(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """monitors kayıtlarını listeler."""
        with self._get_connection() as conn:
            q = "SELECT * FROM monitors" + ("" if include_inactive else " WHERE active = 1")
            return [dict(r) for r in conn.execute(q + " ORDER BY created_at").fetchall()]

    async def save_miniprobe_lead(self, res) -> None:
        """E7 lead hunisi — yalnız GİRİŞ REDDEDİLDİ olmayan ölçüm sonuçları.
        IP/log tutulmaz (KVKK asgari). Yeni satır append; tekrar ziyaret doğaldır."""
        if res.verdict == "GİRİŞ REDDEDİLDİ":
            return
        def _sync():
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO miniprobe_leads (domain, verdict, robots_line, llms_line,"
                    " bots_line, measured, created_at) VALUES (?,?,?,?,?,?,?)",
                    (res.domain, res.verdict, res.robots_line, res.llms_line,
                     res.bots_line, 1 if res.measured else 0, utc_now().isoformat()))
                conn.commit()
        await asyncio.get_running_loop().run_in_executor(None, _sync)

    def list_miniprobe_leads(self, limit: int = 50):
        """miniprobe_leads kayıtlarını listeler."""
        with self._get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT domain, verdict, robots_line, llms_line, bots_line, measured,"
                " created_at FROM miniprobe_leads ORDER BY id DESC LIMIT ?", (limit,))]

    def latest_measured_lead(self, domain: str):
        """En güncel measured_lead kaydını döndürür."""
        with self._get_connection() as conn:
            r = conn.execute(
                "SELECT domain, verdict, robots_line, llms_line, bots_line, measured,"
                " created_at FROM miniprobe_leads WHERE domain = ? AND measured = 1"
                " ORDER BY id DESC LIMIT 1", (domain.strip().lower(),)).fetchone()
            return dict(r) if r else None

    def get_monitor(self, monitor_id: str) -> Optional[Dict[str, Any]]:
        """Tek bir monitor kaydını döndürür; bulunamazsa None."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
            return dict(row) if row else None

    def due_monitors(self, now_iso: str) -> List[Dict[str, Any]]:
        """Vadesi gelen monitors kayıtlarını döndürür."""
        with self._get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM monitors WHERE active = 1 AND (next_due_at IS NULL OR next_due_at <= ?)"
                " ORDER BY next_due_at", (now_iso,)).fetchall()]

    def postpone_next_due(self, monitor_id: str, when: datetime, now_iso: str = "") -> None:
        """next_due zamanlamasını erteler."""
        with self._get_connection() as conn:
            conn.execute("UPDATE monitors SET next_due_at = ? WHERE id = ?",
                         (when.isoformat(), monitor_id))
            conn.commit()

    def insert_monitor_run(self, monitor_id: str, ran_at_iso: str, status: str,
                           score_base, sov_pct, audit_id, citation_run_id, note: str = "") -> int:
        """Yeni bir monitor_run satırı ekler."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO monitor_runs (monitor_id, ran_at, status, score_base, sov_pct,"
                " audit_id, citation_run_id, note) VALUES (?,?,?,?,?,?,?,?)",
                (monitor_id, ran_at_iso, status, score_base, sov_pct, audit_id, citation_run_id, note))
            conn.commit()
            return int(cur.lastrowid)

    def monitor_runs(self, monitor_id: str) -> List[Dict[str, Any]]:
        """İzleme için ölçüm koşumlarını listeler."""
        with self._get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM monitor_runs WHERE monitor_id = ? ORDER BY ran_at", (monitor_id,)).fetchall()]

    def get_dm_visibility(self, domain: str) -> Optional[dict]:
        """Validate only the latest domain run; no fallback to older evidence."""
        from answrank.citations.evidence import visibility_from_row

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT domain, run_id, total_runs, citations_found, citation_rate,"
                " raw_json, created_at FROM citations WHERE domain=?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1", (domain,)).fetchone()
        return visibility_from_row(row, domain) if row else None

    async def get_latest_citations_for_domain(self, domain: str) -> Optional[CitationRunResult]:
        """Report page reader: same fail-closed contract as the DM path.

        The LATEST row only, validated through the shared evidence reader.
        An invalid latest run (simulated, inconsistent, corrupt) yields None;
        older rows are never silently substituted ('son koşu geçersizse
        durdur'). Rendering a simulated run as a genuine stored run is a
        worse failure than showing nothing.
        """
        def _sync_get():
            from answrank.citations.evidence import visibility_from_row
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT domain, run_id, total_runs, citations_found,"
                    " citation_rate, raw_json, created_at FROM citations"
                    " WHERE domain = ? ORDER BY created_at DESC, rowid DESC"
                    " LIMIT 1", (domain,)).fetchone()
            if row is None or visibility_from_row(row, domain) is None:
                return None
            try:
                return CitationRunResult.model_validate_json(row["raw_json"])
            except Exception:
                return None
        return await asyncio.to_thread(_sync_get)

    async def save_citations(self, citation_res: CitationRunResult) -> None:
        """citations kaydını kalıcı olarak saklar."""
        def _sync_save():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO citations (
                        id, run_id, brand_name, domain, sector, city,
                        total_runs, citations_found, citation_rate, raw_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"cite_{citation_res.run_id}",
                        citation_res.run_id,
                        citation_res.brand_name,
                        citation_res.domain,
                        citation_res.sector,
                        citation_res.city,
                        citation_res.total_runs,
                        citation_res.brand_citations_found,
                        citation_res.citation_rate_percentage,
                        citation_res.model_dump_json(),
                        citation_res.timestamp.isoformat(),
                    ),
                )
                conn.commit()
        await asyncio.to_thread(_sync_save)

    async def list_recent_audits(self, limit: int = 10) -> List[Dict[str, Any]]:
        """recent_audits kayıtlarını listeler."""
        def _sync_list():
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, url, domain, sector, overall_score, score_band, created_at FROM audits ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        return await asyncio.to_thread(_sync_list)

    def save_swarm_candidate_sync(self, cand_data: Dict[str, Any]) -> None:
        """swarm_candidate_sync kaydını kalıcı olarak saklar."""
        stage_val = cand_data.get("stage", "DISCOVERED")
        if hasattr(stage_val, "value"):
            stage_str = stage_val.value
        else:
            stage_str = str(stage_val).replace("SwarmStage.", "")

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO swarm_candidates (
                    id, brand_name, domain, sector, city, country, currency, ticket_size,
                    stage, deep_score, lost_revenue_monthly, outreach_pitch, contract_text,
                    fixes_json, territory_locked, fiscal_invoice_id, fiscal_tax_exempt_try,
                    conflict_reason, last_action, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cand_data.get("id"),
                    cand_data.get("brand_name"),
                    cand_data.get("domain"),
                    cand_data.get("sector", "dental"),
                    cand_data.get("city", "London"),
                    cand_data.get("country", "UK"),
                    cand_data.get("currency", "GBP"),
                    float(cand_data.get("ticket_size", 0.0)),
                    stage_str,
                    cand_data.get("deep_score"),
                    cand_data.get("lost_revenue_monthly"),
                    cand_data.get("outreach_pitch"),
                    cand_data.get("contract_text"),
                    json.dumps(cand_data.get("fixes_generated") or {}),
                    1 if cand_data.get("territory_locked") else 0,
                    cand_data.get("fiscal_invoice_id"),
                    cand_data.get("fiscal_tax_exempt_try"),
                    cand_data.get("conflict_reason"),
                    cand_data.get("last_action", "Discovered"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    async def save_swarm_candidate(self, cand_data: Dict[str, Any]) -> None:
        """swarm_candidate kaydını kalıcı olarak saklar."""
        await asyncio.to_thread(self.save_swarm_candidate_sync, cand_data)

    def get_swarm_candidate_sync(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Tek bir swarm_candidate_sync kaydını döndürür; bulunamazsa None."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM swarm_candidates WHERE id = ?", (candidate_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("fixes_json"):
                res["fixes_generated"] = json.loads(res["fixes_json"])
            res["territory_locked"] = bool(res.get("territory_locked"))
            return res

    async def get_swarm_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Tek bir swarm_candidate kaydını döndürür; bulunamazsa None."""
        return await asyncio.to_thread(self.get_swarm_candidate_sync, candidate_id)

    def list_swarm_candidates_sync(self, limit: int = 50) -> List[Dict[str, Any]]:
        """swarm_candidates_sync kayıtlarını listeler."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM swarm_candidates ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get("fixes_json"):
                    item["fixes_generated"] = json.loads(item["fixes_json"])
                item["territory_locked"] = bool(item.get("territory_locked"))
                results.append(item)
            return results

    async def list_swarm_candidates(self, limit: int = 50) -> List[Dict[str, Any]]:
        """swarm_candidates kayıtlarını listeler."""
        return await asyncio.to_thread(self.list_swarm_candidates_sync, limit)

    def save_territory_lock_sync(self, lock_data: Dict[str, Any]) -> None:
        """territory_lock_sync kaydını kalıcı olarak saklar."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO territory_locks (
                    lock_id, country, city, niche, client_domain, brand_name, tier, contract_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lock_data["lock_id"],
                    lock_data["country"],
                    lock_data["city"],
                    lock_data["niche"],
                    lock_data["client_domain"],
                    lock_data["brand_name"],
                    lock_data.get("tier", "EXCLUSIVE"),
                    lock_data.get("contract_id"),
                    lock_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                ),
            )
            conn.commit()

    def list_territory_locks_sync(self) -> List[Dict[str, Any]]:
        """territory_locks_sync kayıtlarını listeler."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM territory_locks ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    # --- Tax ledger invoices (persisted so the fiscal report survives restarts) ---

    def save_tax_invoice_sync(self, inv: Dict[str, Any]) -> None:
        """tax_invoice_sync kaydını kalıcı olarak saklar."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tax_invoices (
                    invoice_id, client_brand, client_country, regime, currency,
                    amount_foreign, exchange_rate, fx_source, amount_try,
                    vat_rate_pct, vat_amount_try, gross_total_try,
                    exempt_income_try, taxable_base_try, legal_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inv["invoice_id"], inv["client_brand"], inv["client_country"],
                    inv["regime"], inv["currency"], inv["amount_foreign"],
                    inv["exchange_rate"], inv.get("fx_source", "static_default"),
                    inv["amount_try"], inv["vat_rate_pct"], inv["vat_amount_try"],
                    inv["gross_total_try"], inv["exempt_income_try"],
                    inv["taxable_base_try"], inv["legal_note"], inv["created_at"],
                ),
            )
            conn.commit()

    def list_tax_invoices_sync(self, limit: int = 500) -> List[Dict[str, Any]]:
        """tax_invoices_sync kayıtlarını listeler."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM tax_invoices ORDER BY created_at ASC, invoice_id ASC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]


