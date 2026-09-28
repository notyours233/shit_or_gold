from pathlib import Path

from utu.data_processing.material_performance_audit import (
    NEW_FILE_TASKS,
    OLD_FILE_TASKS,
    _bind_new_extraction,
    _metric_quality,
    infer_material_elements,
    normalize_doi,
    normalize_material_name,
    parse_numeric,
    render_markdown,
)
from utu.data_processing.material_performance_quality import (
    AuditObservation,
    analyze_cross_record_observations,
    vague_material_name_reasons,
)


def test_declared_source_files_exist() -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "raw" / "material_performance_20260728"
    assert all((root / "material_categories_full_20260706" / name).is_file() for name in OLD_FILE_TASKS)
    assert all((root / "batch3" / name).is_file() for name in NEW_FILE_TASKS)


def test_normalize_doi_removes_url_and_markdown_noise() -> None:
    assert normalize_doi(" https://doi.org/10.1002/CNMA.202000311** ") == "10.1002/cnma.202000311"


def test_parse_numeric_preserves_comparator() -> None:
    parsed = parse_numeric(">90 %")
    assert parsed is not None
    assert parsed.value == 90.0
    assert parsed.comparator == ">"


def test_infer_material_elements_uses_formula_components_and_names() -> None:
    material = {
        "material_name": "Pt-Fe/MWNT",
        "nonmetal_elements": ["C"],
        "components": [
            {"component_name": "Pt-Fe"},
            {"component_name": "multi-walled carbon nanotubes"},
        ],
    }
    assert {"Pt", "Fe", "C"}.issubset(infer_material_elements(material))


def test_new_extraction_exact_name_binding() -> None:
    materials = [
        {"material_name": "gamma-Al2O3"},
        {"material_name": "Pt-Fe/MWNT"},
    ]
    status, index, reasons = _bind_new_extraction(materials, {"material_name": "Pt–Fe/MWNT"})
    assert status == "direct"
    assert index == 1
    assert reasons == []
    assert normalize_material_name("Pt–Fe/MWNT") == normalize_material_name("Pt-Fe/MWNT")


def test_multimaterial_extraction_without_name_is_not_auto_bound() -> None:
    materials = [{"material_name": "CuO"}, {"material_name": "ZnO"}]
    status, index, reasons = _bind_new_extraction(materials, {"evidence": "strong antibacterial activity"})
    assert status == "manual_review"
    assert index is None
    assert "multiple_materials_without_material_name" in reasons


def test_thermoelectric_temperature_is_optional_context() -> None:
    status, reasons, parsed = _metric_quality("thermoelectric", {"figure_of_merit": "1.2"})
    assert status == "direct"
    assert reasons == []
    assert parsed["figure_of_merit"] == 1.2


def test_antibacterial_complete_threshold_is_recoverable_not_silently_numeric() -> None:
    status, reasons, parsed = _metric_quality(
        "antibacterial",
        {"bactericidal_threshold": "complete", "minimum_concentration": "24 ug/mL"},
    )
    assert status == "recoverable"
    assert reasons == ["categorical_complete_threshold_requires_policy"]
    assert parsed == {"minimum_concentration": 24.0}


def test_vague_name_flags_group_or_variable_scope_without_excluding_formula() -> None:
    assert vague_material_name_reasons("gypsum composites with zeolite fillers doped with various metal ions")
    assert vague_material_name_reasons("Gd1-xDyxScO3", "a series with x = 0, 0.1, 0.2 and 1")
    assert vague_material_name_reasons("CuO") == ()


def test_cross_record_analysis_separates_duplicates_conflicts_and_conditions() -> None:
    base = {
        "task_type": "thermoelectric",
        "doi": "10.1/example",
        "material_identity": "bisbte",
        "material_name": "BiSbTe",
        "status": "direct",
        "numeric_prediction_ready": True,
        "source_file": "source.jsonl",
        "row_number": 1,
    }
    observations = [
        AuditObservation(context_key="T=300 K", label_key="ZT=1.0", extraction_index=0, **base),
        AuditObservation(context_key="T=300 K", label_key="ZT=1.0", extraction_index=1, **base),
        AuditObservation(context_key="T=300 K", label_key="ZT=1.2", extraction_index=2, **base),
        AuditObservation(context_key="T=500 K", label_key="ZT=1.4", extraction_index=3, **base),
    ]
    result = analyze_cross_record_observations(observations)["totals"]
    assert result["exact_duplicate_groups"] == 1
    assert result["exact_duplicate_observations_removed"] == 1
    assert result["conflicting_context_groups"] == 1
    assert result["raw_observations_in_conflicting_contexts"] == 3
    assert result["material_identities_with_multiple_contexts"] == 1
    assert result["unique_trainable_samples"] == 1


def test_render_markdown_interpolates_numeric_contract_counts() -> None:
    audit = {
        "overall": {
            "candidate_samples": 1,
            "direct_samples": 1,
            "recoverable_samples": 0,
            "manual_review_samples": 0,
            "deduplicated_trainable_samples": 1,
            "numeric_metric_contract_ready_samples": 1,
            "not_numeric_metric_contract_ready_samples": 0,
        },
        "established_15": {"totals": {}, "by_task": {}},
        "new_4": {"totals": {}, "by_task": {}},
        "cross_record_quality": {"totals": {}},
        "established_truth_quality": {"totals": {}},
        "prompt_field_coverage": {
            "by_group": {
                "established_15": {
                    "material_name_present": 0,
                    "material_objects": 0,
                    "explicit_metal_elements_present": 0,
                },
                "new_4": {
                    "material_name_present": 0,
                    "material_objects": 0,
                    "explicit_metal_elements_present": 0,
                },
            }
        },
        "chroma": {"available": False, "error": "test"},
    }
    report = render_markdown(audit, 0)
    assert "while 0 carry a diagnostic flag" in report
    assert "{overall" not in report
