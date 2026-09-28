"""ChemCouncil web backend package.

This package provides a small HTTP API + static UI around the existing CLI workflows:
- MAD reaction recommendation (rank mode)
- Experimental data feedback -> incremental experience update (training-free GRPO)
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_monorepo_python_paths() -> None:
    """Make sibling packages importable when ChemCouncil is run as `python -m`.

    Docker runs the web service from `/app`, but `utu` lives under the sibling
    directory `/app/youtu-chem-loop/utu` and is not installed as a site-package.
    """
    root = Path(__file__).resolve().parents[1]
    youtu = str(root / "youtu-chem-loop")
    if youtu not in sys.path:
        sys.path.insert(0, youtu)


_ensure_monorepo_python_paths()
