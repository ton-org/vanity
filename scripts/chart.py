#!/usr/bin/env python3
"""
Generate a benchmark comparison chart from tests/results.json.

Compares ton-community/vanity-contract against ton-org/vanity,
showing speedup factors normalized to 5-character patterns.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.transforms import Bbox

# === Configuration ===

RESULTS_PATH = Path(__file__).resolve().parent.parent / "tests" / "results.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "tests" / "benchmarks.png"

OLD_IMPL = "ton-community/vanity-contract"
NEW_IMPL = "ton-org/vanity"

# Categories in display order (top to bottom)
CATEGORIES = [
    ("start 5 ci", "--start"),
    ("start 5 cs", "--case-sensitive --start"),
    ("end 5 ci", "--end"),
    ("end 5 cs", "--case-sensitive --end"),
]

# Device display order and names
DEVICE_ORDER = ["NVIDIA GeForce RTX 4090", "Apple M2 Max"]
DEVICE_NAMES = {
    "Apple M2 Max": "Apple M2 Max",
    "NVIDIA GeForce RTX 4090": "NVIDIA RTX 4090",
}
DEVICE_COLORS = {
    "NVIDIA GeForce RTX 4090": "#F97316",  # orange
    "Apple M2 Max": "#2563EB",  # blue
}

COLORS = {
    "bg": "#F9FAFB",
    "text": "#1A1A1A",
    "text_muted": "#666666",
    "border": "#E5E7EB",
}


# === Data Structures ===


@dataclass
class BenchmarkResult:
    device: str
    category: str
    old_rate: float
    new_rate: float

    @property
    def speedup(self) -> float:
        if self.old_rate <= 0:
            return float("nan")
        return self.new_rate / self.old_rate


# === Data Loading ===


def load_results() -> dict:
    """Load benchmark results from JSON file."""
    if not RESULTS_PATH.exists():
        raise FileNotFoundError(f"Results file not found: {RESULTS_PATH}")
    return json.loads(RESULTS_PATH.read_text())


def normalize_rate(rate: float, length: int, case_insensitive: bool) -> float:
    """Normalize rate to equivalent 5-character match probability."""
    char_prob = 2 / 64 if case_insensitive else 1 / 64
    current_prob = char_prob**length
    target_prob = char_prob**5
    return rate * (target_prob / current_prob)


def parse_case_name(name: str) -> tuple[str, int, bool] | None:
    """Parse case name like 'start 4 ci' into (position, length, case_insensitive)."""
    name = name.lower()

    length_match = re.search(r"(\d+)", name)
    if not length_match:
        return None
    length = int(length_match.group(1))

    if "start" in name:
        position = "start"
    elif "end" in name:
        position = "end"
    else:
        return None

    case_insensitive = "ci" in name

    return position, length, case_insensitive


def _extract_rates_from_entry(entry: dict) -> dict[str, float]:
    """Extract normalized rates for all categories from a single JSON entry."""
    rates: dict[str, float] = {}

    for case in entry.get("cases", []):
        name = case.get("name", "")
        rate = case.get("rate")

        if not isinstance(rate, (int, float)):
            continue

        parsed = parse_case_name(name)
        if not parsed:
            continue

        position, length, case_insensitive = parsed
        ci_str = "ci" if case_insensitive else "cs"
        category = f"{position} 5 {ci_str}"

        rates[category] = normalize_rate(rate, length, case_insensitive)

    return rates


def extract_rates(entries: list[dict], title: str) -> dict[str, float]:
    """Extract normalized rates for each category from benchmark entries."""
    for entry in entries:
        if entry.get("title") != title:
            continue
        return _extract_rates_from_entry(entry)

    return {}


def extract_latest_new_rates(entries: list[dict]) -> dict[str, float]:
    """
    Extract normalized rates for the "new" implementation as
    the latest entry (by timestamp) per device, excluding the
    old implementation baseline.
    """
    latest_entry: dict | None = None
    latest_ts: float | None = None

    for entry in entries:
        if entry.get("title") == OLD_IMPL:
            continue
        ts = entry.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
            latest_entry = entry

    if latest_entry is None:
        return {}

    return _extract_rates_from_entry(latest_entry)


def build_benchmark_data(raw_data: dict) -> list[BenchmarkResult]:
    """Build list of benchmark results from raw JSON data."""
    results = []

    for device, entries in raw_data.items():
        old_rates = extract_rates(entries, OLD_IMPL)
        # For the "new" implementation, always take the latest
        # entry per device (by timestamp), so charts reflect the
        # most recent benchmark run.
        new_rates = extract_latest_new_rates(entries)

        if not old_rates or not new_rates:
            continue

        for cat_key, _ in CATEGORIES:
            if cat_key in old_rates and cat_key in new_rates:
                results.append(
                    BenchmarkResult(
                        device=device,
                        category=cat_key,
                        old_rate=old_rates[cat_key],
                        new_rate=new_rates[cat_key],
                    )
                )

    return results


# === Plotting ===


def setup_style():
    """Configure matplotlib style."""
    # Fail fast if IBM Plex Sans is unavailable
    font_manager.findfont("IBM Plex Sans", fallback_to_default=False)

    plt.rcParams.update(
        {
            "font.family": "IBM Plex Sans",
            "font.size": 11,
            "figure.facecolor": COLORS["bg"],
            "axes.facecolor": COLORS["bg"],
            "text.color": COLORS["text"],
            "xtick.bottom": False,
            "xtick.top": False,
            "ytick.left": False,
            "ytick.right": False,
            "xtick.major.size": 0,
            "xtick.minor.size": 0,
            "ytick.major.size": 0,
            "ytick.minor.size": 0,
        }
    )


def create_chart(results: list[BenchmarkResult]) -> plt.Figure:
    """Create the benchmark comparison chart."""

    # Get devices in specified order, filtering to those with data
    available_devices = set(r.device for r in results)
    devices = [d for d in DEVICE_ORDER if d in available_devices]

    # Add any devices not in DEVICE_ORDER
    for d in sorted(available_devices):
        if d not in devices:
            devices.append(d)

    n_devices = len(devices)
    n_categories = len(CATEGORIES)

    # Create figure
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=200)

    # Bar layout
    bar_height = 0.38
    bar_gap = 0.08
    group_height = n_devices * bar_height + (n_devices - 1) * bar_gap
    group_gap = 0.6

    # Build lookup for results
    result_lookup = {}
    for r in results:
        result_lookup[(r.category, r.device)] = r

    # Find max speedup for x-axis scaling
    speedups = [r.speedup for r in results if np.isfinite(r.speedup) and r.speedup > 0]
    if not speedups:
        raise ValueError("No valid speedup values found")
    max_speedup = max(speedups)

    # Calculate positions and plot (reversed so first category is at TOP)
    y_positions = {}
    current_y = 0

    for cat_idx, (cat_key, cat_label) in enumerate(reversed(CATEGORIES)):
        group_bottom = current_y

        # Plot bars for each device (in order: first device at top of group)
        for dev_idx, device in enumerate(devices):
            y = current_y + (n_devices - 1 - dev_idx) * (bar_height + bar_gap)
            y_positions[(cat_key, device)] = y

            result = result_lookup.get((cat_key, device))
            if not result:
                continue

            speedup = result.speedup
            if not np.isfinite(speedup) or speedup <= 0:
                continue

            color = DEVICE_COLORS.get(device, "#888888")

            ax.barh(
                y + bar_height / 2,
                speedup - 1,
                left=1,
                height=bar_height,
                color=color,
                alpha=0.92,
                zorder=3,
            )

            # Speedup label
            ax.text(
                speedup * 1.08,
                y + bar_height / 2,
                f"×{speedup:,.0f}",
                va="center",
                ha="left",
                fontsize=9,
                fontweight="600",
                color=COLORS["text"],
                zorder=4,
            )

        # Category label (centered on group)
        group_center = group_bottom + group_height / 2
        ax.text(
            0.9,
            group_center,
            cat_label,
            va="center",
            ha="right",
            fontsize=10,
            fontweight="500",
            fontfamily="monospace",
            color=COLORS["text_muted"],
        )

        current_y += group_height + group_gap

    # Separator lines between groups
    current_y = 0
    for cat_idx in range(n_categories - 1):
        current_y += group_height
        sep_y = current_y + group_gap / 2
        ax.axhline(sep_y, color=COLORS["border"], linewidth=0.8, alpha=0.5, zorder=1)
        current_y += group_gap

    # Baseline at x=1
    ax.axvline(1, color=COLORS["border"], linewidth=1, zorder=1)

    # Configure axes
    ax.set_xscale("log")
    ax.set_xlim(0.7, max_speedup * 1.8)  # More room on right for labels

    total_height = n_categories * group_height + (n_categories - 1) * group_gap
    ax.set_ylim(-0.3, total_height + 0.3)

    # Remove ALL ticks and spines completely
    ax.set_xticks([])
    ax.set_yticks([])
    ax.xaxis.set_ticks_position("none")
    ax.yaxis.set_ticks_position("none")
    ax.tick_params(axis="both", which="both", length=0, width=0)

    for spine in ax.spines.values():
        spine.set_visible(False)

    # Legend - bottom right of axes
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=DEVICE_COLORS.get(d, "#888"), alpha=0.92)
        for d in devices
    ]
    labels = [DEVICE_NAMES.get(d, d) for d in devices]

    # Lock subplot geometry before positioning legend/title so we can derive true axis bounds
    plt.subplots_adjust(top=0.84, bottom=0.04, left=0.26, right=0.94)

    # Legend inset from the figure's bottom-right corner by a fixed pixel cushion
    pad_px = 12
    fig_w_px = fig.get_size_inches()[0] * fig.dpi
    fig_h_px = fig.get_size_inches()[1] * fig.dpi
    pad_fig_x = pad_px / fig_w_px
    pad_fig_y = pad_px / fig_h_px
    legend_anchor = (1 - pad_fig_x, pad_fig_y)

    legend = fig.legend(
        handles,
        labels,
        loc="lower right",
        bbox_to_anchor=legend_anchor,
        bbox_transform=fig.transFigure,
        frameon=False,
        fontsize=10,
        handlelength=1.2,
        handleheight=0.9,
        borderaxespad=0.3,
    )

    # Draw once to compute bounding boxes for centering
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    bboxes = [
        ax.get_tightbbox(renderer),
        legend.get_window_extent(renderer=renderer),
    ]
    content_bbox = Bbox.union(bboxes).transformed(fig.transFigure.inverted())
    content_center_x = (content_bbox.x0 + content_bbox.x1) / 2

    # Title centered over the actual rendered content (handles left/right padding automatically)
    fig.text(
        content_center_x,
        0.965,
        f"{NEW_IMPL} vs {OLD_IMPL}",
        ha="center",
        va="top",
        fontsize=14,
        fontweight="bold",
        color=COLORS["text"],
    )
    fig.text(
        content_center_x,
        0.91,
        "Speedup measured with default settings on prefix and suffix lengths from 4 to 6 characters",
        ha="center",
        va="top",
        fontsize=10,
        color=COLORS["text_muted"],
    )

    return fig


def main():
    setup_style()

    raw_data = load_results()
    results = build_benchmark_data(raw_data)

    if not results:
        raise ValueError("No benchmark data found")

    fig = create_chart(results)
    fig.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight", facecolor=COLORS["bg"])

    print(f"Chart saved to {OUTPUT_PATH}")
    plt.close(fig)


if __name__ == "__main__":
    main()
