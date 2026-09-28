#!/usr/bin/env python3
"""Update experiences using recommendation traces aligned to experimental feedback.

This differs from raw debate-trace distillation:
- it only uses trajectories that can be aligned to a real experimental feedback row
- each rollout is labeled with the actual experimental value
- the critique emphasizes the prediction-vs-ground-truth error, so the extracted
  experiences focus on reducing future numeric prediction error
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utu.config import ConfigLoader
from utu.db import EvaluationSample
from utu.debate import LangGraphDebate, Proposal, load_langgraph_debate
from utu.practice.experience_updater import ExperienceUpdater
from utu.practice.utils import TaskRecorder


_EXPERIENCE_BLOCK_RE = re.compile(r"^\s*\[G(\d+)\]\.\s*", flags=re.MULTILINE)
LAB_SAMPLE_PROTOCOL_ID = "SWCNT-COOH_4xMetal_100C_evap_900C_Ar_2h"
LAB_SAMPLE_FORM = "SWCNT-supported metal/oxide nanoparticle composite"
LAB_SAMPLE_PROTOCOL_TEXT = (
    f"LAB_PROTOCOL: SOURCE=lab_feedback; SAMPLE_PROTOCOL={LAB_SAMPLE_PROTOCOL_ID}; "
    f"SAMPLE_FORM={LAB_SAMPLE_FORM}; input components are metal ion species/ratios only; "
    "spectator ions from precursor salts are not target composition metals; "
    "carboxylated single-walled carbon nanotubes (SWCNT-COOH) are added at 4 times the total metal mass; "
    "the mixed aqueous/organic precursor solution is stirred and heated at 100 C until solvent evaporation; "
    "the dried mixture is annealed under Ar at 900 C for 2 h and cooled to room temperature; "
    "interpret lab feedback as this final annealed SWCNT-supported composite, not as dense bulk alloy, pure foil, unsupported oxide powder, or single crystal."
)
LAB_FEEDBACK_LEARNING_OBJECTIVE_SUFFIX = (
    "\n\nLab-feedback protocol requirement:\n"
    f"- For rollouts whose source is feedback_alignment/lab feedback, distill cards under SAMPLE_PROTOCOL={LAB_SAMPLE_PROTOCOL_ID}.\n"
    "- Every such card should explicitly include SOURCE=lab_feedback and "
    f"SAMPLE_PROTOCOL={LAB_SAMPLE_PROTOCOL_ID}; include SAMPLE_FORM={LAB_SAMPLE_FORM} when space allows.\n"
    "- Do not merge these lab-protocol anchors into generic literature-derived experiences unless the sample preparation/support clearly matches.\n"
    "- When a recommendation used bulk alloy, pure metal, unsupported oxide, single-crystal, or differently annealed literature evidence, encode that as a preparation/support mismatch and a correction heuristic.\n"
)


def _extract_experiences_from_instructions(instructions: str) -> dict[str, str]:
    if not isinstance(instructions, str) or not instructions.strip():
        return {}

    matches = list(_EXPERIENCE_BLOCK_RE.finditer(instructions))
    if not matches:
        return {}

    out: dict[str, str] = {}
    for idx, match in enumerate(matches):
        gid = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(instructions)
        chunk = " ".join(instructions[start:end].strip().split())
        if chunk:
            out[str(int(gid))] = chunk
    return out


def _load_seed_experiences(seed_agent_yaml: str | None) -> dict[str, str]:
    if not seed_agent_yaml:
        return {}
    raw = yaml.safe_load(Path(seed_agent_yaml).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"seed agent yaml must be a YAML mapping, got: {type(raw).__name__}")
    agent = raw.get("agent") or {}
    instructions = agent.get("instructions") if isinstance(agent, dict) else None
    return _extract_experiences_from_instructions(str(instructions or ""))


def _write_agent_yaml_with_experiences(*, base_agent_cfg, experiences: dict[str, str], output_path: Path) -> None:
    cfg_dict = base_agent_cfg.model_dump(exclude_none=True)
    instructions = cfg_dict.get("agent", {}).get("instructions", "You are a helpful assistant.")

    exp_text = "\n\nWhen solving problems, you MUST first carefully read and understand the helpful instructions and experiences:\n\n"
    exp_text += "\n\n".join([f"[{k}]. {v}" for k, v in experiences.items()])
    cfg_dict["agent"]["instructions"] = str(instructions) + exp_text

    keep_keys = ["type", "model", "agent", "toolkits", "env", "max_turns"]
    for key in list(cfg_dict.keys()):
        if key not in keep_keys:
            del cfg_dict[key]

    header = "# @package _global_\ndefaults:\n  - _self_\n\n"
    yaml_text = yaml.dump(cfg_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + yaml_text, encoding="utf-8")


def _select_focus_proposal(debate: LangGraphDebate) -> Proposal | None:
    result = debate.raw.get("result") if isinstance(debate.raw, dict) else {}
    winner_id = result.get("winner_proposal_id") if isinstance(result, dict) else None
    if isinstance(winner_id, str) and winner_id.strip():
        for proposal in debate.proposals:
            if proposal.proposal_id == winner_id.strip():
                return proposal

    surviving = [proposal for proposal in debate.proposals if proposal.status == "surviving"]
    if surviving:
        return surviving[0]
    if debate.proposals:
        return debate.proposals[0]
    return None


def _format_number(value: Any, digits: int = 6) -> str:
    try:
        num = float(value)
    except Exception:
        return str(value)
    if not math.isfinite(num):
        return str(value)
    return f"{num:.{digits}g}"


def _direction_text(predicted: float, actual: float) -> str:
    if predicted > actual:
        return "predicted higher than actual"
    if predicted < actual:
        return "predicted lower than actual"
    return "predicted exactly the same as actual"


def _build_ground_truth_text(example: dict[str, Any]) -> str:
    lines = [
        "[Experimental ground truth from lab feedback]",
        f"Source: lab_feedback",
        f"Sample Protocol: {LAB_SAMPLE_PROTOCOL_ID}",
        f"Sample Form: {LAB_SAMPLE_FORM}",
        LAB_SAMPLE_PROTOCOL_TEXT,
        f"Reaction Type: {example['reaction_type']}",
        f"Components: {example['components']}",
        f"Target Metric: {example['metric_key']}",
        f"Actual Value: {_format_number(example['actual_value'])} {example['unit']}",
        f"System Predicted Value: {_format_number(example['predicted_value'])} {example['unit']}",
        f"Absolute Error: {_format_number(example['abs_error'])} {example['unit']}",
        f"Relative Error: {_format_number(example['rel_error'], digits=4)}",
        f"Prediction Direction: {_direction_text(float(example['predicted_value']), float(example['actual_value']))}",
    ]
    condition = str(example.get("condition") or "").strip()
    if condition:
        lines.append(f"Condition: {condition}")

    actual_product = str(example.get("actual_product") or "").strip()
    predicted_product = str(example.get("predicted_product") or "").strip()
    actual_fe = example.get("actual_faradaic_efficiency")
    predicted_fe = example.get("predicted_faradaic_efficiency")
    if actual_product:
        lines.append(f"Actual Product: {actual_product}")
    if predicted_product:
        lines.append(f"Predicted Product: {predicted_product}")
    if actual_product and predicted_product:
        lines.append(f"Product Match: {'yes' if actual_product == predicted_product else 'no'}")
    if actual_fe is not None:
        lines.append(f"Actual Faradaic Efficiency: {_format_number(float(actual_fe) * 100.0, digits=4)} %")
    if predicted_fe is not None:
        lines.append(f"Predicted Faradaic Efficiency: {_format_number(float(predicted_fe) * 100.0, digits=4)} %")
    return "\n".join(lines)


def _build_critique_text(example: dict[str, Any], debate: LangGraphDebate, proposal: Proposal) -> str:
    lines = [
        "[Error-aware critique for experience distillation]",
        (
            f"LAB_PROTOCOL_CONTEXT: SOURCE=lab_feedback; SAMPLE_PROTOCOL={LAB_SAMPLE_PROTOCOL_ID}; "
            f"SAMPLE_FORM={LAB_SAMPLE_FORM}. Distill experiences for this lab preparation protocol, "
            "not for generic literature samples."
        ),
        (
            "The goal is not to preserve the original recommendation narrative as-is. "
            "The goal is to compare the prediction path against the real experimental outcome and distill experiences "
            "that reduce future prediction error."
        ),
        (
            f"For this aligned example, the system predicted {_format_number(example['predicted_value'])} {example['unit']}, "
            f"but the actual lab value was {_format_number(example['actual_value'])} {example['unit']} "
            f"(relative error={_format_number(example['rel_error'], digits=4)}; {_direction_text(float(example['predicted_value']), float(example['actual_value']))})."
        ),
    ]

    final_performance = str(example.get("final_performance") or "").strip()
    if final_performance:
        lines.extend(["", "[Recommendation summary that produced the prediction]", final_performance])

    if proposal.claim:
        lines.extend(["", "[Focus proposal claim]", proposal.claim])

    critiques = debate.critiques_by_target(valid_only=True).get(proposal.proposal_id) or []
    if critiques:
        lines.append("")
        lines.append("[Debate critiques targeting the selected proposal]")
        for critique in critiques:
            flaw_type = str(critique.flaw_type or "issue").strip() or "issue"
            critique_text = str(critique.critique or "").strip()
            from_proposal_id = str(critique.from_proposal_id or "").strip()
            prefix = f"- [{flaw_type}]"
            if from_proposal_id:
                prefix += f" from {from_proposal_id}"
            if critique_text:
                lines.append(f"{prefix}: {critique_text}")

    actual_product = str(example.get("actual_product") or "").strip()
    predicted_product = str(example.get("predicted_product") or "").strip()
    actual_fe = example.get("actual_faradaic_efficiency")
    predicted_fe = example.get("predicted_faradaic_efficiency")
    if actual_product and predicted_product and actual_product != predicted_product:
        lines.extend(
            [
                "",
                "[CO2RR product mismatch]",
                (
                    f"The recommendation trajectory pointed to product={predicted_product}, "
                    f"but the experimental feedback reported product={actual_product}. "
                    "Distill product-discriminating chemistry cues instead of only numeric heuristics."
                ),
            ]
        )
    if actual_fe is not None and predicted_fe is not None:
        lines.extend(
            [
                "",
                "[CO2RR Faradaic-efficiency alignment]",
                (
                    f"The recommendation implied FE={_format_number(float(predicted_fe) * 100.0, digits=4)} %, "
                    f"while the lab feedback reported FE={_format_number(float(actual_fe) * 100.0, digits=4)} %. "
                    "Distill selectivity-correcting cues together with the product choice."
                ),
            ]
        )

    return "\n".join(lines).strip()


def _reward_from_example(example: dict[str, Any]) -> float:
    rel_error = float(example.get("rel_error") or 0.0)
    if rel_error <= 0.02:
        return 1.0
    score = math.exp(-rel_error)
    return max(0.05, min(0.95, float(score)))


def _make_rollout_from_example(example: dict[str, Any]) -> EvaluationSample | None:
    debate = load_langgraph_debate(example["trace_path"])
    proposal = _select_focus_proposal(debate)
    if proposal is None or not proposal.steps:
        return None

    question = proposal.query or (
        f"Reaction Type: {example['reaction_type']}\n"
        f"Components: {example['components']}\n"
        f"Target Metric: {example['metric_key']}\n"
        f"[Feedback Context] recommendation_job_id={example['recommendation_job_id']} csv_row_index={example['csv_row_index']}"
    )
    question = f"{question.rstrip()}\n\n{LAB_SAMPLE_PROTOCOL_TEXT}"
    reward = _reward_from_example(example)

    traj_payload = [
        {
            "trajectory": proposal.steps,
            "reasoning": proposal.final_answer or proposal.claim or example.get("final_performance") or "",
            "meta": {
                "recommendation_job_id": example["recommendation_job_id"],
                "csv_row_index": example["csv_row_index"],
                "reaction_type": example["reaction_type"],
                "metric_key": example["metric_key"],
                "trace_path": example["trace_path"],
                "proposal_id": proposal.proposal_id,
                "proposal_status": proposal.status,
                "source": "lab_feedback",
                "sample_protocol": LAB_SAMPLE_PROTOCOL_ID,
                "sample_form": LAB_SAMPLE_FORM,
            },
        }
    ]

    return EvaluationSample(
        dataset="feedback_alignment",
        dataset_index=None,
        source="feedback_alignment",
        raw_question=question,
        augmented_question=question,
        correct_answer=_build_ground_truth_text(example),
        meta={
            "update_job_id": example["update_job_id"],
            "csv_row_index": example["csv_row_index"],
            "recommendation_job_id": example["recommendation_job_id"],
            "reaction_type": example["reaction_type"],
            "metric_key": example["metric_key"],
            "unit": example["unit"],
            "predicted_value": example["predicted_value"],
            "actual_value": example["actual_value"],
            "rel_error": example["rel_error"],
            "trace_path": example["trace_path"],
            "proposal_id": proposal.proposal_id,
            "proposal_status": proposal.status,
            "source": "lab_feedback",
            "sample_protocol": LAB_SAMPLE_PROTOCOL_ID,
            "sample_form": LAB_SAMPLE_FORM,
        },
        trajectories=json.dumps(traj_payload, ensure_ascii=False),
        reward=reward,
        reasoning=_build_critique_text(example, debate, proposal),
        stage="judged",
        exp_id=f"feedback_alignment_{example['update_job_id']}",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Distill experiences from recommendation traces aligned with lab feedback.")
    ap.add_argument("--config_name", default="chem_performance_single")
    ap.add_argument(
        "--input_json",
        action="append",
        required=True,
        help="JSON file containing a list of feedback-trace alignment examples. Repeatable.",
    )
    ap.add_argument("--seed_agent_yaml", default=None)
    ap.add_argument("--num_experiences_per_query", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--output_agent_yaml", default=None)
    ap.add_argument("--report_path", default=None)
    ap.add_argument("--dump_rollouts_path", default=None)
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    cfg = ConfigLoader.load_training_free_grpo_config(args.config_name)
    base_agent_cfg = cfg.evaluation.agent

    seed_experiences = _load_seed_experiences(args.seed_agent_yaml)
    recorder = TaskRecorder(experiment_name="feedback_alignment_experience_update", experiences=seed_experiences)

    examples: list[dict[str, Any]] = []
    for path_str in args.input_json:
        payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            examples.extend([item for item in payload if isinstance(item, dict)])
        else:
            raise ValueError(f"--input_json expects a JSON list, got {type(payload).__name__}: {path_str}")

    rollouts: list[EvaluationSample] = []
    skipped_examples = 0
    for example in examples:
        try:
            rollout = _make_rollout_from_example(example)
        except Exception:
            rollout = None
        if rollout is None:
            skipped_examples += 1
            continue
        rollouts.append(rollout)

    summary = {
        "config_name": args.config_name,
        "input_json": args.input_json,
        "num_examples": len(examples),
        "num_rollouts": len(rollouts),
        "skipped_examples": skipped_examples,
        "seed_experiences": len(seed_experiences),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not rollouts:
        raise SystemExit("No aligned feedback rollouts generated (nothing to distill).")

    if args.dump_rollouts_path:
        dump_path = Path(args.dump_rollouts_path)
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in rollouts], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.dry_run:
        return

    os.environ.setdefault("UTU_EXPERIENCE_BATCH_UPDATE_MODE", "direct")

    updater = ExperienceUpdater(
        cfg.evaluation.agent,
        agent_objective=cfg.practice.agent_objective,
        learning_objective=str(cfg.practice.learning_objective or "") + LAB_FEEDBACK_LEARNING_OBJECTIVE_SUFFIX,
    )

    t0 = time.time()
    awaitable = updater.run(
        rollouts=rollouts,
        recorder=recorder,
        concurrency=max(1, int(args.concurrency)),
        given_ground_truth=True,
        num_experiences=max(1, int(args.num_experiences_per_query)),
    )
    import asyncio

    asyncio.run(awaitable)
    elapsed = time.time() - t0

    experiences = recorder.experiences or {}
    output_path = (
        Path(args.output_agent_yaml)
        if args.output_agent_yaml
        else Path("configs/agents/practice") / f"feedback_alignment_update_{int(time.time())}_agent.yaml"
    )
    _write_agent_yaml_with_experiences(base_agent_cfg=base_agent_cfg, experiences=experiences, output_path=output_path)

    report = {
        **summary,
        "output_agent_yaml": str(output_path),
        "num_experiences_final": len(experiences),
        "elapsed_sec": elapsed,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.report_path:
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
