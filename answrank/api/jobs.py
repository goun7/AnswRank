"""Background job manager for long-running AnswRank operations.

POST /api/jobs/deep-audit and similar endpoints accept a request, return a
job_id immediately, run the work on a background asyncio task, and expose:

    GET /api/jobs/{job_id}         → status/progress/result
    GET /api/jobs/{job_id}/stream  → SSE live progress

Jobs live in memory (single-process deployments). Completed jobs are kept for
a retention window and then evicted. No new dependencies.
"""

import asyncio
import time
import uuid
from enum import Enum
from typing import Dict, Any, Optional, Callable, Awaitable, List
from dataclasses import dataclass, field

import logging

logger = logging.getLogger("answrank.jobs")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    job_type: str
    created_at: float
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0            # 0..1
    current_step: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    completed_at: Optional[float] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    _task: Optional[asyncio.Task] = None  # runtime handle, not serialized

    def public_view(self) -> Dict[str, Any]:
        """Bir işin herkese-açık görünümünü döndürür."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "progress_pct": round(self.progress * 100, 1) if self.status != JobStatus.COMPLETED else 100.0,
            "current_step": self.current_step,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class JobManager:
    """In-memory background job registry with progress callbacks and SSE support."""

    def __init__(self, max_completed: int = 50, retention_seconds: float = 3600.0):
        self._jobs: Dict[str, Job] = {}
        self._max_completed = max_completed
        self._retention = retention_seconds
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    # -- public API ---------------------------------------------------------

    async def submit(
        self,
        job_type: str,
        work: Callable[["Job"], Awaitable[Any]],
    ) -> str:
        """Registers and immediately starts a background job; returns job_id."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id=job_id, job_type=job_type, created_at=time.time())
        self._jobs[job_id] = job

        async def _runner():
            job.status = JobStatus.RUNNING
            try:
                job.result = await work(job)
                job.status = JobStatus.COMPLETED
                job.progress = 1.0
            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                logger.exception("Job %s (%s) failed", job_id, job_type)
            finally:
                job.completed_at = time.time()
                await self._publish(job_id, {"event": "done", "status": job.status.value})

        job._task = asyncio.create_task(_runner())
        await self._publish(job_id, {"event": "queued"})
        self._evict_old_completed()
        return job_id

    def get(self, job_id: str) -> Optional[Job]:
        """Tek bir get kaydını döndürür; bulunamazsa None."""
        return self._jobs.get(job_id)

    def report_progress(self, job: Job, progress: float, step: str = "") -> None:
        """Called by the work function to update progress; must be non-blocking."""
        job.progress = max(0.0, min(1.0, progress))
        if step:
            job.current_step = step
        # Fire-and-forget publish (sync context inside async work)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._publish(job.job_id, {
                "event": "progress", "progress_pct": round(job.progress * 100, 1), "step": step,
            }))
        except RuntimeError:
            pass  # no running loop (unit tests) — progress still recorded on the job

    # -- SSE subscriptions ---------------------------------------------------

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        """Olay akışına abone olur."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        """Olay akışı aboneliğini sonlandırır."""
        subs = self._subscribers.get(job_id, [])
        if q in subs:
            subs.remove(q)
        if not subs:
            self._subscribers.pop(job_id, None)

    async def _publish(self, job_id: str, payload: Dict[str, Any]) -> None:
        for q in list(self._subscribers.get(job_id, [])):
            try:
                q.put_nowait(payload)
            except Exception as exc:
                # Slow SSE consumer with a full backlog: the event is dropped for
                # THIS subscriber only (others unaffected) — never silently.
                logger.debug("SSE publish dropped for one subscriber of %s: %s", job_id, exc)

    # -- housekeeping ---------------------------------------------------------

    def _evict_old_completed(self) -> None:
        """Keeps at most max_completed finished jobs, oldest first."""
        finished = [j for j in self._jobs.values() if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)]
        if len(finished) <= self._max_completed:
            return
        finished.sort(key=lambda j: j.completed_at or 0)
        excess = len(finished) - self._max_completed
        for j in finished[:excess]:
            self._jobs.pop(j.job_id, None)
            self._subscribers.pop(j.job_id, None)


# Process-wide singleton (single-process deployment model, like the DB handle)
job_manager = JobManager()

__all__ = ["JobManager", "job_manager", "Job", "JobStatus"]
