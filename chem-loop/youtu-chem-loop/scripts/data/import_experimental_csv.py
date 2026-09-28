#!/usr/bin/env python3
"""Convert a lab experimental-record CSV into processed performance JSONL.

This supports the closed-loop update pipeline:
  experimental_records.csv
    -> (this script) processed records JSONL
    -> scripts/data/build_chem_performance_dataset.py
    -> scripts/data/upload_dataset.py
    -> scripts/run_training_free_GRPO.py (update experience library)

CSV assumptions (flexible):
- Material-property rows should include property_type (or reaction_type as a
  compatibility alias), metals, value, unit, and optionally condition/notes.
- Legacy electrocatalysis rows are still accepted for backward compatibility.
- metals cell may look like: "Co(57%),Ni(23%)" (we extract symbols; keep composition in meta)

Output:
- One JSONL file with processed-record schema compatible with:
  scripts/data/build_chem_performance_dataset.py --input_dir <output_dir>
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.data.build_material_property_dataset import PROPERTY_METRICS, normalize_value
from utu.data_processing.chem_performance.experimental_csv import (
    check_eta10_condition,
    infer_metric_key,
    normalize_reaction_type,
    parse_metals_text,
    stitch_value_and_unit,
)
from utu.data_processing.chem_performance.processor import ProcessingStats, process_raw_record
from utu.data_processing.material_feedback import (
    MATERIAL_INPUT_FIELDS,
    MATERIAL_TASK_TYPES,
    canonical_task_type,
    material_input_from_mapping,
    parse_list,
    parse_material_input_json,
)


def _repo_root() -> Path:
    # scripts/data/<this_file>.py -> scripts -> <repo_root>
    return Path(__file__).resolve().parents[2]


def _norm_header(h: str) -> str:
    return " ".join((h or "").strip().split()).lower()


def _find_col(fieldnames: list[str], candidates: list[str], *, fuzzy: bool = True) -> str | None:
    """Return the original header name for the first matching candidate (case/space-insensitive)."""
    if not fieldnames:
        return None
    by_norm = {_norm_header(h): h for h in fieldnames if h is not None}

    # Exact match on normalized headers first.
    for c in candidates:
        c_norm = _norm_header(c)
        if c_norm in by_norm:
            return by_norm[c_norm]

    if not fuzzy:
        return None

    # Fuzzy fallback: candidate is a substring of the header.
    norms = list(by_norm.keys())
    for c in candidates:
        c_norm = _norm_header(c)
        if not c_norm:
            continue
        for h_norm in norms:
            if c_norm in h_norm:
                return by_norm[h_norm]
    return None


def _metric_requires_eta10(metric_key: str) -> bool:
    return metric_key in {"overpotential_10mAcm-2", "potential_10mAcm-2"}


def _material_input_for_row(
    row: dict[str, Any],
    *,
    columns: dict[str, str | None],
    material_input_json_column: str | None,
) -> tuple[dict[str, Any], str | None]:
    """Collect actual material context from a CSV row without formula inference."""
    material_input = parse_material_input_json(row.get(material_input_json_column) if material_input_json_column else None)
    for key, column in columns.items():
        if not column:
            continue
        value = row.get(column)
        if value is None or not str(value).strip():
            continue
        material_input[key] = value

    material_input = material_input_from_mapping(material_input)
    description_column = columns.get("material_description")
    description = None
    if description_column:
        raw_description = row.get(description_column)
        if raw_description is not None and str(raw_description).strip():
            description = str(raw_description).strip()
    if "elements" in material_input:
        elements = parse_list(material_input["elements"])
        if elements:
            material_input["elements"] = elements
        else:
            material_input.pop("elements", None)
    return material_input, description


def _build_material_property_record(
    *,
    rid: str,
    prop: str,
    metals: list[str],
    metals_raw: Any,
    composition_pct: dict[str, float],
    value_text: Any,
    unit_text: Any,
    condition_text: Any,
    notes_text: Any,
    source_file: str,
    row: dict[str, Any],
    col_reco_job_id: str | None,
    col_metals_scope: str | None,
    col_metals_other: str | None,
    col_doi: str | None,
    col_title: str | None,
    material_input: dict[str, Any],
    material_description: str | None,
) -> dict[str, Any] | None:
    spec = PROPERTY_METRICS[prop]
    metric_key = spec["metric_key"]
    stitched = stitch_value_and_unit(value_text, unit_text)
    if stitched is None:
        return None
    normalized = normalize_value(prop, stitched)
    if normalized is None:
        return None
    value, unit = normalized
    answer_text = f"{value:g} {unit}"

    processed: dict[str, Any] = {
        "id": rid,
        "reaction_type": prop,
        "property_type": prop,
        "task_type": prop,
        "application_name": spec["display"],
        "metrics_gt": {metric_key: answer_text},
        "metrics_raw": {metric_key: stitched},
        "units": {metric_key: unit},
        "source_schema": prop,
        "source_type": "experimental_csv",
        "source_file": source_file,
        "metals_raw": str(metals_raw).strip() if metals_raw is not None else None,
    }
    if metals:
        processed["metals"] = metals
    material_name = str(material_input.get("material_name") or "").strip()
    if material_name:
        processed["material_name"] = material_name
        for key in MATERIAL_INPUT_FIELDS:
            value = material_input.get(key)
            if value not in (None, "", [], {}):
                processed[key] = value
    if material_description:
        processed["material_description"] = material_description
    if composition_pct:
        processed["composition_pct"] = composition_pct
    if condition_text is not None and str(condition_text).strip():
        processed["condition_raw"] = str(condition_text).strip()
    if notes_text is not None and str(notes_text).strip():
        processed["notes"] = str(notes_text).strip()
    if col_reco_job_id:
        reco_id = str(row.get(col_reco_job_id) or "").strip()
        if reco_id:
            processed["recommendation_job_id"] = reco_id
    if col_metals_scope:
        scope = str(row.get(col_metals_scope) or "").strip()
        if scope:
            processed["metals_scope"] = scope
    if col_metals_other:
        other = str(row.get(col_metals_other) or "").strip()
        if other:
            processed["metals_other"] = other
    if col_doi:
        doi = str(row.get(col_doi) or "").strip()
        if doi:
            processed["doi"] = doi
            processed["doc_id"] = doi
    if col_title:
        title = str(row.get(col_title) or "").strip()
        if title:
            processed["title"] = title

    return {k: v for k, v in processed.items() if v is not None}


def main() -> None:
    ap = argparse.ArgumentParser(description="Import experimental chem-performance CSV into processed JSONL.")
    ap.add_argument(
        "--csv_path",
        type=str,
        required=True,
        help="Path to experimental record CSV.",
    )
    ap.add_argument(
        "--output_dir",
        type=str,
        default=str(_repo_root() / "data" / "processed" / "chem_performance_experimental"),
        help="Directory to write processed JSONL records.",
    )
    ap.add_argument(
        "--output_name",
        type=str,
        default=None,
        help="Optional output filename (default: <csv_stem>.jsonl).",
    )
    ap.add_argument(
        "--encoding",
        type=str,
        default="utf-8-sig",
        help="CSV encoding (default: utf-8-sig; use gbk if exported from some CN Excel setups).",
    )
    ap.add_argument(
        "--delimiter",
        type=str,
        default=",",
        help="CSV delimiter (default: ',').",
    )
    ap.add_argument(
        "--drop_explicit_non_eta10",
        action="store_true",
        help=(
            "If set, rows whose condition column explicitly indicates a non-10 mA cm^-2 current density "
            "are dropped for eta10 metrics (overpotential_10mAcm-2 / potential_10mAcm-2)."
        ),
    )
    ap.add_argument(
        "--require_eta10_condition",
        action="store_true",
        help=(
            "If set, rows with eta10 metrics must have a condition column parseable as 10 mA cm^-2 "
            "(unknown/unparseable condition -> drop)."
        ),
    )
    ap.add_argument(
        "--dry_run",
        action="store_true",
        help="If set, do not write files; only print a summary.",
    )
    args = ap.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_name = args.output_name or f"{csv_path.stem}.jsonl"
    out_path = output_dir / out_name

    # Column candidates (allow CN headers).
    property_candidates = ["property_type", "property type", "task_type", "task type", "性能方向", "性能类型", "材料性能", "应用方向"]
    reaction_candidates = ["reaction_type", "reaction type", "task_type", "task type", "反应类型", "反应"]
    metals_candidates = ["metals", "metal", "金属元素", "金属", "催化剂", "组成"]
    material_name_candidates = ["material_name", "material name", "材料名称", "样品名称", "催化剂名称"]
    material_input_json_candidates = ["material_input_json", "material input json", "material_input", "material input", "材料输入json"]
    material_description_candidates = ["material_description", "material description", "材料描述", "材料提示词", "提示词"]
    material_field_candidates: dict[str, list[str]] = {
        "material_serial_no": ["material_serial_no", "material serial no", "material_no", "材料序号", "样品序号"],
        "material_name": material_name_candidates,
        "major_category": ["major_category", "major category", "材料类别", "材料大类"],
        "components": ["components", "material components", "material_components", "材料组分", "组分"],
        "structure_relationships": ["structure_relationships", "structure relationships", "结构关系"],
        "precursors": ["precursors", "precursor", "前驱体"],
        "feed_ratio": ["feed_ratio", "feed ratio", "投料比", "前驱体投料比"],
        "preparation_method": ["preparation_method", "preparation method", "制备方法", "制备方式"],
        "elements": ["elements", "element", "元素", "元素列表"],
        "element_content": ["element_content", "element content", "元素含量", "元素比例"],
        "conditions": ["material_conditions", "material conditions", "材料条件"],
        "custom_prompt": ["custom_prompt", "custom prompt", "自定义提示词", "补充材料信息"],
        "material_description": material_description_candidates,
    }
    product_candidates = ["product", "products", "产物", "主要产物", "主产物"]
    co2rr_fe_value_candidates = [
        "faradaic_efficiency",
        "faradaic efficiency",
        "fe",
        "co2rr_faradaic_efficiency",
        "法拉第效率",
        "产物法拉第效率",
    ]
    co2rr_fe_unit_candidates = ["faradaic_efficiency_unit", "fe_unit", "法拉第效率单位", "FE单位"]
    co2rr_partial_value_candidates = [
        "partial_current_density",
        "partial current density",
        "j_partial",
        "j",
        "co2rr_partial_current_density",
        "部分电流密度",
    ]
    co2rr_partial_unit_candidates = [
        "partial_current_density_unit",
        "partial current density unit",
        "j_unit",
        "部分电流密度单位",
    ]
    metric_label_candidates = ["metric", "metric_name", "指标", "指标名称", "性能指标"]
    value_candidates = ["value", "metric_value", "指标值", "数值", "值", "指标数值"]
    unit_candidates = ["unit", "单位"]
    condition_candidates = ["condition", "条件", "测试条件", "电流密度条件", "current_density", "current density"]
    notes_candidates = ["notes", "note", "备注", "说明"]
    id_candidates = ["id", "ID", "编号", "序号", "index", "样品id", "样品ID"]
    doi_candidates = ["doi", "DOI"]
    title_candidates = ["title", "标题", "文献标题"]
    recommendation_job_id_candidates = [
        "recommendation_job_id",
        "recommendation job id",
        "reco_job_id",
        "reco job id",
        "推荐任务id",
        "推荐任务ID",
        "推荐job_id",
        "推荐job id",
    ]
    metals_scope_candidates = ["metals_scope", "metals scope", "components_scope", "scope", "金属范围", "金属scope", "主成分范围"]
    metals_other_candidates = ["metals_other", "metals other", "other_metals", "other metals", "impurities", "其它金属", "其他金属", "杂质", "其他元素", "其它元素"]

    stats = ProcessingStats()
    total_rows = 0
    kept = 0
    dropped_non_eta10 = 0
    dropped_unknown_eta10 = 0
    dropped_unknown_metric = 0
    dropped_bad_reaction = 0
    dropped_missing_material_identity = 0
    dropped_co2rr_missing_product = 0
    dropped_co2rr_incomplete_triplet = 0

    processed_rows: list[dict[str, Any]] = []

    with csv_path.open("r", encoding=str(args.encoding), newline="") as f:
        reader = csv.DictReader(f, delimiter=str(args.delimiter))
        fieldnames = [fn for fn in (reader.fieldnames or []) if fn]
        if not fieldnames:
            raise SystemExit(f"CSV has no header row: {csv_path}")

        col_reaction = _find_col(fieldnames, reaction_candidates)
        col_property = _find_col(fieldnames, property_candidates)
        col_metals = _find_col(fieldnames, metals_candidates)
        material_columns = {key: _find_col(fieldnames, candidates) for key, candidates in material_field_candidates.items()}
        col_material_input_json = _find_col(fieldnames, material_input_json_candidates)
        col_product = _find_col(fieldnames, product_candidates)
        col_co2rr_fe_value = _find_col(fieldnames, co2rr_fe_value_candidates)
        col_co2rr_fe_unit = _find_col(fieldnames, co2rr_fe_unit_candidates)
        col_co2rr_partial_value = _find_col(fieldnames, co2rr_partial_value_candidates, fuzzy=False)
        col_co2rr_partial_unit = _find_col(fieldnames, co2rr_partial_unit_candidates, fuzzy=False)
        col_metric_label = _find_col(fieldnames, metric_label_candidates)
        col_value = _find_col(fieldnames, value_candidates)
        col_unit = _find_col(fieldnames, unit_candidates)
        col_condition = _find_col(fieldnames, condition_candidates)
        if col_condition and "partial" in _norm_header(col_condition):
            # Avoid mis-reading explicit CO2RR partial-current-density columns as a condition column.
            col_condition = None
        col_id = _find_col(fieldnames, id_candidates, fuzzy=False)
        col_notes = _find_col(fieldnames, notes_candidates)
        col_doi = _find_col(fieldnames, doi_candidates)
        col_title = _find_col(fieldnames, title_candidates)
        col_reco_job_id = _find_col(fieldnames, recommendation_job_id_candidates)
        col_metals_scope = _find_col(fieldnames, metals_scope_candidates)
        col_metals_other = _find_col(fieldnames, metals_other_candidates)

        col_kind = col_property or col_reaction
        missing_required = [name for name, col in (("property_type/reaction_type", col_kind),) if not col]
        if not col_metals and not material_columns.get("material_name") and not col_material_input_json:
            missing_required.append("material_name or metals")
        if not col_value and not col_co2rr_partial_value:
            missing_required.append("value")
        if missing_required:
            raise SystemExit(
                "Missing required columns: "
                + ", ".join(missing_required)
                + f"\nDetected headers: {fieldnames}\n"
                + "Tip: use property_type, material_name (preferred) or legacy metals, value, unit, condition."
            )

        print(f"[experimental_csv] csv_path={csv_path}")
        print(
            f"[experimental_csv] detected_columns: property={col_property!r} reaction={col_reaction!r} material_name={material_columns.get('material_name')!r} "
            f"material_input_json={col_material_input_json!r} metals={col_metals!r} product={col_product!r} "
            f"value={col_value!r} unit={col_unit!r} condition={col_condition!r} metric_label={col_metric_label!r} "
            f"co2rr_fe={col_co2rr_fe_value!r}/{col_co2rr_fe_unit!r} "
            f"co2rr_partial={col_co2rr_partial_value!r}/{col_co2rr_partial_unit!r} id={col_id!r} notes={col_notes!r}"
        )

        for i, row in enumerate(reader, start=1):
            total_rows += 1

            metals_raw = row.get(col_metals) if col_metals else None
            metals, composition_pct = parse_metals_text(metals_raw)
            material_input, material_description = _material_input_for_row(
                row,
                columns=material_columns,
                material_input_json_column=col_material_input_json,
            )
            if not metals and not material_input.get("material_name"):
                dropped_missing_material_identity += 1
                continue

            condition_text = row.get(col_condition) if col_condition else None
            eta10_check = None

            rid = None
            if col_id:
                rid_raw = row.get(col_id)
                if rid_raw is not None and str(rid_raw).strip():
                    rid = str(rid_raw).strip()
            if not rid:
                rid = f"exp_{csv_path.stem}_{i}"

            prop_raw = row.get(col_property) if col_property else None
            rt_raw = row.get(col_reaction) if col_reaction else None
            task = canonical_task_type(prop_raw) or canonical_task_type(rt_raw)
            prop = task if task in MATERIAL_TASK_TYPES else None
            if prop:
                processed = _build_material_property_record(
                    rid=rid,
                    prop=prop,
                    metals=metals,
                    metals_raw=metals_raw,
                    composition_pct=composition_pct,
                    value_text=row.get(col_value),
                    unit_text=row.get(col_unit) if col_unit else None,
                    condition_text=condition_text,
                    notes_text=row.get(col_notes) if col_notes else None,
                    source_file=csv_path.name,
                    row=row,
                    col_reco_job_id=col_reco_job_id,
                    col_metals_scope=col_metals_scope,
                    col_metals_other=col_metals_other,
                    col_doi=col_doi,
                    col_title=col_title,
                    material_input=material_input,
                    material_description=material_description,
                )
                if processed is None:
                    stats.record_dropped("material_property_value_parse_failed")
                    continue
                processed_rows.append(processed)
                kept += 1
                continue

            rt = normalize_reaction_type(rt_raw)
            if not rt:
                dropped_bad_reaction += 1
                continue

            product_raw = row.get(col_product) if col_product else None
            product = str(product_raw or "").strip() if product_raw is not None else ""
            if rt == "CO2RR" and not product:
                dropped_co2rr_missing_product += 1
                continue

            raw: dict[str, Any] = {"id": rid, "reaction_type": rt, "task_type": task or rt}
            if metals:
                raw["metals"] = metals
            if material_input:
                raw["material_input"] = material_input
            if material_description:
                raw["material_description"] = material_description

            co2rr_fe_text = None
            co2rr_partial_text = None
            if rt == "CO2RR":
                fe_value_text = row.get(col_co2rr_fe_value) if col_co2rr_fe_value else None
                fe_unit_text = row.get(col_co2rr_fe_unit) if col_co2rr_fe_unit else "%"
                partial_value_text = row.get(col_co2rr_partial_value) if col_co2rr_partial_value else None
                partial_unit_text = row.get(col_co2rr_partial_unit) if col_co2rr_partial_unit else None
                has_fe = fe_value_text is not None and str(fe_value_text).strip() != ""
                has_partial = partial_value_text is not None and str(partial_value_text).strip() != ""
                if has_fe or has_partial:
                    if not (product and has_fe and has_partial):
                        dropped_co2rr_incomplete_triplet += 1
                        continue
                    co2rr_fe_text = stitch_value_and_unit(fe_value_text, fe_unit_text or "%")
                    co2rr_partial_text = stitch_value_and_unit(partial_value_text, partial_unit_text or (row.get(col_unit) if col_unit else None))
                    if co2rr_fe_text is None or co2rr_partial_text is None:
                        stats.record_dropped("missing_metric_value")
                        continue
                    raw["product"] = product
                    raw["faradaic_efficiency"] = co2rr_fe_text
                    raw["partial_current_density"] = co2rr_partial_text

            if co2rr_fe_text is None or co2rr_partial_text is None:
                metric_label = row.get(col_metric_label) if col_metric_label else None
                metric_key = infer_metric_key(rt, metric_label)
                if not metric_key:
                    dropped_unknown_metric += 1
                    continue

                value_text = row.get(col_value)
                unit_text = row.get(col_unit) if col_unit else None
                stitched = stitch_value_and_unit(value_text, unit_text)
                if stitched is None:
                    # Let process_raw_record count it as no_metrics, but keep a clearer counter here.
                    stats.record_dropped("missing_metric_value")
                    continue

                if _metric_requires_eta10(metric_key):
                    eta10_check = check_eta10_condition(condition_text)
                    if eta10_check.status == "mismatch" and args.drop_explicit_non_eta10:
                        dropped_non_eta10 += 1
                        continue
                    if eta10_check.status == "unknown" and args.require_eta10_condition:
                        dropped_unknown_eta10 += 1
                        continue

                raw[metric_key] = stitched
                if rt == "CO2RR" and product:
                    raw["product"] = product

            if col_doi:
                doi = str(row.get(col_doi) or "").strip()
                if doi:
                    raw["doi"] = doi
            if col_title:
                title = str(row.get(col_title) or "").strip()
                if title:
                    raw["title"] = title

            processed = process_raw_record(raw, source_file=csv_path.name, stats=stats)
            if processed is None:
                continue

            # Attach experimental-only provenance fields (kept out of metrics).
            processed["source_type"] = "experimental_csv"
            processed["metals_raw"] = str(metals_raw).strip() if metals_raw is not None else None
            if composition_pct:
                processed["composition_pct"] = composition_pct
            if condition_text is not None and str(condition_text).strip():
                processed["condition_raw"] = str(condition_text).strip()
            if eta10_check is not None:
                processed["eta10_condition_status"] = eta10_check.status
                if eta10_check.current_density_mA_cm_2 is not None:
                    processed["eta10_condition_mA_cm-2"] = eta10_check.current_density_mA_cm_2
            if col_reco_job_id:
                rid2 = str(row.get(col_reco_job_id) or "").strip()
                if rid2:
                    processed["recommendation_job_id"] = rid2
            if col_metals_scope:
                scope = str(row.get(col_metals_scope) or "").strip()
                if scope:
                    processed["metals_scope"] = scope
            if col_metals_other:
                other = str(row.get(col_metals_other) or "").strip()
                if other:
                    processed["metals_other"] = other

            # Remove nulls to keep the processed record compact.
            processed = {k: v for k, v in processed.items() if v is not None}

            processed_rows.append(processed)
            kept += 1

    print(f"[experimental_csv] rows_total={total_rows} kept={kept}")
    if dropped_bad_reaction:
        print(f"[experimental_csv] dropped_bad_reaction_type={dropped_bad_reaction}")
    if dropped_missing_material_identity:
        print(f"[experimental_csv] dropped_missing_material_identity={dropped_missing_material_identity}")
    if dropped_co2rr_missing_product:
        print(f"[experimental_csv] dropped_co2rr_missing_product={dropped_co2rr_missing_product}")
        print(
            "[experimental_csv] tip: CO2RR rows require a 'product' column (main product label). "
            "Allowed: CO, HCOOH, CH4, C2H5OH, C2H4, CH3COOH."
        )
    if dropped_co2rr_incomplete_triplet:
        print(f"[experimental_csv] dropped_co2rr_incomplete_triplet={dropped_co2rr_incomplete_triplet}")
        print(
            "[experimental_csv] tip: structured CO2RR rows must provide product + faradaic_efficiency + partial_current_density together."
        )
    if dropped_unknown_metric:
        print(f"[experimental_csv] dropped_unknown_metric_mapping={dropped_unknown_metric}")
    if dropped_non_eta10:
        print(f"[experimental_csv] dropped_explicit_non_eta10_condition={dropped_non_eta10}")
    if dropped_unknown_eta10:
        print(f"[experimental_csv] dropped_unknown_eta10_condition={dropped_unknown_eta10}")
    if stats.dropped_records_by_reason:
        print(f"[experimental_csv] dropped_records_by_reason={stats.dropped_records_by_reason}")
    if stats.dropped_metrics_by_reason:
        print(f"[experimental_csv] dropped_metrics_by_reason={stats.dropped_metrics_by_reason}")

    if args.dry_run:
        print("[experimental_csv] dry_run=1 (no files written)")
        return

    with out_path.open("w", encoding="utf-8") as out:
        for obj in processed_rows:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"[experimental_csv] wrote {len(processed_rows)} processed records -> {out_path}")
    print("[experimental_csv] Next step:")
    print(
        "  .venv/bin/python scripts/data/build_chem_performance_dataset.py "
        f"--input_dir {out_path.parent} --output_file {out_path.parent / (csv_path.stem + '_dataset.jsonl')} "
        "--include_unit_hint"
    )


if __name__ == "__main__":
    main()
