#!/usr/bin/env python3
"""
Clean an agent YAML by removing too-short experience guidelines.

This repo stores many experience packs inside the agent config under:

  agent.instructions: '... [G0]. ... [G1]. ...'

Some update runs can accidentally add placeholder / fragment guidelines (e.g. a title
without content). This script removes guideline blocks whose character length is
below a configurable threshold, while preserving the rest of the YAML file (including
the Hydra header comment like `# @package _global_`).

By default it only targets guidelines that start at the beginning of a line:
  ^[G<number>].
This avoids accidentally splitting on inline references like "... card [G63]. ...".
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
    raw: str  # raw text (includes the leading "[G..].")

    @property
    def trimmed(self) -> str:
        return self.raw.strip()

    @property
    def trimmed_len(self) -> int:
        return len(self.trimmed)

    @property
    def preview(self) -> str:
        one_line = " ".join(self.trimmed.split())
        return one_line[:180]


_GUIDELINE_START_RE = re.compile(r"^\[G(\d+)\]\.\s*", flags=re.M)


def _iter_guideline_blocks(instructions: str) -> tuple[str, list[GuidelineBlock]]:
    matches = list(_GUIDELINE_START_RE.finditer(instructions))
    if not matches:
        return instructions, []

    prefix = instructions[: matches[0].start()]
    blocks: list[GuidelineBlock] = []
    for i, m in enumerate(matches):
        gid = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if (i + 1) < len(matches) else len(instructions)
        blocks.append(GuidelineBlock(gid=gid, raw=instructions[start:end]))
    return prefix, blocks


def _clean_instructions_min_len(instructions: str, *, min_len: int) -> tuple[str, list[GuidelineBlock]]:
    prefix, blocks = _iter_guideline_blocks(instructions)

    kept: list[str] = []
    removed: list[GuidelineBlock] = []
    for block in blocks:
        if block.trimmed_len < min_len:
            removed.append(block)
        else:
            kept.append(block.trimmed)

    prefix_clean = prefix.rstrip()
    if not kept:
        return prefix_clean, removed

    cleaned = (prefix_clean + "\n\n" + "\n\n".join(kept)).rstrip("\n")
    return cleaned, removed


def _find_single_quoted_scalar_bounds(text: str, *, key_re: re.Pattern[str]) -> tuple[int, int, str]:
    """
    Find the bounds of a single-quoted YAML scalar value.

    Returns:
      (value_start_pos, value_end_pos, continuation_indent)

    Where:
      - value_start_pos points *just after* the opening quote (').
      - value_end_pos points *at* the closing quote (') that terminates the scalar.
      - continuation_indent is the indentation prefix to use for subsequent lines.
    """
    m = key_re.search(text)
    if not m:
        raise ValueError("Could not find instructions single-quoted scalar in YAML text.")

    indent = m.group("indent")
    continuation_indent = indent + "  "

    value_start = m.end()
    i = value_start
    while i < len(text):
        ch = text[i]
        if ch != "'":
            i += 1
            continue
        # YAML single-quoted escape: '' => literal '
        if (i + 1) < len(text) and text[i + 1] == "'":
            i += 2
            continue
        value_end = i
        return value_start, value_end, continuation_indent

    raise ValueError("Unterminated single-quoted scalar for instructions.")


def _encode_as_multiline_single_quoted(value: str, *, continuation_indent: str) -> str:
    """
    Encode a Python string into a YAML single-quoted scalar body (without the surrounding quotes).

    Important YAML nuance:
      - In *quoted* scalars, a single line break is folded to a space.
      - A run of N>=2 line breaks is parsed as N-1 newline characters.

    To preserve the exact newline runs of the input `value` after YAML parsing,
    we expand every run of newlines by +1 before writing it to YAML.
    """
    value = value.rstrip("\n")
    escaped = value.replace("'", "''")

    # Preserve newline runs after YAML's folding rules for quoted scalars:
    # output_run_len = input_run_len + 1 (for every maximal run).
    expanded = re.sub(r"\n+", lambda m: "\n" * (len(m.group(0)) + 1), escaped)

    lines = expanded.split("\n")
    if not lines:
        return ""

    out = lines[0]
    for line in lines[1:]:
        out += "\n" + continuation_indent + line
    return out


def _write_report(
    report_path: Path,
    *,
    input_path: Path,
    output_path: Path,
    min_len: int,
    total_guidelines: int,
    removed: Iterable[GuidelineBlock],
) -> None:
    removed_list = list(removed)
    removed_list_sorted = sorted(removed_list, key=lambda b: (b.trimmed_len, b.gid))
    kept = total_guidelines - len(removed_list)

    lines: list[str] = []
    lines.append("== agent experience clean report ==")
    lines.append(f"input:  {input_path}")
    lines.append(f"output: {output_path}")
    lines.append(f"min_len: {min_len}")
    lines.append(f"total_guidelines: {total_guidelines}")
    lines.append(f"kept: {kept}")
    lines.append(f"removed: {len(removed_list)}")
    lines.append("")

    if removed_list_sorted:
        lines.append("Removed guideline blocks (< min_len):")
        for block in removed_list_sorted:
            lines.append(f"- G{block.gid} len={block.trimmed_len} preview={block.preview!r}")
    else:
        lines.append("No guideline blocks removed.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove too-short [G..] guidelines from an agent YAML.")
    parser.add_argument("--input", required=True, type=Path, help="Input agent YAML file path.")
    parser.add_argument("--output", required=True, type=Path, help="Output cleaned agent YAML file path.")
    parser.add_argument("--report", required=True, type=Path, help="Output report text file path.")
    parser.add_argument("--min-len", type=int, default=200, help="Minimum guideline block length to keep.")
    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path = args.output
    report_path: Path = args.report
    min_len: int = args.min_len

    raw_text = input_path.read_text(encoding="utf-8", errors="replace")
    try:
        parsed = yaml.safe_load(raw_text)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Failed to parse YAML: {e}") from e

    instructions = parsed.get("agent", {}).get("instructions")
    if not isinstance(instructions, str):
        raise SystemExit("YAML does not contain agent.instructions as a string.")

    cleaned_instructions, removed = _clean_instructions_min_len(instructions, min_len=min_len)

    # Replace scalar content in-place in the *original YAML text* to preserve Hydra header comment, ordering, etc.
    key_re = re.compile(r"^(?P<indent>[ \t]*)instructions:\s*'", flags=re.M)
    value_start, value_end, continuation_indent = _find_single_quoted_scalar_bounds(raw_text, key_re=key_re)
    encoded = _encode_as_multiline_single_quoted(cleaned_instructions, continuation_indent=continuation_indent)
    cleaned_text = raw_text[:value_start] + encoded + raw_text[value_end:]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cleaned_text, encoding="utf-8")

    # Sanity-check output parses and matches the intended instruction string.
    parsed_out = yaml.safe_load(output_path.read_text(encoding="utf-8", errors="replace"))
    out_instructions = parsed_out.get("agent", {}).get("instructions")
    if out_instructions != cleaned_instructions:
        raise SystemExit("Output YAML round-trip mismatch: agent.instructions does not match cleaned content.")

    # Recompute guideline count for reporting based on anchored starts.
    _, blocks_after = _iter_guideline_blocks(cleaned_instructions)
    total_before = len(_GUIDELINE_START_RE.findall(instructions))

    _write_report(
        report_path,
        input_path=input_path,
        output_path=output_path,
        min_len=min_len,
        total_guidelines=total_before,
        removed=removed,
    )

    print(f"Wrote cleaned agent YAML: {output_path}")
    print(f"Wrote report: {report_path}")
    print(f"Guidelines: before={total_before} after={len(blocks_after)} removed={len(list(removed))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
