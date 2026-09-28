"""Stdlib-only proxy for using youtu-agent's chem_literature_db via subprocess.

This module is intentionally dependency-light so it can be imported from external
engine subprocesses (e.g. MAD's venv) without pulling in chroma/voyage deps.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _safe_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


def _as_str_list(x: Any) -> list[str]:
    if not x:
        return []
    if isinstance(x, str):
        return [s.strip() for s in x.split(",") if s.strip()]
    if isinstance(x, list):
        out: list[str] = []
        for item in x:
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(x).strip()
    return [s] if s else []


@dataclass(frozen=True)
class SubprocessChemLiteratureRAG:
    """A minimal MAD-compatible RAG system wrapper.

    MAD's `ReActAgent` expects:
      rag_system.retrieve(query: str) -> List[Dict[str, Any]]
    """

    python_bin: str
    runner_path: str
    repo_root: str
    reaction_type: str | None = None
    masked_doc_ids: list[str] | None = None
    limit: int = 5
    max_distance: float | None = None
    timeout_s: float = 30.0
    call_limit: int = 1

    def __post_init__(self) -> None:
        # Validate early to avoid confusing runtime errors inside MAD tool calls.
        pb = Path(self.python_bin)
        if not pb.exists():
            # Allow passing "python3" etc.
            resolved = shutil.which(self.python_bin)
            if not resolved:
                raise FileNotFoundError(f"python_bin not found: {self.python_bin}")
            pb = Path(resolved)

        rp = Path(self.runner_path).resolve()
        rr = Path(self.repo_root).resolve()
        if not rp.exists():
            raise FileNotFoundError(f"runner_path not found: {self.runner_path}")
        if not rr.exists():
            raise FileNotFoundError(f"repo_root not found: {self.repo_root}")

        # Normalize to absolute paths so subprocess calls work even when cwd changes.
        object.__setattr__(self, "python_bin", str(pb))
        object.__setattr__(self, "runner_path", str(rp))
        object.__setattr__(self, "repo_root", str(rr))

        # Dataclass is frozen; use object.__setattr__ to init private mutable state.
        object.__setattr__(self, "_calls", 0)

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        # Enforce an upper bound on retrieval calls for cost/stability.
        calls = getattr(self, "_calls", 0)
        if calls >= int(self.call_limit):
            return []
        object.__setattr__(self, "_calls", calls + 1)

        payload: dict[str, Any] = {
            "query": str(query or ""),
            "limit": int(self.limit),
            "reaction_type": self.reaction_type,
            "max_distance": self.max_distance,
            "masked_doc_ids": _as_str_list(self.masked_doc_ids),
        }

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        # Avoid SQLite temp-file issues in Chroma (consistent with repo practice).
        env.setdefault("SQLITE_TMPDIR", "/tmp")
        env.setdefault("TMPDIR", "/tmp")

        cmd = [self.python_bin, self.runner_path]

        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.repo_root,
                env=env,
                timeout=float(self.timeout_s),
                check=False,
            )
        except Exception:
            # Never break the engine due to RAG errors; return "no results" for stability.
            return []

        if proc.returncode != 0:
            return []

        stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        try:
            hits = json.loads(stdout) if stdout else []
        except Exception:
            return []

        if not isinstance(hits, list) or not hits:
            return []

        # `chem_literature_runner` returns the raw youtu-agent toolkit payload.
        # Convert to MAD's expected list-of-dicts format.
        # - For chroma: entries include doc_id/chunk_id/text/confidence/distance...
        # - For sqlite: entries include doi/title/abstract snippets...
        if isinstance(hits[0], dict) and hits[0].get("hit") is False:
            return []
        if isinstance(hits[0], dict) and hits[0].get("error"):
            return []

        out: list[dict[str, Any]] = []
        for h in hits:
            if not isinstance(h, dict):
                continue

            text = (h.get("text") or "").strip()
            if not text:
                # sqlite backend uses different keys; best-effort fallback to abstract/title.
                text = (h.get("abstract") or h.get("title") or "").strip()

            doc_id = (h.get("doc_id") or h.get("doi") or h.get("paper_id") or "").strip() or None
            chunk_id = h.get("chunk_id")
            rt = h.get("reaction_type") or self.reaction_type

            # Score: prefer confidence, fallback to (1 - distance) for cosine space.
            score = _safe_float(h.get("confidence"))
            if score is None:
                dist = _safe_float(h.get("distance"))
                if dist is not None:
                    score = 1.0 - dist

            meta: dict[str, Any] = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "reaction_type": rt,
                "distance": h.get("distance"),
                "total_chunks": h.get("total_chunks"),
            }
            out.append({"text": text, "score": score, "metadata": meta})

        return out
