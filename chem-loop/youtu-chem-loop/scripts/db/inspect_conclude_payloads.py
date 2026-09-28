#!/usr/bin/env python3
"""Inspect the raw `conclude(...)` tool-call payloads stored in `evaluation_data.trajectories`.

Why this exists
---------------
For chem-loop we ask MAD to submit the final result via the `conclude` tool with a STRICT JSON
payload, e.g.:

  {"conclusion": {"think": "...", "answer": {"overpotential_10mAcm-2": 280}}}

Downstream, the external-engine adapter normalizes this into legacy `<think>/<answer>` blocks
and stores the stitched text into `evaluation_data.response`.

The format-compliance report checks *evaluable answers* from `response`, but when debugging
we also want to confirm the model is actually using the structured tool-call channel.

Typical usage (inside docker container):
  cd /app/youtu-chem-loop
  python scripts/db/inspect_conclude_payloads.py \
    --db /state/test.db \
    --exp_id fmt_eval_smoke_20260309_002544_epoch_0 \
    --stage judged \
    --limit 5
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from typing import Any


def _safe_json_loads(s: Any) -> Any:
    if not isinstance(s, str):
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


@dataclass(frozen=True)
class Row:
    id: int
    reward: float | None
    trajectories_raw: str

    @property
    def trajectories(self) -> Any:
        return _safe_json_loads(self.trajectories_raw)


def _iter_rows(*, con: sqlite3.Connection, exp_id: str, stage: str, limit: int | None) -> list[Row]:
    cur = con.cursor()
    sql = "SELECT id, reward, trajectories FROM evaluation_data WHERE exp_id=? AND stage=? ORDER BY id ASC"
    params: list[Any] = [exp_id, stage]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    cur.execute(sql, tuple(params))
    rows: list[Row] = []
    for rid, reward, trajectories_raw in cur.fetchall():
        rows.append(
            Row(
                id=int(rid),
                reward=reward if reward is None else float(reward),
                trajectories_raw=str(trajectories_raw or ""),
            )
        )
    return rows


def _extract_last_conclude_tool_args(trajectories_obj: Any) -> Any | None:
    """Return the last `conclude(<tool_args_json>)` payload found in trajectories."""
    if not isinstance(trajectories_obj, list) or not trajectories_obj:
        return None
    first = trajectories_obj[0]
    if not isinstance(first, dict):
        return None
    msgs = first.get("trajectory")
    if not isinstance(msgs, list):
        return None

    last_args_text: str | None = None
    for msg in msgs:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, str):
            continue
        c = content.strip()
        if not (c.startswith("conclude(") and c.endswith(")")):
            continue
        inner = c[len("conclude(") : -1].strip()
        if inner:
            last_args_text = inner

    if not last_args_text:
        return None

    tool_args = _safe_json_loads(last_args_text)
    if isinstance(tool_args, dict) and "conclusion" in tool_args:
        conclusion = tool_args.get("conclusion")
        # In some providers, `conclusion` may itself be a pre-serialized JSON string.
        return _safe_json_loads(conclusion)
    return tool_args


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect conclude() tool-call payloads stored in evaluation_data.")
    ap.add_argument("--db", default="test.db", help="SQLite db file path (default: test.db)")
    ap.add_argument("--exp_id", required=True, help="Experiment id, e.g. fmt_eval_smoke_..._epoch_0")
    ap.add_argument("--stage", default="judged", help="Stage to inspect (default: judged)")
    ap.add_argument("--limit", type=int, default=10, help="Number of rows to inspect (default: 10)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    rows = _iter_rows(con=con, exp_id=args.exp_id, stage=args.stage, limit=args.limit)
    if not rows:
        raise SystemExit(f"No rows found for exp_id={args.exp_id!r} stage={args.stage!r}")

    for r in rows:
        payload = _extract_last_conclude_tool_args(r.trajectories)
        print(f"\n== id={r.id} reward={r.reward}")
        if payload is None:
            print("(no conclude() tool call found in trajectories)")
            continue
        if isinstance(payload, (dict, list)):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(str(payload))


if __name__ == "__main__":
    main()

