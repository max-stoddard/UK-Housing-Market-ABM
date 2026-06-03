# -*- coding: utf-8 -*-
"""
Compare v0 and v5o3 age distributions using checked-in input-data CSVs.

Plots the age bin histograms and prints mean/standard-deviation/skew statistics.

@author: Max Stoddard
"""

from __future__ import annotations, division

import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd

from scripts.python.helpers.was.comparison_stats import (
    build_latex_stats_rows,
    compute_percent_stats,
    print_distribution_summary,
    print_percent_comparison,
    to_std_dev_stats,
)
from scripts.python.helpers.was.distributions import read_binned_distribution
from scripts.python.helpers.was.experiments import (
    get_input_version_file,
    get_output_dir,
)
from scripts.python.helpers.was.plotting import apply_axis_grid, format_age_axis

BASE_VERSION = "v0"
TARGET_VERSION = "v5o3"
BASE_AGE_DISTRIBUTION_FILENAME = "Age9-Weighted.csv"
TARGET_AGE_DISTRIBUTION_FILENAME = "Age15-FRS-2023-24-Weighted.csv"
BASE_LABEL = "WAS Wave 3"
TARGET_LABEL = "FRS 2023-24"
BASE_PLOT_LABEL = "WAS Wave 3"
TARGET_PLOT_LABEL = "FRS 2023-24"
BASE_PERIOD = "2011 target year"
TARGET_PERIOD = "2024 target year"


def _split_final_bin_uniform(distribution: pd.DataFrame) -> pd.DataFrame:
    """Split a legacy final 75-85 bin into 75-85 and 85-95 with uniform density."""
    if distribution.empty:
        return distribution
    last_row = distribution.iloc[-1]
    width = float(last_row["upper_edge"] - last_row["lower_edge"])
    if width <= 0:
        return distribution
    # Legacy Round 8 age outputs ended at 85.0; newer outputs already end at 95.0.
    if abs(float(last_row["upper_edge"]) - 85.0) > 1e-9:
        return distribution
    split_point = float(last_row["upper_edge"])
    extended_upper = split_point + width
    half_prob = float(last_row["probability"]) / 2.0

    trimmed = distribution.iloc[:-1].copy()
    split_rows = pd.DataFrame(
        [
            {
                "lower_edge": float(last_row["lower_edge"]),
                "upper_edge": split_point,
                "probability": half_prob,
            },
            {
                "lower_edge": split_point,
                "upper_edge": extended_upper,
                "probability": half_prob,
            },
        ]
    )
    return pd.concat([trimmed, split_rows], ignore_index=True)


def _age_bin_widths(distribution: pd.DataFrame) -> pd.Series:
    """Return positive age-bin widths."""
    widths = distribution["upper_edge"] - distribution["lower_edge"]
    if (widths <= 0.0).any():
        raise ValueError("Age bin widths must be positive.")
    return widths


def _age_density_integral(distribution: pd.DataFrame) -> float:
    """Return the integral of an age-density distribution."""
    return float((distribution["probability"] * _age_bin_widths(distribution)).sum())


def _normalized_age_density(distribution: pd.DataFrame) -> pd.Series:
    """Return age density normalized so density times bin width integrates to 1."""
    density = distribution["probability"].astype(float)
    integral = _age_density_integral(distribution)
    if integral == 0.0:
        return density
    return density / integral


def _density_weighted_mean_variance_skew(
    distribution: pd.DataFrame,
) -> tuple[float, float, float]:
    """Compute moments from an age-density distribution."""
    density = _normalized_age_density(distribution)
    masses = density * _age_bin_widths(distribution)
    total_mass = float(masses.sum())
    if total_mass == 0.0:
        return float("nan"), float("nan"), float("nan")
    probabilities = masses / total_mass
    midpoints = (distribution["lower_edge"] + distribution["upper_edge"]) / 2.0
    mean = float((midpoints * probabilities).sum())
    variance = float((probabilities * (midpoints - mean) ** 2).sum())
    if variance == 0.0:
        return mean, variance, 0.0
    third_moment = float((probabilities * (midpoints - mean) ** 3).sum())
    skew = third_moment / (variance ** 1.5)
    return mean, variance, skew


def _plot_overlay(
    wave_3: pd.DataFrame,
    round_8: pd.DataFrame,
    wave_3_label: str,
    round_8_label: str,
    output_path: str | None = None,
) -> None:
    """Plot overlayed age distributions with shared styling."""
    fig, ax = plt.subplots(figsize=(10, 6))

    wave_3_density = _normalized_age_density(wave_3)
    round_8_density = _normalized_age_density(round_8)

    wave_3_widths = wave_3["upper_edge"] - wave_3["lower_edge"]
    round_8_widths = round_8["upper_edge"] - round_8["lower_edge"]

    ax.bar(
        wave_3["lower_edge"],
        height=wave_3_density,
        width=wave_3_widths,
        align="edge",
        alpha=0.5,
        color="b",
        label=wave_3_label,
    )
    ax.bar(
        round_8["lower_edge"],
        height=round_8_density,
        width=round_8_widths,
        align="edge",
        alpha=0.5,
        color="r",
        label=round_8_label,
    )

    ax.set_xlabel("Age (lower edge)")
    ax.set_ylabel("Household share density")
    ax.legend()
    apply_axis_grid(ax, axis="both")
    format_age_axis(ax, axis="x")

    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=300)
    plt.show()


def _build_version_comparison_rows(
    base_stats: dict[str, float],
    target_stats: dict[str, float],
) -> list[dict[str, str]]:
    """Build LaTeX-friendly rows for the v0/v5o3 age comparison."""
    return build_latex_stats_rows(
        BASE_LABEL,
        BASE_PERIOD,
        base_stats,
        TARGET_LABEL,
        TARGET_PERIOD,
        target_stats,
        "Percent diff. (2024 vs 2011)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare v0 and v5o3 input-data age distributions."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory for generated stats and plots.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or get_output_dir(__file__)

    wave_title = f"{BASE_LABEL} ({BASE_PERIOD})"
    round_title = f"{TARGET_LABEL} ({TARGET_PERIOD})"
    wave_plot_title = f"{BASE_PLOT_LABEL} ({BASE_PERIOD})"
    round_plot_title = f"{TARGET_PLOT_LABEL} ({TARGET_PERIOD})"

    wave_3_dist = read_binned_distribution(
        get_input_version_file(
            __file__,
            BASE_VERSION,
            BASE_AGE_DISTRIBUTION_FILENAME,
        )
    )
    round_8_dist = read_binned_distribution(
        get_input_version_file(
            __file__,
            TARGET_VERSION,
            TARGET_AGE_DISTRIBUTION_FILENAME,
        )
    )

    wave_3_mean, wave_3_variance, wave_3_skew = _density_weighted_mean_variance_skew(
        wave_3_dist
    )
    round_8_mean, round_8_variance, round_8_skew = _density_weighted_mean_variance_skew(
        round_8_dist
    )

    wave_3_stats = to_std_dev_stats(
        {
            "mean": wave_3_mean,
            "variance": wave_3_variance,
            "skew": wave_3_skew,
        }
    )
    round_8_stats = to_std_dev_stats(
        {
            "mean": round_8_mean,
            "variance": round_8_variance,
            "skew": round_8_skew,
        }
    )
    percent_stats = compute_percent_stats(wave_3_stats, round_8_stats)
    stats_rows = _build_version_comparison_rows(wave_3_stats, round_8_stats)

    stats_path = os.path.join(output_dir, "AgeDistributionStats.csv")
    stats_df = pd.DataFrame(stats_rows)
    stats_df.to_csv(stats_path, index=False)

    print_distribution_summary(f"{wave_title} age distribution", wave_3_stats)
    print_distribution_summary(f"{round_title} age distribution", round_8_stats)
    print_percent_comparison(
        "Comparison (v5o3 % vs v0)",
        percent_stats,
    )

    _plot_overlay(
        wave_3_dist,
        round_8_dist,
        wave_plot_title,
        round_plot_title,
        output_path=os.path.join(output_dir, "AgeDistributionComparison.png"),
    )


if __name__ == "__main__":
    main()
