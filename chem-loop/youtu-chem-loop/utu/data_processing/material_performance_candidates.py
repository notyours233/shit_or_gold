"""Build material-performance candidates with the audit's binding rules.

Candidates are the shared intermediate representation between source auditing
and dataset construction.  They preserve the complete bound material and label
payload while exposing the same keys used by the cross-record quality gate.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utu.data_processing.material_performance_audit import (
    NEW_FILE_TASKS,
    OLD_FILE_TASKS,
    TruthTarget,
    _bind_new_extraction,
    _bind_truth_by_elements,
    _deduplicate_truth_targets,
    _evidence_text,
    _material_identity,
    _metric_context_key,
    _metric_quality,
    _new_extraction_context,
    _new_extraction_label_key,
    _unit_suffix,
    is_generic_material_name,
    iter_jsonl,
    load_established_truth,
    material_names,
    normalize_doi,
    parse_numeric,
)
from utu.data_processing.material_performance_quality import (
    AuditObservation,
    vague_material_name_reasons,
)

NEW_TASK_METRIC_FIELDS: dict[str, tuple[str, ...]] = {
    "photocatalytic_h2o2": ("apparent_quantum_efficiency",),
    "antibacterial": ("bactericidal_threshold", "minimum_concentration"),
    "thermoelectric": ("figure_of_merit",),
    "furfural_hydrogenation": ("furfuryl_alcohol_yield",),
}

_ORGANISM_RE = re.compile(
    r"e\.\s*coli|s\.\s*aureus|p\.\s*aeruginosa|b\.\s*subtilis|"
    r"escherichia\s+coli|staphylococcus\s+aureus|pseudomonas\s+aeruginosa|bacillus\s+subtilis",
    re.IGNORECASE,
)
_WAVELENGTH_RE = re.compile(r"\b\d+(?:\.\d+)?\s*nm\b", re.IGNORECASE)
_FURFURAL_CONDITION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:k|°c|c|bar|mpa|h|min)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MaterialPerformanceCandidate:
    """One source observation linking a material to one performance payload."""

    task_type: str
    doi: str
    material: Mapping[str, Any] | None
    material_index: int | None
    metrics: Mapping[str, Any]
    units: Mapping[str, Any]
    categorical_metrics: Mapping[str, Any]
    conditions: Mapping[str, Any]
    product: str | None
    status: str
    binding_mode: str
    reasons: tuple[str, ...]
    context_key: str
    label_key: str
    source_group: str
    source_file: str
    row_number: int | None
    extraction_index: int | None
    truth_source_file: str | None = None
    truth_source_index: int | None = None

    @property
    def material_name(self) -> str:
        if not isinstance(self.material, Mapping):
            return "<ambiguous>"
        return str(self.material.get("material_name") or "").strip() or "<ambiguous>"

    @property
    def material_identity(self) -> str:
        return _material_identity(self.material_name, self.material_index)

    @property
    def quality_flags(self) -> tuple[str, ...]:
        if not isinstance(self.material, Mapping):
            return ()
        vague = vague_material_name_reasons(self.material.get("material_name"), self.material.get("evidence"))
        return tuple(sorted(set(self.reasons).union(vague)))

    def to_audit_observation(self) -> AuditObservation:
        """Return the exact projection consumed by the audit quality gate."""
        return AuditObservation(
            task_type=self.task_type,
            doi=self.doi,
            material_identity=self.material_identity,
            material_name=self.material_name,
            context_key=self.context_key,
            label_key=self.label_key,
            status=self.status,
            numeric_prediction_ready=(
                self.status in {"direct", "recoverable"}
                and bool(self.metrics)
                and all(parse_numeric(value) is not None for value in self.metrics.values())
            ),
            source_file=self.source_file,
            row_number=self.row_number,
            extraction_index=self.extraction_index,
        )


@dataclass(frozen=True)
class CandidateSelection:
    """Result of exact deduplication and context-conflict quarantine."""

    selected: tuple[MaterialPerformanceCandidate, ...]
    excluded: tuple[tuple[MaterialPerformanceCandidate, str], ...]
    stats: Mapping[str, Any]


def _material_list(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = record.get("final_materials")
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, Mapping)]


def _new_conditions(task: str, extraction: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _evidence_text(extraction)
    if task == "thermoelectric":
        temperature = str(extraction.get("temperature") or "").strip()
        return {"temperature": temperature} if temperature else {}
    if task == "photocatalytic_h2o2":
        wavelengths = sorted({match.group(0) for match in _WAVELENGTH_RE.finditer(evidence)})
        return {"wavelengths": wavelengths} if wavelengths else {}
    if task == "antibacterial":
        organisms = sorted({match.group(0) for match in _ORGANISM_RE.finditer(evidence)})
        return {"organisms": organisms} if organisms else {}
    if task == "furfural_hydrogenation":
        values = sorted({match.group(0) for match in _FURFURAL_CONDITION_RE.finditer(evidence)})
        return {"reported_conditions": values} if values else {}
    return {}


def _new_metric_payload(
    task: str, extraction: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    metrics: dict[str, Any] = {}
    units: dict[str, Any] = {}
    categorical: dict[str, Any] = {}
    for field in NEW_TASK_METRIC_FIELDS.get(task, ()):
        raw = extraction.get(field)
        if raw in (None, ""):
            continue
        if parse_numeric(raw) is None:
            categorical[field] = raw
            continue
        metrics[field] = raw
        unit = _unit_suffix(raw)
        if unit:
            units[field] = unit
    return metrics, units, categorical


def iter_established_candidates(
    source_dir: Path,
    truth_by_doi: Mapping[tuple[str, str], Sequence[TruthTarget]],
    truth_by_row: Mapping[tuple[str, str, int], Sequence[TruthTarget]],
) -> Iterator[MaterialPerformanceCandidate]:
    """Yield candidates for the established 15 directions."""
    for filename, task in OLD_FILE_TASKS.items():
        for record in iter_jsonl(source_dir / filename):
            doi = normalize_doi(record.get("doi"))
            row_number = record.get("row_number")
            targets: Sequence[TruthTarget] = ()
            if doi and isinstance(row_number, int):
                targets = truth_by_row.get((task, doi, row_number), ())
            if not targets and doi:
                targets = truth_by_doi.get((task, doi), ())

            unique_targets, _, has_conflict = _deduplicate_truth_targets(list(targets))
            materials = _material_list(record)
            names = material_names(record)
            for target_index, target in enumerate(unique_targets):
                material_index: int | None = None
                binding_mode = "unbound"
                reasons: list[str] = []
                if has_conflict:
                    status = "manual_review"
                    reasons.append("conflicting_labels_for_same_context")
                elif len(materials) == 1 and names and not is_generic_material_name(names[0]):
                    status = "direct"
                    material_index = 0
                    binding_mode = "single_material"
                elif len(materials) > 1:
                    matched_index, matched_mode = _bind_truth_by_elements(materials, target)
                    if (
                        matched_index is not None
                        and matched_mode
                        and not is_generic_material_name(names[matched_index])
                    ):
                        status = "recoverable"
                        material_index = matched_index
                        binding_mode = matched_mode
                    else:
                        status = "manual_review"
                        reasons.append("multiple_materials_not_uniquely_bound")
                else:
                    status = "manual_review"
                    reasons.append("missing_or_generic_material_name")

                yield MaterialPerformanceCandidate(
                    task_type=task,
                    doi=doi,
                    material=materials[material_index] if material_index is not None else None,
                    material_index=material_index,
                    metrics=dict(target.metrics),
                    units=dict(target.units),
                    categorical_metrics={},
                    conditions={},
                    product=target.product,
                    status=status,
                    binding_mode=binding_mode,
                    reasons=tuple(sorted(set(reasons))),
                    context_key=_metric_context_key(task, target.metrics, target.product),
                    label_key=target.label_key,
                    source_group="established_15",
                    source_file=filename,
                    row_number=row_number if isinstance(row_number, int) else None,
                    extraction_index=target_index,
                    truth_source_file=target.source_file,
                    truth_source_index=target.source_index,
                )


def iter_new_candidates(source_dir: Path) -> Iterator[MaterialPerformanceCandidate]:
    """Yield candidates for the four newly extracted directions."""
    for filename, task in NEW_FILE_TASKS.items():
        for record in iter_jsonl(source_dir / filename):
            doi = normalize_doi(record.get("doi"))
            row_number = record.get("row_number")
            materials = _material_list(record)
            extractions = record.get("property_extractions")
            if not isinstance(extractions, list):
                continue
            for extraction_index, extraction in enumerate(extractions):
                if not isinstance(extraction, Mapping):
                    continue
                metric_status, metric_reasons, _ = _metric_quality(task, extraction)
                binding_status, material_index, binding_reasons = _bind_new_extraction(materials, extraction)
                if metric_status == "unusable" or binding_status == "manual_review":
                    status = "manual_review"
                elif metric_status == "recoverable" or binding_status == "recoverable":
                    status = "recoverable"
                else:
                    status = "direct"

                metrics, units, categorical = _new_metric_payload(task, extraction)
                if material_index is None:
                    binding_mode = "unbound"
                elif binding_reasons:
                    binding_mode = binding_reasons[0]
                elif str(extraction.get("material_name") or "").strip():
                    binding_mode = "explicit_material_name"
                else:
                    binding_mode = "single_material"

                yield MaterialPerformanceCandidate(
                    task_type=task,
                    doi=doi,
                    material=materials[material_index] if material_index is not None else None,
                    material_index=material_index,
                    metrics=metrics,
                    units=units,
                    categorical_metrics=categorical,
                    conditions=_new_conditions(task, extraction),
                    product=None,
                    status=status,
                    binding_mode=binding_mode,
                    reasons=tuple(sorted(set(metric_reasons + binding_reasons))),
                    context_key=json.dumps(
                        _new_extraction_context(task, extraction), ensure_ascii=False, sort_keys=True
                    ),
                    label_key=_new_extraction_label_key(task, extraction),
                    source_group="new_4",
                    source_file=filename,
                    row_number=row_number if isinstance(row_number, int) else None,
                    extraction_index=extraction_index,
                )


def iter_material_performance_candidates(
    *,
    established_source_dir: Path,
    new_source_dir: Path,
    reaction_dataset: Path,
    material_truth: Path,
) -> Iterator[MaterialPerformanceCandidate]:
    """Yield all 19-direction candidates from immutable source inputs."""
    truth_by_doi, truth_by_row, _, _ = load_established_truth(reaction_dataset, material_truth)
    yield from iter_established_candidates(established_source_dir, truth_by_doi, truth_by_row)
    yield from iter_new_candidates(new_source_dir)


def _source_sort_key(candidate: MaterialPerformanceCandidate) -> tuple[Any, ...]:
    return (
        candidate.source_file,
        candidate.row_number if candidate.row_number is not None else -1,
        candidate.extraction_index if candidate.extraction_index is not None else -1,
        candidate.material_index if candidate.material_index is not None else -1,
    )


def select_candidates(candidates: Iterable[MaterialPerformanceCandidate]) -> CandidateSelection:
    """Apply the same exact-deduplication and conflict policy as the audit."""
    items = list(candidates)
    exact_groups: dict[tuple[str, str, str, str, str], list[MaterialPerformanceCandidate]] = defaultdict(list)
    context_labels: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for item in items:
        exact_key = (
            item.task_type,
            item.doi,
            item.material_identity,
            item.context_key,
            item.label_key,
        )
        context_key = exact_key[:-1]
        exact_groups[exact_key].append(item)
        context_labels[context_key].add(item.label_key)

    status_rank = {"manual_review": 0, "recoverable": 1, "direct": 2}
    selected: list[MaterialPerformanceCandidate] = []
    excluded: list[tuple[MaterialPerformanceCandidate, str]] = []
    stats: Counter[str] = Counter(raw_candidates=len(items))
    by_task: dict[str, Counter[str]] = defaultdict(Counter)

    for exact_key, group in sorted(exact_groups.items()):
        task = exact_key[0]
        context_key = exact_key[:-1]
        ordered = sorted(
            group,
            key=lambda item: (-status_rank.get(item.status, -1), _source_sort_key(item)),
        )
        best = ordered[0]
        for duplicate in ordered[1:]:
            excluded.append((duplicate, "exact_duplicate"))
            by_task[task]["exact_duplicates_removed"] += 1
        if len(context_labels[context_key]) > 1:
            excluded.append((best, "conflicting_context"))
            by_task[task]["conflicting_unique_labels_excluded"] += 1
            continue
        if best.status in {"direct", "recoverable"} and isinstance(best.material, Mapping) and best.metrics:
            selected.append(best)
            by_task[task]["selected_candidates"] += 1
            by_task[task][f"selected_{best.status}"] += 1
        else:
            excluded.append((best, "manual_review_or_missing_minimum_fields"))
            by_task[task]["manual_or_unusable_excluded"] += 1

    selected.sort(key=lambda item: (item.task_type, item.doi, item.material_identity, item.context_key))
    stats["selected_candidates"] = len(selected)
    stats["excluded_observations"] = len(excluded)
    for _, reason in excluded:
        stats[f"excluded_{reason}"] += 1
    report: dict[str, Any] = dict(stats)
    report["by_task"] = {task: dict(values) for task, values in sorted(by_task.items())}
    return CandidateSelection(tuple(selected), tuple(excluded), report)
