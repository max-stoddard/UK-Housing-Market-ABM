#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot side-by-side runtime histograms from model-speed benchmark summaries.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "uk-housing-matplotlib"))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import MultipleLocator

    HAS_MATPLOTLIB = True
except ImportError:
    plt = None
    np = None
    Line2D = None
    Patch = None
    MultipleLocator = None
    HAS_MATPLOTLIB = False


DEFAULT_BASELINE_SUMMARY = Path(
    "tmp/model-speed/rental-income-rerun/default-second/benchmarks/v0/core-minimal-20k-s1/"
    "20260506T105729Z/summary.json"
)
DEFAULT_CACHE_SUMMARY = Path(
    "tmp/model-speed/rental-income-rerun/after-first/benchmarks/v0/core-minimal-20k-s1/"
    "20260506T105020Z/summary.json"
)
DEFAULT_OUTPUT_DIR = Path("tmp/model-speed/rental-income-rerun")
DEFAULT_BASENAME = "20k-runtime-histogram"
DEFAULT_FORMATS = ("png", "pdf", "svg")
DEFAULT_BASELINE_COLOR = "#4E79A7"
DEFAULT_CACHE_COLOR = "#E15759"
LAYOUT_CHOICES = ("both", "panels", "overlay")
LEVEL_CHOICES = ("batch", "seed")


@dataclass(frozen=True)
class RuntimeSample:
    label: str
    color: str
    runtimes: list[float]
    mean: float


def load_runtime_sample(path: Path, *, label: str, color: str) -> RuntimeSample:
    with path.open(encoding="utf-8") as handle:
        summary = json.load(handle)

    runtimes = [float(run["wall_clock_seconds"]) for run in summary["runs"]]
    mean = float(summary["metric_summary"]["wall_clock_seconds"]["mean"])
    if not runtimes:
        raise ValueError(f"No run runtimes found in {path}")

    return RuntimeSample(label=label, color=color, runtimes=runtimes, mean=mean)


def load_runtime_sample_from_batches_csv(
    path: Path,
    *,
    label: str,
    color: str,
    cache_enabled: bool,
    workers: int,
) -> RuntimeSample:
    runtimes: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if _coerce_bool(row.get("cache_enabled")) != cache_enabled:
                continue
            if int(row["workers"]) != workers:
                continue
            if not _is_success_status(str(row.get("status", ""))):
                continue
            wall_clock_seconds = float(row.get("wall_clock_seconds", 0.0) or 0.0)
            if wall_clock_seconds <= 0.0:
                continue
            runtimes.append(wall_clock_seconds)

    if not runtimes:
        raise ValueError(
            f"No successful batch runtimes found in {path} for cache_enabled={cache_enabled} workers={workers}"
        )

    mean = sum(runtimes) / len(runtimes)
    return RuntimeSample(label=label, color=color, runtimes=runtimes, mean=mean)


def load_seed_runtime_sample_from_batches_csv(
    path: Path,
    *,
    label: str,
    color: str,
    cache_enabled: bool,
    workers: int,
) -> RuntimeSample:
    runtimes: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if _coerce_bool(row.get("cache_enabled")) != cache_enabled:
                continue
            if int(row["workers"]) != workers:
                continue
            if not _is_success_status(str(row.get("status", ""))):
                continue
            raw_json_path = Path(str(row["raw_json_path"]))
            runtimes.extend(_load_successful_child_runtimes(raw_json_path))

    if not runtimes:
        raise ValueError(
            f"No successful seed runtimes found in {path} for cache_enabled={cache_enabled} workers={workers}"
        )

    mean = sum(runtimes) / len(runtimes)
    return RuntimeSample(label=label, color=color, runtimes=runtimes, mean=mean)


def build_bin_edges(
    samples: Sequence[RuntimeSample],
    *,
    bin_width: float = 1.0,
    bin_min: float | None = None,
    bin_max: float | None = None,
) -> "np.ndarray":
    if not HAS_MATPLOTLIB or np is None:
        raise RuntimeError("matplotlib and numpy are required to build histogram bin edges")
    if bin_width <= 0:
        raise ValueError("bin_width must be positive")

    runtimes = [runtime for sample in samples for runtime in sample.runtimes]
    if not runtimes:
        raise ValueError("At least one runtime is required")

    lower = bin_min if bin_min is not None else math.floor(min(runtimes) / bin_width) * bin_width
    upper = bin_max if bin_max is not None else math.ceil(max(runtimes) / bin_width) * bin_width
    if upper <= lower:
        upper = lower + bin_width

    return np.arange(lower, upper + (bin_width * 0.5), bin_width)


def build_legend_handles(samples: Sequence[RuntimeSample]) -> list[object]:
    if not HAS_MATPLOTLIB or Line2D is None or Patch is None:
        raise RuntimeError("matplotlib is required to build legend handles")

    handles: list[object] = [
        Patch(facecolor=sample.color, edgecolor="white", label=sample.label)
        for sample in samples
    ]
    handles.extend(
        Line2D([0], [0], color=sample.color, linestyle="--", linewidth=1.6, label=f"{sample.label} mean")
        for sample in samples
    )
    return handles


def marker_axis_y_span(layout: str) -> tuple[float, float]:
    if layout in {"panels", "overlay"}:
        return (-0.055, 0.055)
    raise ValueError(f"Unsupported layout: {layout}")


def _write_figure_outputs(
    fig: object,
    *,
    output_dir: Path,
    basename: str,
    formats: Sequence[str],
) -> list[Path]:
    output_paths = []
    for suffix in formats:
        normalized_suffix = suffix.lower().lstrip(".")
        output_path = output_dir / f"{basename}.{normalized_suffix}"
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        output_paths.append(output_path)
    return output_paths


def _style_axis(axis: object, *, bin_width: float, x_min: float, x_max: float) -> None:
    axis.set_axisbelow(True)
    axis.grid(True, axis="both", color="#B8B8B8", linewidth=0.7, alpha=0.45)
    axis.xaxis.set_major_locator(MultipleLocator(runtime_tick_step(bin_width)))
    axis.set_xlim(x_min, x_max)
    axis.tick_params(axis="x", pad=7)


def _plot_runtime_markers(axis: object, sample: RuntimeSample, *, layout: str) -> None:
    y_min, y_max = marker_axis_y_span(layout)
    marker_kwargs = {
        "ymin": y_min,
        "ymax": y_max,
        "transform": axis.get_xaxis_transform(),
        "clip_on": False,
        "alpha": 0.98,
    }
    axis.vlines(sample.runtimes, color=sample.color, linewidth=1.6, zorder=8, **marker_kwargs)


def _apply_shared_y_limit(axes: Sequence[object]) -> None:
    y_max = max(axis.get_ylim()[1] for axis in axes)
    major_step = count_tick_step(y_max)
    for axis in axes:
        axis.set_ylim(0.0, max(1.0, math.ceil(y_max)))
        axis.yaxis.set_major_locator(MultipleLocator(major_step))


def _write_panel_histogram(
    samples: Sequence[RuntimeSample],
    *,
    output_dir: Path,
    basename: str,
    formats: Sequence[str],
    bin_edges: object,
    bin_width: float,
    x_min: float,
    x_max: float,
    show_markers: bool,
) -> list[Path]:
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(6.8, 3.3),
        sharex=True,
        sharey=True,
    )
    fig.subplots_adjust(left=0.11, right=0.99, bottom=0.22, top=0.78, wspace=0.08)

    for axis, sample in zip(axes, samples, strict=True):
        axis.hist(
            sample.runtimes,
            bins=bin_edges,
            color=sample.color,
            edgecolor="white",
            linewidth=0.8,
            alpha=0.88,
        )
        axis.axvline(sample.mean, color=sample.color, linestyle="--", linewidth=1.8)
        if show_markers:
            _plot_runtime_markers(axis, sample, layout="panels")
        _style_axis(axis, bin_width=bin_width, x_min=x_min, x_max=x_max)

    _apply_shared_y_limit(axes)
    axes[0].set_ylabel("Number of measured repeats", labelpad=12)
    fig.text(0.5, 0.055, "Wall-clock runtime (s)", ha="center", va="center", fontsize=10.5)
    fig.legend(
        handles=build_legend_handles(samples),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=4,
        frameon=True,
        borderaxespad=0.0,
    )
    output_paths = _write_figure_outputs(fig, output_dir=output_dir, basename=basename, formats=formats)
    plt.close(fig)
    return output_paths


def _write_overlay_histogram(
    samples: Sequence[RuntimeSample],
    *,
    output_dir: Path,
    basename: str,
    formats: Sequence[str],
    bin_edges: object,
    bin_width: float,
    x_min: float,
    x_max: float,
    show_markers: bool,
) -> list[Path]:
    fig, axis = plt.subplots(1, 1, figsize=(6.8, 3.3))
    fig.subplots_adjust(left=0.11, right=0.99, bottom=0.22, top=0.78)

    for sample in samples:
        axis.hist(
            sample.runtimes,
            bins=bin_edges,
            color=sample.color,
            edgecolor="white",
            linewidth=0.8,
            alpha=0.58,
        )
        axis.axvline(sample.mean, color=sample.color, linestyle="--", linewidth=1.8)
        if show_markers:
            _plot_runtime_markers(axis, sample, layout="overlay")

    _style_axis(axis, bin_width=bin_width, x_min=x_min, x_max=x_max)
    axis.set_ylim(0.0, max(1.0, math.ceil(axis.get_ylim()[1])))
    axis.yaxis.set_major_locator(MultipleLocator(count_tick_step(axis.get_ylim()[1])))
    axis.set_ylabel("Number of measured repeats", labelpad=12)
    fig.text(0.5, 0.055, "Wall-clock runtime (s)", ha="center", va="center", fontsize=10.5)
    fig.legend(
        handles=build_legend_handles(samples),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=4,
        frameon=True,
        borderaxespad=0.0,
    )
    output_paths = _write_figure_outputs(fig, output_dir=output_dir, basename=f"{basename}-overlay", formats=formats)
    plt.close(fig)
    return output_paths


def write_runtime_histogram(
    samples: Sequence[RuntimeSample],
    *,
    output_dir: Path,
    basename: str = DEFAULT_BASENAME,
    formats: Sequence[str] = DEFAULT_FORMATS,
    bin_width: float = 1.0,
    bin_min: float | None = None,
    bin_max: float | None = None,
    layout: str = "panels",
    show_markers: bool = True,
) -> list[Path]:
    if not HAS_MATPLOTLIB or plt is None or Line2D is None or Patch is None or MultipleLocator is None:
        raise RuntimeError("matplotlib is required to write runtime histogram figures")
    if len(samples) != 2:
        raise ValueError("This report figure expects exactly two runtime samples")
    if layout not in ("panels", "overlay"):
        raise ValueError(f"Unsupported histogram layout: {layout}")

    output_dir.mkdir(parents=True, exist_ok=True)
    bin_edges = build_bin_edges(samples, bin_width=bin_width, bin_min=bin_min, bin_max=bin_max)
    x_min = float(bin_edges[0])
    x_max = float(bin_edges[-1])

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "font.family": "DejaVu Sans",
        }
    )

    if layout == "panels":
        return _write_panel_histogram(
            samples,
            output_dir=output_dir,
            basename=basename,
            formats=formats,
            bin_edges=bin_edges,
            bin_width=bin_width,
            x_min=x_min,
            x_max=x_max,
            show_markers=show_markers,
        )
    return _write_overlay_histogram(
        samples,
        output_dir=output_dir,
        basename=basename,
        formats=formats,
        bin_edges=bin_edges,
        bin_width=bin_width,
        x_min=x_min,
        x_max=x_max,
        show_markers=show_markers,
    )


def write_runtime_histograms(
    samples: Sequence[RuntimeSample],
    *,
    output_dir: Path,
    basename: str = DEFAULT_BASENAME,
    formats: Sequence[str] = DEFAULT_FORMATS,
    bin_width: float = 1.0,
    bin_min: float | None = None,
    bin_max: float | None = None,
    layout: str = "both",
    show_markers: bool = True,
) -> list[Path]:
    if layout not in LAYOUT_CHOICES:
        raise ValueError(f"Unsupported layout: {layout}")

    layouts = ("panels", "overlay") if layout == "both" else (layout,)
    output_paths: list[Path] = []
    for selected_layout in layouts:
        output_paths.extend(
            write_runtime_histogram(
                samples,
                output_dir=output_dir,
                basename=basename,
                formats=formats,
                bin_width=bin_width,
                bin_min=bin_min,
                bin_max=bin_max,
                layout=selected_layout,
                show_markers=show_markers,
            )
        )
    return output_paths


def _parse_formats(raw: str) -> tuple[str, ...]:
    formats = tuple(item.strip().lower().lstrip(".") for item in raw.split(",") if item.strip())
    if not formats:
        raise argparse.ArgumentTypeError("At least one output format is required")
    return formats


def _load_successful_child_runtimes(path: Path) -> list[float]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    runtimes: list[float] = []
    for batch in payload.get("batches", []):
        for child in batch.get("children", []):
            if not _is_success_status(str(child.get("status", ""))):
                continue
            wall_clock_seconds = float(child.get("wallClockSeconds", 0.0) or 0.0)
            if wall_clock_seconds <= 0.0:
                continue
            runtimes.append(wall_clock_seconds)
    return runtimes


def count_tick_step(y_max: float) -> float:
    if y_max <= 10.0:
        return 1.0
    if y_max <= 20.0:
        return 2.0
    if y_max <= 50.0:
        return 5.0
    if y_max <= 100.0:
        return 10.0
    if y_max <= 200.0:
        return 20.0
    return 50.0


def runtime_tick_step(bin_width: float) -> float:
    if bin_width < 1.0:
        return 1.0
    return bin_width


def _is_success_status(status: str) -> bool:
    return status.strip().lower() in {"success", "successful", "succeeded", "complete", "completed", "ok", "passed"}


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot a two-panel runtime histogram comparison from existing model-speed summary.json files."
    )
    parser.add_argument("--batches-csv", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--level", choices=LEVEL_CHOICES, default="batch")
    parser.add_argument("--baseline-summary", type=Path, default=DEFAULT_BASELINE_SUMMARY)
    parser.add_argument("--cache-summary", type=Path, default=DEFAULT_CACHE_SUMMARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--formats", type=_parse_formats, default=DEFAULT_FORMATS)
    parser.add_argument("--bin-width", type=float, default=1.0)
    parser.add_argument("--bin-min", type=float, default=None)
    parser.add_argument("--bin-max", type=float, default=None)
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="both")
    parser.add_argument("--hide-markers", action="store_true")
    parser.add_argument("--baseline-label", default="Default")
    parser.add_argument("--cache-label", default="Cache-enabled")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.batches_csv is not None:
        load_sample = (
            load_seed_runtime_sample_from_batches_csv if args.level == "seed" else load_runtime_sample_from_batches_csv
        )
        samples = [
            load_sample(
                args.batches_csv,
                label=args.baseline_label,
                color=DEFAULT_BASELINE_COLOR,
                cache_enabled=False,
                workers=args.workers,
            ),
            load_sample(
                args.batches_csv,
                label=args.cache_label,
                color=DEFAULT_CACHE_COLOR,
                cache_enabled=True,
                workers=args.workers,
            ),
        ]
    else:
        samples = [
            load_runtime_sample(
                args.baseline_summary,
                label=args.baseline_label,
                color=DEFAULT_BASELINE_COLOR,
            ),
            load_runtime_sample(
                args.cache_summary,
                label=args.cache_label,
                color=DEFAULT_CACHE_COLOR,
            ),
        ]
    output_paths = write_runtime_histograms(
        samples,
        output_dir=args.output_dir,
        basename=args.basename,
        formats=args.formats,
        bin_width=args.bin_width,
        bin_min=args.bin_min,
        bin_max=args.bin_max,
        layout=args.layout,
        show_markers=not args.hide_markers,
    )
    for path in output_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
