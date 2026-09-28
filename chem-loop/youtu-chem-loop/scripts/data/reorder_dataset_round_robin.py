#!/usr/bin/env python3
"""Reorder a default-format DatasetSample JSONL by reaction_type in a round-robin way.

Why
----
Training-free GRPO truncation (`--rollout_data_truncate N`) currently truncates *before* shuffling.
Therefore the first N records in the dataset strongly affect hyperparam sweeps.

For chem-performance datasets, a naive build order often groups by reaction_type (or file name),
which makes `truncate=40` accidentally become "only OER" or "only HER".

This script rewrites the JSONL so the early portion is balanced across reaction types
by interleaving records (round-robin) in a stable, deterministic way.

Input / Output
--------------
Input:  JSONL in DatasetSample default format (one JSON object per line)
Output: JSONL in the same format, with lines reordered
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_REACTION_ORDER = ["HER", "OER", "ORR", "HOR", "UOR", "EOR", "HzOR", "O5H", "CO2RR"]


def _repo_root() -> Path:
    # scripts/data/<this_file>.py -> scripts -> repo root
    return Path(__file__).resolve().parents[2]


def _get_reaction_type(obj: dict[str, Any]) -> str:
    meta = obj.get("meta") or {}
    rt = meta.get("reaction_type")
    return str(rt).strip() if rt else ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Round-robin reorder a default-format dataset JSONL by reaction_type.")
    ap.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="Input dataset JSONL (default format).",
    )
    ap.add_argument(
        "--output_file",
        type=str,
        required=True,
        help="Output dataset JSONL (default format).",
    )
    ap.add_argument(
        "--reaction_order",
        type=str,
        default=",".join(DEFAULT_REACTION_ORDER),
        help="Comma-separated reaction_type order used for round-robin interleaving.",
    )
    args = ap.parse_args()

    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    order = [s.strip() for s in str(args.reaction_order).split(",") if s.strip()]
    if not order:
        raise SystemExit("--reaction_order must not be empty")

    buckets: dict[str, list[str]] = defaultdict(list)
    unknown: list[str] = []
    total_in = 0

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_in += 1
            obj = json.loads(line)
            rt = _get_reaction_type(obj)
            if not rt:
                unknown.append(line)
                continue
            buckets[rt].append(line)

    # Ensure all known reaction types appear in the cycling list (append any missing).
    for rt in sorted(buckets.keys()):
        if rt not in order:
            order.append(rt)

    out_lines: list[str] = []
    out_lines.extend(unknown)  # keep unknown-meta lines first (rare)

    # Round-robin pop from buckets until all empty.
    remaining = True
    while remaining:
        remaining = False
        for rt in order:
            if buckets.get(rt):
                out_lines.append(buckets[rt].pop(0))
                remaining = True

    if len(out_lines) != total_in:
        raise SystemExit(f"Reorder bug: output_lines={len(out_lines)} input_lines={total_in}")

    with output_file.open("w", encoding="utf-8") as out:
        for line in out_lines:
            out.write(line + "\n")

    print(f"Wrote {len(out_lines)} reordered samples -> {output_file}")


if __name__ == "__main__":
    main()

