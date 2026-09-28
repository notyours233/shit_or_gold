#!/usr/bin/env python3
"""Subprocess runner for chem_literature_db (used by external engines like MAD).

Why this exists:
- MAD runs in a separate Python environment (its own venv) to keep deps isolated.
- We still want to reuse *this repo's* chem literature DB (local Chroma + Voyage embeddings)
  and the existing doc-level masking logic (label leakage prevention).
- Therefore, MAD can call this runner via subprocess, using youtu-agent's Python env.

Protocol:
- Read one JSON object from stdin:
    {
      "query": "...",
      "limit": 5,
      "reaction_type": "OER",
      "max_distance": 0.35,
      "masked_doc_ids": ["10.xxx/..."],   # optional; enforced server-side and NOT echoed back
      "tool_config_override": {...}       # optional; advanced/debug use only
    }
- Write one JSON value to stdout:
    - On success: a list of hits (same shape as `ChemLiteratureDBToolkit.literature_search`).
    - On failure: a list with one dict containing `{"error": "...", "hit": False}`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _repo_root() -> Path:
    # .../utu/external_engines/chem_literature_runner.py -> repo root is two levels up.
    return Path(__file__).resolve().parents[2]


def _as_list_of_str(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    if isinstance(val, list):
        out: list[str] = []
        for x in val:
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    return [str(val).strip()] if str(val).strip() else []


def _build_tool_cfg(payload: dict[str, Any]) -> dict[str, Any]:
    # Prefer explicit backend selector, but default to chroma because this runner is only
    # used for RAG-style retrieval in our chem workflow.
    backend_env = (os.getenv("CHEM_LITERATURE_BACKEND") or "").strip().lower()
    db_path = (os.getenv("CHEM_LITERATURE_DB_PATH") or "").strip()
    backend = backend_env or ("sqlite" if db_path else "chroma")

    # Prefer the newer, fully-built local Chroma DB if present, but allow env overrides.
    repo_root = _repo_root()
    # Monorepo default: share MAD's Chroma DB to avoid keeping duplicate huge stores.
    mad_db = repo_root.parent / "MAD" / "data" / "chroma_db"
    if mad_db.exists():
        default_persist_dir = str(mad_db)
    elif (repo_root / "chroma_db2").exists():
        default_persist_dir = "chroma_db2"
    else:
        default_persist_dir = "chroma_db"

    # Base config from env (mirrors `configs/tools/chem_literature_db.yaml` keys).
    cfg: dict[str, Any] = {
        "backend": backend,
        "db_path": db_path,
        "persist_directory": os.getenv("CHEM_LITERATURE_CHROMA_DIR", default_persist_dir),
        "collection_name": os.getenv("CHEM_LITERATURE_CHROMA_COLLECTION", "literature_agent2"),
        "distance_metric": "cosine",
        "max_distance": os.getenv("CHEM_LITERATURE_CHROMA_MAX_DISTANCE", "0.35"),
        "chroma_snippet_chars": os.getenv("CHEM_LITERATURE_CHROMA_SNIPPET_CHARS", "800"),
        # Voyage config (query embeddings).
        "voyage_api_key": os.getenv("VOYAGE_API_KEY", ""),
        "voyage_model": os.getenv("VOYAGE_EMBED_MODEL", "voyage-3-large"),
        "voyage_input_type": os.getenv("VOYAGE_EMBED_INPUT_TYPE", ""),
        "voyage_timeout": os.getenv("VOYAGE_TIMEOUT", "30"),
        "voyage_max_retries": os.getenv("VOYAGE_MAX_RETRIES", "2"),
    }

    override = payload.get("tool_config_override")
    if isinstance(override, dict):
        # Allow controlled overrides for debugging (do NOT include secrets).
        cfg.update(override)

    # Doc-level masking: enforced server-side, never echoed back.
    cfg["masked_doc_ids"] = _as_list_of_str(payload.get("masked_doc_ids"))
    return cfg


async def _run(payload: dict[str, Any]) -> list[dict[str, Any]]:
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return [{"error": "query must be a non-empty string", "hit": False}]

    limit = int(payload.get("limit", 5))
    reaction_type = payload.get("reaction_type")
    reaction_type = str(reaction_type).strip() if reaction_type else None

    max_distance = payload.get("max_distance")
    max_distance = float(max_distance) if max_distance not in (None, "") else None

    # Ensure `import utu...` works when executed as a script.
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))

    from utu.config.agent_config import ToolkitConfig  # pylint: disable=import-error
    from utu.tools.chem_literature_db_toolkit import ChemLiteratureDBToolkit  # pylint: disable=import-error

    cfg = ToolkitConfig(
        mode="builtin",
        env_mode="local",
        name="chem_literature_db",
        activated_tools=["literature_search"],
        config=_build_tool_cfg(payload),
    )

    toolkit = ChemLiteratureDBToolkit(cfg)
    hits = await toolkit.literature_search(
        query=query,
        limit=limit,
        reaction_type=reaction_type,
        max_distance=max_distance,
    )
    if not isinstance(hits, list):
        return [{"error": "tool returned non-list payload", "hit": False}]
    return hits  # already masked inside toolkit


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        hits = asyncio.run(_run(payload))
        sys.stdout.write(json.dumps(hits, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception as e:
        _eprint(f"[chem_literature_runner] ERROR: {e}")
        _eprint(traceback.format_exc())
        # Return a JSON payload even on failure (for caller stability).
        sys.stdout.write(json.dumps([{"error": str(e), "hit": False}], ensure_ascii=False))
        sys.stdout.flush()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
