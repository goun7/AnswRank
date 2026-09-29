"""Tests for the background job API (slice-2 of the 9h run).

Contract:
- POST /api/jobs/deep-audit returns job_id immediately (non-blocking).
- GET /api/jobs/{id} reports status transitions queued→running→completed.
- The final result payload equals the synchronous endpoint's shape.
- SSE /api/jobs/{id}/stream emits progress and a final snapshot.
- Failed jobs surface an error message, not a crash.
"""

import pytest
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient

from answrank.api.app import app
from answrank.api.jobs import JobManager, Job, JobStatus


client = TestClient(app)


# ---------- JobManager unit behavior ----------

@pytest.mark.anyio
async def test_job_lifecycle_transitions():
    jm = JobManager()

    async def work(job: Job):
        assert job.status == JobStatus.RUNNING
        jm.report_progress(job, 0.5, "halfway")
        return "payload"

    jid = await jm.submit("unit-test", work)
    # Give the background task a tick to run
    for _ in range(20):
        if jm.get(jid).status == JobStatus.COMPLETED:
            break
        await asyncio.sleep(0.01)

    job = jm.get(jid)
    assert job.status == JobStatus.COMPLETED
    assert job.result == "payload"
    assert job.progress == 1.0


@pytest.mark.anyio
async def test_job_failure_is_captured():
    jm = JobManager()

    async def failing(job: Job):
        raise RuntimeError("boom")

    jid = await jm.submit("fail-test", failing)
    for _ in range(20):
        if jm.get(jid).status in (JobStatus.COMPLETED, JobStatus.FAILED):
            break
        await asyncio.sleep(0.01)

    job = jm.get(jid)
    assert job.status == JobStatus.FAILED
    assert "boom" in job.error


@pytest.mark.anyio
async def test_job_manager_sse_subscription():
    jm = JobManager()

    async def work(job: Job):
        jm.report_progress(job, 0.4, "step-1")
        await asyncio.sleep(0.05)
        return 42

    jid = await jm.submit("sse-test", work)
    q = await jm.subscribe(jid)

    for _ in range(30):
        if jm.get(jid).status == JobStatus.COMPLETED:
            break
        await asyncio.sleep(0.01)

    # Drain the queue: must contain the queued event, progress, and done
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    kinds = [e.get("event") for e in events]
    assert "done" in kinds
    assert any(e.get("event") == "progress" and e.get("progress_pct") == 40.0 for e in events)


# ---------- HTTP endpoints ----------

def test_job_404_for_unknown_id():
    with TestClient(app) as c:
        res = c.get("/api/jobs/doesnotexist123")
        assert res.status_code == 404


def test_deep_audit_job_end_to_end():
    """Submit a deep-audit job with a mocked engine, poll until done, and
    verify the result payload carries the audit shape."""
    from answrank.audit.crawler import CrawlData
    from answrank.models import AuditResult, CategoryScores, DeepAuditResult, utc_now
    from answrank.audit.analyzers import (
        RobotsAnalyzer, LlmsTxtAnalyzer, SchemaAnalyzer, MetaAnalyzer,
        CitabilityAnalyzer, EntityAnalyzer, TrustAnalyzer, NegativeAnalyzer,
    )
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html><body><p>rich dental content london implants</p></body></html>", "html.parser")

    fake_audit = AuditResult(
        audit_id="audit_job1",
        url="https://jobtest.com",
        domain="jobtest.com",
        sector="dental",
        timestamp=utc_now(),
        overall_score=55,
        score_band="Foundation",
        categories=CategoryScores(
            robots=RobotsAnalyzer().analyze("User-agent: *\nAllow: /"),
            llms_txt=LlmsTxtAnalyzer().analyze("# T\n> s\n## A\n## B", None),
            schema_jsonld=SchemaAnalyzer().analyze(soup, sector="dental"),
            meta_architecture=MetaAnalyzer().analyze(soup),
            citability_rag=CitabilityAnalyzer().analyze(soup),
            entity_coherence=EntityAnalyzer().analyze(soup, domain="jobtest.com"),
            trust_stack=TrustAnalyzer().analyze(soup, is_https=True),
            negative_signals=NegativeAnalyzer().analyze(soup),
        ),
        recommendations=[],
    )

    class FakeCrawler:
        async def fetch(self, url):
            return CrawlData(
                url=url, domain="jobtest.com",
                html_content="<html><body><p>rich dental content london implants</p></body></html>",
                status_code=200, headers={}, robots_txt="User-agent: *\nAllow: /", is_https=True,
            )

    class FakeEngine:
        crawler = FakeCrawler()

        async def audit_url_deep(self, url, **kwargs):
            return DeepAuditResult(
                base_audit=fake_audit, waf_probe=None, adversarial=None,
                entity_grounding=None, rag_analysis=None,
                composite_deep_score=61.0, deep_tier="STABLE", key_findings=[],
            )

        def audit_crawl_data(self, crawl, sector="general"):
            return fake_audit

    with TestClient(app) as c, patch("answrank.api.app.engine", FakeEngine()):
        submit = c.post("/api/jobs/deep-audit", json={"url": "https://jobtest.com"})
        assert submit.status_code == 200
        body = submit.json()
        assert "job_id" in body and "status_url" in body and "stream_url" in body

        job_id = body["job_id"]
        # Poll until completed (TestClient runs the app loop synchronously)
        final = None
        for _ in range(100):
            poll = c.get(f"/api/jobs/{job_id}")
            assert poll.status_code == 200
            data = poll.json()
            if data["status"] in ("completed", "failed"):
                final = data
                break
        assert final is not None, "job never finished"
        assert final["status"] == "completed"
        assert final["result"]["composite_deep_score"] == 61.0
        assert final["progress_pct"] == 100.0


def test_job_list_endpoint():
    with TestClient(app) as c:
        res = c.get("/api/jobs")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
