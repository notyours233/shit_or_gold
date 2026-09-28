from __future__ import annotations

import asyncio
import json
import os
import signal
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def duration_seconds_between(started_at_utc: str | None, finished_at_utc: str | None) -> float | None:
    """Return a non-negative elapsed duration for two persisted ISO timestamps."""
    if not started_at_utc or not finished_at_utc:
        return None
    try:
        started = datetime.fromisoformat(str(started_at_utc).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(finished_at_utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return round(max(0.0, (finished - started).total_seconds()), 3)


def finish_job_timing(job: "Job", *, finished_at_utc: str | None = None) -> None:
    """Persist the finish timestamp and wall-clock duration on a job."""
    job.finished_at_utc = finished_at_utc or utc_now_iso()
    job.duration_seconds = duration_seconds_between(job.started_at_utc, job.finished_at_utc)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


@dataclass
class Job:
    id: str
    job_type: str
    status: str
    created_at_utc: str
    payload: dict[str, Any]

    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    duration_seconds: float | None = None
    cancel_requested_at_utc: str | None = None
    deleted_at_utc: str | None = None

    command: list[str] | None = None
    cwd: str | None = None
    log_path: str | None = None
    result_path: str | None = None

    returncode: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["duration_seconds"] is None:
            data["duration_seconds"] = duration_seconds_between(self.started_at_utc, self.finished_at_utc)
        return data

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        return cls(**d)


class JobStore:
    """File-backed job store.

    Layout:
      <root>/
        <job_id>/
          job.json
          job.log
          result.json (optional)
          artifacts/...
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def job_json_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def job_log_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.log"

    def job_result_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "result.json"

    def create(self, job_type: str, payload: dict[str, Any]) -> Job:
        jid = str(uuid.uuid4())
        job = Job(
            id=jid,
            job_type=str(job_type),
            status="queued",
            created_at_utc=utc_now_iso(),
            payload=payload,
        )
        self.save(job)
        return job

    def save(self, job: Job) -> None:
        d = job.to_dict()
        # Keep payload JSON-serializable.
        _atomic_write_json(self.job_json_path(job.id), d)

    def load(self, job_id: str) -> Job | None:
        p = self.job_json_path(job_id)
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            return Job.from_dict(raw)
        except Exception:
            return None

    def list_jobs(self, *, limit: int = 50) -> list[Job]:
        jobs: list[Job] = []
        for d in sorted(self.root.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir():
                continue
            j = self.load(d.name)
            if j:
                jobs.append(j)
            if len(jobs) >= limit:
                break
        return jobs


async def run_subprocess_to_log(
    *,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    on_chunk: Optional[Callable[[bytes], None]] = None,
    timeout_s: float | None = None,
) -> int:
    """Run a subprocess and stream combined stdout/stderr into a log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    assert proc.stdout is not None

    async def _stream_and_wait() -> int:
        with log_path.open("ab") as f:
            while True:
                chunk = await proc.stdout.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                f.flush()
                if on_chunk:
                    try:
                        on_chunk(chunk)
                    except Exception:
                        pass
        return await proc.wait()

    async def _terminate_process_group(*, reason: str, grace_s: float = 10.0) -> None:
        """Terminate this job's process group and reap the child process.

        Every job subprocess is started in a new session, so the PID is also
        the process-group leader.  Killing the group covers model/helper
        children that the MAD process may have spawned.
        """
        with log_path.open("ab") as f:
            f.write(f"\n[subprocess_{reason}] terminating process group\n".encode())
            f.flush()

        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=float(grace_s))
            return
        except asyncio.TimeoutError:
            pass

        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        await proc.wait()

    try:
        if timeout_s and timeout_s > 0:
            return await asyncio.wait_for(_stream_and_wait(), timeout=float(timeout_s))
        return await _stream_and_wait()
    except asyncio.CancelledError:
        # A UI cancellation propagates through the guarded task.  Reap the
        # subprocess before re-raising so the server cannot leave a worker
        # running after the job is marked cancelled.
        await _terminate_process_group(reason="cancelled")
        raise
    except TimeoutError:
        with log_path.open("ab") as f:
            f.write(f"\n[subprocess_timeout] exceeded {float(timeout_s):.0f}s\n".encode())
            f.flush()
        await _terminate_process_group(reason="timeout")
        return 124


def tail_text_file(path: Path, *, max_bytes: int = 200_000) -> str:
    """Read the last max_bytes of a text file (best-effort)."""
    if not path.exists():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""


def safe_env_for_subprocess() -> dict[str, str]:
    """Return a sanitized env dict for subprocesses (inherits current env)."""
    env = dict(os.environ)
    # Ensure Python is unbuffered for timely log streaming.
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env
