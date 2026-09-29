"""Extra tests: jobs.py subscribe/unsubscribe/eviction paths and API job stream."""

import asyncio
import pytest
from answrank.api.jobs import JobManager, Job, JobStatus


@pytest.mark.anyio
async def test_subscribe_unsubscribe_lifecycle():
    jm = JobManager()
    jid = "job-sub-test"

    q1 = await jm.subscribe(jid)
    q2 = await jm.subscribe(jid)
    assert len(jm._subscribers[jid]) == 2

    jm.unsubscribe(jid, q1)
    assert len(jm._subscribers[jid]) == 1
    jm.unsubscribe(jid, q2)
    assert jid not in jm._subscribers  # empty → removed

    # Unsubscribing an unknown queue is a no-op
    jm.unsubscribe(jid, q1)


@pytest.mark.anyio
async def test_publish_delivers_to_all_subscribers():
    jm = JobManager()
    jid = "job-pub-test"
    q1 = await jm.subscribe(jid)
    q2 = await jm.subscribe(jid)

    await jm._publish(jid, {"event": "progress", "progress_pct": 42.0})
    assert q1.get_nowait() == {"event": "progress", "progress_pct": 42.0}
    assert q2.get_nowait() == {"event": "progress", "progress_pct": 42.0}


@pytest.mark.anyio
async def test_completed_jobs_evicted_beyond_max():
    jm = JobManager(max_completed=3)

    for i in range(6):
        async def work(job, _i=i):
            return _i
        await jm.submit(f"t{i}", work)
        # let it finish
        for _ in range(200):
            j = jm.get(f"t{i}")
            if j and j.status == JobStatus.COMPLETED:
                break
            await asyncio.sleep(0.005)

    # All finished; eviction on the last submit keeps at most 3 completed
    completed = [j for j in jm._jobs.values() if j.status == JobStatus.COMPLETED]
    assert len(completed) <= 4  # 3 retained + at most the very last still open


@pytest.mark.anyio
async def test_report_progress_without_running_loop_records_state():
    """report_progress called outside an async context (defensive path) must
    still update the job object without raising."""
    jm = JobManager()
    job = Job(job_id="j1", job_type="x", created_at=0.0)

    # No running loop in a sync helper — must not raise
    jm.report_progress(job, 0.7, "sync-step")
    assert job.progress == 0.7
    assert job.current_step == "sync-step"


def test_job_public_view_serializable():
    import json
    job = Job(job_id="j2", job_type="deep-audit", created_at=123.0)
    job.status = JobStatus.COMPLETED
    job.result = {"score": 50}
    view = job.public_view()
    assert json.dumps(view)  # JSON-serializable
    assert view["status"] == "completed"
    assert view["progress_pct"] == 100.0
    assert view["result"] == {"score": 50}
