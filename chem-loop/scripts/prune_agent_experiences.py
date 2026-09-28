#!/usr/bin/env python3
"""
Prune reaction-specific guideline blocks from an agent YAML experience pack.

This is intended for workflows such as:
1. take a stable full-library baseline pack,
2. remove all experience blocks related to one reaction (for example `CO2RR`),
3. use the pruned pack as `--seed_experience_yaml` for an incremental rebuild on a
   reaction-specific dataset.

The script preserves the original YAML layout/comment header by replacing only the
`agent.instructions` scalar body in-place, similar to `scripts/clean_agent_experiences.py`.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class GuidelineBlock:
    gid: int
    raw: str

    @property
    def trimmed(self) -> str:
        return self.raw.strip()

    @property
    def preview(self) -> str:
        one_line = " ".join(self.trimmed.split())
        return one_line[:220]


@dataclass(frozen=True)
class RemovedBlock:
    block: GuidelineBlock
    reason: str


_GUIDELINE_START_RE = re.compile(r"^\[G(\d+)\]\.\s*", flags=re.M)
_CASECARD_RT_RE = re.compile(r"\bRT=([^;]+);")


def _iter_guideline_blocks(instructions: str) -> tuple[str, list[GuidelineBlock]]:
    matches = list(_GUIDELINE_START_RE.finditer(instructions))
    if not matches:
        return instructions, []

    prefix = instructions[: matches[0].start()]
    blocks: list[GuidelineBlock] = []
    for i, match in enumerate(matches):
        gid = int(match.group(1))
        start = match.start()
        end = matches[i + 1].start() if (i + 1) < len(matches) else len(instructions)
        blocks.append(GuidelineBlock(gid=gid, raw=instructions[start:end]))
    return prefix, blocks


def _find_single_quoted_scalar_bounds(text: str, *, key_re: re.Pattern[str]) -> tuple[int, int, str]:
    """Find the bounds of a single-quoted YAML scalar value."""
    match = key_re.search(text)
    if not match:
        raise ValueError("Could not find instructions single-quoted scalar in YAML text.")

    indent = match.group("indent")
    continuation_indent = indent + "  "

    value_start = match.end()
    index = value_start
    while index < len(text):
        char = text[index]
        if char != "'":
            index += 1
            continue
        if (index + 1) < len(text) and text[index + 1] == "'":
            index += 2
            continue
        return value_start, index, continuation_indent

    raise ValueError("Unterminated single-quoted scalar for instructions.")


def _encode_as_multiline_single_quoted(value: str, *, continuation_indent: str) -> str:
    """
    Encode a Python string as a YAML single-quoted scalar body without surrounding quotes.

    For quoted YAML scalars, a single newline is folded to a space while a run of N>=2
    newlines becomes N-1 literal newlines after parsing. To preserve exact newline runs
    after round-tripping, expand each maximal run by +1 before writing.
    """
    value = value.rstrip("\n")
    escaped = value.replace("'", "''")
    expanded = re.sub(r"\n+", lambda match: "\n" * (len(match.group(0)) + 1), escaped)
    lines = expanded.split("\n")
    if not lines:
        return ""
    output = lines[0]
    for line in lines[1:]:
        output += "\n" + continuation_indent + line
    return output


def _extract_explicit_reaction_type(block: str) -> str | None:
    match = _CASECARD_RT_RE.search(block)
    if not match:
        return None
    return match.group(1).strip().upper()


def _should_remove_block(block: GuidelineBlock, *, reaction_type: str) -> str | None:
    explicit_rt = _extract_explicit_reaction_type(block.trimmed)
    if explicit_rt is not None:
        if explicit_rt == reaction_type:
            return f"explicit RT={reaction_type}"
        return None

    if reaction_type in block.trimmed.upper():
        return f"mentions {reaction_type} without explicit other RT"

    return None


def _prune_instructions_by_reaction(
    instructions: str, *, reaction_type: str
) -> tuple[str, list[GuidelineBlock], list[RemovedBlock]]:
    prefix, blocks = _iter_guideline_blocks(instructions)

    kept: list[str] = []
    removed: list[RemovedBlock] = []
    for block in blocks:
        reason = _should_remove_block(block, reaction_type=reaction_type)
        if reason is None:
            kept.append(block.trimmed)
            continue
        removed.append(RemovedBlock(block=block, reason=reason))

    prefix_clean = prefix.rstrip()
    if not kept:
        return prefix_clean, blocks, removed

    cleaned = (prefix_clean + "\n\n" + "\n\n".join(kept)).rstrip("\n")
    return cleaned, blocks, removed


def _write_report(
    report_path: Path,
    *,
    input_path: Path,
    output_path: Path,
    reaction_type: str,
    total_guidelines: int,
    removed: Iterable[RemovedBlock],
) -> None:
    removed_list = list(removed)
    kept = total_guidelines - len(removed_list)

    lines: list[str] = []
    lines.append("== agent experience prune report ==")
    lines.append(f"input:  {input_path}")
    lines.append(f"output: {output_path}")
    lines.append(f"reaction_type: {reaction_type}")
    lines.append(f"total_guidelines: {total_guidelines}")
    lines.append(f"kept: {kept}")
    lines.append(f"removed: {len(removed_list)}")
    lines.append("")

    if removed_list:
        lines.append("Removed guideline blocks:")
        for removed_block in removed_list:
            block = removed_block.block
            lines.append(f"- G{block.gid} reason={removed_block.reason!r} preview={block.preview!r}")
    else:
        lines.append("No guideline blocks removed.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove reaction-specific guideline blocks from an agent YAML.")
    parser.add_argument("--input", required=True, type=Path, help="Input agent YAML file path.")
    parser.add_argument("--output", required=True, type=Path, help="Output pruned agent YAML file path.")
    parser.add_argument("--report", required=True, type=Path, help="Output prune report text file path.")
    parser.add_argument(
        "--reaction-type",
        required=True,
        type=str,
        help="Reaction type to prune, e.g. CO2RR.",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path = args.output
    report_path: Path = args.report
    reaction_type = args.reaction_type.strip().upper()

    raw_text = input_path.read_text(encoding="utf-8", errors="replace")
    try:
        parsed = yaml.safe_load(raw_text)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to parse YAML: {exc}") from exc

    instructions = parsed.get("agent", {}).get("instructions")
    if not isinstance(instructions, str):
        raise SystemExit("YAML does not contain agent.instructions as a string.")

    pruned_instructions, blocks, removed = _prune_instructions_by_reaction(
        instructions,
        reaction_type=reaction_type,
    )

    key_re = re.compile(r"^(?P<indent>[ \t]*)instructions:\s*'", flags=re.M)
    value_start, value_end, continuation_indent = _find_single_quoted_scalar_bounds(raw_text, key_re=key_re)
    encoded = _encode_as_multiline_single_quoted(pruned_instructions, continuation_indent=continuation_indent)
    pruned_text = raw_text[:value_start] + encoded + raw_text[value_end:]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(pruned_text, encoding="utf-8")

    parsed_out = yaml.safe_load(output_path.read_text(encoding="utf-8", errors="replace"))
    out_instructions = parsed_out.get("agent", {}).get("instructions")
    if out_instructions != pruned_instructions:
        raise SystemExit("Sanity check failed: output YAML instructions do not match the intended pruned instructions.")

    _write_report(
        report_path,
        input_path=input_path,
        output_path=output_path,
        reaction_type=reaction_type,
        total_guidelines=len(blocks),
        removed=removed,
    )
    print(
        f"Pruned reaction {reaction_type}: total={len(blocks)} kept={len(blocks) - len(removed)} removed={len(removed)}"
    )
    print(f"Wrote: {output_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
