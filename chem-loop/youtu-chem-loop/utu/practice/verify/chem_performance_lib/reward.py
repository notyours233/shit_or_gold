"""Reward computation for chem-performance.

This is intentionally a simple placeholder reward to make the Training-Free GRPO loop runnable.
It can be replaced by a domain-specific weighted/scaled reward later.

This module lives under `chem_performance_lib/` to avoid shadowing the
`chem_performance.py` verify entrypoint module.
"""

from __future__ import annotations

import math


def _unit_floor(unit: str | None) -> float:
    # Avoid extreme penalties when the GT is close to 0 for bounded metrics.
    if not unit:
        return 0.0
    u = unit.strip()
    if u in {"V", "fraction_0_to_1"}:
        return 0.05
    if u == "%":
        return 1.0
    if u == "K":
        return 1.0
    if u == "emu/g":
        return 1.0
    if u == "W m-1 K-1":
        return 1.0
    if u == "S/m":
        return 1.0
    return 0.0


def score_metric(pred: float, gt: float, *, unit: str | None = None) -> float:
    """Compute a per-metric score in [0, 1]."""
    if not (math.isfinite(pred) and math.isfinite(gt)):
        return 0.0
    denom = abs(gt) + _unit_floor(unit)
    # If denom is 0 (gt==0 and no floor), fall back to absolute error scaling.
    if denom <= 0:
        denom = 1.0
    rel_err = abs(pred - gt) / denom
    # Smooth decay: rel_err=0 -> 1.0; rel_err=1 -> ~0.367
    return float(math.exp(-rel_err))


def _metric_weights(reaction_type: str | None, keys: list[str]) -> dict[str, float]:
    """Return a per-metric weight dict (non-negative floats)."""
    if not keys:
        return {}

    rt = (reaction_type or "").strip()
    if rt == "CO2RR":
        # Equal weights across whatever evaluable metrics exist for this record.
        return {k: 1.0 for k in keys}

    # Default: equal weights.
    return {k: 1.0 for k in keys}


def compute_reward(
    gt_metrics: dict[str, float],
    pred_metrics: dict[str, float],
    *,
    units: dict[str, str] | None = None,
    reaction_type: str | None = None,
) -> tuple[float, dict[str, float]]:
    """Return (reward, per_metric_scores). Missing keys score as 0."""
    if not gt_metrics:
        return 0.0, {}

    per_metric: dict[str, float] = {}
    keys = list(gt_metrics.keys())
    for k in keys:
        gt_v = gt_metrics[k]
        if k not in pred_metrics:
            per_metric[k] = 0.0
            continue
        per_metric[k] = score_metric(pred_metrics[k], gt_v, unit=(units or {}).get(k))

    weights = _metric_weights(reaction_type, keys)
    # If weights are all zero (e.g., unexpected keys for O5H), fall back to equal weights.
    if not any((weights.get(k, 0.0) > 0.0) for k in keys):
        weights = {k: 1.0 for k in keys}

    w_sum = sum(weights.get(k, 0.0) for k in keys)
    if w_sum <= 0:
        reward = sum(per_metric.values()) / len(per_metric)
    else:
        reward = sum(per_metric[k] * weights.get(k, 0.0) for k in keys) / w_sum
    # Clamp to [0, 1] defensively.
    reward = max(0.0, min(1.0, float(reward)))
    return reward, per_metric
