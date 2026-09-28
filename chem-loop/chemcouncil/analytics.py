from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MATERIAL_PROPERTY_TYPES = {
    "photothermal_conversion_efficiency",
    "conductivity",
    "thermal_conductivity",
    "ferromagnetism",
    "ferrimagnetism",
    "antiferromagnetism",
    "photocatalytic_h2o2",
    "antibacterial",
    "thermoelectric",
    "furfural_hydrogenation",
}


REACTION_METRIC: dict[str, dict[str, Any]] = {
    # Current material-property project. Keep the "reaction_type" name for
    # compatibility with existing MAD rank/result payloads.
    "photothermal_conversion_efficiency": {
        "metric_key": "photothermal_conversion_efficiency",
        "unit": "%",
        "require_condition": False,
    },
    "conductivity": {"metric_key": "conductivity", "unit": "S/m", "require_condition": False},
    "thermal_conductivity": {
        "metric_key": "thermal_conductivity",
        "unit": "W m-1 K-1",
        "require_condition": False,
    },
    "ferromagnetism": {"metric_key": "saturation_magnetization", "unit": "emu/g", "require_condition": False},
    "ferrimagnetism": {"metric_key": "saturation_magnetization", "unit": "emu/g", "require_condition": False},
    "antiferromagnetism": {"metric_key": "neel_temperature", "unit": "K", "require_condition": False},
    "photocatalytic_h2o2": {
        "metric_key": "apparent_quantum_efficiency",
        "unit": "%",
        "require_condition": False,
    },
    "antibacterial": {"metric_key": "minimum_concentration", "unit": "ppm", "require_condition": False},
    "thermoelectric": {"metric_key": "figure_of_merit", "unit": "dimensionless", "require_condition": False},
    "furfural_hydrogenation": {
        "metric_key": "furfuryl_alcohol_yield",
        "unit": "%",
        "require_condition": False,
    },
    # v5 scope (one canonical metric per reaction_type).
    # CO2RR keeps partial_current_density as the legacy default metric, but
    # analytics expands it into FE + partial_current_density when available.
    "HER": {"metric_key": "overpotential_10mAcm-2", "unit": "mV", "require_condition": True},
    "OER": {"metric_key": "overpotential_10mAcm-2", "unit": "mV", "require_condition": True},
    "HZOR": {"metric_key": "overpotential_10mAcm-2", "unit": "mV", "require_condition": True},
    "UOR": {"metric_key": "potential_10mAcm-2", "unit": "V", "require_condition": True},
    "ORR": {"metric_key": "half_wave_potential", "unit": "V", "require_condition": False},
    "HOR": {"metric_key": "exchange_current_density", "unit": "mA cm-2", "require_condition": False},
    "EOR": {"metric_key": "mass_activity", "unit": "A mg^-1", "require_condition": False},
    "O5H": {"metric_key": "faradaic_efficiency", "unit": "fraction_0_to_1", "require_condition": False},
    "CO2RR": {"metric_key": "partial_current_density", "unit": "mA cm-2", "require_condition": False},
}


def canonical_reaction_type(value: str | None) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if s in REACTION_METRIC:
        return s
    low = s.lower().replace("-", "_")
    low = "_".join(low.split())
    aliases = {
        "photothermal": "photothermal_conversion_efficiency",
        "photothermal_conversion_efficiency": "photothermal_conversion_efficiency",
        "electrical_conductivity": "conductivity",
        "conductivity": "conductivity",
        "thermal_conductivity": "thermal_conductivity",
        "ferromagnetic": "ferromagnetism",
        "ferromagnetism": "ferromagnetism",
        "ferrimagnetic": "ferrimagnetism",
        "ferrimagnetism": "ferrimagnetism",
        "anti_ferromagnetism": "antiferromagnetism",
        "anti_ferromagnetic": "antiferromagnetism",
        "antiferromagnetic": "antiferromagnetism",
        "antiferromagnetism": "antiferromagnetism",
        "photocatalytic_h2o2": "photocatalytic_h2o2",
        "photocatalytic_hydrogen_peroxide": "photocatalytic_h2o2",
        "photocatalytic h2o2": "photocatalytic_h2o2",
        "antibacterial": "antibacterial",
        "antimicrobial": "antibacterial",
        "thermoelectric": "thermoelectric",
        "zt": "thermoelectric",
        "furfural_hydrogenation": "furfural_hydrogenation",
        "furfural hydrogenation": "furfural_hydrogenation",
        "光热转换效率": "photothermal_conversion_efficiency",
        "电导率": "conductivity",
        "热导率": "thermal_conductivity",
        "铁磁性": "ferromagnetism",
        "亚铁磁性": "ferrimagnetism",
        "反铁磁性": "antiferromagnetism",
        "光催化h2o2": "photocatalytic_h2o2",
        "抑菌": "antibacterial",
        "热电": "thermoelectric",
        "糠醛加氢": "furfural_hydrogenation",
    }
    if low in aliases:
        return aliases[low]
    up = s.upper()
    if up == "HZOR":
        return "HZOR"
    if up in {"HER", "OER", "ORR", "HOR", "UOR", "EOR", "O5H", "CO2RR"}:
        return up
    # Best-effort: keep original (helps debugging) but normalize spaces.
    return " ".join(s.split())


_DASH_TRANSLATION = str.maketrans({"−": "-", "–": "-", "‑": "-", "—": "-"})
# Numeric prefix regex used to parse values like "300 mV" / "~0.8 V vs RHE".
# NOTE: use single backslashes inside raw strings (`\d`, `\s`) to mean regex tokens.
_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_PRODUCT_LINE_RE = re.compile(r"^\s*Products:\s*(?P<value>.+?)\s*$", flags=re.MULTILINE)
_FE_PERCENT_PATTERNS = (
    re.compile(
        r"(?:\bFE\b|Faradaic\s*efficiency)\s*(?:\([^)]+\))?\s*(?:[=:]|\bis\b|\bof\b)?\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*%",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*%\s*(?:\bFE\b|Faradaic\s*efficiency)",
        flags=re.IGNORECASE,
    ),
)
_PCD_PATTERNS = (
    re.compile(
        r"(?:\bj[_A-Za-z0-9+]+\b|partial(?:\s+current)?\s*density)[^0-9\-+]{0,24}(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>mA|A)\s*(?:/|\s+)?\s*cm(?:\^?-?2|²|2)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>mA|A)\s*(?:/|\s+)?\s*cm(?:\^?-?2|²|2)[^A-Za-z]{0,24}(?:partial(?:\s+current)?\s*density|\bj[_A-Za-z0-9+]+\b)",
        flags=re.IGNORECASE,
    ),
)
CO2RR_ANALYTICS_METRICS: tuple[tuple[str, str], ...] = (
    ("partial_current_density", "mA cm-2"),
    ("faradaic_efficiency", "fraction_0_to_1"),
)
CO2RR_COMBINED_METRIC_KEY = "co2rr_combined"
CO2RR_ANALYTICS_WEIGHTS: dict[str, float] = {
    "partial_current_density": 0.5,
    "faradaic_efficiency": 0.5,
}


def _normalize_unit_text(unit_text: str) -> str:
    u = str(unit_text or "").strip()
    if not u:
        return ""
    u = u.translate(_DASH_TRANSLATION)
    u = u.replace("·", " ").replace("⋅", " ").replace("•", " ")
    u = u.replace("cm^-2", "cm-2").replace("cm^−2", "cm-2").replace("cm−2", "cm-2")
    u = u.replace("cm^2", "cm-2").replace("cm^+2", "cm-2")
    u = u.replace("cm²", "cm2").replace("cm2", "cm-2")
    u = u.replace("mg^-1", "mg-1").replace("mg^−1", "mg-1").replace("mg−1", "mg-1")
    u = u.replace("g^-1", "g-1").replace("g^−1", "g-1").replace("g−1", "g-1")
    u = u.replace("m^-1", "m-1").replace("m^−1", "m-1").replace("m−1", "m-1")
    u = u.replace("k^-1", "k-1").replace("k^−1", "k-1").replace("k−1", "k-1")
    u = u.replace("/cm2", " cm-2").replace("/cm²", " cm-2")
    u = u.replace("/", " ")
    u = " ".join(u.split())
    return u


def _parse_numeric_and_unit(value: Any, unit: Any | None) -> tuple[float | None, str]:
    """Parse a best-effort numeric value and its unit string."""
    if value is None:
        return None, ""
    s = str(value).strip()
    if not s:
        return None, ""

    # If value is numeric-only and unit column exists, stitch.
    if unit is not None and str(unit).strip():
        unit_s = str(unit).strip()
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", s):
            s = f"{s} {unit_s}"

    m = _NUM_PREFIX_RE.match(s)
    if not m:
        return None, ""
    try:
        num = float(m.group("num"))
    except Exception:
        return None, ""
    rest = _normalize_unit_text(s[m.end() :])
    return num, rest


def normalize_metric_value(metric_key: str, value: Any, unit: Any | None) -> float | None:
    """Normalize a (value, unit) pair into the canonical unit for the metric_key."""
    num, unit_text = _parse_numeric_and_unit(value, unit)
    if num is None or not math.isfinite(num):
        return None

    u = unit_text.lower()

    # Faradaic efficiency -> fraction
    if metric_key == "faradaic_efficiency":
        if "%" in unit_text:
            return num / 100.0
        if not unit_text and abs(num) > 1.0:
            return num / 100.0
        return num

    if metric_key == "photothermal_conversion_efficiency":
        if "%" in unit_text:
            return num
        if not unit_text and 0.0 <= num <= 1.0:
            return num * 100.0
        return num

    if metric_key == "conductivity":
        raw_low = f"{value or ''} {unit or ''}".lower()
        if "ms/cm" in raw_low or "ms cm-1" in raw_low or "ms cm^-1" in raw_low:
            return num * 0.1
        if "s/cm" in raw_low or "s cm-1" in raw_low or "s cm^-1" in raw_low:
            return num * 100.0
        if "ms/m" in raw_low or "ms m-1" in raw_low or "ms m^-1" in raw_low:
            return num * 1.0e-3
        if "s/m" in raw_low or "s m-1" in raw_low or "s m^-1" in raw_low:
            return num
        if re.search(r"\bms\s*cm-?1\b", u):
            return num * 0.1
        if re.search(r"\bs\s*cm-?1\b", u):
            return num * 100.0
        if re.search(r"\bms\s*m-?1\b", u):
            return num * 1.0e-3
        if re.search(r"\bs\s*m-?1\b", u):
            return num
        return None

    if metric_key == "thermal_conductivity":
        raw_low = f"{value or ''} {unit or ''}".lower()
        if "w/mk" in raw_low or "w/m k" in raw_low:
            return num
        if "w" in u and ("m-1" in u or "m k" in u) and ("k-1" in u or " k" in u):
            return num
        return None

    if metric_key == "saturation_magnetization":
        raw_low = f"{value or ''} {unit or ''}".lower()
        if "emu" in raw_low:
            return num
        if "a" in u and "m2" in u and "kg" in u:
            return num
        return None

    if metric_key == "neel_temperature":
        if re.search(r"\bk\b", u):
            return num
        return num if not unit_text else None

    # overpotential -> mV (accept V/mV)
    if "overpotential" in metric_key:
        if not unit_text:
            return num
        tok0 = u.split()[0] if u.split() else ""
        if tok0 == "mv":
            return num
        if tok0 == "v":
            return num * 1000.0
        return None

    # potential-like -> V (accept V/mV)
    if metric_key in {"potential_10mAcm-2", "half_wave_potential"}:
        if not unit_text:
            return num
        tok0 = u.split()[0] if u.split() else ""
        if tok0 == "v":
            return num
        if tok0 == "mv":
            return num / 1000.0
        return None

    # current density -> mA cm-2 (accept mA/A cm-2)
    if metric_key in {"exchange_current_density", "partial_current_density"}:
        if not unit_text:
            return num
        toks = u.split()
        if len(toks) >= 2 and toks[1] == "cm-2":
            if toks[0] == "ma":
                return num
            if toks[0] == "a":
                return num * 1000.0
        return None

    # mass_activity: allow mA->A conversion but keep the mass basis (mg vs g) strict.
    if metric_key == "mass_activity":
        if not unit_text:
            return num
        toks = u.split()
        if len(toks) >= 2:
            current, mass_basis = toks[0], toks[1]
            if mass_basis not in {"mg-1", "g-1"}:
                return None
            if current == "a":
                return num
            if current == "ma":
                return num / 1000.0
        return None

    # Unknown metric -> keep as-is
    return num


def unit_floor(unit: str | None) -> float:
    if not unit:
        return 0.0
    u = unit.strip()
    if u in {"V", "fraction_0_to_1"}:
        return 0.05
    return 0.0


def rel_error(pred: float, actual: float, *, unit: str | None = None) -> float | None:
    if not (math.isfinite(pred) and math.isfinite(actual)):
        return None
    denom = abs(actual) + unit_floor(unit)
    if denom <= 0:
        denom = 1.0
    return abs(pred - actual) / denom


def score_from_rel_error(err: float | None) -> float | None:
    if err is None or not math.isfinite(err):
        return None
    return float(math.exp(-float(err)))


@dataclass(frozen=True)
class PredictionErrorRecord:
    update_job_id: str
    update_finished_at_utc: str | None
    csv_row_index: int
    recommendation_job_id: str
    recommendation_finished_at_utc: str | None
    components: str
    reaction_type: str
    metric_key: str
    unit: str
    predicted_value: float | None
    actual_value: float | None
    abs_error: float | None
    rel_error: float
    score: float
    predicted_display: str | None = None
    actual_display: str | None = None
    abs_error_display: str | None = None
    component_rel_errors: dict[str, float] | None = None


def _norm_header(h: str) -> str:
    return " ".join(str(h or "").strip().split()).lower()


def extract_recommendation_job_id(row: dict[str, Any]) -> str | None:
    """Extract recommendation_job_id from a CSV row (best-effort; tolerant to CN headers)."""
    if not isinstance(row, dict):
        return None

    # Fast path: common exact headers (no normalization needed).
    direct = (
        row.get("recommendation_job_id")
        or row.get("recommendation job id")
        or row.get("reco_job_id")
        or row.get("reco job id")
        or row.get("recommendation_id")
        or row.get("recommendation id")
        or row.get("推荐任务id")
        or row.get("推荐任务ID")
        or row.get("推荐job_id")
        or row.get("推荐job id")
        or row.get("推荐job")
        or row.get("推荐id")
    )
    if direct is not None and str(direct).strip():
        return str(direct).strip()

    # Normalized fallback: look for a header that contains "recommendation" and "id".
    for k in row.keys():
        nk = _norm_header(k)
        if not nk:
            continue
        if ("recommendation" in nk or "reco" in nk or "推荐" in nk) and ("id" in nk or "任务" in nk):
            v = row.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
    return None


def collect_recommendation_job_ids_from_csv(path: Path, *, max_rows: int = 50_000) -> list[str]:
    """Collect unique recommendation_job_id values appearing in a CSV file."""
    ids: list[str] = []
    seen: set[str] = set()
    for idx, row in enumerate(iter_experimental_csv_rows(path), start=1):
        if idx > max_rows:
            break
        rid = extract_recommendation_job_id(row)
        if not rid or rid in seen:
            continue
        seen.add(rid)
        ids.append(rid)
    return ids


@dataclass(frozen=True)
class RecommendationContext:
    recommendation_job_id: str
    recommendation_finished_at_utc: str | None
    components: str
    recommendation_rank_result: dict[str, Any]


@dataclass(frozen=True)
class PredictionErrorDebug:
    csv_rows_total: int = 0
    rows_unknown_reaction_type: int = 0
    rows_actual_parse_failed: int = 0
    rows_missing_recommendation_job_id: int = 0
    rows_recommendation_job_id_not_found: int = 0
    rows_prediction_missing: int = 0
    rows_prediction_parse_failed: int = 0
    rows_scored: int = 0


def _row_get(row: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            continue
        return value
    return None


def _row_reaction_type(row: dict[str, Any]) -> str:
    rt_raw = _row_get(
        row,
        "task_type",
        "task type",
        "任务方向",
        "property_type",
        "property type",
        "性能方向",
        "性能类型",
        "材料性能",
        "reaction_type",
        "reaction type",
        "反应类型",
        "反应",
    )
    return canonical_reaction_type(str(rt_raw) if rt_raw is not None else "")


def _metric_specs_for_reaction_type(rt: str) -> list[tuple[str, str]]:
    if rt == "CO2RR":
        return list(CO2RR_ANALYTICS_METRICS)
    info = REACTION_METRIC.get(rt)
    if not info:
        return []
    return [(str(info["metric_key"]), str(info["unit"]))]


def _parse_fe_percent_from_text(text: Any) -> tuple[float | None, str]:
    raw = str(text or "").strip()
    if not raw:
        return None, ""
    for pattern in _FE_PERCENT_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        try:
            return float(match.group("value")), "%"
        except Exception:
            continue
    return None, ""


def _parse_current_density_from_text(text: Any) -> tuple[float | None, str]:
    raw = str(text or "").strip()
    if not raw:
        return None, ""
    for pattern in _PCD_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        try:
            value = float(match.group("value"))
        except Exception:
            continue
        unit = f"{match.group('unit')} cm-2"
        return value, unit
    return None, ""


def _extract_co2rr_prediction(rank_item: dict[str, Any]) -> dict[str, Any]:
    perf = rank_item.get("performance_evaluation") if isinstance(rank_item.get("performance_evaluation"), dict) else {}
    raw_metric_text = perf.get("raw_metric_text")
    final_performance = rank_item.get("final_performance")

    product = ""
    raw_products = rank_item.get("final_products")
    if isinstance(raw_products, str) and raw_products.strip():
        product = raw_products.strip()
    elif isinstance(final_performance, str) and final_performance.strip():
        match = _PRODUCT_LINE_RE.search(final_performance)
        if match:
            product = match.group("value").split("(")[0].strip()

    partial_value = perf.get("metric_value", None)
    partial_unit = perf.get("metric_unit", None)
    if partial_value is None:
        partial_value = rank_item.get("metric_value", None)
    if partial_unit is None:
        partial_unit = rank_item.get("metric_unit", None)
    if partial_value is None:
        for text in (raw_metric_text, final_performance):
            parsed_value, parsed_unit = _parse_current_density_from_text(text)
            if parsed_value is None:
                continue
            partial_value = parsed_value
            partial_unit = parsed_unit
            break

    fe_value = None
    fe_unit = ""
    for text in (raw_metric_text, final_performance):
        parsed_value, parsed_unit = _parse_fe_percent_from_text(text)
        if parsed_value is None:
            continue
        fe_value = parsed_value
        fe_unit = parsed_unit
        break

    return {
        "value": partial_value,
        "unit": partial_unit,
        "product": product,
        "partial_current_density": partial_value,
        "partial_current_density_unit": partial_unit,
        "faradaic_efficiency": fe_value,
        "faradaic_efficiency_unit": fe_unit,
    }


def _extract_actual_metric_value(row: dict[str, Any], *, rt: str, metric_key: str) -> float | None:
    if rt == "CO2RR":
        if metric_key == "partial_current_density":
            value_raw = _row_get(
                row,
                "partial_current_density",
                "partial current density",
                "partial current",
                "部分电流密度",
                "value",
                "metric_value",
                "指标值",
                "数值",
                "值",
            )
            unit_raw = _row_get(
                row,
                "partial_current_density_unit",
                "partial current density unit",
                "部分电流密度单位",
                "unit",
                "单位",
            )
            return normalize_metric_value(metric_key, value_raw, unit_raw)
        if metric_key == "faradaic_efficiency":
            value_raw = _row_get(
                row,
                "faradaic_efficiency",
                "faradaic efficiency",
                "FE",
                "fe",
                "法拉第效率",
                "产物法拉第效率",
            )
            unit_raw = _row_get(
                row,
                "faradaic_efficiency_unit",
                "faradaic efficiency unit",
                "FE_unit",
                "FE unit",
                "法拉第效率单位",
            )
            return normalize_metric_value(metric_key, value_raw, unit_raw)

    value_raw = _row_get(row, "value", "metric_value", "指标值", "数值", "值")
    unit_raw = _row_get(row, "unit", "单位")
    return normalize_metric_value(metric_key, value_raw, unit_raw)


def _extract_predicted_metric_value(pred_item: dict[str, Any], *, rt: str, metric_key: str) -> tuple[Any | None, Any | None]:
    if rt == "CO2RR":
        if metric_key == "partial_current_density":
            return pred_item.get("partial_current_density"), pred_item.get("partial_current_density_unit")
        if metric_key == "faradaic_efficiency":
            return pred_item.get("faradaic_efficiency"), pred_item.get("faradaic_efficiency_unit")
    return pred_item.get("value"), pred_item.get("unit")


def _build_prediction_error_record(
    *,
    update_job_id: str,
    update_finished_at_utc: str | None,
    csv_row_index: int,
    recommendation_job_id: str,
    recommendation_finished_at_utc: str | None,
    recommendation_components: str,
    reaction_type: str,
    metric_key: str,
    unit_canonical: str,
    predicted_value: float,
    actual_value: float,
) -> PredictionErrorRecord | None:
    err = float(predicted_value) - float(actual_value)
    rerr = rel_error(float(predicted_value), float(actual_value), unit=unit_canonical)
    if rerr is None:
        return None
    score = score_from_rel_error(rerr)
    if score is None:
        return None
    return PredictionErrorRecord(
        update_job_id=update_job_id,
        update_finished_at_utc=update_finished_at_utc,
        csv_row_index=csv_row_index,
        recommendation_job_id=recommendation_job_id,
        recommendation_finished_at_utc=recommendation_finished_at_utc,
        components=str(recommendation_components or ""),
        reaction_type=reaction_type,
        metric_key=metric_key,
        unit=unit_canonical,
        predicted_value=float(predicted_value),
        actual_value=float(actual_value),
        abs_error=abs(float(err)),
        rel_error=float(rerr),
        score=float(score),
    )


def _compute_row_prediction_error_records(
    *,
    update_job_id: str,
    update_finished_at_utc: str | None,
    csv_row_index: int,
    row: dict[str, Any],
    recommendation_job_id: str,
    recommendation_finished_at_utc: str | None,
    recommendation_components: str,
    reaction_type: str,
    pred_item: dict[str, Any],
) -> tuple[list[PredictionErrorRecord], str | None]:
    records: list[PredictionErrorRecord] = []
    actual_metric_found = False
    predicted_metric_found = False

    for metric_key, unit_canonical in _metric_specs_for_reaction_type(reaction_type):
        actual_value = _extract_actual_metric_value(row, rt=reaction_type, metric_key=metric_key)
        if actual_value is None:
            continue
        actual_metric_found = True

        pred_raw_value, pred_raw_unit = _extract_predicted_metric_value(pred_item, rt=reaction_type, metric_key=metric_key)
        if pred_raw_value is None:
            continue
        predicted_metric_found = True
        predicted_value = normalize_metric_value(metric_key, pred_raw_value, pred_raw_unit)
        if predicted_value is None:
            continue

        record = _build_prediction_error_record(
            update_job_id=update_job_id,
            update_finished_at_utc=update_finished_at_utc,
            csv_row_index=csv_row_index,
            recommendation_job_id=recommendation_job_id,
            recommendation_finished_at_utc=recommendation_finished_at_utc,
            recommendation_components=recommendation_components,
            reaction_type=reaction_type,
            metric_key=metric_key,
            unit_canonical=unit_canonical,
            predicted_value=float(predicted_value),
            actual_value=float(actual_value),
        )
        if record is None:
            continue
        records.append(record)

    if records:
        return records, None
    if not actual_metric_found:
        return [], "actual_parse_failed"
    if not predicted_metric_found:
        return [], "prediction_missing"
    return [], "prediction_parse_failed"


def load_rank_predictions(rank_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return reaction_type -> normalized predicted metrics from a MAD rank result."""
    out: dict[str, dict[str, Any]] = {}
    ranking = rank_result.get("ranking") or []
    if not isinstance(ranking, list):
        return out
    for it in ranking:
        if not isinstance(it, dict):
            continue
        rt = canonical_reaction_type(it.get("task_type") or it.get("reaction_type") or it.get("property_type"))
        if not rt:
            continue
        if rt == "CO2RR":
            out[rt] = _extract_co2rr_prediction(it)
            continue
        perf = it.get("performance_evaluation") if isinstance(it.get("performance_evaluation"), dict) else {}
        value = perf.get("metric_value", None)
        unit = perf.get("metric_unit", None)
        if value is None:
            value = it.get("metric_value", None)
        if unit is None:
            unit = it.get("metric_unit", None)
        if value is None:
            text = str(perf.get("raw_metric_text") or it.get("final_performance") or "").strip()
            if text:
                parsed_value, parsed_unit = _parse_numeric_and_unit(text, None)
                value = parsed_value
                unit = parsed_unit or unit
        if unit is None and rt in REACTION_METRIC:
            unit = REACTION_METRIC[rt].get("unit")
        out[rt] = {"value": value, "unit": unit}
    return out


def _format_display_number(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    v = float(value)
    a = abs(v)
    if v == 0:
        return "0"
    if a >= 1000:
        return f"{v:.0f}"
    if a >= 100:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    if a >= 10:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    if a >= 1:
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return f"{v:.3g}"


def _format_metric_value_display(metric_key: str, value: float | None, unit: str) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    if metric_key == "faradaic_efficiency":
        return f"{_format_display_number(float(value) * 100.0)}%"
    text = _format_display_number(value)
    return f"{text} {unit}".strip()


def _aggregate_co2rr_group_for_analytics(records: list[PredictionErrorRecord]) -> list[PredictionErrorRecord]:
    by_metric: dict[str, PredictionErrorRecord] = {}
    for record in records:
        if record.metric_key in by_metric:
            return records
        by_metric[record.metric_key] = record

    pcd = by_metric.get("partial_current_density")
    fe = by_metric.get("faradaic_efficiency")
    if not pcd or not fe:
        return records

    weighted_sum = 0.0
    weight_total = 0.0
    component_rel_errors: dict[str, float] = {}
    for metric_key, record in (("partial_current_density", pcd), ("faradaic_efficiency", fe)):
        weight = float(CO2RR_ANALYTICS_WEIGHTS.get(metric_key, 0.0))
        if weight <= 0:
            continue
        weighted_sum += float(record.rel_error) * weight
        weight_total += weight
        component_rel_errors[metric_key] = float(record.rel_error)

    if weight_total <= 0:
        return records

    rel = weighted_sum / weight_total
    score = score_from_rel_error(rel)
    if score is None:
        return records

    return [
        PredictionErrorRecord(
            update_job_id=pcd.update_job_id,
            update_finished_at_utc=pcd.update_finished_at_utc,
            csv_row_index=pcd.csv_row_index,
            recommendation_job_id=pcd.recommendation_job_id,
            recommendation_finished_at_utc=pcd.recommendation_finished_at_utc,
            components=pcd.components,
            reaction_type="CO2RR",
            metric_key=CO2RR_COMBINED_METRIC_KEY,
            unit="",
            predicted_value=None,
            actual_value=None,
            abs_error=None,
            rel_error=float(rel),
            score=float(score),
            predicted_display=(
                "j="
                + _format_metric_value_display("partial_current_density", pcd.predicted_value, pcd.unit)
                + "\nFE="
                + _format_metric_value_display("faradaic_efficiency", fe.predicted_value, fe.unit)
            ),
            actual_display=(
                "j="
                + _format_metric_value_display("partial_current_density", pcd.actual_value, pcd.unit)
                + "\nFE="
                + _format_metric_value_display("faradaic_efficiency", fe.actual_value, fe.unit)
            ),
            abs_error_display=(
                "|Δj|="
                + _format_metric_value_display("partial_current_density", pcd.abs_error, pcd.unit)
                + "\n|ΔFE|="
                + _format_metric_value_display("faradaic_efficiency", fe.abs_error, fe.unit)
            ),
            component_rel_errors=component_rel_errors,
        )
    ]


def aggregate_prediction_error_records_for_analytics(records: list[PredictionErrorRecord]) -> list[PredictionErrorRecord]:
    """Collapse analytics-only CO2RR FE + partial-current rows into one combined record.

    This helper is intentionally kept out of the raw record-generation path because
    feedback distillation still needs the atomic per-metric rows.
    """
    out: list[PredictionErrorRecord] = []
    grouped: dict[tuple[str, str, int, str], list[PredictionErrorRecord]] = {}
    emitted_groups: set[tuple[str, str, int, str]] = set()

    for record in records:
        if record.reaction_type != "CO2RR":
            continue
        key = (record.update_job_id, record.recommendation_job_id, record.csv_row_index, record.reaction_type)
        grouped.setdefault(key, []).append(record)

    for record in records:
        if record.reaction_type != "CO2RR":
            out.append(record)
            continue
        key = (record.update_job_id, record.recommendation_job_id, record.csv_row_index, record.reaction_type)
        if key in emitted_groups:
            continue
        emitted_groups.add(key)
        group = grouped.get(key) or [record]
        out.extend(_aggregate_co2rr_group_for_analytics(group))

    return out


def iter_experimental_csv_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not isinstance(row, dict):
                continue
            yield row


def compute_prediction_error_records(
    *,
    update_job_id: str,
    update_finished_at_utc: str | None,
    upload_csv_path: Path,
    recommendation_job_id: str,
    recommendation_finished_at_utc: str | None,
    recommendation_components: str,
    recommendation_rank_result: dict[str, Any],
) -> list[PredictionErrorRecord]:
    preds = load_rank_predictions(recommendation_rank_result)
    out: list[PredictionErrorRecord] = []

    for csv_row_index, row in enumerate(iter_experimental_csv_rows(upload_csv_path), start=1):
        rt = _row_reaction_type(row)
        if not rt or rt not in REACTION_METRIC:
            continue

        # Parse predicted value from MAD rank result.
        pred_item = preds.get(rt)
        if not pred_item:
            continue

        row_records, _ = _compute_row_prediction_error_records(
            update_job_id=update_job_id,
            update_finished_at_utc=update_finished_at_utc,
            csv_row_index=csv_row_index,
            row=row,
            recommendation_job_id=recommendation_job_id,
            recommendation_finished_at_utc=recommendation_finished_at_utc,
            recommendation_components=recommendation_components,
            reaction_type=rt,
            pred_item=pred_item,
        )
        out.extend(row_records)

    return out


def compute_prediction_error_records_multi(
    *,
    update_job_id: str,
    update_finished_at_utc: str | None,
    upload_csv_path: Path,
    recommendation_contexts: dict[str, RecommendationContext],
    default_recommendation_job_id: str | None = None,
) -> list[PredictionErrorRecord]:
    """Compute per-row errors when a single update CSV may reference multiple recommendation jobs.

    Row association:
    - Prefer per-row recommendation_job_id column.
    - Fallback to default_recommendation_job_id (typically from the update job payload).
    """
    preds_by_rec_id = {
        rid: load_rank_predictions(ctx.recommendation_rank_result) for rid, ctx in recommendation_contexts.items()
    }
    out: list[PredictionErrorRecord] = []

    for csv_row_index, row in enumerate(iter_experimental_csv_rows(upload_csv_path), start=1):
        rt = _row_reaction_type(row)
        if not rt or rt not in REACTION_METRIC:
            continue

        rec_id = extract_recommendation_job_id(row) or (str(default_recommendation_job_id).strip() if default_recommendation_job_id else None)
        if not rec_id:
            continue
        ctx = recommendation_contexts.get(rec_id)
        if not ctx:
            continue
        preds = preds_by_rec_id.get(rec_id) or {}

        # Parse predicted value from MAD rank result.
        pred_item = preds.get(rt)
        if not pred_item:
            continue

        row_records, _ = _compute_row_prediction_error_records(
            update_job_id=update_job_id,
            update_finished_at_utc=update_finished_at_utc,
            csv_row_index=csv_row_index,
            row=row,
            recommendation_job_id=ctx.recommendation_job_id,
            recommendation_finished_at_utc=ctx.recommendation_finished_at_utc,
            recommendation_components=str(ctx.components or ""),
            reaction_type=rt,
            pred_item=pred_item,
        )
        out.extend(row_records)

    return out


def compute_prediction_error_records_multi_debug(
    *,
    update_job_id: str,
    update_finished_at_utc: str | None,
    upload_csv_path: Path,
    recommendation_contexts: dict[str, RecommendationContext],
    default_recommendation_job_id: str | None = None,
) -> tuple[list[PredictionErrorRecord], PredictionErrorDebug]:
    """Like `compute_prediction_error_records_multi`, but also returns skip-reason counters for debugging."""
    stats = PredictionErrorDebug()
    preds_by_rec_id = {
        rid: load_rank_predictions(ctx.recommendation_rank_result) for rid, ctx in recommendation_contexts.items()
    }
    out: list[PredictionErrorRecord] = []

    csv_rows_total = 0
    rows_unknown_reaction_type = 0
    rows_actual_parse_failed = 0
    rows_missing_recommendation_job_id = 0
    rows_recommendation_job_id_not_found = 0
    rows_prediction_missing = 0
    rows_prediction_parse_failed = 0

    for csv_row_index, row in enumerate(iter_experimental_csv_rows(upload_csv_path), start=1):
        csv_rows_total += 1

        rt = _row_reaction_type(row)
        if not rt or rt not in REACTION_METRIC:
            rows_unknown_reaction_type += 1
            continue

        rec_id = extract_recommendation_job_id(row) or (str(default_recommendation_job_id).strip() if default_recommendation_job_id else None)
        if not rec_id:
            rows_missing_recommendation_job_id += 1
            continue
        ctx = recommendation_contexts.get(rec_id)
        if not ctx:
            rows_recommendation_job_id_not_found += 1
            continue

        preds = preds_by_rec_id.get(rec_id) or {}
        pred_item = preds.get(rt)
        if not pred_item:
            rows_prediction_missing += 1
            continue

        row_records, failure_reason = _compute_row_prediction_error_records(
            update_job_id=update_job_id,
            update_finished_at_utc=update_finished_at_utc,
            csv_row_index=csv_row_index,
            row=row,
            recommendation_job_id=ctx.recommendation_job_id,
            recommendation_finished_at_utc=ctx.recommendation_finished_at_utc,
            recommendation_components=str(ctx.components or ""),
            reaction_type=rt,
            pred_item=pred_item,
        )
        if row_records:
            out.extend(row_records)
            continue

        if failure_reason == "actual_parse_failed":
            rows_actual_parse_failed += 1
        elif failure_reason == "prediction_missing":
            rows_prediction_missing += 1
        else:
            rows_prediction_parse_failed += 1

    stats = PredictionErrorDebug(
        csv_rows_total=csv_rows_total,
        rows_unknown_reaction_type=rows_unknown_reaction_type,
        rows_actual_parse_failed=rows_actual_parse_failed,
        rows_missing_recommendation_job_id=rows_missing_recommendation_job_id,
        rows_recommendation_job_id_not_found=rows_recommendation_job_id_not_found,
        rows_prediction_missing=rows_prediction_missing,
        rows_prediction_parse_failed=rows_prediction_parse_failed,
        rows_scored=len(out),
    )
    return out, stats


def mean(xs: list[float]) -> float | None:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    if not vals:
        return None
    return sum(vals) / len(vals)
