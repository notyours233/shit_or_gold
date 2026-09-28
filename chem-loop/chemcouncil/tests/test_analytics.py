from __future__ import annotations

from pathlib import Path

import pytest

from chemcouncil.analytics import (
    RecommendationContext,
    aggregate_prediction_error_records_for_analytics,
    compute_prediction_error_records_multi_debug,
    load_rank_predictions,
)


def _write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _build_co2rr_rank_result(final_performance: str, *, metric_value: float = 2.5, metric_unit: str = "mA cm-2") -> dict:
    return {
        "ranking": [
            {
                "reaction_type": "CO2RR",
                "final_products": None,
                "final_performance": final_performance,
                "performance_evaluation": {
                    "reaction_type": "CO2RR",
                    "metric_name": "Partial current density",
                    "metric_value": metric_value,
                    "metric_unit": metric_unit,
                    "raw_metric_text": final_performance,
                },
            }
        ]
    }


def test_load_rank_predictions_parses_co2rr_fe_and_partial_current_density() -> None:
    rank_result = _build_co2rr_rank_result(
        "Reaction Type: CO2RR\nProducts: HCOOH\nPerformance Metrics: 85% FE, 20 mA/cm2 partial current density (Confidence: medium-low)",
        metric_value=20.0,
    )

    preds = load_rank_predictions(rank_result)

    assert preds["CO2RR"]["product"] == "HCOOH"
    assert preds["CO2RR"]["faradaic_efficiency"] == pytest.approx(85.0)
    assert preds["CO2RR"]["faradaic_efficiency_unit"] == "%"
    assert preds["CO2RR"]["partial_current_density"] == pytest.approx(20.0)
    assert preds["CO2RR"]["partial_current_density_unit"] == "mA cm-2"


def test_compute_prediction_error_records_multi_debug_counts_fe_and_partial_current_density_for_co2rr(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "feedback.csv",
        "\n".join(
            [
                "recommendation_job_id,reaction_type,metals,product,faradaic_efficiency,faradaic_efficiency_unit,partial_current_density,partial_current_density_unit,value,unit,condition",
                "rec-1,CO2RR,\"Ni(70%),Co(15%),Fe(10%),Cu(3%),Zn(2%)\",CO,30,%,1.5,mA cm-2,1.5,mA cm-2,",
            ]
        )
        + "\n",
    )
    rec_ctx = {
        "rec-1": RecommendationContext(
            recommendation_job_id="rec-1",
            recommendation_finished_at_utc="2026-03-19T00:00:00Z",
            components="Ni,Co,Fe,Cu,Zn",
            recommendation_rank_result=_build_co2rr_rank_result(
                "Reaction Type: CO2RR\nProducts: CO (highest FE)\nPerformance Metrics: FE(CO)=25% ; j_CO=2.5 mA/cm^2 (Confidence: low)",
                metric_value=2.5,
            ),
        )
    }

    records, debug = compute_prediction_error_records_multi_debug(
        update_job_id="update-1",
        update_finished_at_utc="2026-03-19T01:00:00Z",
        upload_csv_path=csv_path,
        recommendation_contexts=rec_ctx,
    )

    assert len(records) == 2
    by_metric = {record.metric_key: record for record in records}
    assert set(by_metric) == {"partial_current_density", "faradaic_efficiency"}
    assert by_metric["partial_current_density"].predicted_value == pytest.approx(2.5)
    assert by_metric["partial_current_density"].actual_value == pytest.approx(1.5)
    assert by_metric["partial_current_density"].rel_error == pytest.approx(2.0 / 3.0)
    assert by_metric["faradaic_efficiency"].predicted_value == pytest.approx(0.25)
    assert by_metric["faradaic_efficiency"].actual_value == pytest.approx(0.30)
    assert by_metric["faradaic_efficiency"].rel_error == pytest.approx(0.05 / 0.35)
    assert debug.csv_rows_total == 1
    assert debug.rows_scored == 2
    assert debug.rows_actual_parse_failed == 0
    assert debug.rows_prediction_missing == 0
    assert debug.rows_prediction_parse_failed == 0


def test_aggregate_prediction_error_records_for_analytics_combines_complete_co2rr_row(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "feedback.csv",
        "\n".join(
            [
                "recommendation_job_id,reaction_type,metals,product,faradaic_efficiency,faradaic_efficiency_unit,partial_current_density,partial_current_density_unit,value,unit,condition",
                "rec-1,CO2RR,\"Ni(70%),Co(15%),Fe(10%),Cu(3%),Zn(2%)\",CO,30,%,1.5,mA cm-2,1.5,mA cm-2,",
            ]
        )
        + "\n",
    )
    rec_ctx = {
        "rec-1": RecommendationContext(
            recommendation_job_id="rec-1",
            recommendation_finished_at_utc="2026-03-19T00:00:00Z",
            components="Ni,Co,Fe,Cu,Zn",
            recommendation_rank_result=_build_co2rr_rank_result(
                "Reaction Type: CO2RR\nProducts: CO (highest FE)\nPerformance Metrics: FE(CO)=25% ; j_CO=2.5 mA/cm^2 (Confidence: low)",
                metric_value=2.5,
            ),
        )
    }

    raw_records, _ = compute_prediction_error_records_multi_debug(
        update_job_id="update-1",
        update_finished_at_utc="2026-03-19T01:00:00Z",
        upload_csv_path=csv_path,
        recommendation_contexts=rec_ctx,
    )
    records = aggregate_prediction_error_records_for_analytics(raw_records)

    assert len(records) == 1
    assert records[0].metric_key == "co2rr_combined"
    assert records[0].predicted_value is None
    assert records[0].actual_value is None
    assert records[0].abs_error is None
    assert records[0].predicted_display == "j=2.5 mA cm-2\nFE=25%"
    assert records[0].actual_display == "j=1.5 mA cm-2\nFE=30%"
    assert records[0].abs_error_display == "|Δj|=1 mA cm-2\n|ΔFE|=5%"
    assert records[0].component_rel_errors is not None
    assert records[0].component_rel_errors["partial_current_density"] == pytest.approx(2.0 / 3.0)
    assert records[0].component_rel_errors["faradaic_efficiency"] == pytest.approx(0.05 / 0.35)
    assert records[0].rel_error == pytest.approx(((2.0 / 3.0) + (0.05 / 0.35)) / 2.0)


def test_compute_prediction_error_records_multi_debug_keeps_legacy_co2rr_csv_compatible(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "feedback_legacy.csv",
        "\n".join(
            [
                "recommendation_job_id,reaction_type,metals,product,value,unit,condition",
                "rec-1,CO2RR,\"Cu(50%),Ag(20%),Sn(15%),Bi(10%),In(5%)\",HCOOH,18,mA cm-2,",
            ]
        )
        + "\n",
    )
    rec_ctx = {
        "rec-1": RecommendationContext(
            recommendation_job_id="rec-1",
            recommendation_finished_at_utc="2026-03-19T00:00:00Z",
            components="Cu,Ag,Sn,Bi,In",
            recommendation_rank_result=_build_co2rr_rank_result(
                "Reaction Type: CO2RR\nProducts: HCOOH\nPerformance Metrics: 85% FE, 20 mA/cm2 partial current density (Confidence: medium-low)",
                metric_value=20.0,
            ),
        )
    }

    records, debug = compute_prediction_error_records_multi_debug(
        update_job_id="update-legacy",
        update_finished_at_utc="2026-03-19T01:00:00Z",
        upload_csv_path=csv_path,
        recommendation_contexts=rec_ctx,
    )

    assert len(records) == 1
    assert records[0].metric_key == "partial_current_density"
    assert records[0].predicted_value == pytest.approx(20.0)
    assert records[0].actual_value == pytest.approx(18.0)
    assert debug.rows_scored == 1


def test_material_name_feedback_uses_task_type_for_new_direction_analytics(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "material_feedback.csv",
        "\n".join(
            [
                "recommendation_job_id,material_name,task_type,value,unit,condition",
                "rec-material,CuO,photocatalytic_h2o2,18.5,%,420 nm",
            ]
        )
        + "\n",
    )
    rec_ctx = {
        "rec-material": RecommendationContext(
            recommendation_job_id="rec-material",
            recommendation_finished_at_utc="2026-07-30T00:00:00Z",
            components="",
            recommendation_rank_result={
                "ranking": [
                    {
                        "task_type": "photocatalytic_h2o2",
                        "performance_evaluation": {"metric_value": 20.0, "metric_unit": "%"},
                    }
                ]
            },
        )
    }

    records, debug = compute_prediction_error_records_multi_debug(
        update_job_id="update-material",
        update_finished_at_utc="2026-07-30T01:00:00Z",
        upload_csv_path=csv_path,
        recommendation_contexts=rec_ctx,
    )

    assert len(records) == 1
    assert records[0].reaction_type == "photocatalytic_h2o2"
    assert records[0].metric_key == "apparent_quantum_efficiency"
    assert records[0].predicted_value == pytest.approx(20.0)
    assert records[0].actual_value == pytest.approx(18.5)
    assert debug.rows_scored == 1
