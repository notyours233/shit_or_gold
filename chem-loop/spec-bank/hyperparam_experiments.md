# Hyperparameter Experiment Discipline (Training-Free GRPO)

This note records the experiment discipline for Training-Free GRPO runs in this repo.

Goal:
- Keep experiments comparable and reproducible by limiting what we change between runs.

## Allowed To Tune (Only These 3)

Per `memory-bank/step.md` Step 8, treat the following as the ONLY tunable parameters between experiments:

| Parameter | Meaning | Default (chem_performance) | Suggested Sweep (start small) |
| --- | --- | --- | --- |
| `epochs` | number of practice epochs | `1` | `1`, `2` |
| `batch_size` | problems per batch (effective samples = `batch_size * grpo_n`) | `50` | `4`, `8`, `16`, `32`, `50` |
| `grpo_n` | rollouts per problem group | `3` | `2`, `3`, `4`, `6` |

Notes:
- Increase `batch_size` cautiously: it scales rollout cost roughly linearly.
- Increase `grpo_n` cautiously: it scales rollout cost linearly and affects group advantage updates.

## Experiment Naming Convention (Required For Sweeps)

We use the `--experiment_name` value as `exp_id` (and it also becomes the prefix of the exported agent YAML file).
To keep runs comparable and easy to summarize, use a deterministic name that encodes:
- single-agent rollout + RAG status
- dataset subset
- truncate (tN)
- the 3 tunable hyperparams (epochs/batch_size/grpo_n)

Recommended format (filename-safe; only letters/numbers/underscores):

`single_hp_rag{0|1}_u{0|1}_{ds}_t{truncate}_e{epochs}_b{batch_size}_n{grpo_n}`

Where:
- `rag1` means `CHEM_GRPO_RAG_ENABLED=1`.
- `u1` means the chem-performance unit/scale conventions are enabled in the prompt
  (implemented in `utu/eval/processer/training_free_grpo_processor.py`).
- `{ds}` is a short dataset code (examples used in this workspace):
  - `ds350` -> `chem_performance_v2_350_noher_co2rr`
  - `ds450` -> `chem_performance_v2_450`
- `t{truncate}` must match `--rollout_data_truncate`.

Example:
- `single_hp_rag1_u1_ds350_t30_e1_b30_n3`

## Keep Fixed Unless There Is A Clear Need

These parameters should remain fixed when comparing runs:
- `practice.rollout_temperature`
- `practice.rollout_concurrency` (speed vs memory; in docker/RAG setups, `4` is a common starting point; lower to `1` if you see OOM/returncode=-9)
- `practice.task_timeout`
- `practice.rollout_data_truncate` (except for smoke runs; for real comparisons keep it constant)
- Single-agent literature retrieval flags:
  - `CHEM_GRPO_RAG_ENABLED` (set to `1` or `0` for the whole sweep)
  - `CHEM_GRPO_RAG_LIMIT`, `CHEM_LITERATURE_CHROMA_MAX_DISTANCE`, `VOYAGE_TIMEOUT`
- verify function and reward logic
- dataset name/version

## Sweep Runner Script

Use the stdlib-only helper script to run a grid sweep:
- Script: `youtu-chem-loop/scripts/run_hyperparam_sweep.py`
- It enforces the naming convention above and prints per-run + final tables via:
  `scripts/db/summarize_experiments.py`.

Docker wrapper (recommended in this monorepo):
- Script: `scripts/run_hp_sweep.sh`
- Why: runs the sweep inside the `chemcouncil` container against the shared `/state/test.db`, and forces
  deterministic experience batch-merge so long paragraph micro-cards do not get truncated/swallowed by a second LLM pass.

Safety valve (speed vs memory):
- `youtu-chem-loop/scripts/run_hyperparam_sweep.py` supports `--rollout_concurrency_fallback <int>`.
  - If a run fails at the primary `--rollout_concurrency` (OOM/timeout/overload), it retries that run once with the
    fallback concurrency and uses the fallback for the remaining runs.
  - This is **not** a tunable hyperparameter; it is a safety mechanism to avoid losing an entire sweep.
- Docker wrapper `scripts/run_hp_sweep.sh` passes this via env `ROLLOUT_CONCURRENCY_FALLBACK` (default: `4`).

Two-stage sweep helper (batch_size then grpo_n):
- Script: `scripts/run_hp_two_stage.sh`
  - Stage A: fix `grpo_n=3`, sweep `batch_size` in `3,4,5,6,10,15,20`
  - Stage B: pick best `batch_size` (by avg_reward) and sweep `grpo_n` in `2,3,4,5,6,7`
  - Default `rollout_concurrency=4` (stable on WSL/docker), auto-fallback to `4` on first failure

Example (preview commands only):
```bash
SQLITE_TMPDIR=/tmp TMPDIR=/tmp \
.venv/bin/python scripts/run_hyperparam_sweep.py \
  --config_name chem_performance_single \
  --dataset chem_performance_v2_350_noher_co2rr \
  --truncate 30 \
  --epochs 1,2 \
  --batch_sizes 10,30 \
  --grpo_ns 1,3 \
  --dry_run
```

Example (execute; requires `--yes` for larger grids):
```bash
CHEM_GRPO_RAG_ENABLED=1 \
SQLITE_TMPDIR=/tmp TMPDIR=/tmp \
.venv/bin/python scripts/run_hyperparam_sweep.py \
  --epochs 1,2 \
  --batch_sizes 10,30 \
  --grpo_ns 1,3 \
  --yes
```

Tip (cost control):
- For early hyperparam sweeps, consider using a balanced subset dataset (e.g. 9 reactions * 50 = 450 samples)
  so you get multi-reaction coverage with predictable cost. Then confirm top candidates on the full dataset.

Tip (retrieval coverage):
- If your agent relies on the Chroma literature DB for evidence, align your experiment dataset with the
  reaction types that actually exist in the vector store. In this workspace's current Chroma collection,
  `reaction_type` coverage is: ORR/OER/EOR/UOR/HOR/HZOR/O5H, and it does NOT include HER/CO2RR yet.
- For “test / hyperparam” runs before adding HER/CO2RR literature, use a subset dataset that excludes
  HER and CO2RR (e.g. 7 reactions * 50 = 350).

Rationale:
- Changing these can dominate run-to-run differences and make “best hparams” comparisons meaningless.

## Recommended Run Metadata To Record

For each experiment, record at minimum:
- `experiment_name`
- `practice_dataset_name`
- `epochs`, `batch_size`, `grpo_n`, `rollout_data_truncate`
- model name + sampling (`temperature`, `top_p`)
- path of generated agent config YAML

If you use `spec-bank/experience_export.md`, those fields map directly to export format.

## Model / Provider Notes (Avoid “model_not_found”)

Training-Free GRPO loads its default agent from the eval config (e.g. `configs/eval/chem/chem_performance.yaml`).
If your runtime provider does not support that default model name, override the agent config at runtime:

- Aliyun DashScope compatible-mode (DeepSeek-V3.2 thinking):
  - `python3 scripts/run_training_free_GRPO.py ... --agent_config practice/chem_performance_agent_aliyun_thinking`

Alternatively (recommended), use the dedicated practice config that already wires the Aliyun thinking agent:
- `python3 scripts/run_training_free_GRPO.py ... --config_name chem_performance_aliyun_thinking`

`--agent_config` accepts either:
- a Hydra agent config name under `configs/agents/` (recommended), or
- a direct YAML path under `configs/agents/` (convenience).
