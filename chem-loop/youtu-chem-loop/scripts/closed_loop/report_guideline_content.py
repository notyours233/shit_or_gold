#!/usr/bin/env python3
"""Report whether an experience pack's guidelines are chemistry-focused vs format/method boilerplate.

This script is intentionally lightweight (stdlib + PyYAML) so it can run inside Docker
or minimal environments.

What it checks
--------------
- Extract `[G*]. ...` guideline blocks from `agent.instructions` in an agent YAML.
- Categorize each guideline (heuristic):
  - format_like: mostly about `<think>/<answer>` tags, STRICT JSON rules, key-matching reminders, etc.
  - chemistry_like: mentions reaction types / metrics / electrochem-specific keywords.
  - method_like: neither of the above (often generic "weighted average / evidence gathering" style).

This is not a scientific classifier; it's a QA helper to prevent the experience pool from
being dominated by formatting rules instead of reusable chemistry knowledge.

Typical usage
-------------
  cd /app/youtu-chem-loop
  python scripts/closed_loop/report_guideline_content.py \
    --agent_yaml /state/experience_runs/balanced5_smoke_20260309_123456_agent.yaml \
    --max_show 20
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_GUIDELINE_START_RE = re.compile(r"^\s*\[(?P<gid>G?\d+)\]\.\s*(?P<rest>.*)\s*$")


def _safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(obj)


def _load_agent_instructions(path: Path) -> str:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected YAML mapping at top-level, got {type(raw).__name__}")
    agent = raw.get("agent")
    if not isinstance(agent, dict):
        raise ValueError("Missing top-level 'agent' mapping")
    instr = agent.get("instructions")
    if not isinstance(instr, str) or not instr.strip():
        raise ValueError("Missing/empty 'agent.instructions'")
    return instr


@dataclass(frozen=True)
class Guideline:
    gid: str
    text: str


def _parse_guidelines(instructions: str) -> list[Guideline]:
    """Parse `[G*]. ...` blocks from agent.instructions (best effort)."""
    lines = (instructions or "").splitlines()
    current_gid: str | None = None
    current: list[str] = []
    out: list[Guideline] = []

    def _flush() -> None:
        nonlocal current_gid, current
        if current_gid is None:
            return
        text = " ".join([x.strip() for x in current if x.strip()])
        text = " ".join(text.split())
        if text:
            out.append(Guideline(gid=current_gid, text=text))
        current_gid = None
        current = []

    for line in lines:
        m = _GUIDELINE_START_RE.match(line)
        if m:
            _flush()
            raw_gid = (m.group("gid") or "").strip()
            digits = re.sub(r"[^0-9]", "", raw_gid)
            current_gid = f"G{int(digits)}" if digits else raw_gid
            current = [m.group("rest").strip()]
            continue

        if current_gid is None:
            continue
        cont = line.strip()
        if cont:
            current.append(cont)

    _flush()
    return out


def _guideline_title(text: str) -> str:
    if not text:
        return ""
    return text.split(":", 1)[0].strip().lower()


def _is_format_like(text: str) -> bool:
    """Heuristic filter: guidelines that mostly talk about output formatting."""
    t = str(text or "").lower()
    title = _guideline_title(t)

    if not t.strip():
        return True

    # Hard format markers.
    if any(tok in t for tok in ("<think", "</think", "<answer", "</answer")):
        return True
    if "format compliance" in t:
        return True
    if title in {"tool-specific compliance", "tool specific compliance"}:
        return True
    if "no extraneous" in t:
        return True
    if "strict json" in t:
        return True
    if "json dict" in t and "keys" in t:
        return True
    if "key matching" in t and "metrics_to_predict" in t:
        return True
    return False


_CHEM_KEYWORDS = {
    # Reaction types
    "oer",
    "her",
    "orr",
    "hor",
    "uor",
    "eor",
    "hzor",
    "o5h",
    "co2rr",
    # Common metrics / electrochem terms
    "overpotential",
    "eta10",
    "10 ma",
    "10 mA".lower(),
    "mA cm-2".lower(),
    "half-wave",
    "half wave",
    "e1/2",
    "exchange current",
    "j0",
    "faradaic",
    "fe",
    "rhe",
    "partial current",
    "mass activity",
    # Chemistry/materials terms
    "oxide",
    "hydroxide",
    "ldh",
    "perovskite",
    "alloy",
    "doping",
    "dopant",
    "oxophilicity",
    "adsorption",
    "binding",
    "synergy",
    "catalyst",
    "electrode",
}


def _is_chemistry_like(text: str) -> bool:
    t = str(text or "")
    if not t.strip():
        return False
    s = t.lower()
    return any(k in s for k in _CHEM_KEYWORDS)


def _print_bucket(name: str, items: list[Guideline], *, max_show: int) -> None:
    print(f"{name}: {len(items)}")
    if not items:
        return
    show = items[: max(0, int(max_show))]
    for g in show:
        print(f"- [{g.gid}] {g.text}")
    if len(items) > len(show):
        print(f"- ... ({len(items) - len(show)} more)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Report guideline content categories (format vs chemistry vs method).")
    ap.add_argument("--agent_yaml", required=True, help="Path to an agent YAML containing agent.instructions + [G*].")
    ap.add_argument("--max_show", type=int, default=10, help="Max examples to show per bucket (default: 10).")
    ap.add_argument("--out_json", default=None, help="Optional: write the summary JSON to this file.")
    args = ap.parse_args()

    path = Path(str(args.agent_yaml)).expanduser()
    if not path.exists():
        raise SystemExit(f"agent_yaml not found: {path}")

    instr = _load_agent_instructions(path)
    guidelines = _parse_guidelines(instr)
    if not guidelines:
        raise SystemExit("No [G*] guidelines found in agent.instructions")

    format_like: list[Guideline] = []
    chemistry_like: list[Guideline] = []
    method_like: list[Guideline] = []

    for g in guidelines:
        if _is_format_like(g.text):
            format_like.append(g)
        elif _is_chemistry_like(g.text):
            chemistry_like.append(g)
        else:
            method_like.append(g)

    total = len(guidelines)
    fmt_n = len(format_like)
    chem_n = len(chemistry_like)
    method_n = len(method_like)

    def _pct(n: int) -> str:
        return f"{(n / total) * 100:.1f}%" if total else "-"

    print("== Guideline Content Report ==")
    print(f"- file: {path}")
    print(f"- total: {total}")
    print(f"- format_like: {fmt_n} ({_pct(fmt_n)})")
    print(f"- chemistry_like: {chem_n} ({_pct(chem_n)})")
    print(f"- method_like: {method_n} ({_pct(method_n)})")
    print()

    _print_bucket("Format-like (examples)", format_like, max_show=args.max_show)
    print()
    _print_bucket("Chemistry-like (examples)", chemistry_like, max_show=args.max_show)
    print()
    _print_bucket("Method-like (examples)", method_like, max_show=args.max_show)

    if args.out_json:
        out = {
            "file": str(path),
            "counts": {
                "total": total,
                "format_like": fmt_n,
                "chemistry_like": chem_n,
                "method_like": method_n,
            },
            "guidelines": {
                "format_like": [{"gid": g.gid, "text": g.text} for g in format_like],
                "chemistry_like": [{"gid": g.gid, "text": g.text} for g in chemistry_like],
                "method_like": [{"gid": g.gid, "text": g.text} for g in method_like],
            },
        }
        Path(str(args.out_json)).write_text(_safe_json_dumps(out) + "\n", encoding="utf-8")
        print()
        print(f"Wrote JSON summary: {args.out_json}")


if __name__ == "__main__":
    main()

