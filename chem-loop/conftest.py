from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    """Make the monorepo importable from the repo root.

    - `utu` lives under `youtu-chem-loop/utu`
    """
    root = Path(__file__).resolve().parent
    # `utu` must take precedence (it is not installed as a site-package in this repo).
    youtu = str(root / "youtu-chem-loop")
    if youtu not in sys.path:
        sys.path.insert(0, youtu)
