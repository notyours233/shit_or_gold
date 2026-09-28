"""Chem-performance verification helper modules.

Why this is a separate package:
- The Training-Free GRPO processor dynamically loads `utu/practice/verify/chem_performance.py`
  by filename. If we also had a `chem_performance/` package, it would shadow that module
  and cause confusing import errors.
"""
