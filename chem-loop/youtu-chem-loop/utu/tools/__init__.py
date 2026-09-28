"""Toolkits (chem-loop focused).

The upstream youtu-agent framework ships many toolkits (web search, file editing,
image/video, etc.). For this extracted chem-loop repo we only keep the toolkit
needed for literature RAG with masking:

- `chem_literature_db`

If you need other toolkits later, restore them from upstream and expand
`TOOLKIT_MAP` accordingly.
"""

from ..config import ConfigLoader
from .base import AsyncBaseToolkit as AsyncBaseToolkit
from .chem_literature_db_toolkit import ChemLiteratureDBToolkit
from .utils import get_tools_map as get_tools_map, get_tools_schema as get_tools_schema, register_tool as register_tool

TOOLKIT_MAP: dict[str, type[AsyncBaseToolkit]] = {
    "chem_literature_db": ChemLiteratureDBToolkit,
}


def get_toolkits_map(names: list[str] | None = None) -> dict[str, AsyncBaseToolkit]:
    """Load toolkits by name from `configs/tools/*.yaml`."""
    toolkits: dict[str, AsyncBaseToolkit] = {}
    if names is None:
        names = list(TOOLKIT_MAP.keys())
    else:
        assert all(name in TOOLKIT_MAP for name in names), f"Unknown toolkit(s): {names}"

    for name in names:
        cfg = ConfigLoader.load_toolkit_config(name)
        toolkits[name] = TOOLKIT_MAP[name](config=cfg)
    return toolkits

