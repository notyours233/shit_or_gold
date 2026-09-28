import importlib.util
import inspect
import json
from collections import defaultdict
from pathlib import Path

from ...config import EvalConfig
from ...db import EvaluationSample
from ...utils import FileUtils
from .base_llm_processor import BaseLLMJudgeProcesser

VERIFY_DIR = Path(__file__).parent.parent.parent / "practice" / "verify"


class TrainingFreeGRPOProcesser(BaseLLMJudgeProcesser):
    """Processer for training-free GRPO datasets."""

    name = "training_free_grpo"
    config: EvalConfig = None

    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)
        self.verify_func = self._load_verify_func()
        self.prompts = FileUtils.load_prompts("practice/processor.yaml")

    def preprocess_one(self, sample: EvaluationSample, recorder=None) -> EvaluationSample:
        """Preprocess a single sample with optional experience recorder.

        Args:
            sample: EvaluationSample to preprocess
            recorder: Optional TaskRecorder with experiences

        Returns:
            Updated EvaluationSample
        """
        # Chem-performance datasets normalize several units during preprocessing (see spec-bank):
        # - overpotential: canonical unit is mV (η@10 mA cm^-2 by convention for this dataset phase)
        # - other potential-like metrics: canonical unit is V
        # - exchange_current_density: canonical unit is mA cm^-2
        # - percent metrics: % -> fraction [0, 1]
        # Single-agent rollouts can stumble on this when retrieval returns paper-style units.
        problem = sample.raw_question
        if isinstance(sample.dataset, str) and sample.dataset.startswith(
            ("chem_performance", "material_performance_19")
        ):
            problem = (
                f"{problem}\n\n"
                "Unit conventions for this dataset (VERY IMPORTANT):\n"
                "- overpotential_10mAcm-2 means the overpotential (η) at 10 mA cm^-2.\n"
                "- potential_10mAcm-2 means the (over)potential at 10 mA cm^-2.\n"
                "- By convention, potential values correspond to 10 mA cm^-2 unless explicitly stated otherwise.\n"
                "- Any key containing 'overpotential' is in millivolts (mV). If evidence shows V, multiply by 1000.\n"
                "- Any key containing 'potential' BUT NOT 'overpotential' is in volts (V). If evidence shows mV, divide by 1000.\n"
                "- exchange_current_density is in mA cm^-2. If evidence shows A cm^-2, multiply by 1000.\n"
                "- partial_current_density is in mA cm^-2. If evidence shows A cm^-2, multiply by 1000.\n"
                "- mass_activity is in A mg^-1. If evidence shows mA mg^-1, divide by 1000.\n"
                "- faradaic_efficiency is a fraction in [0, 1] (NOT percent). If evidence shows %, divide by 100.\n"
                "Sanity checks: FE/yield/conversion should be <= 1; overpotential is typically < 2000 mV; if you output 0.3 for overpotential you likely forgot V->mV; if you output 300 for half_wave_potential/potential you likely forgot mV->V.\n"
            )

        # Experiences are distilled after grouped rollouts; this stage keeps the held-out question unchanged.
        augmented_question = problem
        sample.update(
            augmented_question=augmented_question,
        )
        return sample

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        """Judge a single sample using the loaded verify function."""
        if self.verify_func is None:
            # directly use the default LLM judging method
            return await super().judge_one(data)

        # Check if verify_func is async or sync and call accordingly
        if inspect.iscoroutinefunction(self.verify_func):
            res = await self.verify_func(sample=data, llm=self.judge_client)
        else:
            res = self.verify_func(sample=data, llm=self.judge_client)

        reward = res.get("reward", 0.0)
        reasoning = res.get("reasoning", None)
        data.update(
            judged_response="Correct" if reward == 1.0 else "Incorrect",
            correct=reward == 1.0,
            reward=reward,
            reasoning=reasoning,
        )
        return data

    def calculate_metrics(self, samples: list[EvaluationSample]) -> dict:
        """Calculate metrics from the judged data."""
        all_rewards = []
        problem_to_scores = defaultdict(list)
        num_tool_calls = []
        # calculate tool calls and rewards
        for sample in samples:
            all_rewards.append(sample.reward)
            problem_to_scores[sample.raw_question].append(sample.reward)
            if sample.trajectories:
                num_tool_calls.append(
                    len([each for each in json.loads(sample.trajectories)[0]["trajectory"] if each["role"] == "tool"])
                )
        problem_to_max_score = {problem: max(scores) for problem, scores in problem_to_scores.items()}
        max_K = max((len(scores) for scores in problem_to_scores.values()), default=0)
        stats = {
            f"Mean@{max_K}": sum(all_rewards) / len(all_rewards) if all_rewards else 0,
            f"Pass@{max_K}": sum(max_reward for max_reward in problem_to_max_score.values()) / len(problem_to_max_score)
            if problem_to_max_score
            else 0,
            "avg_tool_call": sum(num_tool_calls) / len(num_tool_calls) if num_tool_calls else 0,
        }
        return stats

    def _load_verify_func(self):
        """Load the verification function from the given path."""
        try:
            verify_path = str(VERIFY_DIR / self.config.verify_filename)
            spec = importlib.util.spec_from_file_location("verify_module", verify_path)
            verify_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verify_module)
            func = getattr(verify_module, self.config.verify_func_name)
        except Exception as e:
            print(
                f"Warning: Failed to load verification function '{self.config.verify_func_name}' from "
                f"'{self.config.verify_filename}': {e}"
            )
            func = None

        return func
