"""Chem-performance verify entrypoint for Training-Free GRPO.

This file is loaded dynamically by `TrainingFreeGRPOProcesser` via:
  VERIFY_DIR / EvalConfig.verify_filename

Keep this file small: it wires together parsing/alignment/reward modules.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from utu.db import EvaluationSample

# NOTE: This module is loaded dynamically via importlib with the name "verify_module",
# so we must use absolute imports (relative imports would not resolve correctly).
from utu.practice.verify.chem_performance_lib.answer_parser import (
    extract_structured_answer_object,
    parse_answer_numbers,
)
from utu.practice.verify.chem_performance_lib.gt_parser import parse_gt_json
from utu.practice.verify.chem_performance_lib.key_alignment import diff_keys
from utu.practice.verify.chem_performance_lib.reward import compute_reward


_CO2RR_PRODUCT_ALIASES: dict[str, str] = {
    # Match the data-processing normalization (keep small and explicit).
    "co": "CO",
    "carbon monoxide": "CO",
    "hcooh": "HCOOH",
    "hcoo-": "HCOOH",
    "hcoo−": "HCOOH",
    "hcoo": "HCOOH",
    "formic acid": "HCOOH",
    "formate": "HCOOH",
    "c2h4": "C2H4",
    "ethylene": "C2H4",
    "ethene": "C2H4",
    "c2h5oh": "C2H5OH",
    "ethanol": "C2H5OH",
    "ch4": "CH4",
    "methane": "CH4",
    "ch3cooh": "CH3COOH",
    "acetic acid": "CH3COOH",
    "acetate": "CH3COOH",
    "c2+": "C2+",
    "c2 products": "C2+",
    "c2": "C2+",
    "multi-carbon products": "C2+",
    "multi-carbon": "C2+",
    "c3+": "C3+",
    "n-propanol": "C3+",
}

_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def _normalize_co2rr_product_label(product: str) -> str:
    s = " ".join((product or "").strip().split())
    if not s:
        return ""
    return _CO2RR_PRODUCT_ALIASES.get(s.lower(), s)


def _parse_fe_fraction(value: Any) -> float | None:
    """Parse Faradaic efficiency into a fraction in [0, 1].

    Accepts:
    - float/int in [0,1]
    - float/int in (1,100] treated as percent (e.g., 94 -> 0.94)
    - strings with optional trailing units/percent (e.g., "94%", "0.94")
    """
    if isinstance(value, bool) or value is None:
        return None

    num: float
    rest: str = ""
    if isinstance(value, (int, float)):
        num = float(value)
        if not math.isfinite(num):
            return None
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        m = _NUM_PREFIX_RE.match(s)
        if not m:
            return None
        try:
            num = float(m.group("num"))
        except Exception:
            return None
        if not math.isfinite(num):
            return None
        rest = s[m.end() :]
    else:
        return None

    # Percent forms: "94%" or "94" (common) should be treated as 0.94.
    if "%" in rest or (num > 1.0 and num <= 100.0):
        num = num / 100.0

    # Clamp/reject: FE should be in [0, 1].
    if num < 0.0 or num > 1.0:
        return None
    return num


def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict[str, Any]:
    """Verify a chem-performance rollout.

    Returns:
        {"reward": float, "reasoning": str|None}
    """
    response_text = sample.response or ""

    # Decide task type from GT payload:
    # - CO2RR Task 1: correct_answer == {"product": "<string>"}
    # - Default: numeric metrics dict (values parseable as numbers, optionally with units)
    try:
        gt_raw = json.loads(sample.correct_answer or "")
    except Exception as e:  # noqa: BLE001 - stable reward on dataset issues
        return {"reward": float(timeout_score), "reasoning": f"Invalid ground truth correct_answer JSON: {e}"}

    if isinstance(gt_raw, dict) and isinstance(gt_raw.get("product"), str):
        # CO2RR Task 1: product classification, optionally with FE regression.
        # Old GT shape: {"product": "<string>"}
        # New GT shape: {"product": "<string>", "faradaic_efficiency": <number>}

        gt_keys = {str(k) for k in gt_raw.keys()}
        if gt_keys not in ({"product"}, {"product", "faradaic_efficiency"}):
            # Not a CO2RR product task; fall through to numeric-metrics verifier.
            pass
        else:
            pred_raw = extract_structured_answer_object(response_text)
            if pred_raw is None:
                return {"reward": 0.0, "reasoning": "Failed to parse predicted answer object (expected JSON dict)."}

            if not isinstance(pred_raw, dict) or not pred_raw:
                return {"reward": 0.0, "reasoning": "<answer> must be a non-empty JSON object (dict)."}

            pred_keys = {str(k) for k in pred_raw.keys()}

            # If GT includes FE, require FE in prediction too.
            if gt_keys == {"product", "faradaic_efficiency"} and pred_keys != {"product", "faradaic_efficiency"}:
                extra = pred_keys - {"product", "faradaic_efficiency"}
                missing = {"product", "faradaic_efficiency"} - pred_keys
                return {
                    "reward": 0.0,
                    "reasoning": f"Invalid keys for CO2RR product+FE task: extra={sorted(extra)} missing={sorted(missing)}",
                }

            # Old GT: allow either {"product"} or {"product","faradaic_efficiency"} in prediction.
            if gt_keys == {"product"} and pred_keys not in ({"product"}, {"product", "faradaic_efficiency"}):
                extra = pred_keys - {"product", "faradaic_efficiency"}
                missing = {"product"} - pred_keys
                return {
                    "reward": 0.0,
                    "reasoning": f"Invalid keys for product task: extra={sorted(extra)} missing={sorted(missing)}",
                }

            pred_prod = pred_raw.get("product")
            if not isinstance(pred_prod, str) or not pred_prod.strip():
                return {"reward": 0.0, "reasoning": "Predicted 'product' must be a non-empty string."}

            gt_prod = str(gt_raw.get("product") or "")
            ok = _normalize_co2rr_product_label(pred_prod) == _normalize_co2rr_product_label(gt_prod)
            if not ok:
                return {"reward": 0.0, "reasoning": f"Wrong product: pred={pred_prod!r} gt={gt_prod!r}"}

            # If FE is part of the task (new GT), score it. If GT is old-style but the sample contains
            # FE ground truth in meta, we can optionally score it as well when the model provides it.
            gt_fe: float | None = None
            if gt_keys == {"product", "faradaic_efficiency"}:
                gt_fe = _parse_fe_fraction(gt_raw.get("faradaic_efficiency"))
                if gt_fe is None:
                    return {
                        "reward": float(timeout_score),
                        "reasoning": "Invalid GT faradaic_efficiency (expected a number/fraction).",
                    }
            elif isinstance(sample.meta, dict):
                metrics_raw = sample.meta.get("metrics_raw")
                if isinstance(metrics_raw, dict):
                    gt_fe = _parse_fe_fraction(metrics_raw.get("truth_faradaic_efficiency_fraction"))

            if "faradaic_efficiency" in pred_raw and gt_fe is not None:
                pred_fe = _parse_fe_fraction(pred_raw.get("faradaic_efficiency"))
                if pred_fe is None:
                    return {
                        "reward": 0.0,
                        "reasoning": "Predicted 'faradaic_efficiency' must be a number in [0,1] (fraction, not percent).",
                    }
                reward, _ = compute_reward(
                    {"faradaic_efficiency": gt_fe},
                    {"faradaic_efficiency": pred_fe},
                    units={"faradaic_efficiency": "fraction_0_to_1"},
                    reaction_type="CO2RR",
                )
                return {"reward": reward, "reasoning": None}

            # Backward-compatible: if FE isn't being scored, product-only correctness is a full reward.
            if gt_keys == {"product", "faradaic_efficiency"}:
                # New task requires FE; if we couldn't score it, treat as failure.
                return {"reward": 0.0, "reasoning": "Missing or unscorable 'faradaic_efficiency' for CO2RR product+FE task."}
            return {"reward": 1.0, "reasoning": None}

    units = None
    reaction_type = None
    if isinstance(sample.meta, dict):
        rt = sample.meta.get("reaction_type") or sample.meta.get("task_type") or sample.meta.get("property_type")
        if isinstance(rt, str) and rt.strip():
            reaction_type = rt.strip()
        maybe_units = sample.meta.get("units")
        if isinstance(maybe_units, dict):
            # Ensure keys/values are strings for consistent lookups.
            units = {str(k): str(v) for k, v in maybe_units.items() if v is not None}

    try:
        pred = parse_answer_numbers(response_text, expected_units=units)
    except Exception as e:  # noqa: BLE001 - we want a stable reward=0 on parse failures
        return {"reward": 0.0, "reasoning": f"Failed to parse predicted answer object: {e}"}

    try:
        gt = parse_gt_json(sample.correct_answer)
    except Exception as e:  # noqa: BLE001
        # This indicates a dataset/DB issue. Fail closed.
        return {"reward": float(timeout_score), "reasoning": f"Invalid ground truth correct_answer: {e}"}

    missing, extra = diff_keys(gt, pred)
    if extra:
        return {
            "reward": 0.0,
            "reasoning": f"Extra keys in prediction not allowed: {sorted(extra)} (missing={sorted(missing)})",
        }

    reward, per_metric = compute_reward(gt, pred, units=units, reaction_type=reaction_type)
    if missing:
        return {"reward": reward, "reasoning": f"Missing keys: {sorted(missing)}; per_metric={per_metric}"}
    return {"reward": reward, "reasoning": None}
