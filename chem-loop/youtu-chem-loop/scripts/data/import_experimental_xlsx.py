#!/usr/bin/env python3
"""Convert a lab experimental XLSX (wide table) into an experimental-record CSV (long table).

Why this exists
---------------
We keep the closed-loop ingestion pipeline CSV-based (see `import_experimental_csv.py`),
but lab data often arrives as an Excel sheet. To avoid adding heavyweight dependencies
(`openpyxl`) and keep the repo easy to run offline, this script parses XLSX using only
the Python standard library (XLSX is a ZIP of XML files).

Current supported input (project convention)
-------------------------------------------
The sheet is expected to look like:

  col1: experiment_id   (e.g. "1-5-1")
  col2: metals          (e.g. "Ni(69.00%), Co(19.07%), ...")
  col3+: reaction columns (e.g. OER / HER / UOR...) where each cell may contain:
        - two groups: "405 mV,333 mV" / "1.504V，1.134V"
        - missing placeholders: "无" / "无，543mV"

We choose the *better* value per reaction column independently (user rule A):
  - OER/HER/UOR: smaller is better

Output CSV schema (compatible with `import_experimental_csv.py`)
---------------------------------------------------------------
Columns written:
  id, reaction_type, metals, value, unit, condition

Notes:
- This script does NOT normalize/validate units; that is handled by `process_raw_record`
  during CSV->processed conversion.
- Metals strings are kept as-is; downstream parsing will extract symbols and composition_pct.
"""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


_XML_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_to_index(col: str) -> int:
    """A -> 1, B -> 2, ..., Z -> 26, AA -> 27 ..."""
    n = 0
    for ch in col:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - ord("A") + 1)
    return n


def _cell_ref_to_rc(ref: str) -> tuple[int, int] | None:
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref or "")
    if not m:
        return None
    col, row = m.group(1), int(m.group(2))
    return row, _col_to_index(col)


def _read_shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        data = z.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    out: list[str] = []
    for si in root.findall("s:si", _XML_NS):
        # A shared string can contain multiple <t> nodes.
        texts = [t.text or "" for t in si.findall(".//s:t", _XML_NS)]
        out.append("".join(texts))
    return out


def _read_sheet_rows_xlsx(path: Path, *, sheet_index: int = 1) -> list[list[str]]:
    """Read an XLSX worksheet into a 2D array of strings.

    We default to sheet_index=1 -> xl/worksheets/sheet1.xml (the common case).
    """
    with zipfile.ZipFile(path, "r") as z:
        shared = _read_shared_strings(z)

        sheet_fp = f"xl/worksheets/sheet{int(sheet_index)}.xml"
        sheet = ET.fromstring(z.read(sheet_fp))

        cells: dict[tuple[int, int], str] = {}
        max_r = 0
        max_c = 0
        for c in sheet.findall(".//s:c", _XML_NS):
            ref = c.get("r")
            if not ref:
                continue
            rc = _cell_ref_to_rc(ref)
            if not rc:
                continue
            r, col = rc
            max_r = max(max_r, r)
            max_c = max(max_c, col)

            v_el = c.find("s:v", _XML_NS)
            if v_el is None:
                continue
            v = v_el.text or ""
            if c.get("t") == "s":
                try:
                    v = shared[int(v)]
                except Exception:
                    pass
            cells[(r, col)] = str(v)

    rows: list[list[str]] = []
    for r in range(1, max_r + 1):
        row = [cells.get((r, c), "") for c in range(1, max_c + 1)]
        # Trim trailing empty cells to keep output tidy.
        while row and not str(row[-1]).strip():
            row.pop()
        rows.append(row)
    return rows


@dataclass(frozen=True)
class ParsedValue:
    value: float
    unit: str  # canonical unit ("mV" or "V")


def _normalize_sep(s: str) -> str:
    s = str(s or "").strip()
    # Chinese punctuation -> ASCII
    s = s.replace("，", ",").replace("；", ",").replace(";", ",")
    # Fix a common typo in the provided sheet: "无.1.5V"
    s = s.replace("无.", "无,")
    # Remove whitespace (values like "537 mV " are common)
    s = "".join(s.split())
    return s


def _parse_multi_value_cell(
    text: Any,
    *,
    canonical_unit: str,
) -> list[ParsedValue]:
    """Parse a cell that may contain multiple values and units.

    Returns values converted into canonical_unit (either "mV" or "V").
    """
    s0 = _normalize_sep(text)
    if not s0:
        return []

    parts = [p.strip() for p in s0.split(",") if p.strip()]
    if not parts:
        return []

    # First pass: parse number + (optional) unit.
    raw: list[tuple[float, Optional[str]]] = []
    explicit_units: list[str] = []
    for p in parts:
        if p in {"无", "-", "nan", "NaN", "N/A", "NA"}:
            continue
        m = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))([A-Za-z]+)?", p)
        if not m:
            continue
        num = float(m.group(1))
        unit = (m.group(2) or "").strip()
        unit_norm = unit.lower()
        if unit_norm in {"mv", "v"}:
            explicit_units.append(unit_norm)
            raw.append((num, unit_norm))
        else:
            raw.append((num, None))

    if not raw:
        return []

    # If any part had an explicit unit, use it as the default for missing ones.
    default_u = explicit_units[0] if explicit_units else canonical_unit.lower()

    out: list[ParsedValue] = []
    for num, u in raw:
        u = u or default_u
        if canonical_unit.lower() == "mv":
            if u == "v":
                out.append(ParsedValue(value=num * 1000.0, unit="mV"))
            else:
                out.append(ParsedValue(value=num, unit="mV"))
        else:
            # canonical V
            if u == "mv":
                out.append(ParsedValue(value=num / 1000.0, unit="V"))
            else:
                out.append(ParsedValue(value=num, unit="V"))

    return out


def _reaction_from_header(header: str) -> str | None:
    h = str(header or "").strip()
    if not h:
        return None
    up = h.upper()
    if "OER" in up:
        return "OER"
    if "HER" in up:
        return "HER"
    if "UOR" in up:
        return "UOR"
    return None


def _canonical_unit_for_reaction(rt: str) -> str:
    rt = (rt or "").strip().upper()
    if rt in {"OER", "HER"}:
        return "mV"
    if rt == "UOR":
        return "V"
    # Default fallback (should not happen for the current sheet).
    return "mV"


def _sanitize_tag(tag: str) -> str:
    s = str(tag or "").strip()
    if not s:
        return "lab"
    # Keep only ASCII letters/digits/underscore.
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "lab"


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert experimental XLSX to experimental CSV (long table).")
    ap.add_argument("--xlsx_path", required=True, help="Path to the lab XLSX file.")
    ap.add_argument(
        "--output_dir",
        default="data/experimental",
        help="Output directory for CSV (relative to youtu-chem-loop repo root).",
    )
    ap.add_argument("--date", default=None, help="DATE in YYYYMMDD (default: today in local time).")
    ap.add_argument(
        "--tag",
        default="lab_metal_ratio",
        help="Short tag for this batch (letters/digits/_). Default: lab_metal_ratio.",
    )
    ap.add_argument(
        "--condition",
        default="10 mA cm-2",
        help='Condition text to write into the CSV "condition" column (default: 10 mA cm-2).',
    )
    ap.add_argument(
        "--sheet_index",
        type=int,
        default=1,
        help="Which sheetN.xml to read (1-based). Default: 1 (sheet1.xml).",
    )
    ap.add_argument("--dry_run", action="store_true", help="Parse and print a summary, but do not write CSV.")
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Only print machine-parsable key lines (DATASET_NAME/OUTPUT_CSV/RECORDS).",
    )
    args = ap.parse_args()

    xlsx_path = Path(args.xlsx_path).expanduser().resolve()
    if not xlsx_path.exists():
        raise SystemExit(f"XLSX not found: {xlsx_path}")

    # DATE default (local).
    if args.date:
        date = str(args.date).strip()
    else:
        from datetime import datetime

        date = datetime.now().strftime("%Y%m%d")

    tag = _sanitize_tag(str(args.tag))

    rows = _read_sheet_rows_xlsx(xlsx_path, sheet_index=int(args.sheet_index))
    if not rows or len(rows) < 3:
        raise SystemExit(f"XLSX has too few rows (need header+data): {xlsx_path}")

    header = rows[0]
    # Map column index -> reaction type.
    col_rt: dict[int, str] = {}
    for j, h in enumerate(header, start=1):
        rt = _reaction_from_header(h)
        if rt:
            col_rt[j] = rt

    if not col_rt:
        raise SystemExit(f"Failed to detect reaction columns from header row: {header}")

    # Data rows start at row 3 (1-based) -> rows[2:].
    out_rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    skipped_missing_id = 0
    skipped_missing_metals = 0
    skipped_missing_value = 0

    for r in rows[2:]:
        exp_id = str(r[0]).strip() if len(r) >= 1 else ""
        metals = str(r[1]).strip() if len(r) >= 2 else ""
        if not exp_id:
            skipped_missing_id += 1
            continue
        if not metals:
            skipped_missing_metals += 1
            continue

        for col_idx, rt in col_rt.items():
            cell = r[col_idx - 1] if len(r) >= col_idx else ""
            canonical_unit = _canonical_unit_for_reaction(rt)
            parsed = _parse_multi_value_cell(cell, canonical_unit=canonical_unit)
            if not parsed:
                skipped_missing_value += 1
                continue

            # Smaller is better (per user rule for this batch).
            best = min(parsed, key=lambda x: x.value)

            out_rows.append(
                {
                    "id": f"{exp_id}_{rt}",
                    "reaction_type": rt,
                    "metals": metals,
                    "value": f"{best.value:g}",
                    "unit": best.unit,
                    "condition": str(args.condition),
                }
            )
            counts[rt] = counts.get(rt, 0) + 1

    if not out_rows:
        raise SystemExit("No experimental records produced (all rows missing values?)")

    dataset_name = f"chem_performance_exp_{date}_{tag}_{len(out_rows)}"
    output_dir = Path(args.output_dir)
    # Interpret output_dir relative to youtu-chem-loop repo root (cwd).
    output_dir.mkdir(parents=True, exist_ok=True)
    out_csv = (output_dir / f"{dataset_name}__records.csv").resolve()

    if not args.quiet:
        print(f"[xlsx] xlsx_path={xlsx_path}")
        print(f"[xlsx] detected_reaction_columns={col_rt}")
        print(f"[xlsx] produced_records={len(out_rows)} per_reaction={counts}")
        if skipped_missing_id:
            print(f"[xlsx] skipped_missing_id={skipped_missing_id}")
        if skipped_missing_metals:
            print(f"[xlsx] skipped_missing_metals={skipped_missing_metals}")
        if skipped_missing_value:
            print(f"[xlsx] skipped_missing_value_cells={skipped_missing_value}")

    if args.dry_run:
        print("[xlsx] dry_run=1 (no files written)")
    else:
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["id", "reaction_type", "metals", "value", "unit", "condition"],
            )
            w.writeheader()
            w.writerows(out_rows)
        if not args.quiet:
            print(f"[xlsx] wrote_csv={out_csv}")

    # Machine-parsable output (used by bash wrappers).
    print(f"DATASET_NAME={dataset_name}")
    print(f"OUTPUT_CSV={out_csv}")
    print(f"RECORDS={len(out_rows)}")


if __name__ == "__main__":
    main()

