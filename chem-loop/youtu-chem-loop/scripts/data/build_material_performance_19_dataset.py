#!/usr/bin/env python3
"""Build canonical and GRPO-ready datasets for 19 material directions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

YOUTU_ROOT = Path(__file__).resolve().parents[2]
CHEM_LOOP_ROOT = YOUTU_ROOT.parent
PROJECT_ROOT = CHEM_LOOP_ROOT.parent
sys.path.insert(0, str(YOUTU_ROOT))

from utu.data_processing.material_performance_candidates import (  # noqa: E402
    iter_material_performance_candidates,
    select_candidates,
)
from utu.data_processing.material_performance_dataset import (  # noqa: E402
    build_dataset,
    write_dataset_outputs,
    write_jsonl,
)


def main() -> None:
    raw_root = YOUTU_ROOT / "data" / "raw" / "material_performance_20260728"
    output_root = YOUTU_ROOT / "data" / "processed" / "material_performance_19"
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
        "--canonical-output",
        type=Path,
        default=output_root / "material_performance_19_v1.jsonl",
    )
    parser.add_argument(
        "--grpo-output",
        type=Path,
        default=output_root / "material_performance_19_grpo_v1.jsonl",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=output_root / "manifest_v1.json",
    )
    parser.add_argument(
        "--excluded-output",
        type=Path,
        default=output_root / "excluded_observations_v1.jsonl",
    )
    args = parser.parse_args()

    candidates = list(
        iter_material_performance_candidates(
            established_source_dir=args.established_source_dir.resolve(),
            new_source_dir=args.new_source_dir.resolve(),
            reaction_dataset=args.reaction_dataset.resolve(),
            material_truth=args.material_truth.resolve(),
        )
    )
    selection = select_candidates(candidates)
    result = build_dataset(selection.selected, selection.stats)
    write_dataset_outputs(
        result,
        canonical_path=args.canonical_output.resolve(),
        grpo_path=args.grpo_output.resolve(),
        manifest_path=args.manifest_output.resolve(),
    )

    excluded_records = []
    for candidate, reason in selection.excluded:
        excluded_records.append(
            {
                "exclusion_reason": reason,
                "task_type": candidate.task_type,
                "doi": candidate.doi,
                "material_name": candidate.material_name,
                "status": candidate.status,
                "binding_mode": candidate.binding_mode,
                "quality_flags": list(candidate.quality_flags),
                "source_file": candidate.source_file,
                "row_number": candidate.row_number,
                "extraction_index": candidate.extraction_index,
                "context_key": candidate.context_key,
                "label_key": candidate.label_key,
            }
        )
    write_jsonl(args.excluded_output.resolve(), excluded_records)

    print(json.dumps(result.manifest["selection"], ensure_ascii=False, sort_keys=True))
    print(json.dumps(result.manifest["outputs"], ensure_ascii=False, sort_keys=True))
    print(f"canonical_output={args.canonical_output.resolve()}")
    print(f"grpo_output={args.grpo_output.resolve()}")
    print(f"manifest_output={args.manifest_output.resolve()}")
    print(f"excluded_output={args.excluded_output.resolve()}")


if __name__ == "__main__":
    main()
