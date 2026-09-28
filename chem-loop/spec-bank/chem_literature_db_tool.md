# Chem Literature DB Tool Spec

This spec defines the agent-facing tool contract for accessing an **external literature database** during chem-performance rollouts.

## Goal

Enable the chem-performance agent to retrieve supporting evidence (titles/abstracts/metadata) from a literature DB during reasoning, while keeping the final answer format strict:
- output MUST remain machine-parseable (either legacy `<answer>...</answer>` tags or structured JSON)
- numeric regression answers must be numbers only (no units, no strings)

## Toolkit Name

- Toolkit key/name: `chem_literature_db`
- Implementation: `youtu-chem-loop/utu/tools/chem_literature_db_toolkit.py`

## Backends

The toolkit supports two backends (selected by `toolkits.chem_literature_db.config.backend`):

1) `sqlite` (default)
- External SQLite DB file containing paper metadata/content.
- Offline: no network required.
- Best for: your literature DB is already tabular (title/abstract/fulltext paths).

2) `chroma`
- Local persistent Chroma directory containing chunk-level documents + metadata.
- Requires **query embeddings** via the Voyage API (`VOYAGE_API_KEY` + model name).
- Best for: you already have a vector store (this workspace: `MAD/data/chroma_db/`).

## Tools (Functions)

### 1) `literature_healthcheck() -> dict`

Purpose:
- Debug whether the DB path and schema are reachable.

Returns (dict):
- `ok`: bool
- when `backend=sqlite`:
  - when `ok=true`: `db_path`, `table`, `columns`
  - when `ok=false`: `error` (+ best-effort `db_path`/`table`)
- when `backend=chroma`:
  - when `ok=true`: `persist_directory`, `collection_name`, `available_collections`, `count`
  - when `ok=false`: `error` (+ best-effort `persist_directory`/`collection_name`)
  - plus embedding status fields: `voyage_model`, `voyage_input_type`, `voyage_api_key_set`

### 2) `literature_search(query: str, limit: int = 5, reaction_type: str|None = None, max_distance: float|None = None) -> list[dict]`

Purpose:
- Find potentially relevant papers for the current problem.

Recommended query construction:
- Include `metals`, `reaction_type`, metric names (and `product` for CO2RR).
  Example: `"La HER overpotential"` or `"CO2RR Bi HCOOH faradaic_efficiency"`

Returns:
- Backend `sqlite`:
  - list of paper records, each with best-effort fields:
    - `paper_id` (string or int-like)
    - `title` (string)
    - `abstract` (string, may be null/empty)
    - `abstract_snippet` (string, truncated)
    - optional: `doi`, `year`, `url`, `file_path`
    - `score` (float, heuristic keyword match score)

- Backend `chroma`:
  - list of chunk records, each with best-effort fields:
    - `doc_id` (string; often DOI-like)
    - `reaction_type` (string)
    - `chunk_id` (int-ish)
    - `total_chunks` (int-ish)
    - `distance` (float; cosine distance; smaller is better)
    - `confidence` (float; best-effort `1 - distance`)
    - `text` (string; truncated snippet)
  - Important safety behavior:
    - the toolkit applies a `max_distance` threshold by default
    - if no chunk passes the threshold, it returns an explicit “no results / low confidence” payload:
      `[{ "ok": true, "hit": false, "message": "...", ... }]`

Failure mode:
- returns a one-element list like `[{ "error": "..." }]` (no exception thrown).

## Leakage Masking (Train/Eval Only)

### Motivation

For the chem-performance task, the ground-truth performance numbers often come from a specific paper.
If the agent can retrieve that exact paper/chunk, it can **copy the answer** instead of producing a
prediction based on reasoning + generalization. This is *label leakage* and will invalidate both:
- Training-Free GRPO rollouts (experiences become “just search the paper”)
- Evaluation metrics (Pass@k becomes artificially high)

### Scope (Explicit)

Masking is enabled **only** when running dataset rollouts (Training-Free GRPO practice and eval).
It is **not** enabled for the interactive chat CLI by default.

### Contract

Masking is enforced on the **tool side**, not by model instructions:
- The LLM MUST NOT be asked to “avoid certain papers”.
- The LLM MUST NOT receive the masked DOI/doc_id list (that would leak labels).

Implementation contract (toolkit config, injected by the runner):
- `toolkits.chem_literature_db.config.masked_doc_ids: list[str]`
  - A list of `doc_id` values (typically DOI strings) that MUST be excluded from tool outputs.
  - This field is NOT a tool argument; it is injected programmatically per-sample during rollouts.

Backend behavior:
- `backend=chroma`:
  - `literature_search` MUST filter out any candidate whose `doc_id` is in `masked_doc_ids`.
  - If all candidates are filtered (or all are low-confidence), it MUST return the explicit “no hit” payload:
    `[{ "ok": true, "hit": false, "message": "...", ... }]`
- `backend=sqlite` (optional but recommended for consistency):
  - `literature_search` SHOULD filter out any record whose `doi`/`paper_id` matches the masked list.

### Source Of Truth For Sample -> doc_id Mapping (Chem-Performance)

There are two supported ways to resolve `sample -> doc_id`:

1) Preferred (fast path): store it directly in the dataset
- For `chem_performance_v2` and later, the dataset samples SHOULD include:
  - `DatasetSample.meta.doc_id` (a DOI-like string)
- During train/eval rollouts, the runner reads `meta.doc_id` directly and injects it into
  `toolkits.chem_literature_db.config.masked_doc_ids` (no runtime TSV scan).

2) Backward-compatible (fallback): rawdata TSV join (optional)
- For older datasets (e.g. `chem_performance_v1`) where `meta.doc_id` is missing, the runner can resolve it from local TSV files under:
  - `youtu-chem-loop/rawdata/2-cleaned-abstracts-about-<REACTION_TYPE>.tsv`
  - Note: `rawdata/` is not shipped in the repo by default; this is an optional local artifact.

Columns:
- `index`: sample id (matches the chem-performance record `meta.id`)
- `doi`: the DOI string (used as `doc_id` in Chroma)

Example:
- Sample meta: `{"id": "108", "reaction_type": "OER", ...}`
- Mapping row: `index=108 -> doi=10.3390/nano13233076`
- During rollout, the runner injects:
  - `masked_doc_ids=["10.3390/nano13233076"]`

### 3) `literature_get(paper_id: str, chunk_id: int|None = None, limit: int = 5) -> dict`

Purpose:
- Fetch one paper record for deeper inspection after `literature_search`.

Returns:
- Backend `sqlite`:
  - dict with `paper_id`, `title`, `abstract`, and optional fields (`doi/year/url/file_path`).
- Backend `chroma`:
  - dict with `doc_id` and `chunks` (each chunk has `doc_id/reaction_type/chunk_id/total_chunks/text`).

Failure mode:
- returns `{ "error": "..." }` (no exception thrown).

## External SQLite DB Contract (Minimum)

The toolkit targets an **external SQLite DB file** (not the main `test.db` unless you intentionally point it there).

The schema is configurable via toolkit config, but the minimum requirement is a table with:
- `paper_id` (unique id)
- `title`
- `abstract`

Optional columns (if present and configured) will be included in tool outputs:
- `doi`, `year`, `url`, `file_path`, plus any `extra_columns`

Important:
- This toolkit does NOT require SQLite FTS; it uses portable `LIKE` matching for search.

## Configuration

Tool config is controlled by:
- Agent config: `youtu-chem-loop/configs/agents/practice/chem_performance_agent_mad.yaml`
- Toolkit config file: `youtu-chem-loop/configs/tools/chem_literature_db.yaml`
- Environment variable: `CHEM_LITERATURE_DB_PATH` (recommended way to set DB path)

If `CHEM_LITERATURE_DB_PATH` is unset, the toolkit will return an error payload instead of crashing.

### Tool Call Budget (Loop Prevention)

Some models (especially “thinking mode” models) may repeatedly call the same tool to “double-check”
even after they already have enough evidence. This can:
- waste tokens/cost
- exceed `max_turns` and crash dataset rollouts/CLI

To make runs stable, the toolkit supports a per-tool call budget enforced at runtime (not just via prompt rules).

Config keys (inside `toolkits.chem_literature_db.config`):
- `tool_call_limits` (dict, optional): per-tool max calls in a single run
  - example: `{"literature_search": 1}`
- `max_calls_per_run` (int, optional): fallback max calls applied to all tools in this toolkit

Behavior:
- Once a tool reaches its call limit, it is **dynamically disabled** for subsequent turns in the same run.
- This is enforced by the runner/tool layer, so the model cannot override it by ignoring instructions.

## Chroma DB In This Workspace (Current Recommended Backend)

This workspace uses a host-persisted Chroma directory for MAD literature RAG:
- Host path: `MAD/data/chroma_db/`
- Docker mount: `/state/chroma_db` (see `docker-compose.yml`)

Recommended chroma config shape:
- `backend=chroma`
- `persist_directory` points at the Chroma directory (host or container path)
- `collection_name` is runtime-selected by MAD env vars:
  - low-memory testing: `MAD_RAG_MODE=shared` + `MAD_RAG_SHARED_COLLECTION=<name>`
  - server baseline: `MAD_RAG_MODE=per_agent` (or unset)

Embedding model (query time must match indexing time):
- Voyage embedding model is controlled by `VOYAGE_EMBED_MODEL` (commonly `voyage-3-large`).

If you hit `unable to open database file` errors when creating/opening Chroma, set:
- `SQLITE_TMPDIR=/tmp`
- `TMPDIR=/tmp`

For the current Chroma inventory (collections, metadata keys, and known issues), see:
- `spec-bank/chroma_db_inventory.md`
