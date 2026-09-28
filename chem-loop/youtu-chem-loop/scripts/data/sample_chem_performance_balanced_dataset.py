#!/usr/bin/env python3
"""Create a balanced chem-performance dataset subset (e.g., 50 per reaction_type).

Why
----
When generating a "real" experience library, we often want:
- coverage across all 9 reaction types, AND
- predictable cost (fixed sample count), AND
- reproducibility (deterministic sampling via seed).

This script samples from an existing *uploadable* DatasetSample JSONL (default format),
such as:
  data/processed/chem_performance/chem_performance_dataset_v5.jsonl

and writes a new JSONL that can be uploaded as a new dataset name (e.g., chem_performance_v5_450).

Notes
-----
- Standard-library only (no utu import), for portability.
- CO2RR has two task types in this project stage (product classification + partial current density regression).
  When sampling CO2RR we sample at the *record id* level and always include both tasks so the two tasks
  appear equally often in the sampled subset.
"""

from __future__ import annotations

import argparse
import json
import random
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REACTION_TYPES_DEFAULT = ["HER", "OER", "ORR", "HOR", "UOR", "EOR", "HzOR", "O5H", "CO2RR"]

_CO2RR_VALID_PRODUCTS = ["CO", "HCOOH", "CH4", "C2H5OH", "C2H4", "CH3COOH"]


def _build_co2rr_top_product_question_with_fe(input_obj: dict[str, Any]) -> str:
    input_json_str = json.dumps(input_obj, ensure_ascii=False, indent=2)
    labels = ", ".join(_CO2RR_VALID_PRODUCTS)
    return (
        "Task: For CO2RR, predict the main product (the product with the highest Faradaic efficiency) and its Faradaic efficiency.\n\n"
        "INPUT_JSON:\n"
        f"{input_json_str}\n\n"
        f"Valid product labels in this dataset: {labels}.\n\n"
        "Output format MUST be:\n"
        "<think>\n"
        "concise explicit reasoning\n"
        "</think>\n"
        "<answer>\n"
        "{ \"product\": \"PRODUCT_NAME\", \"faradaic_efficiency\": number }\n"
        "</answer>\n\n"
        "Rules:\n"
        "- The <answer> must be valid JSON dict.\n"
        "- The value of 'product' must be a string.\n"
        "- The value of 'faradaic_efficiency' must be a number in [0,1] (fraction, not percent).\n"
        "- Do not output extra keys (only 'product' and 'faradaic_efficiency').\n"
        "- Do not output any text outside <think> and <answer>.\n"
    )


def _upgrade_co2rr_top_product_sample_to_include_fe(obj: dict[str, Any]) -> dict[str, Any]:
    """Upgrade CO2RR Task 1 samples to include truth FE in both question + answer.

    This enables a richer reward signal for Training-Free GRPO without requiring
    regenerating the full base dataset JSONL.
    """
    meta = obj.get("meta") or {}
    if str(meta.get("reaction_type") or "").strip() != "CO2RR":
        return obj
    if str(meta.get("task_type") or "").strip() != "co2rr_top_product":
        return obj

    metrics_raw = meta.get("metrics_raw") or {}
    truth_fe = metrics_raw.get("truth_faradaic_efficiency_fraction")
    if truth_fe is None or not str(truth_fe).strip():
        return obj

    # Update answer JSON (add faradaic_efficiency key).
    try:
        ans = json.loads(obj.get("answer") or "")
    except Exception:
        return obj
    if not isinstance(ans, dict) or not ans:
        return obj
    if "faradaic_efficiency" in ans:
        return obj  # already upgraded

    ans2 = dict(ans)
    ans2["faradaic_efficiency"] = truth_fe

    # Update question prompt to request FE.
    input_obj = meta.get("input_json")
    if not isinstance(input_obj, dict) or not input_obj:
        metals = meta.get("metals") if isinstance(meta.get("metals"), list) else []
        input_obj = {"metals": metals, "reaction_type": "CO2RR"}
    q2 = _build_co2rr_top_product_question_with_fe(input_obj)

    # Update meta.units so unit-repair helpers have a canonical hint.
    units = meta.get("units") or {}
    if not isinstance(units, dict):
        units = {}
    units2 = dict(units)
    units2.setdefault("faradaic_efficiency", "fraction_0_to_1")

    meta2 = dict(meta)
    meta2["units"] = units2

    obj2 = dict(obj)
    obj2["question"] = q2
    obj2["answer"] = json.dumps(ans2, ensure_ascii=False, sort_keys=True)
    obj2["meta"] = meta2
    return obj2


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _sort_key(sample: dict[str, Any]) -> tuple[int, str]:
    meta = sample.get("meta") or {}
    sid = _safe_int(meta.get("id"))
    if sid is None:
        sid = 10**18
    # Add a stable tie-breaker so ordering doesn't depend on Python dict ordering.
    return (sid, json.dumps(meta, ensure_ascii=True, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample a balanced subset from a chem-performance dataset JSONL.")
    parser.add_argument(
        "--input_file",
        type=str,
        default="data/processed/chem_performance/chem_performance_dataset_v5.jsonl",
        help="Input uploadable dataset JSONL (default-format).",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="data/processed/chem_performance/chem_performance_dataset_v5_450.jsonl",
        help="Output JSONL path (default-format; ready for upload).",
    )
    parser.add_argument(
        "--per_reaction",
        type=int,
        default=50,
        help="Number of samples to keep per reaction_type (can be overridden per reaction via --per_reaction_overrides).",
    )
    parser.add_argument(
        "--per_reaction_overrides",
        type=str,
        default="",
        help=(
            "Optional per-reaction override list, e.g. 'HOR=40,HER=200'. "
            "Reaction types not listed use --per_reaction."
        ),
    )
    parser.add_argument(
        "--co2rr_per_task",
        type=int,
        default=None,
        help=(
            "Optional override for CO2RR: number of samples to keep *per CO2RR task type* "
            "(task1=co2rr_top_product and task2=co2rr_partial_current_density). "
            "If set, CO2RR will contribute 2*co2rr_per_task samples and this overrides --per_reaction for CO2RR."
        ),
    )
    parser.add_argument(
        "--reactions",
        type=str,
        default=",".join(REACTION_TYPES_DEFAULT),
        help="Comma-separated reaction types to include (default: 9 reactions).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed used for sampling.",
    )
    parser.add_argument(
        "--shuffle_output",
        action="store_true",
        help="If set, shuffle the combined output order (still deterministic via seed).",
    )
    args = parser.parse_args()

    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    wanted_rts = [s.strip() for s in str(args.reactions).split(",") if s.strip()]
    if not wanted_rts:
        raise ValueError("--reactions must include at least one reaction_type")
    per_reaction = int(args.per_reaction)
    if per_reaction <= 0:
        raise ValueError("--per_reaction must be > 0")

    overrides: dict[str, int] = {}
    overrides_raw = (args.per_reaction_overrides or "").replace("，", ",").replace("、", ",").strip()
    if overrides_raw:
        for part in overrides_raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ValueError(f"Invalid --per_reaction_overrides entry (expected RT=N): {part!r}")
            rt, n = part.split("=", 1)
            rt = rt.strip()
            n = n.strip()
            if not rt or not n:
                raise ValueError(f"Invalid --per_reaction_overrides entry (expected RT=N): {part!r}")
            overrides[rt] = int(n)

    by_rt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts_in = Counter()

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            meta = obj.get("meta") or {}
            rt = str(meta.get("reaction_type") or "").strip()
            if not rt:
                continue
            counts_in[rt] += 1
            if rt in wanted_rts:
                by_rt[rt].append(obj)

    selected: list[dict[str, Any]] = []
    counts_out = Counter()
    co2rr_task_counts_out: Counter[str] = Counter()

    for rt in wanted_rts:
        pool = by_rt.get(rt) or []
        rt_target = overrides.get(rt, per_reaction)
        if rt == "CO2RR":
            # CO2RR: ensure the two tasks are sampled equally often by sampling per *record id*
            # (each record contributes exactly 2 samples: task1 + task2).
            if args.co2rr_per_task is not None:
                n_ids_needed = int(args.co2rr_per_task)
                if n_ids_needed <= 0:
                    raise ValueError("--co2rr_per_task must be > 0")
            else:
                if rt_target % 2 != 0:
                    raise ValueError(
                        "--per_reaction must be even when including CO2RR (two tasks per record), "
                        "or pass --co2rr_per_task to specify per-task count."
                    )
                n_ids_needed = rt_target // 2

            # Group CO2RR samples by record id and keep only complete pairs.
            saw_any_task_type = False
            task_type_counts: Counter[str] = Counter()
            by_id: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
            for obj in pool:
                meta = obj.get("meta") or {}
                rid = meta.get("id")
                task_type = str(meta.get("task_type") or "").strip()
                if task_type:
                    saw_any_task_type = True
                    task_type_counts[task_type] += 1
                if rid is None or not task_type:
                    continue
                by_id[str(rid)][task_type] = obj

            task_a = "co2rr_top_product"
            task_b = "co2rr_partial_current_density"
            valid_ids = [rid for rid, tasks in by_id.items() if task_a in tasks and task_b in tasks]

            if not saw_any_task_type:
                raise ValueError(
                    "CO2RR sampling requires per-sample meta.task_type to form record-id pairs "
                    f"({task_a} + {task_b}), but no meta.task_type was found in the CO2RR pool. "
                    "This usually means you are sampling from an older dataset file (e.g., v2). "
                    "Use a dataset that includes CO2RR task pairs (v3+ recommended; v5 default), "
                    "or exclude CO2RR from --reactions."
                )

            if len(valid_ids) < n_ids_needed:
                raise ValueError(
                    f"Not enough CO2RR record pairs: have {len(valid_ids)}, need {n_ids_needed} "
                    f"(requested per-task count). task_type_counts={dict(task_type_counts)}. "
                    f"Input counts: {dict(counts_in)}"
                )

            # Stable ordering for deterministic sampling.
            def _rid_sort_key(rid: str) -> tuple[int, str]:
                try:
                    return (int(rid), rid)
                except Exception:
                    return (10**18, rid)

            valid_ids = sorted(valid_ids, key=_rid_sort_key)

            rt_seed = (int(args.seed) & 0xFFFFFFFF) ^ zlib.crc32(rt.encode("utf-8"))
            rng = random.Random(rt_seed)
            chosen_ids = rng.sample(valid_ids, n_ids_needed)

            # Always include both tasks for each chosen id.
            for rid in chosen_ids:
                selected.append(by_id[rid][task_a])
                selected.append(by_id[rid][task_b])
                co2rr_task_counts_out[task_a] += 1
                co2rr_task_counts_out[task_b] += 1
            counts_out[rt] = len(chosen_ids) * 2
        else:
            if len(pool) < rt_target:
                raise ValueError(
                    f"Not enough samples for reaction_type={rt}: have {len(pool)}, need {rt_target}. "
                    f"(Input counts: {dict(counts_in)})"
                )
            pool = sorted(pool, key=_sort_key)

            # Derive a stable per-reaction RNG seed (avoid Python's randomized hash()).
            rt_seed = (int(args.seed) & 0xFFFFFFFF) ^ zlib.crc32(rt.encode("utf-8"))
            rng = random.Random(rt_seed)
            chosen = rng.sample(pool, rt_target)
            selected.extend(chosen)
            counts_out[rt] = len(chosen)

    if args.shuffle_output:
        rng = random.Random(int(args.seed))
        rng.shuffle(selected)

    # Optional compatibility upgrade: enrich CO2RR top-product task with truth FE.
    selected = [_upgrade_co2rr_top_product_sample_to_include_fe(obj) for obj in selected]

    with output_file.open("w", encoding="utf-8") as out:
        for obj in selected:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"Wrote {len(selected)} samples to: {output_file}")
    print("Counts by reaction_type (input):")
    for rt, c in sorted(counts_in.items()):
        print(f"- {rt}: {c}")
    print("Counts by reaction_type (output):")
    for rt, c in sorted(counts_out.items()):
        print(f"- {rt}: {c}")
    if co2rr_task_counts_out:
        print("Counts by CO2RR task_type (output):")
        for tt, c in sorted(co2rr_task_counts_out.items()):
            print(f"- {tt}: {c}")


if __name__ == "__main__":
    main()
