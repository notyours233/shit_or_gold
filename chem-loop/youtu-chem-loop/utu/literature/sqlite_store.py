"""SQLite-backed literature store.

Design goals:
- Minimal dependencies (stdlib only) so it works in restricted environments.
- Configurable table/column names so it can connect to *external* literature DBs
  without forcing a single schema.
- Safe-by-default reads: no writes; missing DB should not crash agents/tool calls.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SQLiteLiteratureStoreConfig:
    """Configuration for reading literature from a SQLite DB."""

    db_path: str

    # Main table + columns (configurable to match external DB schemas).
    table: str = "papers"
    id_column: str = "paper_id"
    title_column: str = "title"
    abstract_column: str = "abstract"

    # Optional columns (best-effort: if absent, they are omitted from output).
    doi_column: str | None = "doi"
    year_column: str | None = "year"
    url_column: str | None = "url"
    file_path_column: str | None = "file_path"

    # Search behavior.
    candidate_multiplier: int = 10  # fetch up to limit * candidate_multiplier before scoring
    max_candidates: int = 200
    snippet_chars: int = 400

    extra_columns: list[str] = field(default_factory=list)


class SQLiteLiteratureStore:
    """Read-only helper for searching and fetching paper records from SQLite."""

    def __init__(self, cfg: SQLiteLiteratureStoreConfig):
        self.cfg = cfg

    def _db_exists(self) -> bool:
        return Path(self.cfg.db_path).exists()

    def _connect_ro(self) -> sqlite3.Connection:
        # Using uri=... enables read-only mode. This fails fast when the file is missing.
        # Ref: https://www.sqlite.org/uri.html
        return sqlite3.connect(f"file:{self.cfg.db_path}?mode=ro", uri=True)

    def _list_columns(self, con: sqlite3.Connection) -> set[str]:
        cur = con.cursor()
        cur.execute(f"PRAGMA table_info({self.cfg.table})")
        rows = cur.fetchall()
        # pragma table_info: (cid, name, type, notnull, dflt_value, pk)
        return {r[1] for r in rows}

    def healthcheck(self) -> dict[str, Any]:
        """Return basic connection + schema info to help debug configuration."""
        if not self._db_exists():
            return {
                "ok": False,
                "error": f"DB file not found: {self.cfg.db_path}",
            }
        try:
            with self._connect_ro() as con:
                cols = sorted(self._list_columns(con))
            return {
                "ok": True,
                "db_path": self.cfg.db_path,
                "table": self.cfg.table,
                "columns": cols,
            }
        except Exception as e:  # pylint: disable=broad-except
            return {
                "ok": False,
                "db_path": self.cfg.db_path,
                "table": self.cfg.table,
                "error": str(e),
            }

    def get(self, paper_id: str) -> dict[str, Any]:
        """Fetch one paper by ID (returns dict; may include an 'error' key)."""
        if not self._db_exists():
            return {"error": f"DB file not found: {self.cfg.db_path}"}

        try:
            with self._connect_ro() as con:
                available_cols = self._list_columns(con)
                wanted_cols = self._build_select_columns(available_cols)
                cur = con.cursor()
                cur.execute(
                    f"SELECT {', '.join(wanted_cols)} FROM {self.cfg.table} WHERE {self.cfg.id_column} = ? LIMIT 1",
                    (paper_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return {"error": f"paper_id not found: {paper_id}"}
                return self._row_to_record(wanted_cols, row)
        except Exception as e:  # pylint: disable=broad-except
            return {"error": f"Failed to fetch paper_id={paper_id}: {e}"}

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search papers by simple LIKE matching on title/abstract.

        This intentionally avoids requiring SQLite FTS extensions so it can run
        against many existing external DB files.
        """
        query = (query or "").strip()
        if not query:
            return [{"error": "query must be a non-empty string"}]
        if limit <= 0:
            return [{"error": "limit must be > 0"}]

        if not self._db_exists():
            return [{"error": f"DB file not found: {self.cfg.db_path}"}]

        try:
            tokens = [t for t in query.lower().split() if t]
            # Avoid unbounded candidate scans for very long queries.
            tokens = tokens[:12]

            with self._connect_ro() as con:
                con.row_factory = None
                available_cols = self._list_columns(con)
                wanted_cols = self._build_select_columns(available_cols)

                where_sql, params = self._build_like_where(tokens, available_cols)
                if where_sql is None:
                    return [{"error": "Configured title/abstract columns do not exist in the target table"}]

                fetch_limit = min(max(limit * self.cfg.candidate_multiplier, limit), self.cfg.max_candidates)
                cur = con.cursor()
                cur.execute(
                    f"SELECT {', '.join(wanted_cols)} FROM {self.cfg.table} WHERE {where_sql} LIMIT ?",
                    (*params, fetch_limit),
                )
                rows = cur.fetchall()

            # Score & rank in Python. This keeps SQL simple and portable.
            scored: list[tuple[float, dict[str, Any]]] = []
            for row in rows:
                rec = self._row_to_record(wanted_cols, row)
                score = self._score_record(rec, tokens)
                rec["score"] = score
                rec["abstract_snippet"] = self._build_snippet(rec.get("abstract", ""), tokens)
                scored.append((score, rec))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [rec for _, rec in scored[:limit]]
        except Exception as e:  # pylint: disable=broad-except
            return [{"error": f"Search failed: {e}"}]

    # ---------------------------------------------------------------------
    # helpers

    def _build_select_columns(self, available_cols: set[str]) -> list[str]:
        cols: list[str] = []

        def add(col: str | None):
            if col and col in available_cols and col not in cols:
                cols.append(col)

        add(self.cfg.id_column)
        add(self.cfg.title_column)
        add(self.cfg.abstract_column)
        add(self.cfg.doi_column)
        add(self.cfg.year_column)
        add(self.cfg.url_column)
        add(self.cfg.file_path_column)
        for c in self.cfg.extra_columns:
            add(c)
        return cols

    def _row_to_record(self, cols: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
        rec = {cols[i]: row[i] for i in range(len(cols))}
        # Normalize to a stable external shape (agent-facing keys).
        out: dict[str, Any] = {
            "paper_id": rec.get(self.cfg.id_column),
            "title": rec.get(self.cfg.title_column),
            "abstract": rec.get(self.cfg.abstract_column),
        }
        if self.cfg.doi_column and self.cfg.doi_column in rec:
            out["doi"] = rec.get(self.cfg.doi_column)
        if self.cfg.year_column and self.cfg.year_column in rec:
            out["year"] = rec.get(self.cfg.year_column)
        if self.cfg.url_column and self.cfg.url_column in rec:
            out["url"] = rec.get(self.cfg.url_column)
        if self.cfg.file_path_column and self.cfg.file_path_column in rec:
            out["file_path"] = rec.get(self.cfg.file_path_column)

        # Keep original extra columns (as-is) if present.
        for c in self.cfg.extra_columns:
            if c in rec:
                out[c] = rec[c]
        return out

    def _build_like_where(self, tokens: list[str], available_cols: set[str]) -> tuple[str, list[Any]] | tuple[None, None]:
        title_ok = self.cfg.title_column in available_cols
        abs_ok = self.cfg.abstract_column in available_cols
        if not (title_ok or abs_ok):
            return None, None

        # OR across tokens to avoid overly-strict queries.
        clauses = []
        params: list[Any] = []
        for t in tokens:
            like = f"%{t}%"
            sub = []
            if title_ok:
                sub.append(f"LOWER({self.cfg.title_column}) LIKE ?")
                params.append(like)
            if abs_ok:
                sub.append(f"LOWER({self.cfg.abstract_column}) LIKE ?")
                params.append(like)
            clauses.append("(" + " OR ".join(sub) + ")")
        return " OR ".join(clauses), params

    def _score_record(self, rec: dict[str, Any], tokens: list[str]) -> float:
        title = (rec.get("title") or "").lower()
        abstract = (rec.get("abstract") or "").lower()
        score = 0.0
        for t in tokens:
            if t in title:
                score += 2.0
            if t in abstract:
                score += 1.0
        return score

    def _build_snippet(self, abstract: str | None, tokens: list[str]) -> str:
        text = (abstract or "").strip()
        if not text:
            return ""
        text = " ".join(text.split())  # normalize whitespace
        if len(text) <= self.cfg.snippet_chars:
            return text

        # Try to center snippet around the first matched token.
        lower = text.lower()
        idx = -1
        for t in tokens:
            idx = lower.find(t)
            if idx != -1:
                break
        if idx == -1:
            return text[: self.cfg.snippet_chars] + "..."

        half = self.cfg.snippet_chars // 2
        start = max(idx - half, 0)
        end = min(start + self.cfg.snippet_chars, len(text))
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet

