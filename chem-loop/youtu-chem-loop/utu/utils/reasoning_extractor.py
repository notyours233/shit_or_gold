"""Helpers to extract and reuse "thinking mode" reasoning fields.

Some OpenAI-compatible providers (including Aliyun DashScope compatible-mode with DeepSeek thinking)
return the chain-of-thought in a *separate* field (e.g. `reasoning_content`) rather than in the
assistant `content`.

The openai-agents SDK converts that `reasoning_content` into a Responses-style output item:
  type == "reasoning"
  summary[0].text contains the reasoning text

This module provides best-effort extraction so downstream code can:
- stitch `<think>...</think>` into `EvaluationSample.response` (to satisfy verify contract)
- persist reasoning alongside trajectories for experience distillation
"""

from __future__ import annotations

import re
from typing import Any


_ANSWER_BLOCK_RE = re.compile(r"<answer>\s*.*?\s*</answer>", flags=re.IGNORECASE | re.DOTALL)


def _extract_reasoning_text_from_item(item: Any) -> str | None:
    """Return reasoning text from a single output item (best effort)."""
    if item is None:
        return None

    # Pydantic objects (preferred path)
    item_type = getattr(item, "type", None)
    if item_type == "reasoning":
        summary = getattr(item, "summary", None)
        if isinstance(summary, list) and summary:
            first = summary[0]
            text = getattr(first, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()

        # Fallback: some providers may populate `content` instead of `summary`.
        content = getattr(item, "content", None)
        if isinstance(content, list):
            parts: list[str] = []
            for p in content:
                t = getattr(p, "text", None)
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
            if parts:
                return "\n".join(parts)

        return None

    # Dict path (defensive)
    if isinstance(item, dict) and item.get("type") == "reasoning":
        summary = item.get("summary")
        if isinstance(summary, list) and summary:
            first = summary[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None

    return None


def extract_reasoning_text_from_raw_responses(raw_responses: Any) -> str | None:
    """Extract reasoning text from a RunResult.raw_responses list (best effort).

    Returns:
        A single string (joined with blank lines) or None if no reasoning was found.
    """
    if not raw_responses:
        return None

    chunks: list[str] = []
    for model_resp in raw_responses:
        output_items = getattr(model_resp, "output", None)
        if not isinstance(output_items, list):
            continue
        for item in output_items:
            text = _extract_reasoning_text_from_item(item)
            if text:
                chunks.append(text)

    if not chunks:
        return None

    # Deduplicate exact repeats while keeping order (some providers may echo the same summary).
    uniq: list[str] = []
    seen: set[str] = set()
    for c in chunks:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return "\n\n".join(uniq)


def extract_answer_block(text: str | None) -> str | None:
    """Extract the first full <answer>...</answer> block from text, if present."""
    if not text or not isinstance(text, str):
        return None
    m = _ANSWER_BLOCK_RE.search(text)
    return m.group(0).strip() if m else None


def strip_answer_blocks(text: str) -> str:
    """Remove all <answer>...</answer> blocks from text (best effort)."""
    if not text or not isinstance(text, str):
        return ""
    return _ANSWER_BLOCK_RE.sub("", text).strip()


def stitch_think_and_answer(response_text: str, reasoning_text: str | None) -> str:
    """Ensure the response contains a <think> and (if possible) an <answer> block.

    Some providers may put the *entire* output (including <answer>) into `reasoning_content`
    and leave `content` empty. For strict verify that requires a literal <think> block,
    we "stitch" the provider reasoning into <think> and also recover <answer> if it only
    exists in the reasoning field.

    We do NOT invent reasoning or answers: we only reuse text returned by the provider.
    """
    if not isinstance(response_text, str):
        response_text = "" if response_text is None else str(response_text)

    resp_lower = response_text.lower()
    has_think = "<think" in resp_lower and "</think>" in resp_lower
    has_answer = "<answer" in resp_lower and "</answer>" in resp_lower

    # Already in the expected format (or close enough); don't mutate.
    if has_think and has_answer:
        return response_text

    if not reasoning_text or not isinstance(reasoning_text, str) or not reasoning_text.strip():
        return response_text

    # If the provider accidentally includes <answer> inside reasoning_content, split it out so
    # the final output still has two top-level blocks.
    recovered_answer = None if has_answer else extract_answer_block(reasoning_text)
    think_payload = strip_answer_blocks(reasoning_text) if recovered_answer else reasoning_text.strip()

    out = response_text
    if not has_think and think_payload.strip():
        out = f"<think>\n{think_payload.strip()}\n</think>\n{out}"
    if not has_answer and recovered_answer:
        if out and not out.endswith("\n"):
            out += "\n"
        out += recovered_answer
    return out
