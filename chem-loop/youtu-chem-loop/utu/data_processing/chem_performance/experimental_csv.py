from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import REACTION_ALLOWED_METRICS, REACTION_TYPES
from .metals import normalize_metal_symbol, normalize_metals


_DASH_TRANSLATION = str.maketrans({"−": "-", "–": "-", "‑": "-", "—": "-"})
_REACTION_CANONICAL_BY_UPPER = {rt.upper(): rt for rt in REACTION_TYPES}


def normalize_reaction_type(value: Any) -> str | None:
    """Normalize reaction_type values from experimental CSV rows.

    Supports:
    - canonical tags: HER/OER/ORR/HOR/UOR/EOR/HzOR/O5H/CO2RR (case-insensitive)
    - a small set of Chinese aliases (best-effort)
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    s = s.translate(_DASH_TRANSLATION)
    # Common: case-insensitive (canonicalize to the project enum spelling, e.g. "HZOR" -> "HzOR")
    s_up = s.upper()
    if s_up in _REACTION_CANONICAL_BY_UPPER:
        return _REACTION_CANONICAL_BY_UPPER[s_up]

    # Remove separators to match e.g. "CO2-RR" -> "CO2RR"
    key = re.sub(r"[^A-Za-z0-9]+", "", s).upper()
    if key in _REACTION_CANONICAL_BY_UPPER:
        return _REACTION_CANONICAL_BY_UPPER[key]

    # Chinese best-effort aliases (keep small; expand as real lab tables appear).
    cn = s.replace(" ", "")
    cn_map: dict[str, str] = {
        "析氢": "HER",
        "氢析出": "HER",
        "析氧": "OER",
        "氧析出": "OER",
        "氧还原": "ORR",
        "氢氧化": "HOR",
        "氢氧化反应": "HOR",
        "尿素氧化": "UOR",
        "乙醇氧化": "EOR",
        "联氨氧化": "HzOR",
        "肼氧化": "HzOR",
        "co2rr": "CO2RR",
        "co2rr反应": "CO2RR",
        "co2还原": "CO2RR",
        "co2电还原": "CO2RR",
        "hmf氧化": "O5H",
        "5-hmf氧化": "O5H",
        "5羟甲基糠醛氧化": "O5H",
        "5-羟甲基糠醛氧化": "O5H",
        "5羟甲基糠醛电氧化": "O5H",
        "5-羟甲基糠醛电氧化": "O5H",
    }
    # Use a normalized lookup key for CN mapping.
    cn_key = cn.lower()
    return cn_map.get(cn_key)


_METAL_SPLIT_RE = re.compile(r"[,+;，；/|]+")
_METAL_HEAD_RE = re.compile(r"^\s*(?P<sym>[A-Za-z]{1,2})\b")
_PCT_RE = re.compile(r"(?P<pct>\d+(?:\.\d+)?)\s*%")


def parse_metals_text(metals_text: Any) -> tuple[list[str], dict[str, float]]:
    """Parse a metals string like 'Co(57%),Ni(23%)' into symbols + composition % (if present)."""
    if metals_text is None:
        return [], {}
    s = str(metals_text).strip()
    if not s:
        return [], {}

    metals: list[str] = []
    composition_pct: dict[str, float] = {}

    for part in _METAL_SPLIT_RE.split(s):
        part = part.strip()
        if not part:
            continue

        sym = ""
        m = _METAL_HEAD_RE.match(part)
        if m:
            sym = normalize_metal_symbol(m.group("sym"))
            if sym:
                metals.append(sym)
        else:
            # Fallback: find any element-like tokens (e.g., "CoNi" -> ["Co", "Ni"]).
            for tok in re.findall(r"[A-Z][a-z]?", part):
                t = normalize_metal_symbol(tok)
                if t:
                    metals.append(t)
            sym = normalize_metal_symbol(re.findall(r"[A-Z][a-z]?", part)[0]) if re.findall(r"[A-Z][a-z]?", part) else ""

        # Best-effort composition % extraction (keep as-is; may not sum to 100).
        if sym:
            m_pct = _PCT_RE.search(part)
            if m_pct:
                try:
                    composition_pct[sym] = float(m_pct.group("pct"))
                except ValueError:
                    # Ignore malformed pct.
                    pass

    return normalize_metals(metals), composition_pct


def stitch_value_and_unit(value: Any, unit: Any | None) -> str | None:
    """Join separate CSV value + unit columns into a single parseable string.

    Examples:
    - value='300', unit='mV' -> '300 mV'
    - value='0.14', unit='V' -> '0.14 V'
    - value='98.5', unit='%' -> '98.5%'
    - value='300 mV', unit='mV' -> '300 mV' (do not double-append)
    """
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None

    u = "" if unit is None else str(unit).strip()
    u = u.translate(_DASH_TRANSLATION)
    u = " ".join(u.split())

    if not u:
        return v

    # If the value cell already includes a unit suffix, keep it as-is.
    # (e.g. "300 mV", "0.28 V", "98.5%")
    numeric_only = re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", v.strip()) is not None
    if not numeric_only:
        return v

    if u in {"%", "％"}:
        return f"{v}%"
    return f"{v} {u}".strip()


def normalize_metric_label(metric_label: Any) -> str:
    """Normalize a free-form metric label for matching."""
    if metric_label is None:
        return ""
    s = str(metric_label).strip()
    if not s:
        return ""
    s = s.translate(_DASH_TRANSLATION)
    # Normalize Greek eta to 'eta' and strip common punctuation.
    s = s.replace("η", "eta").replace("Η", "eta")
    s = s.replace("E1/2", "E1/2")  # keep for readability; we'll strip later
    return s


def infer_metric_key(reaction_type: str, metric_label: Any | None = None) -> str | None:
    """Infer the canonical metric key used by the project from a row.

    If metric_label is empty, infer from reaction_type (only works when the allowed
    metric set has exactly 1 item).
    """
    rt = (reaction_type or "").strip()
    if not rt:
        return None

    allowed = REACTION_ALLOWED_METRICS.get(rt)
    label = normalize_metric_label(metric_label)
    if not label:
        # Backward-compat: legacy CO2RR CSV rows without an explicit metric label
        # are interpreted as partial-current-density supervision.
        if rt == "CO2RR":
            return "partial_current_density"
        if allowed and len(allowed) == 1:
            return next(iter(allowed))
        return None

    # Aggressively normalize label for matching.
    key = label.lower()
    key = re.sub(r"\s+", "", key)
    key = key.replace("_", "").replace("-", "").replace("/", "")

    # Generic aliases
    if key in {"eta", "overpotential", "overpotentials", "η", "η10"}:
        if rt in {"HER", "OER", "HzOR"}:
            return "overpotential_10mAcm-2"
        if rt == "UOR":
            return "potential_10mAcm-2"
        # Fallback to reaction default.
        if allowed and len(allowed) == 1:
            return next(iter(allowed))
        return None

    if key in {"potential"}:
        if rt == "UOR":
            return "potential_10mAcm-2"
        if rt == "ORR":
            # Some tables call E1/2 a "potential".
            return "half_wave_potential"
        if allowed and len(allowed) == 1:
            return next(iter(allowed))
        return None

    if key in {"e12", "e1/2", "halfwavepotential", "halfwave", "e1_2", "e1-2"}:
        return "half_wave_potential"

    if key in {"j0", "exchangecurrentdensity", "exchange-current-density"}:
        return "exchange_current_density"

    if key in {"massactivity"}:
        return "mass_activity"

    if key in {"fe", "faradaicefficiency", "faradicefficiency", "faradaiceff"}:
        return "faradaic_efficiency"

    if key in {"partialcurrentdensity", "jpartial", "partialj"}:
        return "partial_current_density"

    # Final fallback: if allowed set is a single metric, trust reaction_type scope.
    if allowed and len(allowed) == 1:
        return next(iter(allowed))

    return None


_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def parse_current_density_to_ma_cm2(value: Any) -> Decimal | None:
    """Parse strings like '10 mA cm-2' / '0.01 A cm-2' into mA cm^-2.

    This is used only for validating conditions (e.g., eta@10 mA cm^-2).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.translate(_DASH_TRANSLATION)
    s = s.replace("·", " ").replace("⋅", " ").replace("•", " ")

    m = _NUM_PREFIX_RE.match(s)
    if not m:
        return None
    try:
        num = Decimal(m.group("num"))
    except InvalidOperation:
        return None

    rest = s[m.end() :].strip().lower()
    # Normalize common unit variants.
    rest = rest.replace("cm^-2", "cm-2").replace("cm^−2", "cm-2").replace("cm−2", "cm-2")
    rest = rest.replace("/cm2", " cm-2").replace("/cm²", " cm-2").replace("cm²", "cm2")
    rest = re.sub(r"/\s*cm\s*2\b", " cm-2", rest)
    rest = re.sub(r"^(ma|a)(?=cm)", r"\1 ", rest)
    rest = " ".join(rest.split())
    rest = rest.replace("cm2", "cm-2")

    if "cm-2" not in rest:
        return None
    if rest.startswith("ma"):
        return num
    if rest.startswith("a"):
        return num * Decimal("1000")
    return None


@dataclass(frozen=True)
class Eta10ConditionCheck:
    status: str  # "ok" | "unknown" | "mismatch"
    current_density_mA_cm_2: str | None = None


def check_eta10_condition(condition_text: Any) -> Eta10ConditionCheck:
    """Check whether a condition column indicates 10 mA cm^-2 (eta10)."""
    if condition_text is None:
        return Eta10ConditionCheck(status="unknown")
    s = str(condition_text).strip()
    if not s:
        return Eta10ConditionCheck(status="unknown")
    cd = parse_current_density_to_ma_cm2(s)
    if cd is None:
        return Eta10ConditionCheck(status="unknown")
    # Exact-match on 10 mA cm^-2 in canonical units.
    if cd == Decimal("10"):
        return Eta10ConditionCheck(status="ok", current_density_mA_cm_2="10")
    return Eta10ConditionCheck(status="mismatch", current_density_mA_cm_2=str(cd))
