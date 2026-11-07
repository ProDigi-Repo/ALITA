"""Job queue: everything that writes to the index runs one job at a time (REQ-83).

Uploads, cluster recomputation and the graph/citation/provision rebuilds change shared data (Qdrant payloads, the
Neo4j graph, cluster assignments). Run side by side, two of them overwrite each other's results – two uploads would
both re-cluster the same database. Here they wait in line and run one after the other in a worker thread with its own
event loop, so they never block the chats.

- **Order across processes:** while a job runs it holds ``<DATA_DIR>/.write.lock`` (``flock``). The command line
  (``python -m app.ingestion``, ``seed``, ``migrate import``) takes the same lock, so a CLI import and an upload never
  run at the same time either.
- **Owner:** every job belongs to whoever started it (account, e-mail or "local"); only they and admins can see it.
- **Survives restarts:** each job is a JSON file in ``<DATA_DIR>/jobs``. Jobs that were queued or running when the
  server stopped are marked ``interrupted`` at the next start. Finished jobs are pruned (JOB_HISTORY, JOB_HISTORY_DAYS).
- **Context:** a job runs with the request's context (visible databases, see ``visibility``) and its own token meter.

Statuses: queued → running → done | error; interrupted after a restart.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import queue
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fileio import atomic_write_json

log = logging.getLogger(__name__)

FINISHED = ("done", "error", "interrupted")

# REQ-87: the steps a job of each kind goes through, in order (from jobs.step() calls) – for its progress bar
_FOLLOW = ["Clustering", "Citation network", "Links to legal provisions"]
PIPELINES = {
    "file": ["Reading the file", "Summary, methods and keywords (LLM)",
             "Chunks, embeddings, rhetorical roles and knowledge graph", *_FOLLOW],
    "project": ["Reading the files", "Summaries, methods and keywords (LLM)",
                "Chunks, embeddings, rhetorical roles and knowledge graph", *_FOLLOW],
    "legal": ["Reading and parsing the legal text", "Summaries (LLM)", "Text units and embeddings", "Knowledge graph"],
}


def pipeline_of(kind: str) -> list[str]:
    """Expected steps of a job kind (empty for maintenance jobs without steps)."""
    if kind == "project":
        return PIPELINES["project"]
    if kind in ("legal_project", "legal_guideline", "standard", "guidance"):
        return PIPELINES["legal"]
    if kind in ("research_paper", "research_notes"):
        return PIPELINES["file"]
    return []
INTERRUPTED = "The server restarted before this job finished – please start it again."


@dataclass
class Job:
    """One queued unit of work and what came of it."""
    id: str
    kind: str
    name: str
    owner: str
    status: str = "queued"
    created: str = ""
    started: str | None = None
    finished: str | None = None
    result: Any = None
    error: str | None = None
    usage: dict | None = None
    waiting_for_lock: bool = False      # another process (CLI, seed) is writing
    step: str | None = None             # REQ-84: pipeline step of a running job, e.g. "Embeddings"
    steps: list = field(default_factory=list)   # steps done so far, in order
    extra: dict = field(default_factory=dict)

    def public(self, position: int | None = None) -> dict:
        """The job as the API returns it (with its place in the queue while it waits and its progress 0–1)."""
        d = asdict(self)
        d.update(d.pop("extra") or {})
        if position is not None:
            d["position"] = position
        d["progress"] = self.progress()
        return d

    def progress(self) -> float:
        """Rough share done: 1 when finished, 0 while waiting, else by the position of the current step."""
        if self.status in FINISHED:
            return 1.0
        if self.status != "running":
            return 0.0
        steps = pipeline_of(self.kind)
        if not steps or not self.step:
            return 0.5 if not steps else 0.02
        idx = steps.index(self.step) if self.step in steps else len(self.steps)
        return round(min(0.97, (idx + 0.5) / len(steps)), 3)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir() -> Path:
    from .config import get_settings
    return Path(get_settings().data_dir) / "jobs"


# ----------------------------------------------------------------- write lock across processes
@contextlib.contextmanager
def write_lock(on_wait: Callable[[], None] | None = None, poll: float = 1.0) -> Iterator[None]:
    """Exclusive write lock on ``<DATA_DIR>/.write.lock`` for this process and every other one using the data folder.
    ``on_wait`` is called once if another process holds the lock. Without ``fcntl`` (Windows) only this process waits."""
    from .config import get_settings
    path = Path(get_settings().data_dir) / ".write.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCAL_LOCK:
        try:
            import fcntl
        except ImportError:            # pragma: no cover – Windows without Docker
            yield
            return
        with open(path, "a+") as f:
            told = False
            while True:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not told and on_wait:
                        on_wait()
                        told = True
                    time.sleep(poll)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


_LOCAL_LOCK = threading.RLock()


# ----------------------------------------------------------------- the queue
class JobQueue:
    """Jobs of this process, run one at a time by a single worker thread."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._work: dict[str, tuple[contextvars.Context, Callable[[], Awaitable[Any]]]] = {}
        self._done: dict[str, threading.Event] = {}
        self._q: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loaded = False

    # -- persistence
    def _save(self, job: Job) -> None:
        try:
            atomic_write_json(_dir() / f"{job.id}.json", asdict(job), default=str)
        except Exception as e:  # noqa: BLE001 – the job itself must not fail because its record could not be written
            log.warning("Job %s not saved: %s", job.id, e)

    def load(self) -> int:
        """Read the stored jobs (once); queued or running ones of an earlier process become ``interrupted``."""
        import json
        with self._lock:
            if self._loaded:
                return 0
            self._loaded = True
            fixed = 0
            d = _dir()
            for f in sorted(d.glob("*.json")) if d.is_dir() else []:
                try:
                    job = Job(**json.loads(f.read_text(encoding="utf-8")))
                except Exception as e:  # noqa: BLE001 – a broken record is skipped, not fatal
                    log.warning("Job record %s skipped: %s", f.name, e)
                    continue
                if job.id in self.jobs:
                    continue
                if job.status not in FINISHED:
                    job.status, job.error, job.finished = "interrupted", INTERRUPTED, _now()
                    self._save(job)
                    fixed += 1
                self.jobs[job.id] = job
        self.prune()
        if fixed:
            log.info("%d job(s) of the previous run marked as interrupted", fixed)
        return fixed

    def prune(self) -> None:
        """Forget finished jobs beyond JOB_HISTORY or older than JOB_HISTORY_DAYS."""
        from .config import get_settings
        s = get_settings()
        cutoff = datetime.now(timezone.utc).timestamp() - s.job_history_days * 86400
        with self._lock:
            done = sorted((j for j in self.jobs.values() if j.status in FINISHED), key=lambda j: j.created, reverse=True)
            drop = done[s.job_history:] + [j for j in done[: s.job_history] if parse_ts(j.created) < cutoff]
            for j in drop:
                self.jobs.pop(j.id, None)
                with contextlib.suppress(OSError):
                    (_dir() / f"{j.id}.json").unlink()

    # -- submit and wait
    def submit(self, kind: str, name: str, owner: str, factory: Callable[[], Awaitable[Any]], **extra) -> Job:
        """Queue ``factory()`` (an async function returning the result) and return the job at once."""
        self.load()
        job = Job(id=str(uuid.uuid4()), kind=kind, name=name, owner=owner, created=_now(), extra=extra)
        with self._lock:
            self.jobs[job.id] = job
            self._work[job.id] = (contextvars.copy_context(), factory)
            self._done[job.id] = threading.Event()
        self._save(job)
        self._q.put(job.id)
        self._ensure_worker()
        return job

    async def wait(self, job_id: str, timeout: float | None = None) -> Job:
        """Wait (without blocking the event loop) until the job is finished or ``timeout`` seconds have passed."""
        ev = self._done.get(job_id)
        if ev is not None:
            await asyncio.get_running_loop().run_in_executor(None, ev.wait, timeout)
        return self.jobs[job_id]

    def position(self, job_id: str) -> int | None:
        """1 = next in line; None when the job is not waiting."""
        with self._lock:
            waiting = [j for j in self.jobs.values() if j.status == "queued"]
        waiting.sort(key=lambda j: j.created)
        ids = [j.id for j in waiting]
        return ids.index(job_id) + 1 if job_id in ids else None

    def view(self, job_id: str) -> dict | None:
        """API view of one job, with its queue position."""
        self.load()
        job = self.jobs.get(job_id)
        return None if job is None else job.public(self.position(job_id))

    def list(self, owner: str | None = None, limit: int = 50) -> list[dict]:
        """Newest jobs first – of one owner, or of everybody when owner is None."""
        self.load()
        with self._lock:
            jobs = [j for j in self.jobs.values() if owner is None or j.owner == owner]
        jobs.sort(key=lambda j: j.created, reverse=True)
        return [j.public(self.position(j.id)) for j in jobs[:limit]]

    def busy(self) -> bool:
        """True while a job is queued or running."""
        return any(j.status in ("queued", "running") for j in self.jobs.values())

    # -- the worker
    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run_forever, name="alita-jobs", daemon=True)
                self._thread.start()

    def _run_forever(self) -> None:
        while True:
            job_id = self._q.get()
            try:
                self._run(job_id)
            except Exception:  # noqa: BLE001 – the worker must survive any job
                log.exception("Job %s crashed the worker step", job_id)
            finally:
                self._done.pop(job_id, threading.Event()).set()
                self._work.pop(job_id, None)

    def _run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        ctx, factory = self._work[job_id]

        def waiting() -> None:
            job.waiting_for_lock = True
            self._save(job)

        with write_lock(on_wait=waiting):
            job.status, job.started, job.waiting_for_lock = "running", _now(), False
            self._save(job)
            ctx.run(asyncio.run, self._execute(job, factory))
        job.finished = _now()
        self._save(job)
        self.prune()

    @staticmethod
    async def _execute(job: Job, factory: Callable[[], Awaitable[Any]]) -> None:
        from . import usage
        meter = usage.start()                    # tokens of this job (LLM + embeddings), shown after an upload
        _CURRENT.set(job)
        try:
            res = await factory()
            job.result = res.model_dump(mode="json", exclude={"source_path"}) if hasattr(res, "model_dump") else res
            job.status = "done"
            if job.step:
                job.steps.append(job.step)
            job.step = None
        except Exception as e:  # noqa: BLE001 – the failure is shown in the job status
            log.exception("Job %s (%s %s) failed", job.id, job.kind, job.name)
            job.status, job.error = "error", str(e) or type(e).__name__
        try:
            job.usage = await asyncio.to_thread(usage.summary, meter)
        except Exception as e:  # noqa: BLE001 – the cost display must not break the job
            log.warning("Usage of job %s not computed: %s", job.id, e)


def parse_ts(iso: str | None) -> float:
    """Epoch seconds of an ISO time stamp of a job record; 0 when missing or malformed."""
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else 0.0
    except (TypeError, ValueError):
        return 0.0


QUEUE = JobQueue()
_CURRENT: contextvars.ContextVar[Job | None] = contextvars.ContextVar("alita_job", default=None)


def step(text: str) -> None:
    """REQ-84: report the pipeline step of the running job (shown in the upload tile); no-op outside a job (CLI)."""
    job = _CURRENT.get()
    if job is None or job.step == text:
        return
    if job.step:
        job.steps.append(job.step)
    job.step = text
    QUEUE._save(job)


def owner_of(request) -> str:
    """Who started a request: the account, the Cloudflare e-mail, "reviewer" or "local"."""
    acc = getattr(request.state, "account", None)
    if acc is not None:
        return f"account:{acc.user}"
    email = getattr(request.state, "email", None)
    if email:
        return f"email:{email}"
    return getattr(request.state, "auth_mode", None) or "local"


def may_see(request, job: dict) -> bool:
    """Owners see their own jobs, admins every job."""
    return bool(getattr(request.state, "is_admin", False)) or job.get("owner") == owner_of(request)
