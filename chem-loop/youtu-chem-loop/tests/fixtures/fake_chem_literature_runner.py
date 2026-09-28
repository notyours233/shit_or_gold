#!/usr/bin/env python3
"""Fake chem_literature_runner used by SubprocessChemLiteratureRAG unit tests.

Protocol: reads JSON from stdin and prints a JSON list of hits to stdout.
It mimics the *shape* of youtu-agent's `chem_literature_db` tool output for chroma backend.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    masked = payload.get("masked_doc_ids") or []

    hits = [
        {
            "id": "hit_masked",
            "doc_id": "10.masked/doi",
            "reaction_type": payload.get("reaction_type") or "OER",
            "chunk_id": 1,
            "total_chunks": 10,
            "distance": 0.05,
            "confidence": 0.95,
            "text": "MASKED DOC TEXT",
        },
        {
            "id": "hit_ok",
            "doc_id": "10.ok/doi",
            "reaction_type": payload.get("reaction_type") or "OER",
            "chunk_id": 2,
            "total_chunks": 8,
            "distance": 0.10,
            "confidence": 0.90,
            "text": "OK DOC TEXT",
        },
    ]

    if "10.masked/doi" in masked:
        hits = [h for h in hits if h.get("doc_id") != "10.masked/doi"]

    sys.stdout.write(json.dumps(hits, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

