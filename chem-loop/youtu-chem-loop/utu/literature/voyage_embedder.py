"""Voyage embedding helper.

This is a thin wrapper around `voyageai.Client` with:
- env-friendly configuration (VOYAGE_*), but also injectable config for tests
- small surface area (embed_query / embed_texts)

We keep it synchronous and let toolkits decide whether to call it via
`asyncio.to_thread` (to avoid blocking the event loop).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)


def _norm_optional_str(val: str | None) -> str | None:
    if val is None:
        return None
    val = val.strip()
    return val or None


@dataclass(frozen=True)
class VoyageEmbedderConfig:
    api_key: str
    model: str = "voyage-3-large"
    input_type: str | None = None  # e.g. "query" / "document" / None
    truncation: bool = True
    timeout: float | None = 30.0
    max_retries: int = 2
    output_dimension: int | None = None

    @classmethod
    def from_env(cls) -> "VoyageEmbedderConfig":
        api_key = os.getenv("VOYAGE_API_KEY", "")
        model = os.getenv("VOYAGE_EMBED_MODEL", "voyage-3-large")
        input_type = _norm_optional_str(os.getenv("VOYAGE_EMBED_INPUT_TYPE", ""))
        timeout_raw = _norm_optional_str(os.getenv("VOYAGE_TIMEOUT", "30"))
        timeout = float(timeout_raw) if timeout_raw else 30.0
        max_retries_raw = _norm_optional_str(os.getenv("VOYAGE_MAX_RETRIES", "2"))
        max_retries = int(max_retries_raw) if max_retries_raw else 2
        out_dim_raw = _norm_optional_str(os.getenv("VOYAGE_OUTPUT_DIMENSION", ""))
        out_dim = int(out_dim_raw) if out_dim_raw else None
        return cls(
            api_key=api_key,
            model=model,
            input_type=input_type,
            timeout=timeout,
            max_retries=max_retries,
            output_dimension=out_dim,
        )

    @classmethod
    def from_dict(cls, cfg: dict[str, Any]) -> "VoyageEmbedderConfig":
        # Allow config dict to override env defaults (useful in Hydra configs).
        env = cls.from_env()
        api_key = str(cfg.get("voyage_api_key", env.api_key) or "")
        model = str(cfg.get("voyage_model", env.model) or env.model)
        input_type = _norm_optional_str(str(cfg.get("voyage_input_type", env.input_type or "") or ""))
        truncation = bool(cfg.get("voyage_truncation", env.truncation))
        timeout = cfg.get("voyage_timeout", env.timeout)
        timeout = float(timeout) if timeout is not None else None
        max_retries = int(cfg.get("voyage_max_retries", env.max_retries))
        out_dim = cfg.get("voyage_output_dimension", env.output_dimension)
        out_dim = int(out_dim) if out_dim not in (None, "") else None
        return cls(
            api_key=api_key,
            model=model,
            input_type=input_type,
            truncation=truncation,
            timeout=timeout,
            max_retries=max_retries,
            output_dimension=out_dim,
        )


class VoyageEmbedder:
    def __init__(self, cfg: VoyageEmbedderConfig):
        self.cfg = cfg
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import voyageai  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("Package `voyageai` is required for Voyage embeddings.") from e
            self._client = voyageai.Client(
                api_key=self.cfg.api_key or None,
                timeout=self.cfg.timeout,
                max_retries=self.cfg.max_retries,
            )
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        # NOTE: Voyage returns EmbeddingsObject with `.embeddings: List[List[float]]`.
        resp = client.embed(
            texts=texts,
            model=self.cfg.model,
            input_type=self.cfg.input_type,
            truncation=self.cfg.truncation,
            output_dimension=self.cfg.output_dimension,
        )
        return [list(v) for v in resp.embeddings]

    def embed_query(self, query: str) -> list[float]:
        query = (query or "").strip()
        if not query:
            raise ValueError("query must be a non-empty string")
        vecs = self.embed_texts([query])
        if not vecs:
            raise RuntimeError("Voyage returned empty embeddings")
        return vecs[0]

