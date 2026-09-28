# Chem Performance Verify Spec (Training-Free GRPO)

This document defines the expected behavior of the chem-performance verification function used by the
Training-Free GRPO pipeline.

Scope:
- parse model output from `EvaluationSample.response`
- parse ground-truth from `EvaluationSample.correct_answer`
- compute a numeric `reward` in `[0, 1]`

Non-goals:
- final reward weighting/scales (can be tuned later)
- unit normalization beyond what is already enforced in data processing

## Output Contract (Model -> Verify)

Verify accepts two response shapes (to support both legacy and newer “structured conclude” modes):

1) **Legacy tags** (string response):
- `<answer>...</answer>` containing a JSON object (dict)
- `<think>...</think>` is recommended but **not required for reward** (format is handled by static prompts + auto-repair)

2) **Structured JSON** (stringified JSON object):
- `{"think": "<string>", "answer": { ... }}` (preferred)
- `{"answer": { ... }}` (think optional)
- In these cases, verify reads the `answer` dict.

For regression tasks, the answer dict MUST:
- be a JSON object (dict)
- contain only the metrics requested for that record (no extra keys)
- contain numeric values only (no units, no strings)

If the answer object cannot be parsed, reward MUST be 0.

### Optional Unit Repair (Best-Effort)

To keep the closed-loop usable in real deployments, verify MAY apply a *best-effort repair* pass
when a predicted value is a string that includes units (e.g., `"0.3 V"`).

Rules:
- Repair is ONLY allowed when the verifier has an expected unit hint for that metric key (usually from `sample.meta.units`).
- If the unit matches (or is safely convertible to) the expected canonical unit, verify may extract/convert the numeric value.
  - Examples: `V <-> mV`, `A cm-2 -> mA cm-2`, `% -> fraction_0_to_1`.
- If the unit is missing, ambiguous, or mismatched, reward MUST be 0 (treat as non-evaluable).

This repair pass is meant to be a safety net; the preferred model behavior is still to output numbers-only.

### CO2RR Special Case: Two-Task Setup

CO2RR is split into two tasks:

1) Task 1 (classification): predict the **top-FE product**
- GT format: `{"product": "<PRODUCT_NAME>"}` (string)
- Prediction format:
  - legacy tags: `<answer>{"product": "<PRODUCT_NAME>"}</answer>`
  - OR structured: `{"answer": {"product": "<PRODUCT_NAME>"}}`
- Reward: 1.0 if product matches (after light normalization), else 0.0

2) Task 2 (regression): predict **partial current density** for that truth product
- GT format: `{"partial_current_density": "<NUM> mA cm-2"}`
- Prediction format:
  - legacy tags: `<answer>{"partial_current_density": <number>}</answer>`
  - OR structured: `{"answer": {"partial_current_density": <number>}}`
- Reward: numeric regression reward (see below)

## Ground Truth Contract

Ground truth is stored as a JSON dict string in:
- `DatasetSample.answer` -> `EvaluationSample.correct_answer`

For regression-style tasks, GT values are raw strings that MUST begin with a numeric literal (examples):
- `288 mV`
- `0.985`
- `2.74 mA cm-2`

Verify MUST parse the numeric prefix into a float.

## Key Alignment Rules

Let:
- `gt_keys` = keys from GT dict
- `pred_keys` = keys from predicted dict

Rules:
- If `pred_keys` has any extra keys not in `gt_keys`, reward MUST be 0.
- Missing keys are penalized by treating their per-metric score as 0.

## Reward (Project-Phase Implementation)

Reward is computed by aggregating per-metric scores across `gt_keys`:
- if a key is missing: score = 0
- otherwise: score is a smooth function of absolute error (scaled), yielding `[0, 1]`

Aggregation rules (current project phase):
- Default: equal weight across metrics present in the record.
- CO2RR: equal weight across metrics present in the record.
  - (O5H currently focuses on faradaic_efficiency only, so aggregation is effectively single-metric.)

The per-metric scoring function is still intentionally simple to keep the Training-Free GRPO loop runnable;
it can be replaced by a more domain-specific scaling (e.g., log-space error for wide-range metrics) later.
