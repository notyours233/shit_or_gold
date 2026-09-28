from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web
from dotenv import load_dotenv

from .analytics import (
    RecommendationContext,
    aggregate_prediction_error_records_for_analytics,
    canonical_reaction_type,
    collect_recommendation_job_ids_from_csv,
    compute_prediction_error_records_multi,
    compute_prediction_error_records_multi_debug,
    mean,
)
from .analytics_ignore import apply_ignore_csv_rows, parse_ignore_request_body, read_ignore_csv_rows
from .jobs import Job, JobStore, finish_job_timing, tail_text_file, utc_now_iso
from .workflows import (
    RepoPaths,
    discover_python_bin,
    run_experience_update_job,
    run_mad_rank_job,
    run_material_property_experience_job,
)


_ELEMENT_RE = re.compile(r"[A-Z][a-z]?")
MATERIAL_PROPERTY_TYPES = [
    "photothermal_conversion_efficiency",
    "conductivity",
    "thermal_conductivity",
    "ferromagnetism",
    "ferrimagnetism",
    "antiferromagnetism",
    "photocatalytic_h2o2",
    "antibacterial",
    "thermoelectric",
    "furfural_hydrogenation",
]
REACTION_TYPES = ["HER", "OER", "ORR", "HOR", "UOR", "EOR", "HZOR", "O5H", "CO2RR"]
TASK_TYPES = REACTION_TYPES + MATERIAL_PROPERTY_TYPES
EXPERIENCE_UPDATE_BATCH_SIZE_DEFAULT = 19
EXPERIENCE_UPDATE_GRPO_N_DEFAULT = 3
EXPERIENCE_UPDATE_ROLLOUT_CONCURRENCY_DEFAULT = 4
EXPERIENCE_UPDATE_EPOCHS_DEFAULT = 1
_PROPERTY_ALIASES = {
    "photothermal conversion efficiency": "photothermal_conversion_efficiency",
    "photothermal_conversion_efficiency": "photothermal_conversion_efficiency",
    "photothermal": "photothermal_conversion_efficiency",
    "conductivity": "conductivity",
    "electrical conductivity": "conductivity",
    "thermal conductivity": "thermal_conductivity",
    "thermal_conductivity": "thermal_conductivity",
    "ferromagnetism": "ferromagnetism",
    "ferromagnetic": "ferromagnetism",
    "ferrimagnetism": "ferrimagnetism",
    "ferrimagnetic": "ferrimagnetism",
    "antiferromagnetism": "antiferromagnetism",
    "anti ferromagnetism": "antiferromagnetism",
    "anti-ferromagnetism": "antiferromagnetism",
    "antiferromagnetic": "antiferromagnetism",
    "photocatalytic h2o2": "photocatalytic_h2o2",
    "photocatalytic hydrogen peroxide": "photocatalytic_h2o2",
    "antibacterial": "antibacterial",
    "antimicrobial": "antibacterial",
    "thermoelectric": "thermoelectric",
    "zt": "thermoelectric",
    "furfural hydrogenation": "furfural_hydrogenation",
    "furfuryl alcohol": "furfural_hydrogenation",
}
_REACTION_ALIASES = {
    "her": "HER",
    "hydrogen evolution": "HER",
    "oer": "OER",
    "oxygen evolution": "OER",
    "orr": "ORR",
    "oxygen reduction": "ORR",
    "hor": "HOR",
    "hydrogen oxidation": "HOR",
    "uor": "UOR",
    "urea oxidation": "UOR",
    "eor": "EOR",
    "ethanol oxidation": "EOR",
    "hzor": "HZOR",
    "hydrazine oxidation": "HZOR",
    "o5h": "O5H",
    "co2rr": "CO2RR",
    "co2 reduction": "CO2RR",
    "carbon dioxide reduction": "CO2RR",
}


def _repo_root() -> Path:
    # chemcouncil/server.py -> chemcouncil -> <repo_root>
    return Path(__file__).resolve().parents[1]


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def _atomic_write_text_file(path: Path, text: str) -> None:
    """Atomic write that preserves symlinks by writing to the resolved target path."""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def _experience_pack_path(paths: "RepoPaths") -> Path:
    """Return the active stable experience pack path used by the UI.

    Preference order:
    1) CHEMCOUNCIL_EXPERIENCE_PACK_PATH (explicit override)
    2) /state/experience_youtu.yaml (Docker deployment)
    3) <repo_root>/youtu-chem-loop/configs/agents/practice/experience.yaml (repo default)
    """
    override = str(os.environ.get("CHEMCOUNCIL_EXPERIENCE_PACK_PATH") or "").strip()
    if override:
        p_override = Path(override)
        if not p_override.is_absolute():
            p_override = (paths.root / p_override).resolve()
        return p_override
    p0 = Path("/state/experience_youtu.yaml")
    if p0.exists():
        return p0
    return paths.youtu / "configs" / "agents" / "practice" / "experience.yaml"


def _safe_env_snapshot() -> dict[str, Any]:
    """Expose non-secret env hints for debugging."""
    def _has(name: str) -> bool:
        v = os.environ.get(name)
        return bool(v and str(v).strip())

    return {
        "UTU_DB_URL": os.environ.get("UTU_DB_URL"),
        "UTU_LLM_MODEL": os.environ.get("UTU_LLM_MODEL"),
        "UTU_LLM_BASE_URL": os.environ.get("UTU_LLM_BASE_URL"),
        "CHEMCOUNCIL_JOB_CONCURRENCY": os.environ.get("CHEMCOUNCIL_JOB_CONCURRENCY"),
        "CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY": os.environ.get("CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY"),
        "MAD_PYTHON_BIN": os.environ.get("MAD_PYTHON_BIN"),
        "MAD_ENABLE_RAG": os.environ.get("MAD_ENABLE_RAG"),
        "MAD_RAG_MODE": os.environ.get("MAD_RAG_MODE"),
        "MAD_RAG_SHARED_AGENT": os.environ.get("MAD_RAG_SHARED_AGENT"),
        "MAD_RAG_SHARED_COLLECTION": os.environ.get("MAD_RAG_SHARED_COLLECTION"),
        "MAD_RAG_SHARED_REACTION_COLLECTION": os.environ.get("MAD_RAG_SHARED_REACTION_COLLECTION"),
        "MAD_RAG_REACTION_PERSIST_DIR": os.environ.get("MAD_RAG_REACTION_PERSIST_DIR"),
        "keys_present": {
            "UTU_LLM_API_KEY": _has("UTU_LLM_API_KEY"),
            "OPENAI_API_KEY": _has("OPENAI_API_KEY"),
            "DEEPSEEK_API_KEY": _has("DEEPSEEK_API_KEY"),
            "GOOGLE_API_KEY": _has("GOOGLE_API_KEY"),
            "QWEN_API_KEY": _has("QWEN_API_KEY"),
            "VOYAGE_API_KEY": _has("VOYAGE_API_KEY"),
        },
    }


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    # Minimal CORS for API usage (safe defaults; tighten in production).
    resp.headers["Access-Control-Allow-Origin"] = os.environ.get("CHEMCOUNCIL_CORS_ORIGIN", "*")
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type"
    return resp


@web.middleware
async def auth_middleware(request: web.Request, handler):
    token = os.environ.get("CHEMCOUNCIL_API_TOKEN")
    if not token:
        return await handler(request)
    if not request.path.startswith("/api/"):
        return await handler(request)
    # Allow health without auth so people can test connectivity.
    if request.path == "/api/health":
        return await handler(request)

    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {token}":
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


def _json_error(message: str, *, status: int = 400, **extra) -> web.Response:
    payload = {"error": message}
    payload.update(extra)
    return web.json_response(payload, status=status)


def _extract_unique_elements_from_components(text: str) -> list[str]:
    uniq: list[str] = []
    seen: set[str] = set()
    for match in _ELEMENT_RE.findall(str(text or "")):
        if match in seen:
            continue
        seen.add(match)
        uniq.append(match)
    return uniq


def _positive_material_serial(value: Any) -> int:
    """Parse a user-facing material serial without imposing an arbitrary maximum."""
    if isinstance(value, bool):
        raise ValueError("material_serial_no must be a positive integer")
    text = str(value or "").strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError("material_serial_no must be a positive integer")
    serial = int(text)
    if serial < 1:
        raise ValueError("material_serial_no must be a positive integer")
    return serial


def _canonical_property_type(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in MATERIAL_PROPERTY_TYPES:
        return raw
    cleaned = raw.replace("_", " ").strip().lower()
    cleaned = re.sub(r"[\u2010-\u2015]+", "-", cleaned)
    cleaned = " ".join(cleaned.split())
    if cleaned in _PROPERTY_ALIASES:
        return _PROPERTY_ALIASES[cleaned]
    underscored = cleaned.replace("-", "_").replace(" ", "_")
    if underscored in MATERIAL_PROPERTY_TYPES:
        return underscored
    return None


def _canonical_task_type(value: Any) -> str | None:
    prop = _canonical_property_type(value)
    if prop:
        return prop
    raw = str(value or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in REACTION_TYPES:
        return upper
    cleaned = raw.replace("_", " ").strip().lower()
    cleaned = re.sub(r"[\u2010-\u2015]+", "-", cleaned)
    cleaned = " ".join(cleaned.split())
    if cleaned in _REACTION_ALIASES:
        return _REACTION_ALIASES[cleaned]
    compact = cleaned.replace(" ", "").replace("-", "")
    if compact in _REACTION_ALIASES:
        return _REACTION_ALIASES[compact]
    return None


async def handle_index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(_static_dir() / "index.html")


async def handle_health(request: web.Request) -> web.Response:
    app = request.app
    paths: RepoPaths = app["paths"]
    return web.json_response(
        {
            "status": "ok",
            "time_utc": utc_now_iso(),
            "repo_root": str(paths.root),
            "python_bin": app["python_bin"],
            "paths_ok": {
                "root": paths.root.exists(),
                "youtu": paths.youtu.exists(),
                "mad": paths.mad.exists(),
            },
            "env": _safe_env_snapshot(),
        }
    )


async def handle_jobs_list(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    limit = int(request.query.get("limit", "50") or 50)
    include_deleted = str(request.query.get("include_deleted", "0") or "0").strip().lower() in {"1", "true", "yes"}

    # We may need to scan more than `limit` because we can filter out deleted jobs.
    scan = max(200, limit * 10)
    jobs = []
    for j in store.list_jobs(limit=scan):
        if not include_deleted and getattr(j, "deleted_at_utc", None):
            continue
        jobs.append(j.to_dict())
        if len(jobs) >= limit:
            break
    return web.json_response({"jobs": jobs})


async def handle_job_get(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)
    return web.json_response(job.to_dict())


async def handle_job_log(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)
    log_path = Path(job.log_path) if job.log_path else store.job_log_path(job_id)
    text = tail_text_file(log_path)
    return web.Response(text=text, content_type="text/plain", charset="utf-8")


async def handle_job_result(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)
    if not job.result_path:
        # Fall back to convention.
        p = store.job_result_path(job_id)
    else:
        p = Path(job.result_path)
    if not p.exists():
        return _json_error("job result not available", status=404)
    try:
        return web.json_response(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return web.Response(text=p.read_text(encoding="utf-8", errors="replace"), content_type="text/plain", charset="utf-8")


def _job_mad_outputs_dir(store: JobStore, job_id: str) -> Path:
    return store.job_dir(job_id) / "artifacts" / "mad_outputs"


def _parse_rt_from_mad_result(payload: dict[str, Any]) -> str | None:
    # Typical shape (LangGraph mode):
    # {"result": {"performance_evaluation": {"reaction_type": "conductivity"}, ...}}
    for path in [
        ("result", "performance_evaluation", "reaction_type"),
        ("result", "reaction_type"),
        ("performance_evaluation", "reaction_type"),
        ("reaction_type",),
    ]:
        cur: Any = payload
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur.get(k)
        if not ok:
            continue
        rt = canonical_reaction_type(str(cur or "").strip())
        if rt:
            return rt
    return None


def _index_mad_result_files(mad_outputs_dir: Path) -> dict[str, Path]:
    """Return mapping reaction_type -> newest result_*.json path."""
    if not mad_outputs_dir.exists():
        return {}

    by_rt: dict[str, Path] = {}
    for p in sorted(mad_outputs_dir.glob("result_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        rt = _parse_rt_from_mad_result(raw)
        if not rt:
            continue
        if rt not in by_rt:
            by_rt[rt] = p
    return by_rt


async def handle_job_mad_traces_list(request: web.Request) -> web.Response:
    """List per-reaction MAD debate traces saved for a rank job (if --save-each-reaction was enabled)."""
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)

    mad_outputs = _job_mad_outputs_dir(store, job_id)
    by_rt = _index_mad_result_files(mad_outputs)

    items: list[dict[str, Any]] = []
    for rt in sorted(by_rt.keys()):
        p = by_rt[rt]
        mtime_utc = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        has_debate_history = False
        has_reasoning_trajectory = False
        debate_events = 0
        consensus_reached = None
        debate_rounds = None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                res = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                hist = res.get("debate_history")
                has_debate_history = bool(hist)
                debate_events = len(hist) if isinstance(hist, list) else 0
                has_reasoning_trajectory = bool(str(res.get("reasoning_trajectory") or "").strip())
                consensus_reached = res.get("consensus_reached")
                debate_rounds = res.get("debate_rounds")
        except Exception:
            pass
        items.append(
            {
                "reaction_type": rt,
                "file": p.name,
                "mtime_utc": mtime_utc,
                "url": f"/api/jobs/{job_id}/mad_traces/{rt}",
                "has_debate_history": has_debate_history,
                "has_reasoning_trajectory": has_reasoning_trajectory,
                "debate_events": debate_events,
                "consensus_reached": consensus_reached,
                "debate_rounds": debate_rounds,
            }
        )

    return web.json_response({"job_id": job_id, "items": items})


async def handle_job_mad_trace_get(request: web.Request) -> web.Response:
    """Get a single per-reaction MAD debate trace JSON."""
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    rt = canonical_reaction_type(str(request.match_info.get("reaction_type") or "").strip())
    if not rt:
        return _json_error("missing reaction_type", status=400)

    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)

    mad_outputs = _job_mad_outputs_dir(store, job_id)
    by_rt = _index_mad_result_files(mad_outputs)
    p = by_rt.get(rt)
    if not p:
        return _json_error(f"trace not found for reaction_type={rt}; available={sorted(by_rt.keys())}", status=404)

    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _json_error("failed to read trace json", status=500)
    if not isinstance(payload, dict):
        return _json_error("invalid trace json", status=500)
    return web.json_response(payload)


def _append_job_log(store: JobStore, job_id: str, text: str) -> None:
    """Append plain text to the job's log file (best-effort)."""
    try:
        p = store.job_log_path(job_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("ab") as f:
            f.write(text.encode("utf-8", errors="replace"))
            if not text.endswith("\n"):
                f.write(b"\n")
    except Exception:
        pass


async def _reconcile_jobs_on_startup(app: web.Application) -> None:
    """Reconcile stale job states after a server/container restart.

    Jobs are persisted on disk under `/state/jobs`. If the container/server restarts
    during a job, both the persisted state and the worker process may survive.
    Clean up any matching non-completed worker before marking the state terminal.
    """
    store: JobStore = app["store"]
    now = utc_now_iso()

    # Best-effort: never block server startup.
    try:
        for d in sorted(store.root.glob("*")):
            if not d.is_dir():
                continue
            job = store.load(d.name)
            if not job:
                continue

            # A previous server version could leave a cancelled worker alive,
            # especially on macOS where /proc does not exist.  Reconcile every
            # non-completed job so such workers do not survive a restart.
            if job.status != "completed":
                stale = _find_job_pids(job.id)
                if stale:
                    kill_info = _kill_job_processes(job.id, sig=signal.SIGTERM)
                    await asyncio.sleep(0.6)
                    remaining = _find_job_pids(job.id)
                    if remaining:
                        force_info = _kill_job_processes(job.id, sig=signal.SIGKILL)
                        kill_info["sigkill_pids"].extend(force_info["sigkill_pids"])
                        remaining = _find_job_pids(job.id)
                    _append_job_log(
                        store,
                        job.id,
                        f"[server] startup process cleanup kill_info={kill_info} remaining_pids={remaining}",
                    )

            if job.status not in {"running", "cancelling"}:
                continue

            job.status = "failed"
            job.error = job.error or "interrupted (server restarted)"
            finish_job_timing(job, finished_at_utc=job.finished_at_utc or now)
            store.save(job)
            _append_job_log(store, job.id, f"[server] marked as failed on startup at {now} (previous process ended)")
    except Exception:
        return


def _read_proc_cmdline(pid: int) -> str:
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except Exception:
        return ""
    return data.decode("utf-8", errors="ignore").replace("\x00", " ").strip()


def _process_commands_from_ps() -> list[tuple[int, str]]:
    """Return (pid, command line) pairs on hosts without Linux /proc."""
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    processes: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        match = re.match(r"^\s*(\d+)\s+(.*)$", line)
        if not match:
            continue
        try:
            pid = int(match.group(1))
        except ValueError:
            continue
        command = match.group(2).strip()
        if command:
            processes.append((pid, command))
    return processes


def _find_job_pids(job_id: str) -> list[int]:
    """Find PIDs whose /proc/<pid>/cmdline contains the job_id.

    Pragmatic: we embed the job_id into command arguments via /state/jobs/<job_id>/... paths.
    """
    job_id = str(job_id or "").strip()
    if not job_id:
        return []
    self_pid = os.getpid()
    out: list[int] = []
    proc_root = Path("/proc")
    if proc_root.exists():
        for d in proc_root.iterdir():
            if not d.name.isdigit():
                continue
            pid = int(d.name)
            if pid == self_pid:
                continue
            cmdline = _read_proc_cmdline(pid)
            if cmdline and job_id in cmdline:
                out.append(pid)
    else:
        for pid, cmdline in _process_commands_from_ps():
            if pid != self_pid and job_id in cmdline:
                out.append(pid)
    return sorted(set(out))


def _kill_job_processes(job_id: str, *, sig: signal.Signals = signal.SIGTERM) -> dict[str, Any]:
    """Best-effort kill of all process groups related to a job_id."""
    pids = _find_job_pids(job_id)
    sigterm_pids: list[int] = []
    sigkill_pids: list[int] = []
    seen_groups: set[int] = set()

    for pid in pids:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            continue
        except OSError:
            pgid = None

        try:
            if pgid is not None and pgid not in seen_groups and pgid != os.getpgrp():
                os.killpg(pgid, sig)
                seen_groups.add(pgid)
            else:
                os.kill(pid, sig)
            if sig == signal.SIGKILL:
                sigkill_pids.append(pid)
            else:
                sigterm_pids.append(pid)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue

    return {
        "matched_pids": pids,
        "sigterm_pids": sigterm_pids,
        "sigkill_pids": sigkill_pids,
    }


async def _run_job_guarded(app: web.Application, job_id: str, coro, *, semaphore_key: str = "job_semaphore"):
    """Run a job coroutine with concurrency limit + robust failure bookkeeping."""
    store: JobStore = app["store"]
    sem = app.get(semaphore_key) or app["job_semaphore"]
    try:
        async with sem:
            try:
                await coro
            except asyncio.CancelledError:
                job = store.load(job_id)
                if job and job.status not in {"completed", "failed", "cancelled"}:
                    job.status = "cancelled"
                    job.error = job.error or "cancelled"
                    finish_job_timing(job)
                    store.save(job)
                _append_job_log(store, job_id, "[server] job cancelled")
                return
            except Exception as e:
                job = store.load(job_id)
                if job:
                    job.status = "failed"
                    job.error = f"{type(e).__name__}: {e}"
                    finish_job_timing(job)
                    store.save(job)

                _append_job_log(store, job_id, "\n[server] exception:\n" + "".join(traceback.format_exc()) + "\n")
                return
    except asyncio.CancelledError:
        # Cancelled while waiting for a semaphore slot (job was still queued).
        job = store.load(job_id)
        if job and job.status not in {"completed", "failed", "cancelled"}:
            job.status = "cancelled"
            job.error = job.error or "cancelled"
            finish_job_timing(job)
            store.save(job)
        _append_job_log(store, job_id, "[server] job cancelled (queued)")
        return
    finally:
        # Avoid unbounded growth.
        try:
            app["tasks"].pop(job_id, None)
        except Exception:
            pass


async def handle_job_cancel(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)

    if job.status in {"completed", "failed", "cancelled"}:
        return _json_error(f"job already finished (status={job.status})", status=409, status_value=job.status)

    now = utc_now_iso()
    job.cancel_requested_at_utc = now
    if job.status == "queued":
        job.status = "cancelled"
        job.error = "cancelled by user"
        finish_job_timing(job, finished_at_utc=now)
    else:
        # running -> cancelling (final state will be set when cancellation completes)
        job.status = "cancelling"
        job.error = "cancellation requested by user"
    store.save(job)

    _append_job_log(store, job_id, f"[server] cancel requested at {now}")

    # Cancel the asyncio Task (if this server instance owns it).
    task = request.app.get("tasks", {}).get(job_id)
    if task is not None and not task.done():
        try:
            task.cancel()
            _append_job_log(store, job_id, "[server] asyncio task cancelled")
        except Exception:
            pass

    # Kill any subprocesses that carry the job_id in their cmdline.  The
    # subprocess helper also performs this cleanup when its task is cancelled;
    # this scan covers jobs left behind after a server restart and macOS hosts
    # where /proc is unavailable.
    kill_info = _kill_job_processes(job_id, sig=signal.SIGTERM)
    await asyncio.sleep(0.6)
    still = _find_job_pids(job_id)
    if still:
        force_info = _kill_job_processes(job_id, sig=signal.SIGKILL)
        kill_info["sigkill_pids"].extend(force_info["sigkill_pids"])

    remaining = _find_job_pids(job_id)
    _append_job_log(store, job_id, f"[server] cancel kill_info={kill_info} remaining_pids={remaining}")

    # If this server doesn't own a task for this job and no processes remain,
    # finalize cancellation immediately (important for stale `running` jobs after a restart).
    task2 = request.app.get("tasks", {}).get(job_id)
    if (task2 is None or task2.done()) and not remaining:
        job2 = store.load(job_id)
        if job2 and job2.status == "cancelling":
            job2.status = "cancelled"
            job2.error = "cancelled by user"
            finish_job_timing(job2)
            store.save(job2)
            _append_job_log(store, job_id, "[server] cancel finalized (no remaining processes)")

    job3 = store.load(job_id)
    return web.json_response(
        {"job_id": job_id, "status": job3.status if job3 else job.status, "kill_info": kill_info, "remaining_pids": remaining}
    )


async def handle_job_hide(request: web.Request) -> web.Response:
    """Soft-delete a job so it no longer appears in analytics/history views."""
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)
    if job.status in {"running", "queued", "cancelling"}:
        return _json_error(f"job is still active (status={job.status}); cancel it first", status=409, status_value=job.status)
    if getattr(job, "deleted_at_utc", None):
        return web.json_response(job.to_dict())
    job.deleted_at_utc = utc_now_iso()
    store.save(job)
    return web.json_response(job.to_dict())


async def handle_job_restore(request: web.Request) -> web.Response:
    """Restore a previously hidden job."""
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)
    if not getattr(job, "deleted_at_utc", None):
        return web.json_response(job.to_dict())
    job.deleted_at_utc = None
    store.save(job)
    return web.json_response(job.to_dict())


async def _require_finished_job_for_analytics_mutation(job: Job) -> web.Response | None:
    if job.status in {"running", "queued", "cancelling"}:
        return _json_error(f"job is still active (status={job.status}); try again after it completes", status=409, status_value=job.status)
    if job.job_type != "experience_update":
        return _json_error("only experience_update jobs support analytics ignore lists", status=400, job_type=job.job_type)
    payload = job.payload or {}
    if str(payload.get("upload_format") or "").lower() != "csv":
        return _json_error("only csv-backed update jobs support per-row ignore", status=400, upload_format=payload.get("upload_format"))
    return None


async def handle_job_analytics_ignore(request: web.Request) -> web.Response:
    """Ignore specific CSV rows for an update job when computing /api/analytics statistics."""
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)

    bad = await _require_finished_job_for_analytics_mutation(job)
    if bad is not None:
        return bad

    try:
        body = await request.json()
    except Exception:
        body = None

    idxs = parse_ignore_request_body(body)
    if not idxs:
        return _json_error("missing csv_row_index(s)", status=400, expected_keys=["csv_row_index", "csv_row_indices"])

    payload = job.payload or {}
    summary = apply_ignore_csv_rows(payload, add=idxs)
    job.payload = payload
    store.save(job)
    return web.json_response({"job_id": job.id, "job_type": job.job_type, "summary": summary})


async def handle_job_analytics_unignore(request: web.Request) -> web.Response:
    """Restore previously ignored CSV rows for an update job in /api/analytics."""
    store: JobStore = request.app["store"]
    job_id = request.match_info["job_id"]
    job = store.load(job_id)
    if not job:
        return _json_error("job not found", status=404)

    bad = await _require_finished_job_for_analytics_mutation(job)
    if bad is not None:
        return bad

    try:
        body = await request.json()
    except Exception:
        body = None

    idxs = parse_ignore_request_body(body)
    if not idxs:
        return _json_error("missing csv_row_index(s)", status=400, expected_keys=["csv_row_index", "csv_row_indices"])

    payload = job.payload or {}
    summary = apply_ignore_csv_rows(payload, remove=idxs)
    job.payload = payload
    store.save(job)
    return web.json_response({"job_id": job.id, "job_type": job.job_type, "summary": summary})


async def handle_recommend_rank(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    paths: RepoPaths = request.app["paths"]
    python_bin: str = request.app["python_bin"]

    try:
        data = await request.json()
    except Exception:
        return _json_error("invalid JSON body")

    nested_material = data.get("material_input")
    if nested_material is None:
        nested_material = {}
    if not isinstance(nested_material, dict):
        return _json_error("'material_input' must be a JSON object")
    material_fields = (
        "material_name",
        "major_category",
        "components",
        "structure_relationships",
        "precursors",
        "feed_ratio",
        "preparation_method",
        "elements",
        "element_content",
        "conditions",
        "custom_prompt",
    )
    material_input: dict[str, Any] = {}
    for key in material_fields:
        value = data.get(key, nested_material.get(key))
        if value not in (None, "", [], {}):
            material_input[key] = value.strip() if isinstance(value, str) else value
    serial_raw = data.get(
        "material_serial_no",
        data.get("material_no", nested_material.get("material_serial_no", nested_material.get("material_no"))),
    )
    material_serial_no: int | None = None
    if serial_raw not in (None, ""):
        try:
            material_serial_no = _positive_material_serial(serial_raw)
        except ValueError as exc:
            return _json_error(str(exc))
        material_input["material_serial_no"] = material_serial_no
    material_name = str(material_input.get("material_name") or "").strip()
    if not material_name:
        return _json_error("missing required 'material_name'")
    material_input["material_name"] = material_name

    element_source = material_input.get("elements") or material_name
    if isinstance(element_source, list):
        element_source = ",".join(str(item) for item in element_source)
    detected_elements = _extract_unique_elements_from_components(str(element_source))

    def _bounded_int(keys: tuple[str, ...], default: int) -> int:
        raw = next((data[key] for key in keys if key in data), default)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{keys[0]} must be an integer") from exc
        if value < 1 or value > len(TASK_TYPES):
            raise ValueError(f"{keys[0]} must be between 1 and {len(TASK_TYPES)}")
        return value

    try:
        requested_top_k = _bounded_int(("top_k_properties", "top_k_reactions"), 2)
        requested_max_parallel = _bounded_int(
            ("max_parallel_properties", "max_parallel_reactions"),
            1,
        )
    except (TypeError, ValueError) as exc:
        return _json_error(str(exc))

    # Default: save every single-task debate trace so later feedback can be aligned to it.
    save_each = bool(data.get("save_each_task", data.get("save_each_reaction", True)))

    valid_rts = set(TASK_TYPES)
    reaction_types = data.get("task_types")
    if reaction_types is None:
        reaction_types = data.get("task_type")
    if reaction_types is None:
        reaction_types = data.get("property_types")
    if reaction_types is None:
        reaction_types = data.get("reaction_types")
    if reaction_types is not None:
        if isinstance(reaction_types, str):
            reaction_types = [s.strip() for s in reaction_types.split(",") if s.strip()]
        if not isinstance(reaction_types, list):
            return _json_error("'task_types' must be a list or comma-separated string")
        if not reaction_types:
            return _json_error("'task_types' must contain at least one task direction")
        all_tokens = [str(value or "").strip().lower() for value in reaction_types]
        if any(value in {"all", "__all__", "全部", "全部方向"} for value in all_tokens):
            if len(reaction_types) != 1:
                return _json_error("the all-directions selector cannot be combined with individual task types")
            reaction_types = list(TASK_TYPES)
        else:
            reaction_types = [
                _canonical_task_type(x) or str(x).strip().upper()
                for x in reaction_types
                if str(x).strip()
            ]
    else:
        # Default: run all directions as independent single-task debates.
        reaction_types = list(TASK_TYPES)

    # Validate early so we fail fast (instead of spawning a long-running MAD job that errors).
    bad = [rt for rt in reaction_types if rt not in valid_rts]
    if bad:
        return _json_error(f"unknown task types: {bad}; choices={TASK_TYPES}")
    # De-duplicate while keeping order.
    seen: set[str] = set()
    reaction_types = [rt for rt in reaction_types if not (rt in seen or seen.add(rt))]
    if not reaction_types:
        return _json_error("'task_types' must contain at least one task direction")

    direction_count = len(reaction_types)
    selection_mode = "all" if reaction_types == TASK_TYPES else "single" if direction_count == 1 else "subset"
    top_k = min(requested_top_k, direction_count)
    max_parallel = min(requested_max_parallel, direction_count)

    job = store.create(
        "mad_rank",
        payload={
            "material_serial_no": material_serial_no,
            "material_name": material_name,
            "material_input": material_input,
            "custom_prompt": material_input.get("custom_prompt"),
            "components": ", ".join(detected_elements),
            "detected_elements": detected_elements,
            "detected_count": len(detected_elements),
            "top_k_reactions": top_k,
            "top_k_properties": top_k,
            "requested_top_k_properties": requested_top_k,
            "task_types": reaction_types,
            "property_types": reaction_types,
            "reaction_types": reaction_types,
            "max_parallel_reactions": max_parallel,
            "max_parallel_properties": max_parallel,
            "requested_max_parallel_properties": requested_max_parallel,
            "save_each_reaction": save_each,
            "save_each_task": save_each,
            "selection_mode": selection_mode,
            "direction_count": direction_count,
            "debate_scope": "single_task_per_debate",
        },
    )

    async def _coro():
        j = store.load(job.id) or job
        await run_mad_rank_job(
            job=j,
            store=store,
            paths=paths,
            python_bin=python_bin,
            material_input=material_input,
            top_k_properties=top_k,
            task_types=reaction_types,
            max_parallel_properties=max_parallel,
            save_each_task=save_each,
        )

    # Each material is an independent MAD process. Use the recommendation-specific
    # semaphore so a batch of up to ten materials can actually run concurrently,
    # while experience/update jobs remain protected by the general semaphore.
    request.app["tasks"][job.id] = asyncio.create_task(
        _run_job_guarded(request.app, job.id, _coro(), semaphore_key="recommendation_semaphore")
    )

    return web.json_response({"job_id": job.id, "status_url": f"/api/jobs/{job.id}"})


async def handle_recommendations_list(request: web.Request) -> web.Response:
    """List completed recommendation jobs (experimenter-friendly)."""
    store: JobStore = request.app["store"]
    limit = int(request.query.get("limit", "50") or 50)
    limit = max(1, min(500, limit))
    q = str(request.query.get("q", "") or "").strip().lower()
    q_tokens = [t for t in re.split(r"[\s,;]+", q) if t] if q else []
    include_legacy = str(request.query.get("include_legacy", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # We may need to scan more than `limit` because we filter by type/status.
    scan = max(500, limit * 20)
    items: list[dict[str, Any]] = []
    for j in store.list_jobs(limit=scan):
        if j.job_type != "mad_rank":
            continue
        if getattr(j, "deleted_at_utc", None):
            continue
        if j.status != "completed":
            continue
        job_payload = j.payload or {}
        comp = str(job_payload.get("components") or "")
        material_input = job_payload.get("material_input") if isinstance(job_payload.get("material_input"), dict) else {}
        material_name = str(job_payload.get("material_name") or material_input.get("material_name") or "").strip()
        material_serial_no = job_payload.get("material_serial_no", material_input.get("material_serial_no"))
        is_legacy_material_record = not bool(material_name)
        if is_legacy_material_record and not include_legacy:
            continue
        task_types = job_payload.get("task_types") if isinstance(job_payload.get("task_types"), list) else []
        property_types = job_payload.get("property_types") if isinstance(job_payload.get("property_types"), list) else []
        reaction_types = job_payload.get("reaction_types") if isinstance(job_payload.get("reaction_types"), list) else []
        searchable = " ".join(
            [
                str(material_serial_no or ""),
                material_name,
                str(j.id),
                " ".join(str(item) for item in [*task_types, *property_types, *reaction_types]),
                str(job_payload.get("custom_prompt") or ""),
                json.dumps(material_input, ensure_ascii=False, sort_keys=True),
            ]
        ).lower()
        if q_tokens and not all(token in searchable for token in q_tokens):
            continue
        items.append(
            {
                "job_id": j.id,
                "created_at_utc": j.created_at_utc,
                "started_at_utc": j.started_at_utc,
                "finished_at_utc": j.finished_at_utc,
                "duration_seconds": j.to_dict().get("duration_seconds"),
                "components": comp,
                "material_serial_no": material_serial_no,
                "material_name": material_name,
                "material_input": material_input,
                "is_legacy_material_record": is_legacy_material_record,
                "detected_elements": (j.payload or {}).get("detected_elements"),
                "detected_count": (j.payload or {}).get("detected_count"),
                "metals_scope": (j.payload or {}).get("metals_scope"),
                "metals_other": (j.payload or {}).get("metals_other"),
                "top_k_reactions": (j.payload or {}).get("top_k_reactions"),
                "top_k_properties": (j.payload or {}).get("top_k_properties"),
                "max_parallel_properties": (j.payload or {}).get("max_parallel_properties"),
                "task_types": (j.payload or {}).get("task_types"),
                "property_types": (j.payload or {}).get("property_types"),
                "reaction_types": (j.payload or {}).get("reaction_types"),
                "selection_mode": (j.payload or {}).get("selection_mode"),
                "direction_count": (j.payload or {}).get("direction_count"),
                "result_url": f"/api/jobs/{j.id}/result",
            }
        )
        if len(items) >= limit:
            break

    return web.json_response({"items": items})


def _int_from_json(data: dict[str, Any], key: str, default: int, *, lo: int, hi: int) -> int:
    try:
        raw = data.get(key, default)
        val = int(raw)
    except Exception:
        val = int(default)
    return max(int(lo), min(int(hi), val))


async def handle_material_property_experience_run(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    paths: RepoPaths = request.app["paths"]
    python_bin: str = request.app["python_bin"]

    try:
        data = await request.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return _json_error("invalid JSON body")

    mode = str(data.get("mode") or "prepare_only").strip().lower()
    if mode not in {"prepare_only", "prepare", "dataset", "dataset_only", "grpo"}:
        return _json_error("mode must be prepare_only or grpo")
    prepare_only = mode in {"prepare_only", "prepare", "dataset", "dataset_only"}
    mode = "prepare_only" if prepare_only else "grpo"

    run_mode = str(data.get("run_mode") or ("prepare_only" if prepare_only else "fresh")).strip().lower()
    if run_mode not in {"prepare_only", "fresh", "resume"}:
        return _json_error("run_mode must be prepare_only, fresh, or resume")
    if prepare_only:
        run_mode = "prepare_only"

    truncate = _int_from_json(data, "truncate", 11291, lo=1, hi=100_000)
    batch_size = _int_from_json(data, "batch_size", 50, lo=1, hi=500)
    grpo_n = _int_from_json(data, "grpo_n", 3, lo=1, hi=32)
    rollout_concurrency = _int_from_json(data, "rollout_concurrency", 1, lo=1, hi=32)
    epochs = _int_from_json(data, "epochs", 1, lo=1, hi=10)
    exp_name = str(data.get("exp_name") or "").strip() or None
    mad_enable_rag = bool(data.get("mad_enable_rag", True))

    if prepare_only:
        exp_name = None
    elif run_mode == "resume" and not exp_name:
        return _json_error("resume mode requires exp_name so the existing experiment can be found")
    elif not exp_name:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        exp_name = (
            f"material_performance_19_web_{stamp}_t{truncate}_e{epochs}"
            f"_b{batch_size}_n{grpo_n}_c{rollout_concurrency}"
        )

    job = store.create(
        "material_property_experience",
        payload={
            "mode": mode,
            "run_mode": run_mode,
            "exp_name": exp_name,
            "truncate": truncate,
            "batch_size": batch_size,
            "grpo_n": grpo_n,
            "rollout_concurrency": rollout_concurrency,
            "epochs": epochs,
            "mad_enable_rag": mad_enable_rag,
        },
    )

    async def _coro():
        j = store.load(job.id) or job
        await run_material_property_experience_job(
            job=j,
            store=store,
            paths=paths,
            python_bin=python_bin,
            mode=mode,
            exp_name=exp_name,
            truncate=truncate,
            batch_size=batch_size,
            grpo_n=grpo_n,
            rollout_concurrency=rollout_concurrency,
            epochs=epochs,
            mad_enable_rag=mad_enable_rag,
            run_mode=run_mode,
        )

    request.app["tasks"][job.id] = asyncio.create_task(_run_job_guarded(request.app, job.id, _coro()))
    return web.json_response({"job_id": job.id, "status_url": f"/api/jobs/{job.id}"})


async def handle_experience_update(request: web.Request) -> web.Response:
    store: JobStore = request.app["store"]
    paths: RepoPaths = request.app["paths"]
    python_bin: str = request.app["python_bin"]

    # Create job early so we have a stable job_dir to stream uploads into.
    job = store.create("experience_update", payload={})
    job_dir = store.job_dir(job.id)
    upload_path = None
    upload_format = None
    tag = "lab"
    recommendation_job_id: str | None = None
    recommendation_job_ids: list[str] = []
    # Keep the selected 19-direction sweep configuration as the server-authoritative default.
    # The GRPO runner supports a final partial batch, so smaller lab uploads still run.
    fixed_batch_size = int(
        os.environ.get("CHEMCOUNCIL_EXPERIENCE_BATCH_SIZE", str(EXPERIENCE_UPDATE_BATCH_SIZE_DEFAULT))
        or EXPERIENCE_UPDATE_BATCH_SIZE_DEFAULT
    )
    batch_size = fixed_batch_size
    requested_batch_size: int | None = None
    grpo_n = int(
        os.environ.get("CHEMCOUNCIL_EXPERIENCE_GRPO_N", str(EXPERIENCE_UPDATE_GRPO_N_DEFAULT))
        or EXPERIENCE_UPDATE_GRPO_N_DEFAULT
    )
    rollout_concurrency = int(
        os.environ.get(
            "CHEMCOUNCIL_EXPERIENCE_ROLLOUT_CONCURRENCY",
            str(EXPERIENCE_UPDATE_ROLLOUT_CONCURRENCY_DEFAULT),
        )
        or EXPERIENCE_UPDATE_ROLLOUT_CONCURRENCY_DEFAULT
    )
    epochs = int(
        os.environ.get("CHEMCOUNCIL_EXPERIENCE_EPOCHS", str(EXPERIENCE_UPDATE_EPOCHS_DEFAULT))
        or EXPERIENCE_UPDATE_EPOCHS_DEFAULT
    )

    try:
        reader = await request.multipart()
        async for part in reader:
            if not part.name:
                continue
            if part.name == "file":
                filename = (part.filename or "").strip() or "upload"
                ext = Path(filename).suffix.lower()
                if ext == ".xlsx":
                    upload_format = "xlsx"
                elif ext == ".csv":
                    upload_format = "csv"
                else:
                    # Allow explicit format field to override.
                    upload_format = None

                upload_path = job_dir / f"upload{ext or ''}"
                with upload_path.open("wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                text = (await part.text()).strip()
                if part.name == "format" and text:
                    upload_format = text.lower()
                elif part.name == "tag" and text:
                    tag = text
                elif part.name == "batch_size" and text:
                    requested_batch_size = int(text)
                elif part.name == "grpo_n" and text:
                    grpo_n = int(text)
                elif part.name == "rollout_concurrency" and text:
                    rollout_concurrency = int(text)
                elif part.name == "epochs" and text:
                    epochs = int(text)
                elif part.name == "recommendation_job_id" and text:
                    recommendation_job_id = text
    except Exception as e:
        job.status = "failed"
        job.error = f"upload parse failed: {type(e).__name__}: {e}"
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return _json_error("failed to parse upload", status=400, job_id=job.id)

    if upload_path is None or not upload_path.exists():
        job.status = "failed"
        job.error = "missing multipart field 'file'"
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return _json_error("missing multipart field 'file'", status=400, job_id=job.id)
    if upload_format not in {"csv", "xlsx"}:
        job.status = "failed"
        job.error = f"unsupported upload_format={upload_format!r}"
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return _json_error(
            "unsupported file type; upload .csv or .xlsx (or set format=csv|xlsx)",
            status=400,
            job_id=job.id,
        )

    if requested_batch_size is not None and int(requested_batch_size) != int(fixed_batch_size):
        job.status = "failed"
        job.error = f"batch_size is fixed to {fixed_batch_size} in this deployment"
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return _json_error(
            f"batch_size is currently fixed to {fixed_batch_size} (do not pass batch_size).",
            status=400,
            job_id=job.id,
            fixed_batch_size=fixed_batch_size,
        )

    # Best-effort: collect per-row recommendation_job_id values from the uploaded CSV.
    # This enables correct analytics when a single update includes multiple recommendation sources.
    if upload_format == "csv" and upload_path is not None and upload_path.exists():
        try:
            recommendation_job_ids = collect_recommendation_job_ids_from_csv(upload_path)
        except Exception:
            recommendation_job_ids = []

    # If the client sent a single recommendation_job_id (legacy flow), keep it too.
    if recommendation_job_id and recommendation_job_id not in recommendation_job_ids:
        if not recommendation_job_ids:
            recommendation_job_ids = [recommendation_job_id]

    # If the CSV only references one reco job, promote it to the single field for backward compat.
    if not recommendation_job_id and len(recommendation_job_ids) == 1:
        recommendation_job_id = recommendation_job_ids[0]

    # Save payload snapshot.
    job = store.load(job.id) or job
    job.payload = {
        "upload_path": str(upload_path),
        "upload_format": upload_format,
        "tag": tag,
        "recommendation_job_id": recommendation_job_id,
        "recommendation_job_ids": recommendation_job_ids,
        "batch_size": batch_size,
        "grpo_n": grpo_n,
        "rollout_concurrency": rollout_concurrency,
        "epochs": epochs,
    }
    store.save(job)

    async def _coro():
        j = store.load(job.id) or job
        await run_experience_update_job(
            job=j,
            store=store,
            paths=paths,
            python_bin=python_bin,
            upload_path=upload_path,
            upload_format=upload_format,
            tag=tag,
            batch_size=batch_size,
            grpo_n=grpo_n,
            rollout_concurrency=rollout_concurrency,
            epochs=epochs,
        )

    request.app["tasks"][job.id] = asyncio.create_task(_run_job_guarded(request.app, job.id, _coro()))
    return web.json_response({"job_id": job.id, "status_url": f"/api/jobs/{job.id}"})


async def handle_experience_meta(request: web.Request) -> web.Response:
    paths: RepoPaths = request.app["paths"]
    exp_path = _experience_pack_path(paths)
    if not exp_path.exists():
        return _json_error("experience.yaml not found", status=404)
    try:
        raw = exp_path.read_text(encoding="utf-8")
    except Exception:
        raw = exp_path.read_text(encoding="utf-8", errors="replace")

    updated_at = None
    source_agent = None
    for line in raw.splitlines():
        if line.startswith("updated_at_utc:"):
            updated_at = line.split(":", 1)[1].strip().strip("'").strip('"')
        if line.startswith("source_agent_yaml:"):
            source_agent = line.split(":", 1)[1].strip()
    return web.json_response(
        {
            "updated_at_utc": updated_at,
            "source_agent_yaml": source_agent,
            "path": str(exp_path),
        }
    )


async def handle_experience_pack(request: web.Request) -> web.Response:
    paths: RepoPaths = request.app["paths"]
    exp_path = _experience_pack_path(paths)
    if not exp_path.exists():
        return _json_error("experience.yaml not found", status=404)
    return web.FileResponse(exp_path)


def _parse_experience_pack_meta(raw_yaml: str) -> tuple[str | None, str | None]:
    """Best-effort extraction without requiring a YAML parser (keep endpoint lightweight)."""
    updated_at = None
    source_agent = None
    for line in (raw_yaml or "").splitlines():
        if line.startswith("updated_at_utc:"):
            updated_at = line.split(":", 1)[1].strip().strip("'").strip('"') or None
        elif line.startswith("source_agent_yaml:"):
            source_agent = line.split(":", 1)[1].strip().strip("'").strip('"') or None
    return updated_at, source_agent


async def handle_experience_history(request: web.Request) -> web.Response:
    paths: RepoPaths = request.app["paths"]
    archive_root = paths.mad / "experience" / "archive"
    if not archive_root.exists():
        return web.json_response({"items": []})

    items: list[dict[str, Any]] = []
    for d in sorted(archive_root.iterdir(), key=lambda p: p.name, reverse=True):
        if not d.is_dir():
            continue
        yaml_path = d / "experience.yaml"
        if not yaml_path.exists():
            continue
        try:
            raw = yaml_path.read_text(encoding="utf-8")
        except Exception:
            raw = yaml_path.read_text(encoding="utf-8", errors="replace")
        updated_at, source_agent = _parse_experience_pack_meta(raw)
        st = yaml_path.stat()
        items.append(
            {
                "id": d.name,
                "updated_at_utc": updated_at,
                "source_agent_yaml": source_agent,
                "size_bytes": int(st.st_size),
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
                "download_url": f"/api/experience/history/{d.name}/pack",
            }
        )

    return web.json_response({"items": items})


async def handle_experience_history_pack(request: web.Request) -> web.Response:
    paths: RepoPaths = request.app["paths"]
    archive_id = str(request.match_info.get("archive_id") or "").strip()
    if not archive_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", archive_id):
        return _json_error("invalid archive_id", status=400)

    archive_root = paths.mad / "experience" / "archive"
    if not archive_root.exists():
        return _json_error("experience archive not found", status=404)

    # Prevent path traversal: resolve and ensure it's under archive_root.
    root_resolved = archive_root.resolve()
    yaml_path = (archive_root / archive_id / "experience.yaml").resolve()
    if root_resolved not in yaml_path.parents:
        return _json_error("invalid archive path", status=400)
    if not yaml_path.exists():
        return _json_error("archive pack not found", status=404)
    return web.FileResponse(yaml_path)


async def handle_experience_activate(request: web.Request) -> web.Response:
    """Activate a historical experience pack (rollback current pack)."""
    paths: RepoPaths = request.app["paths"]
    archive_id = str(request.match_info.get("archive_id") or "").strip()
    if not archive_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", archive_id):
        return _json_error("invalid archive_id", status=400)

    archive_root = paths.mad / "experience" / "archive"
    if not archive_root.exists():
        return _json_error("experience archive not found", status=404)

    src_path = (archive_root / archive_id / "experience.yaml").resolve()
    if not src_path.exists():
        return _json_error("archive pack not found", status=404)

    # Read source YAML.
    try:
        src_text = src_path.read_text(encoding="utf-8")
    except Exception:
        src_text = src_path.read_text(encoding="utf-8", errors="replace")

    # Backup current pack into archive before overwriting (so we can undo an activation).
    cur_path = _experience_pack_path(paths)
    cur_text = ""
    if cur_path.exists():
        try:
            cur_text = cur_path.read_text(encoding="utf-8")
        except Exception:
            cur_text = cur_path.read_text(encoding="utf-8", errors="replace")

    backup_id = None
    if cur_text and cur_text != src_text:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = f"rollback_{ts}_before_{archive_id}"
        # Avoid collisions (rare, but possible in fast repeated clicks).
        for k in range(30):
            cand = base if k == 0 else f"{base}_{k}"
            out_dir = archive_root / cand
            try:
                out_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                continue
            (out_dir / "experience.yaml").write_text(cur_text, encoding="utf-8")
            backup_id = cand
            break

    # Write into the active packs:
    # - youtu stable pack: whatever the UI is currently configured to read (usually /state/experience_youtu.yaml)
    # - MAD stable pack: MAD/experience/experience.yaml (symlinked to /state in Docker)
    _atomic_write_text_file(cur_path, src_text)
    _atomic_write_text_file(paths.mad / "experience" / "experience.yaml", src_text)

    updated_at, source_agent = _parse_experience_pack_meta(src_text)
    return web.json_response(
        {
            "activated_archive_id": archive_id,
            "backup_archive_id": backup_id,
            "updated_at_utc": updated_at,
            "source_agent_yaml": source_agent,
            "path": str(cur_path),
        }
    )


async def handle_analytics(request: web.Request) -> web.Response:
    """Compute prediction-vs-experiment error statistics from feedback-linked jobs."""
    store: JobStore = request.app["store"]
    limit_rounds = int(request.query.get("limit_rounds", "50") or 50)
    limit_rounds = max(1, min(500, limit_rounds))
    limit_records = int(request.query.get("limit_records", "1000") or 1000)
    limit_records = max(1, min(20_000, limit_records))

    # Scan all jobs on disk (analytics is not a hot path; keep logic simple and robust).
    update_jobs: list[Job] = []
    for d in sorted(store.root.glob("*"), key=lambda p: p.stat().st_mtime, reverse=False):
        if not d.is_dir():
            continue
        j = store.load(d.name)
        if not j:
            continue
        if j.job_type != "experience_update":
            continue
        if getattr(j, "deleted_at_utc", None):
            continue
        if j.status != "completed":
            continue
        if str((j.payload or {}).get("upload_format") or "").lower() != "csv":
            continue
        update_jobs.append(j)

    # Keep the last N rounds only (older rounds can be downloaded from /state/jobs).
    if len(update_jobs) > limit_rounds:
        update_jobs = update_jobs[-limit_rounds:]

    records_out: list[dict[str, Any]] = []
    rounds_out: list[dict[str, Any]] = []

    for uj in update_jobs:
        payload = uj.payload or {}
        upload_path = str(payload.get("upload_path") or "").strip()
        if not upload_path:
            continue

        default_rec_job_id = str(payload.get("recommendation_job_id") or "").strip() or None

        csv_path = Path(upload_path)
        if not csv_path.exists():
            continue

        # Determine which recommendation jobs to use for this update:
        # 1) per-job cached list in payload (if present),
        # 2) scan the upload CSV for a per-row recommendation_job_id column,
        # 3) fallback to the legacy single recommendation_job_id field.
        rec_job_ids: list[str] = []
        raw_ids = payload.get("recommendation_job_ids")
        if isinstance(raw_ids, list):
            rec_job_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        if not rec_job_ids:
            try:
                rec_job_ids = collect_recommendation_job_ids_from_csv(csv_path)
            except Exception:
                rec_job_ids = []
        if default_rec_job_id and default_rec_job_id not in rec_job_ids:
            if not rec_job_ids:
                rec_job_ids = [default_rec_job_id]

        if not rec_job_ids:
            continue

        rec_ctx: dict[str, RecommendationContext] = {}
        for rec_job_id in rec_job_ids:
            reco_job = store.load(rec_job_id)
            if not reco_job or reco_job.status != "completed":
                continue
            reco_result_path = Path(reco_job.result_path) if reco_job.result_path else store.job_result_path(rec_job_id)
            if not reco_result_path.exists():
                continue
            try:
                reco_result = json.loads(reco_result_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            rec_ctx[rec_job_id] = RecommendationContext(
                recommendation_job_id=rec_job_id,
                recommendation_finished_at_utc=reco_job.finished_at_utc,
                components=str((reco_job.payload or {}).get("components") or ""),
                recommendation_rank_result=reco_result,
            )
        if not rec_ctx:
            continue

        try:
            recs_raw, debug = compute_prediction_error_records_multi_debug(
                update_job_id=uj.id,
                update_finished_at_utc=uj.finished_at_utc,
                upload_csv_path=csv_path,
                recommendation_contexts=rec_ctx,
                default_recommendation_job_id=default_rec_job_id,
            )
        except Exception:
            continue
        recs = aggregate_prediction_error_records_for_analytics(recs_raw)

        ignored_rows = read_ignore_csv_rows(payload)
        included_recs = [r for r in recs if r.csv_row_index not in ignored_rows]

        # For display, keep a single "components" string if all referenced reco jobs share it,
        # otherwise mark as mixed.
        comp_set = {str(c.components or "").strip() for c in rec_ctx.values() if str(c.components or "").strip()}
        if len(comp_set) == 1:
            components_display = next(iter(comp_set))
        else:
            components_display = f"mixed({len(rec_ctx)})"

        rec_ids_display = [rid for rid in rec_job_ids if rid in rec_ctx]
        primary_rec_job_id = rec_ids_display[0] if len(rec_ids_display) == 1 else None
        primary_reco_job = store.load(primary_rec_job_id) if primary_rec_job_id else None

        # Round summary (mean over all evaluable rows in this upload).
        scores = [r.score for r in included_recs]
        rels = [r.rel_error for r in included_recs]
        round_index = len(rounds_out) + 1
        rounds_out.append(
            {
                "round_index": round_index,
                "update_job_id": uj.id,
                "update_finished_at_utc": uj.finished_at_utc,
                "recommendation_job_id": primary_rec_job_id,
                "recommendation_job_ids": rec_ids_display,
                "recommendation_finished_at_utc": primary_reco_job.finished_at_utc if primary_reco_job else None,
                "components": components_display,
                "num_records": len(included_recs),
                "num_records_total": len(recs),
                "num_records_ignored": max(0, len(recs) - len(included_recs)),
                "mean_score": mean(scores),
                "mean_rel_error": mean(rels),
                "debug": {
                    **debug.__dict__,
                    "rows_scored_raw": debug.rows_scored,
                    "rows_scored": len(recs),
                    "rows_scored_analytics": len(recs),
                    "co2rr_rows_combined": max(0, debug.rows_scored - len(recs)),
                },
            }
        )

        for r in recs:
            if len(records_out) >= limit_records:
                break
            d = r.__dict__.copy()
            d["round_index"] = round_index
            d["ignored"] = bool(r.csv_row_index in ignored_rows)
            records_out.append(d)
        if len(records_out) >= limit_records:
            break

    overall = {
        "total_rounds": len(rounds_out),
        "total_records": len([r for r in records_out if not r.get("ignored")]),
        "total_records_total": len(records_out),
        "total_records_ignored": len([r for r in records_out if r.get("ignored")]),
        "mean_score": mean([r.get("score") for r in records_out if (r.get("score") is not None and not r.get("ignored"))]),
        "mean_rel_error": mean([r.get("rel_error") for r in records_out if (r.get("rel_error") is not None and not r.get("ignored"))]),
    }

    return web.json_response({"overall": overall, "rounds": rounds_out, "records": records_out})


def build_app(*, jobs_root: Path, job_concurrency: int, recommendation_concurrency: int | None = None) -> web.Application:
    root = _repo_root()
    paths = RepoPaths.from_root(root)

    store = JobStore(jobs_root)
    python_bin = discover_python_bin(root)

    static_dir = _static_dir()
    if not static_dir.exists():
        raise RuntimeError(f"Static UI directory not found: {static_dir}")

    app = web.Application(
        middlewares=[cors_middleware, auth_middleware],
        client_max_size=int(os.environ.get("CHEMCOUNCIL_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
    )
    app["paths"] = paths
    app["store"] = store
    app["python_bin"] = python_bin
    app["job_semaphore"] = asyncio.Semaphore(max(1, int(job_concurrency)))
    # Recommendation batches are capped at ten material cards in the UI. Keep a
    # separate cap so rank jobs can run in parallel without making uploads or
    # experience updates concurrent by accident.
    if recommendation_concurrency is None:
        recommendation_concurrency = int(os.environ.get("CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY", "10"))
    app["recommendation_semaphore"] = asyncio.Semaphore(max(1, int(recommendation_concurrency)))
    app["tasks"] = {}
    app.on_startup.append(_reconcile_jobs_on_startup)

    # Static UI
    app.router.add_get("/", handle_index)
    app.router.add_static("/static", static_dir, show_index=False)

    # API
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/jobs", handle_jobs_list)
    app.router.add_get("/api/jobs/{job_id}", handle_job_get)
    app.router.add_get("/api/jobs/{job_id}/log", handle_job_log)
    app.router.add_get("/api/jobs/{job_id}/result", handle_job_result)
    app.router.add_get("/api/jobs/{job_id}/mad_traces", handle_job_mad_traces_list)
    app.router.add_get("/api/jobs/{job_id}/mad_traces/{reaction_type}", handle_job_mad_trace_get)
    app.router.add_post("/api/jobs/{job_id}/cancel", handle_job_cancel)
    app.router.add_post("/api/jobs/{job_id}/hide", handle_job_hide)
    app.router.add_post("/api/jobs/{job_id}/restore", handle_job_restore)
    app.router.add_post("/api/jobs/{job_id}/analytics_ignore", handle_job_analytics_ignore)
    app.router.add_post("/api/jobs/{job_id}/analytics_unignore", handle_job_analytics_unignore)

    app.router.add_post("/api/recommendations/rank", handle_recommend_rank)
    app.router.add_get("/api/recommendations", handle_recommendations_list)
    app.router.add_post("/api/experience/material-property/run", handle_material_property_experience_run)
    app.router.add_post("/api/experience/update", handle_experience_update)
    app.router.add_get("/api/experience/meta", handle_experience_meta)
    app.router.add_get("/api/experience/pack", handle_experience_pack)
    app.router.add_get("/api/experience/history", handle_experience_history)
    app.router.add_get("/api/experience/history/{archive_id}/pack", handle_experience_history_pack)
    app.router.add_post("/api/experience/activate/{archive_id}", handle_experience_activate)
    app.router.add_get("/api/analytics", handle_analytics)

    return app


def main() -> None:
    # Load the repo-level .env before argparse so values such as
    # CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY are honored when the server is
    # started directly (Docker Compose injects them before process start too).
    env_path = _repo_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    ap = argparse.ArgumentParser(description="ChemCouncil web server (backend + static UI).")
    ap.add_argument("--host", default=os.environ.get("CHEMCOUNCIL_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("CHEMCOUNCIL_PORT", "8000")))
    ap.add_argument(
        "--jobs_root",
        default=os.environ.get("CHEMCOUNCIL_JOBS_ROOT", str(_repo_root() / ".local" / "chemcouncil_server" / "jobs")),
        help="Directory to store job state/logs/uploads (default: .local/chemcouncil_server/jobs).",
    )
    ap.add_argument(
        "--job_concurrency",
        type=int,
        default=int(os.environ.get("CHEMCOUNCIL_JOB_CONCURRENCY", "1")),
        help="Max number of running jobs at once (default: 1).",
    )
    ap.add_argument(
        "--recommendation_concurrency",
        type=int,
        default=int(os.environ.get("CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY", "10")),
        help="Max number of material recommendation jobs at once (default: 10; lower if RAM/API limits require).",
    )
    args = ap.parse_args()

    app = build_app(
        jobs_root=Path(args.jobs_root),
        job_concurrency=int(args.job_concurrency),
        recommendation_concurrency=int(args.recommendation_concurrency),
    )
    web.run_app(app, host=str(args.host), port=int(args.port))


if __name__ == "__main__":
    main()
