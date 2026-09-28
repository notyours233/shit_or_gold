# MAD (Multi-Agent Debate) for Electrocatalysis Literature

MAD is a multi-agent debate system for electrocatalysis analysis. Given **exactly 5 metal elements** (catalyst composition; optionally with relative percentages) and a **target reaction type**, the system debates and predicts the required performance metric(s) for that reaction (reaction-type specific; CO2RR includes main product + Faradaic efficiency).

It combines:
- 4 configurable LLM agents (LangChain tool-calling ReAct runtime)
- Chroma-backed RAG over a local Markdown literature corpus
- A debate coordinator (default: "LangGraph-style", implemented in-repo; no external `langgraph` dependency)
- Optional experience-store retrieval

## Monorepo usage (recommended)

This folder is part of the **ChemCouncil** monorepo. Prefer the monorepo flow:

1) Create ONE env file at the monorepo root (not inside `MAD/`):

```bash
cd ChemCouncil
cp .env.example .env
```

2) Install dependencies into ONE venv at the monorepo root:

```bash
cd ChemCouncil
./scripts/setup_venv.sh
source .venv/bin/activate
```

Then run MAD from this directory:

```bash
cd ChemCouncil/MAD
python main.py --components "Pt,Pd,Ru,Ir,Rh" --reaction-type OER
```

## Quickstart

### 1) Install
Tested with Python 3.11.

Monorepo (ChemCouncil) install:

```bash
cd ..
pip install -r requirements.txt
```

Standalone install (MAD only):

```bash
pip install -r requirements.txt
```

### 2) Configure API keys
Create a `.env` file in the *monorepo root* (or in the project root if you are running MAD standalone):

```bash
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
GOOGLE_API_KEY=...
QWEN_API_KEY=...
VOYAGE_API_KEY=...
OPENROUTER_API_KEY=...
```

Notes:
- All four chat credentials are sent to the shared OpenAI-compatible gateway in the current default config.
- Agent 1 chats via the shared gateway (`model: gpt-5.5`, `base_url: https://agent-team-api.myrimate.cn/v1`).
- Agent 2 chats via the shared gateway (`model: deepseek-v4-pro`, `base_url: https://agent-team-api.myrimate.cn/v1`).
- Agent 3 chats via the shared gateway (`model: gemini-3.5-flash`, `base_url: https://agent-team-api.myrimate.cn/v1`).
- Agent 4 chats via the shared gateway (`model: qwen3.7-max`, `base_url: https://agent-team-api.myrimate.cn/v1`).
- Agent 1 and Agent 3 embeddings use OpenRouter with the separate `OPENROUTER_API_KEY` credential.
- Agent 4 embeddings use the same gateway (`emb_url: https://agent-team-api.myrimate.cn/v1/embeddings`) and `embedding_api_key` (typically `QWEN_API_KEY`).
- See `config/config.yaml` for the exact mapping.

### 3) Prepare literature data
Place Markdown papers under:

```text
data/raw/CO2RR/*.md
data/raw/EOR/*.md
data/raw/HER/*.md
data/raw/HOR/*.md
data/raw/HZOR/*.md
data/raw/O5H/*.md
data/raw/OER/*.md
data/raw/ORR/*.md
data/raw/UOR/*.md
```

### 4) Build vector databases (Chroma)
Preferred: build per-agent collections via the batch script.

```bash
python build_vector_db_batch.py --agents agent1,agent2,agent3,agent4 --clear
```

Collections are stored in `vector_store.persist_directory` (default `./data/chroma_db`) and named:
`<vector_store.collection_name>_<agent_name>` (e.g., `electrochemistry_literature_agent1`).

Useful options:
- `--max-workers 1` (sequential build)
- `--embedding-batch-size 10`
- `--sleep-between-batches 0.5`

Legacy (single-agent) script:

```bash
python build_vector_db.py
```

### 5) Run a debate
Provide **exactly 5** metal elements (symbols only):

```bash
python main.py --components "Pt,Pd,Ru,Ir,Rh" --reaction-type CO2RR
```

You may also provide relative percentages (the system will treat them as the electrode composition):

```bash
python main.py --components "Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)" --reaction-type OER
```

Arguments:
- `--components`: comma-separated 5 metal elements
- `--reaction-type`: one of `CO2RR/EOR/HER/HOR/HZOR/O5H/OER/ORR/UOR` (recommended)
- `--engine`: `langgraph` (default; currently the only supported engine)

### 6) Rank reaction types (auto-run debates for each reaction)
If you want to **fix the composition** (5 metals + optional relative %) and let the system
run debates for **all reaction types** and return the **Top-K** reactions by grade:

```bash
python main.py --components "Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)" --rank-reactions
```

Optional controls:
- Subset of reactions:
  ```bash
  python main.py --components "Pt,Pd,Ru,Ir,Rh" --rank-reactions --reaction-types "OER,HER,ORR"
  ```
- Top-K (default 2):
  ```bash
  python main.py --components "Pt,Pd,Ru,Ir,Rh" --rank-reactions --top-k-reactions 3
  ```
- Reaction-level parallelism (default 1; higher may trigger API rate limits):
  ```bash
  python main.py --components "Pt,Pd,Ru,Ir,Rh" --rank-reactions --max-parallel-reactions 2
  ```
- Also save each per-reaction `outputs/result_*.json` (off by default):
  ```bash
  python main.py --components "Pt,Pd,Ru,Ir,Rh" --rank-reactions --save-each-reaction
  ```

Outputs:
- Ranking summary: `outputs/rank_<timestamp>.json`
- Logs and per-debate artifacts: under `logs/runs/<run_id>/`

### Outputs
- Results: `paths.outputs` (default `./outputs`) as `result_<timestamp>.json` (timestamp format: `YYYYMMDD_HHMMSS`)
- Logs:
  - rolling: `./logs/system.log`
  - per-run: `./logs/runs/<run_id>/run.log` (plus `events.jsonl`, `db.log`, `debate.log`)

## Configuration
All runtime configuration lives in `config/config.yaml`:
- `llm.*`: per-agent provider/model + embedding settings
- `vector_store.*`: Chroma persistence + base collection name
- `rag.*`: chunking + retrieval parameters
- `debate.*`: debate protocol parameters
- `paths.outputs`: output directory for saved results

## How it works (high level)
- `database/text_processor.py`: load + chunk Markdown documents (LlamaIndex parsers)
- `database/embedder.py`: multi-provider embeddings selected per agent
- `database/vector_store.py`: Chroma persistence with stable chunk ids
- `database/rag_system.py`: query embedding + Chroma similarity search
- `agents/react_agent.py`: LangChain tool-calling ReAct agent (`search_literature`, `search_experience`)
- `debate/langgraph_coordinator.py`: default debate coordinator and evidence enforcement

## Tests
```bash
python -m unittest discover -s test -p "test_*.py"
```

## License
MIT
