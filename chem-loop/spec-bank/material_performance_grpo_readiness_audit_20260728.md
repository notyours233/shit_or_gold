# Material Performance GRPO Readiness Audit (2026-07-28)

## Conclusion

The data is usable for GRPO only with a strict ingestion gate. Of 12533 candidate material-performance samples, 11251 (89.77%) are directly usable, 302 are deterministically recoverable, and 980 must be excluded until reviewed.
After cross-record deduplication and conflict quarantine, 11311 unique samples are eligible after any recorded deterministic repairs. Of these, 11311 meet the audit's stricter diagnostic contract, while 0 carry a diagnostic flag. The actual dataset builder uses the user-approved minimum contract: a uniquely bound material name plus numeric performance truth; optional conditions are retained when present but are not required.

Training policy:

- `direct`: may enter the first GRPO build.
- `recoverable`: enter only after the documented deterministic normalization/match is applied.
- `manual_review`: do not copy labels across materials; keep in the review queue.
- Every rollout with literature RAG must mask the sample DOI to prevent exact-paper label leakage.

## Overall Counts

| Group | Source records | Material objects | Candidate samples | Direct | Recoverable | Manual review |
|---|---:|---:|---:|---:|---:|---:|
| Established 15 | 11342 | 12997 | 11330 | 10201 | 212 | 917 |
| New 4 | 1116 | 1225 | 1203 | 1050 | 90 | 63 |

## Established 15 Directions

| Task | Records | Multi-material | Truth matched | Candidate samples | Direct | Recoverable | Manual | Chroma-maskable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `CO2RR` | 1415 | 153 | 1414 | 1414 | 1260 | 34 | 120 | 1415 |
| `EOR` | 76 | 6 | 76 | 76 | 70 | 3 | 3 | 76 |
| `HER` | 2867 | 214 | 2867 | 2867 | 2653 | 41 | 173 | 2867 |
| `HOR` | 86 | 6 | 82 | 82 | 76 | 2 | 4 | 86 |
| `HZOR` | 72 | 1 | 72 | 72 | 71 | 0 | 1 | 72 |
| `O5H` | 59 | 2 | 59 | 59 | 57 | 2 | 0 | 59 |
| `OER` | 219 | 13 | 218 | 218 | 205 | 5 | 8 | 219 |
| `ORR` | 240 | 7 | 240 | 240 | 233 | 1 | 6 | 240 |
| `UOR` | 92 | 6 | 92 | 92 | 86 | 3 | 3 | 92 |
| `antiferromagnetism` | 1114 | 199 | 1113 | 1113 | 914 | 25 | 174 | 1114 |
| `conductivity` | 1447 | 154 | 1444 | 1444 | 1290 | 28 | 126 | 1447 |
| `ferrimagnetism` | 65 | 6 | 65 | 65 | 59 | 2 | 4 | 65 |
| `ferromagnetism` | 835 | 109 | 834 | 834 | 725 | 20 | 89 | 835 |
| `photothermal_conversion_efficiency` | 1515 | 67 | 1515 | 1515 | 1448 | 17 | 50 | 1515 |
| `thermal_conductivity` | 1240 | 185 | 1239 | 1239 | 1054 | 29 | 156 | 1240 |

## Newly Added 4 Directions

| Task | Records | Multi-material | Extractions | Direct | Recoverable | Manual | Condition present | Chroma-maskable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `photocatalytic_h2o2` | 261 | 9 | 267 | 267 | 0 | 0 | 210 | 261 |
| `antibacterial` | 99 | 5 | 100 | 63 | 31 | 6 | 42 | 99 |
| `thermoelectric` | 611 | 66 | 686 | 570 | 59 | 57 | 686 | 609 |
| `furfural_hydrogenation` | 145 | 6 | 150 | 150 | 0 | 0 | 12 | 144 |

## Material Identity and Label Risks

- Established directions contain 1128 records with multiple material objects.
- New directions contain 86 records with multiple material objects.
- Across both groups, 0 material objects have blank names and 1 use generic placeholder-like names under the audit heuristic.
- A broader review-only heuristic flags 258 material objects as series/group/variable-composition names; these are not automatically discarded.
- The generated review queue contains 1313 recoverable/manual items, including cross-record conflict groups.
- New-property extractions missing their primary test condition: 253 of 1203.

## Cross-Record Duplicate and Conflict Check

- Raw material-label observations: 12533.
- Exact duplicate groups: 191, removing 234 repeated observations before training.
- Indistinguishable-context conflict groups: 19, covering 50 raw observations that must be quarantined.
- Material identities with multiple distinguishable metric contexts: 18; these are retained as legitimate condition-specific labels.

## Established Truth Parseability and Unit Contracts

- Parseable numeric truth values: 12731 of 12731.
- Values carrying a comparator: 0; comparators must remain in the label contract.
- Noncanonical/relative or missing unit-contract values: 13.
- A leading number is not sufficient for GRPO: relative improvements and mass-normalized exchange-current values must not be mixed with area-normalized absolute exchange current.

## Coverage of the New Material Prompt Fields

- Material name is present for 12997 of 12997 established material objects and 1225 of 1225 new material objects.
- Explicit metal-element lists exist for 0 established and 1225 new material objects; established metals currently require conservative inference from names/components.
- Structured `precursors`, `feed_ratio`, `preparation_method`, and `element_content` fields are absent from both imported schemas. Evidence text sometimes mentions them, but it is not a complete or deterministic substitute.
- Therefore the first safe GRPO build uses `material_name` plus only the optional composition, relationship, condition, or synthesis fields actually present. Missing optional fields are omitted, not filled with `unspecified`.

## Chroma Leakage-Masking Check

The unified collection `literature_agent2` is readable and exposes task-filterable `doc_id` metadata. The per-task tables report how many source records can be masked under the matching task filter.

## Required Dataset-Build Gates

1. Join the established 15 directions by canonical task plus normalized DOI; use source row number when available.
2. Never fan one performance label out to every material in a multi-material article.
3. Deduplicate identical task/context/label targets and quarantine conflicting labels with indistinguishable input context.
4. Keep comparator information such as `>90%`; do not silently replace it with an exact value.
5. Preserve temperature for thermoelectric ZT and test-organism/context evidence for antibacterial data when present; do not fabricate missing optional conditions.
6. Store `doc_id` in every GRPO sample and mask that DOI in Chroma retrieval during rollout/evaluation.
7. Version the generated dataset and experience pack; do not seed from the old metal-only experience pack.

## Reproduction

Run from `chem-loop/youtu-chem-loop`:

```bash
python scripts/data/audit_material_performance_grpo_readiness.py
```

Machine-readable output and the review queue are written under `data/audits/material_performance_20260728/`.
