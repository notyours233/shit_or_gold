"""Chroma-backed literature store (vector retrieval).

This module is intended for *read-only* retrieval against an existing persistent
Chroma directory (e.g. `chroma_db2/` in this repo).

Key requirement for this workspace:
- Some environments fail with `sqlite3.OperationalError: unable to open database file`
  unless SQLITE temp dirs are configured. We set safe defaults (`/tmp`) before
  creating the Chroma PersistentClient.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils import DIR_ROOT, get_logger

logger = get_logger(__name__)


def _set_sqlite_tmp_env_defaults() -> None:
    # Chroma uses SQLite under the hood; in constrained environments temp-file
    # placement can break SQLite and surface as "unable to open database file".
    os.environ.setdefault("SQLITE_TMPDIR", "/tmp")
    os.environ.setdefault("TMPDIR", "/tmp")


def _as_abs_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (DIR_ROOT / p)


@dataclass(frozen=True)
class ChromaLiteratureStoreConfig:
    persist_directory: str
    collection_name: str
    distance_metric: str = "cosine"  # stored in metadata as hnsw:space
    # NOTE: Chroma's global SharedSystemClient keys on (path, settings). If some other
    # code in the same process creates a client with allow_reset=True, then creating
    # another client with allow_reset=False for the same path can raise:
    # "An instance of Chroma already exists ... with different settings".
    # To avoid this footgun, default to allow_reset=True (we still don't call reset).
    allow_reset: bool = True


class ChromaLiteratureStore:
    """Thin wrapper around a persistent Chroma collection for similarity search."""

    def __init__(self, cfg: ChromaLiteratureStoreConfig):
        self.cfg = cfg
        self.persist_directory = _as_abs_path(cfg.persist_directory)
        self._client = None
        self._collection = None

    # ---------------------------------------------------------------------
    # internal

    def _get_client(self):
        if self._client is None:
            _set_sqlite_tmp_env_defaults()
            try:
                import chromadb  # type: ignore
                from chromadb.config import Settings  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("Package `chromadb` is required for Chroma literature retrieval.") from e
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False, allow_reset=self.cfg.allow_reset),
            )
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            # Use get_collection (not get_or_create) to avoid silently creating an
            # empty collection when config is wrong.
            self._collection = client.get_collection(name=self.cfg.collection_name)
        return self._collection

    # ---------------------------------------------------------------------
    # public

    def healthcheck(self) -> dict[str, Any]:
        """Return basic status info; never raises."""
        try:
            client = self._get_client()
            collections = client.list_collections()
            names = [c.name for c in collections]
            ok = self.cfg.collection_name in names
            out: dict[str, Any] = {
                "ok": ok,
                "backend": "chroma",
                "persist_directory": str(self.persist_directory),
                "collection_name": self.cfg.collection_name,
                "available_collections": names,
            }
            if ok:
                col = self._get_collection()
                out["count"] = col.count()
            else:
                out["error"] = "collection not found"
            return out
        except Exception as e:  # pylint: disable=broad-except
            return {
                "ok": False,
                "backend": "chroma",
                "persist_directory": str(self.persist_directory),
                "collection_name": self.cfg.collection_name,
                "error": str(e),
            }

    def similarity_search(
        self,
        *,
        query_embedding: list[float],
        top_k: int = 5,
        max_distance: float | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return top-k similar chunks with optional distance threshold.

        Distances are Chroma distances (for cosine space: smaller is closer).
        When `max_distance` is provided, results with distance > max_distance are filtered out.
        """
        if top_k <= 0:
            return []
        if not query_embedding:
            raise ValueError("query_embedding must be a non-empty vector")

        col = self._get_collection()
        res = col.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]

        out: list[dict[str, Any]] = []
        for i in range(len(docs)):
            dist = dists[i] if i < len(dists) else None
            if max_distance is not None and dist is not None and dist > max_distance:
                continue
            out.append(
                {
                    "id": ids[i] if i < len(ids) else None,
                    "document": docs[i],
                    "distance": dist,
                    "metadata": metas[i] if i < len(metas) else None,
                }
            )
        return out

    def get_chunks(
        self,
        *,
        doc_id: str,
        limit: int = 5,
        chunk_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch chunks by doc_id (and optionally chunk_id); best-effort order."""
        doc_id = (doc_id or "").strip()
        if not doc_id:
            return []
        limit = max(int(limit), 1)

        where: dict[str, Any]
        if chunk_id is None:
            where = {"doc_id": {"$eq": doc_id}}
        else:
            where = {"$and": [{"doc_id": {"$eq": doc_id}}, {"chunk_id": {"$eq": int(chunk_id)}}]}

        col = self._get_collection()
        res = col.get(where=where, limit=limit, include=["documents", "metadatas"])
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        ids = res.get("ids") or []

        out: list[dict[str, Any]] = []
        for i in range(len(docs)):
            out.append({"id": ids[i] if i < len(ids) else None, "document": docs[i], "metadata": metas[i]})
        return out
