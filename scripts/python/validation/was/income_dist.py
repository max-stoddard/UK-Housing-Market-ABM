# -*- coding: utf-8 -*-
"""
Class to study households' income distribution, for validation purposes, based on Wealth and Assets Survey data.

@author: Adrian Carro, Max Stoddard
"""

from __future__ import division
import os
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from scripts.python.helpers.was.csv_write import write_1d_distribution
from scripts.python.helpers.was.derived_columns import (
    GROSS_NON_RENT_INCOME,
    NET_NON_RENT_INCOME,
    derive_non_rent_income_columns,
)
from scripts.python.helpers.was.config import (
    WAS_DATA_ROOT,
    WAS_RESULTS_ROOT,
    WAS_RESULTS_RUN_SUBDIR,
    WAS_VALIDATION_PLOTS,
)
from scripts.python.helpers.was.plotting import (
    apply_axis_grid,
    plot_hist_overlay,
    print_hist_percent_diff,
    set_compact_currency_log_ticks,
)
from scripts.python.helpers.was.row_filters import (
    filter_percentile_outliers,
    filter_positive_values,
)
from scripts.python.helpers.was.io import read_was_data
from scripts.python.helpers.was.model_histograms import (
    averaged_model_histogram,
    resolve_model_result_files,
)
from scripts.python.helpers.was.constants import (
    WAS_WEIGHT,
    WAS_NET_ANNUAL_INCOME,
    WAS_GROSS_ANNUAL_INCOME,
    WAS_NET_ANNUAL_RENTAL_INCOME,
    WAS_GROSS_ANNUAL_RENTAL_INCOME,
)
from scripts.python.helpers.was.timing import start_timer, end_timer


# Set control variables and addresses. Note that available variables to print and plot are "GrossTotalIncome",
# "NetTotalIncome", "GrossRentalIncome", "NetRentalIncome", "GrossNonRentIncome" and "NetNonRentIncome"
printResults = False
plotResults = WAS_VALIDATION_PLOTS
printBucketDiffs = False
start_time = 1000
end_time = 2000
min_income = 1000.0
min_log_income_bin_edge = np.log(min_income)
max_log_income_bin_edge = 12.25
variableToPlot = GROSS_NON_RENT_INCOME
rootData = WAS_DATA_ROOT
rootResults = WAS_RESULTS_ROOT
results_run_dir = os.path.join(rootResults, WAS_RESULTS_RUN_SUBDIR)
timer_start = start_timer(os.path.basename(__file__), "validation")


def _env_text(name: str, default: str | None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value, got {value!r}")


def _annual_income_values(results: list[float]) -> list[float]:
    annual_income = [12.0 * value for value in results if value > 0.0]
    return [value for value in annual_income if value >= min_income]


def _income_comparison_mode() -> bool:
    return (
        os.getenv("WAS_2011_RESULTS_FILE_GLOB") is not None
        or os.getenv("WAS_2024_RESULTS_FILE_GLOB") is not None
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} must be set when using income comparison mode")
    return value


def _averaged_income_histogram(
    result_files: list[str],
    income_bin_edges: np.ndarray,
    *,
    model_name: str = "model",
) -> np.ndarray:
    return averaged_model_histogram(
        result_files,
        income_bin_edges,
        start_time=start_time,
        end_time=end_time,
        value_transform=_annual_income_values,
        value_label="annual income",
        model_name=model_name,
    )


def _apply_income_axis_style(axes: plt.Axes, *, force_grid: bool) -> None:
    axes.set_xscale("log")
    axes.set_axisbelow(True)
    set_compact_currency_log_ticks(
        axes,
        axis="x",
        include_half_decades=False,
    )
    if force_grid or _env_bool("WAS_PLOT_GRID", False):
        apply_axis_grid(
            axes,
            axis="both",
            which="both",
            major_alpha=0.28,
            minor_alpha=0.14,
        )


def _save_or_show(figure: plt.Figure) -> None:
    figure.tight_layout()
    plot_output_path = os.getenv("WAS_PLOT_OUTPUT_PATH")
    if plot_output_path:
        output_path = Path(plot_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Wrote plot to {output_path}")
    else:
        plt.show()

# Read Wealth and Assets Survey data for households
use_columns = [
    WAS_WEIGHT,
    WAS_GROSS_ANNUAL_INCOME,
    WAS_NET_ANNUAL_INCOME,
    WAS_GROSS_ANNUAL_RENTAL_INCOME,
    WAS_NET_ANNUAL_RENTAL_INCOME,
]
chunk = read_was_data(rootData, use_columns)

# List of household variables currently used
# DVTotGIRw3                  Household Gross Annual (regular) income
# DVTotNIRw3                  Household Net Annual (regular) income
# DVGrsRentAmtAnnualw3_aggr   Household Gross Annual income from rent
# DVNetRentAmtAnnualw3_aggr   Household Net Annual income from rent

# Derive non-rent income columns for filtering and plots.
derive_non_rent_income_columns(chunk)

# Filter down to keep only columns of interest
chunk = chunk[
    [
        WAS_GROSS_ANNUAL_INCOME,
        WAS_NET_ANNUAL_INCOME,
        WAS_GROSS_ANNUAL_RENTAL_INCOME,
        WAS_NET_ANNUAL_RENTAL_INCOME,
        GROSS_NON_RENT_INCOME,
        NET_NON_RENT_INCOME,
        WAS_WEIGHT,
    ]
]

# Remove extreme income outliers to stabilize distribution.
chunk = filter_percentile_outliers(
    chunk,
    lower_bound_column=WAS_NET_ANNUAL_INCOME,
    upper_bound_column=WAS_GROSS_ANNUAL_INCOME,
)

results_file = os.path.join(results_run_dir, "MonthlyGrossEmploymentIncome-run1.csv")

# If printing data to files is required, histogram data and print results
if printResults:
    number_of_bins = int(max_log_income_bin_edge - min_log_income_bin_edge) * 4 + 2
    income_bin_edges = np.linspace(
        min_log_income_bin_edge, max_log_income_bin_edge, number_of_bins
    )
    for name in [
        WAS_GROSS_ANNUAL_INCOME,
        WAS_NET_ANNUAL_INCOME,
        WAS_GROSS_ANNUAL_RENTAL_INCOME,
        WAS_NET_ANNUAL_RENTAL_INCOME,
        GROSS_NON_RENT_INCOME,
        NET_NON_RENT_INCOME,
    ]:
        # Keep positive values for log-scale histogram.
        positive_chunk = filter_positive_values(chunk, [name])
        frequency = np.histogram(
            np.log(positive_chunk[name].values),
            bins=income_bin_edges,
            density=True,
            weights=positive_chunk[WAS_WEIGHT].values,
        )[0]
        # Write income distribution for validation output.
        write_1d_distribution(
            name + "-Weighted.csv",
            name,
            income_bin_edges,
            frequency,
            log_label=False,
        )

# Build model/data histograms and print percentage-point differences regardless of plotting mode.
number_of_bins = int(max_log_income_bin_edge - min_log_income_bin_edge) * 4 + 2
income_bin_edges = np.logspace(
    min_log_income_bin_edge, max_log_income_bin_edge, number_of_bins, base=np.e
)
# Histogram data from WAS
# Keep positive values for log-scale histogram.
positive_chunk = filter_positive_values(chunk, [variableToPlot])
positive_chunk = positive_chunk[positive_chunk[variableToPlot] >= min_income]
WAS_hist = np.histogram(
    positive_chunk[variableToPlot].values,
    bins=income_bin_edges,
    density=False,
    weights=positive_chunk[WAS_WEIGHT].values,
)[0]
WAS_hist = WAS_hist / sum(WAS_hist)

comparison_mode = _income_comparison_mode()
if comparison_mode:
    results_2011_files = resolve_model_result_files(
        results_file,
        result_glob=_required_env("WAS_2011_RESULTS_FILE_GLOB"),
        glob_env_name="WAS_2011_RESULTS_FILE_GLOB",
    )
    results_2024_files = resolve_model_result_files(
        results_file,
        result_glob=_required_env("WAS_2024_RESULTS_FILE_GLOB"),
        glob_env_name="WAS_2024_RESULTS_FILE_GLOB",
    )
    model_2011_hist = _averaged_income_histogram(
        results_2011_files,
        income_bin_edges,
        model_name="2011 model",
    )
    model_2024_hist = _averaged_income_histogram(
        results_2024_files,
        income_bin_edges,
        model_name="2024 model",
    )
    # Print percentage-point differences vs WAS for diagnostics.
    print_hist_percent_diff(
        income_bin_edges,
        model_2011_hist,
        WAS_hist,
        label="2011 Income",
        print_buckets=printBucketDiffs,
    )
    print_hist_percent_diff(
        income_bin_edges,
        model_2024_hist,
        WAS_hist,
        label="2024 Income",
        print_buckets=printBucketDiffs,
    )
else:
    model_result_files = resolve_model_result_files(results_file)
    model_hist = _averaged_income_histogram(
        model_result_files,
        income_bin_edges,
    )
    # Print percentage-point differences vs WAS for diagnostics.
    print_hist_percent_diff(
        income_bin_edges,
        model_hist,
        WAS_hist,
        label="Income",
        print_buckets=printBucketDiffs,
    )

# If plotting data and results is required, plot model and validation distributions.
if plotResults:
    figure, axes = plt.subplots(figsize=(10.0, 6.5))
    if comparison_mode:
        bin_widths = np.diff(income_bin_edges)
        axes.bar(
            income_bin_edges[:-1],
            height=WAS_hist,
            width=bin_widths,
            align="edge",
            label=_env_text("WAS_DATA_LABEL", "Validation data (Latest WAS)"),
            alpha=0.45,
            color="0.65",
            edgecolor="none",
        )
        axes.stairs(
            model_2011_hist,
            income_bin_edges,
            label=_env_text(
                "WAS_2011_MODEL_LABEL",
                "2011 Model Output (10-seed output)",
            ),
            color="#1f77b4",
            linewidth=2.0,
        )
        axes.stairs(
            model_2024_hist,
            income_bin_edges,
            label=_env_text(
                "WAS_2024_MODEL_LABEL",
                "2024 Model Output (10-seed output)",
            ),
            color="#d62728",
            linewidth=2.0,
        )
        axes.set_xlabel(_env_text("WAS_PLOT_XLABEL", "Income (log scale)"))
        axes.set_ylabel("Frequency (fraction of cases)")
        plot_title = _env_text(
            "WAS_PLOT_TITLE",
            "Distribution of Gross Non-rent Income vs WAS Round 8",
        )
        if plot_title:
            axes.set_title(plot_title)
        _apply_income_axis_style(axes, force_grid=True)
        axes.legend(loc=os.getenv("WAS_LEGEND_LOCATION", "upper left"))
    else:
        # Plot model vs WAS income distributions for validation.
        axes = plot_hist_overlay(
            income_bin_edges,
            model_hist,
            WAS_hist,
            xlabel=_env_text("WAS_PLOT_XLABEL", "Income (log scale)"),
            ylabel="Frequency (fraction of cases)",
            title=_env_text(
                "WAS_PLOT_TITLE",
                "Distribution of {}".format(variableToPlot),
            ),
            log_x=True,
            model_label=_env_text("WAS_MODEL_LABEL", "Model results"),
            data_label=_env_text("WAS_DATA_LABEL", "Validation data (WAS)"),
            ax=axes,
        )
        _apply_income_axis_style(axes, force_grid=False)
        legend_location = os.getenv("WAS_LEGEND_LOCATION")
        if legend_location:
            axes.legend(loc=legend_location)
    _save_or_show(figure)

end_timer(timer_start)
