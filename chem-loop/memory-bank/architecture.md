# Architecture (ChemCouncil Monorepo)

This document is the canonical reference for the **ChemCouncil** monorepo architecture used in this workspace.

Hard rules for contributors/agents:
- Read this file (`memory-bank/architecture.md`) and `memory-bank/design-document.md` before writing any code.
- After any major feature/milestone, update `memory-bank/architecture.md` (especially DB schema + dataflow).
- Prefer modular changes across multiple small files/modules; avoid monolithic ("one giant file") implementations.

## Scope

This architecture doc focuses on the parts relevant to:
- Dataset ingestion into SQLModel-backed storage (SQLite)
- Training-Free GRPO “practice” pipeline (rollouts -> verify -> distill chemistry-focused experiences)
- MAD multi-agent debate/rank (reaction recommendation)
- Web backend job orchestration (API wrapper around CLI workflows)

UI/docker details are out of scope unless they affect the DB schema or the core runtime dataflow.

## Key Directories (Repo Root)

- `chemcouncil/`: web backend (aiohttp) + static frontend (for experimenters)
  - wraps existing CLI flows into `/api/*` jobs (cancellable)
  - persists job artifacts under `state/jobs/<job_id>/`
  - job records are file-backed (`state/jobs/<job_id>/job.json`) and support **soft-delete** via `deleted_at_utc`
    - hidden jobs are excluded from experimenter-facing lists (recommendation history, analytics rounds) by default
  - current active experience pack for the Web UI is resolved with priority:
    1. `CHEMCOUNCIL_EXPERIENCE_PACK_PATH`
    2. `/state/experience_youtu.yaml` (Docker/shared persistent state)
    3. `youtu-chem-loop/configs/agents/practice/experience.yaml`
  - extra endpoints for experimenter workflow + evaluation:
    - `GET /api/recommendations` (list completed rank jobs)
    - `GET /api/analytics` (prediction vs experiment error stats, derived from linked jobs)
    - `POST /api/jobs/{job_id}/hide` / `POST /api/jobs/{job_id}/restore` (hide/restore a job without deleting artifacts)
    - `GET /api/experience/history` + `POST /api/experience/activate/{archive_id}` (browse + activate archived experience packs)
- `MAD/`: multi-agent debate + rank mode (reaction recommendation)
  - optional literature RAG (Chroma), controlled via env vars
  - uses `search_experience` to retrieve guideline packs (YAML) instead of prompt-stuffing
- `youtu-chem-loop/`: Training-Free GRPO + verify + data processing + external-engine adapters
  - `youtu-chem-loop/utu/`: core Python package (config/db/practice/verify/external engines)
  - `youtu-chem-loop/configs/`: Hydra YAML configs (eval/practice/agents/tools)
  - `youtu-chem-loop/scripts/`: CLI entrypoints (practice runner, dataset import/upload, closed-loop helpers)
  - `youtu-chem-loop/tests/`: pytest suite
  - `youtu-chem-loop/data/`: datasets and processed artifacts
- `memory-bank/`: canonical project docs in this workspace (only these must be kept up to date)
- `spec-bank/`: additional specs/contracts (data processing rules, metric key lists, etc.)
- `state/`: local persistent runtime state (used by docker/web flows)
  - `state/test.db`: SQLite DB for datasets + practice caches
  - `state/jobs/`: logs/uploads/results for web backend jobs
  - `state/chroma_db/`: (optional) external-mounted Chroma vector DB directory

### Material-Performance Source and Audit Gate (2026-07-28)

- Imported material-performance sources are kept immutable and local under
  `youtu-chem-loop/data/raw/material_performance_20260728/`:
  - `material_categories_full_20260706/`: re-extracted material identities for the established 15 directions
  - `batch3/`: material identities plus performance extractions for the four new directions
- The established 15-direction truth remains in:
  - `youtu-chem-loop/data/processed/chem_performance/chem_performance_dataset_v2.jsonl` (9 electrochemical)
  - `../material_property_extraction/results/final_review_package_20260415/all_results.jsonl` (6 material properties)
- The active unified literature database is `MAD/data/chroma_db/`, with collections
  `literature_agent1..4`. The prior split database is preserved at
  `MAD/data/chroma_db_legacy_split_20260728/` for rollback/comparison.
- `scripts/data/audit_material_performance_grpo_readiness.py` applies four diagnostic gates:
  1. deterministic material-to-truth binding (`direct`, `recoverable`, or `manual_review`)
  2. cross-record exact deduplication and indistinguishable-context conflict quarantine
  3. numeric parseability plus metric/unit contract checks
  4. primary-condition checks for the four new directions
- The shared candidate layer is `utu/data_processing/material_performance_candidates.py`; both audit keys and
  the dataset builder use the same deterministic material-binding representation. `direct` and
  deterministically `recoverable` candidates may proceed, while `manual_review` candidates remain excluded.
  Series/group/variable-composition material names are tracked as quality flags rather than silently treated
  as precise material identities.
- The imported material-object schema does not contain structured precursor, feed-ratio, preparation-method,
  or element-content fields. The material-name-centered builder uses `material_name` as its only mandatory
  prompt field and appends category, components, structure, elements, conditions, or synthesis fields only
  when present. It never fabricates missing optional fields.
- Audited outputs are local under `youtu-chem-loop/data/audits/material_performance_20260728/`; the durable
  human-readable report is `spec-bank/material_performance_grpo_readiness_audit_20260728.md`.
- GRPO samples must preserve normalized `doc_id`; literature RAG masks that DOI during rollout/evaluation.

### Material-Performance 19-Direction Dataset Build (2026-07-28)

- Entrypoint: `youtu-chem-loop/scripts/data/build_material_performance_19_dataset.py`.
- Core serialization: `youtu-chem-loop/utu/data_processing/material_performance_dataset.py`.
- Minimum automatic-ingestion contract: a uniquely bound material name, at least one numeric performance
  truth, task type, and normalized DOI. Test conditions and all synthesis fields are optional.
- Cross-record selection uses exact deduplication and indistinguishable-context conflict quarantine before
  any prompt is built. Ambiguous multi-material records are never expanded into multiple labels.
- Long-lived local artifacts under `youtu-chem-loop/data/processed/material_performance_19/`:
  - `material_performance_19_v1.jsonl`: canonical lossless records, including comparator and categorical labels
  - `material_performance_19_grpo_v1.jsonl`: current point-value verify-compatible DatasetSample records
  - `manifest_v1.json`: conservation counts and per-task output counts
  - `excluded_observations_v1.jsonl`: duplicate, conflicting, ambiguous, or otherwise excluded observations
- The current numeric verify has no interval semantics. One-sided bounds remain canonical-only; approximate
  values may enter as point estimates while preserving their comparator in `meta.metric_comparators`. HOR
  exchange-current values with mass-normalized or relative semantics also remain canonical-only so they are
  not mixed with the area-normalized `mA cm-2` regression target.
- Full field and comparator policy: `spec-bank/material_performance_19_dataset_contract.md`.

### Gated 19-Direction Formal Experience Build (2026-08-05)

- The selected formal GRPO parameters are fixed at `batch_size=19`, `grpo_n=3`, `epochs=1`, literature
  `RAG=1`, and `rollout_concurrency=4`. The formal population is 50 questions per task, 950 questions and
  2,850 prediction rollouts total. The formal runner also fixes a 300-second timeout per rollout attempt so
  an isolated stalled provider connection reaches the existing retry path without blocking a batch for 30 minutes.
- `youtu-chem-loop/scripts/data/sample_material_performance_19_formal.py` builds the versioned formal JSONL.
  It excludes every document in the existing 57-question hyperparameter validation JSONL, allocates scarce
  directions first, and enforces one selected row per `doc_id` across all 19 directions. Its manifest records
  source/exclusion hashes, ordered sample/document IDs, per-task counts, and zero-overlap assertions.
- `scripts/run_material_performance_19_formal.sh` is the only supported formal entrypoint. Its explicit stages
  are `--prepare-only`, `--canary-only`, `--formal`, `--resume`, and `--promote`; it never uses the legacy
  11,291-row default runner for this release.
- Before any formal launch, the entrypoint requires a passing isolated 19-question/57-rollout canary. Both
  canary and formal runs use `chem_performance_single` plus the empty experience seed. They do not sync or
  overwrite either stable `experience.yaml` pack.
- `youtu-chem-loop/scripts/db/audit_material_performance_19_run.py` verifies ordered dataset sample IDs,
  judged rollout counts, `grpo_n` group sizes, all 19 task directions, parseable answer objects, finite rewards,
  non-MAD trajectories, provider-error log markers, generated experience cards, HZOR state, and unchanged
  hashes for protected stable packs. Formal promotion additionally requires 19/19 experience-card task coverage.
- Promotion is a separate operation after a passing formal audit. It archives the prior stable packs and then
  exports the audited formal agent YAML through the existing closed-loop sync path.

Note (SQLite temp files):
- If you hit `unable to open database file` errors, set `SQLITE_TMPDIR=/tmp` and `TMPDIR=/tmp`.

## Runtime Dataflow (High Level)

### Dataset Ingestion

Typical flow:
1. (Audited base dataset) Build the 19-direction material-performance JSONL under
   `youtu-chem-loop/data/processed/material_performance_19/`:
   - every current GRPO sample has `material_name`, rendered `material_description`, `task_type`,
     `metrics_to_predict`, and numeric truth
   - all synthesis/composition/condition fields are optional and omitted when unavailable
   - ambiguous multi-material observations, conflicts, and point-incompatible bounds are quarantined
   - entrypoint: `youtu-chem-loop/scripts/data/build_material_performance_19_dataset.py`
2. (Closed loop / real experiments) Import lab experimental record tables (CSV/XLSX) into the feedback schema:
   - `youtu-chem-loop/scripts/data/import_experimental_csv.py --csv_path <file.csv>`
   - `youtu-chem-loop/scripts/data/import_experimental_xlsx.py --xlsx_path <file.xlsx>`
   - the preferred identity is required `material_name`; optional `material_input_json` preserves the
     original structured material input and `elements` is retained only when the experimenter supplied it
   - legacy `metals`-only CSV rows remain readable, but new rows are never rejected merely because they
     have no metals/elements and no elements are fabricated from a material formula
   - feedback accepts all 19 task directions and emits the same material-name-centered `INPUT_JSON` as
     the audited base dataset
   - CO2RR experimental rows can now carry an explicit triplet:
     - `product`
     - `faradaic_efficiency`
     - `partial_current_density`
   - For backward-compatible analytics, the web UI still mirrors CO2RR `partial_current_density` into the generic `value/unit` CSV columns.
   - outputs: `youtu-chem-loop/data/processed/chem_performance_experimental/*.jsonl`
3. Build an uploadable DatasetSample JSONL (question/answer/meta; `source="training_free_grpo"`):
   - `youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`
   - material-name rows use a single current task direction, including `CO2RR`; legacy metal-only CO2RR
     rows retain their historical split for backward compatibility
4. Upload dataset JSONL into the SQLite DB table `data` (`DatasetSample`):
   - `youtu-chem-loop/scripts/data/upload_dataset.py`

### Recommendation (MAD rank / debate)

Recommendation runs are executed by MAD (task-rank mode) and orchestrated either via CLI or via the web backend:
- CLI: `MAD/main.py --rank-tasks ...` (`--rank-reactions` remains a compatibility alias)
- Web: `chemcouncil/` spawns MAD as a background job and persists artifacts under `state/jobs/<job_id>/`.
- Recommendation input requires `material_name` and optionally accepts `major_category`, components,
  structural relationships, precursors, feed ratio, preparation method, explicit elements, element content,
  conditions, and a custom prompt. The user may provide any subset of the optional structured fields or
  only a custom prompt. Missing fields are omitted and `custom_prompt` is material data, never a replacement
  for system instructions or the debate/output protocol.
- Each debate runs exactly one `task_type`. Selecting one direction creates one independent four-agent debate;
  selecting a subset or all directions performs independent debates in the outer rank loop, bounded by the
  user-provided direction-level concurrency. The request preserves `selection_mode`, `direction_count`,
  `top_k_properties`, and `max_parallel_properties` in the job payload. Both numeric controls are capped to
  the number of selected directions.
- The outer rank result contains every completed direction in `ranking` and at most `top_k_properties` entries
  in `top_k`. Cross-direction ordering uses a unit-free score derived from each direction's calibrated grade
  (`normalized_score`, `ranking_basis="task_specific_grade"`); raw values are shown but never compared across
  incompatible units. `reaction_type`, `property_type`, `top_k_reactions`, and `max_parallel_reactions` remain
  readable compatibility aliases for older clients and history records.

For downstream feedback alignment and experience distillation you must preserve per-task traces:
- enable `--save-each-task` (default in the web backend; `--save-each-reaction` remains an alias)
- rank summaries (`rank_*.json`) may not include full debate history

### Prediction-vs-Experiment Analytics (Monitoring)

To validate whether the closed loop improves recommendation accuracy over time:
- Manual feedback submissions link experimental rows back to their recommendation source via `recommendation_job_id`:
  - preferred: **per-row** `recommendation_job_id` column in the uploaded CSV (supports merging multiple recommendation blocks into one update job)
  - legacy/compat: a single `recommendation_job_id` multipart field to `/api/experience/update` when all rows share one source
- The web backend records parsed IDs into the experience_update job payload (e.g., `recommendation_job_id` and/or `recommendation_job_ids`) in `state/jobs/<job_id>/job.json`.
- During an `experience_update`, the backend first runs the normal experimental-feedback incremental GRPO update, then (if linked recommendation jobs have saved `result_*.json` debate traces and can be aligned to scored feedback rows) performs an additional **error-aware trace distillation** pass seeded from the feedback-updated agent YAML.
  - This second pass does **not** blindly distill the raw recommendation trajectory.
  - Instead, it aligns:
    - the earlier MAD recommendation trace for the same `task_type` (legacy fields are still accepted)
    - the recommendation's predicted value
    - the actual experimental value from the feedback row
    - for CO2RR, it also carries `product` and `faradaic_efficiency` when those are available in the feedback CSV / recommendation summary
  - The resulting pseudo-rollouts are labeled with the real lab outcome and explicit prediction-vs-ground-truth error, so the extracted experiences focus on reducing future prediction error rather than only preserving debate heuristics.
- For non-destructive cleanup, an experience_update job may also store an **analytics-only ignore list**:
  - payload key: `analytics_ignore_csv_rows: list[int]` (1-based CSV row indices)
  - ignored rows are skipped in `/api/analytics` aggregation + plots
  - this does **not** modify the original `upload.csv` and does **not** roll back the experience pack
- `/api/analytics` scans linked jobs (experience_update -> recommendation) and computes:
  - unit-normalized absolute error
  - standardized relative error
  - score `exp(-rel_error)` for easy trend plotting
  - for CO2RR, raw parsing still keeps the two atomic metrics (`faradaic_efficiency`, `partial_current_density`) so feedback distillation can use them independently
  - but in the **analytics/UI aggregation path only**, a complete CO2RR row is collapsed into **one** evaluable record:
    - metric key: `co2rr_combined`
    - relative error: equal-weight mean of FE relative error and partial-current-density relative error
    - the record still carries display-only subfields so the UI can show both predicted/actual values in one row
  - note: hidden rounds (jobs with `deleted_at_utc`) are skipped by default

### Prompt Boundary (Eval/Practice)

- The model only receives `EvaluationSample.augmented_question` (a single string) during rollout.
- `DatasetSample.meta` is persisted to DB and copied onto `EvaluationSample.meta`,
  but it is not automatically appended to the prompt unless a processor explicitly renders it.
- GRPO rollouts do not receive the growing experience list. They predict from the held-out material prompt
  plus optional masked literature retrieval; `ExperienceUpdater` distills the grouped reward differences afterward.
- The resulting stable experience pack is synced to MAD and retrieved only during recommendation.
- Current experience cards use `MaterialCard` fields (`TASK`, `MATERIAL`, `ELEMENTS`, `TARGET`, `ANCHOR`,
  `CONTEXT`, `TAKEAWAY`, `HOW_TO_USE`, `CAVEATS`, `APPLIES`). Retrieval is hard-scoped to the current
  performance direction for new cards; legacy `CaseCard` data remains readable.

### External Rollout Engines (Optional)

Legacy evaluation experiments may delegate the *rollout* step to an external engine (e.g., MAD) while
reusing youtu-chem-loop's existing evaluation pipeline for:
- dataset loading + batching
- verify/reward computation
- experience distillation + export

In this workspace:
- `youtu-chem-loop/utu/eval/benchmarks/base_benchmark.py` checks `EvalConfig.agent.env.name`.
  - Normal/empty env uses the standard OpenAI Agents SDK `Agent + Runner` path.
  - If `env.name == "mad"`, it calls the subprocess adapter:
    - `youtu-chem-loop/utu/external_engines/mad_engine.py`
    - which runs `youtu-chem-loop/utu/external_engines/mad_runner.py` inside a MAD Python env.
- `TrainingFreeGRPO` rejects `env.name == "mad"`; the external branch is not a supported GRPO rollout path.
- Output/verify contract:
  - MAD is asked to call the `conclude` tool with a STRICT JSON payload:
    `{"think": "...", "answer": {...}}`
  - The adapter normalizes the structured JSON into legacy `<think>/<answer>` blocks for compatibility with:
    - chem verify (`youtu-chem-loop/utu/practice/verify/chem_performance_verify.py`)
    - experience distillation prompts (which expect a chat-style transcript)
  - Verify accepts both legacy tags and structured JSON (see `spec-bank/chem_verify_spec.md`).

Optional: literature retrieval inside external engines (MAD + masking)
- Some external engines (MAD) can call the same local literature DB used by youtu-chem-loop (Chroma + Voyage),
  but do so via a subprocess bridge to keep dependencies isolated.
  - Proxy (stdlib-only, safe to import from MAD venv): `youtu-chem-loop/utu/external_engines/chem_literature_proxy.py`
  - Runner (uses youtu-chem-loop Python env + `chem_literature_db` toolkit + doc-level masking):
    `youtu-chem-loop/utu/external_engines/chem_literature_runner.py`
- Doc-level masking is still enforced in code (not prompts):
  - `BaseBenchmark.rollout_one()` resolves the sample's `doc_id` (DOI) and passes it as `masked_doc_ids`
    to the external engine adapter.
  - The bridge runner/toolkit filters out any hit whose `metadata.doc_id` is masked and never exposes the
    masked list to the model.

### Practice (Training-Free GRPO)

Entry point: `youtu-chem-loop/scripts/run_training_free_GRPO.py`
1. Load `TrainingFreeGRPOConfig` via `ConfigLoader.load_training_free_grpo_config(...)`.
2. For each epoch and batch:
   - Load epoch data by duplicating dataset samples `pass_k` times into `evaluation_data` with `exp_id = "{exp_id}_epoch_{epoch}"`.
     - For small experimental uploads, the last partial batch still runs (so datasets smaller than `batch_size` are allowed).
   - Rollout: generate multiple responses per sample (group size = `grpo_n`).
     - All candidates are independent samples from one `type: simple` prediction agent.
     - Proposal/review/rebuttal/voting are not part of GRPO.
   - Tool calls: the single agent may call `chem_literature_db.literature_search` at most once when RAG is enabled.
   - Leakage masking (chem-performance only): during dataset rollouts, the runner may inject a per-sample `masked_doc_ids`
     list into the `chem_literature_db` toolkit config so the agent cannot retrieve the exact source paper that contains
     the ground-truth performance number (prevents label leakage).
     - Preferred: use `sample.meta.doc_id` directly (used by the 19-direction dataset and `chem_performance_v2`).
     - Fallback: for older datasets without `meta.doc_id`, resolve via `rawdata/2-cleaned-abstracts-about-*.tsv`.
   - Judge: run the verify function to compute `reward`.
   - Distill: `ExperienceUpdater` summarizes trajectories and distills **chemistry-focused** experiences (guidelines).
   - Persist:
     - experiences cached to DB (`cache_experience`)
     - generated agent config YAML written under `youtu-chem-loop/configs/agents/practice/`
3. The versioned 19-direction formal workflow first runs the 19-question canary, then starts or resumes the
   950-question run only after the canary audit passes. Stable recommendation packs remain protected until the
   formal audit and explicit promotion complete.

### Debate -> Experience (Closed Loop)

In the closed-loop workflow, multi-agent debate traces are treated as an additional
supervision signal for experience distillation:
- Each agent makes a *proposal* (prediction) with its own ReAct-style trajectory.
- Other agents generate *reviews* (critiques) pointing out flaws (e.g., wrong inference,
  tool misuse, unit errors).
- Proposals can be marked as `defeated` by the debate runner.

We distill "what went wrong" from defeated proposals into reusable experiences
that can be injected back into future agents (for rollouts and/or debate).

Current implementation (debate ingestion is file-based; no DB schema changes):
- Parser:
  - `youtu-chem-loop/utu/debate/langgraph_trace.py` loads LangGraph JSON exports and extracts:
    - proposals (`type="propose"`)
    - valid critiques/reviews targeting each proposal (`type="review"`, `valid=true`)
    - proposal status from `result.{surviving,defeated,withdrawn}_proposals`
- Distillation/update script:
  - `youtu-chem-loop/scripts/debate/update_experiences_from_debate.py`
  - Converts proposals into pseudo-`EvaluationSample` rollouts:
    - `reward=1.0` for surviving proposals; `reward=0.0` for defeated proposals
    - `trajectories` stores the proposal's `steps` list (ReAct trace)
    - `reasoning` stores aggregated valid critiques targeting that proposal
    - `correct_answer` is an explicit "pseudo label" summary of debate outcome (NOT experimental GT)
  - Runs `youtu-chem-loop/utu/practice/experience_updater.py` (`ExperienceUpdater`) to extract/merge experiences and writes a new agent YAML
    under `youtu-chem-loop/configs/agents/practice/` (plus optional JSON report artifacts).

Safety note:
- Debate-derived labels are *not* experimental ground truth. They are used to distill robust,
  generally-applicable guidance (e.g., chemistry heuristics + tool-use + unit discipline), and should be
  validated against real experimental results when available.

Interop note (MAD in this monorepo):
- MAD debate traces live under `MAD/outputs/` (e.g. `result_*.json`).
- For operational simplicity we maintain stable experience pack file names:
  - `MAD/experience/experience.yaml`
  - `youtu-chem-loop/configs/agents/practice/experience.yaml`
- In Docker/Web deployment we also mirror the active stable pack into:
  - `/state/experience_youtu.yaml`
  - `/state/experience_mad.yaml`
  so the frontend/API always reads the same latest promoted pack from persistent state.
- Old packs are archived under `MAD/experience/archive/<timestamp>_<tag>/experience.yaml`.

## Database

### Connection

DB access is via SQLModel and configured by:
- Environment variable: `UTU_DB_URL`
- Engine helper: `youtu-chem-loop/utu/utils/sqlmodel_utils.py` (`SQLModelUtils.get_engine()`)

`SQLModelUtils._init_db_schema()` calls `SQLModel.metadata.create_all(engine)` to ensure tables exist.

### Tables (Complete Schema)

The schema below is derived from `youtu-chem-loop/utu/db/*.py`.

#### Table: `data` (`DatasetSample`)

Defined in: `youtu-chem-loop/utu/db/eval_datapoint.py`

- `id` (int, PK)
- `dataset` (str): dataset name
- `index` (int, nullable): index within dataset
- `source` (str): source dataset name for mixed datasets
- `source_index` (int, nullable): index within the source dataset
- `question` (str)
- `answer` (str, nullable)
- `topic` (str, nullable)
- `level` (int, nullable)
- `file_name` (str, nullable)
- `meta` (JSON, nullable): arbitrary extra metadata (dict-like)

#### Table: `evaluation_data` (`EvaluationSample`)

Defined in: `youtu-chem-loop/utu/db/eval_datapoint.py`

- `id` (int, PK)
- `created_at` (datetime, nullable)
- `updated_at` (datetime, nullable)

Base info:
- `dataset` (str)
- `dataset_index` (int, nullable)
- `source` (str)
- `raw_question` (str)
- `level` (int, nullable)
- `augmented_question` (str, nullable)
- `correct_answer` (str, nullable)
- `file_name` (str, nullable)
- `meta` (JSON, nullable)

Rollout:
- `trace_id` (str, nullable)
- `trace_url` (str, nullable)
- `response` (str, nullable)
- `time_cost` (float, nullable)
- `trajectory` (str, nullable): deprecated (single-agent)
- `trajectories` (str, nullable): JSON string for multi-agent trajectories

Judgement:
- `extracted_final_answer` (str, nullable)
- `judged_response` (str, nullable)
- `reasoning` (str, nullable)
- `correct` (bool, nullable)
- `reward` (float, nullable)
- `confidence` (int, nullable)

Control:
- `exp_id` (str): experiment id (default: "default")
- `stage` (str): stage marker, typically one of `init` / `rollout` / `judged`

#### Table: `cache_experience` (`ExperienceCacheModel`)

Defined in: `youtu-chem-loop/utu/db/experience_cache_model.py`

- `id` (int, PK)
- `experiment_name` (str)
- `step` (int)
- `epoch` (int, nullable)
- `batch` (int, nullable)
- `experiences` (JSON, nullable): distilled experiences payload
- `timestamp` (float)
- `datetime` (str)

#### Table: `cache_tool` (`ToolCacheModel`)

Defined in: `youtu-chem-loop/utu/db/tool_cache_model.py`

- `id` (int, PK)
- `function` (str)
- `args` (str, nullable)
- `kwargs` (str, nullable)
- `result` (JSON, nullable)
- `cache_key` (str)
- `timestamp` (float)
- `datetime` (str)
- `execution_time` (float)

#### Table: `tracing_tool` (`ToolTracingModel`)

Defined in: `youtu-chem-loop/utu/db/tracing_model.py`

- `id` (int, PK)
- `trace_id` (str)
- `span_id` (str)
- `name` (str)
- `input` (JSON, nullable)
- `output` (JSON, nullable)
- `mcp_data` (JSON, nullable)

#### Table: `tracing_generation` (`GenerationTracingModel`)

Defined in: `youtu-chem-loop/utu/db/tracing_model.py`

- `id` (int, PK)
- `trace_id` (str)
- `span_id` (str)
- `type` (str): "chat.completions" or "responses"
- `input` (JSON, nullable)
- `output` (JSON, nullable)
- `model` (str)
- `model_configs` (JSON, nullable)
- `usage` (JSON, nullable)
- `response_id` (str, nullable)

#### Table: `trajectory` (`TrajectoryModel`)

Defined in: `youtu-chem-loop/utu/db/trajectory_model.py`

- `id` (int, PK)
- `trace_id` (str, nullable)
- `trace_url` (str, nullable)
- `d_input` (str, nullable)
- `d_output` (str, nullable)
- `trajectories` (str, nullable): JSON string
- `time_cost` (float, nullable)

## Modularity Guidelines (Anti-Monolith)

When adding new functionality:
- Split by responsibility: config, core logic, verification, and CLI should live in separate modules/files.
- Avoid adding large "god files" (e.g., dumping multiple subsystems into one `utils.py`).
- Prefer adding a small module with a clear name over extending an unrelated module.
- Keep verify/reward logic isolated (e.g., `youtu-chem-loop/utu/practice/verify/<domain>.py`) so it can be swapped without touching the practice orchestrator.

## Change Checklist (When You Finish a Milestone)

Update `architecture.md` if you:
- add/rename DB tables or columns
- change the eval/practice dataflow (new stages, new caching rules)
- introduce new long-lived artifacts (new config outputs, new caches)

## Config Loading & Verify Wiring (Implementation Notes)

This section documents where things are wired so future contributors can trace config -> runtime behavior quickly.

### Hydra Config Loading

- Entry point: `youtu-chem-loop/utu/config/loader.py` (`ConfigLoader`)
  - Uses Hydra `initialize(...)/compose(...)` and `OmegaConf.resolve(...)` to produce a resolved dict, then validates into Pydantic models (e.g., `EvalConfig`, `TrainingFreeGRPOConfig`, `ToolkitConfig`).
  - Implication: `${oc.env:...}` interpolations must either be present in env or provide defaults; otherwise config loading fails before any runtime logic executes.

### Judge Model (ChemCouncil)

ChemCouncil’s chem-performance workflows use a **non-LLM verify** function, so there is no separate “judge model”.
All rollout/distillation LLM calls are controlled by the shared env vars:
- `UTU_LLM_API_KEY`, `UTU_LLM_BASE_URL`, `UTU_LLM_MODEL` (and optionally `UTU_LLM_TYPE`)

### Training-Free GRPO Custom Verify Function

- Processor: `youtu-chem-loop/utu/eval/processer/training_free_grpo_processor.py`
  - Defines `VERIFY_DIR = youtu-chem-loop/utu/practice/verify/`
  - Loads the verify function dynamically at init time from:
    - `verify_path = VERIFY_DIR / EvalConfig.verify_filename`
    - `verify_func = getattr(module, EvalConfig.verify_func_name)`
  - Calls verify during `judge_one(...)`, supporting both sync and async functions.
  - Expected return: dict with at least `reward: float` (defaults to `0.0` if missing); optional `reasoning` is stored to DB and can be used by the experience distillation stage.

Chem-performance verify implementation in this workspace:
- Entrypoint (configured via `verify_filename`): `youtu-chem-loop/utu/practice/verify/chem_performance_verify.py`
- Helper modules (parsing/alignment/reward): `youtu-chem-loop/utu/practice/verify/chem_performance_lib/`

Implementation gotchas:
- The processor loads the verify file via `importlib` under a synthetic module name (currently `"verify_module"`).
  This means relative imports inside the verify file are brittle; prefer absolute imports.
- Avoid naming a package directory the same as the verify entrypoint module (e.g. `chem_performance.py` vs `chem_performance/`),
  otherwise Python import resolution can shadow the module and break imports/tests.

## Chem Performance Configs (This Workspace)

These configs wire DB dataset -> agent rollout -> verify -> GRPO loop:
- Agent: `youtu-chem-loop/configs/agents/practice/chem_performance_agent_single.yaml`
- Eval (dataset + verify): `youtu-chem-loop/configs/eval/chem/chem_performance_single.yaml`
- Practice (GRPO loop): `youtu-chem-loop/configs/practice/chem_performance_single.yaml`
- Historical `*_mad.yaml` configs are retained for explicit evaluation reproducibility, but cannot be used by
  `TrainingFreeGRPO`.

### Toolkits (Literature + Experience)

- Literature toolkit config (multi-backend):
  - `youtu-chem-loop/configs/tools/chem_literature_db.yaml`
  - Backend selection is env-driven (see `spec-bank/chem_literature_db_tool.md`).
- Experience retrieval is recommendation-only and implemented inside MAD:
  - Stable packs:
    - `MAD/experience/experience.yaml`
    - `youtu-chem-loop/configs/agents/practice/experience.yaml`

### Legacy Chem-Performance Offline Data Processing

This workspace retains a metal/reaction-centered offline preprocessing path under
`youtu-chem-loop/data/processed/chem_performance/` for historical records. New production GRPO data uses
the material-name-centered 19-direction pipeline described above; the legacy path is compatibility-only.

Spec docs (contracts):
- `spec-bank/data_layout.md`: raw vs processed file layout conventions
- `spec-bank/material_performance_19_dataset_contract.md`: current material-name-centered 19-direction base-data contract
- `spec-bank/experimental_csv_contract.md`: current material-name-centered feedback/import contract
- `spec-bank/chem_dataset_contract.md`: historical reaction/metals compatibility contract
- CO2RR task split in the current code path:
  - Task 1: `{"product": "<LABEL>", "faradaic_efficiency": <fraction>}` (FE may be omitted only for backward-compatible legacy labels)
  - Task 2: `{"partial_current_density": <value>}`
- `spec-bank/chem_metrics_keys.md`: metric key vocabulary to prevent key drift
- `spec-bank/data_processing_rules.md`: deterministic cleaning/normalization rules

Implementation (code):
- `youtu-chem-loop/utu/data_processing/chem_performance/constants.py`
  - `REACTION_TYPES` enum-like set for validation
  - `NON_METRIC_KEYS` list so metadata fields never leak into metric dictionaries
  - `O5H_KEY_ALIASES` for key casing normalization
- `youtu-chem-loop/utu/data_processing/chem_performance/metals.py`
  - canonicalizes element symbol casing, deduplicates and sorts `metals`
- `youtu-chem-loop/utu/data_processing/chem_performance/metrics.py`
  - metric key canonicalization (O5H)
  - metric value normalization: key-aware units (e.g., overpotential->mV, potential->V, %->fraction_0_to_1)
  - parseability rule: metric strings must begin with a numeric literal
- `youtu-chem-loop/utu/data_processing/chem_performance/processor.py`
  - `process_raw_record`: core per-record cleaning; drops records with zero evaluable metrics
- `process_jsonl_file` / `process_directory`: batch processing for JSONL files
- `youtu-chem-loop/scripts/data/process_chem_performance_data.py`
  - CLI entrypoint for processing into `youtu-chem-loop/data/processed/chem_performance/*.jsonl` and printing stats
- `youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`
  - CLI entrypoint for converting processed records into an uploadable DatasetSample JSONL (default format)

## Source-Only Distribution (2026-09-28)

This publication copy intentionally excludes real environment files, vector stores,
SQLite/runtime state, original and processed datasets, trained experience packs,
and exported per-run agent YAMLs. Blank credential templates and static prompt/config
files remain available. No application dataflow or database schema changes are introduced.

Provision model credentials, matching Chroma collections, and audited experience packs
separately before restoring the full workflow. `scripts/init_state.sh` can create empty
placeholder packs for setup; these are not the trained production experience library.
See the publication root `SOURCE_RELEASE.md` for the source/data/security boundary.
