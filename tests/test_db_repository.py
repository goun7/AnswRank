"""Tests for Database repository: prospect/audit/citation round-trips, list, territory locks."""

import os
import tempfile
import pytest

from answrank.db import Database
from answrank.audit.engine import AuditEngine
from answrank.audit.crawler import CrawlData
from answrank.models import Prospect, utc_now


def _tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    return path


def _make_audit(score: int = 50):
    engine = AuditEngine()
    crawl = CrawlData(
        url="https://dbtest.com/",
        domain="dbtest.com",
        html_content="<html><head><title>DB Test</title></head><body><h1>X</h1><p>Test</p></body></html>",
        status_code=200,
        headers={},
        robots_txt="User-agent: *\nAllow: /",
        llms_txt="# T\n> D\n## S",
        is_https=True,
    )
    audit = engine.audit_crawl_data(crawl, sector="dental")
    audit.overall_score = score
    return audit


def _make_citation_result():
    from answrank.models import CitationRunResult, CitationQueryItem

    items = [
        CitationQueryItem(
            question_id=0,
            question="Soru 0",
            model="Perplexity-Sonar",
            brand_mentioned=True,
            domain_cited=True,
            raw_snippet="...",
            was_simulated=False,
        )
    ]
    return CitationRunResult(
        run_id="run_dbtest",
        brand_name="DBTest",
        domain="dbtest.com",
        sector="dental",
        city="İstanbul",
        timestamp=utc_now(),
        total_runs=1,
        brand_citations_found=1,
        citation_rate_percentage=100.0,
        live_items_count=1,
        live_response_rate_percentage=100.0,
        is_fully_live=True,
        items=items,
    )


@pytest.fixture()
def db():
    path = _tmp_db()
    instance = Database(db_path=path)
    yield instance
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.anyio
async def test_prospect_roundtrip(db):
    p = Prospect(
        id="prop-1",
        brand_name="Test Klinik",
        sector="dental",
        city="İzmir",
        website_url="https://testklinik.com",
        contact_person="Dr. Ayşe",
        platform="instagram",
        status="lead",
    )
    await db.save_prospect(p)
    fetched = await db.get_prospect("prop-1")
    assert fetched is not None
    assert fetched["brand_name"] == "Test Klinik"
    assert fetched["platform"] == "instagram"

    # Replace and verify INSERT OR REPLACE semantics
    p2 = p.model_copy(update={"status": "contacted"})
    await db.save_prospect(p2)
    fetched2 = await db.get_prospect("prop-1")
    assert fetched2["status"] == "contacted"
    assert fetched2["city"] == "İzmir"


@pytest.mark.anyio
async def test_get_prospect_missing_returns_none(db):
    assert await db.get_prospect("no-such-id") is None


@pytest.mark.anyio
async def test_audit_roundtrip_and_recent_list(db):
    audit = _make_audit(55)
    await db.save_audit(audit, prospect_id="prop-1")

    fetched = await db.get_audit(audit.audit_id)
    assert fetched is not None
    assert fetched["domain"] == "dbtest.com"
    assert fetched["overall_score"] == 55
    assert fetched["prospect_id"] == "prop-1"
    assert fetched["raw_json"]  # full JSON blob stored

    audit2 = _make_audit(70)
    await db.save_audit(audit2)
    recent = await db.list_recent_audits(limit=10)
    assert len(recent) == 2
    # ORDER BY created_at DESC — both present, scores intact
    scores = {r["overall_score"] for r in recent}
    assert scores == {55, 70}

    # limit respected
    recent_limited = await db.list_recent_audits(limit=1)
    assert len(recent_limited) == 1


@pytest.mark.anyio
async def test_citation_save(db):
    cite = _make_citation_result()
    await db.save_citations(cite)
    with db._get_connection() as conn:
        row = conn.execute("SELECT * FROM citations WHERE run_id = ?", ("run_dbtest",)).fetchone()
        assert row is not None
        assert dict(row)["citation_rate"] == 100.0


def test_swarm_candidate_stage_variants(db):
    # Enum stage
    db.save_swarm_candidate_sync({
        "id": "cand-enum",
        "brand_name": "Enum Stage",
        "domain": "enum.com",
        "stage": "QUALIFIED",
    })
    saved = db.get_swarm_candidate_sync("cand-enum")
    assert saved["stage"] == "QUALIFIED"

    # Missing candidate
    assert db.get_swarm_candidate_sync("missing") is None


def test_swarm_candidate_async_and_list(db):
    import asyncio

    async def _run():
        await db.save_swarm_candidate({
            "id": "cand-1",
            "brand_name": "Async Cand",
            "domain": "async.com",
            "sector": "legal",
            "city": "Berlin",
            "country": "DE",
            "currency": "EUR",
            "ticket_size": 2500.0,
            "stage": "CONTRACTED",
            "deep_score": 42.5,
            "territory_locked": True,
            "fixes_generated": {"fix": "add llms.txt"},
        })
        single = await db.get_swarm_candidate("cand-1")
        assert single is not None
        assert single["stage"] == "CONTRACTED"
        assert single["territory_locked"] is True
        assert single["fixes_generated"] == {"fix": "add llms.txt"}

        listed = await db.list_swarm_candidates(limit=5)
        assert any(c["id"] == "cand-1" for c in listed)

    asyncio.run(_run())


def test_territory_lock_save_and_list(db):
    lock = {
        "lock_id": "lock-1",
        "country": "UK",
        "city": "London",
        "niche": "dental",
        "client_domain": "kensingtonsmiles.co.uk",
        "brand_name": "Kensington Smiles",
        "tier": "EXCLUSIVE",
        "contract_id": "contract-9",
    }
    db.save_territory_lock_sync(lock)
    locks = db.list_territory_locks_sync()
    assert len(locks) == 1
    assert locks[0]["lock_id"] == "lock-1"
    assert locks[0]["client_domain"] == "kensingtonsmiles.co.uk"
    assert locks[0]["contract_id"] == "contract-9"


# ---------- latest-citations-for-domain getter (SoV bridge source) ----------

def test_get_latest_citations_for_domain_roundtrip_and_order(isolated_db_path):
    import asyncio
    from datetime import timedelta
    from answrank.db import Database
    from answrank.models import CitationRunResult, CitationQueryItem, utc_now

    db = Database()

    def _run(brand, ts):
        # Rapor okuyucusu ancak geçerli tam-ölçüm koşuyu render eder;
        # sahte/eksik koşu SoV sayısı olarak sunulmaz.
        return CitationRunResult(
            run_id=f"r_{brand}", brand_name=brand, domain="t.com", sector="dental",
            city="Istanbul", total_runs=2, brand_citations_found=1,
            citation_rate_percentage=50.0, timestamp=ts, is_fully_live=True,
            live_items_count=2, live_response_rate_percentage=100.0,
            grounding_status={"test-model": "model-recall"},
            items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                     model="test-model", was_simulated=False,
                                     brand_mentioned=i == 0) for i in range(2)],
        )

    async def go():
        await db.save_citations(_run("Eski", utc_now() - timedelta(days=2)))
        await db.save_citations(_run("Yeni", utc_now()))
        got = await db.get_latest_citations_for_domain("t.com")
        assert got is not None and got.brand_name == "Yeni"
        assert await db.get_latest_citations_for_domain("yok.com") is None
    asyncio.run(go())


def test_get_latest_citations_stops_on_malformed_newest_row(isolated_db_path):
    """Sözleşme: SON koşu geçersizse dur — eski koşuya dönüş yok."""
    import asyncio, contextlib, sqlite3
    from answrank.db import Database
    from answrank.models import CitationRunResult, CitationQueryItem
    db = Database()

    async def go():
        await db.save_citations(CitationRunResult(
            run_id="good", brand_name="Iyi", domain="m.com", sector="dental",
            city="Istanbul", total_runs=2, brand_citations_found=1,
            citation_rate_percentage=50.0, is_fully_live=True,
            live_items_count=2, live_response_rate_percentage=100.0,
            grounding_status={"test-model": "model-recall"},
            items=[CitationQueryItem(question_id=i, question=f"Q{i}",
                                     model="test-model", was_simulated=False,
                                     brand_mentioned=i == 0) for i in range(2)],
        ))
        with contextlib.closing(sqlite3.connect(db.db_path)) as conn:
            conn.execute(
                "INSERT INTO citations (id, run_id, brand_name, domain, sector, city, total_runs,"
                " citations_found, citation_rate, raw_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("cite_bad", "bad", "X", "m.com", "dental", "I", 1, 0, 0.0, "{bozuk json", "2099-01-01T00:00:00"),
            )
            conn.commit()
        # bozuk EN SON koşu: eski koşuya dönülmez, hiçbir şey render edilmez
        got = await db.get_latest_citations_for_domain("m.com")
        assert got is None
    asyncio.run(go())


def test_legacy_db_without_evidence_run_id_is_migrated(tmp_path, monkeypatch):
    """Eski DB (sütun yok) açıldığında evidence_run_id otomatik eklenmeli."""
    import sqlite3, contextlib
    from answrank.db import Database
    from answrank.config import settings
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(settings, "db_path", path)
    monkeypatch.setenv("ANSWRANK_DB_PATH", path)
    with contextlib.closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TABLE approval_queue (id INTEGER PRIMARY KEY,"
                  " kind TEXT, ref_id TEXT, status TEXT DEFAULT 'PENDING')")
        c.commit()
    db = Database()
    with db._get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(approval_queue)")}
    assert "evidence_run_id" in cols, "eski DB göç edilmedi"


def test_legacy_db_still_enforces_status_check(tmp_path, monkeypatch):
    """Göç sonrası yeni yazımlar CHECK(status) ile sınırlı: 'BOGUS' reddedilmeli."""
    import sqlite3, contextlib
    from answrank.db import Database
    from answrank.config import settings
    path = str(tmp_path / "legacy2.db")
    monkeypatch.setattr(settings, "db_path", path)
    monkeypatch.setenv("ANSWRANK_DB_PATH", path)
    with contextlib.closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TABLE approval_queue (id INTEGER PRIMARY KEY,"
                  " kind TEXT, ref_id TEXT, status TEXT DEFAULT 'PENDING')")
        c.commit()
    Database()  # tablo şemayı _ensure_columns ile göçürür
    # göçlü tabloda geçersiz status yazımı CHECK tarafından reddedilir
    with contextlib.closing(sqlite3.connect(path)) as c:
        try:
            c.execute("INSERT INTO approval_queue (kind, ref_id, status)"
                      " VALUES ('DM','x.example','BOGUS')")
            c.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
    assert raised, "göçlü DB geçersiz status yazımını engellemeli"




def test_get_latest_citations_for_domain_returns_none_on_corrupt_json(isolated_db_path):
    """Bozuk raw_json None dönmeli — uydurma run gösterilmez (fail-closed)."""
    import asyncio
    from answrank.db import Database
    db = Database()
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO citations (id, run_id, brand_name, domain, sector, city,"
            " total_runs, citations_found, citation_rate, raw_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("cite_bad", "run-bad", "X", "corrupt.com", "d", "c", 1, 0, 0.0,
             "{bu geçerli json değil", "2026-09-18T00:00:00+00:00"))
        conn.commit()
    assert asyncio.run(db.get_latest_citations_for_domain("corrupt.com")) is None
