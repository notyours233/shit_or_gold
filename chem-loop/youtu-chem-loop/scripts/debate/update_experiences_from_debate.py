#!/usr/bin/env python3
"""Update an experience library using multi-agent debate traces (LangGraph JSON export).

This script is the first "closed-loop" integration point between:
  - multi-agent debate (proposals + critiques, including defeated proposals)
  - training-free GRPO style experience distillation (ExperienceUpdater prompts)

High-level idea
---------------
1) Parse debate JSON(s)
2) Convert each proposal into a pseudo-rollout (EvaluationSample) with:
   - raw_question: the proposal query
   - trajectories: the step list (ReAct-style)
   - reward: 1 for surviving proposals, 0 for defeated (optional: ignore withdrawn)
   - reasoning: aggregated *valid* critiques targeting that proposal
3) Run ExperienceUpdater to distill & merge experiences into an existing pool
4) Write a new agent YAML under configs/agents/practice/ with the updated experiences appended

Notes
-----
- This does NOT run rollouts; it only distills experiences from already-recorded debate traces.
- It *does* call the configured LLM to perform experience extraction/merging (network required).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

from utu.config import ConfigLoader
from utu.db import EvaluationSample
from utu.debate import load_langgraph_debate
from utu.practice.experience_updater import ExperienceUpdater
from utu.practice.utils import TaskRecorder


def _extract_experiences_from_instructions(instructions: str) -> dict[str, str]:
    """Parse an agent.instructions string and return {"0": "...", "1": "..."} experiences.

    Expected format in instructions:
      [G0]. Experience text...
      [G1]. Experience text...
    """

    if not isinstance(instructions, str) or not instructions.strip():
        return {}

    matches = list(re.finditer(r"^\s*\[G(\d+)\]\.\s*", instructions, flags=re.MULTILINE))
    if not matches:
        return {}

    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        gid = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(instructions)
        chunk = instructions[start:end].strip()
        # Normalize whitespace to one line; the updater prompts expect one experience per line.
        chunk = " ".join(chunk.split())
        if chunk:
            out[str(int(gid))] = chunk
    return out


def _load_seed_experiences(seed_agent_yaml: str | None) -> dict[str, str]:
    if not seed_agent_yaml:
        return {}
    p = Path(seed_agent_yaml)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"seed agent yaml must be a YAML mapping, got: {type(raw).__name__}")
    agent = raw.get("agent") or {}
    instr = agent.get("instructions") if isinstance(agent, dict) else None
    exps = _extract_experiences_from_instructions(instr or "")
    return exps


def _format_debate_pseudo_gt(debate: dict[str, Any]) -> str:
    """Return a compact, human-readable pseudo-ground-truth string for ExperienceUpdater.

    We intentionally avoid pretending this is real experimental GT; it is debate outcome only.
    """

    res = debate.get("result") or {}
    surv = res.get("surviving_proposals") or []
    defeated = res.get("defeated_proposals") or []
    lines = ["[Debate outcome (pseudo label; NOT experimental ground truth)]"]
    if surv:
        lines.append("Surviving proposals:")
        for p in surv:
            if not isinstance(p, dict):
                continue
            pid = p.get("proposal_id")
            claim = (p.get("claim") or "").strip()
            if pid and claim:
                lines.append(f"- ({pid}) {claim}")
    if defeated:
        lines.append("Defeated proposals:")
        for p in defeated:
            if not isinstance(p, dict):
                continue
            pid = p.get("proposal_id")
            claim = (p.get("claim") or "").strip()
            if pid and claim:
                lines.append(f"- ({pid}) {claim}")
    return "\n".join(lines).strip()


def _make_rollouts_from_debate(
    debate_path: str,
    *,
    include_withdrawn: bool,
) -> list[EvaluationSample]:
    d = load_langgraph_debate(debate_path)
    crit_by_target = d.critiques_by_target(valid_only=True)

    # Use the shared query from proposals as the "problem" for grouping.
    # (All proposals in a debate share the same query prompt.)
    query = None
    for p in d.proposals:
        if p.query:
            query = p.query
            break
    if not query:
        query = f"[Debate {d.debate_id or Path(debate_path).stem}] reaction_type={d.reaction_type} components={d.components}"

    # Provide a pseudo-GT summary for the prompts (explicitly NOT experimental GT).
    pseudo_gt = _format_debate_pseudo_gt(d.raw)

    rollouts: list[EvaluationSample] = []
    for p in d.proposals:
        if p.status == "withdrawn" and not include_withdrawn:
            continue

        # Reward is only used as a relative quality signal during distillation.
        # We treat "defeated" as 0 and "surviving" as 1.
        reward = 1.0 if p.status == "surviving" else 0.0

        critiques = crit_by_target.get(p.proposal_id) or []
        critique_lines: list[str] = []
        for c in critiques:
            ft = (c.flaw_type or "issue").strip()
            txt = (c.critique or "").strip()
            frm = (c.from_proposal_id or "").strip()
            prefix = f"- [{ft}]"
            if frm:
                prefix += f" from {frm}"
            if txt:
                critique_lines.append(f"{prefix}: {txt}")
        critique_text = "\n".join(critique_lines).strip() or "[No critique provided]"

        # Pack the trajectory in the shape expected by ExperienceUpdater:
        # it will read json.loads(item.trajectories)[0]["trajectory"].
        traj_payload = [
            {
                "trajectory": p.steps,
                # Best-effort "thinking" side-channel: store the final JSON answer text if present.
                "reasoning": p.final_answer or "",
                "meta": {
                    "debate_id": d.debate_id,
                    "proposal_id": p.proposal_id,
                    "proposal_status": p.status,
                    "agent_name": p.agent_name,
                    "reaction_type": d.reaction_type,
                    "components": d.components,
                    "trace_path": d.path,
                },
            }
        ]

        rollouts.append(
            EvaluationSample(
                dataset="debate_langgraph",
                dataset_index=None,
                source="debate_langgraph",
                raw_question=query,
                augmented_question=query,
                correct_answer=pseudo_gt,
                meta={
                    "debate_id": d.debate_id,
                    "proposal_id": p.proposal_id,
                    "proposal_status": p.status,
                    "agent_name": p.agent_name,
                    "reaction_type": d.reaction_type,
                    "components": d.components,
                    "trace_path": d.path,
                },
                trajectories=json.dumps(traj_payload, ensure_ascii=False),
                reward=reward,
                reasoning=critique_text,
                stage="judged",
                exp_id=f"debate_{d.debate_id or Path(debate_path).stem}",
            )
        )

    return rollouts


def _write_agent_yaml_with_experiences(
    *,
    base_agent_cfg,
    experiences: dict[str, str],
    output_path: Path,
) -> None:
    """Write a new agent YAML (Hydra-style) with the given experiences injected."""

    cfg_dict = base_agent_cfg.model_dump(exclude_none=True)
    instr = cfg_dict.get("agent", {}).get("instructions", "You are a helpful assistant.")

    exp_text = "\n\nWhen solving problems, you MUST first carefully read and understand the helpful instructions and experiences:\n\n"
    exp_text += "\n\n".join([f"[{k}]. {v}" for k, v in experiences.items()])
    cfg_dict["agent"]["instructions"] = str(instr) + exp_text

    # Keep only fields that make sense as a standalone agent config.
    remain_default_keys = ["type", "model", "agent", "toolkits", "env", "max_turns"]
    for key in list(cfg_dict.keys()):
        if key not in remain_default_keys:
            del cfg_dict[key]

    header = "# @package _global_\ndefaults:\n  - _self_\n\n"
    yaml_text = yaml.dump(cfg_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + yaml_text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Distill/update experiences from debate traces (LangGraph JSON).")
    ap.add_argument(
        "--config_name",
        default="chem_performance_single",
        help="Training-free GRPO config name (configs/practice/*.yaml). Used for objectives + model config.",
    )
    ap.add_argument(
        "--debate_json",
        action="append",
        required=True,
        help="Path to a LangGraph debate JSON export. Repeatable.",
    )
    ap.add_argument(
        "--seed_agent_yaml",
        default=None,
        help=(
            "Optional: existing agent YAML (with [G*] experiences) used to seed the experience pool. "
            "If omitted, start from an empty pool."
        ),
    )
    ap.add_argument(
        "--include_withdrawn",
        action="store_true",
        help="If set, include withdrawn proposals as negative rollouts (default: ignore withdrawn).",
    )
    ap.add_argument(
        "--num_experiences_per_query",
        type=int,
        default=2,
        help="Max experiences extracted per debate question (passed to ExperienceUpdater).",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Concurrency for experience distillation/update LLM calls (recommended 2-8 to avoid rate limits).",
    )
    ap.add_argument(
        "--output_agent_yaml",
        default=None,
        help=(
            "Output agent YAML path. Default: configs/agents/practice/debate_update_<ts>_agent.yaml "
            "(relative to repo root)."
        ),
    )
    ap.add_argument(
        "--report_path",
        default=None,
        help="Optional: write a JSON report (rollout counts, defeated IDs, extracted experiences).",
    )
    ap.add_argument(
        "--dry_run",
        action="store_true",
        help="If set, do NOT call any LLM. Only parse debate files and print a summary, then exit.",
    )
    ap.add_argument(
        "--dump_rollouts_path",
        default=None,
        help="Optional: dump the generated pseudo-rollouts to a JSON file for inspection (no LLM needed).",
    )
    args = ap.parse_args()

    cfg = ConfigLoader.load_training_free_grpo_config(args.config_name)
    base_agent_cfg = cfg.evaluation.agent

    seed_exps = _load_seed_experiences(args.seed_agent_yaml)
    recorder = TaskRecorder(experiment_name="debate_experience_update", experiences=seed_exps)

    rollouts: list[EvaluationSample] = []
    for p in args.debate_json:
        rollouts.extend(_make_rollouts_from_debate(p, include_withdrawn=bool(args.include_withdrawn)))

    # Basic summary (no network)
    summary = {
        "config_name": args.config_name,
        "debate_files": args.debate_json,
        "num_rollouts": len(rollouts),
        "seed_experiences": len(seed_exps),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not rollouts:
        raise SystemExit("No rollouts generated from debate files (nothing to distill).")

    if args.dump_rollouts_path:
        rp = Path(args.dump_rollouts_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            json.dumps(
                [
                    {
                        "raw_question": r.raw_question,
                        "reward": r.reward,
                        "meta": r.meta,
                        "reasoning": r.reasoning,
                        "trajectories": json.loads(r.trajectories) if r.trajectories else None,
                    }
                    for r in rollouts
                ],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Wrote rollouts dump: {rp}")

    if args.dry_run:
        # Print a compact status breakdown without requiring any network calls.
        by_status: dict[str, int] = {}
        for r in rollouts:
            st = str((r.meta or {}).get("proposal_status") or "unknown")
            by_status[st] = by_status.get(st, 0) + 1
        print("Dry-run status counts:", json.dumps(by_status, ensure_ascii=False))
        return

    updater = ExperienceUpdater(
        base_agent_cfg,
        agent_objective=cfg.practice.agent_objective,
        learning_objective=cfg.practice.learning_objective,
    )

    # Distill + merge. We keep given_ground_truth=True so reward signals remain visible to the LLM.
    # IMPORTANT: This is debate-derived pseudo-labels, not experimental ground truth.
    new_exps = updater.run(
        rollouts=rollouts,
        recorder=recorder,
        concurrency=int(args.concurrency),
        given_ground_truth=True,
        num_experiences=int(args.num_experiences_per_query),
    )

    # ExperienceUpdater.run is async; support both sync/async invocation.
    if hasattr(new_exps, "__await__"):
        import asyncio

        new_exps = asyncio.run(new_exps)  # type: ignore[assignment]

    # `new_exps` is the latest pool in recorder (keys become G0..).
    experiences = recorder.experiences or {}

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = (
        Path(args.output_agent_yaml)
        if args.output_agent_yaml
        else Path("configs/agents/practice") / f"debate_update_{ts}_agent.yaml"
    )
    _write_agent_yaml_with_experiences(base_agent_cfg=base_agent_cfg, experiences=experiences, output_path=out_path)
    print(f"Wrote updated agent config: {out_path}")

    if args.report_path:
        rp = Path(args.report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            json.dumps(
                {
                    **summary,
                    "output_agent_yaml": str(out_path),
                    "num_experiences_out": len(experiences),
                    "experiences": experiences,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Wrote report: {rp}")


if __name__ == "__main__":
    main()
