from __future__ import annotations


def normalize_metal_symbol(symbol: str) -> str:
    """Normalize an element symbol-like token to canonical casing.

    Examples:
    - "pt" -> "Pt"
    - "NI" -> "Ni"
    - "Fe" -> "Fe"
    """
    s = (symbol or "").strip()
    if not s:
        return ""
    if len(s) == 1:
        return s.upper()
    return s[0].upper() + s[1:].lower()


def normalize_metals(metals: list[str]) -> list[str]:
    """Normalize, deduplicate, and sort a list of metal symbols."""
    normalized = [normalize_metal_symbol(m) for m in (metals or [])]
    normalized = [m for m in normalized if m]
    # Deduplicate after normalization, then sort for stable ordering.
    return sorted(set(normalized))

