# -*- coding: utf-8 -*-
"""
Class to study households' housing wealth distribution, for validation purposes, based on Wealth and Assets Survey
data.

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
    GROSS_HOUSING_WEALTH,
    derive_gross_housing_wealth_column,
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
from scripts.python.helpers.was.row_filters import filter_positive_values
from scripts.python.helpers.was.io import read_was_data
from scripts.python.helpers.was.model_histograms import (
    averaged_model_histogram,
    resolve_model_result_files,
)
from scripts.python.helpers.was.constants import (
    WAS_WEIGHT,
    WAS_TOTAL_PROPERTY_WEALTH,
    WAS_PROPERTY_VALUE_SUM,
    WAS_MAIN_RESIDENCE_VALUE,
    WAS_OTHER_HOUSES_TOTAL_VALUE,
    WAS_BTL_HOUSES_TOTAL_VALUE,
)
from scripts.python.helpers.was.timing import start_timer, end_timer


# Set control variables and addresses. Available variables to print and plot are:
# WAS_TOTAL_PROPERTY_WEALTH, WAS_PROPERTY_VALUE_SUM, WAS_GROSS_HOUSING_WEALTH
printResults = False
plotResults = WAS_VALIDATION_PLOTS
printBucketDiffs = False
start_time = 1000
end_time = 2000
min_log_bin_edge = 6.0
max_log_bin_edge = 16.0
# variableToPlot = WAS_GROSS_HOUSING_WEALTH
variableToPlot = WAS_TOTAL_PROPERTY_WEALTH
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


def _positive_values(results: list[float]) -> list[float]:
    return [value for value in results if value > 0.0]

# Read Wealth and Assets Survey data for households
use_column_constants = [
    WAS_WEIGHT,
    WAS_TOTAL_PROPERTY_WEALTH,
    WAS_PROPERTY_VALUE_SUM,
    WAS_MAIN_RESIDENCE_VALUE,
    WAS_OTHER_HOUSES_TOTAL_VALUE,
    WAS_BTL_HOUSES_TOTAL_VALUE,
]
chunk = read_was_data(rootData, use_column_constants)

# List of household variables currently used
# HPROPWW3                      Total (net) property wealth (net, i.e., = DVPropertyW3 - HMORTGW3)
# DVPropertyW3                  Total (gross) property wealth (sum of all property values)
# DVHValueW3                    Value of main residence
# DVHseValW3_sum                Total value of other houses
# DVBltValW3_sum                Total value of buy to let houses

# Derive gross housing wealth column for distribution.
derive_gross_housing_wealth_column(chunk)
# Filter down to keep only housing wealth
chunk = chunk[
    [
        WAS_TOTAL_PROPERTY_WEALTH,
        WAS_PROPERTY_VALUE_SUM,
        GROSS_HOUSING_WEALTH,
        WAS_WEIGHT,
    ]
]
# Keep positive wealth values for log-scale histogram.
chunk = filter_positive_values(
    chunk,
    [WAS_TOTAL_PROPERTY_WEALTH, WAS_PROPERTY_VALUE_SUM, GROSS_HOUSING_WEALTH],
)

# Define bin edges and widths
number_of_bins = int(max_log_bin_edge - min_log_bin_edge) * 4 + 1
bin_edges = np.logspace(min_log_bin_edge, max_log_bin_edge, number_of_bins, base=np.e)

# If printing data to files is required, histogram data and print results
if printResults:
    for variable in [
        WAS_TOTAL_PROPERTY_WEALTH,
        WAS_PROPERTY_VALUE_SUM,
        GROSS_HOUSING_WEALTH,
    ]:
        hist = np.histogram(
            chunk[variable].values,
            bins=bin_edges,
            density=True,
            weights=chunk[WAS_WEIGHT].values,
        )[0]
        # Write housing wealth distribution for validation.
        write_1d_distribution(
            "{}-Weighted.csv".format(variable),
            variable,
            bin_edges,
            hist,
            log_label=True,
        )

# Build model/data histograms and print percentage-point differences regardless of plotting mode.
model_results_file = os.path.join(results_run_dir, "HousingWealth-run1.csv")
model_result_files = resolve_model_result_files(model_results_file)
model_hist = averaged_model_histogram(
    model_result_files,
    bin_edges,
    start_time=start_time,
    end_time=end_time,
    value_transform=_positive_values,
    value_label="positive housing wealth",
)

# Histogram data from WAS
# Keep positive values for log-scale histogram.
positive_chunk = filter_positive_values(chunk, [variableToPlot])
WAS_hist = np.histogram(
    positive_chunk[variableToPlot].values,
    bins=bin_edges,
    density=False,
    weights=positive_chunk[WAS_WEIGHT].values,
)[0]
WAS_hist = WAS_hist / sum(WAS_hist)
# Print percentage-point differences vs WAS for diagnostics.
print_hist_percent_diff(
    bin_edges,
    model_hist,
    WAS_hist,
    label="Housing wealth",
    print_buckets=printBucketDiffs,
)

# If plotting data and results is required, plot model and validation distributions.
if plotResults:
    # Plot model vs WAS housing wealth distributions for validation.
    plot_title = _env_text(
        "WAS_PLOT_TITLE",
        "Distribution of Mark-to-market Net Housing Wealth ({})".format(variableToPlot),
    )
    figure, axes = plt.subplots(figsize=(10.0, 6.5))
    axes = plot_hist_overlay(
        bin_edges,
        model_hist,
        WAS_hist,
        xlabel=_env_text("WAS_PLOT_XLABEL", "Net housing wealth (log scale)"),
        ylabel="Frequency (fraction of cases)",
        title=plot_title,
        log_x=True,
        model_label=_env_text("WAS_MODEL_LABEL", "Model results"),
        data_label=_env_text("WAS_DATA_LABEL", "Validation data (WAS)"),
        ax=axes,
    )
    legend_location = os.getenv("WAS_LEGEND_LOCATION")
    if legend_location:
        axes.legend(loc=legend_location)
    if _env_bool("WAS_PLOT_GRID", False):
        apply_axis_grid(
            axes,
            axis="both",
            which="both",
            major_alpha=0.28,
            minor_alpha=0.14,
        )
    set_compact_currency_log_ticks(
        axes,
        axis="x",
        include_half_decades=_env_bool(
            "WAS_INCLUDE_HALF_DECADE_CURRENCY_TICKS",
            True,
        ),
    )
    figure.tight_layout()
    plot_output_path = os.getenv("WAS_PLOT_OUTPUT_PATH")
    if plot_output_path:
        output_path = Path(plot_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Wrote plot to {output_path}")
    else:
        plt.show()

end_timer(timer_start)
