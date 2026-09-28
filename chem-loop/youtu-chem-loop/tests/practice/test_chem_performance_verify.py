import pytest

from utu.db import EvaluationSample
from utu.practice.verify.chem_performance_verify import verify_func
from utu.practice.verify.chem_performance_lib.answer_parser import has_think_block, parse_answer_json, parse_answer_numbers
from utu.practice.verify.chem_performance_lib.gt_parser import parse_gt_json
from utu.practice.verify.chem_performance_lib.key_alignment import diff_keys
from utu.practice.verify.chem_performance_lib.reward import compute_reward


def test_has_think_block():
    assert has_think_block("<think>a</think><answer>{\"x\": 1}</answer>")
    assert not has_think_block("<answer>{\"x\": 1}</answer>")


def test_parse_answer_json_ok():
    resp = "<think>t</think><answer>{\"overpotential_10mAcm-2\": 300}</answer>"
    got = parse_answer_json(resp)
    assert got == {"overpotential_10mAcm-2": 300.0}


def test_parse_answer_json_reject_unit_string():
    resp = "<think>t</think><answer>{\"overpotential_10mAcm-2\": \"0.6 V\"}</answer>"
    with pytest.raises(ValueError):
        parse_answer_json(resp)


def test_parse_gt_json_parses_numeric_prefix():
    gt = parse_gt_json("{\"overpotential_10mAcm-2\": \"288 mV\"}")
    assert gt["overpotential_10mAcm-2"] == pytest.approx(288.0)


def test_diff_keys():
    missing, extra = diff_keys({"a": 1, "b": 2}, {"a": 1, "c": 3})
    assert missing == {"b"}
    assert extra == {"c"}


def test_verify_func_missing_think_can_still_score():
    sample = EvaluationSample(
        response="<answer>{\"overpotential_10mAcm-2\": 300}</answer>",
        correct_answer="{\"overpotential_10mAcm-2\": \"300 mV\"}",
        meta={"reaction_type": "OER", "units": {"overpotential_10mAcm-2": "mV"}},
    )
    res = verify_func(sample)
    assert res["reward"] == pytest.approx(1.0)


def test_verify_func_extra_key_is_zero_reward():
    sample = EvaluationSample(
        response="<think>x</think><answer>{\"overpotential_10mAcm-2\": 300, \"extra\": 1}</answer>",
        correct_answer="{\"overpotential_10mAcm-2\": \"300 mV\"}",
        meta={"reaction_type": "OER", "units": {"overpotential_10mAcm-2": "mV"}},
    )
    res = verify_func(sample)
    assert res["reward"] == 0.0


def test_parse_answer_numbers_accepts_structured_json_shape():
    resp = '{"think":"short","answer":{"overpotential_10mAcm-2": 300}}'
    got = parse_answer_numbers(resp)
    assert got == {"overpotential_10mAcm-2": 300.0}


def test_parse_answer_numbers_can_repair_unit_string_when_expected_units_provided():
    resp = '<answer>{"overpotential_10mAcm-2": "0.3 V"}</answer>'
    got = parse_answer_numbers(resp, expected_units={"overpotential_10mAcm-2": "mV"})
    assert got["overpotential_10mAcm-2"] == pytest.approx(300.0)


def test_verify_func_can_repair_unit_string_prediction():
    sample = EvaluationSample(
        response='<answer>{"overpotential_10mAcm-2": "0.3 V"}</answer>',
        correct_answer='{"overpotential_10mAcm-2": "300 mV"}',
        meta={"reaction_type": "HER", "units": {"overpotential_10mAcm-2": "mV"}},
    )
    res = verify_func(sample)
    assert res["reward"] == pytest.approx(1.0)


def test_compute_reward_o5h_focuses_on_fe_only() -> None:
    import math

    gt = {"faradaic_efficiency": 1.0}
    units = {"faradaic_efficiency": "fraction_0_to_1"}

    reward_ok, per_metric_ok = compute_reward(
        gt,
        {"faradaic_efficiency": 1.0},
        units=units,
        reaction_type="O5H",
    )
    assert reward_ok == pytest.approx(1.0)
    assert per_metric_ok["faradaic_efficiency"] == pytest.approx(1.0)

    # A full-point miss should decay smoothly (with the unit floor applied for fraction metrics).
    reward_bad, _ = compute_reward(
        gt,
        {"faradaic_efficiency": 0.0},
        units=units,
        reaction_type="O5H",
    )
    expected = math.exp(-(1.0 / 1.05))
    assert reward_bad == pytest.approx(expected)


def test_verify_func_reads_new_material_task_type_for_reward_rules() -> None:
    sample = EvaluationSample(
        response='<answer>{"faradaic_efficiency": 0.0}</answer>',
        correct_answer='{"faradaic_efficiency": 1.0}',
        meta={"task_type": "O5H", "units": {"faradaic_efficiency": "fraction_0_to_1"}},
    )

    result = verify_func(sample)

    expected, _ = compute_reward(
        {"faradaic_efficiency": 1.0},
        {"faradaic_efficiency": 0.0},
        units={"faradaic_efficiency": "fraction_0_to_1"},
        reaction_type="O5H",
    )
    assert result["reward"] == pytest.approx(expected)


def test_verify_func_co2rr_product_with_fe_scores_fe_when_product_correct() -> None:
    sample = EvaluationSample(
        response='<think>x</think><answer>{"product": "CO", "faradaic_efficiency": 0.8}</answer>',
        correct_answer='{"product": "CO", "faradaic_efficiency": 0.8}',
        meta={"reaction_type": "CO2RR"},
    )
    res = verify_func(sample)
    assert res["reward"] == pytest.approx(1.0)


def test_verify_func_co2rr_product_with_fe_zero_when_wrong_product() -> None:
    sample = EvaluationSample(
        response='<think>x</think><answer>{"product": "HCOOH", "faradaic_efficiency": 0.8}</answer>',
        correct_answer='{"product": "CO", "faradaic_efficiency": 0.8}',
        meta={"reaction_type": "CO2RR"},
    )
    res = verify_func(sample)
    assert res["reward"] == 0.0


def test_verify_func_co2rr_product_with_fe_accepts_percent_string() -> None:
    sample = EvaluationSample(
        response='<think>x</think><answer>{"product": "CO", "faradaic_efficiency": "80%"}</answer>',
        correct_answer='{"product": "CO", "faradaic_efficiency": 0.8}',
        meta={"reaction_type": "CO2RR"},
    )
    res = verify_func(sample)
    assert res["reward"] == pytest.approx(1.0)


def test_verify_func_co2rr_product_only_gt_can_optionally_score_fe_from_meta() -> None:
    # Backward-compat: old GT may only include product; if meta carries truth FE and the
    # model outputs faradaic_efficiency, we score FE instead of a hard 0/1.
    sample = EvaluationSample(
        response='<think>x</think><answer>{"product": "CO", "faradaic_efficiency": 0.8}</answer>',
        correct_answer='{"product": "CO"}',
        meta={"reaction_type": "CO2RR", "metrics_raw": {"truth_faradaic_efficiency_fraction": "0.8"}},
    )
    res = verify_func(sample)
    assert res["reward"] == pytest.approx(1.0)


def test_parse_answer_numbers_repairs_material_property_units() -> None:
    resp = (
        '<answer>{'
        '"conductivity": "7781 S cm-1", '
        '"photothermal_conversion_efficiency": "0.865", '
        '"thermal_conductivity": "0.53 W/(mK)", '
        '"saturation_magnetization": "2.27 A m2/kg", '
        '"neel_temperature": "250 K"'
        "}</answer>"
    )
    got = parse_answer_numbers(
        resp,
        expected_units={
            "conductivity": "S/m",
            "photothermal_conversion_efficiency": "%",
            "thermal_conductivity": "W m-1 K-1",
            "saturation_magnetization": "emu/g",
            "neel_temperature": "K",
        },
    )
    assert got["conductivity"] == pytest.approx(778100.0)
    assert got["photothermal_conversion_efficiency"] == pytest.approx(86.5)
    assert got["thermal_conductivity"] == pytest.approx(0.53)
    assert got["saturation_magnetization"] == pytest.approx(2.27)
    assert got["neel_temperature"] == pytest.approx(250.0)


def test_verify_func_material_property_prediction_with_units() -> None:
    sample = EvaluationSample(
        response='<answer>{"conductivity": "7781 S cm-1"}</answer>',
        correct_answer='{"conductivity": "778100 S/m"}',
        meta={"property_type": "conductivity", "reaction_type": "conductivity", "units": {"conductivity": "S/m"}},
    )
    res = verify_func(sample)
    assert res["reward"] == pytest.approx(1.0)
