#!/usr/bin/env python3
"""Generate a GRPO-readiness audit for the 19 material-performance directions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

YOUTU_ROOT = Path(__file__).resolve().parents[2]
CHEM_LOOP_ROOT = YOUTU_ROOT.parent
PROJECT_ROOT = CHEM_LOOP_ROOT.parent
sys.path.insert(0, str(YOUTU_ROOT))

from utu.data_processing.material_performance_audit import build_audit, write_audit_outputs  # noqa: E402


def main() -> None:
    raw_root = YOUTU_ROOT / "data" / "raw" / "material_performance_20260728"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--established-source-dir",
        type=Path,
        default=raw_root / "material_categories_full_20260706",
    )
    parser.add_argument("--new-source-dir", type=Path, default=raw_root / "batch3")
    parser.add_argument(
        "--reaction-dataset",
        type=Path,
        default=YOUTU_ROOT / "data" / "processed" / "chem_performance" / "chem_performance_dataset_v2.jsonl",
    )
    parser.add_argument(
        "--material-truth",
        type=Path,
        default=PROJECT_ROOT
        / "material_property_extraction"
        / "results"
        / "final_review_package_20260415"
        / "all_results.jsonl",
    )
    parser.add_argument(
        "--chroma-db",
        type=Path,
        default=CHEM_LOOP_ROOT / "MAD" / "data" / "chroma_db" / "chroma.sqlite3",
    )
    parser.add_argument("--chroma-collection", default="literature_agent2")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=YOUTU_ROOT / "data" / "audits" / "material_performance_20260728",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=CHEM_LOOP_ROOT / "spec-bank" / "material_performance_grpo_readiness_audit_20260728.md",
    )
    args = parser.parse_args()

    audit, review_queue = build_audit(
        established_source_dir=args.established_source_dir.resolve(),
        new_source_dir=args.new_source_dir.resolve(),
        reaction_dataset=args.reaction_dataset.resolve(),
        material_truth=args.material_truth.resolve(),
        chroma_db=args.chroma_db.resolve(),
        chroma_collection=args.chroma_collection,
    )
    write_audit_outputs(audit, review_queue, args.output_dir.resolve(), args.report_path.resolve())

    overall = audit["overall"]
    print(f"candidate_samples={overall['candidate_samples']}")
    print(f"direct_samples={overall['direct_samples']}")
    print(f"recoverable_samples={overall['recoverable_samples']}")
    print(f"manual_review_samples={overall['manual_review_samples']}")
    print(f"deduplicated_trainable_samples={overall['deduplicated_trainable_samples']}")
    print(f"numeric_metric_contract_ready_samples={overall['numeric_metric_contract_ready_samples']}")
    print(f"report={args.report_path.resolve()}")
    print(f"review_queue={args.output_dir.resolve() / 'review_queue.jsonl'}")


if __name__ == "__main__":
    main()
