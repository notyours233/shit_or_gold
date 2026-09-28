from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from chemcouncil import server as server_module
from chemcouncil.jobs import Job, JobStore, finish_job_timing, run_subprocess_to_log
from chemcouncil.workflows import RepoPaths, run_mad_rank_job


def _job() -> Job:
    return Job(
        id="timing-job",
        job_type="mad_rank",
        status="running",
        created_at_utc="2026-08-13T10:00:00+00:00",
        payload={},
        started_at_utc="2026-08-13T10:00:01+00:00",
    )


def test_job_timing_is_persisted_and_legacy_jobs_are_backfilled() -> None:
    job = _job()
    finish_job_timing(job, finished_at_utc="2026-08-13T10:01:31+00:00")
    assert job.duration_seconds == 90.0
    assert job.to_dict()["duration_seconds"] == 90.0

    job.duration_seconds = None
    assert job.to_dict()["duration_seconds"] == 90.0


def test_mad_rank_result_contains_backend_timing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    (root / "MAD" / "config").mkdir(parents=True)
    (root / "MAD" / "config" / "config.yaml").write_text("paths: {}\nlogging: {}\n", encoding="utf-8")

    store = JobStore(tmp_path / "jobs")
    job = store.create("mad_rank", {"material_name": "CuO"})

    async def _fake_subprocess(**_kwargs) -> int:
        outputs = store.job_dir(job.id) / "artifacts" / "mad_outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        (outputs / "rank_test.json").write_text(
            json.dumps(
                {
                    "material_name": "CuO",
                    "selection_mode": "single",
                    "direction_count": 1,
                    "ranking": [],
                    "top_k": [],
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr("chemcouncil.workflows.run_subprocess_to_log", _fake_subprocess)
    asyncio.run(
        run_mad_rank_job(
            job=job,
            store=store,
            paths=RepoPaths.from_root(root),
            python_bin="python",
            material_input={"material_name": "CuO"},
            top_k_properties=1,
            task_types=["conductivity"],
            max_parallel_properties=1,
            save_each_task=True,
        )
    )

    saved = store.load(job.id)
    assert saved is not None
    assert saved.status == "completed"
    assert saved.started_at_utc
    assert saved.finished_at_utc
    assert saved.duration_seconds is not None

    result = json.loads(store.job_result_path(job.id).read_text(encoding="utf-8"))
    assert result["recommendation_timing"] == {
        "started_at_utc": saved.started_at_utc,
        "finished_at_utc": saved.finished_at_utc,
        "duration_seconds": saved.duration_seconds,
    }


def test_subprocess_is_reaped_when_task_is_cancelled(tmp_path: Path) -> None:
    """Cancelling a workflow task must terminate and reap its MAD child."""
    pid_file = tmp_path / "child.pid"
    log_path = tmp_path / "job.log"
    code = (
        "import os, pathlib, time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(300)"
    )

    async def _run_and_cancel() -> int:
        task = asyncio.create_task(
            run_subprocess_to_log(
                cmd=[sys.executable, "-c", code],
                cwd=tmp_path,
                env=dict(os.environ),
                log_path=log_path,
            )
        )
        child_pid = None
        for _ in range(100):
            if pid_file.exists():
                child_pid = int(pid_file.read_text(encoding="utf-8"))
                break
            await asyncio.sleep(0.02)
        assert child_pid is not None

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return child_pid

    child_pid = asyncio.run(_run_and_cancel())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        raise AssertionError(f"cancelled subprocess {child_pid} is still alive")


def test_find_job_pids_uses_ps_on_hosts_without_proc(monkeypatch) -> None:
    job_id = "job-without-proc"
    real_exists = Path.exists

    def _exists(path: Path) -> bool:
        if str(path) == "/proc":
            return False
        return real_exists(path)

    monkeypatch.setattr(Path, "exists", _exists)
    monkeypatch.setattr(
        server_module,
        "_process_commands_from_ps",
        lambda: [(123, f"python main.py --job {job_id}"), (456, "python unrelated.py")],
    )
    monkeypatch.setattr(server_module.os, "getpid", lambda: 999)

    assert server_module._find_job_pids(job_id) == [123]
