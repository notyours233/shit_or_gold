"""Chem literature database toolkit.

This exposes a small set of tools to the agent so it can retrieve supporting
evidence from an *external* literature database during reasoning.

Current implementation:
- Supports two backends (selected via `config.backend`):
  - `sqlite`: read-only paper metadata/content in an external SQLite DB (no network)
  - `chroma`: vector retrieval over a local persistent Chroma directory (embeddings via Voyage API)
"""

from __future__ import annotations

from typing import Any

from ..config import ToolkitConfig
from ..literature import (
    ChromaLiteratureStore,
    ChromaLiteratureStoreConfig,
    SQLiteLiteratureStore,
    SQLiteLiteratureStoreConfig,
    VoyageEmbedder,
    VoyageEmbedderConfig,
)
from ..utils import get_logger
from .base import AsyncBaseToolkit, register_tool

logger = get_logger(__name__)


def _cfg_get(d: dict[str, Any], key: str, default: Any) -> Any:
    val = d.get(key, default)
    return default if val is None else val


def _snip(text: str | None, limit: int) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = " ".join(s.split())
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


def _as_float(val: Any, default: float | None) -> float | None:
    if val is None:
        return default
    if isinstance(val, str) and not val.strip():
        return default
    try:
        return float(val)
    except Exception:  # pylint: disable=broad-except
        return default


class ChemLiteratureDBToolkit(AsyncBaseToolkit):
    """Expose external literature DB access as agent tools."""

    def __init__(self, config: ToolkitConfig | None = None) -> None:
        super().__init__(config)
        raw = self.config.config or {}
        self._raw_cfg = raw

        self._backend = str(_cfg_get(raw, "backend", "sqlite")).strip().lower()
        self._init_error: str | None = None
        raw_result_limit = raw.get("max_results_per_search")
        try:
            self._max_results_per_search = max(1, int(raw_result_limit)) if raw_result_limit is not None else None
        except (TypeError, ValueError):
            self._max_results_per_search = None
        # Doc-level masking (label-leakage prevention). This list is injected by the
        # rollout/eval runner and MUST NOT be exposed to the model.
        masked_doc_ids = _cfg_get(raw, "masked_doc_ids", []) or []
        if isinstance(masked_doc_ids, str):
            masked_list = [s.strip() for s in masked_doc_ids.split(",") if s.strip()]
        elif isinstance(masked_doc_ids, list):
            masked_list = [str(s).strip() for s in masked_doc_ids if str(s).strip()]
        else:
            masked_list = [str(masked_doc_ids).strip()] if masked_doc_ids else []
        self._masked_doc_ids = {s.lower() for s in masked_list if s}

        # Backend: sqlite (default)
        self._sqlite_store: SQLiteLiteratureStore | None = None
        self._sqlite_store_cfg: SQLiteLiteratureStoreConfig | None = None

        # Backend: chroma (vector retrieval)
        self._chroma_store: ChromaLiteratureStore | None = None
        self._chroma_store_cfg: ChromaLiteratureStoreConfig | None = None
        self._voyage_cfg: VoyageEmbedderConfig | None = None
        self._voyage_embedder: VoyageEmbedder | None = None
        self._chroma_default_max_distance: float | None = None
        self._chroma_snippet_chars: int = 800

        if self._backend in ("sqlite", ""):
            self._sqlite_store_cfg = SQLiteLiteratureStoreConfig(
                db_path=str(_cfg_get(raw, "db_path", "")),
                table=str(_cfg_get(raw, "table", "papers")),
                id_column=str(_cfg_get(raw, "id_column", "paper_id")),
                title_column=str(_cfg_get(raw, "title_column", "title")),
                abstract_column=str(_cfg_get(raw, "abstract_column", "abstract")),
                doi_column=_cfg_get(raw, "doi_column", "doi"),
                year_column=_cfg_get(raw, "year_column", "year"),
                url_column=_cfg_get(raw, "url_column", "url"),
                file_path_column=_cfg_get(raw, "file_path_column", "file_path"),
                candidate_multiplier=int(_cfg_get(raw, "candidate_multiplier", 10)),
                max_candidates=int(_cfg_get(raw, "max_candidates", 200)),
                snippet_chars=int(_cfg_get(raw, "snippet_chars", 400)),
                extra_columns=list(_cfg_get(raw, "extra_columns", [])),
            )
            self._sqlite_store = SQLiteLiteratureStore(self._sqlite_store_cfg)
        elif self._backend == "chroma":
            try:
                self._chroma_store_cfg = ChromaLiteratureStoreConfig(
                    persist_directory=str(_cfg_get(raw, "persist_directory", "chroma_db")),
                    collection_name=str(_cfg_get(raw, "collection_name", "")),
                    distance_metric=str(_cfg_get(raw, "distance_metric", "cosine")),
                    allow_reset=bool(_cfg_get(raw, "allow_reset", True)),
                )
                self._chroma_store = ChromaLiteratureStore(self._chroma_store_cfg)
                self._voyage_cfg = VoyageEmbedderConfig.from_dict(raw)
                self._chroma_default_max_distance = _as_float(raw.get("max_distance"), 0.35)
                self._chroma_snippet_chars = int(
                    _cfg_get(raw, "chroma_snippet_chars", _cfg_get(raw, "snippet_chars", 800))
                )
            except Exception as e:  # pylint: disable=broad-except
                # Do not crash agent init; surface errors via tool calls.
                self._init_error = str(e)
        else:
            # Unknown backend: don't crash agent init; surface error on tool usage.
            self._init_error = f"Unknown chem_literature_db backend: {self._backend!r} (expected 'sqlite' or 'chroma')"

    def _get_voyage_embedder(self) -> VoyageEmbedder | None:
        if self._voyage_embedder is not None:
            return self._voyage_embedder
        if self._voyage_cfg is None:
            return None
        if not self._voyage_cfg.api_key:
            return None
        self._voyage_embedder = VoyageEmbedder(self._voyage_cfg)
        return self._voyage_embedder

    @register_tool
    async def literature_healthcheck(self) -> dict[str, Any]:
        """Check if the configured literature DB is reachable and report basic schema info."""
        if self._init_error:
            return {"ok": False, "backend": self._backend, "error": self._init_error}

        if self._backend == "sqlite":
            assert self._sqlite_store is not None
            res = self._sqlite_store.healthcheck()
            res["backend"] = "sqlite"
            logger.info(f"[tool] literature_healthcheck(sqlite): ok={res.get('ok')}")
            return res

        if self._backend == "chroma":
            assert self._chroma_store is not None
            res = self._chroma_store.healthcheck()
            # Add embedding config status (but never echo keys).
            res["voyage_model"] = self._voyage_cfg.model if self._voyage_cfg else None
            res["voyage_input_type"] = self._voyage_cfg.input_type if self._voyage_cfg else None
            res["voyage_api_key_set"] = bool((self._voyage_cfg.api_key if self._voyage_cfg else "") or "")
            logger.info(f"[tool] literature_healthcheck(chroma): ok={res.get('ok')}")
            return res

        return {"ok": False, "backend": self._backend, "error": "backend not initialized"}

    @register_tool
    async def literature_search(
        self,
        query: str,
        limit: int = 5,
        reaction_type: str | None = None,
        max_distance: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search the external literature DB for papers matching the query.

        Args:
            query (str): Free-text query. Recommended to include metals, reaction_type, and metric names.
            limit (int): Max number of results to return.
            reaction_type (str, optional): For Chroma backend, apply metadata filter `reaction_type == ...`.
            max_distance (float, optional): For Chroma backend, apply a distance threshold; larger distances are filtered.
        """
        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = self._max_results_per_search or 5
        if self._max_results_per_search is not None:
            limit = min(limit, self._max_results_per_search)
        logger.info(
            f"[tool] literature_search(backend={self._backend}): query={query!r} limit={limit} reaction_type={reaction_type!r}"
        )

        if self._init_error:
            return [{"error": self._init_error}]

        if self._backend == "sqlite":
            assert self._sqlite_store is not None
            hits = self._sqlite_store.search(query=query, limit=limit)
            if not self._masked_doc_ids:
                return hits
            # Best-effort masking (if DOI/paper_id matches the masked list).
            filtered: list[dict[str, Any]] = []
            for h in hits:
                doi = (h.get("doi") or "").strip().lower()
                pid = (h.get("paper_id") or "").strip().lower()
                if (doi and doi in self._masked_doc_ids) or (pid and pid in self._masked_doc_ids):
                    continue
                filtered.append(h)
            return filtered

        if self._backend == "chroma":
            assert self._chroma_store is not None
            embedder = self._get_voyage_embedder()
            if embedder is None:
                return [
                    {
                        "error": "Voyage embedding is not configured. Set VOYAGE_API_KEY (and optionally VOYAGE_EMBED_MODEL).",
                        "hit": False,
                    }
                ]

            query = (query or "").strip()
            if not query:
                return [{"error": "query must be a non-empty string", "hit": False}]

            # Default threshold is required for safety: avoid returning unrelated chunks.
            dist_th = max_distance if max_distance is not None else self._chroma_default_max_distance

            where = None
            if reaction_type:
                rt = str(reaction_type).strip()
                # Historical electrochemistry collections used upper-case reaction labels
                # (OER/HER/...), while the material-property Chroma DB stores lower-case
                # canonical property names in metadata["reaction_type"].
                prop = None
                try:
                    # Avoid importing MAD utilities here; keep the youtu tool standalone.
                    aliases = {
                        "photothermal conversion efficiency": "photothermal_conversion_efficiency",
                        "photothermal_conversion_efficiency": "photothermal_conversion_efficiency",
                        "conductivity": "conductivity",
                        "thermal conductivity": "thermal_conductivity",
                        "thermal_conductivity": "thermal_conductivity",
                        "ferromagnetism": "ferromagnetism",
                        "ferrimagnetism": "ferrimagnetism",
                        "antiferromagnetism": "antiferromagnetism",
                    }
                    key = " ".join(rt.replace("_", " ").lower().split())
                    prop = aliases.get(key) or aliases.get(rt.strip())
                except Exception:
                    prop = None

                where = {"reaction_type": {"$eq": prop or rt.upper()}}

            try:
                # NOTE: Avoid `asyncio.to_thread` here. In some environments, using the
                # default executor can cause the process to hang on shutdown (tests/CLI).
                # Voyage calls are network-bound anyway, so blocking within the tool call
                # is acceptable.
                query_vec = embedder.embed_query(query)
                # NOTE: Chroma's Rust-backed client can hang when called from a background
                # thread in some environments. Keep Chroma calls on the main thread.
                hits = self._chroma_store.similarity_search(
                    query_embedding=query_vec,
                    top_k=int(limit),
                    max_distance=dist_th,
                    where=where,
                )
            except Exception as e:  # pylint: disable=broad-except
                return [{"error": f"Chroma search failed: {e}", "hit": False}]

            # Doc-level masking to prevent label leakage: drop any hit whose doc_id is masked.
            if self._masked_doc_ids:
                hits = [
                    h
                    for h in hits
                    if str((h.get("metadata") or {}).get("doc_id") or "").strip().lower() not in self._masked_doc_ids
                ]

            if not hits:
                # Explicit "no hit / low confidence" to avoid misleading the model.
                return [
                    {
                        "ok": True,
                        "hit": False,
                        "message": "No results (or all candidates are low-confidence or masked).",
                        "query": query,
                        "reaction_type": reaction_type,
                        "max_distance": dist_th,
                    }
                ]

            out: list[dict[str, Any]] = []
            for h in hits:
                meta = h.get("metadata") or {}
                dist = h.get("distance")
                conf = None
                if isinstance(dist, (int, float)):
                    # For cosine space, distance ~= 1 - cosine_similarity
                    conf = 1.0 - float(dist)
                out.append(
                    {
                        "id": h.get("id"),
                        "doc_id": meta.get("doc_id"),
                        "reaction_type": meta.get("reaction_type"),
                        "chunk_id": meta.get("chunk_id"),
                        "total_chunks": meta.get("total_chunks"),
                        "distance": dist,
                        "confidence": conf,
                        "text": _snip(h.get("document"), self._chroma_snippet_chars),
                    }
                )
            return out

        return [{"error": f"Unsupported backend: {self._backend}", "hit": False}]

    @register_tool
    async def literature_get(self, paper_id: str, chunk_id: int | None = None, limit: int = 5) -> dict[str, Any]:
        """Fetch one record by id.

        Backend behavior:
        - sqlite: `paper_id` is the primary key in the configured table.
        - chroma: `paper_id` is treated as `doc_id` and returns up to `limit` chunks
          (optionally a specific `chunk_id`).
        """
        logger.info(f"[tool] literature_get(backend={self._backend}): paper_id={paper_id!r} chunk_id={chunk_id!r}")

        if self._init_error:
            return {"error": self._init_error}

        if self._backend == "sqlite":
            assert self._sqlite_store is not None
            return self._sqlite_store.get(paper_id=paper_id)

        if self._backend == "chroma":
            assert self._chroma_store is not None
            # Defensive: if the requested doc_id is masked, pretend it doesn't exist.
            if self._masked_doc_ids and str(paper_id).strip().lower() in self._masked_doc_ids:
                return {"ok": True, "doc_id": paper_id, "chunks": [], "message": "not found"}
            try:
                # Same thread-safety note as in `literature_search`.
                chunks = self._chroma_store.get_chunks(doc_id=str(paper_id), limit=int(limit), chunk_id=chunk_id)
            except Exception as e:  # pylint: disable=broad-except
                return {"error": f"Chroma get failed: {e}"}

            if not chunks:
                return {"ok": True, "doc_id": paper_id, "chunks": [], "message": "not found"}

            out_chunks: list[dict[str, Any]] = []
            for c in chunks:
                meta = c.get("metadata") or {}
                out_chunks.append(
                    {
                        "id": c.get("id"),
                        "doc_id": meta.get("doc_id"),
                        "reaction_type": meta.get("reaction_type"),
                        "chunk_id": meta.get("chunk_id"),
                        "total_chunks": meta.get("total_chunks"),
                        "text": _snip(c.get("document"), self._chroma_snippet_chars),
                    }
                )
            return {"ok": True, "doc_id": paper_id, "chunks": out_chunks}

        return {"error": f"Unsupported backend: {self._backend}"}
