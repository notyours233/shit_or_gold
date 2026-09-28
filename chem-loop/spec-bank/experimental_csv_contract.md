# Experimental Feedback CSV Contract (Material-Name-First)

This contract defines the current closed-loop ingestion path for real material-performance
measurements in ChemCouncil. It applies to:

- `youtu-chem-loop/scripts/data/import_experimental_csv.py`
- `youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`
- the Web manual-feedback CSV generated from a completed recommendation

The output is an uploadable `DatasetSample` JSONL for incremental Training-Free GRPO.

## Identity and Direction

Each row contains one measured metric for one performance direction.

Required row concepts:

- `task_type` (preferred) or `property_type` / `reaction_type` (compatibility aliases)
- `material_name` (preferred material identity) or legacy `metals`
- numeric `value` (or structured CO2RR metric cells)

New feedback must use `material_name` as its identity. A material name is sufficient;
elements, synthesis conditions, precursors, composition and all other material fields are optional.
The importer must not derive element data from a formula and label that inferred result as experimental input.

Legacy metal-only CSV rows remain readable, but they use the older input form and are not the
template for newly submitted feedback.

## Preferred Columns

The Web UI writes the following columns for each manually entered measurement:

```text
recommendation_job_id,material_name,material_input_json,elements,task_type,
property_type,reaction_type,value,unit,condition,notes
```

- `material_input_json` is a JSON object copied from the source recommendation. It may include
  `major_category`, `components`, `structure_relationships`, `precursors`, `feed_ratio`,
  `preparation_method`, `elements`, `element_content`, `conditions`, and `custom_prompt`.
- `elements` is optional. Only values explicitly present in the original material input are written.
- `task_type` is the authoritative new field. `property_type` and `reaction_type` are repeated only
  for compatibility with existing analytics and historical CSV readers.
- `recommendation_job_id` is optional for raw laboratory CSVs but required for prediction-vs-experiment
  linkage in the Web feedback workflow.

Researchers may instead provide structured columns directly. The importer recognizes English and Chinese
aliases for `material_name`, material category, components, structure relationships, precursors, feed ratio,
preparation method, elements, element content, conditions, custom prompt and material description.

`material_description` is optional. When absent, the importer/build step assembles the template from the
available structured fields. When present, it is preserved exactly as experimenter-supplied material context.

## Prompt Projection

For a material-name row, the DatasetSample question carries the same contract as the audited 19-direction
base dataset:

```json
{
  "material_name": "MoS2负载CuO纳米颗粒",
  "material_description": "材料是MoS2负载CuO纳米颗粒。该材料是以...为前驱体。",
  "task_type": "photocatalytic_h2o2",
  "metrics_to_predict": [{"key": "apparent_quantum_efficiency", "unit_hint": "%"}],
  "custom_prompt": "使用 420 nm 光源。"
}
```

Only populated optional fields are rendered. A material-only row with `material_name=CuO` produces
`材料是CuO。`; it does not gain a fictitious precursor, ratio, element list or test condition.

`custom_prompt` is material data. It cannot replace the system prompt, tool rules, debate protocol or
strict JSON output schema.

## Supported Directions and Main Metrics

The current vocabulary has 19 directions:

| Direction | Main metric | Canonical unit |
| --- | --- | --- |
| HER / OER / HZOR | `overpotential_10mAcm-2` | mV |
| ORR | `half_wave_potential` | V |
| HOR | `exchange_current_density` | mA cm-2 |
| UOR | `potential_10mAcm-2` | V |
| EOR | `mass_activity` | A mg-1 |
| O5H | `faradaic_efficiency` | fraction_0_to_1 |
| CO2RR | `partial_current_density` | mA cm-2 |
| photothermal_conversion_efficiency | `photothermal_conversion_efficiency` | % |
| conductivity | `conductivity` | S/m |
| thermal_conductivity | `thermal_conductivity` | W m-1 K-1 |
| ferromagnetism / ferrimagnetism | `saturation_magnetization` | emu/g |
| antiferromagnetism | `neel_temperature` | K |
| photocatalytic_h2o2 | `apparent_quantum_efficiency` | % |
| antibacterial | `minimum_concentration` | ppm (`ug/mL` and `mg/L` accepted) |
| thermoelectric | `figure_of_merit` | dimensionless |
| furfural_hydrogenation | `furfuryl_alcohol_yield` | % |

For a 19-direction material-name record, `CO2RR` remains a single direction. Historical metal-only
records retain the old product and partial-current-density split only so old datasets can still be imported.

## Units, Conditions, and Provenance

`value` can carry its unit directly or use a separate `unit` column. The importer normalizes established
reaction metrics and material-property units before producing `metrics_gt`. Percent feedback is represented
as percent for the material-name property tasks and as a fraction for the legacy electrochemical FE contract.

`condition`, DOI, title, notes, and `recommendation_job_id` are optional provenance. Eta10 directions retain
the existing `--drop_explicit_non_eta10` and `--require_eta10_condition` checks. Missing conditions do not
invalidate an otherwise usable material-name row.

## Legacy Metals Compatibility

If an older CSV has no `material_name`, the importer still accepts `metals` cells such as `Pt,Ru` or
`Co(57%),Ni(23%)`, normalizes the list, and retains composition percentages where available. New code must
never force a material-name feedback row to add this legacy field.
