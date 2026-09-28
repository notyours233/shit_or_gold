#!/usr/bin/env python3
"""A tiny fake MAD runner used by unit tests.

It mimics the CLI + stdin/stdout protocol of `utu/external_engines/mad_runner.py`
but avoids importing MAD or calling real LLMs.
"""

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
    question = payload.get("question", "")

    # Return only <answer>; adapter should stitch <think> from reasoning.
    out = {
        "final_output": "<answer>{\"overpotential\": 0.288}</answer>",
        "reasoning": f"Fake reasoning for question head: {question[:30]}",
        "trajectory": {
            "steps": [
                {
                    "thought": "I should use available evidence and units to estimate a plausible value.",
                    "tool_calls": [
                        {
                            "tool_name": "conclude",
                            "tool_args": {"conclusion": "<answer>{\"overpotential\": 0.288}</answer>"},
                            "observation": "<answer>{\"overpotential\": 0.288}</answer>",
                        }
                    ],
                    "observation": "<answer>{\"overpotential\": 0.288}</answer>",
                }
            ]
        },
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

