from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .constants import NON_METRIC_KEYS, REACTION_ALLOWED_METRICS, REACTION_TYPES
from .metals import normalize_metals
from .metrics import normalize_metric_key, normalize_metric_value
from utu.data_processing.material_feedback import MATERIAL_INPUT_FIELDS, material_input_from_mapping, parse_list


_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_REACTION_CANONICAL_BY_UPPER = {rt.upper(): rt for rt in REACTION_TYPES}


def _decimal_to_str(value: Decimal) -> str:
    """Convert Decimal to a non-scientific string, stripping trailing zeros."""
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s


# CO2RR product label normalization to keep the classification task stable.
# We keep this mapping intentionally small and derived from the observed co2rr_final.jsonl values.
_CO2RR_PRODUCT_ALIASES: dict[str, str] = {
    # Core canonical labels (case normalization)
    "co": "CO",
    "carbon monoxide": "CO",
    "hcooh": "HCOOH",
    # Common text/chemical variants for formate.
    "hcoo-": "HCOOH",
    "hcoo−": "HCOOH",  # unicode minus
    "hcoo": "HCOOH",
    "formic acid": "HCOOH",
    "formate": "HCOOH",
    "c2h4": "C2H4",
    "ethylene": "C2H4",
    "ethene": "C2H4",
    "c2h5oh": "C2H5OH",
    "ethanol": "C2H5OH",
    "ch4": "CH4",
    "methane": "CH4",
    "ch3cooh": "CH3COOH",
    "acetic acid": "CH3COOH",
    "acetate": "CH3COOH",
    # Aggregate buckets sometimes reported in papers
    "c2+": "C2+",
    "c2 products": "C2+",
    "c2": "C2+",
    "multi-carbon products": "C2+",
    "multi-carbon": "C2+",
    "c3+": "C3+",
    "n-propanol": "C3+",
}

# For this project stage we only care about these "main products" for CO2RR.
# Records whose highest-FE product falls outside this set are dropped.
_CO2RR_ALLOWED_TRUTH_PRODUCTS: set[str] = {
    "CO",
    "HCOOH",
    "CH4",
    "C2H5OH",
    "C2H4",
    "CH3COOH",
}


def _normalize_co2rr_product_label(product: str) -> str:
    s = " ".join((product or "").strip().split())
    if not s:
        return ""
    key = s.lower()
    return _CO2RR_PRODUCT_ALIASES.get(key, s)


def _parse_percent_to_fraction(value: Any) -> Decimal | None:
    """Parse a percent string like '94.2%' into a fraction Decimal in [0, 1]."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    s = value.strip().replace("％", "%")
    if not s:
        return None
    # Allow approximate/inequality prefixes.
    while s and s[0] in {"~", "≈", "≃", "∼", "<", ">", "≤", "≥", "="}:
        s = s[1:].lstrip()
    # Remove thousands separators inside the number (e.g., "1,000%").
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    m = _NUM_PREFIX_RE.match(s)
    if not m:
        return None
    try:
        pct = Decimal(m.group("num"))
    except InvalidOperation:
        return None
    return pct / Decimal("100")


def _parse_current_density_to_ma_cm2(value: Any) -> Decimal | None:
    """Parse current density strings into canonical mA cm^-2 (Decimal).

    Supports common variants seen in `data/co2rr_final.jsonl`, e.g.:
    - '200 mA·cm−2', '10 mA cm−2', '~24 mA/cm2', '0.02 A cm-2'
    - unicode minus variants and separators
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    s = value.strip()
    if not s:
        return None

    # Normalize unicode dashes and common separators.
    s = s.replace("−", "-").replace("–", "-").replace("‑", "-").replace("—", "-")
    s = s.replace("·", " ").replace("⋅", " ").replace("•", " ")

    # Strip leading approximate/inequality symbols until we hit a numeric sign/digit/dot.
    s = s.lstrip()
    while s and s[0] in {"~", "≈", "≃", "∼", "<", ">", "≤", "≥", "="}:
        s = s[1:].lstrip()

    # Remove thousands separators inside the number.
    s = re.sub(r"(?<=\d),(?=\d)", "", s)

    m = _NUM_PREFIX_RE.match(s)
    if not m:
        return None
    try:
        num = Decimal(m.group("num"))
    except InvalidOperation:
        return None

    rest = s[m.end() :].strip()
    if not rest:
        return None

    # Normalize unit spelling.
    u = rest.lower()
    u = u.replace("cm^-2", "cm-2").replace("cm^−2", "cm-2")
    u = u.replace("cm−2", "cm-2").replace("cm–2", "cm-2").replace("cm -2", "cm-2")
    u = u.replace("cm–2", "cm-2").replace("cm– 2", "cm-2")
    u = u.replace("cm - 2", "cm-2").replace("cm- 2", "cm-2")
    # Handle slash forms like "mA/cm2" or "mA/cm²".
    u = u.replace("cm²", "cm2")
    u = re.sub(r"/\s*cm\s*2\b", " cm-2", u)
    u = u.replace("/cm2", " cm-2")
    u = u.replace("/cm²", " cm-2")
    # Handle concatenated forms like "mAcm-2" / "Acm-2" by inserting a space.
    u = re.sub(r"^(ma|a)(?=cm)", r"\1 ", u)
    # Collapse whitespace.
    u = " ".join(u.split())
    # Some forms end up as "ma cm 2" (rare); best-effort.
    u = u.replace("cm2", "cm-2")

    if "cm-2" not in u:
        return None

    # Detect the current unit (mA or A). We only keep absolute values convertible to mA cm^-2.
    if u.startswith("ma"):
        ma = num
    elif u.startswith("a"):
        ma = num * Decimal("1000")
    else:
        return None

    return ma


def _process_co2rr_final_record(
    raw: dict[str, Any],
    *,
    source_file: str | None = None,
    stats: ProcessingStats | None = None,
) -> dict[str, Any] | None:
    """Process one CO2RR record from `co2rr_final.jsonl` into a unified label + metric record."""
    reaction_type = "CO2RR"
    metals = normalize_metals(raw.get("metals") or [])
    material_input_raw = raw.get("material_input")
    material_input = material_input_from_mapping(material_input_raw if isinstance(material_input_raw, dict) else raw)
    material_name = str(material_input.get("material_name") or raw.get("material_name") or "").strip()
    if not metals and not material_name:
        if stats:
            stats.record_dropped("missing_material_identity")
        return None

    record_id = raw.get("id")

    products = raw.get("product")
    fes = raw.get("faradaic_efficiency")
    cds = raw.get("current_density")
    if not (isinstance(products, list) and isinstance(fes, list) and isinstance(cds, list)):
        if stats:
            stats.record_dropped("co2rr_final_bad_schema")
        return None
    if len(products) != len(fes) or not products:
        if stats:
            stats.record_dropped("co2rr_final_mismatched_lists")
        return None

    # Pick the highest-FE product as the truth product.
    truth_prod = ""
    truth_fe = None
    truth_fe_raw = None
    truth_prod_raw = None
    for pr_raw, fe_raw in zip(products, fes):
        pr = _normalize_co2rr_product_label(str(pr_raw) if pr_raw is not None else "")
        fe = _parse_percent_to_fraction(fe_raw)
        if fe is None:
            if stats:
                stats.metric_dropped("unparseable_fe_percent")
            continue
        if stats:
            stats.conversions_percent_to_fraction += 1

        if (truth_fe is None) or (fe > truth_fe):
            truth_prod = pr
            truth_fe = fe
            truth_fe_raw = fe_raw
            truth_prod_raw = pr_raw

    if truth_fe is None or not truth_prod:
        if stats:
            stats.record_dropped("co2rr_missing_truth_product")
        return None

    # Filter: keep only records whose top-FE product is within our focused label set.
    if truth_prod not in _CO2RR_ALLOWED_TRUTH_PRODUCTS:
        if stats:
            stats.record_dropped("co2rr_unwanted_truth_product")
        return None

    # Gather current density evidence.
    partial_vals: list[Decimal] = []
    total_vals: list[Decimal] = []
    total_vals_same_prod: list[Decimal] = []
    partial_vals_same_prod: list[Decimal] = []

    for cd in cds:
        if not isinstance(cd, dict):
            if stats:
                stats.metric_dropped("co2rr_bad_current_density_item")
            continue
        cd_type = str(cd.get("type") or "").strip().lower()
        cd_prod = _normalize_co2rr_product_label(str(cd.get("product") or ""))
        cd_val_raw = cd.get("value")
        cd_val = _parse_current_density_to_ma_cm2(cd_val_raw)
        if cd_val is None:
            if stats:
                stats.metric_dropped("unparseable_current_density")
            continue
        # Track A->mA conversions opportunistically.
        if isinstance(cd_val_raw, str) and "a" in cd_val_raw.lower() and "ma" not in cd_val_raw.lower():
            if stats:
                stats.conversions_a_to_ma += 1

        if cd_type == "partial":
            partial_vals.append(cd_val)
            if cd_prod == truth_prod:
                partial_vals_same_prod.append(cd_val)
        elif cd_type == "total":
            total_vals.append(cd_val)
            if cd_prod == truth_prod:
                total_vals_same_prod.append(cd_val)
        else:
            if stats:
                stats.metric_dropped("unknown_current_density_type")

    # Derive truth partial current density for the truth product.
    partial_truth: Decimal | None = None
    partial_source = None
    total_used: Decimal | None = None

    if partial_vals_same_prod:
        # Prefer explicitly reported partial current density when available.
        partial_truth = max(partial_vals_same_prod, key=lambda x: abs(x))
        partial_source = "reported_partial"
    else:
        # Compute from total current density and FE if partial is not reported.
        if total_vals_same_prod:
            total_used = max(total_vals_same_prod, key=lambda x: abs(x))
        elif total_vals:
            total_used = max(total_vals, key=lambda x: abs(x))
        if total_used is not None:
            partial_truth = total_used * truth_fe
            partial_source = "computed_total_times_fe"

    if partial_truth is None:
        if stats:
            stats.record_dropped("co2rr_missing_partial_current_density")
        return None

    processed: dict[str, Any] = {
        "id": record_id,
        "reaction_type": reaction_type,
        # For CO2RR we store the "truth" product (highest FE) as a label and as
        # input context for the partial-current-density task.
        "product": truth_prod,
    }
    if metals:
        processed["metals"] = metals
    if material_name:
        material_input["material_name"] = material_name
        processed["material_name"] = material_name
        for key in MATERIAL_INPUT_FIELDS:
            value = material_input.get(key)
            if value not in (None, "", [], {}):
                processed[key] = value
        explicit_elements = parse_list(material_input.get("elements"))
        if explicit_elements:
            processed["elements"] = explicit_elements
    if source_file:
        processed["source_file"] = source_file

    # CO2RR carries two supervision signals:
    # - product task: top-FE product + its FE
    # - regression task: partial current density for that product
    metrics_gt = {
        "faradaic_efficiency": _decimal_to_str(truth_fe),
        "partial_current_density": f"{_decimal_to_str(partial_truth)} mA cm-2",
    }
    processed["metrics_gt"] = metrics_gt
    processed["units"] = {"faradaic_efficiency": "fraction_0_to_1", "partial_current_density": "mA cm-2"}
    processed["metrics_raw"] = {
        # Keep raw extraction fields for debugging / audit.
        "product_candidates": products,
        "faradaic_efficiency_candidates": fes,
        "current_density": cds,
        "truth_product_raw": truth_prod_raw,
        "truth_faradaic_efficiency_raw": truth_fe_raw,
        "truth_faradaic_efficiency_fraction": _decimal_to_str(truth_fe),
        "partial_current_density_source": partial_source,
        "total_current_density_used_mA_cm-2": _decimal_to_str(total_used) if total_used is not None else None,
    }
    # Remove nulls to keep processed records compact.
    processed["metrics_raw"] = {k: v for k, v in processed["metrics_raw"].items() if v is not None}
    return processed


@dataclass
class ProcessingStats:
    total_records: int = 0
    kept_records: int = 0
    dropped_records: int = 0

    dropped_records_by_reason: dict[str, int] = field(default_factory=dict)
    dropped_metrics_by_reason: dict[str, int] = field(default_factory=dict)

    conversions_v_to_mv: int = 0
    conversions_mv_to_v: int = 0
    conversions_a_to_ma: int = 0
    conversions_ma_to_a: int = 0
    conversions_percent_to_fraction: int = 0

    def _inc(self, d: dict[str, int], key: str, n: int = 1) -> None:
        d[key] = d.get(key, 0) + n

    def record_dropped(self, reason: str) -> None:
        self.dropped_records += 1
        self._inc(self.dropped_records_by_reason, reason)

    def metric_dropped(self, reason: str) -> None:
        self._inc(self.dropped_metrics_by_reason, reason)


def process_raw_record(raw: dict[str, Any], *, source_file: str | None = None, stats: ProcessingStats | None = None) -> dict[str, Any] | None:
    """Convert one raw extracted record into a processed record.

    Returns None if the record has no evaluable metrics after cleaning.
    """
    reaction_type = (raw.get("reaction_type") or "").strip()
    # Be tolerant to case/format drift, e.g., "HZOR" -> "HzOR", "CO2-RR" -> "CO2RR".
    if reaction_type and reaction_type not in REACTION_TYPES:
        rt_key = re.sub(r"[^A-Za-z0-9]+", "", reaction_type).upper()
        reaction_type = _REACTION_CANONICAL_BY_UPPER.get(rt_key, reaction_type)
    if reaction_type and reaction_type not in REACTION_TYPES:
        # Unknown reaction_type should not silently propagate.
        if stats:
            stats.record_dropped("unknown_reaction_type")
        return None

    # Special-case CO2RR final extraction format (product list + FE list + current_density list).
    # This enables the two-task setup:
    # - Task 1: classify the top-FE product
    # - Task 2: regress the partial current density for that product
    if reaction_type == "CO2RR" and isinstance(raw.get("product"), list) and isinstance(raw.get("faradaic_efficiency"), list) and isinstance(raw.get("current_density"), list):
        return _process_co2rr_final_record(raw, source_file=source_file, stats=stats)

    metals = normalize_metals(raw.get("metals") or [])
    material_input_raw = raw.get("material_input")
    material_input = material_input_from_mapping(material_input_raw if isinstance(material_input_raw, dict) else raw)
    material_name = str(material_input.get("material_name") or raw.get("material_name") or "").strip()
    if not metals and not material_name:
        if stats:
            stats.record_dropped("missing_material_identity")
        return None

    record_id = raw.get("id")

    processed: dict[str, Any] = {
        "id": record_id,
        "reaction_type": reaction_type,
    }
    if metals:
        processed["metals"] = metals
    if material_name:
        material_input["material_name"] = material_name
        processed["material_name"] = material_name
        for key in MATERIAL_INPUT_FIELDS:
            value = material_input.get(key)
            if value not in (None, "", [], {}):
                processed[key] = value
        explicit_elements = parse_list(material_input.get("elements"))
        if explicit_elements:
            processed["elements"] = explicit_elements
    raw_description = raw.get("material_description")
    if raw_description is not None and str(raw_description).strip():
        processed["material_description"] = str(raw_description).strip()
    raw_task_type = raw.get("task_type")
    if raw_task_type is not None and str(raw_task_type).strip():
        processed["task_type"] = str(raw_task_type).strip()
    if source_file:
        processed["source_file"] = source_file

    # Optional bibliographic metadata (manual curation may add it to raw JSONL records).
    # We store DOI under a consistent key `doc_id` so downstream masking can use it.
    raw_doc_id = raw.get("doc_id") or raw.get("doi")
    if raw_doc_id is not None:
        doc_id = str(raw_doc_id).strip()
        if doc_id:
            processed["doc_id"] = doc_id
    raw_title = raw.get("title")
    if raw_title is not None:
        title = str(raw_title).strip()
        if title:
            processed["title"] = title

    # Keep CO2RR product as input context (not part of metrics).
    #
    # Important: our dataset builder always splits CO2RR into two tasks:
    #   1) classify the main product (top-FE product) and optionally regress FE
    #   2) regress the partial current density for that product
    # So CO2RR records MUST carry a single truth product label.
    if reaction_type == "CO2RR":
        raw_prod = raw.get("product")
        if not isinstance(raw_prod, str) or not raw_prod.strip():
            if stats:
                stats.record_dropped("co2rr_missing_truth_product")
            return None
        prod = _normalize_co2rr_product_label(raw_prod)
        if prod not in _CO2RR_ALLOWED_TRUTH_PRODUCTS:
            if stats:
                stats.record_dropped("co2rr_unwanted_truth_product")
            return None
        processed["product"] = prod

    metrics_gt: dict[str, str] = {}
    metrics_raw: dict[str, Any] = {}
    units: dict[str, str] = {}

    allowed_metrics = REACTION_ALLOWED_METRICS.get(reaction_type) if reaction_type else None

    for key, value in raw.items():
        if key in NON_METRIC_KEYS:
            continue
        if value is None:
            if stats:
                stats.metric_dropped("null_value")
            continue

        key_norm = normalize_metric_key(key, reaction_type)
        if not key_norm:
            if stats:
                stats.metric_dropped("empty_key")
            continue

        if allowed_metrics is not None and key_norm not in allowed_metrics:
            if stats:
                stats.metric_dropped("metric_not_in_scope")
            continue

        normalized = normalize_metric_value(value, metric_key=key_norm, reaction_type=reaction_type)
        if normalized is None:
            if stats:
                stats.metric_dropped("unparseable_value")
            continue

        # If UOR contains both "potential" and "overpotential", keep the value coming
        # from "potential" (it is usually the more standard reporting form) and do
        # not let a later "overpotential" overwrite it.
        if (
            reaction_type == "UOR"
            and key_norm == "potential_10mAcm-2"
            and key_norm in metrics_gt
            and str(key).strip() == "overpotential"
        ):
            if stats:
                stats.metric_dropped("duplicate_metric_prefer_potential")
            continue

        # Track conversions for reporting.
        if isinstance(value, str):
            if "%" in value:
                if stats:
                    stats.conversions_percent_to_fraction += 1
            # Best-effort unit conversion counters; conversion itself is key-aware in normalize_metric_value.
            low = value.lower()
            if " v" in low and "overpotential" in key_norm.lower():
                if stats:
                    stats.conversions_v_to_mv += 1
            if "mv" in low and ("potential" in key_norm.lower()) and ("overpotential" not in key_norm.lower()):
                if stats:
                    stats.conversions_mv_to_v += 1
            if " a " in f" {low} " and key_norm == "exchange_current_density":
                if stats:
                    stats.conversions_a_to_ma += 1
            if " ma " in f" {low} " and key_norm == "mass_activity":
                if stats:
                    stats.conversions_ma_to_a += 1

        metrics_gt[key_norm] = normalized.value_str
        metrics_raw[key_norm] = value
        if normalized.unit_hint is not None:
            units[key_norm] = normalized.unit_hint

    if not metrics_gt:
        if stats:
            stats.record_dropped("no_metrics_after_cleaning")
        return None

    processed["metrics_gt"] = metrics_gt
    processed["metrics_raw"] = metrics_raw
    processed["units"] = units
    return processed


def process_jsonl_file(input_path: Path, output_path: Path) -> ProcessingStats:
    """Process one JSONL file into cleaned/normalized JSONL records."""
    stats = ProcessingStats()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            stats.total_records += 1
            raw = json.loads(line)
            processed = process_raw_record(raw, source_file=input_path.name, stats=stats)
            if processed is None:
                continue
            fout.write(json.dumps(processed, ensure_ascii=False) + "\n")
            stats.kept_records += 1

    stats.dropped_records = stats.total_records - stats.kept_records
    return stats


def process_directory(input_dir: Path, output_dir: Path) -> dict[str, ProcessingStats]:
    """Process all *.jsonl files directly under input_dir into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, ProcessingStats] = {}
    inputs = sorted(input_dir.glob("*.jsonl"))
    # If a "final" CO2RR extraction file is present, prefer it over the older co2rr.jsonl.
    names = {p.name for p in inputs}
    if "co2rr_final.jsonl" in names and "co2rr.jsonl" in names:
        inputs = [p for p in inputs if p.name != "co2rr.jsonl"]

    for input_path in inputs:
        out_path = output_dir / input_path.name
        results[input_path.name] = process_jsonl_file(input_path=input_path, output_path=out_path)
    return results
