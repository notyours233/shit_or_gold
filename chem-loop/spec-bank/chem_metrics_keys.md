# Material Property Metric Keys

This document is the canonical vocabulary of metric keys for the material-property dataset used in Training-Free GRPO.

Goals:
- prevent verify/data mismatches due to key naming drift
- make it explicit which metrics are expected per `property_type`

## Canonical Metric Keys (All)

After key normalization, the material-property metric keys used in this workspace are:

- `photothermal_conversion_efficiency`
- `conductivity`
- `thermal_conductivity`
- `saturation_magnetization`
- `neel_temperature`

## Task Label Keys (Non-metric)

No current material-property task uses a string label in `<answer>`; all six tasks are numeric regression tasks.

## Metric Keys by Property Type

- `photothermal_conversion_efficiency`
  - `photothermal_conversion_efficiency` (%)
- `conductivity`
  - `conductivity` (S/m)
- `thermal_conductivity`
  - `thermal_conductivity` (W m-1 K-1)
- `ferromagnetism`
  - `saturation_magnetization` (emu/g)
- `ferrimagnetism`
  - `saturation_magnetization` (emu/g)
- `antiferromagnetism`
  - `neel_temperature` (K)

## Key Normalization Rules

Unit-normalization rules applied at the data-processing / verify stage:

- Photothermal conversion efficiency is normalized to percent numeric values (`%`).
- Conductivity is normalized to `S/m`.
  - Accepted examples: `S/m`, `mS/m`, `S/cm`, `mS/cm`, `S m-1`, `S cm-1`.
- Thermal conductivity is normalized to `W m-1 K-1`.
- `A m2/kg` is accepted as equivalent to `emu/g` for saturation magnetization.
- Neel temperature is normalized to `K`.
- All six metrics are higher-is-better for grading/ranking.
