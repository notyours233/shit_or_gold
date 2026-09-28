from utu.data_processing.chem_performance.metals import normalize_metal_symbol, normalize_metals
from utu.data_processing.chem_performance.metrics import normalize_metric_key, normalize_metric_value
from utu.data_processing.chem_performance.processor import ProcessingStats, process_raw_record


def test_normalize_metal_symbol():
    assert normalize_metal_symbol("pt") == "Pt"
    assert normalize_metal_symbol("NI") == "Ni"
    assert normalize_metal_symbol("Fe") == "Fe"
    assert normalize_metal_symbol(" ") == ""


def test_normalize_metals_dedup_and_sort():
    assert normalize_metals(["Pt", "Ru", "pt", " RU "]) == ["Pt", "Ru"]


def test_normalize_metric_key_o5h():
    assert normalize_metric_key("Faradaic_efficiency", "O5H") == "faradaic_efficiency"
    # already normalized should remain stable
    assert normalize_metric_key("faradaic_efficiency", "O5H") == "faradaic_efficiency"


def test_normalize_metric_value_units():
    # overpotential is stored as mV (η@10 by convention)
    mv = normalize_metric_value("300.00 mV", metric_key="overpotential_10mAcm-2")
    assert mv is not None
    assert mv.value_str == "300 mV"
    assert mv.unit_hint == "mV"

    v_as_mv = normalize_metric_value("0.14 V", metric_key="overpotential_10mAcm-2")
    assert v_as_mv is not None
    assert v_as_mv.value_str == "140 mV"
    assert v_as_mv.unit_hint == "mV"

    # potential-like metrics are stored as V
    pot = normalize_metric_value(" -0.064 V", metric_key="potential_10mAcm-2")
    assert pot is not None
    assert pot.value_str == "-0.064 V"
    assert pot.unit_hint == "V"

    pct = normalize_metric_value("95.0 %")
    assert pct is not None
    assert pct.value_str == "0.95"
    assert pct.unit_hint == "fraction_0_to_1"

    pct2 = normalize_metric_value("98.5%")
    assert pct2 is not None
    assert pct2.value_str == "0.985"

    # exchange_current_density is stored as mA cm^-2 and must be absolute (convertible).
    j0 = normalize_metric_value("3.68 mA cm-2", metric_key="exchange_current_density")
    assert j0 is not None
    assert j0.value_str == "3.68 mA cm-2"
    assert j0.unit_hint == "mA cm-2"

    j0_from_a = normalize_metric_value("0.00368 A cm-2", metric_key="exchange_current_density")
    assert j0_from_a is not None
    assert j0_from_a.value_str == "3.68 mA cm-2"

    assert normalize_metric_value("9 times greater than Pt/HSC", metric_key="exchange_current_density") is None

    assert normalize_metric_value("cm-2") is None


def test_process_raw_record_filters_null_and_non_metrics():
    stats = ProcessingStats()
    raw = {
        "id": "33",
        "pos": 33,
        "block_index": 0,
        "metals": ["Pt", "Ru"],
        "reaction_type": "HOR",
        "exchange_current_density": "3.68 mA cm-2",
        "overpotential_10mAcm-2": None,
        "overpotential_50mAcm-2": None,
    }
    processed = process_raw_record(raw, source_file="hor.jsonl", stats=stats)
    assert processed is not None
    assert processed["metals"] == ["Pt", "Ru"]
    assert processed["reaction_type"] == "HOR"
    assert processed["metrics_gt"] == {"exchange_current_density": "3.68 mA cm-2"}
    # Non-metric fields must not appear as metrics
    assert "product" not in processed["metrics_gt"]
    assert "pos" not in processed["metrics_gt"]

def test_process_raw_record_her_overpotential_is_normalized_to_mv():
    raw = {"id": "x", "metals": ["Mo"], "reaction_type": "HER", "overpotential": "0.18 V"}
    processed = process_raw_record(raw)
    assert processed is not None
    assert processed["metrics_gt"] == {"overpotential_10mAcm-2": "180 mV"}


def test_process_raw_record_hzor_overpotential_key_is_canonicalized_to_eta10_mv():
    raw = {
        "id": "17",
        "metals": ["Cu"],
        "reaction_type": "HzOR",
        "overpotential_10mAcm-2": "0.36 V",
        "overpotential_100mAcm-2": None,
    }
    processed = process_raw_record(raw)
    assert processed is not None
    assert processed["reaction_type"] == "HzOR"
    assert processed["metrics_gt"] == {"overpotential_10mAcm-2": "360 mV"}


def test_process_raw_record_accepts_uppercase_hzor_reaction_type():
    raw = {
        "id": "18",
        "metals": ["Cu"],
        "reaction_type": "HZOR",
        "overpotential": "0.36 V",
    }
    processed = process_raw_record(raw)
    assert processed is not None
    assert processed["reaction_type"] == "HzOR"
    assert processed["metrics_gt"] == {"overpotential_10mAcm-2": "360 mV"}


def test_process_raw_record_o5h_key_and_percent_normalization():
    raw = {
        "id": "13",
        "metals": ["Co", "Ni"],
        "reaction_type": "O5H",
        "Faradaic_efficiency": "98.5%",
        "HMF_conversion": "100%",
        "FDCA_yield": "99.6%",
    }
    processed = process_raw_record(raw)
    assert processed is not None
    assert processed["reaction_type"] == "O5H"
    # Current requirement: O5H focuses on FE only.
    assert processed["metrics_gt"] == {"faradaic_efficiency": "0.985"}


def test_process_raw_record_co2rr_product_is_preserved_but_not_a_metric():
    # CO2RR final schema: product list + FE list + current density list.
    # We keep only the top-FE product as the truth product, and derive its partial current density.
    raw = {
        "id": "0",
        "metals": ["Bi"],
        "reaction_type": "CO2RR",
        "product": ["HCOOH", "CO"],
        "faradaic_efficiency": ["95.0 %", "10%"],
        "current_density": [
            {"type": "total", "product": "HCOOH", "value": "100 mA cm-2"},
        ],
    }
    processed = process_raw_record(raw)
    assert processed is not None
    assert processed["reaction_type"] == "CO2RR"
    assert processed["product"] == "HCOOH"
    assert processed["metrics_gt"] == {"faradaic_efficiency": "0.95", "partial_current_density": "95 mA cm-2"}


def test_process_raw_record_co2rr_manual_record_keeps_fe_and_partial_current_density() -> None:
    raw = {
        "id": "manual_1",
        "metals": ["Cu", "Zn"],
        "reaction_type": "CO2RR",
        "product": "CO",
        "faradaic_efficiency": "62%",
        "partial_current_density": "180 mA cm-2",
    }
    processed = process_raw_record(raw)
    assert processed is not None
    assert processed["product"] == "CO"
    assert processed["metrics_gt"] == {"faradaic_efficiency": "0.62", "partial_current_density": "180 mA cm-2"}


def test_process_raw_record_co2rr_drops_unwanted_truth_product() -> None:
    # If the highest-FE product is outside our focused CO2RR label set (e.g. C2+),
    # the record should be dropped entirely.
    stats = ProcessingStats()
    raw = {
        "id": "1",
        "metals": ["Cu"],
        "reaction_type": "CO2RR",
        "product": ["C2+", "CO"],
        "faradaic_efficiency": ["90%", "80%"],
        "current_density": [
            {"type": "total", "product": "C2+", "value": "100 mA cm-2"},
        ],
    }
    processed = process_raw_record(raw, stats=stats)
    assert processed is None
    assert stats.dropped_records_by_reason.get("co2rr_unwanted_truth_product", 0) == 1


def test_drop_record_if_no_metrics_left():
    stats = ProcessingStats()
    raw = {"id": "x", "metals": ["Pt"], "reaction_type": "HER", "overpotential": None}
    assert process_raw_record(raw, stats=stats) is None
    assert stats.dropped_records_by_reason.get("no_metrics_after_cleaning", 0) == 1


def test_drop_hor_record_if_exchange_current_density_unit_is_not_convertible():
    # We only keep absolute exchange_current_density values in mA cm^-2 for HOR.
    stats = ProcessingStats()
    raw = {
        "id": "y",
        "metals": ["Pt"],
        "reaction_type": "HOR",
        "exchange_current_density": "1 A g-1 Ir",
    }
    assert process_raw_record(raw, stats=stats) is None
    assert stats.dropped_records_by_reason.get("no_metrics_after_cleaning", 0) == 1
