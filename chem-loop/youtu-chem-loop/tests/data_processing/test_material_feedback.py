import csv
import json
import subprocess
import sys
from pathlib import Path

from scripts.data.build_chem_performance_dataset import build_dataset_sample
from utu.data_processing.chem_performance.processor import process_raw_record
from utu.data_processing.material_feedback import build_material_description, canonical_task_type


def test_material_feedback_description_omits_absent_fields() -> None:
    assert build_material_description({"material_name": "CuO"}) == "材料是CuO。"


def test_material_feedback_accepts_material_name_without_elements() -> None:
    processed = process_raw_record(
        {
            "id": "feedback_1",
            "reaction_type": "HER",
            "task_type": "HER",
            "material_input": {"material_name": "CuO"},
            "overpotential": "180 mV",
        }
    )
    assert processed is not None
    assert processed["material_name"] == "CuO"
    assert "metals" not in processed
    assert "elements" not in processed
    assert processed["metrics_gt"] == {"overpotential_10mAcm-2": "180 mV"}


def test_material_feedback_dataset_sample_uses_19_direction_contract() -> None:
    record = {
        "id": "feedback_2",
        "reaction_type": "thermoelectric",
        "task_type": "thermoelectric",
        "material_name": "Bi2Te3",
        "precursors": ["Bi", "Te"],
        "feed_ratio": [2, 3],
        "preparation_method": "烧结法",
        "custom_prompt": "测试温度为 500 K。",
        "metrics_gt": {"figure_of_merit": "1.2"},
        "metrics_raw": {"figure_of_merit": "1.2"},
        "units": {"figure_of_merit": "dimensionless"},
        "source_file": "feedback.jsonl",
    }
    sample = build_dataset_sample(record, source="training_free_grpo", include_unit_hint=True)
    assert sample["meta"]["task_type"] == "thermoelectric"
    assert sample["meta"]["material_name"] == "Bi2Te3"
    assert "elements" not in sample["meta"]
    payload = sample["meta"]["input_json"]
    assert payload["material_description"].startswith("材料是Bi2Te3。")
    assert payload["custom_prompt"] == "测试温度为 500 K。"
    assert payload["metrics_to_predict"] == [{"key": "figure_of_merit", "unit_hint": "dimensionless"}]
    assert json.loads(sample["answer"]) == {"figure_of_merit": "1.2"}


def test_feedback_csv_material_only_round_trip(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = tmp_path / "material_feedback.csv"
    material_input = {
        "material_name": "MoS2负载CuO纳米颗粒",
        "precursors": ["(NH4)6Mo7O24", "Cu(NO3)2"],
        "feed_ratio": [1, 2],
        "preparation_method": "水热法",
        "custom_prompt": "使用 420 nm 光源。",
    }
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["material_name", "material_input_json", "task_type", "value", "unit", "condition"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "material_name": material_input["material_name"],
                "material_input_json": json.dumps(material_input, ensure_ascii=False),
                "task_type": "photocatalytic_h2o2",
                "value": "18.5",
                "unit": "%",
                "condition": "420 nm",
            }
        )

    processed_dir = tmp_path / "processed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.data.import_experimental_csv",
            "--csv_path",
            str(csv_path),
            "--output_dir",
            str(processed_dir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    processed_records = [json.loads(line) for line in (processed_dir / "material_feedback.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(processed_records) == 1
    processed = processed_records[0]
    assert processed["task_type"] == "photocatalytic_h2o2"
    assert processed["material_name"] == material_input["material_name"]
    assert "metals" not in processed
    assert processed["metrics_gt"] == {"apparent_quantum_efficiency": "18.5 %"}

    dataset_path = tmp_path / "feedback_dataset.jsonl"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.data.build_chem_performance_dataset",
            "--input_dir",
            str(processed_dir),
            "--output_file",
            str(dataset_path),
            "--include_unit_hint",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    sample = json.loads(dataset_path.read_text(encoding="utf-8").strip())
    assert sample["meta"]["task_type"] == "photocatalytic_h2o2"
    assert sample["meta"]["material_name"] == material_input["material_name"]
    assert sample["meta"]["input_json"]["custom_prompt"] == "使用 420 nm 光源。"
    assert sample["meta"]["input_json"]["metrics_to_predict"] == [
        {"key": "apparent_quantum_efficiency", "unit_hint": "%"}
    ]


def test_current_frontend_feedback_csv_accepts_direct_material_and_co2rr(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = tmp_path / "frontend_feedback.csv"
    fieldnames = [
        "recommendation_job_id",
        "material_serial_no",
        "material_name",
        "material_input_json",
        "elements",
        "task_type",
        "value",
        "unit",
        "product",
        "faradaic_efficiency",
        "faradaic_efficiency_unit",
        "partial_current_density",
        "partial_current_density_unit",
        "condition",
        "notes",
    ]
    material_input = {
        "material_serial_no": 17,
        "material_name": "MoS2负载CuO纳米颗粒",
        "precursors": ["钼酸钠", "硫脲", "硝酸铜"],
        "feed_ratio": "1:4:0.2",
        "preparation_method": "水热法",
        "elements": ["Mo", "S", "Cu", "O"],
        "custom_prompt": "CuO纳米颗粒均匀负载于MoS2片层表面。",
    }
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "material_serial_no": "17",
                "material_name": material_input["material_name"],
                "material_input_json": json.dumps(material_input, ensure_ascii=False),
                "elements": "Mo, S, Cu, O",
                "task_type": "conductivity",
                "value": "125000",
                "unit": "S/m",
                "condition": "298 K",
                "notes": "四探针测试",
            }
        )
        writer.writerow(
            {
                "material_serial_no": "17",
                "material_name": material_input["material_name"],
                "material_input_json": json.dumps(material_input, ensure_ascii=False),
                "elements": "Mo, S, Cu, O",
                "task_type": "CO2RR",
                "product": "CO",
                "faradaic_efficiency": "62",
                "faradaic_efficiency_unit": "%",
                "partial_current_density": "180",
                "partial_current_density_unit": "mA cm-2",
                "condition": "-0.8 V vs RHE",
            }
        )

    processed_dir = tmp_path / "processed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.data.import_experimental_csv",
            "--csv_path",
            str(csv_path),
            "--output_dir",
            str(processed_dir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    records = [
        json.loads(line)
        for line in (processed_dir / "frontend_feedback.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["task_type"] for record in records] == ["conductivity", "CO2RR"]
    assert records[0]["metrics_gt"] == {"conductivity": "125000 S/m"}
    assert records[1]["product"] == "CO"
    assert records[1]["metrics_gt"] == {
        "faradaic_efficiency": "0.62",
        "partial_current_density": "180 mA cm-2",
    }
    assert records[1]["material_name"] == material_input["material_name"]
    assert records[0]["material_serial_no"] == 17
    assert records[1]["material_serial_no"] == 17
    assert records[1]["custom_prompt"] == material_input["custom_prompt"]

    sample = build_dataset_sample(records[0], source="training_free_grpo", include_unit_hint=True)
    assert sample["meta"]["material_serial_no"] == 17
    assert sample["meta"]["material_input"]["material_serial_no"] == 17


def test_task_aliases_cover_new_and_legacy_directions() -> None:
    assert canonical_task_type("HZOR") == "HZOR"
    assert canonical_task_type("photocatalytic h2o2") == "photocatalytic_h2o2"
    assert canonical_task_type("糠醛加氢") == "furfural_hydrogenation"
