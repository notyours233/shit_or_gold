from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import List, Sequence


_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "must",
    "no",
    "not",
    "of",
    "on",
    "only",
    "or",
    "our",
    "should",
    "so",
    "that",
    "the",
    "their",
    "then",
    "these",
    "this",
    "those",
    "to",
    "use",
    "using",
    "we",
    "when",
    "will",
    "with",
    "without",
    "you",
    "your",
}


def _tokenize(text: str) -> list[str]:
    s = str(text or "").lower()
    raw = [t for t in _TOKEN_SPLIT_RE.split(s) if t]
    out: list[str] = []
    for tok in raw:
        if tok in _STOPWORDS:
            continue
        if tok.isdigit():
            continue
        if len(tok) < 2:
            continue
        out.append(tok)
    return out


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _hash_embed(text: str, *, dim: int) -> list[float]:
    """Deterministic local embedding (hashing trick).

    This is a fallback provider that requires no network/API keys and is suitable
    for unit tests. It is NOT meant to be a high-quality semantic embedder.
    """
    dim = max(8, int(dim))
    vec = [0.0] * dim
    for tok in _tokenize(text):
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = -1.0 if (h[4] & 1) else 1.0
        vec[idx] += sign
    return _l2_normalize(vec)


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str | None = None
    hash_dim: int = 256

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        provider = (os.getenv("MAD_EXPERIENCE_EMBED_PROVIDER", "voyage") or "voyage").strip().lower()
        model = (os.getenv("MAD_EXPERIENCE_EMBED_MODEL") or "").strip() or None
        hash_dim = int(os.getenv("MAD_EXPERIENCE_HASH_EMBED_DIM", "256") or 256)
        return cls(provider=provider, model=model, hash_dim=hash_dim)


class ExperienceEmbedder:
    def __init__(self, cfg: EmbeddingConfig):
        self.cfg = cfg

    @property
    def model_id(self) -> str:
        if self.cfg.provider == "hash":
            return f"hash:dim={int(self.cfg.hash_dim)}"
        if self.cfg.provider == "voyage":
            return f"voyage:{self.cfg.model or 'default'}"
        return f"{self.cfg.provider}:{self.cfg.model or 'default'}"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(list(texts), input_type="document")

    def embed_query(self, text: str) -> list[float]:
        out = self._embed([text], input_type="query")
        return out[0] if out else []

    def _embed(self, texts: List[str], *, input_type: str) -> list[list[float]]:
        provider = (self.cfg.provider or "").strip().lower()
        if provider == "hash":
            return [_hash_embed(t, dim=int(self.cfg.hash_dim)) for t in texts]

        if provider == "voyage":
            try:
                import voyageai  # type: ignore
            except Exception as e:  # noqa: BLE001 - keep MAD importable without optional deps
                raise RuntimeError("voyageai is not installed (pip install voyageai)") from e

            api_key = (os.getenv("VOYAGE_API_KEY") or "").strip()
            if not api_key:
                raise RuntimeError("VOYAGE_API_KEY is not set (required for MAD_EXPERIENCE_EMBED_PROVIDER=voyage)")

            model = self.cfg.model or (os.getenv("VOYAGE_EMBED_MODEL") or "").strip() or "voyage-3-lite"
            client = voyageai.Client(api_key=api_key, max_retries=2, timeout=60.0)
            obj = client.embed(texts, model=model, input_type=str(input_type))
            return list(obj.embeddings or [])

        raise RuntimeError(f"Unknown embedding provider: {provider!r} (supported: voyage, hash)")

