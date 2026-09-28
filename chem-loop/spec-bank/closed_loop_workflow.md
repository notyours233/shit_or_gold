# Closed Loop Workflow (ChemCouncil Monorepo)

This document describes the intended end-to-end **closed loop** workflow in this repository.

Closed loop goal:
1) Use Training-Free GRPO to distill/update an **experience pack** (guidelines; `[G0]...[Gx]`).
2) Let MAD multi-agent debate reuse the experience pack while **recommending reaction types** and predicting performance.
3) Run real experiments and record measured results in a lab table (CSV or XLSX).
4) Feed experimental GT + debate traces back into GRPO to refresh the experience pack.

The loop is **file-based**: we exchange only YAML/JSON/CSV artifacts (no shared schema required).

## Components (Folders)

- `chemcouncil/`:
  - aiohttp backend + static frontend (one-click UX for experimenters)
  - wraps existing CLI flows into `/api/*` jobs
- `MAD/`:
  - multi-agent debate + rank mode (recommend reaction types)
  - optional literature RAG (Chroma)
  - uses `search_experience` to retrieve guidelines from experience packs
- `youtu-chem-loop/`:
  - single-agent Training-Free GRPO + verify/reward + experience distillation
  - experimental CSV/XLSX import -> processed JSONL -> dataset JSONL -> DB upload
  - syncs the completed experience pack to MAD after GRPO; it does not use MAD for GRPO rollouts

## Core Artifacts (Where They Live)

1) **Stable experience pack (canonical file name)**
- `youtu-chem-loop/configs/agents/practice/experience.yaml`
- synced into MAD:
  - `MAD/experience/experience.yaml`
- old packs are archived under:
  - `MAD/experience/archive/<timestamp>_<tag>/experience.yaml`

2) **MAD debate traces**
- per-reaction outputs (required for distillation): `MAD/outputs/result_*.json`
- rank summary (UI result): `MAD/outputs/rank_*.json`
- Important: `rank_*.json` is a summary; it does NOT necessarily contain full debate history.
  For distillation you need `result_*.json`, hence `--save-each-reaction`.

3) **Lab experimental records**
- CSV or XLSX provided by lab
- converted into processed JSONL and uploaded into the SQLite DB (`test.db`)

## Recommended Operational Flow (CLI)

### A) Generate/Update Experience Pack (GRPO)

Run Training-Free GRPO in `youtu-chem-loop/` against a dataset already uploaded into `test.db`.

Outputs:
- `youtu-chem-loop/configs/agents/practice/<experiment_name>_agent.yaml` (new agent pack)

### B) Export Stable `experience.yaml` + Sync to MAD

Run:
- `scripts/run_closed_loop.sh --seed_agent_yaml youtu-chem-loop/configs/agents/practice/<experiment_name>_agent.yaml --skip_debate_update`

This will:
- archive old `MAD/experience/*.yaml` into `MAD/experience/archive/...`
- write stable `experience.yaml` in both `MAD/experience/` and `youtu-chem-loop/configs/agents/practice/`

Normalization note (important):
- `export_experience_yaml.py` will, by default, **normalize chem-loop experience packs**:
  - prune format-only guidelines (e.g., `<think>/<answer>` tag rules, JSON key-matching reminders)
  - rewrite `agent.instructions` header into a canonical chem-loop contract (inputs + output contract + guideline list)
  - flag: `--normalize_chem_loop` (default true; can disable via `--no-normalize-chem-loop`)

### C) Recommend Reaction Types (MAD rank mode)

Run:
- `cd MAD && python main.py --components "Ni(69%),Co(19%),Fe(11%),Cu(0.4%),Zn(0.05%)" --rank-reactions --save-each-reaction`

### D) Distill Experiences From Debate Traces (pseudo-label signal)

Run:
- `scripts/run_closed_loop.sh --seed_agent_yaml <seed_agent_yaml> --debate_latest_n 2 --concurrency 1`

### E) Feed Back Experimental CSV/XLSX (experimental GT signal)

The backend workflow is:
1) import experimental CSV/XLSX -> processed JSONL
2) build dataset JSONL
3) upload dataset to DB
4) run GRPO (incremental seed) to update experience pack
5) sync stable `experience.yaml` into MAD

You can run it via:
- Web UI (recommended), or
- `scripts/run_experimental_update_from_xlsx.sh` (CLI helper)

## Web Workflow (Experimenter UI)

Start the web app:
- local dev: `./scripts/run_web.sh`
- docker: `./scripts/init_state.sh && docker compose up --build`

The UI has 3 pages:
- 推荐反应 / Recommendations
- 经验回流 / Experimental feedback (update experience pack)
- 经验库 / Experience library (current + history archive)
- 效果评估 / Analytics (prediction vs experiment)

Manual feedback note:
- In the manual feedback tab, users should select a previous recommendation first.
- The UI will include `recommendation_job_id` **per row** in the generated CSV.
  - Legacy/compat: when all rows share the same reco id, the UI may also send `recommendation_job_id=<rank_job_id>` as a form field.
  This enables `/api/analytics` to compute prediction-vs-experiment gaps even when one feedback update merges multiple recommendation sources.

## Operational Notes (Memory / RAG / Concurrency)

- Large Chroma DBs can be very memory-hungry.
- **RAG mode env-only switch**:
  - test/low-memory: `MAD_RAG_MODE=shared`
  - server/high-memory: unset `MAD_RAG_MODE` or set `MAD_RAG_MODE=per_agent`
- Even on a large server, increasing `CHEMCOUNCIL_JOB_CONCURRENCY` can multiply memory usage:
  - each job spawns a MAD process and loads Chroma
  - memory roughly scales with the number of concurrent jobs

## Cancellation

Jobs are cancellable (queued or running):
- API: `POST /api/jobs/{job_id}/cancel`
- UI: “停止任务 / Stop job” button on each workflow page

## Format Compliance (Structured Output) — Preflight Gate

Before running large GRPO sweeps or generating a full experience library, we want the rollout model
to produce **evaluable structured answers** at a high rate (target: **80–90%+**).

Definition (chem-performance regression tasks):
- answer object is extractable (`<answer>{...}</answer>` or structured JSON)
- keys match exactly (no missing / no extra)
- values are numbers-only, or become evaluable via the verifier's unit-repair pass (when unit hints exist)

How to measure (CLI; DB-based):
1) Run a small GRPO rollout (creates `evaluation_data` rows under `exp_id=<name>_epoch_0`).
2) Run the report (from `youtu-chem-loop/`):
   - `python3 scripts/db/report_format_compliance.py --db test.db --exp_id <name>_epoch_0 --stage judged`

How to *spot-check* the structured tool-call payload:
- `python3 scripts/db/inspect_conclude_payloads.py --db test.db --exp_id <name>_epoch_0 --stage judged --limit 5`

Quick end-to-end smoke (balanced 9 reactions; includes CO2RR both tasks):
- Docker helper: `scripts/run_balanced5_smoke.sh`
  - samples 5 per reaction_type (CO2RR: 5 per task)
  - runs GRPO once
  - writes reports under `state/reports/` and agent YAML under `state/experience_runs/`

## Analytics (Prediction vs Experiment)

Endpoint:
- `GET /api/analytics`

What it does:
- scans completed `experience_update` jobs with CSV uploads
- reads the upload CSV (real lab values) and links each row to its recommendation source via `recommendation_job_id` (per row; or legacy single field)
- loads the linked rank job result (predictions)
- computes unit-normalized error + standardized relative error + a score `exp(-rel_error)`
