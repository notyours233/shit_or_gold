#!/usr/bin/env python3
"""Generate per-reaction metric distribution reports for processed chem_performance JSONL.

This is an offline analysis helper:
  - Input:  data/processed/chem_performance/*.jsonl (one reaction per file)
  - Output: one Markdown + one JSON report per reaction, plus an index.md

By default this script generates SVG plots without third-party dependencies.
If you request PNG output, it will use matplotlib (optional dependency).
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def _slugify(s: str) -> str:
    """Create an ASCII-safe slug for filenames."""
    s = (s or "").strip()
    if not s:
        return "unknown"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return slug or "unknown"


def _svg_escape(s: str) -> str:
    return html.escape(s, quote=True)


def _repo_root() -> Path:
    # scripts/analysis/<this_file>.py -> scripts -> <repo_root>
    return Path(__file__).resolve().parents[2]


def _safe_float_prefix(value: Any) -> float | None:
    """Parse the leading numeric literal from a value (string/number)."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Preserve NaN/inf filtering.
        f = float(value)
        if not math.isfinite(f):
            return None
        return f
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None

    # Normalize common unicode minus variants so regex can match.
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")

    m = _NUM_PREFIX_RE.match(s)
    if not m:
        return None
    num_s = m.group("num").replace(",", "")
    try:
        f = float(num_s)
    except ValueError:
        return None
    if not math.isfinite(f):
        return None
    return f


def _quantile_sorted(xs_sorted: list[float], q: float) -> float:
    """Linear-interpolated quantile for 0<=q<=1."""
    if not xs_sorted:
        raise ValueError("empty")
    if q <= 0:
        return xs_sorted[0]
    if q >= 1:
        return xs_sorted[-1]
    n = len(xs_sorted)
    if n == 1:
        return xs_sorted[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs_sorted[lo]
    w = pos - lo
    return xs_sorted[lo] * (1 - w) + xs_sorted[hi] * w


def _basic_stats(xs: list[float]) -> dict[str, float]:
    xs_sorted = sorted(xs)
    q05 = _quantile_sorted(xs_sorted, 0.05)
    q25 = _quantile_sorted(xs_sorted, 0.25)
    q50 = _quantile_sorted(xs_sorted, 0.50)
    q75 = _quantile_sorted(xs_sorted, 0.75)
    q95 = _quantile_sorted(xs_sorted, 0.95)
    mean = statistics.fmean(xs_sorted)
    # sample stdev if n>1; else 0
    stdev = statistics.stdev(xs_sorted) if len(xs_sorted) > 1 else 0.0
    return {
        "min": xs_sorted[0],
        "p05": q05,
        "p25": q25,
        "median": q50,
        "mean": mean,
        "p75": q75,
        "p95": q95,
        "max": xs_sorted[-1],
        "stdev": stdev,
        "n": float(len(xs_sorted)),
    }


def _choose_bins(xs: list[float], *, clamp: tuple[int, int] = (5, 50)) -> int:
    n = len(xs)
    if n <= 1:
        return 1
    xs_sorted = sorted(xs)
    q25 = _quantile_sorted(xs_sorted, 0.25)
    q75 = _quantile_sorted(xs_sorted, 0.75)
    iqr = q75 - q25
    xmin, xmax = xs_sorted[0], xs_sorted[-1]
    if xmax <= xmin:
        return 1
    if iqr <= 0:
        # Fallback: sqrt rule
        bins = int(math.ceil(math.sqrt(n)))
    else:
        # Freedman-Diaconis
        bw = 2 * iqr / (n ** (1 / 3))
        if bw <= 0:
            bins = int(math.ceil(math.sqrt(n)))
        else:
            bins = int(math.ceil((xmax - xmin) / bw))
    bins = max(clamp[0], min(clamp[1], bins))
    return bins


def _histogram(xs: list[float], *, bins: int | None = None, force_range: tuple[float, float] | None = None) -> dict[str, Any]:
    if not xs:
        return {"bins": [], "counts": []}
    if bins is None:
        bins = _choose_bins(xs)

    if force_range is not None:
        xmin, xmax = force_range
    else:
        xmin, xmax = min(xs), max(xs)

    if xmax <= xmin:
        return {"bins": [xmin, xmax], "counts": [len(xs)]}

    width = (xmax - xmin) / bins
    # Keep a stable, monotonic edge list.
    edges = [xmin + i * width for i in range(bins + 1)]
    counts = [0 for _ in range(bins)]

    # last bin is inclusive of xmax
    for x in xs:
        if x <= xmin:
            idx = 0
        elif x >= xmax:
            idx = bins - 1
        else:
            idx = int((x - xmin) / width)
            if idx >= bins:
                idx = bins - 1
        counts[idx] += 1

    return {"bins": edges, "counts": counts}


def _ascii_hist(hist: dict[str, Any], *, width: int = 40, fmt: str = "{:.4g}") -> str:
    edges: list[float] = hist.get("bins") or []
    counts: list[int] = hist.get("counts") or []
    if not edges or not counts:
        return "(no data)"
    max_c = max(counts) if counts else 0
    if max_c <= 0:
        max_c = 1
    lines: list[str] = []
    for i, c in enumerate(counts):
        lo = edges[i]
        hi = edges[i + 1]
        bar_len = int(round((c / max_c) * width))
        bar = "#" * bar_len
        lines.append(f"[{fmt.format(lo)}, {fmt.format(hi)}): {c:5d} {bar}")
    return "\n".join(lines)


def _maybe_import_matplotlib():
    """Import matplotlib lazily (only required for PNG output)."""
    try:
        import matplotlib  # type: ignore

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt  # type: ignore

        # Better defaults for headless rendering.
        plt.rcParams["figure.dpi"] = 180
        plt.rcParams["savefig.dpi"] = 180
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["font.family"] = "DejaVu Sans"
        return plt
    except Exception as e:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "PNG plots requested but matplotlib is not available. "
            "Install it in a venv and re-run, e.g.:\n"
            "  python3 -m venv .venv\n"
            "  . .venv/bin/activate\n"
            "  python -m pip install matplotlib\n"
            "  python <this_script> --plot_format png\n"
        ) from e


def _plot_histogram_png(
    hist: dict[str, Any],
    *,
    title: str,
    subtitle: str | None,
    x_label: str,
    out_path: Path,
    mean: float | None = None,
    median: float | None = None,
) -> None:
    plt = _maybe_import_matplotlib()
    edges: list[float] = hist.get("bins") or []
    counts: list[int] = hist.get("counts") or []

    fig, ax = plt.subplots(figsize=(9.0, 4.2))

    if edges and counts:
        widths = [edges[i + 1] - edges[i] for i in range(len(counts))]
        ax.bar(
            edges[:-1],
            counts,
            width=widths,
            align="edge",
            color="#4C78A8",
            edgecolor="white",
            linewidth=0.5,
            alpha=0.85,
            label="hist",
        )
    else:
        ax.text(0.5, 0.5, "(no data)", ha="center", va="center", transform=ax.transAxes)

    # KDE overlay (scaled to "count" axis) when we have enough samples.
    try:
        kde = hist.get("kde")  # optional precomputed {x:[], y:[]}
        if kde and kde.get("x") and kde.get("y"):
            ax.plot(kde["x"], kde["y"], color="#E45756", linewidth=2.0, label="kde")
    except Exception:
        pass

    if median is not None and math.isfinite(median):
        ax.axvline(median, color="#F58518", linewidth=2, label="median")
    if mean is not None and math.isfinite(mean):
        ax.axvline(mean, color="#54A24B", linewidth=2, label="mean")
    if (mean is not None and math.isfinite(mean)) or (median is not None and math.isfinite(median)):
        ax.legend(loc="best", frameon=False)

    ax.set_title(title, fontsize=12)
    if subtitle:
        ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, ha="left", va="bottom", fontsize=9, color="#333")
    ax.set_xlabel(x_label)
    ax.set_ylabel("count")
    ax.grid(axis="y", linestyle="-", linewidth=0.6, color="#ddd")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _plot_bar_png(
    labels: list[str],
    counts: list[int],
    *,
    title: str,
    x_label: str,
    out_path: Path,
) -> None:
    plt = _maybe_import_matplotlib()
    fig, ax = plt.subplots(figsize=(9.0, 4.6))

    xs = list(range(len(labels)))
    ax.bar(xs, counts, color="#4C78A8")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_title(title, fontsize=12)
    ax.set_xlabel(x_label)
    ax.set_ylabel("count")
    ax.grid(axis="y", linestyle="-", linewidth=0.6, color="#ddd")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _plot_barh_png(
    labels: list[str],
    counts: list[int],
    *,
    title: str,
    out_path: Path,
    x_label: str = "count",
) -> None:
    plt = _maybe_import_matplotlib()
    # Dynamic height: keep it readable for longer label lists.
    fig_h = max(3.2, 0.36 * len(labels) + 1.4)
    fig, ax = plt.subplots(figsize=(9.0, fig_h))

    ys = list(range(len(labels)))
    ax.barh(ys, counts, color="#4C78A8")
    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()  # highest count on top if labels are already sorted
    ax.set_title(title, fontsize=12)
    ax.set_xlabel(x_label)
    ax.grid(axis="x", linestyle="-", linewidth=0.6, color="#ddd")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _topk_with_other(items: list[tuple[str, int]], *, top_k: int) -> tuple[list[str], list[int]]:
    """Return labels/counts for a bar plot, folding tail into OTHER if needed."""
    if top_k <= 0 or len(items) <= top_k:
        labels = [k for k, _ in items]
        counts = [int(v) for _, v in items]
        return labels, counts
    head = items[:top_k]
    other = sum(int(v) for _, v in items[top_k:])
    labels = [k for k, _ in head] + ["OTHER"]
    counts = [int(v) for _, v in head] + [other]
    return labels, counts


def _plot_overview_counts_grid_png(
    panels: list[dict[str, Any]],
    *,
    out_path: Path,
    ncols: int = 3,
    title: str = "Chem Performance: Count Distributions Overview",
) -> None:
    """Make a single big PNG containing 9 subplots (one per reaction)."""
    plt = _maybe_import_matplotlib()
    n = len(panels)
    if n == 0:
        return
    nrows = int(math.ceil(n / ncols))

    fig_w = 6.2 * ncols
    fig_h = 4.6 * nrows
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h))
    # Flatten axes for easy indexing.
    if hasattr(axes, "flat"):
        # numpy.ndarray of Axes
        axes_flat = list(axes.flat)
    else:
        # Single Axes
        axes_flat = [axes]

    for ax in axes_flat:
        ax.set_visible(False)

    for i, p in enumerate(panels):
        ax = axes_flat[i]
        ax.set_visible(True)
        labels: list[str] = p["labels"]
        counts: list[int] = p["counts"]
        rxn = p.get("reaction_type") or "UNKNOWN"
        kind = p.get("kind") or ""
        n_records = p.get("n_records")

        ys = list(range(len(labels)))
        ax.barh(ys, counts, color="#4C78A8")
        ax.set_yticks(ys)
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.grid(axis="x", linestyle="-", linewidth=0.6, color="#ddd")
        ax.set_xlabel("count", fontsize=10)
        ax.tick_params(axis="x", labelsize=9)

        title_line = rxn
        if kind == "product_counts":
            title_line += " (product counts)"
        else:
            title_line += " (metric counts)"
        ax.set_title(title_line, fontsize=12)

        if n_records is not None:
            ax.text(
                0.99,
                0.01,
                f"n_records={n_records}",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=9,
                color="#333",
            )

    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _maybe_import_numpy():
    try:
        import numpy as np  # type: ignore

        return np
    except Exception as e:  # pragma: no cover - env-dependent
        raise RuntimeError("numpy is required for KDE/hist overview plots (it should come with matplotlib).") from e


def _kde_counts_curve(
    xs: list[float],
    *,
    xmin: float,
    xmax: float,
    bin_width: float,
    grid_n: int = 240,
) -> tuple[list[float], list[float]] | None:
    """Compute Gaussian KDE scaled to histogram counts (so it overlays count histogram nicely)."""
    if len(xs) < 3:
        return None
    if xmax <= xmin:
        return None
    np = _maybe_import_numpy()
    arr = np.asarray(xs, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = int(arr.size)
    if n < 3:
        return None

    std = float(arr.std(ddof=1)) if n > 1 else 0.0
    if not math.isfinite(std) or std <= 0:
        return None

    # Silverman's rule of thumb for Gaussian KDE bandwidth
    h = 1.06 * std * (n ** (-1 / 5))
    if not math.isfinite(h) or h <= 0:
        return None

    grid = np.linspace(xmin, xmax, grid_n)
    # (grid_n, n) broadcast; OK for our dataset sizes.
    z = (grid[:, None] - arr[None, :]) / h
    dens = np.exp(-0.5 * z * z).mean(axis=1) / (h * math.sqrt(2 * math.pi))

    # Scale density -> expected counts per bin (density * n * bin_width)
    y = dens * n * float(bin_width)
    return grid.tolist(), y.tolist()


def _select_metric_unit_for_overview(
    rows: list[dict[str, Any]],
    reaction_type: str,
) -> tuple[str, str, list[float], int]:
    """Pick a single (metric_key, unit, values, out_of_range_count) for the overview histogram grid."""
    # Default preference per reaction. unit=None means "pick the most common unit group".
    preferred: dict[str, tuple[str, str | None]] = {
        "OER": ("overpotential_10mAcm-2", "mV"),
        "ORR": ("half_wave_potential", "V"),
        "UOR": ("potential_10mAcm-2", "V"),
        "CO2RR": ("partial_current_density", "mA cm-2"),
        "EOR": ("mass_activity", None),
        "HER": ("overpotential_10mAcm-2", "mV"),
        "HOR": ("exchange_current_density", "mA cm-2"),
        "HzOR": ("overpotential_10mAcm-2", "mV"),
        "O5H": ("faradaic_efficiency", "fraction_0_to_1"),
    }

    # Build metric->unit->values
    metric_unit_vals: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        metrics_gt = r.get("metrics_gt") or {}
        units = r.get("units") or {}
        for k, v_str in metrics_gt.items():
            u = units.get(k, "unknown")
            v = _safe_float_prefix(v_str)
            if v is None:
                continue
            metric_unit_vals.setdefault(str(k), {}).setdefault(str(u), []).append(float(v))

    if not metric_unit_vals:
        # Fallback: empty
        return "unknown", "unknown", [], 0

    pref_key, pref_unit = preferred.get(reaction_type, (None, None))  # type: ignore[assignment]

    # Resolve metric key
    metric_key: str
    if pref_key and pref_key in metric_unit_vals:
        metric_key = pref_key
    else:
        # Choose the most frequent metric key overall.
        metric_key = max(metric_unit_vals.keys(), key=lambda k: sum(len(vs) for vs in metric_unit_vals[k].values()))

    unit_map = metric_unit_vals[metric_key]
    unit: str
    if pref_unit and pref_unit in unit_map:
        unit = pref_unit
    else:
        unit = max(unit_map.keys(), key=lambda u: len(unit_map[u]))

    xs_all = unit_map[unit]
    out_of_range = 0
    xs = xs_all
    if unit == "fraction_0_to_1":
        out_of_range = sum(1 for x in xs_all if x < 0.0 or x > 1.0)
        xs = [x for x in xs_all if 0.0 <= x <= 1.0]

    return metric_key, unit, xs, out_of_range


def _plot_overview_hist_grid_png(
    panels: list[dict[str, Any]],
    *,
    out_path: Path,
    ncols: int = 3,
    title: str = "Chem Performance Metric Distributions (9 reactions)",
) -> None:
    plt = _maybe_import_matplotlib()
    n = len(panels)
    if n == 0:
        return
    nrows = int(math.ceil(n / ncols))
    fig_w = 6.2 * ncols
    fig_h = 4.6 * nrows
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h))
    axes_flat = list(axes.flat) if hasattr(axes, "flat") else [axes]

    for ax in axes_flat:
        ax.set_visible(False)

    for i, p in enumerate(panels):
        ax = axes_flat[i]
        ax.set_visible(True)
        hist = p["hist"]
        edges: list[float] = hist.get("bins") or []
        counts: list[int] = hist.get("counts") or []
        rxn = p["reaction_type"]
        metric_key = p["metric_key"]
        unit = p["unit"]
        n_numeric = p["n_numeric"]
        out_of_range = p.get("out_of_range", 0)

        if edges and counts:
            widths = [edges[j + 1] - edges[j] for j in range(len(counts))]
            ax.bar(
                edges[:-1],
                counts,
                width=widths,
                align="edge",
                color="#4C78A8",
                edgecolor="white",
                linewidth=0.5,
                alpha=0.85,
            )

            kde = hist.get("kde")
            if kde and kde.get("x") and kde.get("y"):
                ax.plot(kde["x"], kde["y"], color="#E45756", linewidth=2.0)

        else:
            ax.text(0.5, 0.5, "(no data)", ha="center", va="center", transform=ax.transAxes)

        subtitle = f"n={n_numeric}"
        if unit == "fraction_0_to_1":
            subtitle += f", out_of_range={out_of_range}"

        ax.set_title(f"{rxn}: {metric_key}", fontsize=12)
        ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, ha="left", va="bottom", fontsize=9, color="#333")
        ax.set_xlabel(f"{metric_key} ({unit})", fontsize=10)
        ax.set_ylabel("count", fontsize=10)
        ax.grid(axis="y", linestyle="-", linewidth=0.6, color="#ddd")
        ax.tick_params(axis="both", labelsize=9)

    # Global legend (avoid per-subplot clutter).
    try:
        from matplotlib.lines import Line2D  # type: ignore
        from matplotlib.patches import Patch  # type: ignore

        handles = [
            Patch(facecolor="#4C78A8", edgecolor="white", label="histogram"),
            Line2D([0], [0], color="#E45756", linewidth=2.0, label="KDE"),
        ]
        fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.985, 0.965), frameon=False)
    except Exception:
        pass

    fig.suptitle(title, fontsize=14, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _plot_overview_metric_keysets_grid_png(
    panels: list[dict[str, Any]],
    *,
    out_path: Path,
    ncols: int = 3,
    title: str = "Chem Performance: Metric-Keyset Distribution (9 reactions)",
) -> None:
    plt = _maybe_import_matplotlib()
    n = len(panels)
    if n == 0:
        return
    nrows = int(math.ceil(n / ncols))
    fig_w = 6.2 * ncols
    # A bit taller to fit multi-line x tick labels cleanly.
    fig_h = 5.2 * nrows
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h))
    axes_flat = list(axes.flat) if hasattr(axes, "flat") else [axes]

    for ax in axes_flat:
        ax.set_visible(False)

    for i, p in enumerate(panels):
        ax = axes_flat[i]
        ax.set_visible(True)
        rxn = p["reaction_type"]
        n_records = p["n_records"]
        combo_items: list[tuple[str, int]] = p["combo_items"]
        k_summary: str = p["k_summary"]

        # Swap axes vs the previous horizontal bar version:
        # - x: keyset categories (formatted with line breaks)
        # - y: counts
        def _wrap_label(lbl: str) -> str:
            # "k=2: a + b" -> "k=2\na\n+\nb"
            if ": " in lbl:
                head, rest = lbl.split(": ", 1)
                parts = [p.strip() for p in rest.split(" + ")]
                return head + "\n" + "\n+\n".join(parts)
            return lbl

        labels = [_wrap_label(lbl) for lbl, _ in combo_items]
        counts = [int(c) for _, c in combo_items]
        xs = list(range(len(labels)))
        ax.bar(xs, counts, color="#4C78A8")
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=9)
        ax.grid(axis="y", linestyle="-", linewidth=0.6, color="#ddd")
        ax.set_ylabel("count", fontsize=10)
        ax.tick_params(axis="y", labelsize=9)
        ax.margins(x=0.06)

        ax.set_title(rxn, fontsize=12)
        # Put summary INSIDE the subplot (avoid inter-subplot overlap).
        ax.text(
            0.02,
            0.98,
            f"n_records={n_records}\n{k_summary}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="#333",
            bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none", "pad": 2},
        )

    fig.suptitle(title, fontsize=14, y=0.99)
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)

def _svg_histogram(
    hist: dict[str, Any],
    *,
    title: str,
    subtitle: str | None,
    x_label: str,
    width: int = 900,
    height: int = 420,
    mean: float | None = None,
    median: float | None = None,
) -> str:
    """Render a simple histogram as SVG (no third-party deps)."""
    edges: list[float] = hist.get("bins") or []
    counts: list[int] = hist.get("counts") or []

    # Layout
    ml, mr, mt, mb = 70, 20, 55, 60
    pw = max(10, width - ml - mr)
    ph = max(10, height - mt - mb)

    if edges and len(edges) >= 2:
        xmin, xmax = float(edges[0]), float(edges[-1])
    else:
        xmin, xmax = 0.0, 1.0
    if xmax <= xmin:
        xmax = xmin + 1.0

    max_c = max(counts) if counts else 0
    if max_c <= 0:
        max_c = 1

    def x_map(x: float) -> float:
        return ml + (float(x) - xmin) / (xmax - xmin) * pw

    def y_map_count(c: float) -> float:
        # count -> y coordinate
        return mt + ph - (float(c) / max_c) * ph

    # Tick helpers
    def fmt_tick(v: float) -> str:
        if abs(v) >= 1e6 or (abs(v) > 0 and abs(v) < 1e-4):
            return f"{v:.4g}"
        return f"{v:.6f}".rstrip("0").rstrip(".")

    y_ticks = [0, int(round(max_c * 0.25)), int(round(max_c * 0.5)), int(round(max_c * 0.75)), int(max_c)]
    # Ensure unique & sorted.
    y_ticks = sorted({t for t in y_ticks if t >= 0})

    # Choose x ticks: for [0,1] range show quarters, else show quintiles.
    if abs(xmin - 0.0) < 1e-12 and abs(xmax - 1.0) < 1e-12:
        x_ticks = [0.0, 0.25, 0.5, 0.75, 1.0]
    else:
        x_ticks = [xmin, xmin + 0.25 * (xmax - xmin), xmin + 0.5 * (xmax - xmin), xmin + 0.75 * (xmax - xmin), xmax]

    # Begin SVG
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append(
        "<style>"
        ".axis{stroke:#333;stroke-width:1}"
        ".grid{stroke:#ddd;stroke-width:1}"
        ".bar{fill:#4C78A8}"
        ".tick{font:12px sans-serif;fill:#333}"
        ".title{font:16px sans-serif;font-weight:600;fill:#111}"
        ".subtitle{font:12px sans-serif;fill:#333}"
        ".label{font:12px sans-serif;fill:#111}"
        ".line-mean{stroke:#54A24B;stroke-width:2}"
        ".line-median{stroke:#F58518;stroke-width:2}"
        "</style>"
    )
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>')

    # Title/subtitle
    parts.append(f'<text class="title" x="{ml}" y="24">{_svg_escape(title)}</text>')
    if subtitle:
        parts.append(f'<text class="subtitle" x="{ml}" y="42">{_svg_escape(subtitle)}</text>')

    # Grid + y ticks
    for t in y_ticks:
        y = y_map_count(t)
        parts.append(f'<line class="grid" x1="{ml}" y1="{y:.2f}" x2="{ml+pw}" y2="{y:.2f}"/>')
        parts.append(f'<text class="tick" x="{ml-8}" y="{y+4:.2f}" text-anchor="end">{t}</text>')

    # Axes
    parts.append(f'<line class="axis" x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}"/>')
    parts.append(f'<line class="axis" x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}"/>')

    # Bars (use uniform spacing based on bin count, not x_map, to keep consistent even if edges are odd)
    if counts:
        n_bins = len(counts)
        bin_px = pw / n_bins
        for i, c in enumerate(counts):
            x0 = ml + i * bin_px
            x1 = ml + (i + 1) * bin_px
            bw = (x1 - x0) * 0.88
            bx = x0 + (x1 - x0) * 0.06
            by = y_map_count(c)
            bh = (mt + ph) - by
            parts.append(f'<rect class="bar" x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}"/>')
    else:
        parts.append(f'<text class="subtitle" x="{ml}" y="{mt + ph/2:.2f}">(no data)</text>')

    # X ticks
    for v in x_ticks:
        x = x_map(v)
        parts.append(f'<line class="grid" x1="{x:.2f}" y1="{mt}" x2="{x:.2f}" y2="{mt+ph}"/>')
        parts.append(f'<text class="tick" x="{x:.2f}" y="{mt+ph+18}" text-anchor="middle">{_svg_escape(fmt_tick(v))}</text>')

    # Mean/median markers
    def maybe_marker(val: float | None, *, klass: str, label: str, dy: float) -> None:
        if val is None:
            return
        if not (xmin <= val <= xmax):
            return
        x = x_map(val)
        parts.append(f'<line class="{klass}" x1="{x:.2f}" y1="{mt}" x2="{x:.2f}" y2="{mt+ph}"/>')
        parts.append(f'<text class="tick" x="{x+3:.2f}" y="{mt+12+dy:.2f}" text-anchor="start">{_svg_escape(label)}</text>')

    maybe_marker(median, klass="line-median", label="median", dy=0)
    maybe_marker(mean, klass="line-mean", label="mean", dy=14)

    # Axis labels
    parts.append(f'<text class="label" x="{ml+pw/2:.2f}" y="{height-18}" text-anchor="middle">{_svg_escape(x_label)}</text>')
    parts.append(f'<text class="label" x="{ml-50}" y="{mt+ph/2:.2f}" text-anchor="middle" transform="rotate(-90 {ml-50} {mt+ph/2:.2f})">count</text>')

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


@dataclass
class _Example:
    value: float
    value_str: str
    record_id: str | None
    metals: list[str] | None


def _load_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _format_float(x: float) -> str:
    # Compact but stable formatting for markdown tables.
    if abs(x) >= 1e6 or (abs(x) > 0 and abs(x) < 1e-4):
        return f"{x:.4g}"
    return f"{x:.6f}".rstrip("0").rstrip(".")


def analyze_reaction_file(path: Path) -> tuple[dict[str, Any], str]:
    """Return (json_report_dict, markdown_report_text)."""
    return analyze_reaction_file_with_plots(
        path,
        plot_output_dir=None,
        plot_rel_dir=None,
        plot_formats=set(),
        include_metrics_per_record=False,
    )


def analyze_reaction_file_with_plots(
    path: Path,
    *,
    plot_output_dir: Path | None,
    plot_rel_dir: str | None,
    plot_formats: set[str],
    include_metrics_per_record: bool,
) -> tuple[dict[str, Any], str]:
    """Return (json_report_dict, markdown_report_text), optionally writing plots."""
    rows = list(_load_jsonl(path))
    reaction_type = rows[0].get("reaction_type") if rows else None

    # metric -> unit -> accumulator
    metrics: dict[str, dict[str, dict[str, Any]]] = {}
    # Optional CO2RR product breakdown.
    product_values: dict[str, list[float]] = {}

    for r in rows:
        rid = r.get("id")
        metals = r.get("metals")
        metrics_gt = r.get("metrics_gt") or {}
        units = r.get("units") or {}
        product = r.get("product") if r.get("reaction_type") == "CO2RR" else None

        for k, v_str in metrics_gt.items():
            unit = units.get(k, "unknown")
            bucket = metrics.setdefault(k, {}).setdefault(
                unit,
                {
                    "values": [],
                    "examples_min": None,
                    "examples_max": None,
                    "unparsed_examples": [],
                    "n_total": 0,
                },
            )
            bucket["n_total"] += 1
            val = _safe_float_prefix(v_str)
            if val is None:
                # Keep a few examples for debugging.
                if len(bucket["unparsed_examples"]) < 10:
                    bucket["unparsed_examples"].append(
                        {"id": rid, "metals": metals, "value_str": v_str, "unit": unit}
                    )
                continue
            bucket["values"].append(val)
            ex = _Example(value=val, value_str=str(v_str), record_id=rid, metals=metals)
            cur_min: _Example | None = bucket["examples_min"]
            cur_max: _Example | None = bucket["examples_max"]
            if cur_min is None or val < cur_min.value:
                bucket["examples_min"] = ex
            if cur_max is None or val > cur_max.value:
                bucket["examples_max"] = ex

            if product is not None and k == "faradaic_efficiency":
                product_values.setdefault(str(product), []).append(val)

    # Metric-keyset (which metrics are present together) distribution.
    from collections import Counter

    keyset_ctr: Counter[tuple[str, ...]] = Counter()
    for r in rows:
        keys = tuple(sorted((r.get("metrics_gt") or {}).keys()))
        keyset_ctr[tuple(str(k) for k in keys)] += 1
    keyset_size_ctr: Counter[int] = Counter()
    for keys, c in keyset_ctr.items():
        keyset_size_ctr[len(keys)] += int(c)

    # Build JSON report
    json_report: dict[str, Any] = {
        "reaction_type": reaction_type,
        "source_file": path.name,
        "n_records": len(rows),
        "metrics": {},
        "metric_keyset_size_dist": {str(k): int(v) for k, v in sorted(keyset_size_ctr.items())},
        "metric_keysets": [
            {"keys": list(keys), "count": int(c), "k": len(keys)}
            for keys, c in sorted(keyset_ctr.items(), key=lambda kv: kv[1], reverse=True)
        ],
    }

    # Markdown header
    md_lines: list[str] = []
    md_lines.append(f"# Chem Performance Metric Distribution: {path.name}")
    md_lines.append("")
    md_lines.append(f"- reaction_type: `{reaction_type}`")
    md_lines.append(f"- records: `{len(rows)}`")
    md_lines.append("")

    # Optional count plots (metric counts / metrics-per-record / CO2RR product).
    # Currently only implemented for PNG (via matplotlib).
    if plot_output_dir is not None and plot_rel_dir is not None and "png" in plot_formats:
        # Metric totals (presence count per metric key)
        metric_totals: dict[str, int] = {}
        for metric_key, unit_map in metrics.items():
            metric_totals[metric_key] = sum(int(b["n_total"]) for b in unit_map.values())

        # Metrics-per-record distribution (data completeness)
        from collections import Counter

        metrics_per_record = Counter(len((r.get("metrics_gt") or {})) for r in rows)

        json_report.setdefault("plots", {})
        md_lines.append("## Count Distributions")
        md_lines.append("")

        # metrics-per-record plot (optional; can be noisy in presentations)
        if include_metrics_per_record:
            mpr_x = [str(k) for k in sorted(metrics_per_record.keys())]
            mpr_y = [int(metrics_per_record[k]) for k in sorted(metrics_per_record.keys())]
            mpr_name = "metrics_per_record.png"
            _plot_bar_png(
                mpr_x,
                mpr_y,
                title=f"{reaction_type}: metrics per record",
                x_label="#metrics in metrics_gt",
                out_path=plot_output_dir / mpr_name,
            )
            mpr_rel = f"{plot_rel_dir.rstrip('/')}/{mpr_name}"
            json_report["plots"]["metrics_per_record_png"] = {"file": mpr_name, "rel_path": mpr_rel}
            md_lines.append("### Metrics per record")
            md_lines.append("")
            md_lines.append(f"![]({mpr_rel})")
            md_lines.append("")

        # metric key counts plot
        mk_labels = sorted(metric_totals.keys(), key=lambda k: metric_totals[k], reverse=True)
        mk_counts = [metric_totals[k] for k in mk_labels]
        mk_name = "metric_counts.png"
        _plot_bar_png(
            mk_labels,
            mk_counts,
            title=f"{reaction_type}: metric key presence counts",
            x_label="metric key",
            out_path=plot_output_dir / mk_name,
        )
        mk_rel = f"{plot_rel_dir.rstrip('/')}/{mk_name}"
        json_report["plots"]["metric_counts_png"] = {"file": mk_name, "rel_path": mk_rel}
        md_lines.append("### Metric key counts")
        md_lines.append("")
        md_lines.append(f"![]({mk_rel})")
        md_lines.append("")

        # Unit breakdown per metric (helpful when same key has multiple unit strings)
        for metric_key, unit_map in sorted(metrics.items()):
            if len(unit_map) <= 1:
                continue
            unit_counts = sorted(
                [(u, int(b["n_total"])) for u, b in unit_map.items()],
                key=lambda t: t[1],
                reverse=True,
            )
            top_k = 12
            if len(unit_counts) > top_k:
                head = unit_counts[:top_k]
                other = sum(c for _, c in unit_counts[top_k:])
                unit_counts = head + [("OTHER", other)]
            labels = [u for u, _ in unit_counts]
            counts = [c for _, c in unit_counts]
            fname = f"unit_counts__{_slugify(metric_key)}.png"
            _plot_barh_png(
                labels,
                counts,
                title=f"{reaction_type}: unit breakdown for {metric_key}",
                out_path=plot_output_dir / fname,
            )
            rel = f"{plot_rel_dir.rstrip('/')}/{fname}"
            json_report["plots"][f"unit_counts_png__{metric_key}"] = {"file": fname, "rel_path": rel}
            md_lines.append(f"### Unit breakdown: `{metric_key}`")
            md_lines.append("")
            md_lines.append(f"![]({rel})")
            md_lines.append("")

        # CO2RR product distribution
        if reaction_type == "CO2RR":
            prod_ctr = Counter(str(r.get("product")) for r in rows if r.get("product") is not None)
            prod_items = sorted(prod_ctr.items(), key=lambda kv: kv[1], reverse=True)
            labels = [k for k, _ in prod_items]
            counts = [int(v) for _, v in prod_items]
            json_report["product_counts"] = {k: int(v) for k, v in prod_items}
            fname = "product_counts.png"
            _plot_barh_png(
                labels,
                counts,
                title=f"{reaction_type}: product counts",
                out_path=plot_output_dir / fname,
            )
            rel = f"{plot_rel_dir.rstrip('/')}/{fname}"
            json_report["plots"]["product_counts_png"] = {"file": fname, "rel_path": rel}
            md_lines.append("### CO2RR product counts")
            md_lines.append("")
            md_lines.append(f"![]({rel})")
            md_lines.append("")

    # Summary table
    md_lines.append("## Metric Summary")
    md_lines.append("")
    md_lines.append(
        "Notes: for `fraction_0_to_1`, the histogram is computed on values within [0, 1]; "
        "out-of-range values are counted separately (often indicates extraction/unit issues)."
    )
    md_lines.append("")
    md_lines.append("| metric | unit | n_total | n_numeric | n_failed | out_of_range | min | median | mean | max |")
    md_lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")

    # Deterministic ordering
    for metric_key in sorted(metrics.keys()):
        json_report["metrics"].setdefault(metric_key, {"unit_groups": {}})
        for unit in sorted(metrics[metric_key].keys()):
            bucket = metrics[metric_key][unit]
            xs = bucket["values"]
            n_total = int(bucket["n_total"])
            n_num = len(xs)
            n_fail = n_total - n_num

            group_json: dict[str, Any] = {
                "unit": unit,
                "n_total": n_total,
                "n_numeric": n_num,
                "n_failed": n_fail,
                "unparsed_examples": bucket["unparsed_examples"],
            }

            if xs:
                out_of_range = 0
                if unit == "fraction_0_to_1":
                    out_of_range = sum(1 for x in xs if x < 0.0 or x > 1.0)
                st = _basic_stats(xs)
                group_json["stats"] = st

                if unit == "fraction_0_to_1":
                    xs_in = [x for x in xs if 0.0 <= x <= 1.0]
                    xs_out = [x for x in xs if x < 0.0 or x > 1.0]
                    group_json["sanity"] = {
                        "expected_range": [0.0, 1.0],
                        "n_in_range": len(xs_in),
                        "n_out_of_range": len(xs_out),
                    }
                    if xs_in:
                        group_json["stats_in_range"] = _basic_stats(xs_in)
                        hist = _histogram(xs_in, bins=20, force_range=(0.0, 1.0))
                    else:
                        hist = _histogram([], bins=20, force_range=(0.0, 1.0))
                else:
                    hist = _histogram(xs, bins=None, force_range=None)

                # KDE overlay (for PNG plots) uses the same samples as the histogram.
                if "png" in plot_formats and hist.get("bins") and xs:
                    edges = hist["bins"]
                    if isinstance(edges, list) and len(edges) >= 2:
                        xmin = float(edges[0])
                        xmax = float(edges[-1])
                        bw = float(edges[1]) - float(edges[0])
                        xs_for_kde = xs
                        if unit == "fraction_0_to_1":
                            xs_for_kde = [x for x in xs if 0.0 <= x <= 1.0]
                        kde = _kde_counts_curve(xs_for_kde, xmin=xmin, xmax=xmax, bin_width=bw)
                        if kde is not None:
                            kx, ky = kde
                            hist["kde"] = {"x": kx, "y": ky}

                group_json["histogram"] = hist

                # Optional plot outputs (SVG and/or PNG)
                if plot_output_dir is not None and plot_rel_dir is not None and plot_formats:
                    plot_output_dir.mkdir(parents=True, exist_ok=True)
                    unit_slug = _slugify(unit)
                    metric_slug = _slugify(metric_key)

                    # Prefer in-range mean/median for fraction plots.
                    if unit == "fraction_0_to_1" and "stats_in_range" in group_json:
                        mean_v = float(group_json["stats_in_range"]["mean"])
                        median_v = float(group_json["stats_in_range"]["median"])
                    else:
                        mean_v = float(st["mean"])
                        median_v = float(st["median"])

                    subtitle = f"n_numeric={n_num}"
                    if unit == "fraction_0_to_1":
                        subtitle += f", out_of_range={out_of_range}"

                    if "svg" in plot_formats:
                        svg_name = f"{metric_slug}__{unit_slug}.svg"
                        svg_path = plot_output_dir / svg_name
                        svg_rel = f"{plot_rel_dir.rstrip('/')}/{svg_name}"
                        svg = _svg_histogram(
                            hist,
                            title=f"{reaction_type} · {metric_key}",
                            subtitle=subtitle,
                            x_label=f"{metric_key} ({unit})",
                            mean=mean_v,
                            median=median_v,
                        )
                        svg_path.write_text(svg, encoding="utf-8")
                        group_json["plot_svg"] = {"file": svg_name, "rel_path": svg_rel}

                    if "png" in plot_formats:
                        png_name = f"hist__{metric_slug}__{unit_slug}.png"
                        png_path = plot_output_dir / png_name
                        png_rel = f"{plot_rel_dir.rstrip('/')}/{png_name}"
                        _plot_histogram_png(
                            hist,
                            title=f"{reaction_type} · {metric_key}",
                            subtitle=subtitle,
                            x_label=f"{metric_key} ({unit})",
                            out_path=png_path,
                            mean=mean_v,
                            median=median_v,
                        )
                        group_json["plot_png"] = {"file": png_name, "rel_path": png_rel}
                if bucket["examples_min"] is not None:
                    ex_min: _Example = bucket["examples_min"]
                    group_json["example_min"] = {
                        "value": ex_min.value,
                        "value_str": ex_min.value_str,
                        "id": ex_min.record_id,
                        "metals": ex_min.metals,
                    }
                if bucket["examples_max"] is not None:
                    ex_max: _Example = bucket["examples_max"]
                    group_json["example_max"] = {
                        "value": ex_max.value,
                        "value_str": ex_max.value_str,
                        "id": ex_max.record_id,
                        "metals": ex_max.metals,
                    }

                md_lines.append(
                    f"| `{metric_key}` | `{unit}` | {n_total} | {n_num} | {n_fail} | {out_of_range} | "
                    f"{_format_float(st['min'])} | {_format_float(st['median'])} | {_format_float(st['mean'])} | {_format_float(st['max'])} |"
                )
            else:
                md_lines.append(
                    f"| `{metric_key}` | `{unit}` | {n_total} | {n_num} | {n_fail} | - | - | - | - | - |"
                )

            json_report["metrics"][metric_key]["unit_groups"][unit] = group_json

    md_lines.append("")

    # Detailed sections
    md_lines.append("## Details")
    md_lines.append("")
    for metric_key in sorted(metrics.keys()):
        md_lines.append(f"### {metric_key}")
        md_lines.append("")
        for unit in sorted(metrics[metric_key].keys()):
            bucket = metrics[metric_key][unit]
            xs = bucket["values"]
            n_total = int(bucket["n_total"])
            n_num = len(xs)
            n_fail = n_total - n_num
            md_lines.append(f"#### unit: `{unit}`")
            md_lines.append("")
            md_lines.append(f"- n_total: `{n_total}`  n_numeric: `{n_num}`  n_failed: `{n_fail}`")
            if not xs:
                if bucket["unparsed_examples"]:
                    md_lines.append("")
                    md_lines.append("Unparsed examples (up to 10):")
                    md_lines.append("```json")
                    md_lines.append(json.dumps(bucket["unparsed_examples"], ensure_ascii=False, indent=2))
                    md_lines.append("```")
                md_lines.append("")
                continue

            st = _basic_stats(xs)
            md_lines.append(
                "- stats_all: "
                + ", ".join(
                    [
                        f"min={_format_float(st['min'])}",
                        f"p05={_format_float(st['p05'])}",
                        f"p25={_format_float(st['p25'])}",
                        f"median={_format_float(st['median'])}",
                        f"mean={_format_float(st['mean'])}",
                        f"p75={_format_float(st['p75'])}",
                        f"p95={_format_float(st['p95'])}",
                        f"max={_format_float(st['max'])}",
                        f"stdev={_format_float(st['stdev'])}",
                    ]
                )
            )

            # Histogram
            xs_for_hist = xs
            if unit == "fraction_0_to_1":
                xs_in = [x for x in xs if 0.0 <= x <= 1.0]
                xs_out = [x for x in xs if x < 0.0 or x > 1.0]
                md_lines.append(f"- sanity: expected_range=[0,1], in_range=`{len(xs_in)}`, out_of_range=`{len(xs_out)}`")
                if xs_out:
                    md_lines.append(f"  - out_of_range_min={_format_float(min(xs_out))}, out_of_range_max={_format_float(max(xs_out))}")
                if xs_in:
                    st_in = _basic_stats(xs_in)
                    md_lines.append(
                        "- stats_in_range: "
                        + ", ".join(
                            [
                                f"min={_format_float(st_in['min'])}",
                                f"p05={_format_float(st_in['p05'])}",
                                f"p25={_format_float(st_in['p25'])}",
                                f"median={_format_float(st_in['median'])}",
                                f"mean={_format_float(st_in['mean'])}",
                                f"p75={_format_float(st_in['p75'])}",
                                f"p95={_format_float(st_in['p95'])}",
                                f"max={_format_float(st_in['max'])}",
                            ]
                        )
                    )
                xs_for_hist = xs_in

            if unit == "fraction_0_to_1":
                hist = _histogram(xs_for_hist, bins=20, force_range=(0.0, 1.0))
            else:
                hist = _histogram(xs_for_hist, bins=None, force_range=None)
            md_lines.append("")
            md_lines.append("Histogram:")
            md_lines.append("```text")
            md_lines.append(_ascii_hist(hist, width=50, fmt="{:.4g}"))
            md_lines.append("```")

            # Embed plots if present.
            unit_group = json_report["metrics"][metric_key]["unit_groups"][unit]
            plot_png = unit_group.get("plot_png")
            plot_svg = unit_group.get("plot_svg")
            if plot_png is not None:
                md_lines.append("")
                md_lines.append("Plot (PNG):")
                md_lines.append("")
                md_lines.append(f"![]({plot_png['rel_path']})")
            if plot_svg is not None:
                md_lines.append("")
                md_lines.append("Plot (SVG):")
                md_lines.append("")
                md_lines.append(f"![]({plot_svg['rel_path']})")

            # Min/max examples
            ex_min: _Example = bucket["examples_min"]
            ex_max: _Example = bucket["examples_max"]
            md_lines.append("")
            md_lines.append("Example min/max (for quick sanity-check):")
            md_lines.append("```json")
            md_lines.append(
                json.dumps(
                    {
                        "min": {
                            "value": ex_min.value,
                            "value_str": ex_min.value_str,
                            "id": ex_min.record_id,
                            "metals": ex_min.metals,
                        },
                        "max": {
                            "value": ex_max.value,
                            "value_str": ex_max.value_str,
                            "id": ex_max.record_id,
                            "metals": ex_max.metals,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            md_lines.append("```")

            if bucket["unparsed_examples"]:
                md_lines.append("")
                md_lines.append("Unparsed examples (up to 10):")
                md_lines.append("```json")
                md_lines.append(json.dumps(bucket["unparsed_examples"], ensure_ascii=False, indent=2))
                md_lines.append("```")

            md_lines.append("")

    # CO2RR product breakdown (optional, compact)
    if product_values:
        md_lines.append("## CO2RR Product Breakdown (faradaic_efficiency)")
        md_lines.append("")
        md_lines.append("| product | n | median | mean | min | max |")
        md_lines.append("|---|---:|---:|---:|---:|---:|")
        for product, xs in sorted(product_values.items(), key=lambda kv: len(kv[1]), reverse=True)[:20]:
            st = _basic_stats(xs)
            md_lines.append(
                f"| `{product}` | {len(xs)} | {_format_float(st['median'])} | {_format_float(st['mean'])} | {_format_float(st['min'])} | {_format_float(st['max'])} |"
            )
        md_lines.append("")
        json_report["product_breakdown_faradic_efficiency"] = {
            product: {"n": len(xs), "stats": _basic_stats(xs)} for product, xs in product_values.items()
        }

    return json_report, "\n".join(md_lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-reaction metric distribution reports.")
    parser.add_argument(
        "--input_dir",
        type=str,
        default=str(_repo_root() / "data" / "processed" / "chem_performance"),
        help="Directory containing processed reaction JSONL files (default: <repo_root>/data/processed/chem_performance).",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(_repo_root() / "data" / "processed" / "chem_performance" / "metric_distributions"),
        help="Directory to write Markdown/JSON reports.",
    )
    parser.add_argument(
        "--plots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to write plot files and embed them in the Markdown reports (default: true).",
    )
    parser.add_argument(
        "--plot_format",
        type=str,
        choices=["svg", "png", "both"],
        default="svg",
        help="Plot file format to generate when --plots is enabled (default: svg).",
    )
    parser.add_argument(
        "--include_metrics_per_record",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Whether to include the metrics-per-record count distribution (default: false).",
    )
    parser.add_argument(
        "--overview",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to generate a single combined overview PNG (default: true). Requires --plot_format png|both.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = output_dir / "plots"
    if args.plots:
        plots_dir.mkdir(parents=True, exist_ok=True)
    if args.plots and args.plot_format in {"png", "both"}:
        # Validate early so we fail fast with a clear error message.
        _maybe_import_matplotlib()

    # We treat "reaction files" as JSONL that have records with metrics_gt.
    # Ignore large merged dataset JSONLs in this directory by pattern.
    ignore_prefixes = {
        "chem_performance_dataset",
        "chem_performance_v2_",
    }

    candidates = []
    for p in sorted(input_dir.glob("*.jsonl")):
        if any(p.name.startswith(pref) for pref in ignore_prefixes):
            continue
        candidates.append(p)

    index_rows = []
    overview_panels: list[dict[str, Any]] = []
    overview_hist_panels: list[dict[str, Any]] = []
    overview_keyset_panels: list[dict[str, Any]] = []
    for p in candidates:
        stem = p.stem
        plot_out = (plots_dir / stem) if args.plots else None
        plot_rel = f"./plots/{stem}" if args.plots else None
        plot_formats: set[str] = set()
        if args.plots:
            if args.plot_format == "svg":
                plot_formats = {"svg"}
            elif args.plot_format == "png":
                plot_formats = {"png"}
            elif args.plot_format == "both":
                plot_formats = {"svg", "png"}
        report_json, report_md = analyze_reaction_file_with_plots(
            p,
            plot_output_dir=plot_out,
            plot_rel_dir=plot_rel,
            plot_formats=plot_formats,
            include_metrics_per_record=args.include_metrics_per_record,
        )
        stem = p.stem
        out_md = output_dir / f"{stem}.md"
        out_json = output_dir / f"{stem}.json"
        out_md.write_text(report_md, encoding="utf-8")
        out_json.write_text(json.dumps(report_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index_rows.append(
            {
                "reaction_file": p.name,
                "reaction_type": report_json.get("reaction_type"),
                "n_records": report_json.get("n_records"),
                "md": out_md.name,
                "json": out_json.name,
            }
        )

        # Build overview panel data (for one combined big figure).
        rxn = report_json.get("reaction_type")
        if args.overview and args.plots and ("png" in plot_formats):
            if rxn == "CO2RR":
                prod_counts: dict[str, int] = report_json.get("product_counts") or {}
                items = sorted(prod_counts.items(), key=lambda kv: kv[1], reverse=True)
                # CO2RR currently has a small number of product categories; keep all by default.
                labels, counts = _topk_with_other(items, top_k=20)
                overview_panels.append(
                    {
                        "reaction_type": rxn,
                        "kind": "product_counts",
                        "labels": labels,
                        "counts": counts,
                        "n_records": report_json.get("n_records"),
                    }
                )
            else:
                # metric key totals across unit groups
                metric_totals: dict[str, int] = {}
                for metric_key, metric_obj in (report_json.get("metrics") or {}).items():
                    unit_groups = (metric_obj or {}).get("unit_groups") or {}
                    metric_totals[str(metric_key)] = sum(int(g.get("n_total", 0)) for g in unit_groups.values())
                items = sorted(metric_totals.items(), key=lambda kv: kv[1], reverse=True)
                labels = [k for k, _ in items]
                counts = [int(v) for _, v in items]
                overview_panels.append(
                    {
                        "reaction_type": rxn,
                        "kind": "metric_counts",
                        "labels": labels,
                        "counts": counts,
                        "n_records": report_json.get("n_records"),
                    }
                )

            # Overview: pick ONE representative metric distribution per reaction (hist + KDE).
            metrics_obj: dict[str, Any] = report_json.get("metrics") or {}
            if metrics_obj:
                preferred: dict[str, tuple[str, str | None]] = {
                    "OER": ("overpotential_10mAcm-2", "mV"),
                    "ORR": ("half_wave_potential", "V"),
                    "UOR": ("potential_10mAcm-2", "V"),
                    "CO2RR": ("partial_current_density", "mA cm-2"),
                    "EOR": ("mass_activity", None),
                    "HER": ("overpotential_10mAcm-2", "mV"),
                    "HOR": ("exchange_current_density", "mA cm-2"),
                    "HzOR": ("overpotential_10mAcm-2", "mV"),
                    "O5H": ("faradaic_efficiency", "fraction_0_to_1"),
                }
                pref_key, pref_unit = preferred.get(str(rxn), (None, None))  # type: ignore[assignment]

                # Pick metric key
                if pref_key and pref_key in metrics_obj:
                    sel_metric = pref_key
                else:
                    # Use the metric with the largest total n_total across unit groups.
                    def _total_for_metric(k: str) -> int:
                        ug = (metrics_obj.get(k) or {}).get("unit_groups") or {}
                        return sum(int(g.get("n_total", 0)) for g in ug.values())

                    sel_metric = max(metrics_obj.keys(), key=_total_for_metric)

                unit_groups: dict[str, Any] = (metrics_obj.get(sel_metric) or {}).get("unit_groups") or {}
                if not unit_groups:
                    pass
                else:
                    # Pick unit group
                    if pref_unit and pref_unit in unit_groups:
                        sel_unit = pref_unit
                    else:
                        sel_unit = max(unit_groups.keys(), key=lambda u: int((unit_groups[u] or {}).get("n_total", 0)))

                    ug = unit_groups.get(sel_unit) or {}
                    hist = ug.get("histogram") or {}
                    out_of_range = 0
                    sanity = ug.get("sanity") or {}
                    if isinstance(sanity, dict):
                        out_of_range = int(sanity.get("n_out_of_range", 0) or 0)
                    overview_hist_panels.append(
                        {
                            "reaction_type": str(rxn),
                            "metric_key": str(sel_metric),
                            "unit": str(sel_unit),
                            "hist": hist,
                            "n_numeric": int(ug.get("n_numeric", 0) or 0),
                            "out_of_range": out_of_range,
                        }
                    )

            # Overview: metric-keyset distribution (k=1,2,3+ plus which keysets).
            keysets = report_json.get("metric_keysets") or []
            if keysets:
                combo_items: list[tuple[str, int]] = []
                for item in keysets:
                    keys = item.get("keys") or []
                    k = int(item.get("k", len(keys)) or len(keys))
                    cnt = int(item.get("count", 0) or 0)
                    if cnt <= 0:
                        continue
                    label = f"k={k}: " + " + ".join(str(x) for x in keys)
                    combo_items.append((label, cnt))

                # k summary (focus on 1 / 2 / 3+)
                k_dist = report_json.get("metric_keyset_size_dist") or {}
                try:
                    k1 = int(k_dist.get("1", 0) or 0)
                    k2 = int(k_dist.get("2", 0) or 0)
                    k3p = 0
                    for kk, vv in k_dist.items():
                        k_int = int(kk)
                        if k_int >= 3:
                            k3p += int(vv)
                except Exception:
                    k1, k2, k3p = 0, 0, 0
                k_summary = f"k=1:{k1}, k=2:{k2}, k>=3:{k3p}"

                overview_keyset_panels.append(
                    {
                        "reaction_type": str(rxn),
                        "n_records": int(report_json.get("n_records", 0) or 0),
                        "k_summary": k_summary,
                        "combo_items": combo_items,
                    }
                )

    # Write a small index for convenience.
    idx_lines: list[str] = []
    idx_lines.append("# Chem Performance Metric Distributions (Index)")
    idx_lines.append("")
    idx_lines.append(f"- input_dir: `{input_dir}`")
    idx_lines.append(f"- output_dir: `{output_dir}`")
    idx_lines.append("")
    if args.overview and args.plots and args.plot_format in {"png", "both"}:
        idx_lines.append("## Overview Figures")
        idx_lines.append("")
        idx_lines.append("### Counts overview (9 reactions)")
        idx_lines.append("")
        idx_lines.append("![](./counts_overview_9rxn.png)")
        idx_lines.append("")
        idx_lines.append("### One metric per reaction: histogram + KDE (9 reactions)")
        idx_lines.append("")
        idx_lines.append("![](./hist_overview_9rxn_kde.png)")
        idx_lines.append("")
        idx_lines.append("### Metric keysets per record (9 reactions)")
        idx_lines.append("")
        idx_lines.append("![](./metric_keysets_overview_9rxn.png)")
        idx_lines.append("")
    idx_lines.append("| reaction_file | reaction_type | n_records | md | json |")
    idx_lines.append("|---|---|---:|---|---|")
    for r in index_rows:
        idx_lines.append(
            f"| `{r['reaction_file']}` | `{r['reaction_type']}` | {r['n_records']} | `{r['md']}` | `{r['json']}` |"
        )
    idx_lines.append("")
    (output_dir / "index.md").write_text("\n".join(idx_lines), encoding="utf-8")

    # Combined overview figure (PNG only).
    if args.overview and args.plots and args.plot_format in {"png", "both"} and overview_panels:
        # Order panels by a stable, chemistry-friendly sequence.
        rxn_order = ["OER", "ORR", "UOR", "CO2RR", "EOR", "HER", "HOR", "HzOR", "O5H"]
        rank = {r: i for i, r in enumerate(rxn_order)}
        overview_panels_sorted = sorted(overview_panels, key=lambda p: rank.get(p.get("reaction_type"), 999))
        out_overview = output_dir / "counts_overview_9rxn.png"
        _plot_overview_counts_grid_png(
            overview_panels_sorted,
            out_path=out_overview,
            ncols=3,
            title="Chem Performance Count Distributions (9 reactions)",
        )
        print(f"Wrote overview figure to: {out_overview}")

        if overview_hist_panels:
            overview_hist_panels_sorted = sorted(overview_hist_panels, key=lambda p: rank.get(p.get("reaction_type"), 999))
            out_hist = output_dir / "hist_overview_9rxn_kde.png"
            _plot_overview_hist_grid_png(
                overview_hist_panels_sorted,
                out_path=out_hist,
                ncols=3,
                title="Chem Performance: One Metric per Reaction (Histogram + KDE)",
            )
            print(f"Wrote overview figure to: {out_hist}")

        if overview_keyset_panels:
            overview_keyset_panels_sorted = sorted(overview_keyset_panels, key=lambda p: rank.get(p.get("reaction_type"), 999))
            out_keysets = output_dir / "metric_keysets_overview_9rxn.png"
            _plot_overview_metric_keysets_grid_png(
                overview_keyset_panels_sorted,
                out_path=out_keysets,
                ncols=3,
                title="Chem Performance: Metric Keysets per Record (9 reactions)",
            )
            print(f"Wrote overview figure to: {out_keysets}")

    print(f"Wrote {len(index_rows)} reaction reports to: {output_dir}")


if __name__ == "__main__":
    main()
