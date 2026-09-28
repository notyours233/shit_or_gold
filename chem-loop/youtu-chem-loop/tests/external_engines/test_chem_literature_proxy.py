from __future__ import annotations

import sys
from pathlib import Path

from utu.external_engines.chem_literature_proxy import SubprocessChemLiteratureRAG


def test_subprocess_chem_literature_rag_masks_doc_ids_and_converts_shape(tmp_path):
    # Resolve fixture path independent of current working directory (monorepo-friendly).
    runner = (Path(__file__).resolve().parents[1] / "fixtures" / "fake_chem_literature_runner.py").resolve()
    assert runner.exists()

    rag = SubprocessChemLiteratureRAG(
        python_bin=sys.executable,
        runner_path=str(runner),
        repo_root=str(tmp_path),
        reaction_type="OER",
        masked_doc_ids=["10.masked/doi"],
        limit=5,
        max_distance=0.35,
        timeout_s=5,
        call_limit=1,
    )

    results = rag.retrieve("dummy query")
    assert isinstance(results, list)
    assert len(results) == 1
    r0 = results[0]
    assert r0["metadata"]["doc_id"] == "10.ok/doi"
    assert "OK DOC TEXT" in r0["text"]
    assert r0.get("score") is not None


def test_subprocess_chem_literature_rag_enforces_call_limit(tmp_path):
    runner = (Path(__file__).resolve().parents[1] / "fixtures" / "fake_chem_literature_runner.py").resolve()
    rag = SubprocessChemLiteratureRAG(
        python_bin=sys.executable,
        runner_path=str(runner),
        repo_root=str(tmp_path),
        reaction_type="OER",
        masked_doc_ids=[],
        timeout_s=5,
        call_limit=1,
    )
    assert rag.retrieve("q1")  # first call returns something
    assert rag.retrieve("q2") == []  # second call is blocked
