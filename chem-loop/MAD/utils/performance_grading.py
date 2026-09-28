import re
from typing import Any, Dict, Optional, Tuple

from utils.material_properties import PROPERTY_METRICS, canonical_property_type, display_name
from utils.task_types import canonical_reaction_type


# Grade labels (kept consistent across reactions)
GRADE_OUTSTANDING = "Outstanding"
GRADE_GOOD = "Good"
GRADE_FAIR = "Fair"
GRADE_POOR = "Poor"
GRADE_TERRIBLE = "Terrible"
GRADE_UNCALIBRATED = "Uncalibrated"


# Per-reaction metric metadata (normalized output unit + display name)
_METRIC_META: Dict[str, Dict[str, str]] = {
    "HER": {"metric_name": "\u03b710", "unit": "mV"},
    "OER": {"metric_name": "\u03b710", "unit": "mV"},
    "ORR": {"metric_name": "E1/2", "unit": "V"},
    "HOR": {"metric_name": "j0", "unit": "mA cm-2"},
    "UOR": {"metric_name": "E@10", "unit": "V"},
    "EOR": {"metric_name": "Mass activity", "unit": "A mgmetal-1"},
    "HZOR": {"metric_name": "E@10", "unit": "mV"},
    "O5H": {"metric_name": "FE", "unit": "%"},
    "CO2RR": {"metric_name": "Product FE", "metric_key": "faradaic_efficiency", "unit": "%"},
}
_METRIC_META.update({k: dict(v) for k, v in PROPERTY_METRICS.items()})


# Threshold tables. Boundaries overlap in the original definitions; we resolve ties by
# checking from the better grade to the worse grade (as specified in the plan).
_LOWER_IS_BETTER: Dict[str, Tuple[Tuple[float, str], ...]] = {
    "HER": (
        (50.0, GRADE_OUTSTANDING),
        (150.0, GRADE_GOOD),
        (200.0, GRADE_FAIR),
        (250.0, GRADE_POOR),
    ),
    "OER": (
        (200.0, GRADE_OUTSTANDING),
        (270.0, GRADE_GOOD),
        (350.0, GRADE_FAIR),
        (400.0, GRADE_POOR),
    ),
    "UOR": (
        (1.3, GRADE_OUTSTANDING),
        (1.4, GRADE_GOOD),
        (1.45, GRADE_FAIR),
        (1.6, GRADE_POOR),
    ),
    "HZOR": (
        (-50.0, GRADE_OUTSTANDING),
        (0.0, GRADE_GOOD),
        (100.0, GRADE_FAIR),
        (200.0, GRADE_POOR),
    ),
}

_HIGHER_IS_BETTER: Dict[str, Tuple[Tuple[float, str], ...]] = {
    "ORR": (
        (0.92, GRADE_OUTSTANDING),
        (0.85, GRADE_GOOD),
        (0.75, GRADE_FAIR),
        (0.65, GRADE_POOR),
    ),
    "HOR": (
        (3.0, GRADE_OUTSTANDING),
        (1.5, GRADE_GOOD),
        (1.0, GRADE_FAIR),
        (0.65, GRADE_POOR),
    ),
    "EOR": (
        (20.0, GRADE_OUTSTANDING),
        (5.0, GRADE_GOOD),
        (1.0, GRADE_FAIR),
        (0.5, GRADE_POOR),
    ),
    "O5H": (
        (95.0, GRADE_OUTSTANDING),
        (90.0, GRADE_GOOD),
        (85.0, GRADE_FAIR),
        (80.0, GRADE_POOR),
    ),
}


_PROPERTY_HIGHER_IS_BETTER: Dict[str, Tuple[Tuple[float, str], ...]] = {
    "photothermal_conversion_efficiency": (
        (90.0, GRADE_OUTSTANDING),
        (70.0, GRADE_GOOD),
        (50.0, GRADE_FAIR),
        (20.0, GRADE_POOR),
    ),
    "conductivity": (
        (1.0e7, GRADE_OUTSTANDING),
        (1.0e6, GRADE_GOOD),
        (1.0e4, GRADE_FAIR),
        (1.0e-2, GRADE_POOR),
    ),
    "thermal_conductivity": (
        (400.0, GRADE_OUTSTANDING),
        (200.0, GRADE_GOOD),
        (50.0, GRADE_FAIR),
        (1.0, GRADE_POOR),
    ),
    "ferromagnetism": (
        (200.0, GRADE_OUTSTANDING),
        (150.0, GRADE_GOOD),
        (50.0, GRADE_FAIR),
        (20.0, GRADE_POOR),
    ),
    "ferrimagnetism": (
        (100.0, GRADE_OUTSTANDING),
        (50.0, GRADE_GOOD),
        (10.0, GRADE_FAIR),
        (1.0, GRADE_POOR),
    ),
    "antiferromagnetism": (
        (600.0, GRADE_OUTSTANDING),
        (400.0, GRADE_GOOD),
        (300.0, GRADE_FAIR),
        (100.0, GRADE_POOR),
    ),
    "photocatalytic_h2o2": (
        (30.0, GRADE_OUTSTANDING),
        (10.0, GRADE_GOOD),
        (2.0, GRADE_FAIR),
        (0.5, GRADE_POOR),
    ),
    "furfural_hydrogenation": (
        (95.0, GRADE_OUTSTANDING),
        (85.0, GRADE_GOOD),
        (70.0, GRADE_FAIR),
        (60.0, GRADE_POOR),
    ),
    "thermoelectric": (
        (2.0, GRADE_OUTSTANDING),
        (1.0, GRADE_GOOD),
        (0.5, GRADE_FAIR),
        (0.1, GRADE_POOR),
    ),
}

_PROPERTY_LOWER_IS_BETTER: Dict[str, Tuple[Tuple[float, str], ...]] = {
    "antibacterial": (
        (10.0, GRADE_OUTSTANDING),
        (50.0, GRADE_GOOD),
        (100.0, GRADE_FAIR),
        (500.0, GRADE_POOR),
    ),
}

_CO2RR_PRODUCT_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("CH3COOH", (r"\bCH3COOH\b", r"\bacetate\b", r"\bacetic\s+acid\b")),
    ("C2H5OH", (r"\bC2H5OH\b", r"\bethanol\b")),
    ("C2H4", (r"\bC2H4\b", r"\bethylene\b")),
    ("HCOOH", (r"\bHCOOH\b", r"\bHCOO-?\b", r"\bformate\b", r"\bformic\s+acid\b")),
    ("CH4", (r"\bCH4\b", r"\bmethane\b")),
    ("C2+", (r"(?<![A-Za-z0-9])C2\+(?![A-Za-z0-9])", r"\bC2\+\s*products?\b")),
    ("C3+", (r"(?<![A-Za-z0-9])C3\+(?![A-Za-z0-9])", r"\bC3\+\s*products?\b")),
    ("CO", (r"\bCO\b", r"\bcarbon\s+monoxide\b")),
)

_CO2RR_FE_THRESHOLDS: Dict[str, Tuple[Tuple[float, str], ...]] = {
    "CO": (
        (95.0, GRADE_OUTSTANDING),
        (90.0, GRADE_GOOD),
        (80.0, GRADE_FAIR),
        (75.0, GRADE_POOR),
    ),
    "HCOOH": (
        (95.0, GRADE_OUTSTANDING),
        (90.0, GRADE_GOOD),
        (80.0, GRADE_FAIR),
        (75.0, GRADE_POOR),
    ),
    "CH4": (
        (75.0, GRADE_OUTSTANDING),
        (55.0, GRADE_GOOD),
        (40.0, GRADE_FAIR),
        (35.0, GRADE_POOR),
    ),
    "C2H5OH": (
        (65.0, GRADE_OUTSTANDING),
        (50.0, GRADE_GOOD),
        (40.0, GRADE_FAIR),
        (35.0, GRADE_POOR),
    ),
    "C2H4": (
        (65.0, GRADE_OUTSTANDING),
        (50.0, GRADE_GOOD),
        (40.0, GRADE_FAIR),
        (35.0, GRADE_POOR),
    ),
    "CH3COOH": (
        (70.0, GRADE_OUTSTANDING),
        (55.0, GRADE_GOOD),
        (45.0, GRADE_FAIR),
        (40.0, GRADE_POOR),
    ),
    "C2+": (
        (80.0, GRADE_OUTSTANDING),
        (70.0, GRADE_GOOD),
        (60.0, GRADE_FAIR),
        (55.0, GRADE_POOR),
    ),
    "C3+": (
        (45.0, GRADE_OUTSTANDING),
        (30.0, GRADE_GOOD),
        (15.0, GRADE_FAIR),
        (5.0, GRADE_POOR),
    ),
}

_CO2RR_PARTIAL_CURRENT_THRESHOLDS: Tuple[Tuple[float, str], ...] = (
    (500.0, GRADE_OUTSTANDING),
    (100.0, GRADE_GOOD),
    (40.0, GRADE_FAIR),
    (20.0, GRADE_POOR),
)


def normalize_text(text: str) -> str:
    """
    Normalize common Unicode variants to make parsing resilient.

    Keep this conservative: only normalize characters that frequently appear in copied
    scientific text and break regex matching on Windows terminals.
    """
    s = str(text or "")
    if not s:
        return ""

    # Dashes/minus variants -> ASCII hyphen-minus
    for ch in ["\u2212", "\u2013", "\u2014", "\u207b"]:
        s = s.replace(ch, "-")

    # Superscript digits -> ASCII digits (helps "cm\u207b\u00b2", "mg\u207b\u00b9", etc.)
    s = s.replace("\u00b9", "1").replace("\u00b2", "2").replace("\u00b3", "3")

    # Unify common exponent notations (best-effort)
    s = re.sub(r"(?i)cm\s*\^\s*-?\s*2\b", "cm-2", s)
    s = re.sub(r"(?i)mg\s*\^\s*-?\s*1\b", "mg-1", s)

    return s


def _grade_higher_is_better(value: float, thresholds: Tuple[Tuple[float, str], ...]) -> str:
    for thr, grade in thresholds:
        if float(value) >= float(thr):
            return grade
    return GRADE_TERRIBLE


def _canonical_co2rr_product(*texts: object) -> Optional[str]:
    for text in texts:
        raw = normalize_text(str(text or ""))
        if not raw:
            continue
        for canonical, patterns in _CO2RR_PRODUCT_PATTERNS:
            for pat in patterns:
                if re.search(pat, raw, flags=re.IGNORECASE):
                    return canonical
    return None


def _extract_products_line_text(claim: str) -> Optional[str]:
    s = normalize_text(claim)
    m = re.search(r"(?im)^\s*Products?\s*:\s*([^\n\r]*)", s)
    if not m:
        return None
    raw = str(m.group(1) or "").strip()
    return raw or None


def extract_co2rr_product(claim: str, metric_text: Optional[str] = None) -> Optional[str]:
    """Return the main CO2RR product label when it can be inferred."""
    return _canonical_co2rr_product(_extract_products_line_text(claim), metric_text, claim)


def _normalize_percent_value(value: float) -> float:
    v = float(value)
    if 0.0 <= v <= 1.0:
        return v * 100.0
    return v


def grade_co2rr_faradaic_efficiency(value: float, product: Optional[str] = None) -> str:
    """Grade CO2RR product-specific Faradaic efficiency (%) by product class."""
    prod = _canonical_co2rr_product(product) or "CO"
    thresholds = _CO2RR_FE_THRESHOLDS.get(prod, _CO2RR_FE_THRESHOLDS["CO"])
    return _grade_higher_is_better(_normalize_percent_value(float(value)), thresholds)


def grade_co2rr_partial_current_density(value: float) -> str:
    """Grade optional CO2RR partial current density by magnitude in mA cm-2."""
    return _grade_higher_is_better(abs(float(value)), _CO2RR_PARTIAL_CURRENT_THRESHOLDS)


def extract_reaction_type(claim: str) -> Optional[str]:
    s = normalize_text(claim)
    m = re.search(r"(?i)\bReaction\s*Type\s*:\s*([A-Za-z0-9_\-+\s]+)", s)
    if not m:
        return None
    raw = re.split(r"[\n\r;]", str(m.group(1) or "").strip(), maxsplit=1)[0].strip()
    rt = canonical_reaction_type(raw)
    return rt if rt in _METRIC_META else None


def extract_property_type(claim: str) -> Optional[str]:
    s = normalize_text(claim)
    label_patterns = [
        r"(?i)\bProperty\s*Type\s*:\s*([A-Za-z0-9_\-\s]+)",
        r"(?i)\bApplication\s*Type\s*:\s*([A-Za-z0-9_\-\s]+)",
        r"(?i)\bApplication\s*:\s*([A-Za-z0-9_\-\s]+)",
        r"(?i)\bTarget\s*Property\s*:\s*([A-Za-z0-9_\-\s]+)",
        # Compatibility: old prompt/rendering uses Reaction Type for the task label.
        r"(?i)\bReaction\s*Type\s*:\s*([A-Za-z0-9_\-\s]+)",
    ]
    for pat in label_patterns:
        m = re.search(pat, s)
        if not m:
            continue
        raw = str(m.group(1) or "").strip()
        raw = re.split(r"[\n\r;]", raw, maxsplit=1)[0].strip()
        prop = canonical_property_type(raw)
        if prop:
            return prop
    return None


def extract_last_performance_metrics_text(claim: str) -> Optional[str]:
    """
    Extract the last "Performance Metrics ...: <text>" segment from a claim.

    - Works for both "Performance Metrics:" and "Performance Metrics (xxx):"
    - Picks the last occurrence to handle claims that include multiple metric lines.
    """
    s = normalize_text(claim)
    matches = list(
        re.finditer(
            r"(?i)Performance\s*Metrics[^\n\r:]*:\s*([^\n\r]*)",
            s,
        )
    )
    if not matches:
        return None
    raw = str(matches[-1].group(1) or "").strip()
    return raw or None


def grade_value(reaction_type: str, value: float) -> str:
    prop = canonical_property_type(reaction_type)
    if prop and prop in _PROPERTY_LOWER_IS_BETTER:
        for thr, grade in _PROPERTY_LOWER_IS_BETTER[prop]:
            if value <= float(thr):
                return grade
        return GRADE_TERRIBLE
    if prop and prop in _PROPERTY_HIGHER_IS_BETTER:
        for thr, grade in _PROPERTY_HIGHER_IS_BETTER[prop]:
            if value >= float(thr):
                return grade
        return GRADE_TERRIBLE
    rt = str(reaction_type or "").strip().upper()
    if rt == "CO2RR":
        return grade_co2rr_faradaic_efficiency(float(value))

    if rt in _LOWER_IS_BETTER:
        for thr, grade in _LOWER_IS_BETTER[rt]:
            if value <= float(thr):
                return grade
        return GRADE_TERRIBLE

    if rt in _HIGHER_IS_BETTER:
        for thr, grade in _HIGHER_IS_BETTER[rt]:
            if value >= float(thr):
                return grade
        return GRADE_TERRIBLE

    # Unknown reaction type: cannot grade.
    return GRADE_TERRIBLE


def _to_float(x: str) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _extract_value_unit_near_10ma(text: str) -> Optional[Tuple[float, str]]:
    """
    Extract a (value, unit) pair for V/mV metrics, preferring matches near "10 mA".
    """
    t = normalize_text(text)
    if not t:
        return None

    num = r"([-+]?\d+(?:\.\d+)?)"
    pm = r"(?:\+/-|\u00b1)"
    unit = r"(mV|V)"

    # Value before/after the "10 mA" anchor, with optional "+/-" uncertainty.
    pats = [
        rf"{num}\s*{pm}\s*\d+(?:\.\d+)?\s*{unit}\b[^\n\r]{{0,160}}\b10\s*mA\b",
        rf"\b10\s*mA\b[^\n\r]{{0,160}}{num}\s*{pm}\s*\d+(?:\.\d+)?\s*{unit}\b",
        rf"{num}\s*{unit}\b[^\n\r]{{0,160}}\b10\s*mA\b",
        rf"\b10\s*mA\b[^\n\r]{{0,160}}{num}\s*{unit}\b",
    ]
    for pat in pats:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if not m:
            continue
        val = _to_float(m.group(1))
        u = str(m.group(2) or "").strip()
        if val is None or not u:
            continue
        return val, u
    return None


def _extract_first_value_with_unit(text: str, unit_pat: str) -> Optional[Tuple[float, str]]:
    t = normalize_text(text)
    m = re.search(rf"([-+]?\d+(?:\.\d+)?)\s*{unit_pat}\b", t, flags=re.IGNORECASE)
    if not m:
        return None
    val = _to_float(m.group(1))
    if val is None:
        return None
    u = str(m.group(2) or "").strip() if m.lastindex and m.lastindex >= 2 else ""
    return val, u


def _extract_current_density(text: str, prefer_label: Optional[str] = None) -> Optional[Tuple[float, str]]:
    """
    Extract a current density like "<val> mA cm-2" or "<val> A/cm^2".
    Returns (value, unit) where unit is "mA" or "A" (caller normalizes).
    """
    t = normalize_text(text)
    if not t:
        return None

    num = r"([-+]?\d+(?:\.\d+)?)"
    unit = r"(mA|A)"
    cm2 = r"cm\s*(?:\^\s*)?-?\s*2\b"

    if prefer_label:
        # Accept small variations like j0 / j₀.
        label = str(prefer_label)
        m = re.search(rf"(?i){label}\s*[:=]\s*{num}\s*{unit}\s*(?:/|\s*){cm2}", t)
        if m:
            v = _to_float(m.group(1))
            u = str(m.group(2) or "").strip()
            if v is not None and u:
                return v, u

    # Generic current density pattern.
    m = re.search(rf"(?i){num}\s*{unit}\s*(?:/|\s*){cm2}", t)
    if not m:
        return None
    v = _to_float(m.group(1))
    u = str(m.group(2) or "").strip()
    if v is None or not u:
        return None
    return v, u


def parse_co2rr_partial_current_density(raw_metric_text: str) -> Tuple[Optional[float], Optional[str]]:
    """Parse optional CO2RR partial current density into mA cm-2."""
    res = _extract_current_density(raw_metric_text)
    if res is None:
        return None, None
    v, u = res
    if str(u).strip().lower() == "a":
        return v * 1000.0, "mA cm-2"
    return v, "mA cm-2"


def _extract_mass_activity(text: str) -> Optional[Tuple[float, str]]:
    """
    Extract mass activity like "<val> mA/mg" or "<val> A mg-1".
    Returns (value, unit) where unit is "mA" or "A" (caller normalizes to A/mg).
    """
    t = normalize_text(text)
    if not t:
        return None

    num = r"([-+]?\d+(?:\.\d+)?)"
    unit = r"(mA|A)"

    # Prefer "mass activity" labeled forms.
    m = re.search(rf"(?i)mass\s*activity[^\n\r]{{0,60}}?{num}\s*{unit}\s*(?:/|\s*)mg", t)
    if not m:
        # Generic A/mg style.
        m = re.search(rf"(?i){num}\s*{unit}\s*(?:/|\s*)mg", t)
    if not m:
        return None

    v = _to_float(m.group(1))
    u = str(m.group(2) or "").strip()
    if v is None or not u:
        return None
    return v, u


def _extract_percent_value(text: str) -> Optional[Tuple[float, str]]:
    t = normalize_text(text)
    if not t:
        return None
    m = re.search(r"(?i)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*%", t)
    if m:
        v = _to_float(m.group(1))
        return (v, "%") if v is not None else None

    m = re.search(r"(?i)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", t)
    if not m:
        return None
    v = _to_float(m.group(1))
    if v is None:
        return None
    if 0.0 <= v <= 1.0:
        v *= 100.0
    return v, "%"


def _extract_co2rr_faradaic_efficiency(text: str, product_hint: Optional[str] = None) -> Optional[Tuple[float, str, Optional[str]]]:
    t = normalize_text(text)
    if not t:
        return None

    num = r"([-+]?\d+(?:\.\d+)?)"
    product = _canonical_co2rr_product(product_hint, t)
    patterns = [
        rf"(?i)\bFE\s*\(\s*([^)]+?)\s*\)\s*(?:[=:]|\bis\b|\bof\b)?\s*{num}\s*%",
        rf"(?i)\bFaradaic\s*efficiency\s*\(\s*([^)]+?)\s*\)\s*(?:[=:]|\bis\b|\bof\b)?\s*{num}\s*%",
        rf"(?i)([A-Za-z0-9+\- ]{{1,32}}?)\s*(?:Faradaic\s*efficiency|\bFE\b)\s*(?:[=:]|\bis\b|\bof\b)?\s*{num}\s*%",
        rf"(?i)(?:\bFE\b|Faradaic\s*efficiency)\s*(?:[=:]|\bis\b|\bof\b)?\s*{num}\s*%\s*(?:for|towards?|to)?\s*([A-Za-z0-9+\- ]{{0,32}})",
        rf"(?i){num}\s*%\s*(?:\bFE\b|Faradaic\s*efficiency)(?:\s*(?:for|towards?|to)\s*([A-Za-z0-9+\- ]{{0,32}}))?",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if not m:
            continue
        groups = [g for g in m.groups()]
        value_raw = None
        product_raw = None
        for g in groups:
            if g is None:
                continue
            if re.fullmatch(num, str(g).strip()):
                value_raw = str(g).strip()
            elif not product_raw:
                product_raw = str(g).strip()
        if value_raw is None:
            continue
        v = _to_float(value_raw)
        if v is None:
            continue
        product = _canonical_co2rr_product(product_raw, product_hint, t) or product
        return _normalize_percent_value(v), "%", product
    return None


def _extract_conductivity(text: str) -> Optional[Tuple[float, str]]:
    t = normalize_text(text)
    if not t:
        return None

    # Normalize copied unit variants without changing the numerical value.
    t = t.replace("S/m", "S m-1").replace("s/m", "S m-1")
    t = t.replace("mS/m", "mS m-1").replace("ms/m", "mS m-1")
    t = t.replace("S/cm", "S cm-1").replace("s/cm", "S cm-1")
    t = t.replace("mS/cm", "mS cm-1").replace("ms/cm", "mS cm-1")
    num = r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    m = re.search(
        rf"{num}\s*(mS|S)\s*(?:/|\s+)?\s*(cm|m)\s*(?:\^?\s*-?\s*1|[-]1)?\b",
        t,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    v = _to_float(m.group(1))
    prefix = str(m.group(2) or "").strip().lower()
    denom = str(m.group(3) or "").strip().lower()
    if v is None or not prefix or not denom:
        return None

    if prefix == "ms":
        v *= 1.0e-3
    if denom == "cm":
        v *= 100.0
    return v, "S/m"


def _extract_thermal_conductivity(text: str) -> Optional[Tuple[float, str]]:
    t = normalize_text(text)
    if not t:
        return None
    t = re.sub(r"(?i)W\s*/\s*\(\s*m\s*K\s*\)", "W m-1 K-1", t)
    t = re.sub(r"(?i)W\s*/\s*m\s*K\b", "W m-1 K-1", t)
    t = re.sub(r"(?i)W\s*/\s*mK\b", "W m-1 K-1", t)
    num = r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    patterns = [
        rf"{num}\s*W\s*m\s*(?:\^?\s*-?\s*1|[-]1)?\s*K\s*(?:\^?\s*-?\s*1|[-]1)?\b",
        rf"{num}\s*W\s*/\s*\(?\s*m\s*K\s*\)?\b",
    ]
    for pat in patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if not m:
            continue
        v = _to_float(m.group(1))
        if v is not None:
            return v, "W m-1 K-1"
    return None


def _extract_saturation_magnetization(text: str) -> Optional[Tuple[float, str]]:
    t = normalize_text(text)
    if not t:
        return None
    t = t.replace("emu/g", "emu g-1").replace("EMU/g", "emu g-1")
    t = t.replace("A m^2/kg", "A m2 kg-1").replace("A m2/kg", "A m2 kg-1")
    t = t.replace("A m^2 kg-1", "A m2 kg-1")
    num = r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    patterns = [
        rf"{num}\s*emu\s*(?:/|\s+)?\s*g\s*(?:\^?\s*-?\s*1|[-]1)?\b",
        rf"{num}\s*A\s*m\s*2\s*(?:/|\s+)?\s*kg\s*(?:\^?\s*-?\s*1|[-]1)?\b",
    ]
    for pat in patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if not m:
            continue
        v = _to_float(m.group(1))
        if v is not None:
            return v, "emu/g"
    return None


def _extract_temperature_k(text: str) -> Optional[Tuple[float, str]]:
    t = normalize_text(text)
    if not t:
        return None
    m = re.search(r"(?i)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*K\b", t)
    if not m:
        return None
    v = _to_float(m.group(1))
    return (v, "K") if v is not None else None


def _parse_property_metric_value(prop: str, raw_metric_text: str) -> Tuple[Optional[float], Optional[str]]:
    p = canonical_property_type(prop)
    if not p:
        return None, None
    if p == "photothermal_conversion_efficiency":
        res = _extract_percent_value(raw_metric_text)
    elif p == "conductivity":
        res = _extract_conductivity(raw_metric_text)
    elif p == "thermal_conductivity":
        res = _extract_thermal_conductivity(raw_metric_text)
    elif p in {"ferromagnetism", "ferrimagnetism"}:
        res = _extract_saturation_magnetization(raw_metric_text)
    elif p == "antiferromagnetism":
        res = _extract_temperature_k(raw_metric_text)
    elif p == "antibacterial":
        match = re.search(
            r"(?i)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(ppm|ug\s*/\s*mL|mg\s*/\s*L)\b",
            normalize_text(raw_metric_text),
        )
        if match:
            value = _to_float(match.group(1))
            res = (value, "ppm") if value is not None else None
        else:
            res = None
    elif p == "thermoelectric":
        match = re.search(
            r"(?i)(?:\bz\s*T\b|figure\s+of\s+merit)?\s*[:=]?\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)",
            normalize_text(raw_metric_text),
        )
        value = _to_float(match.group(1)) if match else None
        res = (value, "dimensionless") if value is not None else None
    elif p in {"photocatalytic_h2o2", "furfural_hydrogenation"}:
        res = _extract_percent_value(raw_metric_text)
    else:
        res = None
    if res is None:
        return None, None
    return res


def parse_metric_value(rt: str, raw_metric_text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse and normalize a metric point estimate for a given reaction type.

    Returns:
        (metric_value, metric_unit) in the normalized unit expected by the grading rules.
    """
    prop = canonical_property_type(rt)
    if prop:
        return _parse_property_metric_value(prop, raw_metric_text)

    reaction = str(rt or "").strip().upper()
    t = normalize_text(raw_metric_text)
    if not reaction or not t:
        return None, None

    # ---- V/mV metrics ----
    if reaction in {"HER", "OER", "UOR", "HZOR", "ORR"}:
        # Prefer "10 mA" anchored extraction for @10 mA metrics.
        val_unit = None
        if reaction in {"HER", "OER", "UOR", "HZOR"}:
            val_unit = _extract_value_unit_near_10ma(t)

        if val_unit is None:
            # ORR: prefer E1/2/half-wave tagged values.
            if reaction == "ORR":
                m = re.search(
                    r"(?i)(?:E\s*1/2|E1/2|E_\s*1/2|half[-\s]*wave(?:\s*potential)?)\s*[:=]?\s*"
                    r"([-+]?\d+(?:\.\d+)?)\s*(mV|V)\b",
                    t,
                )
                if m:
                    v = _to_float(m.group(1))
                    u = str(m.group(2) or "").strip()
                    if v is not None and u:
                        val_unit = (v, u)

        if val_unit is None:
            # Fallback: first mV/V occurrence.
            m = re.search(r"(?i)([-+]?\d+(?:\.\d+)?)\s*(mV|V)\b", t)
            if m:
                v = _to_float(m.group(1))
                u = str(m.group(2) or "").strip()
                if v is not None and u:
                    val_unit = (v, u)

        if val_unit is None:
            return None, None

        v, u = val_unit
        u_norm = u.lower()
        if reaction in {"HER", "OER", "HZOR"}:
            # Normalize to mV.
            if u_norm == "v":
                return v * 1000.0, "mV"
            return v, "mV"

        # ORR/UOR normalize to V.
        if u_norm == "mv":
            return v / 1000.0, "V"
        return v, "V"

    if reaction == "CO2RR":
        product = extract_co2rr_product("", t)
        res = _extract_co2rr_faradaic_efficiency(t, product_hint=product)
        if res is None:
            return None, None
        v, u, _product = res
        return v, u

    # ---- Current density metrics ----
    if reaction == "HOR":
        # Prefer j0-labeled extraction for HOR.
        res = _extract_current_density(t, prefer_label=r"j0|j\u2080")
        if res is None:
            return None, None
        v, u = res
        if str(u).strip().lower() == "a":
            return v * 1000.0, "mA cm-2"
        return v, "mA cm-2"

    # ---- Mass activity ----
    if reaction == "EOR":
        res = _extract_mass_activity(t)
        if res is None:
            return None, None
        v, u = res
        if str(u).strip().lower() == "ma":
            return v / 1000.0, "A mgmetal-1"
        return v, "A mgmetal-1"

    # ---- Faradaic efficiency ----
    if reaction == "O5H":
        # Prefer explicit percent.
        m = re.search(r"(?i)([-+]?\d+(?:\.\d+)?)\s*%", t)
        if m:
            v = _to_float(m.group(1))
            return (v, "%") if v is not None else (None, None)

        # Prefer FE-labeled numeric.
        m = re.search(r"(?i)(?:\bFE\b|faradaic\s*efficiency)[^0-9\-+]{0,20}([-+]?\d+(?:\.\d+)?)", t)
        if not m:
            m = re.search(r"(?i)([-+]?\d+(?:\.\d+)?)", t)
        if not m:
            return None, None

        v = _to_float(m.group(1))
        if v is None:
            return None, None
        if 0.0 <= v <= 1.0:
            return v * 100.0, "%"
        return v, "%"

    return None, None


def evaluate_claim(claim: str, reaction_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Evaluate a final claim and return a normalized metric + grade.

    Returns None if we cannot extract a single point estimate with a known unit.
    """
    s = normalize_text(claim)
    prop_given = canonical_property_type(reaction_type)
    prop = prop_given or extract_property_type(s)
    if prop:
        task_key = prop
    else:
        rt_given = canonical_reaction_type(reaction_type) or str(reaction_type or "").strip().upper()
        task_key = rt_given if rt_given and rt_given != "UNKNOWN" else (extract_reaction_type(s) or "")
        task_key = task_key.strip().upper()

    if not task_key or task_key not in _METRIC_META:
        return None

    raw_metric_text = extract_last_performance_metrics_text(s)
    if not raw_metric_text:
        return None

    if task_key == "CO2RR":
        product = extract_co2rr_product(s, raw_metric_text)
        fe_res = _extract_co2rr_faradaic_efficiency(raw_metric_text, product_hint=product)
        if fe_res is None:
            return None
        metric_value, metric_unit, product_from_metric = fe_res
        product = product_from_metric or product
        if not product:
            return None
        grade = grade_co2rr_faradaic_efficiency(float(metric_value), product=product)
        partial_value, partial_unit = parse_co2rr_partial_current_density(raw_metric_text)
        out = {
            "reaction_type": "CO2RR",
            "product": product,
            "metric_key": "faradaic_efficiency",
            "metric_name": f"FE({product})",
            "metric_value": float(metric_value),
            "metric_unit": str(metric_unit),
            "grade": grade,
            "raw_metric_text": str(raw_metric_text),
        }
        if partial_value is not None and partial_unit:
            out.update(
                {
                    "partial_current_density": float(partial_value),
                    "partial_current_density_unit": str(partial_unit),
                    "partial_current_density_grade": grade_co2rr_partial_current_density(float(partial_value)),
                }
            )
        return out

    metric_value, metric_unit = parse_metric_value(task_key, raw_metric_text)
    if metric_value is None or not metric_unit:
        return None

    grade = grade_value(task_key, float(metric_value))
    meta = _METRIC_META.get(task_key, {})
    out = {
        "reaction_type": task_key,
        "metric_name": meta.get("metric_name", ""),
        "metric_value": float(metric_value),
        "metric_unit": str(metric_unit),
        "grade": grade,
        "grade_calibrated": grade != GRADE_UNCALIBRATED,
        "raw_metric_text": str(raw_metric_text),
    }
    prop_out = canonical_property_type(task_key)
    if prop_out:
        out.update(
            {
                "property_type": prop_out,
                "application_name": display_name(prop_out),
                "metric_key": meta.get("metric_key", ""),
            }
        )
    return out


def metric_direction(reaction_type: str) -> Optional[str]:
    """
    Return the optimization direction for the reaction's normalized metric.

    Returns:
        "lower" if lower metric values are better,
        "higher" if higher metric values are better,
        None if unknown reaction type / not gradable.
    """
    rt = str(reaction_type or "").strip().upper()
    rt = canonical_reaction_type(rt) or rt
    if rt in _LOWER_IS_BETTER:
        return "lower"
    if rt in _HIGHER_IS_BETTER:
        return "higher"
    prop = canonical_property_type(reaction_type)
    if prop in _PROPERTY_LOWER_IS_BETTER:
        return "lower"
    if prop:
        return "higher"
    return None


def grade_rank(grade: str) -> int:
    """
    Map a grade label to an integer rank for sorting.

    Outstanding > Good > Fair > Poor > Terrible. Unknown grades map to -1.
    """
    g = str(grade or "").strip().lower()
    if not g:
        return -1

    mapping = {
        GRADE_OUTSTANDING.lower(): 4,
        GRADE_GOOD.lower(): 3,
        GRADE_FAIR.lower(): 2,
        GRADE_POOR.lower(): 1,
        GRADE_TERRIBLE.lower(): 0,
    }
    return int(mapping.get(g, -1))
