"""
Model-result histogram helpers for WAS validation scripts.

@author: Max Stoddard
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import glob
import os

import numpy as np

from scripts.python.helpers.was.io import read_results


ValueTransform = Callable[[list[float]], Iterable[float]]


def resolve_model_result_files(
    default_file: str,
    *,
    result_glob: str | None = None,
    glob_env_name: str = "WAS_RESULTS_FILE_GLOB",
) -> list[str]:
    """Resolve model result files from an explicit/default glob or a single file."""
    resolved_glob = result_glob
    if resolved_glob is None:
        resolved_glob = os.getenv(glob_env_name)
    if resolved_glob is None:
        return [default_file]

    result_files = sorted(glob.glob(os.path.expanduser(resolved_glob)))
    if not result_files:
        raise FileNotFoundError(
            f"{glob_env_name} matched no files: {resolved_glob}"
        )
    return result_files


def normalised_model_histogram(
    results_file: str,
    bin_edges: np.ndarray,
    *,
    start_time: int,
    end_time: int,
    value_transform: ValueTransform,
    value_label: str,
) -> np.ndarray:
    """Build one normalized model histogram from a model micro-data result file."""
    results = read_results(results_file, start_time, end_time)
    values = list(value_transform(results))
    hist = np.histogram(values, bins=bin_edges, density=False)[0]
    total = float(np.sum(hist))
    if total <= 0.0:
        raise ValueError(f"No {value_label} observations found in {results_file}")
    return hist / total


def averaged_model_histogram(
    result_files: list[str],
    bin_edges: np.ndarray,
    *,
    start_time: int,
    end_time: int,
    value_transform: ValueTransform,
    value_label: str,
    model_name: str = "model",
) -> np.ndarray:
    """Average normalized model histograms across one or more result files."""
    model_histograms = [
        normalised_model_histogram(
            results_file,
            bin_edges,
            start_time=start_time,
            end_time=end_time,
            value_transform=value_transform,
            value_label=value_label,
        )
        for results_file in result_files
    ]
    if len(model_histograms) > 1:
        print(f"Averaged {len(model_histograms)} {model_name} result files")
    model_hist = np.mean(np.vstack(model_histograms), axis=0)
    return model_hist / np.sum(model_hist)
