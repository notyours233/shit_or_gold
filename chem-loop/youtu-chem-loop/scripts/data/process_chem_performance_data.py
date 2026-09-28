#!/usr/bin/env python3
"""Process raw chem-performance JSONL into cleaned/normalized records.

Input:
  data/*.jsonl

Output:
  data/processed/chem_performance/*.jsonl

This script is intentionally offline and does not touch the DB. It prepares
processed records that are later turned into DatasetSample rows for upload.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from utu.data_processing.chem_performance.processor import process_directory


def _repo_root() -> Path:
    # scripts/data/<this_file>.py -> scripts -> <repo_root>
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Process chem-performance JSONL files into normalized records.")
    parser.add_argument(
        "--input_dir",
        type=str,
        default=str(_repo_root() / "data"),
        help="Directory containing raw extracted JSONL files (default: <repo_root>/data).",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(_repo_root() / "data" / "processed" / "chem_performance"),
        help="Directory to write processed JSONL files.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    results = process_directory(input_dir=input_dir, output_dir=output_dir)

    # Print a compact summary for manual verification.
    print(f"Processed {len(results)} files.")
    for fn, st in results.items():
        print(
            f"- {fn}: total={st.total_records} kept={st.kept_records} dropped={st.dropped_records} "
            f"(V->mV={st.conversions_v_to_mv}, mV->V={st.conversions_mv_to_v}, "
            f"A->mA={st.conversions_a_to_ma}, mA->A={st.conversions_ma_to_a}, "
            f"%->fraction={st.conversions_percent_to_fraction})"
        )
        if st.dropped_records_by_reason:
            print(f"  dropped_records_by_reason={st.dropped_records_by_reason}")
        if st.dropped_metrics_by_reason:
            print(f"  dropped_metrics_by_reason={st.dropped_metrics_by_reason}")


if __name__ == "__main__":
    main()
