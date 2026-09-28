"""
Reaction/property ranking utilities.

This module ranks multiple task debate results using each task's calibrated grade.
The grade thresholds are task-specific, so the resulting score is comparable across
directions. Raw metric values are retained for display but are never compared across
different units. Equal normalized scores keep the caller's stable task order.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from utils.performance_grading import grade_rank
from utils.task_types import canonical_task_or_raw


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _canonical_task_key(value: Any) -> str:
    return canonical_task_or_raw(value)


def _extract_summary_fields(item: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[float], Optional[str]]:
    """
    Extract (reaction_type, grade, metric_value, metric_unit) from a per-reaction summary dict.
    """
    if not isinstance(item, dict):
        return "", None, None, None

    pe = item.get("performance_evaluation")
    rt = _canonical_task_key(item.get("task_type") or item.get("property_type") or item.get("reaction_type"))

    grade = None
    metric_value = None
    metric_unit = None
    if isinstance(pe, dict):
        grade = pe.get("grade")
        metric_value = pe.get("metric_value")
        metric_unit = pe.get("metric_unit")
        if not rt:
            rt = _canonical_task_key(pe.get("task_type") or pe.get("property_type") or pe.get("reaction_type"))

    if grade is None:
        grade = item.get("grade")
    if metric_value is None:
        metric_value = item.get("metric_value")
    if metric_unit is None:
        metric_unit = item.get("metric_unit")

    return rt, (str(grade).strip() if grade is not None else None), _to_float(metric_value), (str(metric_unit).strip() if metric_unit else None)


def _sort_key(item: Dict[str, Any]) -> Tuple[int, int]:
    if str(item.get("error") or "").strip():
        return -1, 0

    _rt, grade, metric_value, _metric_unit = _extract_summary_fields(item)

    g_rank = grade_rank(grade or "")
    return g_rank, 1 if metric_value is not None else 0


def _attach_normalized_score(item: Dict[str, Any]) -> None:
    """Attach a unit-free cross-direction score derived from task-specific grades."""
    _rt, grade, _metric_value, _metric_unit = _extract_summary_fields(item)
    rank = grade_rank(grade or "")
    item["normalized_score"] = (rank / 4.0) if rank >= 0 else None
    item["ranking_basis"] = "task_specific_grade"


def rank_reactions(items: List[Dict[str, Any]], top_k: int = 2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Rank reaction summaries and return (ranking, top_k_items).
    """
    safe_items: List[Dict[str, Any]] = [it for it in (items or []) if isinstance(it, dict)]
    for item in safe_items:
        _attach_normalized_score(item)

    ranking = sorted(safe_items, key=_sort_key, reverse=True)
    try:
        k = int(top_k)
    except Exception:
        k = 2
    k = max(0, k)
    selectable: List[Dict[str, Any]] = []
    unscored: List[Dict[str, Any]] = []
    for it in ranking:
        if not isinstance(it, dict) or str(it.get("error") or "").strip():
            continue
        _rt, grade, metric_value, metric_unit = _extract_summary_fields(it)
        if metric_value is None or not str(grade or "").strip() or grade_rank(grade or "") < 0:
            unscored.append(it)
            continue
        if it.get("metric_value") is None:
            it["metric_value"] = metric_value
        if it.get("metric_unit") is None and metric_unit:
            it["metric_unit"] = metric_unit
        if not str(it.get("grade") or "").strip():
            it["grade"] = grade
        selectable.append(it)
    if len(selectable) < k:
        selectable.extend(unscored[: max(0, k - len(selectable))])
    return ranking, selectable[:k]


def rank_properties(items: List[Dict[str, Any]], top_k: int = 2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Alias for the material-property version of the task."""
    return rank_reactions(items, top_k=top_k)
