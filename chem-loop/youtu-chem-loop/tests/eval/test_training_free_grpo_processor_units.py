from utu.config import ConfigLoader
from utu.db import EvaluationSample
from utu.eval.processer import TrainingFreeGRPOProcesser


def test_training_free_grpo_processor_injects_unit_conventions_for_chem_performance() -> None:
    config = ConfigLoader.load_eval_config("chem/chem_performance_mad")
    processer = TrainingFreeGRPOProcesser(config)

    sample = EvaluationSample(dataset="chem_performance_v2_350_noher_co2rr", raw_question="Q")
    processer.preprocess_one(sample, recorder=None)

    assert sample.augmented_question is not None
    assert "Unit conventions for this dataset" in sample.augmented_question
    assert "divide by 1000" in sample.augmented_question
    assert "multiply by 1000" in sample.augmented_question
    assert "overpotential" in sample.augmented_question


def test_training_free_grpo_processor_injects_units_for_material_performance_19() -> None:
    config = ConfigLoader.load_eval_config("chem/chem_performance_single")
    processer = TrainingFreeGRPOProcesser(config)

    sample = EvaluationSample(dataset="material_performance_19_hp_train_s3_v3_seed20260803", raw_question="Q")
    processer.preprocess_one(sample, recorder=None)

    assert sample.augmented_question is not None
    assert "Unit conventions for this dataset" in sample.augmented_question
    assert "faradaic_efficiency is a fraction" in sample.augmented_question


def test_training_free_grpo_processor_does_not_inject_unit_conventions_for_other_datasets() -> None:
    config = ConfigLoader.load_eval_config("chem/chem_performance_mad")
    processer = TrainingFreeGRPOProcesser(config)

    sample = EvaluationSample(dataset="gaia", raw_question="Q")
    processer.preprocess_one(sample, recorder=None)

    assert sample.augmented_question is not None
    assert "Unit conventions for this dataset" not in sample.augmented_question
