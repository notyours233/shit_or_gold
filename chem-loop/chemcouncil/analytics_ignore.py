from __future__ import annotations

from typing import Any, Iterable

IGNORE_PAYLOAD_KEY = "analytics_ignore_csv_rows"


def normalize_csv_row_index(value: Any) -> int | None:
    """Parse a positive (1-based) CSV row index from arbitrary input."""
    if value is None:
        return None
    try:
        i = int(str(value).strip())
    except Exception:
        return None
    if i <= 0:
        return None
    return i


def parse_ignore_request_body(body: Any) -> list[int]:
    """Parse a request body into a list of CSV row indices.

    Supported shapes:
    - {"csv_row_index": 3}
    - {"csv_row_indices": [3, 8, 12]}
    - [3, 8, 12]
    """
    if body is None:
        return []

    if isinstance(body, list):
        idxs = [normalize_csv_row_index(x) for x in body]
        return sorted({x for x in idxs if x is not None})

    if isinstance(body, dict):
        if "csv_row_indices" in body:
            raw = body.get("csv_row_indices")
            if isinstance(raw, list):
                idxs = [normalize_csv_row_index(x) for x in raw]
                return sorted({x for x in idxs if x is not None})
            return []
        if "csv_row_index" in body:
            idx = normalize_csv_row_index(body.get("csv_row_index"))
            return [idx] if idx is not None else []

    return []


def read_ignore_csv_rows(payload: dict[str, Any] | None) -> set[int]:
    if not isinstance(payload, dict):
        return set()
    raw = payload.get(IGNORE_PAYLOAD_KEY)
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for x in raw:
        idx = normalize_csv_row_index(x)
        if idx is not None:
            out.add(idx)
    return out


def apply_ignore_csv_rows(
    payload: dict[str, Any],
    *,
    add: Iterable[int] | None = None,
    remove: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Update ignore list inside a job payload (in-place) and return a summary."""
    add = list(add or [])
    remove = list(remove or [])

    cur = read_ignore_csv_rows(payload)
    before = set(cur)

    for x in add:
        idx = normalize_csv_row_index(x)
        if idx is None:
            continue
        cur.add(idx)

    for x in remove:
        idx = normalize_csv_row_index(x)
        if idx is None:
            continue
        cur.discard(idx)

    payload[IGNORE_PAYLOAD_KEY] = sorted(cur)
    return {
        "ignore_key": IGNORE_PAYLOAD_KEY,
        "before": sorted(before),
        "after": sorted(cur),
        "added": sorted(set(cur) - set(before)),
        "removed": sorted(set(before) - set(cur)),
    }

