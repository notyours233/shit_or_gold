import json
import sqlite3
from pathlib import Path

import pytest

from utu.config import ToolkitConfig
from utu.hooks.base_hooks import TOOL_CALL_COUNTS_KEY
from utu.tools.chem_literature_db_toolkit import ChemLiteratureDBToolkit


def _build_sqlite_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE papers (
          paper_id TEXT PRIMARY KEY,
          title TEXT,
          abstract TEXT,
          doi TEXT,
          year INTEGER
        )
        """
    )
    cur.executemany(
        "INSERT INTO papers(paper_id, title, abstract, doi, year) VALUES(?,?,?,?,?)",
        [
            (
                "p1",
                "Lanthanum-based catalysts for HER in alkaline media",
                "We report HER activity for La and related catalysts. Overpotential at 10 mA/cm2 is discussed.",
                "10.0000/example1",
                2022,
            ),
            (
                "p2",
                "OER overpotential of Mn-Ni-Tb mixed oxides",
                "OER results: overpotential 288 mV at 10 mA/cm2 for MnNiTb oxide catalysts.",
                "10.0000/example2",
                2021,
            ),
            (
                "p3",
                "CO2RR on Bi catalysts towards formate",
                "CO2RR selectivity to HCOOH with high faradaic efficiency is described.",
                "10.0000/example3",
                2020,
            ),
        ],
    )
    con.commit()
    con.close()


@pytest.mark.asyncio
async def test_literature_healthcheck_missing_db_returns_error(tmp_path: Path):
    db_path = tmp_path / "missing.sqlite"
    tk = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={"db_path": str(db_path)},
        )
    )
    res = await tk.literature_healthcheck()
    assert res["ok"] is False
    assert "DB file not found" in res.get("error", "")


@pytest.mark.asyncio
async def test_literature_search_and_get_ok(tmp_path: Path):
    db_path = tmp_path / "lit.sqlite"
    _build_sqlite_db(db_path)

    tk = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={"db_path": str(db_path)},
        )
    )

    hits = await tk.literature_search(query="OER overpotential Mn Ni Tb", limit=3)
    assert isinstance(hits, list)
    assert hits and "error" not in hits[0]
    assert hits[0]["paper_id"] == "p2"
    assert "abstract_snippet" in hits[0]

    paper = await tk.literature_get("p2")
    assert paper["paper_id"] == "p2"
    assert "OER overpotential" in (paper["title"] or "")


@pytest.mark.asyncio
async def test_literature_search_respects_configured_result_limit(tmp_path: Path):
    db_path = tmp_path / "lit.sqlite"
    _build_sqlite_db(db_path)
    tk = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={"db_path": str(db_path), "max_results_per_search": 1},
        )
    )

    hits = await tk.literature_search(query="catalyst", limit=10)

    assert len(hits) == 1


@pytest.mark.asyncio
async def test_budgeted_tool_stays_registered_and_returns_error_after_limit(tmp_path: Path):
    db_path = tmp_path / "lit.sqlite"
    _build_sqlite_db(db_path)
    toolkit = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            activated_tools=["literature_search"],
            config={"db_path": str(db_path), "tool_call_limits": {"literature_search": 1}},
        )
    )
    tool = toolkit.get_tools_in_agents()[0]

    class FakeContext:
        context = {TOOL_CALL_COUNTS_KEY: {"literature_search": 2}}

    result = await tool.on_invoke_tool(FakeContext(), '{"query":"OER"}')

    assert tool.name == "literature_search"
    assert tool.is_enabled is True
    payload = json.loads(result)
    assert payload["error"] == "tool_call_budget_exceeded"
    assert payload["max_calls_per_run"] == 1
