# -*- coding: utf-8 -*-
"""
Compare v0 and v5o3 age-by-gross-income input-data distributions.
"""

from __future__ import annotations, division

import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.python.helpers.was.comparison_stats import (
    build_latex_stats_rows,
    compute_percent_stats,
    format_currency,
    print_distribution_summary,
    print_percent_comparison,
    to_std_dev_stats,
)
from scripts.python.helpers.was.distributions import (
    conditional_mean_variance_by_x,
    read_binned_distribution,
    read_joint_distribution_grid,
)
from scripts.python.helpers.was.experiments import (
    get_input_version_file,
    get_output_dir,
    write_stats_csv,
)
from scripts.python.helpers.was.plotting import (
    apply_axis_grid,
    format_age_axis,
    format_currency_axis,
)

BASE_VERSION = "v0"
TARGET_VERSION = "v5o3"
BASE_AGE_DISTRIBUTION_FILENAME = "Age9-Weighted.csv"
TARGET_AGE_DISTRIBUTION_FILENAME = "Age15-FRS-2023-24-Weighted.csv"
AGE_GROSS_INCOME_FILENAME = "AgeGrossIncomeJointDist.csv"
BASE_LABEL = "WAS Wave 3"
TARGET_LABEL = "FRS 2023-24"
BASE_PLOT_LABEL = "WAS Wave 3"
TARGET_PLOT_LABEL = "FRS 2023-24"
BASE_PERIOD = "2011 target year"
TARGET_PERIOD = "2024 target year"


def _build_version_comparison_rows(
    base_stats: dict[str, float],
    target_stats: dict[str, float],
) -> list[dict[str, str]]:
    """Build formatted rows for the v0/v5o3 gross-income comparison."""
    return build_latex_stats_rows(
        BASE_LABEL,
        BASE_PERIOD,
        base_stats,
        TARGET_LABEL,
        TARGET_PERIOD,
        target_stats,
        "Percent diff. (2024 vs 2011)",
        value_formatters={
            "mean": format_currency,
            "stddev": format_currency,
        },
    )


def _gross_income_stats_from_age_conditional(
    age_distribution: pd.DataFrame,
    income_edges: np.ndarray,
    conditional_grid: np.ndarray,
) -> dict[str, float]:
    """Compute gross-income moments from P(income|age) and age-bin probabilities."""
    age_widths = (
        age_distribution["upper_edge"] - age_distribution["lower_edge"]
    ).to_numpy()
    if np.any(age_widths <= 0.0):
        raise ValueError("Age bin widths must be positive.")
    age_masses = age_distribution["probability"].astype(float).to_numpy() * age_widths
    if len(age_masses) != conditional_grid.shape[0]:
        raise ValueError("Age distribution and joint distribution age bins do not align.")

    age_total = float(age_masses.sum())
    if age_total == 0.0:
        return {"mean": float("nan"), "variance": float("nan"), "skew": float("nan")}
    age_probabilities = age_masses / age_total

    income_midpoints = np.exp((income_edges[:-1] + income_edges[1:]) / 2.0)
    if conditional_grid.shape[1] != len(income_midpoints):
        raise ValueError("Income bin edges and joint distribution income bins do not align.")

    row_sums = conditional_grid.sum(axis=1, keepdims=True)
    conditional_probabilities = np.divide(
        conditional_grid,
        row_sums,
        out=np.zeros_like(conditional_grid, dtype=float),
        where=row_sums > 0.0,
    )
    joint_probabilities = conditional_probabilities * age_probabilities[:, None]
    total_probability = float(joint_probabilities.sum())
    if total_probability == 0.0:
        return {"mean": float("nan"), "variance": float("nan"), "skew": float("nan")}

    probabilities = (joint_probabilities / total_probability).ravel()
    values = np.tile(income_midpoints, conditional_grid.shape[0])
    mean = float(probabilities @ values)
    variance = float(probabilities @ (values - mean) ** 2)
    if variance == 0.0:
        return {"mean": mean, "variance": variance, "skew": 0.0}
    third_moment = float(probabilities @ (values - mean) ** 3)
    skew = third_moment / (variance ** 1.5)
    return {"mean": mean, "variance": variance, "skew": skew}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare v0 and v5o3 age-by-gross-income input-data distributions."
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

    wave_age_dist = read_binned_distribution(
        get_input_version_file(
            __file__,
            BASE_VERSION,
            BASE_AGE_DISTRIBUTION_FILENAME,
        )
    )
    round_age_dist = read_binned_distribution(
        get_input_version_file(
            __file__,
            TARGET_VERSION,
            TARGET_AGE_DISTRIBUTION_FILENAME,
        )
    )
    wave_age_edges, wave_income_edges, wave_gross = read_joint_distribution_grid(
        get_input_version_file(
            __file__,
            BASE_VERSION,
            AGE_GROSS_INCOME_FILENAME,
        )
    )
    round_age_edges, round_income_edges, round_gross = read_joint_distribution_grid(
        get_input_version_file(
            __file__,
            TARGET_VERSION,
            AGE_GROSS_INCOME_FILENAME,
        )
    )

    wave_stats = to_std_dev_stats(
        _gross_income_stats_from_age_conditional(
            wave_age_dist,
            wave_income_edges,
            wave_gross,
        )
    )
    round_stats = to_std_dev_stats(
        _gross_income_stats_from_age_conditional(
            round_age_dist,
            round_income_edges,
            round_gross,
        )
    )
    percent_stats = compute_percent_stats(wave_stats, round_stats)
    stats_rows = _build_version_comparison_rows(wave_stats, round_stats)
    stats_path = os.path.join(output_dir, "AgeGrossIncomeJointDistStats.csv")
    write_stats_csv(stats_path, stats_rows, separator=";")

    print_distribution_summary(
        f"{wave_title} gross income distribution",
        wave_stats,
    )
    print_distribution_summary(
        f"{round_title} gross income distribution",
        round_stats,
    )
    print_percent_comparison(
        "Comparison (v5o3 % vs v0)",
        percent_stats,
    )

    # Compare mean and standard deviation of gross income by age for each wave.
    wave_age_mid, wave_mean, wave_variance = conditional_mean_variance_by_x(
        wave_age_edges,
        wave_income_edges,
        wave_gross,
        log_x=False,
        log_y=True,
    )
    wave_std_dev = np.sqrt(wave_variance)
    round_age_mid, round_mean, round_variance = conditional_mean_variance_by_x(
        round_age_edges,
        round_income_edges,
        round_gross,
        log_x=False,
        log_y=True,
    )
    round_std_dev = np.sqrt(round_variance)

    fig, axes = plt.subplots(nrows=2, figsize=(11, 8), sharex=True)
    axes[0].plot(
        wave_age_mid,
        wave_mean,
        marker="o",
        label=wave_plot_title,
    )
    axes[0].plot(
        round_age_mid,
        round_mean,
        marker="s",
        label=round_plot_title,
    )
    axes[0].set_ylabel("Mean gross income (GBP, log scale)")
    axes[0].set_yscale("log")
    apply_axis_grid(axes[0], axis="x")
    apply_axis_grid(axes[0], axis="y")
    format_currency_axis(axes[0], axis="y")
    axes[0].legend()

    axes[1].plot(
        wave_age_mid,
        wave_std_dev,
        marker="o",
        label=wave_plot_title,
    )
    axes[1].plot(
        round_age_mid,
        round_std_dev,
        marker="s",
        label=round_plot_title,
    )
    axes[1].set_xlabel("Age (midpoint)")
    axes[1].set_ylabel("Gross income standard deviation (GBP, log scale)")
    axes[1].set_yscale("log")
    apply_axis_grid(axes[1], axis="x")
    apply_axis_grid(axes[1], axis="y")
    format_age_axis(axes[1], axis="x")
    format_currency_axis(axes[1], axis="y")

    fig.tight_layout()
    fig.savefig(
        os.path.join(output_dir, "AgeGrossIncomeJointDistComparison.png"),
        dpi=300,
    )
    plt.show()


if __name__ == "__main__":
    main()
