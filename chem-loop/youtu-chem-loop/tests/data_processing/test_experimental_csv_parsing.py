from utu.data_processing.chem_performance.experimental_csv import (
    check_eta10_condition,
    infer_metric_key,
    normalize_reaction_type,
    parse_metals_text,
    stitch_value_and_unit,
)


def test_normalize_reaction_type():
    assert normalize_reaction_type("her") == "HER"
    assert normalize_reaction_type(" CO2-RR ") == "CO2RR"
    assert normalize_reaction_type("HZOR") == "HzOR"
    assert normalize_reaction_type("尿素氧化") == "UOR"
    assert normalize_reaction_type("") is None


def test_parse_metals_text_with_composition_pct():
    metals, pct = parse_metals_text("Co(57%),Ni(23%)")
    assert metals == ["Co", "Ni"]
    assert pct == {"Co": 57.0, "Ni": 23.0}


def test_parse_metals_text_basic_tokens():
    metals, pct = parse_metals_text("pt, ru")
    assert metals == ["Pt", "Ru"]
    assert pct == {}


def test_stitch_value_and_unit():
    assert stitch_value_and_unit("300", "mV") == "300 mV"
    assert stitch_value_and_unit("0.14", "V") == "0.14 V"
    assert stitch_value_and_unit("98.5", "%") == "98.5%"
    # Already has unit; do not double-append.
    assert stitch_value_and_unit("300 mV", "mV") == "300 mV"


def test_infer_metric_key_by_reaction_type_only():
    # In project v5 scope each reaction has a single target metric.
    assert infer_metric_key("HER") == "overpotential_10mAcm-2"
    assert infer_metric_key("ORR") == "half_wave_potential"
    assert infer_metric_key("HOR") == "exchange_current_density"
    assert infer_metric_key("O5H") == "faradaic_efficiency"
    assert infer_metric_key("CO2RR") == "partial_current_density"


def test_infer_metric_key_from_metric_label():
    assert infer_metric_key("ORR", "E1/2") == "half_wave_potential"
    assert infer_metric_key("HOR", "j0") == "exchange_current_density"
    assert infer_metric_key("O5H", "FE") == "faradaic_efficiency"
    assert infer_metric_key("EOR", "mass_activity") == "mass_activity"


def test_check_eta10_condition():
    assert check_eta10_condition("10 mA cm-2").status == "ok"
    assert check_eta10_condition("0.01 A cm-2").status == "ok"
    assert check_eta10_condition("20 mA cm-2").status == "mismatch"
    assert check_eta10_condition("").status == "unknown"
