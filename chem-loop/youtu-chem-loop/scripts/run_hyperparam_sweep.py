#!/usr/bin/env python3
"""Run a disciplined hyperparameter sweep for single-agent Training-Free GRPO.

This script is intentionally stdlib-only so it can be executed in minimal environments
without extra deps.

Design goals (spec-bank/hyperparam_experiments.md):
- Only tune: epochs / batch_size / grpo_n
- Keep everything else fixed (dataset, truncate, rollout_concurrency, RAG settings, verify logic)
- Use a deterministic, comparable experiment naming convention
"""

from __future__ import annotations

import argparse
import itertools
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SweepConfig:
    config_name: str
    dataset: str
    truncate: int
    rollout_concurrency: int
    restart_step: int

    rag_enabled: bool
    rag_limit: int
    rag_max_distance: float
    rag_timeout_s: float

    exp_prefix: str


def _repo_root() -> Path:
    # scripts/run_hyperparam_sweep.py -> repo root is one level up
    return Path(__file__).resolve().parents[1]


_SQLITE_URL_RE = re.compile(r"^sqlite(?P<driver>\\+[^:]*)?:(?P<rest>.*)$", flags=re.IGNORECASE)


def _db_path_from_utu_db_url(*, repo_root: Path, env: dict[str, str]) -> Path:
    """Resolve the SQLite DB filepath from UTU_DB_URL when running inside Docker.

    Why:
    - In docker compose we set `UTU_DB_URL=sqlite:////state/test.db` so all subprocesses share the same DB.
    - This sweep runner also uses sqlite3 directly (for skip-existing checks), so it must point at the same file.
    """
    url = str(env.get("UTU_DB_URL") or "").strip()
    m = _SQLITE_URL_RE.match(url)
    if not m:
        return repo_root / "test.db"

    rest = str(m.group("rest") or "")
    # SQLAlchemy conventions:
    # - sqlite:////abs/path.db  -> /abs/path.db
    # - sqlite:///rel/path.db   -> rel/path.db   (relative to CWD)
    if rest.startswith("////"):
        return Path(rest[3:])  # keep the leading "/" (absolute)
    if rest.startswith("///"):
        rel = rest[3:]
        return (repo_root / rel).resolve() if rel else (repo_root / "test.db")

    # Other sqlite URL forms are uncommon in this repo (e.g., :memory:); fall back.
    return repo_root / "test.db"


def _normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return "single_hp_"
    return p if p.endswith("_") else (p + "_")


def _dataset_code(dataset: str) -> str:
    ds = (dataset or "").strip()
    # Common, short, stable codes for our current chem-performance subsets.
    if ds == "chem_performance_v2_350_noher_co2rr":
        return "ds350"
    if ds == "chem_performance_v2_450":
        return "ds450"
    if ds == "chem_performance_v2":
        return "dsfull"
    if ds.startswith("chem_performance_v5_balanced5_seed"):
        return "bal50"
    m = re.match(r"^material_property_param_bal(?P<per>[0-9]+)_seed(?P<seed>[0-9]+)$", ds)
    if m:
        total = 6 * int(m.group("per"))
        return f"mptest{total}"
    m = re.match(r"^material_property_bal(?P<per>[0-9]+)_seed(?P<seed>[0-9]+)$", ds)
    if m:
        total = 6 * int(m.group("per"))
        return f"mpbal{total}"
    m = re.match(r"^chem_performance_v5_bal(?P<per>[0-9]+)_co2(?P<co2>[0-9]+)_seed(?P<seed>[0-9]+)$", ds)
    if m:
        per = int(m.group("per"))
        co2 = int(m.group("co2"))
        total = 8 * per + 2 * co2
        return f"bal{total}"
    # Fallback: sanitize
    safe = []
    for ch in ds:
        if ch.isalnum():
            safe.append(ch)
        elif ch in ("-", "_"):
            safe.append(ch)
    out = "".join(safe)
    return out[:24] if out else "ds"


def make_experiment_name(
    *,
    prefix: str,
    dataset: str,
    truncate: int,
    epochs: int,
    batch_size: int,
    grpo_n: int,
    rag_enabled: bool,
    units_enabled: bool = True,
) -> str:
    # Keep this filename-safe: only letters/numbers/underscore.
    p = _normalize_prefix(prefix)
    ds_code = _dataset_code(dataset)
    rag = 1 if rag_enabled else 0
    u = 1 if units_enabled else 0
    return f"{p}rag{rag}_u{u}_{ds_code}_t{int(truncate)}_e{int(epochs)}_b{int(batch_size)}_n{int(grpo_n)}"


def _epoch0_exp_id(experiment_name: str) -> str:
    return f"{experiment_name}_epoch_0"


def _exp_exists(*, db_path: Path, epoch0_exp_id: str) -> bool:
    if not db_path.exists():
        return False
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        try:
            cur.execute("SELECT 1 FROM evaluation_data WHERE exp_id=? LIMIT 1", (epoch0_exp_id,))
        except sqlite3.OperationalError:
            # Fresh/empty DB (or unexpected schema): treat as "not exists" so the sweep can proceed and create tables.
            return False
        return cur.fetchone() is not None
    finally:
        con.close()


def _exp_judged_count(*, db_path: Path, epoch0_exp_id: str) -> int:
    if not db_path.exists():
        return 0
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM evaluation_data WHERE exp_id=? AND stage='judged'",
                (epoch0_exp_id,),
            )
        except sqlite3.OperationalError:
            return 0
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        con.close()


def _run_one(cmd: list[str], *, env: dict[str, str], cwd: Path, dry_run: bool) -> int:
    print("\n$ " + " ".join(cmd), flush=True)
    if dry_run:
        return 0
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, check=False)
    return int(proc.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--config_name", default="chem_performance_single")
    ap.add_argument("--dataset", default="chem_performance_v2_350_noher_co2rr")
    ap.add_argument("--truncate", type=int, default=30, help="rollout_data_truncate (keep fixed for the sweep)")
    ap.add_argument(
        "--rollout_concurrency",
        type=int,
        default=4,
        help=(
            "rollout_concurrency (keep fixed for the sweep). Higher is faster but may increase memory usage "
            "significantly (especially when literature RAG/Chroma is enabled)."
        ),
    )
    ap.add_argument(
        "--rollout_concurrency_fallback",
        type=int,
        default=None,
        help=(
            "Optional: if a run fails at the primary rollout_concurrency (OOM/timeout/overload), retry the same run "
            "once with this lower concurrency and use it for the remaining runs. This is a speed/memory safety valve, "
            "not a tunable hyperparameter."
        ),
    )
    ap.add_argument(
        "--restart_step",
        type=int,
        default=0,
        help="Pass through to run_training_free_GRPO.py (0 = no cache; recommended for clean sweeps).",
    )

    # Defaults are intentionally small to avoid accidentally launching a large/costly sweep.
    ap.add_argument("--epochs", default="1", help="Comma-separated list, e.g. '1,2'")
    ap.add_argument("--batch_sizes", default="10", help="Comma-separated list, e.g. '10,30,50'")
    ap.add_argument("--grpo_ns", default="1", help="Comma-separated list, e.g. '1,2,3'")
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Allow running a large sweep (otherwise large plans require --dry_run first).",
    )

    ap.add_argument("--exp_prefix", default="single_hp_", help="Prefix for experiment_name (used by summarize script)")
    ap.add_argument("--skip_existing", action="store_true", default=True, help="Skip if exp_id already exists in DB")
    ap.add_argument("--no-skip_existing", dest="skip_existing", action="store_false")
    ap.add_argument("--dry_run", action="store_true", help="Print commands without executing")

    # RAG settings (keep fixed when comparing).
    ap.add_argument("--rag", action="store_true", default=True, help="Enable single-agent literature retrieval (RAG)")
    ap.add_argument("--no-rag", dest="rag", action="store_false")
    ap.add_argument("--rag_limit", type=int, default=5)
    ap.add_argument("--rag_max_distance", type=float, default=0.35)
    ap.add_argument("--rag_timeout_s", type=float, default=30.0)

    # Optional post-GRPO evaluation. This is deliberately external to TrainingFreeGRPO.do_eval:
    # the generated agent YAML must be loaded so the held-out run actually sees the new experiences.
    ap.add_argument("--heldout_dataset", default=None)
    ap.add_argument("--heldout_concurrency", type=int, default=1)
    ap.add_argument("--heldout_exp_suffix", default="_heldout")
    ap.add_argument("--heldout_expected_questions", type=int, default=None)
    ap.add_argument("--report_dir", type=Path, default=None)

    args = ap.parse_args()

    repo_root = _repo_root()
    base_env_probe = os.environ.copy()
    db_path = _db_path_from_utu_db_url(repo_root=repo_root, env=base_env_probe)

    def _parse_int_list(s: str) -> list[int]:
        out: list[int] = []
        # Accept common Chinese list separators to reduce copy/paste mistakes.
        s_norm = (s or "").replace("，", ",").replace("、", ",")
        for part in s_norm.split(","):
            part = part.strip()
            if not part:
                continue
            out.append(int(part))
        if not out:
            raise SystemExit(f"Empty int list: {s!r}")
        return out

    epochs_list = _parse_int_list(args.epochs)
    batch_sizes = _parse_int_list(args.batch_sizes)
    grpo_ns = _parse_int_list(args.grpo_ns)

    primary_concurrency = int(args.rollout_concurrency)
    fallback_concurrency = (
        int(args.rollout_concurrency_fallback) if args.rollout_concurrency_fallback is not None else None
    )
    if fallback_concurrency is not None and fallback_concurrency >= primary_concurrency:
        print(
            f"[warn] rollout_concurrency_fallback={fallback_concurrency} >= rollout_concurrency={primary_concurrency}; "
            "disabling fallback.",
            flush=True,
        )
        fallback_concurrency = None

    sweep_cfg = SweepConfig(
        config_name=str(args.config_name),
        dataset=str(args.dataset),
        truncate=int(args.truncate),
        rollout_concurrency=primary_concurrency,
        restart_step=int(args.restart_step),
        rag_enabled=bool(args.rag),
        rag_limit=int(args.rag_limit),
        rag_max_distance=float(args.rag_max_distance),
        rag_timeout_s=float(args.rag_timeout_s),
        exp_prefix=_normalize_prefix(str(args.exp_prefix)),
    )

    # Fixed env knobs for stability (Chroma/SQLite temp files).
    base_env = os.environ.copy()
    base_env.setdefault("SQLITE_TMPDIR", "/tmp")
    base_env.setdefault("TMPDIR", "/tmp")

    # Fixed single-agent literature RAG knobs for comparability.
    base_env["CHEM_GRPO_RAG_ENABLED"] = "1" if sweep_cfg.rag_enabled else "0"
    base_env["CHEM_GRPO_RAG_LIMIT"] = str(sweep_cfg.rag_limit)
    base_env["CHEM_LITERATURE_CHROMA_MAX_DISTANCE"] = str(sweep_cfg.rag_max_distance)
    base_env["VOYAGE_TIMEOUT"] = str(sweep_cfg.rag_timeout_s)

    # Run combinations in deterministic order.
    combos = list(itertools.product(epochs_list, batch_sizes, grpo_ns))
    n_plan = len(combos)
    print(f"Planned runs: {n_plan} combos", flush=True)
    print(
        f"Fixed: dataset={sweep_cfg.dataset} truncate={sweep_cfg.truncate} rollout_concurrency={sweep_cfg.rollout_concurrency} "
        f"rag={int(sweep_cfg.rag_enabled)} rag_limit={sweep_cfg.rag_limit} rag_max_distance={sweep_cfg.rag_max_distance}",
        flush=True,
    )
    if args.heldout_dataset:
        print(
            f"Held-out: dataset={args.heldout_dataset} concurrency={args.heldout_concurrency} "
            f"expected_questions={args.heldout_expected_questions} report_dir={args.report_dir}",
            flush=True,
        )
        if args.heldout_concurrency <= 0:
            raise SystemExit("heldout_concurrency must be greater than zero")
        if args.report_dir is None:
            raise SystemExit("--report_dir is required when --heldout_dataset is set")
    if fallback_concurrency is not None:
        print(f"Safety: rollout_concurrency_fallback={fallback_concurrency} (auto-switch on first failure)", flush=True)
    if n_plan > 12 and not args.dry_run and not args.yes:
        raise SystemExit(
            f"Refusing to run a large sweep ({n_plan} combos) without --yes. "
            "Re-run with --dry_run to preview, or pass --yes to proceed."
        )

    python_bin = sys.executable
    # IMPORTANT: call as a module so `utu` imports resolve correctly (sys.path includes repo root).
    # Running it as a file path (`python scripts/run_training_free_GRPO.py`) sets sys.path[0] to `scripts/`,
    # which makes `import utu` fail inside Docker.
    runner_mod = "scripts.run_training_free_GRPO"

    ran = 0
    skipped = 0
    failed = 0
    curr_concurrency = int(sweep_cfg.rollout_concurrency)

    for e, b, n in combos:
        experiment_name = make_experiment_name(
            prefix=sweep_cfg.exp_prefix,
            dataset=sweep_cfg.dataset,
            truncate=sweep_cfg.truncate,
            epochs=e,
            batch_size=b,
            grpo_n=n,
            rag_enabled=sweep_cfg.rag_enabled,
            units_enabled=True,  # unit conventions are injected in preprocess for chem_performance datasets
        )
        epoch0 = _epoch0_exp_id(experiment_name)
        expected_training_rollouts = int(sweep_cfg.truncate) * int(n)
        existing_judged = _exp_judged_count(db_path=db_path, epoch0_exp_id=epoch0)
        training_ready = False
        if args.skip_existing and existing_judged == expected_training_rollouts:
            print(
                f"[skip] {epoch0} already complete in DB "
                f"(judged={existing_judged}/{expected_training_rollouts})",
                flush=True,
            )
            skipped += 1
            training_ready = True

        def _make_cmd(*, rollout_concurrency: int) -> list[str]:
            return [
                python_bin,
                "-m",
                runner_mod,
                "--config_name",
                sweep_cfg.config_name,
                "--experiment_name",
                experiment_name,
                "--practice_dataset_name",
                sweep_cfg.dataset,
                "--epochs",
                str(e),
                "--batch_size",
                str(b),
                "--grpo_n",
                str(n),
                "--rollout_data_truncate",
                str(sweep_cfg.truncate),
                "--rollout_concurrency",
                str(int(rollout_concurrency)),
                "--restart_step",
                str(sweep_cfg.restart_step),
            ]

        rc = 0
        if not training_ready:
            rc = _run_one(
                _make_cmd(rollout_concurrency=curr_concurrency),
                env=base_env,
                cwd=repo_root,
                dry_run=bool(args.dry_run),
            )
        if not training_ready and rc != 0:
            # Auto-fallback: drop rollout concurrency and retry once to avoid losing the whole sweep to OOM/timeouts.
            if fallback_concurrency is not None and curr_concurrency != fallback_concurrency:
                print(
                    f"[fallback] run failed (rc={rc}); switching rollout_concurrency {curr_concurrency} -> {fallback_concurrency} "
                    "and retrying this run once.",
                    flush=True,
                )
                curr_concurrency = int(fallback_concurrency)
                rc2 = _run_one(
                    _make_cmd(rollout_concurrency=curr_concurrency),
                    env=base_env,
                    cwd=repo_root,
                    dry_run=bool(args.dry_run),
                )
                if rc2 != 0:
                    print(f"[fail] experiment_name={experiment_name} rc={rc2} (after fallback)", flush=True)
                    failed += 1
                else:
                    ran += 1
                    training_ready = True
            else:
                print(f"[fail] experiment_name={experiment_name} rc={rc}", flush=True)
                failed += 1
        elif not training_ready:
            ran += 1
            training_ready = True

        if not training_ready:
            continue

        # Print a one-line summary for quick feedback (epoch_0 only).
        summarize_cmd = [
            python_bin,
            "scripts/db/summarize_experiments.py",
            "--db",
            str(db_path),
            "--exp_id",
            epoch0,
            "--order",
            "exp_id",
        ]
        _run_one(summarize_cmd, env=base_env, cwd=repo_root, dry_run=bool(args.dry_run))

        if args.heldout_dataset:
            agent_yaml = repo_root / "configs" / "agents" / "practice" / f"{experiment_name}_agent.yaml"
            if not args.dry_run and not agent_yaml.is_file():
                print(f"[fail] generated agent YAML missing: {agent_yaml}", flush=True)
                failed += 1
                continue
            heldout_exp_id = f"{experiment_name}{args.heldout_exp_suffix}"
            eval_cmd = [
                python_bin,
                "scripts/eval_material_performance_experience.py",
                "--agent-config",
                str(agent_yaml),
                "--dataset",
                str(args.heldout_dataset),
                "--exp-id",
                heldout_exp_id,
                "--concurrency",
                str(args.heldout_concurrency),
            ]
            eval_rc = _run_one(eval_cmd, env=base_env, cwd=repo_root, dry_run=bool(args.dry_run))
            if eval_rc != 0:
                print(f"[fail] held-out evaluation failed: {heldout_exp_id} rc={eval_rc}", flush=True)
                failed += 1
                continue

            report_path = args.report_dir / f"{experiment_name}.json"
            report_cmd = [
                python_bin,
                "scripts/db/report_material_performance_hp.py",
                "--db",
                str(db_path),
                "--training-exp-id",
                epoch0,
                "--heldout-exp-id",
                heldout_exp_id,
                "--agent-config",
                str(agent_yaml),
                "--batch-size",
                str(b),
                "--grpo-n",
                str(n),
                "--expected-train-questions",
                str(sweep_cfg.truncate),
                "--output",
                str(report_path),
            ]
            if args.heldout_expected_questions is not None:
                report_cmd.extend(
                    ["--expected-heldout-questions", str(args.heldout_expected_questions)]
                )
            report_rc = _run_one(report_cmd, env=base_env, cwd=repo_root, dry_run=bool(args.dry_run))
            if report_rc != 0:
                print(f"[fail] candidate report failed: {report_path} rc={report_rc}", flush=True)
                failed += 1

    print(f"\nDone. ran={ran} skipped={skipped} failed={failed} (prefix={sweep_cfg.exp_prefix})", flush=True)

    # Final table for the whole sweep prefix.
    final_cmd = [
        python_bin,
        "scripts/db/summarize_experiments.py",
        "--db",
        str(db_path),
        "--exp_prefix",
        sweep_cfg.exp_prefix,
    ]
    _run_one(final_cmd, env=base_env, cwd=repo_root, dry_run=bool(args.dry_run))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
