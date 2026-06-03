# -*- coding: utf-8 -*-
"""
Shared helpers for WAS experiment scripts.

@author: Max Stoddard
"""

from __future__ import annotations

import os
from typing import Callable, Mapping

import pandas as pd

from scripts.python.helpers.was.comparison_stats import build_latex_stats_rows
from scripts.python.helpers.was.config import ROUND_8_DATA, WAVE_3_DATA

_DATASET_LABELS: dict[str, tuple[str, str]] = {
    WAVE_3_DATA: ("WAS Wave 3", "2010-2012"),
    ROUND_8_DATA: ("WAS Round 8", "2020-2022"),
}


def get_output_dir(script_file: str) -> str:
    """Return the experiment outputs directory for a script."""
    output_dir = os.path.join(os.path.dirname(script_file), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def get_project_root(script_file: str) -> str:
    """Resolve the project root from a script path."""
    return os.path.abspath(
        os.path.join(os.path.dirname(script_file), "..", "..", "..", "..")
    )


def get_input_version_file(script_file: str, version: str, filename: str) -> str:
    """Return a checked-in input-data-version file path from an experiment script."""
    return os.path.join(
        get_project_root(script_file),
        "input-data-versions",
        version,
        filename,
    )


def get_dataset_label(dataset: str) -> tuple[str, str]:
    """Return (label, period) for a WAS dataset identifier."""
    try:
        return _DATASET_LABELS[dataset]
    except KeyError as exc:
        raise ValueError(f"Unknown dataset identifier: {dataset}") from exc


def build_was_comparison_rows(
    wave_stats: Mapping[str, float],
    round_stats: Mapping[str, float],
    percent_label: str = "Percent diff (Round 8 vs Wave 3)",
    value_formatters: Mapping[str, Callable[[float], str]] | None = None,
) -> list[dict[str, str]]:
    """Build LaTeX-friendly rows using standard WAS wave/round labels."""
    wave_label, wave_period = _DATASET_LABELS[WAVE_3_DATA]
    round_label, round_period = _DATASET_LABELS[ROUND_8_DATA]
    return build_latex_stats_rows(
        wave_label,
        wave_period,
        wave_stats,
        round_label,
        round_period,
        round_stats,
        percent_label,
        value_formatters=value_formatters,
    )


def write_stats_csv(
    output_path: str,
    rows: list[dict[str, str]],
    separator: str = ",",
) -> None:
    """Write stats rows to CSV with a configurable separator."""
    pd.DataFrame(rows).to_csv(output_path, index=False, sep=separator)
