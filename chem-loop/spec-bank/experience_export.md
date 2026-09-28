# Experience Export Spec (Training-Free GRPO)

This document specifies how to export distilled experiences (G0/G1/...) produced by the Training-Free GRPO practice pipeline.

Scope:
- Export is a *portable* record for downstream usage (other repos, prompt injection, audit/debug).
- This spec does NOT define how to train models; it only standardizes what we carry out of this repo.

## Source Of Truth

- Experiences are materialized as:
  - `cache_experience` table rows in DB during runs (optional intermediate cache), AND
  - a generated agent config YAML written to `configs/agents/practice/<experiment_name>_agent.yaml`

For manual export, the generated agent config YAML is the easiest single artifact.

## Export Format (Recommended)

Export a single JSON object (one file per experiment) with the fields below.

Required fields:
- `export_version`: string, semantic version of this spec (e.g., "1.0")
- `experiment_name`: string, matches CLI `--experiment_name`
- `exp_id`: string, practice config `exp_id` (e.g., "chem_performance_practice")
- `timestamp_utc`: string, ISO-8601 (e.g., "2026-01-21T11:04:51Z")
- `practice_hparams`:
  - `epochs`: int
  - `batch_size`: int
  - `grpo_n`: int
  - `rollout_data_truncate`: int | null
- `dataset`:
  - `practice_dataset_name`: string
  - `eval_dataset_name`: string | null (if `do_eval=false`, keep null)
- `agent_config_path`: string, workspace-relative path to the generated YAML
- `experiences`: array of objects, ordered by ID
  - `id`: string ("G0", "G1", ...)
  - `content`: string (one-line guidance)

Optional fields (useful for audit/debug):
- `model`:
  - `provider_type`: string ("chat.completions" | "responses")
  - `model_name`: string (e.g., "deepseek-reasoner")
  - `temperature`: number
  - `top_p`: number | null
- `notes`: string

## Example (JSON)

```json
{
  "export_version": "1.0",
  "experiment_name": "chem_perf_smoke_01",
  "exp_id": "chem_performance_practice",
  "timestamp_utc": "2026-01-21T11:04:51Z",
  "practice_hparams": {
    "epochs": 1,
    "batch_size": 4,
    "grpo_n": 2,
    "rollout_data_truncate": 20
  },
  "dataset": {
    "practice_dataset_name": "chem_performance_v2",
    "eval_dataset_name": null
  },
  "agent_config_path": "configs/agents/practice/chem_perf_smoke_01_agent.yaml",
  "experiences": [
    { "id": "G0", "content": "Format Compliance: ... (example)" }
  ],
  "model": {
    "provider_type": "chat.completions",
    "model_name": "deepseek-reasoner",
    "temperature": 1.0,
    "top_p": 0.95
  },
  "notes": "Smoke run; truncate=20."
}
```

## Extraction Guidance

To extract experiences from the generated agent config YAML:
- Find the `agent.instructions` block.
- Experiences are embedded as lines like `[G0]. ...`, `[G1]. ...`.

If you need programmatic extraction later, prefer parsing YAML and then regex matching `\\[G\\d+\\]` lines.
