#!/usr/bin/env python3
"""Fake MAD runner that requires `masked_doc_ids` to be passed via stdin payload."""

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
    masked = payload.get("masked_doc_ids")
    if masked != ["10.1234/test-doi"]:
        print(f"Expected masked_doc_ids=['10.1234/test-doi'], got: {masked!r}", file=sys.stderr)
        return 3

    out = {
        "final_output": "<answer>{\"overpotential\": 0.123}</answer>",
        "reasoning": "Fake reasoning; masking was provided.",
        "trajectory": {"steps": [{"thought": "ok", "tool_calls": [], "observation": ""}]},
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

