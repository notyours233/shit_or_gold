# Data Layout (Chem Performance)

This document records where the raw extracted chem-performance data lives and where processed (cleaned/normalized) outputs should be written.

## Imported 19-Direction Material-Performance Package (2026-07-28)

The current re-extracted material inputs are local, immutable audit sources under:

- `youtu-chem-loop/data/raw/material_performance_20260728/material_categories_full_20260706/`
  - re-extracted material objects for the established 15 directions
  - performance truth remains in the two established processed/review datasets below
- `youtu-chem-loop/data/raw/material_performance_20260728/batch3/`
  - material objects and performance extractions for the four new directions

Established truth sources:

- 9 electrochemical directions: `youtu-chem-loop/data/processed/chem_performance/chem_performance_dataset_v2.jsonl`
- 6 material-property directions: `../material_property_extraction/results/final_review_package_20260415/all_results.jsonl`

Audit artifacts:

- Reproducible report: `spec-bank/material_performance_grpo_readiness_audit_20260728.md`
- Local machine-readable output: `youtu-chem-loop/data/audits/material_performance_20260728/`
  - `summary.json`
  - `review_queue.jsonl`

Integrated dataset artifacts:

- Canonical material-performance records:
  `youtu-chem-loop/data/processed/material_performance_19/material_performance_19_v1.jsonl`
- Current point-value verify-compatible DatasetSample records:
  `youtu-chem-loop/data/processed/material_performance_19/material_performance_19_grpo_v1.jsonl`
- Build accounting:
  `youtu-chem-loop/data/processed/material_performance_19/manifest_v1.json`
- Excluded duplicate/conflict/ambiguous observations:
  `youtu-chem-loop/data/processed/material_performance_19/excluded_observations_v1.jsonl`
- Contract: `spec-bank/material_performance_19_dataset_contract.md`

The imported raw package and generated audit queue are git-ignored. Dataset builders must consume only
gated, deduplicated observations; they must not fan one article-level truth label out to every material in
a multi-material record.

The imported material-object schemas provide `material_name`, category, evidence, components, structure
relationships, and element lists (the established 15 omit an explicit metal list). They do not provide
structured `precursors`, `feed_ratio`, `preparation_method`, or `element_content` fields. Those fields may
be added when later sources provide them. The current material-name-centered builder includes only fields
that exist and omits missing optional fields. A consistently complete version of the new prompt template
requires a separate re-extraction from source text.

## Literature Chroma Layout (2026-07-28)

- Active unified 19-direction database: `MAD/data/chroma_db/`
  - collections: `literature_agent1` through `literature_agent4`
  - shared mode uses `literature_agent2`
- Preserved pre-migration split database: `MAD/data/chroma_db_legacy_split_20260728/`
  - retained for rollback/comparison; it is not the default runtime database

Every GRPO sample must retain its normalized DOI as `doc_id`, and literature retrieval must mask that DOI
during rollout/evaluation to prevent exact-paper label leakage.

## Raw Data (Input)

- Location: `youtu-chem-loop/data/*.jsonl`
- Current files (one reaction_type per file):
  - `youtu-chem-loop/data/her.jsonl` (HER)
  - `youtu-chem-loop/data/OER.jsonl` (OER)
  - `youtu-chem-loop/data/ORR.jsonl` (ORR)
  - `youtu-chem-loop/data/hor.jsonl` (HOR)
  - `youtu-chem-loop/data/UOR.jsonl` (UOR)
  - `youtu-chem-loop/data/eor.jsonl` (EOR)
  - `youtu-chem-loop/data/hzor.jsonl` (HzOR)
  - `youtu-chem-loop/data/o5h.jsonl` (O5H)
  - `youtu-chem-loop/data/co2rr_final.jsonl` (CO2RR, final extraction; preferred)
  - `youtu-chem-loop/data/co2rr.jsonl` (CO2RR, legacy; ignored if co2rr_final.jsonl exists)

Notes:
- Raw files may contain non-metric fields like `pos` / `block_index` (HOR/HzOR/O5H) and `product` (CO2RR).
- Raw files may contain `null` metric values; those must be removed during processing.
- Raw `data/` is git-ignored in this repo (by design); do not rely on committing raw/processed JSONL to git.

## Processed Data (Output)

- Location (recommended): `youtu-chem-loop/data/processed/chem_performance/`
- Requirements:
  - Processed outputs must never overwrite or mutate `youtu-chem-loop/data/*.jsonl`.
  - The processed directory may be absent/empty; processing scripts should create it as needed.

Suggested convention:
- Keep output filenames aligned with inputs (e.g. `OER.jsonl` -> `data/processed/chem_performance/OER.jsonl`) so source tracing is trivial.
- Each processed line represents one cleaned record with:
  - normalized `metals`
  - canonicalized metric keys (notably O5H key casing)
  - normalized metric values (key-aware unit conventions, notably overpotential->mV, potential->V, %->fraction)
  - `metrics_gt` computed as the set of evaluable metrics for that record

## Uploadable Dataset JSONL (for DB upload)

To upload chem-performance samples into the DB, we build a DatasetSample "default format" JSONL:
- Input: `data/processed/chem_performance/*.jsonl`
- Output (recommended):
  - `youtu-chem-loop/data/processed/chem_performance/chem_performance_dataset.jsonl`

Script:
- `youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`

The resulting JSONL is intended to be used with:
- `youtu-chem-loop/scripts/data/upload_dataset.py --data_format default`
