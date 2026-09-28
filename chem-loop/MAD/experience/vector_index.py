from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from experience.embeddings import ExperienceEmbedder


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        # Defensive: mismatched embedding dims should not crash; treat as unrelated.
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0 or nb <= 0:
        return 0.0
    return float(dot / math.sqrt(na * nb))


def default_cache_path() -> Path:
    env = (os.getenv("MAD_EXPERIENCE_EMBED_CACHE_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    # Docker-first: /state is our persisted mount.
    if Path("/state").exists():
        return Path("/state") / "experience_embed_cache.json"
    # Fallback: repo-local cache under MAD/.cache
    return Path(__file__).resolve().parents[1] / ".cache" / "experience_embed_cache.json"


@dataclass
class VectorCache:
    model_id: str
    items: Dict[str, Dict[str, Any]]  # id -> {"hash": str, "vector": list[float]}

    @classmethod
    def load(cls, path: Path) -> "VectorCache | None":
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        model_id = str(raw.get("model_id") or "").strip()
        items = raw.get("items")
        if not model_id or not isinstance(items, dict):
            return None
        # Shallow validation.
        out_items: Dict[str, Dict[str, Any]] = {}
        for k, v in items.items():
            if not isinstance(k, str) or not k:
                continue
            if not isinstance(v, dict):
                continue
            h = v.get("hash")
            vec = v.get("vector")
            if not isinstance(h, str) or not h:
                continue
            if not isinstance(vec, list) or not vec:
                continue
            out_items[k] = {"hash": h, "vector": vec}
        return cls(model_id=model_id, items=out_items)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        obj = {"version": 1, "model_id": self.model_id, "items": self.items}
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ExperienceVectorIndex:
    """Embedding-based experience index with a small on-disk cache."""

    def __init__(self, *, embedder: ExperienceEmbedder, cache_path: Path | None = None) -> None:
        self.embedder = embedder
        self.cache_path = cache_path or default_cache_path()
        self._cache = VectorCache.load(self.cache_path)
        if self._cache is None or self._cache.model_id != self.embedder.model_id:
            self._cache = VectorCache(model_id=self.embedder.model_id, items={})

    def ensure_index(self, docs: Iterable[Tuple[str, str]]) -> None:
        """Ensure embeddings exist for all docs (id, text)."""
        missing: list[tuple[str, str, str]] = []  # (id, hash, text)
        for doc_id, text in docs:
            if not doc_id:
                continue
            h = _sha256_text(text)
            item = self._cache.items.get(doc_id)
            if not item or item.get("hash") != h:
                missing.append((doc_id, h, text))

        if not missing:
            return

        # Embed in batches to avoid provider limits.
        batch_size = int(os.getenv("MAD_EXPERIENCE_EMBED_BATCH_SIZE", "32") or 32)
        batch_size = max(1, min(256, batch_size))

        for i in range(0, len(missing), batch_size):
            chunk = missing[i : i + batch_size]
            texts = [t for _id, _h, t in chunk]
            vectors = self.embedder.embed_documents(texts)
            if len(vectors) != len(chunk):
                raise RuntimeError(
                    f"Embedding provider returned unexpected count: got={len(vectors)} expected={len(chunk)}"
                )
            for (doc_id, h, _text), vec in zip(chunk, vectors, strict=False):
                self._cache.items[doc_id] = {"hash": h, "vector": vec}

        # Best-effort persistence.
        try:
            self._cache.save(self.cache_path)
        except Exception:
            pass

    def query(self, *, query_text: str, docs: Iterable[Tuple[str, str]], top_k: int) -> list[tuple[str, float]]:
        query_vec = self.embedder.embed_query(query_text)
        if not query_vec:
            return []

        scored: list[tuple[str, float]] = []
        for doc_id, text in docs:
            if not doc_id:
                continue
            h = _sha256_text(text)
            item = self._cache.items.get(doc_id)
            vec = None
            if item and item.get("hash") == h:
                vec = item.get("vector")
            if not isinstance(vec, list):
                # Not embedded yet; skip (caller should have called ensure_index()).
                continue
            sim = _cosine_similarity(query_vec, vec)
            scored.append((doc_id, sim))

        scored.sort(key=lambda x: float(x[1]), reverse=True)
        return scored[: max(1, int(top_k))]

