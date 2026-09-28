"""Chem-performance label-leakage masking helpers.

Goal
-----
During Training-Free GRPO / eval dataset rollouts, the agent may use the external
literature DB (Chroma) for evidence. However, the ground-truth metric value for a
sample often comes from a specific paper; if the model can retrieve that paper's
chunks, it can copy the answer (label leakage).

This module resolves `sample_id -> doc_id (DOI)` using the local TSV mapping under
`rawdata/` so the runner can inject `masked_doc_ids=[...]` into the toolkit config.

Important:
- Masking is enforced in code (toolkit config / filtering), NOT via prompt rules.
- The masked DOI/doc_id list MUST NOT be returned to the model via tool outputs.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import select

from ..db import DatasetSample
from ..utils import DIR_ROOT, SQLModelUtils, get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ChemPerformanceRawdataTSVConfig:
    """Where to find the sample-id -> DOI mapping TSV files."""

    rawdata_dir: Path = DIR_ROOT / "rawdata"
    file_template: str = "2-cleaned-abstracts-about-{reaction_type}.tsv"
    index_column: str = "index"
    doi_column: str = "doi"


def _safe_int(val: Any) -> int | None:
    try:
        if val is None:
            return None
        if isinstance(val, int):
            return val
        s = str(val).strip()
        if not s:
            return None
        return int(s)
    except Exception:  # pylint: disable=broad-except
        return None


def load_doi_map_from_tsv(tsv_path: Path, *, wanted_ids: set[int], index_col: str = "index", doi_col: str = "doi") -> dict[int, str]:
    """Scan a large TSV once and extract only the DOI rows we care about.

    The TSV files in `rawdata/` are big (hundreds of MB) because they contain full
    abstracts. We avoid loading everything into memory by scanning once and only
    keeping the `index -> doi` pairs for the ids we actually need.
    """

    if not wanted_ids:
        return {}

    # Some abstracts can be very long; raise the CSV field limit defensively.
    try:
        csv.field_size_limit(1024 * 1024 * 1024)  # 1 GiB
    except Exception:  # pylint: disable=broad-except
        pass

    remaining = set(wanted_ids)
    out: dict[int, str] = {}

    with tsv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        if not header:
            raise ValueError(f"Empty TSV: {tsv_path}")
        try:
            idx_i = header.index(index_col)
            doi_i = header.index(doi_col)
        except ValueError as e:
            raise ValueError(f"TSV missing required columns: {e}. header={header}") from e

        for row in reader:
            if not row:
                continue
            # Defensive: short rows can occur if the TSV is malformed.
            if idx_i >= len(row) or doi_i >= len(row):
                continue

            idx = _safe_int(row[idx_i])
            if idx is None or idx not in remaining:
                continue

            doi = str(row[doi_i]).strip()
            if doi:
                out[idx] = doi
            remaining.remove(idx)
            if not remaining:
                break

    if remaining:
        logger.warning(
            "Chem-performance DOI mapping incomplete for %s: missing %d/%d ids (example_missing=%s)",
            tsv_path.name,
            len(remaining),
            len(wanted_ids),
            sorted(list(remaining))[:5],
        )
    return out


class ChemPerformanceDocIdResolver:
    """Resolve chem-performance sample id -> DOI/doc_id using `rawdata/*.tsv`.

    This class is safe to use in concurrent rollouts within a single process:
    it caches only small dicts (for the current dataset) and never mutates
    shared AgentConfig objects.
    """

    def __init__(self, cfg: ChemPerformanceRawdataTSVConfig | None = None) -> None:
        self.cfg = cfg or ChemPerformanceRawdataTSVConfig()

        # dataset -> reaction_type -> set(sample_id)
        self._needed_ids_by_dataset: dict[str, dict[str, set[int]]] = {}

        # (dataset, reaction_type) -> {sample_id: doi}
        self._doi_map_cache: dict[tuple[str, str], dict[int, str]] = {}

    def _get_needed_ids_for_dataset(self, dataset: str) -> dict[str, set[int]]:
        if dataset in self._needed_ids_by_dataset:
            return self._needed_ids_by_dataset[dataset]

        # If the DB is unavailable, masking can't be computed safely; degrade gracefully.
        if not SQLModelUtils.check_db_available():
            self._needed_ids_by_dataset[dataset] = {}
            return {}

        by_rt: dict[str, set[int]] = defaultdict(set)
        with SQLModelUtils.create_session() as session:
            dps = session.exec(select(DatasetSample).where(DatasetSample.dataset == dataset)).all()
        for dp in dps:
            meta = dp.meta or {}
            rt = (meta.get("reaction_type") or "").strip()
            sid = _safe_int(meta.get("id"))
            if rt and sid is not None:
                by_rt[rt].add(sid)

        self._needed_ids_by_dataset[dataset] = dict(by_rt)
        return self._needed_ids_by_dataset[dataset]

    def _load_reaction_doi_map(self, *, dataset: str, reaction_type: str) -> dict[int, str]:
        cache_key = (dataset, reaction_type)
        if cache_key in self._doi_map_cache:
            return self._doi_map_cache[cache_key]

        needed = self._get_needed_ids_for_dataset(dataset).get(reaction_type) or set()
        if not needed:
            self._doi_map_cache[cache_key] = {}
            return {}

        tsv_path = self.cfg.rawdata_dir / self.cfg.file_template.format(reaction_type=reaction_type)
        if not tsv_path.exists():
            logger.warning("Rawdata TSV not found for reaction_type=%s: %s", reaction_type, tsv_path)
            self._doi_map_cache[cache_key] = {}
            return {}

        mapping = load_doi_map_from_tsv(
            tsv_path,
            wanted_ids=needed,
            index_col=self.cfg.index_column,
            doi_col=self.cfg.doi_column,
        )
        self._doi_map_cache[cache_key] = mapping
        return mapping

    def resolve_doc_id(self, *, dataset: str, reaction_type: str, sample_id: Any) -> str | None:
        """Return DOI/doc_id for this (dataset, reaction_type, sample_id) triple, if available."""

        dataset = (dataset or "").strip()
        reaction_type = (reaction_type or "").strip()
        sid = _safe_int(sample_id)
        if not dataset or not reaction_type or sid is None:
            return None

        m = self._load_reaction_doi_map(dataset=dataset, reaction_type=reaction_type)
        doi = m.get(sid)
        if not doi:
            return None
        return str(doi).strip()


# Module-level singleton for rollout/eval processes.
CHEM_PERF_DOC_ID_RESOLVER = ChemPerformanceDocIdResolver()

