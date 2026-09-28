from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .analytics import RecommendationContext, collect_recommendation_job_ids_from_csv
from .feedback_distillation import build_feedback_distill_examples
from .jobs import Job, JobStore, finish_job_timing, run_subprocess_to_log, safe_env_for_subprocess, utc_now_iso


@dataclass(frozen=True)
class RepoPaths:
    root: Path
    youtu: Path
    mad: Path

    @classmethod
    def from_root(cls, root: Path) -> "RepoPaths":
        root = Path(root).resolve()
        return cls(root=root, youtu=root / "youtu-chem-loop", mad=root / "MAD")


def discover_python_bin(repo_root: Path) -> str:
    """Prefer repo venv python if present; else fall back to current interpreter."""
    venv_py = Path(repo_root).resolve() / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _short_id(job_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "", job_id or "")
    return (s[:8] or "job").lower()


def _append_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as f:
        f.write(text.encode("utf-8", errors="replace"))
        if not text.endswith("\n"):
            f.write(b"\n")


def _quote_cmd(cmd: list[str]) -> str:
    # Best-effort, avoid shell injection concerns (we never exec via shell).
    out = []
    for a in cmd:
        if re.fullmatch(r"[A-Za-z0-9_./:=+-]+", a or ""):
            out.append(a)
        else:
            out.append(json.dumps(a))
    return " ".join(out)


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return raw


def _dump_yaml(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False), encoding="utf-8")


def active_experience_pack_path(paths: RepoPaths) -> Path:
    """Return the currently active stable experience pack path."""
    override = str(os.environ.get("CHEMCOUNCIL_EXPERIENCE_PACK_PATH") or "").strip()
    if override:
        p_override = Path(override)
        if not p_override.is_absolute():
            p_override = (paths.root / p_override).resolve()
        return p_override
    p_state = Path("/state/experience_youtu.yaml")
    if p_state.exists():
        return p_state
    return paths.youtu / "configs" / "agents" / "practice" / "experience.yaml"


def _recommendation_job_ids_from_update_job(job: Job) -> list[str]:
    payload = job.payload or {}
    out: list[str] = []
    seen: set[str] = set()

    raw_ids = payload.get("recommendation_job_ids")
    if isinstance(raw_ids, list):
        for item in raw_ids:
            rid = str(item or "").strip()
            if rid and rid not in seen:
                seen.add(rid)
                out.append(rid)

    single = str(payload.get("recommendation_job_id") or "").strip()
    if single and single not in seen:
        out.append(single)
    return out


def _linked_recommendation_trace_paths(*, job: Job, store: JobStore) -> tuple[list[str], list[Path]]:
    """Collect saved `result_*.json` debate traces from linked recommendation jobs."""
    reco_job_ids = _recommendation_job_ids_from_update_job(job)
    used_job_ids: list[str] = []
    trace_paths: list[Path] = []
    seen_paths: set[Path] = set()

    for reco_job_id in reco_job_ids:
        reco_job = store.load(reco_job_id)
        if reco_job is None or reco_job.job_type != "mad_rank":
            continue
        mad_outputs_dir = store.job_dir(reco_job_id) / "artifacts" / "mad_outputs"
        result_files = sorted(mad_outputs_dir.glob("result_*.json"))
        if not result_files:
            continue
        used_job_ids.append(reco_job_id)
        for path in result_files:
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            trace_paths.append(resolved)

    return used_job_ids, trace_paths


def write_mad_job_config(*, base_config: Path, out_config: Path, outputs_dir: Path, logs_dir: Path) -> None:
    cfg = _load_yaml(base_config)
    cfg.setdefault("paths", {})
    cfg["paths"]["outputs"] = str(outputs_dir)

    cfg.setdefault("logging", {})
    cfg["logging"]["log_file"] = str(logs_dir / "system.log")
    cfg["logging"]["run_dir"] = str(logs_dir / "runs")

    _dump_yaml(out_config, cfg)


async def run_mad_rank_job(
    *,
    job: Job,
    store: JobStore,
    paths: RepoPaths,
    python_bin: str,
    material_input: dict[str, Any],
    top_k_properties: int = 2,
    task_types: list[str] | None = None,
    max_parallel_properties: int = 3,
    save_each_task: bool = False,
) -> None:
    job_dir = store.job_dir(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)

    log_path = store.job_log_path(job.id)
    artifacts = job_dir / "artifacts"
    mad_outputs = artifacts / "mad_outputs"
    mad_logs = artifacts / "mad_logs"
    mad_outputs.mkdir(parents=True, exist_ok=True)
    mad_logs.mkdir(parents=True, exist_ok=True)

    base_cfg = paths.mad / "config" / "config.yaml"
    cfg_path = artifacts / "mad_config.yaml"
    write_mad_job_config(base_config=base_cfg, out_config=cfg_path, outputs_dir=mad_outputs, logs_dir=mad_logs)
    material_input_path = artifacts / "material_input.json"
    material_input_path.write_text(
        json.dumps(material_input, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    cmd = [
        python_bin,
        "main.py",
        "--config",
        str(cfg_path),
        "--material-input-file",
        str(material_input_path),
        "--rank-tasks",
        "--top-k-properties",
        str(int(top_k_properties)),
        "--max-parallel-properties",
        str(int(max_parallel_properties)),
    ]
    if task_types:
        cmd += ["--task-types", ",".join([str(x).strip() for x in task_types if str(x).strip()])]
    if save_each_task:
        cmd.append("--save-each-task")

    job.status = "running"
    job.started_at_utc = utc_now_iso()
    job.command = cmd
    job.cwd = str(paths.mad)
    job.log_path = str(log_path)
    store.save(job)

    _append_log(log_path, f"[job] type={job.job_type} id={job.id}")
    _append_log(log_path, f"[job] started_at_utc={job.started_at_utc}")
    _append_log(log_path, f"[cmd] cwd={paths.mad}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd) }")

    env = safe_env_for_subprocess()
    rc = await run_subprocess_to_log(cmd=cmd, cwd=paths.mad, env=env, log_path=log_path)
    job.returncode = int(rc)

    if rc != 0:
        job.status = "failed"
        job.error = f"MAD task ranking failed (returncode={rc}). See job.log."
        finish_job_timing(job)
        store.save(job)
        return

    # Find the rank JSON in our per-job outputs directory.
    rank_files = sorted(mad_outputs.glob("rank_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not rank_files:
        job.status = "failed"
        job.error = "MAD finished but no rank_*.json was produced."
        finish_job_timing(job)
        store.save(job)
        return

    # Copy the newest rank file into result.json for stable API access, including
    # backend-authoritative wall-clock timing that survives browser refreshes.
    result_path = store.job_result_path(job.id)
    payload = json.loads(rank_files[0].read_text(encoding="utf-8"))

    job.status = "completed"
    if isinstance(payload, dict):
        job.payload["material_description"] = payload.get("material_description")
        job.payload["selection_mode"] = payload.get("selection_mode", job.payload.get("selection_mode"))
        job.payload["direction_count"] = payload.get("direction_count", job.payload.get("direction_count"))
    job.result_path = str(result_path)
    finish_job_timing(job)
    if isinstance(payload, dict):
        payload["recommendation_timing"] = {
            "started_at_utc": job.started_at_utc,
            "finished_at_utc": job.finished_at_utc,
            "duration_seconds": job.duration_seconds,
        }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _append_log(log_path, f"[job] finished_at_utc={job.finished_at_utc}")
    _append_log(log_path, f"[job] duration_seconds={job.duration_seconds}")
    store.save(job)


async def run_material_property_experience_job(
    *,
    job: Job,
    store: JobStore,
    paths: RepoPaths,
    python_bin: str,
    mode: str,
    exp_name: str | None = None,
    truncate: int = 11291,
    batch_size: int = 50,
    grpo_n: int = 3,
    rollout_concurrency: int = 1,
    epochs: int = 1,
    mad_enable_rag: bool = True,
    run_mode: str = "fresh",
) -> None:
    """Run the audited 19-direction dataset -> GRPO experience pipeline as a Web job."""
    job_dir = store.job_dir(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = store.job_log_path(job.id)

    script = paths.root / "scripts" / "run_material_property_experience.sh"
    if not script.exists():
        job.status = "failed"
        job.error = f"material-property experience script not found: {script}"
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    mode = str(mode or "prepare_only").strip().lower()
    run_mode = str(run_mode or "fresh").strip().lower()
    prepare_only = mode in {"prepare", "prepare_only", "dataset", "dataset_only"}

    cmd = [str(script)]
    if prepare_only:
        cmd.append("--prepare-only")
    elif run_mode == "resume":
        cmd.append("--resume")
    else:
        cmd.append("--fresh")

    if exp_name and not prepare_only:
        cmd += ["--exp_name", str(exp_name)]

    env = safe_env_for_subprocess()
    env.update(
        {
            "PYTHON_BIN": str(python_bin),
            "EPOCHS": str(int(epochs)),
            "BATCH_SIZE": str(int(batch_size)),
            "GRPO_N": str(int(grpo_n)),
            "TRUNCATE": str(int(truncate)),
            "ROLLOUT_CONCURRENCY": str(int(rollout_concurrency)),
            "MAD_ENABLE_RAG": "1" if mad_enable_rag else "0",
            "REBUILD_DATASET": "1",
        }
    )

    job.status = "running"
    job.started_at_utc = utc_now_iso()
    job.command = cmd
    job.cwd = str(paths.root)
    job.log_path = str(log_path)
    store.save(job)

    _append_log(log_path, f"[job] type={job.job_type} id={job.id}")
    _append_log(log_path, f"[job] started_at_utc={job.started_at_utc}")
    _append_log(log_path, f"[cmd] cwd={paths.root}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd) }")
    _append_log(
        log_path,
        (
            "[env] "
            f"mode={mode} run_mode={run_mode} exp_name={exp_name or ''} "
            f"truncate={int(truncate)} batch_size={int(batch_size)} grpo_n={int(grpo_n)} "
            f"rollout_concurrency={int(rollout_concurrency)} mad_enable_rag={1 if mad_enable_rag else 0}"
        ),
    )

    rc = await run_subprocess_to_log(cmd=cmd, cwd=paths.root, env=env, log_path=log_path)
    job.returncode = int(rc)
    if rc != 0:
        job.status = "failed"
        job.error = f"material-property experience pipeline failed (returncode={rc}). See job.log."
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    dataset_name = "material_performance_19_v1"
    dataset_jsonl = (
        paths.youtu
        / "data"
        / "processed"
        / "material_performance_19"
        / "material_performance_19_grpo_v1.jsonl"
    )
    dataset_rows = 0
    if dataset_jsonl.exists():
        try:
            with dataset_jsonl.open("r", encoding="utf-8") as f:
                dataset_rows = sum(1 for line in f if line.strip())
        except Exception:
            dataset_rows = 0

    active_pack_after = active_experience_pack_path(paths)
    updated_at = None
    source_agent = None
    if active_pack_after.exists():
        try:
            exp_pack = yaml.safe_load(active_pack_after.read_text(encoding="utf-8"))
            if isinstance(exp_pack, dict):
                updated_at = exp_pack.get("updated_at_utc")
                source_agent = exp_pack.get("source_agent_yaml")
        except Exception:
            pass

    result = {
        "mode": mode,
        "run_mode": run_mode,
        "exp_name": exp_name,
        "dataset_name": dataset_name,
        "dataset_jsonl": str(dataset_jsonl),
        "dataset_rows": dataset_rows,
        "mad_enable_rag": bool(mad_enable_rag),
        "truncate": int(truncate),
        "batch_size": int(batch_size),
        "grpo_n": int(grpo_n),
        "rollout_concurrency": int(rollout_concurrency),
        "epochs": int(epochs),
        "experience_yaml": str(paths.youtu / "configs" / "agents" / "practice" / "experience.yaml"),
        "active_experience_yaml": str(active_pack_after),
        "updated_at_utc": updated_at,
        "source_agent_yaml": source_agent,
    }
    result_path = store.job_result_path(job.id)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    job.status = "completed"
    job.result_path = str(result_path)
    job.finished_at_utc = utc_now_iso()
    store.save(job)


async def run_experience_update_job(
    *,
    job: Job,
    store: JobStore,
    paths: RepoPaths,
    python_bin: str,
    upload_path: Path,
    upload_format: str,
    tag: str,
    batch_size: int = 19,
    grpo_n: int = 3,
    rollout_concurrency: int = 4,
    epochs: int = 1,
) -> None:
    job_dir = store.job_dir(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = store.job_log_path(job.id)

    job.status = "running"
    job.started_at_utc = utc_now_iso()
    job.log_path = str(log_path)
    store.save(job)

    tag = re.sub(r"[^A-Za-z0-9_]+", "_", str(tag or "lab")).strip("_") or "lab"
    # Add a short id suffix to avoid dataset name collisions across repeated uploads.
    tag = f"{tag}_{_short_id(job.id)}"

    # We use local date (server timezone) for naming, matching the existing CLI scripts.
    date = datetime.now().strftime("%Y%m%d")
    dataset_name = f"chem_performance_exp_{date}_{tag}"

    artifacts = job_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    processed_dir = artifacts / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    active_seed_pack = active_experience_pack_path(paths)

    # 1) Create an experimental-record CSV if upload is XLSX.
    if upload_format.lower() == "xlsx":
        _append_log(log_path, "[1/7] XLSX -> experimental_records CSV (long table)")
        cmd_xlsx = [
            python_bin,
            "-m",
            "scripts.data.import_experimental_xlsx",
            "--xlsx_path",
            str(upload_path),
            "--date",
            date,
            "--tag",
            tag,
            "--output_dir",
            str(artifacts),
            "--quiet",
        ]
        _append_log(log_path, f"[cmd] cwd={paths.youtu}")
        _append_log(log_path, f"[cmd] { _quote_cmd(cmd_xlsx) }")
        env = safe_env_for_subprocess()
        rc = await run_subprocess_to_log(cmd=cmd_xlsx, cwd=paths.youtu, env=env, log_path=log_path)
        if rc != 0:
            job.status = "failed"
            job.error = f"import_experimental_xlsx failed (returncode={rc})."
            job.returncode = int(rc)
            job.finished_at_utc = utc_now_iso()
            store.save(job)
            return

        # Parse the converter output which was appended to the log.
        # It prints machine-parsable lines:
        #   DATASET_NAME=...
        #   OUTPUT_CSV=...
        #   RECORDS=...
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        m_ds = re.findall(r"^DATASET_NAME=(.+)$", log_text, flags=re.MULTILINE)
        m_csv = re.findall(r"^OUTPUT_CSV=(.+)$", log_text, flags=re.MULTILINE)
        ds_from_xlsx = m_ds[-1].strip() if m_ds else ""
        csv_path = Path(m_csv[-1].strip()).expanduser().resolve() if m_csv else None
        if not ds_from_xlsx or not csv_path or not csv_path.exists():
            job.status = "failed"
            job.error = "Failed to parse DATASET_NAME/OUTPUT_CSV from import_experimental_xlsx output."
            job.finished_at_utc = utc_now_iso()
            store.save(job)
            return
        dataset_name = ds_from_xlsx
    elif upload_format.lower() == "csv":
        csv_path = upload_path
    else:
        job.status = "failed"
        job.error = f"Unsupported upload_format={upload_format!r} (expected csv|xlsx)."
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # 2) CSV -> processed JSONL
    _append_log(log_path, "[2/7] CSV -> processed JSONL")
    processed_path = processed_dir / f"{dataset_name}__processed.jsonl"
    cmd_import_csv = [
        python_bin,
        "-m",
        "scripts.data.import_experimental_csv",
        "--csv_path",
        str(csv_path),
        "--output_dir",
        str(processed_dir),
        "--output_name",
        processed_path.name,
        "--require_eta10_condition",
    ]
    _append_log(log_path, f"[cmd] cwd={paths.youtu}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd_import_csv) }")
    env = safe_env_for_subprocess()
    rc = await run_subprocess_to_log(cmd=cmd_import_csv, cwd=paths.youtu, env=env, log_path=log_path)
    if rc != 0:
        job.status = "failed"
        job.error = f"import_experimental_csv failed (returncode={rc})."
        job.returncode = int(rc)
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # 3) processed -> dataset JSONL
    _append_log(log_path, "[3/7] processed -> dataset JSONL")
    dataset_jsonl = artifacts / f"{dataset_name}__dataset.jsonl"
    cmd_build = [
        python_bin,
        "-m",
        "scripts.data.build_chem_performance_dataset",
        "--input_dir",
        str(processed_dir),
        "--output_file",
        str(dataset_jsonl),
        "--include_unit_hint",
    ]
    _append_log(log_path, f"[cmd] cwd={paths.youtu}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd_build) }")
    rc = await run_subprocess_to_log(cmd=cmd_build, cwd=paths.youtu, env=env, log_path=log_path)
    if rc != 0:
        job.status = "failed"
        job.error = f"build_chem_performance_dataset failed (returncode={rc})."
        job.returncode = int(rc)
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # Count dataset size (N).
    n = 0
    with dataset_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    if n <= 0:
        job.status = "failed"
        job.error = "Dataset JSONL is empty after build step."
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # 4) upload dataset -> sqlite DB
    _append_log(log_path, f"[4/7] upload dataset -> sqlite DB (n={n})")
    cmd_upload = [
        python_bin,
        "-m",
        "scripts.data.upload_dataset",
        "--file_path",
        str(dataset_jsonl),
        "--dataset_name",
        str(dataset_name),
        "--data_format",
        "default",
    ]
    _append_log(log_path, f"[cmd] cwd={paths.youtu}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd_upload) }")
    rc = await run_subprocess_to_log(cmd=cmd_upload, cwd=paths.youtu, env=env, log_path=log_path)
    if rc != 0:
        job.status = "failed"
        job.error = f"upload_dataset failed (returncode={rc})."
        job.returncode = int(rc)
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # -----------------------------------------------------------------------
    # Optional bootstrap: ensure the baseline eval dataset exists in the DB.
    #
    # Why:
    # - Some configs/overrides may enable `practice.do_eval`, which requires
    #   `evaluation.data.dataset` (default: chem_performance_v2) to exist.
    # - In Docker deployments, /state/test.db may be empty on first run.
    #
    # This is safe/idempotent: we check existence first and only upload when missing.
    base_eval_dataset = "chem_performance_v2"
    base_eval_file = (
        paths.youtu / "data" / "processed" / "chem_performance" / "chem_performance_dataset_v2.jsonl"
    )
    _append_log(log_path, f"[4.5/7] ensure baseline dataset exists: {base_eval_dataset}")
    cmd_check_base = [
        python_bin,
        "-c",
        (
            "import sys\n"
            "try:\n"
            "  from utu.utils import SQLModelUtils\n"
            "  from utu.db import DatasetSample\n"
            "  from sqlalchemy import func\n"
            "  from sqlmodel import select\n"
            "  name=sys.argv[1]\n"
            "  with SQLModelUtils.create_session() as session:\n"
            "    n=session.exec(select(func.count()).select_from(DatasetSample).where(DatasetSample.dataset==name)).one()\n"
            "  n=int(n or 0)\n"
            "  print(n)\n"
            "  sys.exit(0 if n>0 else 1)\n"
            "except Exception as e:\n"
            "  print(f'CHECK_FAILED: {type(e).__name__}: {e}')\n"
            "  sys.exit(2)\n"
        ),
        base_eval_dataset,
    ]
    _append_log(log_path, f"[cmd] cwd={paths.youtu}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd_check_base) }")
    rc = await run_subprocess_to_log(cmd=cmd_check_base, cwd=paths.youtu, env=env, log_path=log_path)
    if rc == 0:
        _append_log(log_path, f"[4.5/7] baseline dataset present; skip upload: {base_eval_dataset}")
    elif rc == 1:
        if not base_eval_file.exists():
            job.status = "failed"
            job.error = f"Baseline dataset file not found: {base_eval_file}"
            job.finished_at_utc = utc_now_iso()
            store.save(job)
            return

        _append_log(log_path, f"[4.5/7] baseline dataset missing; uploading from: {base_eval_file}")
        cmd_seed_base = [
            python_bin,
            "-m",
            "scripts.data.upload_dataset",
            "--file_path",
            str(base_eval_file),
            "--dataset_name",
            base_eval_dataset,
            "--data_format",
            "default",
        ]
        _append_log(log_path, f"[cmd] cwd={paths.youtu}")
        _append_log(log_path, f"[cmd] { _quote_cmd(cmd_seed_base) }")
        rc = await run_subprocess_to_log(cmd=cmd_seed_base, cwd=paths.youtu, env=env, log_path=log_path)
        if rc != 0:
            job.status = "failed"
            job.error = f"baseline upload_dataset failed (returncode={rc})."
            job.returncode = int(rc)
            job.finished_at_utc = utc_now_iso()
            store.save(job)
            return
    else:
        job.status = "failed"
        job.error = f"baseline dataset check failed (returncode={rc}). See job.log."
        job.returncode = int(rc)
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # 5) Training-free GRPO (incremental seeding)
    exp_id = (
        f"single_update_exp_{date}_{tag}_{n}_rag1_u1_t{n}_e{int(epochs)}"
        f"_b{int(batch_size)}_n{int(grpo_n)}_c{int(rollout_concurrency)}"
    )
    _append_log(log_path, f"[5/7] Training-free GRPO (incremental seeding from active pack: {active_seed_pack})")
    cmd_grpo = [
        python_bin,
        "-m",
        "scripts.run_training_free_GRPO",
        "--config_name",
        "chem_performance_single",
        "--experiment_name",
        exp_id,
        "--practice_dataset_name",
        str(dataset_name),
        "--epochs",
        str(int(epochs)),
        "--batch_size",
        str(int(batch_size)),
        "--grpo_n",
        str(int(grpo_n)),
        "--rollout_data_truncate",
        str(int(n)),
        "--rollout_concurrency",
        str(int(rollout_concurrency)),
        "--restart_step",
        "0",
        "--seed_experience_yaml",
        str(active_seed_pack),
    ]
    _append_log(log_path, f"[cmd] cwd={paths.youtu}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd_grpo) }")
    rc = await run_subprocess_to_log(cmd=cmd_grpo, cwd=paths.youtu, env=env, log_path=log_path)
    if rc != 0:
        job.status = "failed"
        job.error = f"run_training_free_GRPO failed (returncode={rc})."
        job.returncode = int(rc)
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    grpo_agent_yaml = paths.youtu / "configs" / "agents" / "practice" / f"{exp_id}_agent.yaml"
    final_agent_yaml = grpo_agent_yaml

    default_rec_job_id = str((job.payload or {}).get("recommendation_job_id") or "").strip() or None
    rec_job_ids: list[str] = []
    raw_ids = (job.payload or {}).get("recommendation_job_ids")
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

    feedback_alignment_examples = []
    feedback_alignment_summary: dict[str, Any] = {}
    debate_trace_job_ids: list[str] = []
    debate_trace_paths: list[str] = []
    if rec_ctx:
        try:
            feedback_alignment_examples, feedback_alignment_summary = build_feedback_distill_examples(
                store=store,
                update_job_id=job.id,
                update_finished_at_utc=job.finished_at_utc,
                upload_csv_path=csv_path,
                recommendation_contexts=rec_ctx,
                default_recommendation_job_id=default_rec_job_id,
            )
        except Exception as exc:
            feedback_alignment_examples = []
            feedback_alignment_summary = {"error": f"{type(exc).__name__}: {exc}"}

    if feedback_alignment_examples:
        debate_trace_job_ids = sorted({str(item.recommendation_job_id) for item in feedback_alignment_examples})
        debate_trace_paths = sorted({str(item.trace_path) for item in feedback_alignment_examples})

        feedback_examples_path = artifacts / "feedback_alignment_examples.json"
        feedback_examples_path.write_text(
            json.dumps([item.to_dict() for item in feedback_alignment_examples], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        feedback_output_agent_yaml = (
            paths.youtu / "configs" / "agents" / "practice" / f"{exp_id}_feedback_aligned_agent.yaml"
        )
        feedback_report_path = artifacts / "feedback_alignment_report.json"
        feedback_concurrency = max(1, min(int(rollout_concurrency), 2))
        _append_log(
            log_path,
            (
                f"[6/7] Distill error-aligned recommendation traces into the feedback-updated pack "
                f"(jobs={len(debate_trace_job_ids)}, traces={len(debate_trace_paths)}, "
                f"examples={len(feedback_alignment_examples)}, concurrency={feedback_concurrency})"
            ),
        )
        _append_log(
            log_path,
            f"[6/7] alignment_summary={json.dumps(feedback_alignment_summary, ensure_ascii=False)}",
        )
        cmd_feedback = [
            python_bin,
            "scripts/debate/update_experiences_from_feedback_alignment.py",
            "--config_name",
            "chem_performance_single",
            "--seed_agent_yaml",
            str(grpo_agent_yaml),
            "--concurrency",
            str(feedback_concurrency),
            "--input_json",
            str(feedback_examples_path),
            "--output_agent_yaml",
            str(feedback_output_agent_yaml),
            "--report_path",
            str(feedback_report_path),
        ]
        feedback_env = dict(env)
        feedback_env.setdefault("UTU_EXPERIENCE_BATCH_UPDATE_MODE", "direct")
        feedback_timeout_s = float(os.environ.get("CHEMCOUNCIL_FEEDBACK_ALIGNMENT_TIMEOUT_S", "900") or 900)
        _append_log(log_path, f"[cmd] cwd={paths.youtu}")
        _append_log(log_path, f"[cmd] { _quote_cmd(cmd_feedback) }")
        _append_log(
            log_path,
            f"[6/7] feedback distillation safeguards: batch_update=direct timeout_s={feedback_timeout_s:.0f}",
        )
        rc = await run_subprocess_to_log(
            cmd=cmd_feedback,
            cwd=paths.youtu,
            env=feedback_env,
            log_path=log_path,
            timeout_s=feedback_timeout_s,
        )
        if rc != 0:
            job.status = "failed"
            job.error = f"feedback alignment distillation failed (returncode={rc})."
            job.returncode = int(rc)
            job.finished_at_utc = utc_now_iso()
            store.save(job)
            return
        final_agent_yaml = feedback_output_agent_yaml
    else:
        _append_log(
            log_path,
            (
                "[6/7] No trace-aligned experimental error examples found; "
                "using the lab-feedback-updated agent as final output."
            ),
        )
        if feedback_alignment_summary:
            _append_log(
                log_path,
                f"[6/7] alignment_summary={json.dumps(feedback_alignment_summary, ensure_ascii=False)}",
            )

    # 7) Export stable experience.yaml + sync into MAD/+state from the final agent YAML.
    _append_log(log_path, "[7/7] Sync stable experience.yaml for Web + MAD")
    cmd_sync = [
        str(paths.root / "scripts" / "run_closed_loop.sh"),
        "--seed_agent_yaml",
        str(final_agent_yaml),
        "--skip_debate_update",
    ]
    _append_log(log_path, f"[cmd] cwd={paths.root}")
    _append_log(log_path, f"[cmd] { _quote_cmd(cmd_sync) }")
    rc = await run_subprocess_to_log(cmd=cmd_sync, cwd=paths.root, env=env, log_path=log_path)
    if rc != 0:
        job.status = "failed"
        job.error = f"run_closed_loop sync failed (returncode={rc})."
        job.returncode = int(rc)
        job.finished_at_utc = utc_now_iso()
        store.save(job)
        return

    # Produce a small JSON result for the API.
    active_pack_after = active_experience_pack_path(paths)
    result = {
        "dataset_name": dataset_name,
        "num_samples": n,
        "exp_id": exp_id,
        "seed_experience_yaml": str(active_seed_pack),
        "grpo_agent_yaml": str(grpo_agent_yaml),
        "final_agent_yaml": str(final_agent_yaml),
        "experience_yaml": str(paths.youtu / "configs" / "agents" / "practice" / "experience.yaml"),
        "active_experience_yaml": str(active_pack_after),
        "recommendation_job_ids": _recommendation_job_ids_from_update_job(job),
        "debate_trace_job_ids_used": debate_trace_job_ids,
        "debate_trace_files_used": len(debate_trace_paths),
        "feedback_alignment_examples_used": len(feedback_alignment_examples),
        "feedback_alignment_summary": feedback_alignment_summary,
        "updated_at_utc": None,
    }
    try:
        exp_pack = yaml.safe_load(active_pack_after.read_text(encoding="utf-8"))
        if isinstance(exp_pack, dict) and exp_pack.get("updated_at_utc"):
            result["updated_at_utc"] = exp_pack.get("updated_at_utc")
    except Exception:
        pass

    result_path = store.job_result_path(job.id)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    job.status = "completed"
    job.result_path = str(result_path)
    job.finished_at_utc = utc_now_iso()
    store.save(job)
