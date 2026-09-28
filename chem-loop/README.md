# ChemCouncil (Monorepo Workspace)

ChemCouncil is an end-to-end material-property **recommendation loop**:

1) run **training-free GRPO** on the extracted material-property performance database to distill an **experience library** (guidelines like `[G0]`)
2) export a stable pack `experience.yaml` and sync it into the debate/rank project
3) run MAD recommendation/ranking with both the experience library and literature RAG available

Directory layout:

- `youtu-chem-loop/`: training-free GRPO + experience distillation + data/DB tooling + closed-loop scripts
- `MAD/`: recommendation-time multi-agent debate + ranking (“rank mode”) consuming `experience.yaml`

Chinese README: `README_ZH.md`.

---

## 0) One env file + one venv (recommended)

All subprojects load env via `python-dotenv` and will search for `.env` in the current
directory and its parents. So we keep exactly **one** `.env` at monorepo root.

### 0.1 Create `.env`

```bash
cd ChemCouncil
cp .env.example .env
# edit .env and fill your API keys
```

Minimum required keys:

- `UTU_LLM_API_KEY`
- `UTU_LLM_BASE_URL`
- `UTU_LLM_MODEL`

Optional (literature RAG / embeddings):

- `VOYAGE_API_KEY` (needed if you enable Chroma-based literature RAG)

Optional (MAD debate/rank providers):

- `OPENAI_API_KEY` (ZenMux key for agent1 in the default config)
- `DEEPSEEK_API_KEY` (Alibaba Cloud DashScope-compatible key for agent2)
- `GOOGLE_API_KEY` (ZenMux key for agent3 in the default config)
- `QWEN_API_KEY` (Alibaba Cloud DashScope-compatible key for agent4)

### 0.2 Install dependencies (ONE venv for everything)

```bash
cd ChemCouncil
./scripts/setup_venv.sh
source .venv/bin/activate
```

---

## Web UI (backend + frontend)

This repo includes a minimal web app (aiohttp backend + static frontend) that wraps:

- **Experience build**: extracted performance JSONL → GRPO dataset → Training-Free GRPO → synced `experience.yaml`
- **Recommendation**: MAD rank mode (`MAD/main.py --rank-reactions`) across the six material-property directions
- **Experimental feedback**: upload CSV/XLSX (or select a previous recommendation) → build dataset → incremental GRPO update → refresh `experience.yaml`
- **Analytics**: prediction vs experiment error stats (per feedback round)
- Lab-friendly UI: separate pages (recommend / feedback / experience / analytics), bilingual (ZH/EN), light/dark theme, and experience history browsing

### Run locally (recommended for development)

```bash
cd ChemCouncil
./scripts/run_web.sh
```

Then open:

- `http://localhost:8000`

### Run with Docker (recommended for users who don’t want to install deps)

```bash
cd ChemCouncil
./scripts/init_state.sh
docker compose up --build
```

Notes:

- Create `.env` first (`cp .env.example .env`) and fill your API keys.
- The Docker image ships **code only**; persistent data (experience packs + literature DB + sqlite DB) must live on the host (or another server/volume).
- `docker-compose.yml` mounts `./state/` to `/state` and the container wires expected paths via symlinks:
  - `test.db` → `/state/test.db`
  - `MAD/data/chroma_db` → `/state/chroma_db`
  - `experience.yaml` packs → `/state/experience_*.yaml`
  - job logs/uploads/results → `/state/jobs`
- `docker-compose.yml` also forces `UTU_DB_URL=sqlite:////state/test.db` so all subprocesses (with different `cwd`) share the same DB.
- Docker does not ship a repo-local `.venv`, so `docker-compose.yml` also forces `MAD_PYTHON_BIN=/usr/local/bin/python`.
- **Memory note (important for large Chroma DBs)**:
  - Server default / lower-memory: set `MAD_RAG_MODE=shared` to reuse the verified Voyage-backed `literature_agent2` collection
  - Optional high-memory mode: set `MAD_RAG_MODE=per_agent` only after all four embedding routes have been verified
  - Each material recommendation job starts an independent MAD process and may load Chroma. `CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY` (default 10) controls how many material cards run at once; lower it to 2–5 on a smaller server.
  - The form's “directions evaluated concurrently” setting controls concurrency inside one material. The two levels multiply model calls and memory (for example, 10 materials × 3 directions can approach 30 direction-level tasks).
  - `CHEMCOUNCIL_JOB_CONCURRENCY` controls general experience-generation/feedback-update jobs and does not serialize the recommendation pool. GRPO uses single-agent calls; its `rollout_concurrency` mainly affects API and local retrieval load.
- Batch recommendation accepts up to 10 material cards. The browser submits and polls cards concurrently, while the backend enforces the separate recommendation pool described above.
- Optional auth: set `CHEMCOUNCIL_API_TOKEN` and pass `Authorization: Bearer <token>` to `/api/*`.

## 1) Material-Property Experience Generation (Before Recommendation)

For the material-property project, the normal workflow is:

1. Convert the extracted performance database into a GRPO dataset.
2. Sample 50 records for each of the 6 material-property directions, producing a balanced 300-row dataset.
3. Run a parameter test before the final experience build and choose `batch_size` / `grpo_n`.
4. Run Training-Free GRPO to distill/update the experience library.
5. Sync the stable `experience.yaml` into `MAD/experience/`.
6. Run MAD recommendation/ranking with both `search_experience` and literature RAG available.

Prepare/upload the material-property dataset without model calls:

```bash
cd ChemCouncil
./scripts/run_material_property_experience.sh --prepare-only
```

The default prepared dataset is:

```text
dataset_name = material_property_bal50_seed20260521
JSONL        = youtu-chem-loop/data/processed/material_property/material_property_bal50_seed20260521.jsonl
size         = 6 directions x 50 records = 300 rows
```

The parameter test defaults to a balanced small sample of 10 records per direction (60 rows total) to control model cost. The final experience build still uses 50 records per direction (300 rows). Preview the parameter test without model calls:

```bash
cd ChemCouncil
./scripts/run_material_property_param_test.sh --dry-run
```

Then run the two-stage parameter test:

```bash
cd ChemCouncil
./scripts/run_material_property_param_test.sh
```

The helper writes Stage A / Stage B summaries and a recommended final command under `state/reports/`.

To run the parameter test on the full 300-row dataset as well:

```bash
cd ChemCouncil
TEST_SAMPLES_PER_PROPERTY=50 ./scripts/run_material_property_param_test.sh
```

Run a small smoke if you only want to confirm the environment before a full experience build:

```bash
cd ChemCouncil
CHEM_GRPO_RAG_ENABLED=0 TRUNCATE=2 BATCH_SIZE=2 GRPO_N=1 ROLLOUT_CONCURRENCY=1 \
  EXP_NAME=material_property_smoke_no_rag \
  ./scripts/run_material_property_experience.sh --fresh
```

Run the default material-property GRPO build and sync the resulting experience pack:

```bash
cd ChemCouncil
./scripts/run_material_property_experience.sh --fresh
```

The default dataset is `material_property_bal50_seed20260521`, built from:

```text
../material_property_extraction/results/final_review_package_20260415/all_results.jsonl
```

The default literature collection is:

```text
MAD/data/chroma_db/material_property_literature_agent2
```

## 2) Legacy Experience Generation (training-free GRPO)

### 1.1 Smoke run

```bash
cd ChemCouncil
./scripts/run_grpo_smoke.sh
```

### 1.2 Full v5 experience build (500 samples)

If this is a **fresh DB** (e.g. you just cloned and `test.db` does not exist yet), upload the v5_500 dataset first:

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.data.upload_dataset \
  --file_path data/processed/chem_performance/chem_performance_dataset_v5_500.jsonl \
  --dataset_name chem_performance_v5_500 \
  --data_format default
```

Then run:

```bash
cd ChemCouncil
./scripts/run_full_v5_500.sh
```

This script includes:

- preflight checks on DB dataset size (to avoid duplicate uploads)
- `tee` logs
- rerun hints (`--fresh`, `--resume`, `--restart_step`, lowering concurrency, etc.)

### 1.3 Custom GRPO run (CLI)

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.run_training_free_GRPO \
  --config_name chem_performance_single \
  --experiment_name single_agent_smoke \
  --practice_dataset_name chem_performance_v5_500 \
  --epochs 1 \
  --batch_size 20 \
  --grpo_n 6 \
  --rollout_data_truncate 40 \
  --rollout_concurrency 4 \
  --restart_step 0
```

Key knobs:

- `--rollout_concurrency`: how many rollouts run in parallel (faster but easier to hit rate limits)
- `--restart_step`: `0` = clean run; omit for reusing caches

---

## 2) Inspect results (offline)

Summarize experiments in `test.db`:

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.db.summarize_experiments --exp_prefix mad_hp_v5_ --order avg_reward_desc
```

---

## 3) Debate / rank (optional)

The debate/ranking system lives in `MAD/`.

- debate mode: `--components ... --reaction-type conductivity`
- rank mode: `--components ... --rank-reactions` (runs debates for multiple property types and returns Top-K)

Example (rank mode + save per-reaction traces):

```bash
cd ChemCouncil/MAD
python main.py \
  --components "Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)" \
  --rank-reactions \
  --property-types "photothermal_conversion_efficiency,conductivity,thermal_conductivity,ferromagnetism,ferrimagnetism,antiferromagnetism" \
  --save-each-reaction \
  --max-parallel-reactions 3
```

If you want `youtu-chem-loop` to distill experiences from these traces, you MUST use
`--save-each-reaction` so `outputs/result_*.json` exists.

---

## 4) Closed-loop helper (sync experience.yaml + distill from debate traces)

```bash
cd ChemCouncil
./scripts/run_closed_loop.sh
```

---

## 5) Experimental CSV feedback (ingestion)

Convert a lab-record CSV to processed JSONL, then build+upload a dataset, then re-run GRPO
on the new dataset.

See `README_ZH.md` for a complete walkthrough.

---

## Security Notes

- Never commit `.env` (secrets). It is gitignored.
- Local secret backups are stored under `chem-loop/.local/` (gitignored).
- Large local artifacts (e.g. `MAD/data/chroma_db/`, `youtu-chem-loop/test.db`) are **gitignored by default**
  so the repo can be pushed to GitHub. Keep them locally or distribute via Git LFS / download scripts if needed.
