#!/usr/bin/env python3
"""Fake MAD runner: outputs a JSON dict without <answer> tags."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mad_repo_path", required=True)
    ap.add_argument("--max_react_steps", type=int, default=6)
    ap.add_argument("--agent_name", default="mad_engine")
    _args = ap.parse_args()

    payload = json.loads(sys.stdin.read() or "{}")
    _question = payload.get("question", "")

    out = {
        "final_output": "{\"overpotential\": 0.288}",
        "reasoning": "Some reasoning that should become <think>.",
        "trajectory": {"steps": []},
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

