"""In-memory background jobs (downloads, imports, template copies) with progress for the UI to poll."""

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)
MAX_JOBS = 100


@dataclass
class Job:
    id: str
    kind: str
    label: str
    username: str
    server_id: int | None = None
    status: str = "running"  # running | done | error
    progress: float | None = None  # 0..1, None when unknown
    message: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created: float = field(default_factory=time.time)
    finished: float | None = None

    def update(self, progress: float | None = None, message: str | None = None) -> None:
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if message is not None:
            self.message = message

    def out(self) -> dict:
        return asdict(self)


_jobs: "OrderedDict[str, Job]" = OrderedDict()
_tasks: set[asyncio.Task] = set()


def start(
    kind: str, label: str, username: str, fn: Callable[[Job], Awaitable[dict | None]], server_id: int | None = None
) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label, username=username, server_id=server_id)
    _jobs[job.id] = job
    while len(_jobs) > MAX_JOBS:
        _jobs.popitem(last=False)

    async def runner():
        try:
            job.result = (await fn(job)) or {}
            job.status = "done"
            job.progress = 1.0
        except Exception as exc:  # noqa: BLE001  (reported to the user through the job)
            log.exception("Job %s (%s) failed", job.id, kind)
            job.status = "error"
            job.error = str(exc) or exc.__class__.__name__
        finally:
            job.finished = time.time()

    task = asyncio.create_task(runner())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def recent(limit: int = 30) -> list[Job]:
    return list(reversed(_jobs.values()))[:limit]
