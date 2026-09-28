"""Quality helpers for material-performance dataset audits."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_VAGUE_NAME_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "collective_or_variable_scope",
        re.compile(r"\b(?:series|family|various|different|several|multiple|assorted|range)\b", re.IGNORECASE),
    ),
    (
        "unspecified_constituent",
        re.compile(
            r"\b(?:transition|rare[- ]earth)\s+metal(?:s|\s+ions|\s+elements)?\b"
            r"|\b(?:various|different|multiple|unspecified)\s+(?:metal\s+)?(?:ions|elements|dopants)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "group_level_descriptor",
        re.compile(
            r"\b(?:materials?|catalysts?|composites?|compounds?|semiconductors?)\s+(?:with|containing|based on)\b"
            r"|\b\w+[- ]based\s+(?:materials?|catalysts?|composites?|compounds?|semiconductors?)\b",
            re.IGNORECASE,
        ),
    ),
)
_ANONYMOUS_SAMPLE_RE = re.compile(
    r"^\s*(?:sample|material|compound|catalyst)?\s*\(?\s*(?:[ivx]{1,5}|\d+[a-z]?)\s*\)?\s*$",
    re.IGNORECASE,
)
_VARIABLE_FORMULA_RE = re.compile(r"(?:\d|\))[+-]?[xyz](?:\b|(?=[A-Z]))|\b[xyz]\s*(?:=|<|>|<=|>=|≤|≥)")
_VARIABLE_SCOPE_RE = re.compile(
    r"\b(?:series|various|different|range|compositions?|concentrations?)\b|\b[xyz]\s*(?:=|<|>|≤|≥)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AuditObservation:
    """One material-context-label observation used for cross-record checks."""

    task_type: str
    doi: str
    material_identity: str
    material_name: str
    context_key: str
    label_key: str
    status: str
    numeric_prediction_ready: bool
    source_file: str
    row_number: int | None
    extraction_index: int | None = None


def canonical_text(value: object) -> str:
    """Normalize text for deterministic audit keys without semantic guessing."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(text.split())


def vague_material_name_reasons(name: object, evidence: object = "") -> tuple[str, ...]:
    """Flag names that identify a family, series, or anonymous sample rather than one material.

    These are review flags, not automatic exclusions. Variable-composition formulas are
    only flagged when their evidence also describes a range or series.
    """
    raw_name = unicodedata.normalize("NFKC", str(name or "")).strip()
    joined = f"{raw_name} {unicodedata.normalize('NFKC', str(evidence or ''))}".strip()
    reasons: list[str] = []
    if raw_name and _ANONYMOUS_SAMPLE_RE.fullmatch(raw_name):
        reasons.append("anonymous_sample_code")
    for reason, pattern in _VAGUE_NAME_PATTERNS:
        if pattern.search(raw_name):
            reasons.append(reason)
    if _VARIABLE_FORMULA_RE.search(raw_name) and _VARIABLE_SCOPE_RE.search(joined):
        reasons.append("variable_composition_range")
    return tuple(sorted(set(reasons)))


def analyze_cross_record_observations(observations: Iterable[AuditObservation]) -> dict[str, Any]:
    """Find exact duplicates and indistinguishable-context label conflicts."""
    items = list(observations)
    exact_groups: dict[tuple[str, str, str, str, str], list[AuditObservation]] = defaultdict(list)
    context_groups: dict[tuple[str, str, str, str], list[AuditObservation]] = defaultdict(list)
    identity_groups: dict[tuple[str, str, str], list[AuditObservation]] = defaultdict(list)
    for item in items:
        exact_groups[(item.task_type, item.doi, item.material_identity, item.context_key, item.label_key)].append(item)
        context_groups[(item.task_type, item.doi, item.material_identity, item.context_key)].append(item)
        identity_groups[(item.task_type, item.doi, item.material_identity)].append(item)

    conflicting_contexts = {
        key: group for key, group in context_groups.items() if len({item.label_key for item in group}) > 1
    }
    multiple_context_identities = {
        key: group for key, group in identity_groups.items() if len({item.context_key for item in group}) > 1
    }

    by_task: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        by_task[item.task_type]["raw_observations"] += 1
    for key, group in exact_groups.items():
        task = key[0]
        by_task[task]["unique_context_label_samples"] += 1
        if len(group) > 1:
            by_task[task]["exact_duplicate_groups"] += 1
            by_task[task]["exact_duplicate_observations_removed"] += len(group) - 1
    for key, group in conflicting_contexts.items():
        task = key[0]
        by_task[task]["conflicting_context_groups"] += 1
        by_task[task]["raw_observations_in_conflicting_contexts"] += len(group)
    for key in multiple_context_identities:
        by_task[key[0]]["material_identities_with_multiple_contexts"] += 1

    status_rank = {"manual_review": 0, "recoverable": 1, "direct": 2}
    for key, group in exact_groups.items():
        task, doi, material_identity, context_key, _ = key
        if (task, doi, material_identity, context_key) in conflicting_contexts:
            continue
        best_status = max((item.status for item in group), key=lambda status: status_rank.get(status, -1))
        by_task[task]["unique_nonconflicting_samples"] += 1
        by_task[task][f"unique_{best_status}_samples"] += 1
        if best_status in {"direct", "recoverable"}:
            by_task[task]["unique_trainable_samples"] += 1
            if any(item.numeric_prediction_ready for item in group):
                by_task[task]["numeric_prediction_ready_samples"] += 1

    totals: Counter[str] = Counter()
    for counts in by_task.values():
        totals.update(counts)

    conflict_examples = []
    for key, group in sorted(conflicting_contexts.items()):
        conflict_examples.append(
            {
                "task_type": key[0],
                "doi": key[1],
                "material_name": group[0].material_name,
                "context_key": key[3],
                "labels": sorted({item.label_key for item in group}),
                "source_rows": sorted(
                    {f"{item.source_file}:{item.row_number}:{item.extraction_index}" for item in group}
                ),
            }
        )

    return {
        "totals": dict(totals),
        "by_task": {task: dict(counts) for task, counts in sorted(by_task.items())},
        "definitions": {
            "exact_duplicate": "Same task, DOI, normalized material, metric context, and label.",
            "conflict": "Same task, DOI, normalized material, and metric context but different labels.",
            "multiple_context": (
                "Same task, DOI, and material with distinguishable metric contexts; usually legitimate."
            ),
        },
        "conflict_examples": conflict_examples,
    }
