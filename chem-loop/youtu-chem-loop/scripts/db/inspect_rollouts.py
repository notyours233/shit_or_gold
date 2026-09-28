#!/usr/bin/env python3
"""Inspect rollout outputs stored in `evaluation_data`.

This is a debugging/analysis helper for checking the *actual persisted* `<think>`/`<answer>`
content used by chem verify and experience distillation.

Typical usage:
  SQLITE_TMPDIR=/tmp TMPDIR=/tmp .venv/bin/python scripts/db/inspect_rollouts.py \
    --exp_id mad_baseline_n3_epoch_0 --stage judged --order reward_desc --limit 5 \
    --include_question --out_file data/inspect_mad_baseline_top5.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


_TAG_RE_TEMPLATE = r"<{tag}>\s*(.*?)\s*</{tag}>"


def _extract_tag(text: str, tag: str) -> str | None:
    m = re.search(_TAG_RE_TEMPLATE.format(tag=re.escape(tag)), text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


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
    response: str
    raw_question: str | None
    augmented_question: str | None
    meta_raw: str | None

    @property
    def meta(self) -> dict[str, Any]:
        obj = _safe_json_loads(self.meta_raw)
        return obj if isinstance(obj, dict) else {}

    @property
    def think(self) -> str | None:
        return _extract_tag(self.response, "think")

    @property
    def answer(self) -> str | None:
        return _extract_tag(self.response, "answer")


def _iter_rows(
    *,
    con: sqlite3.Connection,
    exp_id: str,
    stage: str,
    order: str,
    limit: int | None,
    reaction_type: str | None,
) -> list[Row]:
    cur = con.cursor()
    where = ["exp_id=?", "stage=?"]
    params: list[Any] = [exp_id, stage]

    if reaction_type:
        # meta is stored as JSON string; use LIKE for best-effort filtering.
        where.append("meta LIKE ?")
        params.append(f"%\"reaction_type\": \"{reaction_type}\"%")

    order_sql = "id ASC"
    if order == "reward_desc":
        order_sql = "reward DESC, id ASC"
    elif order == "reward_asc":
        order_sql = "reward ASC, id ASC"

    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))

    sql = (
        "SELECT id, reward, response, raw_question, augmented_question, meta "
        "FROM evaluation_data "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {order_sql}"
        f"{limit_sql}"
    )
    cur.execute(sql, tuple(params))
    rows = []
    for rid, reward, response, raw_q, aug_q, meta_raw in cur.fetchall():
        rows.append(
            Row(
                id=int(rid),
                reward=reward if reward is None else float(reward),
                response=str(response or ""),
                raw_question=str(raw_q) if raw_q is not None else None,
                augmented_question=str(aug_q) if aug_q is not None else None,
                meta_raw=str(meta_raw) if meta_raw is not None else None,
            )
        )
    return rows


def _write_md(out_file: str, *, exp_id: str, stage: str, rows: Iterable[Row], include_question: bool) -> None:
    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"# Rollout Inspect\n\n- exp_id: `{exp_id}`\n- stage: `{stage}`\n- generated_at: `{now}`\n\n")
        for r in rows:
            meta = r.meta
            metals = meta.get("metals")
            reaction_type = meta.get("reaction_type")
            doc_id = meta.get("doc_id")
            input_json = meta.get("input_json") if isinstance(meta.get("input_json"), dict) else None

            f.write(f"## id={r.id} reward={r.reward}\n\n")
            f.write(f"- reaction_type: `{reaction_type}`\n")
            f.write(f"- metals: `{metals}`\n")
            f.write(f"- doc_id: `{doc_id}`\n")
            if input_json:
                f.write(f"- metrics_to_predict: `{input_json.get('metrics_to_predict')}`\n")
                if input_json.get("product") is not None:
                    f.write(f"- product: `{input_json.get('product')}`\n")
            f.write("\n")

            if include_question:
                q = r.augmented_question or r.raw_question or ""
                f.write("### Question\n\n```text\n")
                f.write(q)
                if q and not q.endswith("\n"):
                    f.write("\n")
                f.write("```\n\n")

            f.write("### Think\n\n```text\n")
            f.write(r.think or "")
            if (r.think or "") and not (r.think or "").endswith("\n"):
                f.write("\n")
            f.write("```\n\n")

            f.write("### Answer\n\n```json\n")
            f.write(r.answer or "")
            if (r.answer or "") and not (r.answer or "").endswith("\n"):
                f.write("\n")
            f.write("```\n\n")

            f.write("### Response (raw)\n\n```text\n")
            f.write(r.response)
            if r.response and not r.response.endswith("\n"):
                f.write("\n")
            f.write("```\n\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="test.db", help="SQLite db file path (default: test.db)")
    ap.add_argument("--exp_id", required=True, help="Experiment id, e.g. mad_baseline_n3_epoch_0")
    ap.add_argument("--stage", default="judged", help="Stage to inspect (default: judged)")
    ap.add_argument("--order", choices=["id", "reward_desc", "reward_asc"], default="id")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of rows")
    ap.add_argument("--reaction_type", default=None, help="Filter by reaction_type (best effort)")
    ap.add_argument("--include_question", action="store_true", help="Include augmented_question in the output")
    ap.add_argument("--out_file", default=None, help="Write markdown to this file (recommended)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    rows = _iter_rows(
        con=con,
        exp_id=args.exp_id,
        stage=args.stage,
        order=args.order,
        limit=args.limit,
        reaction_type=args.reaction_type,
    )
    if not rows:
        raise SystemExit(f"No rows found for exp_id={args.exp_id!r} stage={args.stage!r}")

    if args.out_file:
        _write_md(args.out_file, exp_id=args.exp_id, stage=args.stage, rows=rows, include_question=args.include_question)
        print(f"Wrote {len(rows)} rows to {args.out_file}")
        return

    # Fallback: print to stdout (may be very large if <think> is long).
    for r in rows:
        print(f"\n== id {r.id} reward {r.reward}")
        print("<think>")
        print(r.think or "")
        print("</think>")
        print("<answer>")
        print(r.answer or "")
        print("</answer>")


if __name__ == "__main__":
    main()

