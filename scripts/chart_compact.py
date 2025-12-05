#!/usr/bin/env python3
"""
Generate a compact benchmark chart suitable for social media posts.

Creates a visually striking, easy-to-read chart showing the speedup
of ton-org/vanity vs ton-community/vanity-contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image

# === Configuration ===

RESULTS_PATH = Path(__file__).resolve().parent.parent / "tests" / "results.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "tests" / "benchmarks_compact.png"
LOGO_PATH = Path(__file__).resolve().parent / "ton-studio.png"

OLD_IMPL = "ton-community/vanity-contract"
NEW_IMPL = "ton-org/vanity"

# Simplified categories for compact view
COMPACT_CATEGORIES = [
    ("prefix", "Prefix"),
    ("suffix", "Suffix"),
]

DEVICE_ORDER = ["NVIDIA GeForce RTX 4090"]
DEVICE_NAMES = {
    "Apple M2 Max": "M2 Max",
    "NVIDIA GeForce RTX 4090": "RTX 4090",
}
DEVICE_COLORS = {
    "NVIDIA GeForce RTX 4090": "#2563EB",
    "Apple M2 Max": "#2563EB",
}

COLORS = {
    "bg": "#FFFFFF",
    "text": "#1A1A1A",
    "text_muted": "#666666",
    "text_light": "#999999",
    "accent": "#10B981",
    "old_bar": "#D1D5DB",  # Gray for old implementation baseline
}


@dataclass
class CompactResult:
    device: str
    category: str  # "prefix" or "suffix"
    old_rate: float  # Normalized old implementation rate
    new_rate: float  # Normalized new implementation rate

    @property
    def speedup(self) -> float:
        if self.old_rate <= 0:
            return float("nan")
        return self.new_rate / self.old_rate


def load_results() -> dict:
    if not RESULTS_PATH.exists():
        raise FileNotFoundError(f"Results file not found: {RESULTS_PATH}")
    return json.loads(RESULTS_PATH.read_text())


def parse_case_name(name: str) -> tuple[str, int, bool] | None:
    """Parse case name like 'start 4 ci' into (position, length, case_insensitive)."""
    import re

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


def normalize_rate(rate: float, length: int, case_insensitive: bool) -> float:
    """Normalize rate to equivalent 5-character match probability."""
    char_prob = 2 / 64 if case_insensitive else 1 / 64
    current_prob = char_prob**length
    target_prob = char_prob**5
    return rate * (target_prob / current_prob)


def extract_rates(entries: list[dict], title: str) -> dict[str, list[float]]:
    """Extract normalized rates grouped by prefix/suffix (case-insensitive only)."""
    rates: dict[str, list[float]] = {"prefix": [], "suffix": []}

    for entry in entries:
        if entry.get("title") != title:
            continue
        for case in entry.get("cases", []):
            name = case.get("name", "")
            rate = case.get("rate")
            if not isinstance(rate, (int, float)):
                continue
            parsed = parse_case_name(name)
            if not parsed:
                continue
            position, length, case_insensitive = parsed
            # Only use case-insensitive results
            if not case_insensitive:
                continue
            normalized = normalize_rate(rate, length, case_insensitive)
            category = "prefix" if position == "start" else "suffix"
            rates[category].append(normalized)

    return rates


def extract_latest_new_rates(entries: list[dict]) -> dict[str, list[float]]:
    """Extract rates for the latest non-baseline entry (case-insensitive only)."""
    latest_entry = None
    latest_ts = None

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
        return {"prefix": [], "suffix": []}

    rates: dict[str, list[float]] = {"prefix": [], "suffix": []}
    for case in latest_entry.get("cases", []):
        name = case.get("name", "")
        rate = case.get("rate")
        if not isinstance(rate, (int, float)):
            continue
        parsed = parse_case_name(name)
        if not parsed:
            continue
        position, length, case_insensitive = parsed
        # Only use case-insensitive results
        if not case_insensitive:
            continue
        normalized = normalize_rate(rate, length, case_insensitive)
        category = "prefix" if position == "start" else "suffix"
        rates[category].append(normalized)

    return rates


def build_compact_data(raw_data: dict) -> list[CompactResult]:
    """Build compact results with average rates per category."""
    results = []

    for device, entries in raw_data.items():
        old_rates = extract_rates(entries, OLD_IMPL)
        new_rates = extract_latest_new_rates(entries)

        for cat_key in ["prefix", "suffix"]:
            old_list = old_rates.get(cat_key, [])
            new_list = new_rates.get(cat_key, [])

            if not old_list or not new_list:
                continue

            # Use geometric mean for averaging rates
            old_avg = np.exp(np.mean(np.log(old_list)))
            new_avg = np.exp(np.mean(np.log(new_list)))

            if old_avg > 0:
                results.append(
                    CompactResult(
                        device=device,
                        category=cat_key,
                        old_rate=old_avg,
                        new_rate=new_avg,
                    )
                )

    return results


def setup_style():
    """Configure matplotlib style."""
    font_manager.findfont("IBM Plex Sans", fallback_to_default=False)
    plt.rcParams.update(
        {
            "font.family": "IBM Plex Sans",
            "font.size": 12,
            "figure.facecolor": COLORS["bg"],
            "axes.facecolor": COLORS["bg"],
            "text.color": COLORS["text"],
        }
    )


def load_logo_inverted() -> np.ndarray | None:
    """Load the logo and invert it to black."""
    if not LOGO_PATH.exists():
        return None

    img = Image.open(LOGO_PATH).convert("RGBA")
    data = np.array(img)

    # Invert: white (255) -> black (0), preserve alpha
    # The logo is white on transparent, so we invert RGB channels
    rgb = data[:, :, :3]
    alpha = data[:, :, 3:]

    # Invert RGB (255 - value)
    inverted_rgb = 255 - rgb

    # Combine back
    inverted = np.concatenate([inverted_rgb, alpha], axis=2)
    return inverted


def create_compact_chart(results: list[CompactResult]) -> plt.Figure:
    """Create a compact, social-media-friendly chart."""

    # Group results by device
    available_devices = set(r.device for r in results)
    devices = [d for d in DEVICE_ORDER if d in available_devices]

    # Create figure - square-ish for social media
    fig = plt.figure(figsize=(8, 6.5), dpi=200)

    # Main content area - use log scale for better visualization
    ax = fig.add_axes([0.08, 0.18, 0.84, 0.58])

    # Build lookup
    result_lookup = {}
    for r in results:
        result_lookup[(r.category, r.device)] = r

    # Bar layout - now with old/new pairs per device
    n_devices = len(devices)
    bar_width = 0.22
    pair_gap = 0.03  # Small gap between old/new bars
    device_gap = 0.12  # Gap between devices
    group_gap = 0.5  # Gap between prefix/suffix groups

    # Calculate positions
    # Each group has: [old1, new1, gap, old2, new2]
    positions = []  # [(old_pos, new_pos), ...] for each device in each category
    x = 0
    for cat_idx, (cat_key, _) in enumerate(COMPACT_CATEGORIES):
        cat_positions = []
        for dev_idx in range(n_devices):
            old_pos = x
            new_pos = x + bar_width + pair_gap
            cat_positions.append((old_pos, new_pos))
            x += 2 * bar_width + pair_gap + device_gap
        positions.append(cat_positions)
        x += group_gap - device_gap

    # Find max rate for scaling (use actual rates, not speedup)
    max_rate = max(r.new_rate for r in results)
    min_rate = min(r.old_rate for r in results)

    # Plot bars
    for cat_idx, (cat_key, cat_label) in enumerate(COMPACT_CATEGORIES):
        for dev_idx, device in enumerate(devices):
            result = result_lookup.get((cat_key, device))
            if not result:
                continue

            old_pos, new_pos = positions[cat_idx][dev_idx]
            color = DEVICE_COLORS.get(device, "#888888")

            # Draw old (baseline) bar - gray, using actual old rate
            ax.bar(
                old_pos + bar_width / 2,
                result.old_rate,
                width=bar_width,
                color=COLORS["old_bar"],
                alpha=0.9,
                zorder=2,
            )

            # Draw new bar - colored, using actual new rate
            ax.bar(
                new_pos + bar_width / 2,
                result.new_rate,
                width=bar_width,
                color=color,
                alpha=0.92,
                zorder=3,
            )

            # Speedup label on top of new bar
            label_y = result.new_rate * 1.12
            ax.text(
                new_pos + bar_width / 2,
                label_y,
                f"{result.speedup:,.0f}x",
                ha="center",
                va="bottom",
                fontsize=14,
                fontweight="700",
                color=COLORS["text"],
            )

    # Use power scale to compress tall bars while keeping old bars small
    from matplotlib.scale import FuncScale
    ax.set_yscale("function", functions=(lambda x: np.power(x, 0.35), lambda x: np.power(x, 1/0.35)))
    ax.set_ylim(0, max_rate * 1.3)
    ax.set_xlim(-0.2, x - group_gap + 0.2)

    # X-axis labels (category names) - positioned below the chart
    # We need to convert data coords to figure coords for proper placement
    for cat_idx, (cat_key, cat_label) in enumerate(COMPACT_CATEGORIES):
        # Find center of the category group in data coordinates
        first_old = positions[cat_idx][0][0]
        last_new = positions[cat_idx][-1][1] + bar_width
        group_center = (first_old + last_new) / 2

        # Convert x from data coords to axes fraction
        x_min, x_max = ax.get_xlim()
        x_frac = (group_center - x_min) / (x_max - x_min)

        # Get axes position in figure coords
        ax_bbox = ax.get_position()
        x_fig = ax_bbox.x0 + x_frac * ax_bbox.width

        fig.text(
            x_fig,
            0.15,
            cat_label,
            ha="center",
            va="top",
            fontsize=15,
            fontweight="600",
            color=COLORS["text"],
        )

    # Remove all ticks and spines
    ax.set_xticks([])
    ax.set_yticks([])
    ax.tick_params(axis="both", which="both", length=0, width=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Title
    fig.text(
        0.5,
        0.96,
        "TON Vanity",
        ha="center",
        va="top",
        fontsize=32,
        fontweight="bold",
        color=COLORS["text"],
    )

    # Subtitle
    fig.text(
        0.5,
        0.87,
        "Comparison against ton-community/vanity-contract",
        ha="center",
        va="top",
        fontsize=13,
        color=COLORS["text_muted"],
    )

    # Add logo in bottom-left corner (aligned with footnote)
    logo_data = load_logo_inverted()
    if logo_data is not None:
        logo_ax = fig.add_axes([0.02, 0.017, 0.12, 0.05])
        logo_ax.imshow(logo_data)
        logo_ax.axis("off")

    # Add note at bottom right with benchmark info
    fig.text(
        0.98,
        0.03,
        "Chart is log-scale. Old scores are gray, new scores are blue. Evaluated on RTX 4090 with 5-6 char case-insensitive patterns.",
        ha="right",
        va="bottom",
        fontsize=8,
        color=COLORS["text_muted"],
    )

    return fig


def main():
    setup_style()

    raw_data = load_results()
    results = build_compact_data(raw_data)

    if not results:
        raise ValueError("No benchmark data found")

    fig = create_compact_chart(results)
    fig.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight", facecolor=COLORS["bg"])

    print(f"Compact chart saved to {OUTPUT_PATH}")
    plt.close(fig)


if __name__ == "__main__":
    main()
