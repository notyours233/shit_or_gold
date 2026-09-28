"""Key alignment checks between prediction and ground truth.

This module lives under `chem_performance_lib/` to avoid shadowing the
`chem_performance.py` verify entrypoint module.
"""

from __future__ import annotations


def diff_keys(gt: dict, pred: dict) -> tuple[set[str], set[str]]:
    gt_keys = {str(k) for k in gt.keys()}
    pred_keys = {str(k) for k in pred.keys()}
    missing = gt_keys - pred_keys
    extra = pred_keys - gt_keys
    return missing, extra
