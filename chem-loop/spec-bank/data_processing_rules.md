# Data Processing Rules (Chem Performance)

This document defines the deterministic cleaning + normalization rules for converting the raw extracted chem-performance JSONL files into processed records suitable for later dataset construction and verification.

## Input / Output

- Input: `youtu-chem-loop/data/*.jsonl`
- Output directory: `youtu-chem-loop/data/processed/chem_performance/`

The processing program must:
- never overwrite/mutate raw input files
- drop records that do not contain any evaluable metrics after cleaning

After processing, a second step converts processed records into an uploadable DatasetSample JSONL:
- Script: `youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`
- Output (recommended): `data/processed/chem_performance/chem_performance_dataset.jsonl`

## Processed Record Schema (JSONL)

Each processed JSONL line represents one record and SHOULD contain:
- `id`: original record id (string)
- `reaction_type`: one of the 9 enums
- `metals`: normalized list of element symbols
- `product`: only for CO2RR (input context, not a metric)
- `metrics_gt`: `dict[str, str]`
  - all evaluable metrics for this record (after cleaning)
  - values are normalized raw strings (parseable; starts with number)
- `metrics_raw`: optional, raw extracted metric values before normalization (debug only)
- `units`: optional, extracted unit hints per metric key (for later question/unit_hint generation)

## Cleaning Rules

### Drop Unused Fields

Remove these fields if present:
- `pos`
- `block_index`

### Drop Null Metric Keys

- Any metric key whose value is `null` must be removed.
- Null metric keys must not be preserved as placeholders.

### Metric Key Canonicalization

Normalize O5H key casing:
- `Faradaic_efficiency` -> `faradaic_efficiency`

Normalize overpotential keys to make the current-density condition explicit (η@10 mA cm^-2):
- `HER/OER`: `overpotential` -> `overpotential_10mAcm-2`
- `HzOR`: keep `overpotential_10mAcm-2` (drop other current-density variants as out-of-scope)

Normalize UOR potential keys (treat potential and overpotential as the same metric in this project stage):
- `UOR`: `potential` / `overpotential` -> `potential_10mAcm-2`

All other metric keys are kept unchanged.

### Metric Scope (Reaction-Specific)

At this project stage we keep only the metric(s) we plan to optimize/judge for each `reaction_type`.
Any metric key outside the scope below MUST be dropped during processing.

- `HER`: keep `overpotential_10mAcm-2`
- `OER`: keep `overpotential_10mAcm-2`
- `ORR`: keep `half_wave_potential`
- `HOR`: keep `exchange_current_density`
- `UOR`: keep `potential_10mAcm-2`
- `EOR`: keep `mass_activity`
- `HzOR`: keep `overpotential_10mAcm-2`
- `O5H`: keep `faradaic_efficiency`
- `CO2RR`: handled specially using `data/co2rr_final.jsonl` schema:
  - keep only the top-FE product as the truth `product` label
  - keep `partial_current_density` for that truth product (mA cm-2)

## Metals Normalization

`metals: list[str]` MUST be normalized by:
- trimming whitespace
- canonical casing (`pt` -> `Pt`, `NI` -> `Ni`)
- deduplicating
- sorting alphabetically

## Unit Normalization

### Potential / Overpotential Units (Key-Aware)

This workspace uses different canonical units depending on the metric key:

- For any key containing `overpotential`:
  - canonical unit is `mV`
  - if raw value is in `V`, convert `V -> mV` by multiplying by 1000
- For other potential-like keys (e.g. `potential`, `half_wave_potential`):
  - canonical unit is `V`
  - if raw value is in `mV`, convert `mV -> V` by dividing by 1000

Example:
- overpotential: `0.30 V` -> `300 mV`
- potential: `420 mV` -> `0.42 V`

### Exchange Current Density Units (HOR)

For `exchange_current_density`:
- canonical unit is `mA cm-2`
- keep only absolute values convertible to `mA cm-2` (accept `mA cm-2` and `A cm-2`)
- drop non-absolute or non-convertible strings (e.g. "*times greater*", "*fold improvement*", `A g-1`, etc.)

### Percent -> Fraction

If a metric value includes a percent sign:
- interpret it as a percentage
- convert to a fraction in `[0, 1]` by dividing by 100
- drop the `%` sign in the normalized value string

Examples:
- `95%` -> `0.95`
- `98.5%` -> `0.985`
- `95.0 %` -> `0.95`

### Other Units

Other units may be preserved as-is (for now) if:
- the numeric part is parseable, and
- the string begins with that numeric literal (see parseability rules below)

## Parseability / Filtering Rules

To avoid treating non-numeric text (e.g. `cm-2`) as a number:
- A metric value is considered parseable only if the string begins with a numeric literal (allowing sign and decimals), e.g.:
  - `3.68 mA cm-2`
  - `-0.064 V`
  - `0.36 V`

If a record ends up with zero metrics in `metrics_gt` after cleaning:
- drop the record entirely

## CO2RR Special Case

- `product` is an input condition, not a metric.
- It MUST be preserved for CO2RR records, but MUST NOT be included in:
  - `metrics_gt`
  - the future `metrics_to_predict`
  - the future `answer` payload

## Verification Checklist

When validating a processing run:
- raw line count vs processed line count (processed may be smaller; report drop reasons)
- processed records contain no `pos` / `block_index`
- processed records contain no metric keys with null values
- percent values are converted into 0~1 fractions
- CO2RR keeps `product` and excludes it from metrics
