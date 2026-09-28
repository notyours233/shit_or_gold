#!/usr/bin/env python3
"""Import manually curated HOR exchange current density rows from a CSV.

This script merges `data/HOR.csv` into the raw JSONL extraction file `data/hor.jsonl`
so the standard chem-performance processing pipeline can pick them up:

  data/hor.jsonl  -> scripts/data/process_chem_performance_data.py
                  -> data/processed/chem_performance/hor.jsonl
                  -> scripts/data/build_chem_performance_dataset.py

We keep this script stdlib-only for portability.
"""

from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    # scripts/data/<this_file>.py -> scripts -> repo root
    return Path(__file__).resolve().parents[2]


def _decimal_to_str(value: Decimal) -> str:
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s


def _normalize_metal_symbol(symbol: str) -> str:
    s = (symbol or "").strip()
    if not s:
        return ""
    if len(s) == 1:
        return s.upper()
    return s[0].upper() + s[1:].lower()


def _parse_metals(metals_text: str) -> list[str]:
    parts = [p.strip() for p in (metals_text or "").split("+") if p.strip()]
    metals = [_normalize_metal_symbol(p) for p in parts]
    metals = [m for m in metals if m]
    return sorted(set(metals))


def _parse_decimal(x: Any) -> Decimal:
    if x is None:
        raise InvalidOperation("empty")
    if isinstance(x, (int, float)):
        return Decimal(str(x))
    s = str(x).strip()
    if not s:
        raise InvalidOperation("empty")
    return Decimal(s)


def _load_jsonl_by_id(path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return (rows_in_order, id->index_in_rows)."""
    rows: list[dict[str, Any]] = []
    idx: dict[str, int] = {}
    if not path.exists():
        return rows, idx
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rid = str(obj.get("id") or "").strip()
            if not rid:
                # Keep the row but don't index it.
                rows.append(obj)
                continue
            idx[rid] = len(rows)
            rows.append(obj)
    return rows, idx


def _build_hor_record_from_csv_row(row: dict[str, str]) -> dict[str, Any]:
    rid = str(row.get("id") or "").strip()
    if not rid:
        raise ValueError("CSV row missing id")

    metals = _parse_metals(row.get("metals") or "")
    if not metals:
        raise ValueError(f"CSV row id={rid} has empty metals")

    # Use the numeric column as the source of truth (cleaned by manual curation).
    j0 = _parse_decimal(row.get("exchange_current_density_mA_cm-2"))
    j0_str = _decimal_to_str(j0)

    rec: dict[str, Any] = {
        "id": rid,
        "metals": metals,
        "reaction_type": "HOR",
        "exchange_current_density": f"{j0_str} mA cm-2",
        # Keep extra fields for backward-compat with older extractions.
        "overpotential_10mAcm-2": None,
        "overpotential_50mAcm-2": None,
    }

    doi = str(row.get("doi") or "").strip()
    if doi:
        rec["doi"] = doi

    title = str(row.get("title") or "").strip()
    if title:
        rec["title"] = title

    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge curated HOR.csv rows into data/hor.jsonl.")
    ap.add_argument(
        "--csv_path",
        type=str,
        default=str(_repo_root() / "data" / "HOR.csv"),
        help="Path to HOR.csv (manual curation).",
    )
    ap.add_argument(
        "--jsonl_path",
        type=str,
        default=str(_repo_root() / "data" / "hor.jsonl"),
        help="Path to raw hor.jsonl to update in-place.",
    )
    ap.add_argument(
        "--encoding",
        type=str,
        default="gbk",
        help="CSV encoding (default: gbk/cp936).",
    )
    ap.add_argument(
        "--dry_run",
        action="store_true",
        help="If set, do not write files; only print the planned changes.",
    )
    args = ap.parse_args()

    csv_path = Path(args.csv_path)
    jsonl_path = Path(args.jsonl_path)
    encoding = str(args.encoding)

    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    existing_rows, existing_idx = _load_jsonl_by_id(jsonl_path)

    created: list[str] = []
    updated: list[str] = []

    # Build a map of curated rows (id -> record payload).
    curated_by_id: dict[str, dict[str, Any]] = {}
    with csv_path.open("r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            curated_by_id[rid] = _build_hor_record_from_csv_row(row)

    # Update existing rows in-place (preserve ordering of existing file).
    for rid, i in list(existing_idx.items()):
        if rid not in curated_by_id:
            continue
        curated = curated_by_id[rid]
        obj = dict(existing_rows[i])  # shallow copy
        # Overwrite key fields from curated data; keep any extra keys from original.
        obj["metals"] = curated["metals"]
        obj["reaction_type"] = "HOR"
        obj["exchange_current_density"] = curated["exchange_current_density"]
        obj["overpotential_10mAcm-2"] = None
        obj["overpotential_50mAcm-2"] = None
        if "doi" in curated:
            obj["doi"] = curated["doi"]
        if "title" in curated:
            obj["title"] = curated["title"]
        existing_rows[i] = obj
        updated.append(rid)

    # Append missing ids (deterministic order: numeric ids ascending, then the rest).
    def _id_sort_key(rid: str) -> tuple[int, int, str]:
        if rid.isdigit():
            return (0, int(rid), rid)
        return (1, 10**18, rid)

    for rid in sorted(set(curated_by_id.keys()) - set(existing_idx.keys()), key=_id_sort_key):
        existing_rows.append(curated_by_id[rid])
        created.append(rid)

    print(f"[HOR import] jsonl_path={jsonl_path}")
    print(f"[HOR import] csv_path={csv_path} encoding={encoding}")
    print(f"[HOR import] updated_existing={len(updated)} created_new={len(created)}")
    if created:
        print(f"[HOR import] created_ids={created}")
    if updated:
        # Only print a few to keep logs compact.
        print(f"[HOR import] updated_ids_example={updated[:10]}")

    if args.dry_run:
        print("[HOR import] dry_run=1 (no files written)")
        return

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as out:
        for obj in existing_rows:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"[HOR import] wrote {len(existing_rows)} records -> {jsonl_path}")


if __name__ == "__main__":
    main()
