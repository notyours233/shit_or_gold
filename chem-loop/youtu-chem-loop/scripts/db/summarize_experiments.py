#!/usr/bin/env python3
"""Summarize Training-Free GRPO experiment results from `evaluation_data`.

This is a lightweight stdlib-only helper to compare multiple exp_id runs quickly.

Example:
  SQLITE_TMPDIR=/tmp TMPDIR=/tmp .venv/bin/python scripts/db/summarize_experiments.py \
    --exp_prefix mad_hp_ --order avg_reward_desc

Or specify explicit exp_ids:
  SQLITE_TMPDIR=/tmp TMPDIR=/tmp .venv/bin/python scripts/db/summarize_experiments.py \
    --exp_id mad_baseline_n3_epoch_0 --exp_id mad_hp_e1_b10_n2_t30_epoch_0
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


def _safe_int(x: Any) -> int | None:
    try:
        return int(x)
    except Exception:
        return None


def _safe_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


def _strip_epoch_suffix(exp_id: str) -> tuple[str, int | None]:
    """Return (experiment_name, epoch) for exp_id like 'foo_epoch_0'."""
    if "_epoch_" not in exp_id:
        return exp_id, None
    base, _, epoch_s = exp_id.rpartition("_epoch_")
    return base, _safe_int(epoch_s)


def _json_load_demo(s: str | None) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


@dataclass(frozen=True)
class ExpSummary:
    exp_id: str
    experiment_name: str
    epoch: int | None
    n_judged: int
    avg_reward: float | None
    min_reward: float | None
    max_reward: float | None
    n_reward_gt0: int
    n_reward_ge_05: int
    n_reward_ge_08: int
    n_parse_error: int
    n_experience_steps: int | None
    n_guidelines_latest: int | None

    @property
    def parse_error_rate(self) -> float | None:
        if self.n_judged <= 0:
            return None
        return self.n_parse_error / self.n_judged

    @property
    def pass_rate_gt0(self) -> float | None:
        if self.n_judged <= 0:
            return None
        return self.n_reward_gt0 / self.n_judged


def _iter_exp_ids(con: sqlite3.Connection, exp_ids: list[str] | None, exp_prefix: str | None) -> list[str]:
    cur = con.cursor()

    if exp_ids:
        return list(dict.fromkeys(exp_ids))

    if exp_prefix is None:
        raise SystemExit("Must provide either --exp_id (repeatable) or --exp_prefix.")

    cur.execute(
        "SELECT DISTINCT exp_id FROM evaluation_data WHERE exp_id LIKE ? ORDER BY exp_id ASC",
        (f"{exp_prefix}%",),
    )
    return [str(r[0]) for r in cur.fetchall() if r and r[0]]


def _get_experience_stats(con: sqlite3.Connection, *, experiment_name: str) -> tuple[int | None, int | None]:
    cur = con.cursor()
    cur.execute(
        "SELECT step, experiences FROM cache_experience WHERE experiment_name=? ORDER BY step DESC LIMIT 1",
        (experiment_name,),
    )
    row = cur.fetchone()
    if not row:
        return None, None

    step, payload = row
    obj = _json_load_demo(payload if isinstance(payload, str) else None)
    n_guidelines = len(obj) if isinstance(obj, dict) else None
    return _safe_int(step), n_guidelines


def summarize_one(con: sqlite3.Connection, *, exp_id: str) -> ExpSummary:
    cur = con.cursor()

    cur.execute(
        "SELECT COUNT(*), AVG(reward), MIN(reward), MAX(reward) "
        "FROM evaluation_data WHERE exp_id=? AND stage='judged'",
        (exp_id,),
    )
    n_judged, avg_r, min_r, max_r = cur.fetchone()

    cur.execute(
        "SELECT "
        "SUM(CASE WHEN reward>0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN reward>=0.5 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN reward>=0.8 THEN 1 ELSE 0 END) "
        "FROM evaluation_data WHERE exp_id=? AND stage='judged'",
        (exp_id,),
    )
    n_gt0, n_ge05, n_ge08 = cur.fetchone()

    # "reasoning" is used by chem verify as an error channel for parse/format failures.
    cur.execute(
        "SELECT COUNT(*) FROM evaluation_data "
        "WHERE exp_id=? AND stage='judged' AND reasoning IS NOT NULL AND reasoning<>''",
        (exp_id,),
    )
    n_parse_error = cur.fetchone()[0]

    experiment_name, epoch = _strip_epoch_suffix(exp_id)
    latest_step, n_guidelines_latest = _get_experience_stats(con, experiment_name=experiment_name)

    return ExpSummary(
        exp_id=exp_id,
        experiment_name=experiment_name,
        epoch=epoch,
        n_judged=int(n_judged or 0),
        avg_reward=_safe_float(avg_r),
        min_reward=_safe_float(min_r),
        max_reward=_safe_float(max_r),
        n_reward_gt0=int(n_gt0 or 0),
        n_reward_ge_05=int(n_ge05 or 0),
        n_reward_ge_08=int(n_ge08 or 0),
        n_parse_error=int(n_parse_error or 0),
        n_experience_steps=int(latest_step) if latest_step is not None else None,
        n_guidelines_latest=int(n_guidelines_latest) if n_guidelines_latest is not None else None,
    )


def _format_pct(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x*100:.1f}%"


def _format_float(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:.4f}"


def _print_table(rows: Iterable[ExpSummary]) -> None:
    headers = [
        "exp_id",
        "n_judged",
        "avg",
        "min",
        "max",
        "pass>0",
        ">=0.5",
        ">=0.8",
        "parse_err",
        "guidelines",
    ]
    print(" | ".join(headers))
    print(" | ".join(["---"] * len(headers)))
    for r in rows:
        guidelines = "-" if r.n_guidelines_latest is None else str(r.n_guidelines_latest)
        print(
            " | ".join(
                [
                    r.exp_id,
                    str(r.n_judged),
                    _format_float(r.avg_reward),
                    _format_float(r.min_reward),
                    _format_float(r.max_reward),
                    _format_pct(r.pass_rate_gt0),
                    str(r.n_reward_ge_05),
                    str(r.n_reward_ge_08),
                    str(r.n_parse_error),
                    guidelines,
                ]
            )
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="test.db", help="SQLite db file path (default: test.db)")
    ap.add_argument("--exp_id", action="append", default=None, help="Repeatable exp_id (e.g. foo_epoch_0)")
    ap.add_argument("--exp_prefix", default=None, help="List exp_ids starting with this prefix")
    ap.add_argument("--order", choices=["exp_id", "avg_reward_desc", "avg_reward_asc"], default="avg_reward_desc")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    exp_ids = _iter_exp_ids(con, exp_ids=args.exp_id, exp_prefix=args.exp_prefix)
    summaries = [summarize_one(con, exp_id=eid) for eid in exp_ids]

    if args.order == "exp_id":
        summaries.sort(key=lambda s: s.exp_id)
    elif args.order == "avg_reward_desc":
        summaries.sort(key=lambda s: (s.avg_reward is None, -(s.avg_reward or 0.0), s.exp_id))
    elif args.order == "avg_reward_asc":
        summaries.sort(key=lambda s: (s.avg_reward is None, (s.avg_reward or 0.0), s.exp_id))

    _print_table(summaries)


if __name__ == "__main__":
    main()
