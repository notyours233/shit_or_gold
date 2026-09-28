"""MAD external engine adapter.

This module integrates the debate/rank runtime (folder: `MAD/` in this monorepo)
as an *external* engine for rollout.

Key design goals (per memory-bank/spec-bank):
- Keep the eval/verify contract unchanged: model output must contain `<think>` + `<answer>` blocks.
- Keep dependencies isolated: call MAD via a subprocess, so youtu-agent doesn't need MAD's deps.
- Return trajectories in the same shape as `AgentsUtils.get_trajectory_from_agent_result()` so the
  Training-Free GRPO experience distillation stage can reuse existing prompts.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import Field

from ..config.base_config import ConfigBaseModel
from ..utils.reasoning_extractor import stitch_think_and_answer, strip_answer_blocks


class MADEngineConfig(ConfigBaseModel):
    """Configuration for running MAD as an external subprocess."""

    mad_repo_path: str = Field(..., description="Path to MAD repo root (must contain `agents/`).")
    python_bin: str = Field(default_factory=lambda: sys.executable, description="Python executable to run MAD runner.")
    runner_path: str | None = Field(
        default=None,
        description="Path to the runner script. Defaults to `utu/external_engines/mad_runner.py` in this repo.",
    )
    timeout_s: int = Field(default=1800, description="Subprocess timeout in seconds.")
    max_react_steps: int = Field(default=6, description="Max ReAct steps for MAD engine.")
    agent_name: str = Field(default="mad_engine", description="Agent name stored in trajectories.")


@dataclass(frozen=True)
class ExternalEngineRunResult:
    """Minimal payload needed by BaseBenchmark.rollout_one()."""

    final_output: str
    trajectories: list[dict[str, Any]]


class MADEngineAdapter:
    """Adapter to call MAD from youtu-agent rollouts via a subprocess."""

    def __init__(self, config: MADEngineConfig):
        self.config = config

    def _resolve_runner_path(self) -> str:
        """Resolve the subprocess runner path.

        In a monorepo, pytest/scripts are often executed from the workspace root,
        so relative runner paths should be interpreted relative to the youtu-chem-loop
        repo root (the directory that contains `utu/`), not the current working dir.
        """

        if self.config.runner_path:
            p = Path(self.config.runner_path)
            if not p.is_absolute():
                # .../utu/external_engines/mad_engine.py -> repo root is two levels up.
                ytu_root = Path(__file__).resolve().parents[2]
                p = ytu_root / p
            return str(p)

        # Default: bundled runner next to this file.
        return str(Path(__file__).resolve().with_name("mad_runner.py"))

    async def run(
        self,
        *,
        question: str,
        meta: dict[str, Any] | None = None,
        masked_doc_ids: list[str] | None = None,
    ) -> ExternalEngineRunResult:
        """Run MAD engine and return a youtu-agent compatible result.

        Args:
            question: The full augmented question string (same as what we'd send to SimpleAgent).
            meta: Optional per-sample metadata (metals/reaction_type/doc_id/etc). Passed through to runner.
            masked_doc_ids: Optional doc-level masking list (DOI/doc_id). Used to prevent label leakage
                when the MAD engine performs literature retrieval via youtu-agent's chem_literature_db.
        """
        runner_path = self._resolve_runner_path()

        payload = {
            "question": question,
            "meta": meta or {},
            "masked_doc_ids": [str(x) for x in (masked_doc_ids or []) if str(x).strip()],
        }

        # Propagate caller env so the runner can read UTU_LLM_* values (and any other creds).
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        cmd = [
            self.config.python_bin,
            runner_path,
            "--mad_repo_path",
            self.config.mad_repo_path,
            "--max_react_steps",
            str(self.config.max_react_steps),
            "--agent_name",
            self.config.agent_name,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
                timeout=float(self.config.timeout_s),
            )
        except TimeoutError:
            proc.kill()
            raise TimeoutError(f"MAD engine timed out after {self.config.timeout_s}s") from None

        stdout = (stdout_b or b"").decode("utf-8", errors="replace").strip()
        stderr = (stderr_b or b"").decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            raise RuntimeError(
                "MAD engine subprocess failed "
                f"(returncode={proc.returncode}). stderr:\n{stderr or '[empty]'}\nstdout:\n{stdout or '[empty]'}"
            )

        try:
            out = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"MAD runner returned non-JSON stdout:\n{stdout[:2000]}") from e

        final_output = str(out.get("final_output") or out.get("content") or "")
        reasoning_text = out.get("reasoning")
        if isinstance(reasoning_text, str) and not reasoning_text.strip():
            reasoning_text = None
        elif reasoning_text is not None and not isinstance(reasoning_text, str):
            reasoning_text = str(reasoning_text)
        if isinstance(reasoning_text, str) and reasoning_text.strip():
            # Defensive: MAD's trajectory summary can embed the *original prompt*, which itself contains
            # `<answer>...</answer>` in the instructions template. If we stitch that into `<think>`,
            # verify will parse the wrong <answer> block and reward will be 0.
            sanitized = strip_answer_blocks(reasoning_text) or ""
            # Also remove stray literal tags like "<answer>" in the prompt template (even if unpaired),
            # otherwise they can pair with the *real* closing </answer> later and break parsing.
            sanitized = re.sub(r"<\s*/?\s*answer\s*>", "", sanitized, flags=re.IGNORECASE)
            reasoning_text = sanitized.strip() or None

        # Normalize MAD output into the verify contract.
        #
        # Newer chem-loop runs ask MAD to `conclude` with a STRICT JSON payload:
        #   {"think": "...", "answer": {...}}
        # We convert that into legacy <think>/<answer> blocks for compatibility with
        # existing verify + experience distillation prompts.
        normalized = self._normalize_structured_output(
            question=question,
            raw_final_output=final_output,
            reasoning_text=reasoning_text,
        )
        if normalized is not None:
            stitched = normalized
        else:
            # Legacy behavior: Ensure strict verify contract (<think> + <answer>) using only model-returned reasoning text.
            stitched = stitch_think_and_answer(final_output, reasoning_text)
            stitched = self._ensure_answer_block(question=question, stitched=stitched, raw_final_output=final_output)

        traj_messages = self._convert_to_chat_messages(question=question, out=out, stitched_final=stitched)
        trajectories = [
            {
                "agent": self.config.agent_name,
                "trajectory": traj_messages,
                # Side-channel: expose engine reasoning to experience distillation prompts.
                "reasoning": reasoning_text,
            }
        ]

        return ExternalEngineRunResult(final_output=stitched, trajectories=trajectories)

    def _normalize_structured_output(
        self,
        *,
        question: str,
        raw_final_output: str,
        reasoning_text: str | None,
    ) -> str | None:
        """Convert a structured JSON payload into legacy <think>/<answer> blocks.

        Expected structured shape (preferred):
          {"think": "<string>", "answer": {<metric_key>: <number>, ...}}

        Also supported:
          {"answer": {...}}  (think is optional)
          {<metric_key>: <number>, ...}  (legacy direct dict)
        """
        if not raw_final_output or not isinstance(raw_final_output, str):
            return None

        text = raw_final_output.strip()
        if not text:
            return None

        # Already in legacy format.
        if re.search(r"<answer>\s*.*?\s*</answer>", text, flags=re.IGNORECASE | re.DOTALL):
            return None

        input_obj = self._extract_input_json(question)
        expected_keys = self._extract_metric_keys(input_obj)

        # Best-effort: parse a JSON object embedded in the model output.
        obj = None
        if text.startswith("{"):
            try:
                obj = json.loads(text)
            except Exception:
                obj = None
        if obj is None:
            obj = self._extract_json_dict_from_text(text, expected_keys=[])

        if not isinstance(obj, dict) or not obj:
            return None

        think_payload = None
        answer_obj = None

        if isinstance(obj.get("answer"), dict) and obj.get("answer"):
            answer_obj = obj.get("answer")
            if isinstance(obj.get("think"), str) and obj.get("think").strip():
                think_payload = obj.get("think").strip()
        else:
            # If the object overlaps expected metric keys, treat it as the answer dict directly.
            if expected_keys and (set(obj.keys()) & set(expected_keys)):
                answer_obj = obj

        if not isinstance(answer_obj, dict) or not answer_obj:
            return None

        # Prefer explicit think from the structured payload; fall back to engine reasoning.
        if not think_payload:
            think_payload = reasoning_text.strip() if isinstance(reasoning_text, str) and reasoning_text.strip() else ""

        try:
            answer_json = json.dumps(answer_obj, ensure_ascii=False)
        except Exception:
            return None

        think_block = f"<think>\n{think_payload}\n</think>" if think_payload else "<think>\n</think>"
        answer_block = f"<answer>\n{answer_json}\n</answer>"
        return f"{think_block}\n{answer_block}"

    def _ensure_answer_block(self, *, question: str, stitched: str, raw_final_output: str) -> str:
        """Best-effort ensure we have a valid `<answer>...</answer>` block.

        The chem verify function is strict and will return reward=0 if `<answer>` is missing.

        Important: we do NOT invent values. We only:
        - wrap an existing JSON dict (if present) into `<answer>...</answer>`
        - OR (single-metric only) extract the last numeric literal from the model text and wrap it.
        """

        if re.search(r"<answer>\s*.*?\s*</answer>", stitched, flags=re.IGNORECASE | re.DOTALL):
            return stitched

        input_obj = self._extract_input_json(question)
        expected_keys = self._extract_metric_keys(input_obj)

        # 1) If the model already output a JSON dict (but forgot <answer> tags), wrap it.
        parsed = self._extract_json_dict_from_text(raw_final_output, expected_keys) or self._extract_json_dict_from_text(
            stitched, expected_keys
        )
        if parsed is not None:
            answer_block = f"<answer>\n{json.dumps(parsed, ensure_ascii=False)}\n</answer>"
            think_block = self._extract_think_block(stitched)
            if think_block:
                return f"{think_block}\n{answer_block}"
            # Fallback: no think (should be rare for MAD engine), keep original stitched prefix.
            return f"{stitched.rstrip()}\n{answer_block}"

        # 2) Single-metric fallback: extract a numeric literal and wrap into JSON dict.
        if len(expected_keys) == 1:
            value = self._extract_last_number(raw_final_output) or self._extract_last_number(stitched)
            if value is not None:
                answer_block = f"<answer>\n{json.dumps({expected_keys[0]: value}, ensure_ascii=False)}\n</answer>"
                think_block = self._extract_think_block(stitched)
                if think_block:
                    return f"{think_block}\n{answer_block}"
                return f"{stitched.rstrip()}\n{answer_block}"

        # 3) Multi-metric fallback: if the model mentioned metric keys in text, extract numbers after each key.
        if len(expected_keys) > 1:
            extracted: dict[str, float] = {}
            for k in expected_keys:
                v = self._extract_number_after_key(raw_final_output, k)
                if v is not None:
                    extracted[k] = v
            if extracted:
                answer_block = f"<answer>\n{json.dumps(extracted, ensure_ascii=False)}\n</answer>"
                think_block = self._extract_think_block(stitched)
                if think_block:
                    return f"{think_block}\n{answer_block}"
                return f"{stitched.rstrip()}\n{answer_block}"

        return stitched

    @staticmethod
    def _extract_think_block(text: str) -> str | None:
        m = re.search(r"(<think>\s*.*?\s*</think>)", text, flags=re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_last_number(text: str) -> float | None:
        if not text or not isinstance(text, str):
            return None
        # A conservative "float literal" matcher; we pick the last occurrence.
        nums = re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text)
        if not nums:
            return None
        try:
            return float(nums[-1])
        except Exception:
            return None

    @staticmethod
    def _extract_number_after_key(text: str, key: str) -> float | None:
        if not text or not isinstance(text, str) or not key:
            return None
        # Look for patterns like:
        #   overpotential_10mAcm-2: 0.28
        #   exchange_current_density = 0.65
        pattern = re.compile(
            rf"{re.escape(key)}\s*[:=]?\s*[^0-9+-]*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
            flags=re.IGNORECASE,
        )
        m = pattern.search(text)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    @staticmethod
    def _extract_metric_keys(input_obj: dict[str, Any] | None) -> list[str]:
        if not isinstance(input_obj, dict):
            return []
        mtp = input_obj.get("metrics_to_predict")
        if not isinstance(mtp, list):
            return []
        keys: list[str] = []
        for item in mtp:
            if isinstance(item, str) and item.strip():
                keys.append(item.strip())
            elif isinstance(item, dict):
                k = item.get("key")
                if isinstance(k, str) and k.strip():
                    keys.append(k.strip())
        return keys

    @staticmethod
    def _extract_input_json(question: str) -> dict[str, Any] | None:
        """Extract the INPUT_JSON object from the augmented question text (best effort)."""
        if not question or not isinstance(question, str):
            return None
        marker = "INPUT_JSON"
        idx = question.find(marker)
        if idx < 0:
            return None
        brace_start = question.find("{", idx)
        if brace_start < 0:
            return None

        end = MADEngineAdapter._find_matching_brace(question, brace_start)
        if end is None:
            return None
        raw = question[brace_start : end + 1]
        try:
            obj = json.loads(raw)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None

    @staticmethod
    def _find_matching_brace(text: str, start: int) -> int | None:
        """Find the matching '}' for the '{' at `start` (handles strings/escapes)."""
        if start < 0 or start >= len(text) or text[start] != "{":
            return None
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == "\"":
                    in_str = False
                continue

            if ch == "\"":
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        return None

    @staticmethod
    def _extract_json_dict_from_text(text: str, expected_keys: list[str]) -> dict[str, Any] | None:
        """Find a JSON dict inside `text` (best effort) and return it.

        If `expected_keys` is non-empty, prefer dicts that overlap with expected metric keys.
        """
        if not text or not isinstance(text, str):
            return None

        expected = set(expected_keys or [])
        best_obj: dict[str, Any] | None = None
        best_overlap = -1
        best_pos = -1

        # Scan for JSON objects by locating '{' and finding its matching '}'.
        for pos in (m.start() for m in re.finditer(r"\{", text)):
            end = MADEngineAdapter._find_matching_brace(text, pos)
            if end is None:
                continue
            raw = text[pos : end + 1]
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if not isinstance(obj, dict) or not obj:
                continue

            if expected:
                overlap = len(set(obj.keys()) & expected)
                if overlap <= 0:
                    continue
            else:
                overlap = 0

            # Choose max overlap; break ties by later occurrence (often closer to final answer).
            if overlap > best_overlap or (overlap == best_overlap and pos > best_pos):
                best_obj = obj
                best_overlap = overlap
                best_pos = pos

        return best_obj

    def _convert_to_chat_messages(self, *, question: str, out: dict[str, Any], stitched_final: str) -> list[dict]:
        """Convert MAD runner output into a simplified OpenAI chat-style message list.

        The ExperienceUpdater expects `trajectory` to be a list of `{role, content}` objects.
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]

        traj = out.get("trajectory")
        steps = None
        if isinstance(traj, dict):
            steps = traj.get("steps")

        # Best-effort mapping from MAD ReAct steps into a chat transcript.
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue

                thought = step.get("thought")
                if isinstance(thought, str) and thought.strip():
                    messages.append({"role": "assistant", "content": thought.strip()})

                tool_calls = step.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    for call in tool_calls:
                        if not isinstance(call, dict):
                            continue
                        tool_name = str(call.get("tool_name") or "").strip() or "tool"
                        tool_args = call.get("tool_args")
                        try:
                            args_str = json.dumps(tool_args or {}, ensure_ascii=False)
                        except Exception:
                            args_str = str(tool_args)
                        messages.append({"role": "assistant", "content": f"{tool_name}({args_str})"})
                        obs = call.get("observation")
                        if obs is None:
                            obs = ""
                        messages.append({"role": "tool", "content": str(obs)})
                else:
                    # Older/simplified shape: represent single action/observation.
                    action = step.get("action")
                    action_input = step.get("action_input")
                    if action:
                        try:
                            a_in = json.dumps(action_input or {}, ensure_ascii=False)
                        except Exception:
                            a_in = str(action_input)
                        messages.append({"role": "assistant", "content": f"{action}({a_in})"})
                    obs = step.get("observation")
                    if obs:
                        messages.append({"role": "tool", "content": str(obs)})

        messages.append({"role": "assistant", "content": stitched_final})
        return messages
