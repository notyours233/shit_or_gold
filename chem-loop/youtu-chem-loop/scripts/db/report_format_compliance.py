#!/usr/bin/env python3
"""Report structured-output / format compliance for chem-performance rollouts.

This script analyzes persisted rows in the SQLite table `evaluation_data` and measures:
  - whether an answer object can be extracted
  - whether predicted keys exactly match ground-truth keys
  - whether values are strict numbers-only (no units/strings)
  - whether values become evaluable after the verifier's best-effort unit repair pass

It is designed to support the project goal:
  - achieve 80–90%+ "evaluable structured output" rate before running large GRPO sweeps.

Typical workflow:
  1) Run a small GRPO/eval job (produces evaluation_data rows with exp_id=<...>_epoch_0)
  2) Run this report on that exp_id to see compliance metrics.

Example:
  cd project/chem-loop/youtu-chem-loop
  SQLITE_TMPDIR=/tmp TMPDIR=/tmp python3 scripts/db/report_format_compliance.py \
    --db test.db --exp_id mad_smoke_epoch_0 --stage judged
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


_TAG_RE_TEMPLATE = r"<{tag}>\s*(.*?)\s*</{tag}>"


def _extract_tag(text: str, tag: str) -> str | None:
    m = re.search(_TAG_RE_TEMPLATE.format(tag=re.escape(tag)), text or "", flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


def _safe_json_loads(s: Any) -> Any:
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_answer_object_fallback(response_text: str) -> dict[str, Any] | None:
    # Prefer <answer>...</answer>.
    answer_txt = _extract_tag(response_text or "", "answer")
    if answer_txt:
        try:
            obj = json.loads(answer_txt)
        except Exception:
            obj = None
        if isinstance(obj, dict) and obj:
            return obj

    # Fall back to structured JSON in the full text.
    s = (response_text or "").strip()
    if s.startswith("{"):
        try:
            obj2 = json.loads(s)
        except Exception:
            obj2 = None
        if isinstance(obj2, dict) and obj2:
            if isinstance(obj2.get("answer"), dict) and obj2.get("answer"):
                return obj2["answer"]
            return obj2
    return None


def _is_number(x: Any) -> bool:
    # bool is a subclass of int in Python; disallow it.
    return isinstance(x, (int, float)) and not isinstance(x, bool)


_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def _parse_fe_fraction(value: Any) -> float | None:
    """Parse Faradaic efficiency into a fraction in [0, 1]."""
    if isinstance(value, bool) or value is None:
        return None
    num: float
    rest = ""
    if isinstance(value, (int, float)):
        num = float(value)
        if not math.isfinite(num):
            return None
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        m = _NUM_PREFIX_RE.match(s)
        if not m:
            return None
        try:
            num = float(m.group("num"))
        except Exception:
            return None
        if not math.isfinite(num):
            return None
        rest = s[m.end() :]
    else:
        return None

    # Accept percent forms ("94%") and bare percent-like values (94 -> 0.94).
    if "%" in rest or (num > 1.0 and num <= 100.0):
        num = num / 100.0

    if num < 0.0 or num > 1.0:
        return None
    return num


@dataclass(frozen=True)
class Row:
    id: int
    response: str
    correct_answer: str
    meta_raw: str | None

    @property
    def meta(self) -> dict[str, Any]:
        obj = _safe_json_loads(self.meta_raw)
        return obj if isinstance(obj, dict) else {}

    @property
    def reaction_type(self) -> str | None:
        rt = self.meta.get("reaction_type")
        return str(rt).strip() if isinstance(rt, str) and rt.strip() else None

    @property
    def units(self) -> dict[str, str] | None:
        u = self.meta.get("units")
        if not isinstance(u, dict) or not u:
            return None
        out: dict[str, str] = {}
        for k, v in u.items():
            if not isinstance(k, str) or not k.strip():
                continue
            if v is None:
                continue
            out[str(k)] = str(v)
        return out or None

    @property
    def has_think(self) -> bool:
        return _extract_tag(self.response or "", "think") is not None


def _iter_rows(con: sqlite3.Connection, *, exp_id: str, stage: str, limit: int | None) -> list[Row]:
    cur = con.cursor()
    limit_sql = ""
    params: list[Any] = [exp_id, stage]
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))
    cur.execute(
        "SELECT id, response, correct_answer, meta FROM evaluation_data "
        "WHERE exp_id=? AND stage=? "
        "ORDER BY id ASC" + limit_sql,
        tuple(params),
    )
    out: list[Row] = []
    for rid, response, correct_answer, meta_raw in cur.fetchall():
        out.append(
            Row(
                id=int(rid),
                response=str(response or ""),
                correct_answer=str(correct_answer or ""),
                meta_raw=str(meta_raw) if meta_raw is not None else None,
            )
        )
    return out


def _is_co2rr_product_task(gt_raw: Any) -> bool:
    if not isinstance(gt_raw, dict):
        return False
    if not isinstance(gt_raw.get("product"), str):
        return False
    keys = {str(k) for k in gt_raw.keys()}
    return keys in ({"product"}, {"product", "faradaic_efficiency"})


def _extract_answer_object(response_text: str) -> dict[str, Any] | None:
    # Prefer the canonical parser if available, but keep a fallback for portability.
    try:
        from utu.practice.verify.chem_performance_lib.answer_parser import (  # type: ignore
            extract_structured_answer_object,
        )

        obj = extract_structured_answer_object(response_text or "")
        return obj if isinstance(obj, dict) and obj else None
    except Exception:
        return _extract_answer_object_fallback(response_text or "")


def _parse_numbers_with_repair(response_text: str, *, expected_units: dict[str, str] | None) -> dict[str, float] | None:
    try:
        from utu.practice.verify.chem_performance_lib.answer_parser import (  # type: ignore
            parse_answer_numbers,
        )

        return parse_answer_numbers(response_text or "", expected_units=expected_units)
    except Exception:
        return None


def _format_pct(n: int, d: int) -> str:
    if d <= 0:
        return "-"
    return f"{(n / d) * 100:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="test.db", help="SQLite db file path (default: test.db)")
    ap.add_argument("--exp_id", required=True, help="Experiment id (e.g., mad_smoke_epoch_0)")
    ap.add_argument("--stage", default="judged", help="Stage to analyze (default: judged)")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of rows (debug)")
    ap.add_argument("--out_json", default=None, help="Write the summary JSON to this file")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    rows = _iter_rows(con, exp_id=str(args.exp_id), stage=str(args.stage), limit=args.limit)
    if not rows:
        raise SystemExit(f"No rows found for exp_id={args.exp_id!r} stage={args.stage!r}")

    # Overall counters
    totals: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    by_rt: dict[str, Counter[str]] = defaultdict(Counter)

    # Detailed metrics are computed for regression tasks; product tasks are tracked separately.
    for r in rows:
        totals["rows_total"] += 1
        if r.has_think:
            totals["has_think"] += 1

        gt_raw = _safe_json_loads(r.correct_answer)
        if gt_raw is None:
            totals["gt_parse_failed"] += 1
            reasons["gt_parse_failed"] += 1
            continue

        rt = r.reaction_type or "UNKNOWN"
        rt_counter = by_rt[rt]

        pred_obj = _extract_answer_object(r.response)
        if pred_obj is None:
            totals["pred_answer_missing"] += 1
            reasons["pred_answer_missing"] += 1
            rt_counter["pred_answer_missing"] += 1
            continue

        # CO2RR product classification task (string-valued).
        if _is_co2rr_product_task(gt_raw):
            totals["task_product"] += 1
            rt_counter["task_product"] += 1

            gt_keys = {str(k) for k in gt_raw.keys()} if isinstance(gt_raw, dict) else set()
            pred_keys = {str(k) for k in pred_obj.keys()}

            # Old: {"product"}; New: {"product","faradaic_efficiency"}.
            wants_fe = gt_keys == {"product", "faradaic_efficiency"}
            if wants_fe:
                if pred_keys != {"product", "faradaic_efficiency"}:
                    totals["product_keys_bad"] += 1
                    reasons["product_keys_bad"] += 1
                    rt_counter["product_keys_bad"] += 1
                    continue
            else:
                # Backward-compat: allow FE to be present even when GT is product-only.
                if pred_keys not in ({"product"}, {"product", "faradaic_efficiency"}):
                    totals["product_keys_bad"] += 1
                    reasons["product_keys_bad"] += 1
                    rt_counter["product_keys_bad"] += 1
                    continue

            if not isinstance(pred_obj.get("product"), str) or not str(pred_obj.get("product")).strip():
                totals["product_value_bad"] += 1
                reasons["product_value_bad"] += 1
                rt_counter["product_value_bad"] += 1
                continue

            if wants_fe:
                fe = _parse_fe_fraction(pred_obj.get("faradaic_efficiency"))
                if fe is None:
                    totals["product_fe_value_bad"] += 1
                    reasons["product_fe_value_bad"] += 1
                    rt_counter["product_fe_value_bad"] += 1
                    continue
                totals["task_product_fe"] += 1
                rt_counter["task_product_fe"] += 1
                totals["product_fe_structured_ok"] += 1
                rt_counter["product_fe_structured_ok"] += 1

            totals["product_structured_ok"] += 1
            rt_counter["product_structured_ok"] += 1
            continue

        # Regression-style tasks (numbers-only with optional unit repair).
        totals["task_regression"] += 1
        rt_counter["task_regression"] += 1

        if not isinstance(gt_raw, dict) or not gt_raw:
            totals["gt_not_dict"] += 1
            reasons["gt_not_dict"] += 1
            rt_counter["gt_not_dict"] += 1
            continue

        gt_keys = {str(k) for k in gt_raw.keys()}
        pred_keys = {str(k) for k in pred_obj.keys()}

        extra = pred_keys - gt_keys
        missing = gt_keys - pred_keys

        if extra:
            totals["extra_keys"] += 1
            reasons["extra_keys"] += 1
            rt_counter["extra_keys"] += 1
            continue
        if missing:
            totals["missing_keys"] += 1
            reasons["missing_keys"] += 1
            rt_counter["missing_keys"] += 1
            continue

        # Keys align exactly.
        totals["keys_exact"] += 1
        rt_counter["keys_exact"] += 1

        # Strict numbers-only check (JSON types).
        strict_numbers = True
        for v in pred_obj.values():
            if not _is_number(v):
                strict_numbers = False
                break
        if strict_numbers:
            totals["strict_numbers_only_ok"] += 1
            rt_counter["strict_numbers_only_ok"] += 1
            continue

        # Best-effort repair (must match expected units).
        repaired = _parse_numbers_with_repair(r.response, expected_units=r.units)
        if repaired is not None:
            totals["repaired_numbers_ok"] += 1
            rt_counter["repaired_numbers_ok"] += 1
            continue

        totals["non_numeric_unrepaired"] += 1
        reasons["non_numeric_unrepaired"] += 1
        rt_counter["non_numeric_unrepaired"] += 1

    # -------------------------
    # Print summary (human)
    # -------------------------
    n_total = int(totals["rows_total"])
    n_reg = int(totals["task_regression"])
    n_prod = int(totals["task_product"])
    n_prod_fe = int(totals["task_product_fe"])

    keys_exact = int(totals["keys_exact"])
    strict_ok = int(totals["strict_numbers_only_ok"])
    repaired_ok = int(totals["repaired_numbers_ok"])
    after_repair_ok = strict_ok + repaired_ok

    has_think = int(totals["has_think"])

    print("== ChemCouncil Format Compliance Report ==")
    print(f"- exp_id: {args.exp_id}")
    print(f"- stage:  {args.stage}")
    print(f"- rows:   {n_total}")
    print()

    print("Overall:")
    print(f"- has_think: {has_think}/{n_total} ({_format_pct(has_think, n_total)})")
    print()

    print("Regression tasks (numbers-only):")
    print(f"- rows: {n_reg}")
    if n_reg > 0:
        print(f"- keys_exact: {keys_exact}/{n_reg} ({_format_pct(keys_exact, n_reg)})")
        print(f"- strict_numbers_only_ok: {strict_ok}/{n_reg} ({_format_pct(strict_ok, n_reg)})")
        print(f"- repaired_numbers_ok: {repaired_ok}/{n_reg} ({_format_pct(repaired_ok, n_reg)})")
        print(f"- evaluable_after_repair: {after_repair_ok}/{n_reg} ({_format_pct(after_repair_ok, n_reg)})")
    print()

    print("CO2RR product tasks (classification):")
    print(f"- rows: {n_prod}")
    if n_prod > 0:
        ok_prod = int(totals["product_structured_ok"])
        print(f"- structured_ok: {ok_prod}/{n_prod} ({_format_pct(ok_prod, n_prod)})")
        if n_prod_fe > 0:
            ok_prod_fe = int(totals["product_fe_structured_ok"])
            print(f"- product+FE structured_ok: {ok_prod_fe}/{n_prod_fe} ({_format_pct(ok_prod_fe, n_prod_fe)})")
    print()

    if reasons:
        print("Top failure reasons:")
        for name, cnt in reasons.most_common(10):
            print(f"- {name}: {cnt}")
        print()

    # Per reaction type table (small; keep stable ordering).
    if by_rt:
        print("By reaction_type (regression only):")
        rts_sorted = sorted(by_rt.keys())
        hdr = ["reaction_type", "rows", "keys_exact", "strict_ok", "repaired_ok", "after_repair_ok"]
        print(" | ".join(hdr))
        print(" | ".join(["---"] * len(hdr)))
        for rt in rts_sorted:
            c = by_rt[rt]
            rt_rows = int(c["task_regression"])
            if rt_rows <= 0:
                continue
            rt_keys = int(c["keys_exact"])
            rt_strict = int(c["strict_numbers_only_ok"])
            rt_repaired = int(c["repaired_numbers_ok"])
            rt_after = rt_strict + rt_repaired
            print(
                " | ".join(
                    [
                        rt,
                        str(rt_rows),
                        f"{rt_keys} ({_format_pct(rt_keys, rt_rows)})",
                        f"{rt_strict} ({_format_pct(rt_strict, rt_rows)})",
                        f"{rt_repaired} ({_format_pct(rt_repaired, rt_rows)})",
                        f"{rt_after} ({_format_pct(rt_after, rt_rows)})",
                    ]
                )
            )
        print()

    # -------------------------
    # Write JSON summary (machine)
    # -------------------------
    if args.out_json:
        out = {
            "exp_id": str(args.exp_id),
            "stage": str(args.stage),
            "totals": dict(totals),
            "reasons": dict(reasons),
            "by_reaction_type": {k: dict(v) for k, v in by_rt.items()},
            "metrics": {
                "rows_total": n_total,
                "rows_regression": n_reg,
                "rows_product": n_prod,
                "keys_exact_rate": (keys_exact / n_reg) if n_reg else None,
                "strict_numbers_only_rate": (strict_ok / n_reg) if n_reg else None,
                "evaluable_after_repair_rate": (after_repair_ok / n_reg) if n_reg else None,
            },
        }
        with open(str(args.out_json), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(f"Wrote JSON summary: {args.out_json}")


if __name__ == "__main__":
    main()
