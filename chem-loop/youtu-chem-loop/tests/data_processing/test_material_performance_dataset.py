import json

from utu.data_processing.material_performance_candidates import (
    MaterialPerformanceCandidate,
    select_candidates,
)
from utu.data_processing.material_performance_dataset import (
    build_dataset,
    build_material_description,
    candidate_to_canonical,
    canonical_to_grpo_sample,
)
from utu.practice.verify.chem_performance_lib.gt_parser import parse_gt_json


def make_candidate(**overrides):
    values = {
        "task_type": "thermoelectric",
        "doi": "10.1/example",
        "material": {"material_name": "Bi2Te3"},
        "material_index": 0,
        "metrics": {"figure_of_merit": "1.2"},
        "units": {},
        "categorical_metrics": {},
        "conditions": {},
        "product": None,
        "status": "direct",
        "binding_mode": "single_material",
        "reasons": (),
        "context_key": "ZT",
        "label_key": "1.2",
        "source_group": "new_4",
        "source_file": "source.jsonl",
        "row_number": 1,
        "extraction_index": 0,
    }
    values.update(overrides)
    return MaterialPerformanceCandidate(**values)


def test_prompt_uses_material_name_when_every_optional_field_is_missing() -> None:
    assert build_material_description({"material_name": "CuO"}) == "材料是CuO。"


def test_prompt_assembles_only_available_material_fields() -> None:
    description = build_material_description(
        {
            "material_name": "MoS2/CuO",
            "major_category": "composite",
            "components": [{"component_name": "MoS2"}, {"component_name": "CuO"}],
            "elements": ["Cu", "Mo", "O", "S"],
        }
    )
    assert "材料是MoS2/CuO" in description
    assert "材料类别是composite" in description
    assert "材料组分包括：MoS2、CuO" in description
    assert "含有元素：Cu、Mo、O、S" in description
    assert "前驱体" not in description
    assert "投料比" not in description


def test_prompt_assembles_optional_synthesis_fields_when_present() -> None:
    description = build_material_description(
        {
            "material_name": "CuO",
            "precursors": ["Cu(NO3)2", "NaOH"],
            "feed_ratio": [1, 2],
            "preparation_method": "水热法",
            "elements": ["Cu", "O"],
            "element_content": {"Cu": "80%", "O": "20%"},
        }
    )
    assert "以前驱体Cu(NO3)2、NaOH制备" in description
    assert "前驱体投料比为：1：2" in description
    assert "通过水热法的方式制备" in description
    assert "元素含量大概分别为：Cu 80%、O 20%" in description


def test_missing_optional_conditions_still_builds_grpo_sample() -> None:
    record = candidate_to_canonical(make_candidate())
    sample = canonical_to_grpo_sample(record)
    assert sample is not None
    assert sample["meta"]["material_name"] == "Bi2Te3"
    assert sample["meta"]["conditions"] == {}
    assert parse_gt_json(sample["answer"]) == {"figure_of_merit": 1.2}


def test_bound_comparator_is_preserved_but_not_treated_as_exact_gt() -> None:
    candidate = make_candidate(
        task_type="furfural_hydrogenation",
        metrics={"furfuryl_alcohol_yield": ">=90 %"},
        units={"furfuryl_alcohol_yield": "%"},
        context_key="yield",
        label_key=">=90",
    )
    record = candidate_to_canonical(candidate)
    metric = record["performance"]["metrics"]["furfuryl_alcohol_yield"]
    assert metric["numeric_value"] == 90.0
    assert metric["comparator"] == ">="
    assert canonical_to_grpo_sample(record) is None


def test_approximate_metric_is_emitted_with_comparator_metadata() -> None:
    candidate = make_candidate(metrics={"figure_of_merit": "~1.2"}, label_key="~1.2")
    sample = canonical_to_grpo_sample(candidate_to_canonical(candidate))
    assert sample is not None
    assert parse_gt_json(sample["answer"]) == {"figure_of_merit": 1.2}
    assert sample["meta"]["metric_comparators"] == {"figure_of_merit": "~"}


def test_categorical_complete_is_retained_but_not_fabricated_as_number() -> None:
    candidate = make_candidate(
        task_type="antibacterial",
        metrics={"minimum_concentration": "24 ug/mL"},
        units={"minimum_concentration": "ug/mL"},
        categorical_metrics={"bactericidal_threshold": "complete"},
        context_key="antibacterial",
        label_key="complete+24",
    )
    record = candidate_to_canonical(candidate)
    assert record["performance"]["categorical_metrics"] == {"bactericidal_threshold": "complete"}
    sample = canonical_to_grpo_sample(record)
    assert sample is not None
    assert json.loads(sample["answer"]) == {"minimum_concentration": 24.0}


def test_hor_noncanonical_exchange_current_is_not_mixed_into_point_gt() -> None:
    candidate = make_candidate(
        task_type="HOR",
        metrics={"exchange_current_density": "51.5 mA mg-1 Pd"},
        units={"exchange_current_density": "mA mg-1 Pd"},
        context_key="exchange_current_density",
        label_key="51.5 mA mg-1 Pd",
    )
    record = candidate_to_canonical(candidate)
    assert canonical_to_grpo_sample(record) is None


def test_hor_canonical_area_exchange_current_is_grpo_ready() -> None:
    candidate = make_candidate(
        task_type="HOR",
        metrics={"exchange_current_density": "2.74 mA cm-2"},
        units={"exchange_current_density": "mA cm-2"},
        context_key="exchange_current_density",
        label_key="2.74 mA cm-2",
    )
    sample = canonical_to_grpo_sample(candidate_to_canonical(candidate))
    assert sample is not None
    assert json.loads(sample["answer"]) == {"exchange_current_density": 2.74}


def test_selection_removes_duplicates_and_quarantines_context_conflicts() -> None:
    duplicate = make_candidate(source_file="duplicate.jsonl", extraction_index=1)
    conflict = make_candidate(
        metrics={"figure_of_merit": "1.5"},
        label_key="1.5",
        extraction_index=2,
    )
    clean = make_candidate(
        doi="10.1/clean",
        context_key="ZT@500K",
        label_key="1.4",
        metrics={"figure_of_merit": "1.4"},
        extraction_index=3,
    )
    selection = select_candidates([make_candidate(), duplicate, conflict, clean])
    assert selection.selected == (clean,)
    reasons = [reason for _, reason in selection.excluded]
    assert reasons.count("exact_duplicate") == 1
    assert reasons.count("conflicting_context") == 2


def test_build_manifest_counts_current_verify_ready_samples() -> None:
    exact = make_candidate()
    bounded = make_candidate(
        doi="10.1/bounded",
        metrics={"figure_of_merit": ">1.0"},
        label_key=">1.0",
    )
    result = build_dataset([exact, bounded], {"selected_candidates": 2})
    assert len(result.canonical_records) == 2
    assert len(result.grpo_samples) == 1
    assert result.manifest["outputs"]["bounded_metric_values_deferred_from_grpo"] == 1
