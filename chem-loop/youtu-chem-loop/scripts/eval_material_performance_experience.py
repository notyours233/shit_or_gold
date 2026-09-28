#!/usr/bin/env python3
"""Evaluate a generated single-agent experience pack on a held-out dataset."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import func
from sqlmodel import select


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utu.config import ConfigLoader  # noqa: E402
from utu.config.eval_config import DataConfig, EvalConfig  # noqa: E402
from utu.db import DatasetSample, EvaluationSample  # noqa: E402
from utu.eval import BaseBenchmark  # noqa: E402
from utu.utils import SQLModelUtils  # noqa: E402


def _agent_config_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("agent config is required")
    path = Path(raw)
    if path.suffix in {".yaml", ".yml"}:
        candidate = path if path.is_absolute() else (Path.cwd() / path)
        if not candidate.is_file():
            candidate = REPO_ROOT / path
        if not candidate.is_file():
            raise FileNotFoundError(f"agent config not found: {value}")
        agents_dir = REPO_ROOT / "configs" / "agents"
        try:
            return candidate.resolve().relative_to(agents_dir.resolve()).with_suffix("").as_posix()
        except ValueError as exc:
            raise ValueError(f"agent config must be under {agents_dir}: {candidate}") from exc
    return raw


def build_eval_config(
    *,
    agent_config: str,
    dataset: str,
    exp_id: str,
    concurrency: int,
) -> EvalConfig:
    if not dataset.strip() or not exp_id.strip():
        raise ValueError("dataset and exp_id are required")
    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")

    config = ConfigLoader.load_eval_config("chem/chem_performance_single")
    config.agent = ConfigLoader.load_agent_config(_agent_config_name(agent_config))
    env_name = (config.agent.env.name or "").strip().lower() if config.agent.env else ""
    if env_name == "mad":
        raise ValueError("held-out GRPO evaluation requires a single-agent config; MAD is not allowed")
    if config.agent.type != "simple":
        raise ValueError(f"held-out GRPO evaluation requires agent.type='simple', got {config.agent.type!r}")
    config.exp_id = exp_id.strip()
    config.data = DataConfig(dataset=dataset.strip())
    config.concurrency = concurrency
    config.pass_k = 1
    return config


def _dataset_count(dataset: str) -> int:
    with SQLModelUtils.create_session() as session:
        value = session.exec(
            select(func.count()).select_from(DatasetSample).where(DatasetSample.dataset == dataset)
        ).one()
    return int(value or 0)


def _exp_stage_counts(exp_id: str) -> dict[str, int]:
    counts = {"total": 0, "init": 0, "rollout": 0, "judged": 0}
    with SQLModelUtils.create_session() as session:
        rows = session.exec(
            select(EvaluationSample.stage, func.count())
            .where(EvaluationSample.exp_id == exp_id)
            .group_by(EvaluationSample.stage)
        ).all()
    for stage, count in rows:
        key = str(stage or "")
        if key in counts:
            counts[key] = int(count or 0)
        counts["total"] += int(count or 0)
    return counts


async def _run(args: argparse.Namespace) -> None:
    config = build_eval_config(
        agent_config=args.agent_config,
        dataset=args.dataset,
        exp_id=args.exp_id,
        concurrency=args.concurrency,
    )
    expected = _dataset_count(config.data.dataset)
    if expected <= 0:
        raise RuntimeError(f"held-out dataset is empty or missing: {config.data.dataset}")

    before = _exp_stage_counts(config.exp_id)
    if before["total"] not in (0, expected):
        raise RuntimeError(
            f"held-out exp_id={config.exp_id!r} has {before['total']} rows; expected 0 or {expected}. "
            "Use a fresh exp_id instead of mixing stale evaluation rows."
        )
    if before["judged"] == expected and before["total"] == expected:
        print(
            f"heldout_status=complete_reused exp_id={config.exp_id} dataset={config.data.dataset} "
            f"judged={expected}"
        )
        return

    benchmark = BaseBenchmark(config)
    await benchmark.main()
    after = _exp_stage_counts(config.exp_id)
    if after["total"] != expected or after["judged"] != expected:
        raise RuntimeError(
            f"held-out evaluation incomplete for exp_id={config.exp_id!r}: "
            f"expected={expected}, counts={after}"
        )
    print(
        f"heldout_status=complete exp_id={config.exp_id} dataset={config.data.dataset} "
        f"judged={after['judged']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-config", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--exp-id", required=True)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
