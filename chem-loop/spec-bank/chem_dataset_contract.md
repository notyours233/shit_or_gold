# Chem Performance Dataset Contract

This document defines the minimal, stable data contract for the chem-performance Training-Free GRPO task:

- input conditions: `metals` + `reaction_type` (+ `product` for CO2RR)
- evaluation ground truth: a JSON dict of the **evaluable target(s)** for that record
  - usually numeric metrics (regression)
  - for CO2RR Task 1, a string label (product classification)

It is intentionally small and focuses on what must be true for later steps (verify / GRPO) to run reliably.

## Reaction Type Enum

`reaction_type` MUST be one of:
- `HER`
- `OER`
- `ORR`
- `HOR`
- `UOR`
- `EOR`
- `HzOR`
- `O5H`
- `CO2RR`

## Metals Field

- Type: `list[str]`
- Normalization rules (MUST):
  - deduplicate
  - canonical casing for element symbols (e.g. `pt` -> `Pt`, `NI` -> `Ni`)
  - sort alphabetically

## Metrics Ground Truth

### `metrics_gt`

- Type: `dict[str, str]`
- Meaning: the set of metrics that are present (non-null) and evaluable for this record.
- Constraints (MUST):
  - contains at least 1 key
  - keys are canonical metric keys (see key vocabulary in `spec-bank/chem_metrics_keys.md`)
  - values are raw strings (not necessarily unit-free) but MUST be parseable by verify (numeric prefix):
    - the string MUST start with a numeric literal (allowing sign and decimals), e.g. `0.36 V`, `-0.064 V`, `3.68 mA cm-2`
  - unit normalization happens in data processing (key-aware conventions):
    - overpotential_10mAcm-2 is stored as `mV` (accept V/mV in raw)
    - other potential-like metrics are stored as `V` (accept V/mV in raw)
    - exchange_current_density is stored as `mA cm-2` (accept A/mA in raw)
    - percent values are stored as fractions in `[0, 1]` (divide by 100)

### Ground Truth Storage in DB

In Training-Free GRPO, ground truth is stored as:

- `DatasetSample.answer` (string) MUST be a JSON dict string for `metrics_gt`
- during evaluation/practice this becomes `EvaluationSample.correct_answer`

Important:
- `id` / `metals` / `reaction_type` / `product` / `pos` / `block_index` are metadata, not metrics.
- Those metadata fields MUST NOT appear as keys inside `metrics_gt`.

## CO2RR Special Case

CO2RR is split into two tasks:

1) Task 1 (classification): predict the top-FE product
- Input: `metals` + `reaction_type`
- Ground truth (answer): `{"product": "<PRODUCT_NAME>"}` (string)

2) Task 2 (regression): predict partial current density for that truth product
- Input: `metals` + `reaction_type` + `product` (truth product)
- Ground truth (answer): `{"partial_current_density": "<NUM> mA cm-2"}` (numeric prefix)

## Recommended DatasetSample.meta Fields

When converting a processed record into a DB dataset sample (`youtu-chem-loop/scripts/data/upload_dataset.py --data_format default`),
each row SHOULD include these metadata fields in `meta`:

- `meta.metals`: normalized metals list
- `meta.reaction_type`: reaction type string
- `meta.metrics_gt`: same payload as `answer` (JSON dict, raw strings)
- `meta.product`: only for CO2RR
- `meta.doc_id`: OPTIONAL but strongly recommended for `chem_performance_v2`+
  - A DOI-like string that matches the literature DB (Chroma) metadata field `doc_id`
  - Used for **doc-level leakage masking** during Training-Free GRPO / eval rollouts (prevents “search the exact paper and copy the label”)
- `meta.metrics_raw`: optional, raw extracted metric values before normalization (for debugging)
- `meta.units`: optional, unit hints per metric key (for question construction/debugging)

## Uploadable Dataset JSONL (DatasetSample default format)

To upload into the DB with `youtu-chem-loop/scripts/data/upload_dataset.py --data_format default`, each JSONL line SHOULD be a dict
containing at least:

- `source`: MUST be `training_free_grpo` (so the Training-Free GRPO processor is selected)
- `question`: the task prompt (string)
- `answer`: a JSON dict string of `metrics_gt`
- `meta`: metadata dict (see above)

The build script for this workspace:
- `youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`

## Record Validity / Dropping Rules

- If after cleaning/normalization a record has zero evaluable metrics (empty `metrics_gt`), it MUST be dropped.
