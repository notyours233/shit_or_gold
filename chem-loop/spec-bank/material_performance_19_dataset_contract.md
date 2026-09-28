# Material Performance 19-Direction Dataset Contract

## Purpose

This contract defines the material-name-centered dataset used to rebuild the
Training-Free GRPO experience database for 19 performance directions.

The minimum usable observation is:

1. a material name that can be bound to exactly one material object;
2. at least one numeric performance truth;
3. a performance direction (`task_type`);
4. a normalized DOI for provenance and Chroma leakage masking.

Precursor, feed ratio, preparation method, element content, components,
structure relationships, elements, and test conditions are optional. The
builder includes them only when they exist in the source data. It does not
invent missing values or emit filler text such as `unspecified`.

## Inputs

- Established 15 material identities:
  `youtu-chem-loop/data/raw/material_performance_20260728/material_categories_full_20260706/`
- New four material identities and performance extractions:
  `youtu-chem-loop/data/raw/material_performance_20260728/batch3/`
- Established 9 electrochemical truths:
  `youtu-chem-loop/data/processed/chem_performance/chem_performance_dataset_v2.jsonl`
- Established 6 material-property truths:
  `../material_property_extraction/results/final_review_package_20260415/all_results.jsonl`

## Binding and Quality Gates

- A one-material record binds directly.
- A multi-material established record binds only when target elements uniquely
  identify one material object.
- A new-property extraction binds by exact normalized material name, a unique
  conservative substring match, a singleton material, or a unique evidence
  mention. Ambiguous multi-material observations are excluded.
- Exact duplicate observations are reduced to one deterministic representative.
- Different labels for the same DOI, material identity, task, and
  indistinguishable metric context are all quarantined.
- Series, group, and variable-composition names remain in the canonical and
  GRPO datasets when their binding is deterministic, but carry `quality_flags`.

## Canonical JSONL

Path:

`youtu-chem-loop/data/processed/material_performance_19/material_performance_19_v1.jsonl`

Each line contains:

```json
{
  "schema_version": "material_performance_19_v1",
  "sample_id": "mp19_<stable hash>",
  "task_type": "thermoelectric",
  "doi": "10.xxxx/example",
  "material": {
    "material_name": "Bi2Te3",
    "major_category": "thermoelectric material",
    "components": [],
    "structure_relationships": [],
    "metal_elements": ["Bi"],
    "nonmetal_elements": ["Te"],
    "elements": ["Bi", "Te"],
    "evidence": "..."
  },
  "prompt_fields": {
    "material_name": "Bi2Te3",
    "material_description": "材料是Bi2Te3。..."
  },
  "performance": {
    "metrics": {
      "figure_of_merit": {
        "raw_value": "1.2",
        "numeric_value": 1.2,
        "comparator": ""
      }
    },
    "conditions": {
      "temperature": "800 K"
    }
  },
  "binding": {
    "status": "direct",
    "mode": "single_material"
  },
  "quality_flags": [],
  "source": {
    "source_group": "new_4",
    "source_file": "source.jsonl",
    "row_number": 1,
    "extraction_index": 0,
    "material_index": 0
  }
}
```

The canonical output is lossless with respect to comparisons:

- exact value: `comparator=""`;
- approximate value: `comparator="~"` or `"≈"`;
- one-sided bound: `comparator=">"`, `">="`, `"<"`, `"<="`, `"≥"`, or `"≤"`.

Categorical values such as antibacterial `complete` are stored under
`performance.categorical_metrics`; they are never converted into arbitrary
numbers.

## GRPO DatasetSample JSONL

Path:

`youtu-chem-loop/data/processed/material_performance_19/material_performance_19_grpo_v1.jsonl`

Each line uses the existing DB upload contract:

```json
{
  "source": "training_free_grpo",
  "question": "material-name-centered prompt plus INPUT_JSON",
  "answer": "{\"figure_of_merit\": 1.2}",
  "meta": {
    "sample_id": "mp19_<stable hash>",
    "doc_id": "10.xxxx/example",
    "task_type": "thermoelectric",
    "material_name": "Bi2Te3",
    "material_description": "材料是Bi2Te3。...",
    "metrics_gt": {"figure_of_merit": 1.2},
    "metrics_raw": {"figure_of_merit": "1.2"},
    "units": {},
    "metric_comparators": {},
    "conditions": {"temperature": "800 K"},
    "binding_status": "direct",
    "binding_mode": "single_material",
    "source_file": "source.jsonl",
    "row_number": 1,
    "input_json": {}
  }
}
```

The current verify function computes point-value relative error. Therefore:

- exact numeric values enter the GRPO output;
- approximate values enter as point estimates and preserve the comparator in
  metadata;
- one-sided bounds remain in the canonical output but are deferred from the
  GRPO projection until verify supports interval semantics;
- HOR exchange-current values with mass-normalized or relative-improvement
  semantics remain canonical-only so they are not mixed with the canonical
  area-normalized `mA cm-2` regression target;
- if a record has both a bounded metric and another exact metric, only its
  exact metric enters the current GRPO answer.

Every GRPO sample keeps `meta.doc_id`; literature retrieval must mask this DOI
during rollout and evaluation.

## Other Outputs

- `manifest_v1.json`: selection accounting and per-task output counts.
- `excluded_observations_v1.jsonl`: exact duplicates, conflicts, ambiguous
  bindings, and other candidates that did not pass the minimum contract.

## Reproduction

Run from `chem-loop/youtu-chem-loop`:

```bash
PYTHONPATH=. ../.venv/bin/python scripts/data/build_material_performance_19_dataset.py
```
