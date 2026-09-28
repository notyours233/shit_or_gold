#!/usr/bin/env python3
"""Compatibility entrypoint for the main extractor script."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


if __name__ == "__main__":
    target = Path(__file__).with_name("main_extract.py")
    spec = spec_from_file_location("newshit_main_extract", target)
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    raise SystemExit(module.main())
