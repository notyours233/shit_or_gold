#!/usr/bin/env python3
"""Seed minimal demo job artifacts for the ChemCouncil Web UI.

Why this exists
---------------
The Web UI has pages that depend on historical job artifacts:
- Manual feedback needs at least one completed `mad_rank` job (so the UI can auto-fill components + predictions).
- Analytics needs at least one completed `experience_update` job that links to a `mad_rank` job via
  `payload.recommendation_job_id`, and uses a CSV upload.

This script creates small, fake-but-valid jobs under a jobs root directory so you can test the frontend
without running expensive model jobs.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from chemcouncil.jobs import JobStore, utc_now_iso


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def build_demo_rank_result(*, components: str) -> dict[str, Any]:
    # Keep the schema compatible with:
    # - chemcouncil/static/app.js (manual feedback predicted values)
    # - chemcouncil/analytics.py (prediction-vs-experiment stats)
    ranking = [
        {
            "reaction_type": "HER",
            "performance_evaluation": {"metric_key": "overpotential_10mAcm-2", "metric_value": 260, "metric_unit": "mV"},
            "consensus": True,
            "evidence": "demo",
        },
        {
            "reaction_type": "OER",
            "performance_evaluation": {"metric_key": "overpotential_10mAcm-2", "metric_value": 300, "metric_unit": "mV"},
            "consensus": True,
            "evidence": "demo",
        },
        {
            "reaction_type": "HzOR",
            "performance_evaluation": {"metric_key": "overpotential_10mAcm-2", "metric_value": 80, "metric_unit": "mV"},
            "consensus": True,
            "evidence": "demo",
        },
        {
            "reaction_type": "UOR",
            "performance_evaluation": {"metric_key": "potential_10mAcm-2", "metric_value": 1.32, "metric_unit": "V"},
            "consensus": False,
            "evidence": "demo",
        },
        {
            "reaction_type": "ORR",
            "performance_evaluation": {"metric_key": "half_wave_potential", "metric_value": 0.80, "metric_unit": "V"},
            "consensus": True,
            "evidence": "demo",
        },
        {
            "reaction_type": "HOR",
            "performance_evaluation": {"metric_key": "exchange_current_density", "metric_value": 0.40, "metric_unit": "mA cm-2"},
            "consensus": False,
            "evidence": "demo",
        },
        {
            "reaction_type": "EOR",
            "performance_evaluation": {"metric_key": "mass_activity", "metric_value": 1.80, "metric_unit": "A mg^-1"},
            "consensus": False,
            "evidence": "demo",
        },
        {
            "reaction_type": "O5H",
            "performance_evaluation": {"metric_key": "faradaic_efficiency", "metric_value": 0.94, "metric_unit": "fraction_0_to_1"},
            "consensus": True,
            "evidence": "demo",
        },
        {
            "reaction_type": "CO2RR",
            "performance_evaluation": {"metric_key": "partial_current_density", "metric_value": 160, "metric_unit": "mA cm-2"},
            "consensus": True,
            "evidence": "demo",
        },
    ]
    return {
        "components": components,
        # What the UI uses to auto-build manual rows.
        "top_k": [{"reaction_type": "HER"}, {"reaction_type": "OER"}],
        "ranking": ranking,
        "meta": {"seeded": True},
    }


def build_demo_experimental_csv(*, components: str) -> str:
    # Keep this compatible with:
    # - youtu-chem-loop/scripts/data/import_experimental_csv.py
    # - chemcouncil/analytics.py (DictReader)
    lines = [
        "reaction_type,metals,product,value,unit,condition",
        f'HER,"{components}",,280,mV,"10 mA cm-2"',
        f'OER,"{components}",,310,mV,"10 mA cm-2"',
        f'HzOR,"{components}",,90,mV,"10 mA cm-2"',
        f'UOR,"{components}",,1.35,V,"10 mA cm-2"',
        f'ORR,"{components}",,0.82,V,',
        f'HOR,"{components}",,0.35,mA cm-2,',
        f'EOR,"{components}",,1.60,A mg^-1,',
        f'O5H,"{components}",,92,%, "1 M KOH"',
        f'CO2RR,"{components}",CO,180,mA cm-2,"-0.8 V vs RHE"',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed demo jobs for ChemCouncil Web UI (manual feedback + analytics).")
    ap.add_argument(
        "--jobs_root",
        type=Path,
        default=Path(".local/chemcouncil_server/jobs"),
        help="Jobs root directory (default: .local/chemcouncil_server/jobs).",
    )
    ap.add_argument(
        "--components",
        type=str,
        default="Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)",
        help="Components/metals string stored in the demo recommendation job payload.",
    )
    args = ap.parse_args()

    store = JobStore(Path(args.jobs_root))

    now = datetime.now(timezone.utc).replace(microsecond=0)
    created = now - timedelta(minutes=20)
    finished_rank = now - timedelta(minutes=18)
    finished_update = now - timedelta(minutes=10)

    # ------------------------------------------------------------------
    # 1) Demo mad_rank job
    rank_job = store.create(
        "mad_rank",
        payload={
            "components": args.components,
            "top_k_reactions": 2,
            "reaction_types": None,
            "max_parallel_reactions": 1,
            "save_each_reaction": False,
            "seeded": True,
        },
    )
    rank_job.created_at_utc = _iso(created)
    rank_job.status = "completed"
    rank_job.started_at_utc = _iso(created + timedelta(minutes=1))
    rank_job.finished_at_utc = _iso(finished_rank)
    rank_job.returncode = 0

    rank_result = build_demo_rank_result(components=args.components)
    rank_result_path = store.job_result_path(rank_job.id)
    _atomic_write_json(rank_result_path, rank_result)
    rank_job.result_path = str(rank_result_path)

    rank_log_path = store.job_log_path(rank_job.id)
    _atomic_write_text(
        rank_log_path,
        "\n".join(
            [
                f"[job] type=mad_rank id={rank_job.id}",
                f"[job] created_at_utc={rank_job.created_at_utc}",
                f"[job] finished_at_utc={rank_job.finished_at_utc}",
                "[demo] This is seeded data for frontend testing (no real model calls).",
                "",
            ]
        ),
    )
    rank_job.log_path = str(rank_log_path)
    store.save(rank_job)

    # ------------------------------------------------------------------
    # 2) Demo experience_update job (links to the rank job)
    update_job = store.create(
        "experience_update",
        payload={},
    )
    update_job.created_at_utc = _iso(created + timedelta(minutes=5))
    update_job.status = "completed"
    update_job.started_at_utc = _iso(created + timedelta(minutes=6))
    update_job.finished_at_utc = _iso(finished_update)
    update_job.returncode = 0

    update_job_dir = store.job_dir(update_job.id)
    upload_csv_path = update_job_dir / "upload.csv"
    _atomic_write_text(upload_csv_path, build_demo_experimental_csv(components=args.components))

    update_job.payload = {
        "upload_path": str(upload_csv_path),
        "upload_format": "csv",
        "tag": "demo",
        "recommendation_job_id": rank_job.id,
        "batch_size": 4,
        "grpo_n": 2,
        "rollout_concurrency": 1,
        "epochs": 1,
        "seeded": True,
    }

    update_result_path = store.job_result_path(update_job.id)
    _atomic_write_json(
        update_result_path,
        {
            "dataset_name": "chem_performance_exp_demo",
            "num_samples": 9,
            "exp_id": f"demo_update_{uuid.uuid4().hex[:8]}",
            "seed_agent_yaml": "demo",
            "experience_yaml": "demo",
            "updated_at_utc": utc_now_iso(),
            "seeded": True,
        },
    )
    update_job.result_path = str(update_result_path)

    update_log_path = store.job_log_path(update_job.id)
    _atomic_write_text(
        update_log_path,
        "\n".join(
            [
                f"[job] type=experience_update id={update_job.id}",
                f"[job] created_at_utc={update_job.created_at_utc}",
                f"[job] finished_at_utc={update_job.finished_at_utc}",
                "[demo] This is seeded data for frontend testing (no GRPO ran).",
                "",
            ]
        ),
    )
    update_job.log_path = str(update_log_path)
    store.save(update_job)

    print("Seeded demo jobs:")
    print(f"- jobs_root: {store.root}")
    print(f"- mad_rank job_id: {rank_job.id}")
    print(f"- experience_update job_id: {update_job.id} (linked reco={rank_job.id})")
    print("")
    print("Next:")
    print("- If running local web server, start it with the same jobs_root:")
    print(f"    CHEMCOUNCIL_JOBS_ROOT={store.root} ./scripts/run_web.sh")
    print("- Then open: http://localhost:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

