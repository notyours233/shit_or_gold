from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from chemcouncil.jobs import JobStore, run_subprocess_to_log, utc_now_iso
from chemcouncil.server import _reconcile_jobs_on_startup, _run_job_guarded, handle_job_cancel


class _CancelRequest:
    def __init__(self, app: dict, job_id: str):
        self.app = app
        self.match_info = {"job_id": job_id}


def test_cancel_endpoint_terminates_running_subprocess(tmp_path: Path) -> None:
    """The same endpoint used by the UI must stop the child process too."""
    async def _scenario() -> tuple[dict, int]:
        store = JobStore(tmp_path / "jobs")
        job = store.create("mad_rank", {"material_name": "CuO"})
        job.status = "running"
        job.started_at_utc = utc_now_iso()
        store.save(job)

        pid_file = tmp_path / "child.pid"
        log_path = store.job_log_path(job.id)
        code = (
            "import os, pathlib, time; "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
            "time.sleep(300)"
        )

        async def _worker() -> None:
            await run_subprocess_to_log(
                cmd=[sys.executable, "-c", code, "--job-id", job.id],
                cwd=tmp_path,
                env=dict(os.environ),
                log_path=log_path,
            )

        app = {
            "store": store,
            "tasks": {},
            "job_semaphore": asyncio.Semaphore(1),
        }
        app["tasks"][job.id] = asyncio.create_task(_run_job_guarded(app, job.id, _worker()))

        child_pid = None
        for _ in range(100):
            if pid_file.exists():
                child_pid = int(pid_file.read_text(encoding="utf-8"))
                break
            await asyncio.sleep(0.02)
        assert child_pid is not None

        response = await handle_job_cancel(_CancelRequest(app, job.id))
        payload = json.loads(response.text)
        assert response.status == 200
        assert payload["status"] == "cancelled"
        assert payload["remaining_pids"] == []

        for _ in range(50):
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError(f"cancelled subprocess {child_pid} is still alive")
        return payload, child_pid

    asyncio.run(_scenario())


def test_startup_reconciliation_cleans_noncompleted_worker(tmp_path: Path) -> None:
    """A restart must also clean workers left by an older server version."""
    async def _scenario() -> None:
        store = JobStore(tmp_path / "jobs")
        job = store.create("mad_rank", {"material_name": "CuO"})
        job.status = "cancelled"
        store.save(job)

        pid_file = tmp_path / "child.pid"
        code = (
            "import os, pathlib, time; "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
            "time.sleep(300)"
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            "--job-id",
            job.id,
            cwd=str(tmp_path),
            env=dict(os.environ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            for _ in range(100):
                if pid_file.exists():
                    break
                await asyncio.sleep(0.02)
            assert pid_file.exists()

            await _reconcile_jobs_on_startup({"store": store})
            await asyncio.wait_for(proc.wait(), timeout=2)
            assert proc.returncode is not None
        finally:
            if proc.returncode is None:
                os.killpg(proc.pid, 9)
                await proc.wait()

    asyncio.run(_scenario())
