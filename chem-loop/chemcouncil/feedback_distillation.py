from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .analytics import (
    RecommendationContext,
    canonical_reaction_type,
    compute_prediction_error_records_multi_debug,
    extract_recommendation_job_id,
    iter_experimental_csv_rows,
)
from .jobs import JobStore


_PRODUCT_LINE_RE = re.compile(r"^\s*Products:\s*(?P<value>.+?)\s*$", flags=re.MULTILINE)
_REACTION_TYPE_RE = re.compile(r"\b(?:Reaction\s*Type|Target\s*reaction)\s*:\s*(?P<rt>[A-Za-z0-9_+-]+)\b")
_FE_PERCENT_RE = re.compile(
    r"(?:\bFE\b|Faradaic\s*efficiency)\s*(?:\([^)]+\))?\s*[=:]?\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*%",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class FeedbackDistillExample:
    update_job_id: str
    csv_row_index: int
    recommendation_job_id: str
    recommendation_finished_at_utc: str | None
    reaction_type: str
    metric_key: str
    unit: str
    predicted_value: float
    actual_value: float
    abs_error: float
    rel_error: float
    score: float
    components: str
    condition: str | None
    actual_product: str | None
    predicted_product: str | None
    actual_faradaic_efficiency: float | None
    predicted_faradaic_efficiency: float | None
    final_performance: str | None
    trace_path: str
    trace_reaction_type: str | None
    csv_row: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_rank_item_map(rank_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    ranking = rank_result.get("ranking") or []
    if not isinstance(ranking, list):
        return out
    for item in ranking:
        if not isinstance(item, dict):
            continue
        rt = canonical_reaction_type(item.get("task_type") or item.get("reaction_type") or item.get("property_type"))
        if not rt:
            continue
        out[rt] = item
    return out


def _extract_predicted_product(*, rank_item: dict[str, Any] | None, trace_path: Path | None) -> str | None:
    if isinstance(rank_item, dict):
        raw = rank_item.get("final_products")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        perf = rank_item.get("final_performance")
        if isinstance(perf, str) and perf.strip():
            m = _PRODUCT_LINE_RE.search(perf)
            if m:
                value = m.group("value").strip()
                if value and value.upper() != "N/A":
                    return value.split("(")[0].strip()

    if trace_path is not None and trace_path.exists():
        try:
            raw = json.loads(trace_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        for claim in _iter_trace_claims(raw):
            m = _PRODUCT_LINE_RE.search(claim)
            if not m:
                continue
            value = m.group("value").strip()
            if value and value.upper() != "N/A":
                return value.split("(")[0].strip()
    return None


def _parse_percent_fraction(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        try:
            return float(text[:-1].strip()) / 100.0
        except ValueError:
            return None
    try:
        num = float(text)
    except ValueError:
        return None
    return num / 100.0 if num > 1.0 else num


def _extract_predicted_faradaic_efficiency(*, rank_item: dict[str, Any] | None, trace_path: Path | None) -> float | None:
    candidates: list[str] = []
    if isinstance(rank_item, dict):
        perf = rank_item.get("final_performance")
        if isinstance(perf, str) and perf.strip():
            candidates.append(perf)

    if trace_path is not None and trace_path.exists():
        try:
            raw = json.loads(trace_path.read_text(encoding="utf-8"))
        except Exception:
            raw = None
        if isinstance(raw, dict):
            candidates.extend(_iter_trace_claims(raw))

    for text in candidates:
        match = _FE_PERCENT_RE.search(text)
        if not match:
            continue
        try:
            return float(match.group("value")) / 100.0
        except ValueError:
            continue
    return None


def _iter_trace_claims(raw: dict[str, Any]) -> list[str]:
    out: list[str] = []
    result = raw.get("result") if isinstance(raw, dict) else {}
    if not isinstance(result, dict):
        return out
    for key in ("surviving_proposals", "defeated_proposals", "withdrawn_proposals"):
        items = result.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            claim = item.get("claim")
            if isinstance(claim, str) and claim.strip():
                out.append(claim.strip())
    return out


def _infer_trace_reaction_type(raw: dict[str, Any]) -> str | None:
    top_level = canonical_reaction_type(raw.get("reaction_type"))
    if top_level:
        return top_level
    for claim in _iter_trace_claims(raw):
        match = _REACTION_TYPE_RE.search(claim)
        if not match:
            continue
        inferred = canonical_reaction_type(match.group("rt"))
        if inferred:
            return inferred
    return None


def _trace_paths_by_recommendation_job(store: JobStore, recommendation_job_id: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    mad_outputs_dir = store.job_dir(recommendation_job_id) / "artifacts" / "mad_outputs"
    if not mad_outputs_dir.exists():
        return out

    result_files = sorted(mad_outputs_dir.glob("result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in result_files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reaction_type = _infer_trace_reaction_type(raw)
        if not reaction_type or reaction_type in out:
            continue
        out[reaction_type] = path.resolve()
    return out


def build_feedback_distill_examples(
    *,
    store: JobStore,
    update_job_id: str,
    update_finished_at_utc: str | None,
    upload_csv_path: Path,
    recommendation_contexts: dict[str, RecommendationContext],
    default_recommendation_job_id: str | None = None,
) -> tuple[list[FeedbackDistillExample], dict[str, Any]]:
    raw_rows: dict[int, dict[str, Any]] = {
        idx: row for idx, row in enumerate(iter_experimental_csv_rows(upload_csv_path), start=1)
    }
    error_records, debug = compute_prediction_error_records_multi_debug(
        update_job_id=update_job_id,
        update_finished_at_utc=update_finished_at_utc,
        upload_csv_path=upload_csv_path,
        recommendation_contexts=recommendation_contexts,
        default_recommendation_job_id=default_recommendation_job_id,
    )

    trace_maps: dict[str, dict[str, Path]] = {
        recommendation_job_id: _trace_paths_by_recommendation_job(store, recommendation_job_id)
        for recommendation_job_id in recommendation_contexts
    }
    rank_item_maps: dict[str, dict[str, dict[str, Any]]] = {
        recommendation_job_id: _load_rank_item_map(ctx.recommendation_rank_result)
        for recommendation_job_id, ctx in recommendation_contexts.items()
    }

    examples: list[FeedbackDistillExample] = []
    missing_trace_rows = 0

    for record in error_records:
        row = raw_rows.get(record.csv_row_index) or {}
        trace_path = (trace_maps.get(record.recommendation_job_id) or {}).get(record.reaction_type)
        if trace_path is None:
            missing_trace_rows += 1
            continue

        rank_item = (rank_item_maps.get(record.recommendation_job_id) or {}).get(record.reaction_type) or {}
        actual_product_raw = row.get("product") or row.get("products") or row.get("产物") or row.get("主要产物") or row.get("主产物")
        actual_product = str(actual_product_raw).strip() if actual_product_raw is not None and str(actual_product_raw).strip() else None
        actual_fe_raw = (
            row.get("faradaic_efficiency")
            or row.get("faradaic efficiency")
            or row.get("FE")
            or row.get("fe")
            or row.get("法拉第效率")
            or row.get("产物法拉第效率")
        )
        actual_faradaic_efficiency = _parse_percent_fraction(actual_fe_raw)
        condition_raw = row.get("condition") or row.get("条件")
        condition = str(condition_raw).strip() if condition_raw is not None and str(condition_raw).strip() else None
        predicted_product = _extract_predicted_product(rank_item=rank_item, trace_path=trace_path)
        predicted_faradaic_efficiency = _extract_predicted_faradaic_efficiency(rank_item=rank_item, trace_path=trace_path)

        examples.append(
            FeedbackDistillExample(
                update_job_id=record.update_job_id,
                csv_row_index=record.csv_row_index,
                recommendation_job_id=record.recommendation_job_id,
                recommendation_finished_at_utc=record.recommendation_finished_at_utc,
                reaction_type=record.reaction_type,
                metric_key=record.metric_key,
                unit=record.unit,
                predicted_value=record.predicted_value,
                actual_value=record.actual_value,
                abs_error=record.abs_error,
                rel_error=record.rel_error,
                score=record.score,
                components=record.components,
                condition=condition,
                actual_product=actual_product,
                predicted_product=predicted_product,
                actual_faradaic_efficiency=actual_faradaic_efficiency,
                predicted_faradaic_efficiency=predicted_faradaic_efficiency,
                final_performance=str(rank_item.get("final_performance") or "").strip() or None,
                trace_path=str(trace_path),
                trace_reaction_type=record.reaction_type,
                csv_row=row,
            )
        )

    summary = {
        "csv_rows_total": len(raw_rows),
        "prediction_error_records_scored": len(error_records),
        "feedback_alignment_examples_built": len(examples),
        "rows_missing_matching_trace": missing_trace_rows,
        "debug": debug.__dict__,
    }
    return examples, summary
