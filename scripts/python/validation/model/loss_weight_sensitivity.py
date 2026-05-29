"""Cached validation-loss sensitivity analysis for v0 versus v0o7.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Mapping, Sequence

CURRENT_WEIGHT_LABEL = "r0.5-d0.25-current"
ORIGINAL_MODEL_LABEL = "The original model"
OPTIMISED_MODEL_LABEL = "The optimised model"
METRIC_DELTA_COLORBAR_LABEL = f"Optimised vs original model loss delta (%)"
TOTAL_LOSS_COLORBAR_LABEL = f"Optimised vs original model loss delta (%)"
TOTAL_LOSS_HEATMAP_COLORMAP = "RdBu_r"
RANK_STABILITY_COLORMAP = "Blues"
SIGN_HEATMAP_COLORMAP = "validation_delta_sign"
METRIC_DELTA_SIGN_COLORS = ("#2166AC", "#B2182B")
SIGN_HEATMAP_BAD_COLOR = "#F2F2F2"
SIGN_HEATMAP_BOUNDARIES = (-1.5, 0.0, 1.5)
SIGN_HEATMAP_TICKS = (-1, 1)
SIGN_HEATMAP_TICK_LABELS = ("Improved", "Regressed")
METRIC_DELTA_COLORBAR_SHRINK = 0.35
METRIC_DELTA_COLORBAR_FRACTION = 0.035
METRIC_DELTA_COLORBAR_PAD = 0.04
METRIC_DELTA_ANNOTATION_FONTSIZE = 7
TOTAL_LOSS_SIGNIFICANT_FIGURES = 3
RANK_STABILITY_DECIMALS = 3
CURRENT_WEIGHT_TICK_SUFFIX = "\n(current)"
GROUP_SEPARATOR_COLOR = "#1F1F1F"
GROUP_SEPARATOR_LINEWIDTH = 0.7
GROUP_SEPARATOR_TOP_EXTENSION = 0.35
GROUP_SEPARATOR_TOP_EXTENSION_FRACTION = 0.03
DEFAULT_BASELINE_PATH = Path("input-data-versions/validation-overlays/v0-2011.json")
DEFAULT_CANDIDATE_PATH = Path("input-data-versions/validation-overlays/v0o7-2011.json")
DEFAULT_OUTPUT_DIR = Path(
    "tmp/validation-loss-sensitivity/v0-v0o7-2011-10seed-500-3500"
)
EXPECTED_SEEDS = list(range(1, 11))
EXPECTED_WINDOW = {"startIndex": 500, "endIndex": 3500}
REPORT_METRIC_LABELS = {
    "core_mortgageApprovals": "Mortgage Approvals",
    "core_housingTransactions": "Housing Transactions",
    "core_advancesToFTB": "Advances to FTB",
    "core_advancesToHM": "Advances to Home Movers",
    "core_advancesToBTL": "Advances to BTL",
    "core_debtToIncome": "HH DTI",
    "core_priceToIncome": "House PIR",
    "core_housePriceGrowth": "House Price Growth",
    "core_hpiMean": "HPI Mean",
    "core_hpiStd": "HPI Std",
    "core_hpiCyclePeriod": "HPI Cycle Period",
    "rpi_mean": "RPI Mean",
    "household_owning_share": "HH Owning Share",
    "household_renting_share": "HH Private Renting Share",
    "core_ooDebtToIncome": "OO DTI",
    "core_rentalYield": "Rental Yield",
    "core_interestRateSpread": "Interest Rate Spread",
    "income_distribution_jsd": "Income Realism",
    "housing_wealth_distribution_jsd": "Housing Wealth Realism",
    "financial_wealth_distribution_jsd": "Financial Wealth Realism",
}


@dataclass(frozen=True)
class WeightSpec:
    label: str
    reliability: float
    dispersion_shape: float
    central: float = 1.0


@dataclass(frozen=True)
class WeightAxisGroup:
    start: int
    end: int
    center: float
    label: str


@dataclass(frozen=True)
class WeightAxisSpec:
    dispersion_labels: tuple[str, ...]
    reliability_groups: tuple[WeightAxisGroup, ...]
    separator_positions: tuple[float, ...]
    current_index: int | None


@dataclass(frozen=True)
class MetricComponents:
    metric_id: str
    central_distance: float
    reliability_raw: float
    dispersion_shape_raw: float
    metric_weight: float


def default_weight_grid() -> list[WeightSpec]:
    weights: list[WeightSpec] = []
    for reliability in (0.25, 0.5, 0.75):
        for dispersion_shape in (0.125, 0.25, 0.375, 0.5):
            if 0.0 < dispersion_shape < reliability:
                label = f"r{reliability:g}-d{dispersion_shape:g}"
                if reliability == 0.5 and dispersion_shape == 0.25:
                    label = CURRENT_WEIGHT_LABEL
                weights.append(
                    WeightSpec(
                        label=label,
                        reliability=reliability,
                        dispersion_shape=dispersion_shape,
                    )
                )
    return weights


def load_summary(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_expected_summary(
    summary: Mapping[str, object], *, expected_version: str
) -> None:
    if summary.get("version") != expected_version:
        raise ValueError(
            f"expected version {expected_version}, got {summary.get('version')}"
        )
    if summary.get("validationTargetYear") != 2011:
        raise ValueError(f"expected validationTargetYear 2011 for {expected_version}")
    if summary.get("seeds") != EXPECTED_SEEDS:
        raise ValueError(f"expected seeds {EXPECTED_SEEDS} for {expected_version}")
    window = summary.get("window")
    if not isinstance(window, Mapping) or dict(window) != EXPECTED_WINDOW:
        raise ValueError(f"expected window {EXPECTED_WINDOW} for {expected_version}")


def _float_or_zero(value: object) -> float:
    return 0.0 if value is None else float(value)


def metric_components_from_summary_metric(
    metric: Mapping[str, object],
) -> MetricComponents:
    metric_id = str(metric["metricId"])
    metric_weight = float(metric.get("metricWeight") or 0.0)
    if metric_weight <= 0.0 or metric.get("metricLoss") is None:
        raise ValueError(f"{metric_id} is not a scored metric")

    central_distance = _float_or_zero(metric.get("distanceComponent"))
    inside_rate_component = _float_or_zero(metric.get("insideRateComponent"))
    reliability_raw = inside_rate_component / 0.5

    normalized_iqr = metric.get("normalizedIqr")
    if normalized_iqr is None:
        normalized_iqr = _float_or_zero(metric.get("spreadComponent")) / 0.25

    level_component = _float_or_zero(metric.get("levelComponent"))
    normalized_level = level_component / 0.25
    dispersion_shape_raw = float(normalized_iqr) + normalized_level

    return MetricComponents(
        metric_id=metric_id,
        central_distance=central_distance,
        reliability_raw=reliability_raw,
        dispersion_shape_raw=dispersion_shape_raw,
        metric_weight=metric_weight,
    )


def rescore_metric_loss(components: MetricComponents, weight: WeightSpec) -> float:
    return (
        weight.central * components.central_distance
        + weight.reliability * components.reliability_raw
        + weight.dispersion_shape * components.dispersion_shape_raw
    )


@dataclass(frozen=True)
class ComparisonResult:
    weight_rows: list[dict[str, object]]
    metric_delta_by_weight: list[dict[str, object]]
    metric_delta_stability: list[dict[str, object]]
    rank_stability: list[dict[str, object]]


def scored_components_from_summary(
    summary: Mapping[str, object],
) -> list[MetricComponents]:
    raw_metrics = summary.get("metrics")
    if not isinstance(raw_metrics, Sequence):
        raise ValueError("summary is missing metrics")
    components: list[MetricComponents] = []
    for raw_metric in raw_metrics:
        if not isinstance(raw_metric, Mapping):
            raise ValueError("summary contains a non-object metric")
        if (
            raw_metric.get("requirement") != "required"
            or raw_metric.get("metricLoss") is None
        ):
            continue
        components.append(metric_components_from_summary_metric(raw_metric))
    if not components:
        raise ValueError("summary has no scored required metrics")
    return components


def aggregate_loss(components: Sequence[MetricComponents], weight: WeightSpec) -> float:
    total_weight = sum(component.metric_weight for component in components)
    if total_weight <= 0.0:
        raise ValueError("total metric weight must be positive")
    return (
        sum(
            rescore_metric_loss(component, weight) * component.metric_weight
            for component in components
        )
        / total_weight
    )


def sign_label(value: float, *, tolerance: float = 1.0e-12) -> str:
    if value < -tolerance:
        return "improved"
    if value > tolerance:
        return "regressed"
    return "tied"


def sign_score(value: float, *, tolerance: float = 1.0e-12) -> int:
    if value < -tolerance:
        return -1
    if value > tolerance:
        return 1
    return 0


def metric_display_label(metric_id: str, fallback_label: str) -> str:
    return REPORT_METRIC_LABELS.get(metric_id, fallback_label)


def _format_significant_figures(value: float, significant_figures: int) -> str:
    magnitude = math.floor(math.log10(abs(value))) + 1
    decimal_places = significant_figures - magnitude
    rounded_value = round(value, decimal_places)
    if decimal_places > 0:
        return f"{rounded_value:.{decimal_places}f}"
    return f"{rounded_value:.0f}"


def format_heatmap_label(
    value: float,
    *,
    decimals: int | None = None,
    significant_figures: int | None = None,
    suffix: str = "",
    signed: bool = False,
) -> str:
    if (decimals is None) == (significant_figures is None):
        raise ValueError("provide exactly one of decimals or significant_figures")
    if decimals is not None:
        rounded_value = round(value, decimals)
    else:
        rounded_value = round(value, significant_figures - math.floor(math.log10(abs(value))) - 1) if value else 0.0
    if rounded_value == 0:
        return f"0{suffix}"
    if significant_figures is not None:
        formatted_value = _format_significant_figures(rounded_value, significant_figures)
        if signed and rounded_value > 0:
            formatted_value = f"+{formatted_value}"
        return f"{formatted_value}{suffix}"
    if signed:
        return f"{rounded_value:+.{decimals}f}{suffix}"
    return f"{rounded_value:.{decimals}f}{suffix}"


def _loss_pct_delta(loss_delta: float, baseline_loss: float) -> float | None:
    if baseline_loss != 0.0:
        return (loss_delta / baseline_loss) * 100.0
    if loss_delta == 0.0:
        return 0.0
    return None


def _components_by_id(
    components: Sequence[MetricComponents],
) -> dict[str, MetricComponents]:
    return {component.metric_id: component for component in components}


def _metric_labels(summary: Mapping[str, object]) -> dict[str, str]:
    raw_metrics = summary.get("metrics")
    if not isinstance(raw_metrics, Sequence):
        return {}
    labels: dict[str, str] = {}
    for raw_metric in raw_metrics:
        if not isinstance(raw_metric, Mapping):
            continue
        metric_id = str(raw_metric.get("metricId"))
        fallback_label = str(raw_metric.get("label") or metric_id)
        labels[metric_id] = metric_display_label(metric_id, fallback_label)
    return labels


def _rank_values(
    components: Sequence[MetricComponents], weight: WeightSpec
) -> list[float]:
    return [rescore_metric_loss(component, weight) for component in components]


def spearman_correlation(
    reference_values: Sequence[float], observed_values: Sequence[float]
) -> float:
    if len(reference_values) != len(observed_values):
        raise ValueError("rank inputs must have the same length")
    n = len(reference_values)
    if n < 2:
        return 1.0
    reference_ranks = _ordinal_ranks(reference_values)
    observed_ranks = _ordinal_ranks(observed_values)
    mean_reference = sum(reference_ranks) / n
    mean_observed = sum(observed_ranks) / n
    covariance = sum(
        (a - mean_reference) * (b - mean_observed)
        for a, b in zip(reference_ranks, observed_ranks)
    )
    reference_var = sum((a - mean_reference) ** 2 for a in reference_ranks)
    observed_var = sum((b - mean_observed) ** 2 for b in observed_ranks)
    if reference_var == 0.0 or observed_var == 0.0:
        return 1.0
    return covariance / math.sqrt(reference_var * observed_var)


def _ordinal_ranks(values: Sequence[float]) -> list[float]:
    sorted_indices = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    for rank, index in enumerate(sorted_indices, start=1):
        ranks[index] = float(rank)
    return ranks


def kendall_tau(
    reference_values: Sequence[float], observed_values: Sequence[float]
) -> float:
    if len(reference_values) != len(observed_values):
        raise ValueError("rank inputs must have the same length")
    concordant = 0
    discordant = 0
    n = len(reference_values)
    for left in range(n):
        for right in range(left + 1, n):
            reference_delta = reference_values[left] - reference_values[right]
            observed_delta = observed_values[left] - observed_values[right]
            product = reference_delta * observed_delta
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 1.0
    return (concordant - discordant) / total


def rank_stability_rows(
    *,
    components_by_version: Mapping[str, Sequence[MetricComponents]],
    weights: Sequence[WeightSpec],
    worst_n: int = 5,
) -> list[dict[str, object]]:
    current_weight = next(
        weight for weight in weights if weight.label == CURRENT_WEIGHT_LABEL
    )
    rows: list[dict[str, object]] = []
    for version, components in components_by_version.items():
        reference_values = _rank_values(components, current_weight)
        reference_worst = _worst_metric_ids(
            components, reference_values, worst_n=worst_n
        )
        for weight in weights:
            observed_values = _rank_values(components, weight)
            observed_worst = _worst_metric_ids(
                components, observed_values, worst_n=worst_n
            )
            rows.append(
                {
                    "version": version,
                    "weightLabel": weight.label,
                    "spearman": spearman_correlation(reference_values, observed_values),
                    "kendall": kendall_tau(reference_values, observed_values),
                    "worstN": worst_n,
                    "worstNOverlap": len(set(reference_worst) & set(observed_worst)),
                    "currentWorstMetrics": "|".join(reference_worst),
                    "weightedWorstMetrics": "|".join(observed_worst),
                }
            )
    return rows


def _worst_metric_ids(
    components: Sequence[MetricComponents], values: Sequence[float], *, worst_n: int
) -> list[str]:
    paired = sorted(zip(components, values), key=lambda item: item[1], reverse=True)
    return [component.metric_id for component, _ in paired[:worst_n]]


def compare_summaries(
    *,
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    weights: Sequence[WeightSpec],
) -> ComparisonResult:
    if not weights:
        raise ValueError("at least one weight specification is required")

    baseline_components = scored_components_from_summary(baseline)
    candidate_components = scored_components_from_summary(candidate)
    baseline_by_id = _components_by_id(baseline_components)
    candidate_by_id = _components_by_id(candidate_components)
    metric_labels = _metric_labels(baseline)
    shared_metric_ids = sorted(set(baseline_by_id) & set(candidate_by_id))
    if not shared_metric_ids:
        raise ValueError("baseline and candidate have no shared scored metrics")

    ordered_baseline = [baseline_by_id[metric_id] for metric_id in shared_metric_ids]
    ordered_candidate = [candidate_by_id[metric_id] for metric_id in shared_metric_ids]

    weight_rows: list[dict[str, object]] = []
    metric_delta_by_weight: list[dict[str, object]] = []
    deltas_by_metric: dict[str, list[float]] = {
        metric_id: [] for metric_id in shared_metric_ids
    }

    for weight in weights:
        baseline_loss = aggregate_loss(ordered_baseline, weight)
        candidate_loss = aggregate_loss(ordered_candidate, weight)
        loss_delta = candidate_loss - baseline_loss
        weight_rows.append(
            {
                "weightLabel": weight.label,
                "centralWeight": weight.central,
                "reliabilityWeight": weight.reliability,
                "dispersionShapeWeight": weight.dispersion_shape,
                "baselineLoss": baseline_loss,
                "candidateLoss": candidate_loss,
                "lossDelta": loss_delta,
                "lossPctDelta": _loss_pct_delta(loss_delta, baseline_loss),
                "candidateLower": loss_delta < 0.0,
            }
        )
        for metric_id, baseline_component, candidate_component in zip(
            shared_metric_ids, ordered_baseline, ordered_candidate
        ):
            baseline_metric_loss = rescore_metric_loss(baseline_component, weight)
            candidate_metric_loss = rescore_metric_loss(candidate_component, weight)
            metric_delta = candidate_metric_loss - baseline_metric_loss
            metric_pct_delta = _loss_pct_delta(metric_delta, baseline_metric_loss)
            deltas_by_metric[metric_id].append(metric_delta)
            metric_delta_by_weight.append(
                {
                    "weightLabel": weight.label,
                    "metricId": metric_id,
                    "metricLabel": metric_labels.get(metric_id, metric_id),
                    "baselineLoss": baseline_metric_loss,
                    "candidateLoss": candidate_metric_loss,
                    "lossDelta": metric_delta,
                    "lossPctDelta": metric_pct_delta,
                    "deltaSign": sign_label(metric_delta),
                }
            )

    reference_label = (
        CURRENT_WEIGHT_LABEL
        if any(weight.label == CURRENT_WEIGHT_LABEL for weight in weights)
        else weights[0].label
    )
    reference_delta_by_metric = {
        row["metricId"]: row["lossDelta"]
        for row in metric_delta_by_weight
        if row["weightLabel"] == reference_label
    }
    metric_delta_stability = []
    for metric_id in shared_metric_ids:
        signs = [sign_label(delta) for delta in deltas_by_metric[metric_id]]
        reference_sign = sign_label(float(reference_delta_by_metric[metric_id]))
        metric_delta_stability.append(
            {
                "metricId": metric_id,
                "metricLabel": metric_labels.get(metric_id, metric_id),
                "currentDelta": reference_delta_by_metric[metric_id],
                "currentSign": reference_sign,
                "stableSign": all(sign == reference_sign for sign in signs),
                "improvedCount": signs.count("improved"),
                "regressedCount": signs.count("regressed"),
                "tiedCount": signs.count("tied"),
                "minDelta": min(deltas_by_metric[metric_id]),
                "maxDelta": max(deltas_by_metric[metric_id]),
            }
        )

    rank_rows = []
    if any(weight.label == CURRENT_WEIGHT_LABEL for weight in weights):
        rank_rows = rank_stability_rows(
            components_by_version={
                str(baseline["version"]): ordered_baseline,
                str(candidate["version"]): ordered_candidate,
            },
            weights=weights,
        )
    return ComparisonResult(
        weight_rows=weight_rows,
        metric_delta_by_weight=metric_delta_by_weight,
        metric_delta_stability=metric_delta_stability,
        rank_stability=rank_rows,
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"no rows to write for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    *,
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    result: ComparisonResult,
) -> None:
    all_candidate_lower = all(bool(row["candidateLower"]) for row in result.weight_rows)
    unstable_metrics = [
        row for row in result.metric_delta_stability if not bool(row["stableSign"])
    ]
    current_row = next(
        row for row in result.weight_rows if row["weightLabel"] == CURRENT_WEIGHT_LABEL
    )
    lines = [
        "# v0 versus v0o7 loss-weight sensitivity",
        "",
        f"- Baseline: `{baseline['version']}` loss at current weights = `{current_row['baselineLoss']:.12f}`",
        f"- Candidate: `{candidate['version']}` loss at current weights = `{current_row['candidateLoss']:.12f}`",
        f"- Current-weight delta: `{current_row['lossDelta']:.12f}`",
        f"- Candidate lower across all weights: `{all_candidate_lower}`",
        f"- Metrics with delta sign flips: `{len(unstable_metrics)}`",
        "",
        "Generated from cached validation overlay summaries only; no Java model runs were executed.",
        "",
    ]
    if unstable_metrics:
        lines.append("## Metrics With Delta Sign Flips")
        lines.append("")
        for row in unstable_metrics:
            lines.append(
                f"- `{row['metricId']}`: current `{row['currentSign']}`, "
                f"min `{row['minDelta']}`, max `{row['maxDelta']}`"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_figures(output_dir: Path, result: ComparisonResult) -> None:
    plt, colors, np = _load_plotting()
    _write_total_loss_heatmap(output_dir, result, plt, colors, np)
    _write_metric_delta_heatmap(output_dir, result, plt, colors, np)
    _remove_stale_figure(output_dir, "metric_delta_sign_heatmap")
    _write_rank_stability_heatmap(output_dir, result, plt, np)


def _load_plotting():
    Path("tmp/matplotlib").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(Path("tmp/matplotlib").resolve()))
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.colors as colors
    import matplotlib.pyplot as plt
    import numpy as np

    return plt, colors, np


def _weight_sort_key(label: str) -> tuple[float, float]:
    row = next((row for row in default_weight_grid() if row.label == label), None)
    if row is None:
        return (math.inf, math.inf)
    return (row.reliability, row.dispersion_shape)


def _weight_spec_for_label(label: str) -> WeightSpec | None:
    return next((row for row in default_weight_grid() if row.label == label), None)


def _weight_axis_label(label: str) -> str:
    row = _weight_spec_for_label(label)
    if row is None:
        return label
    return f"r={row.reliability:g}\nd={row.dispersion_shape:g}"


def weight_axis_spec(weight_labels: Sequence[str]) -> WeightAxisSpec:
    dispersion_labels: list[str] = []
    reliability_groups: list[WeightAxisGroup] = []
    separator_positions: list[float] = []
    current_index: int | None = None
    group_start = 0
    group_label: str | None = None

    for index, weight_label in enumerate(weight_labels):
        if weight_label == CURRENT_WEIGHT_LABEL:
            current_index = index
        weight = _weight_spec_for_label(weight_label)
        if weight is None:
            next_group_label = weight_label
            dispersion_label = weight_label
        else:
            next_group_label = f"{weight.reliability:g}"
            dispersion_label = f"{weight.dispersion_shape:g}"
        if weight_label == CURRENT_WEIGHT_LABEL:
            dispersion_label = f"{dispersion_label}{CURRENT_WEIGHT_TICK_SUFFIX}"
        dispersion_labels.append(dispersion_label)

        if group_label is None:
            group_label = next_group_label
            group_start = index
        elif next_group_label != group_label:
            group_end = index - 1
            separator_positions.append(index - 0.5)
            reliability_groups.append(
                WeightAxisGroup(
                    start=group_start,
                    end=group_end,
                    center=(group_start + group_end) / 2.0,
                    label=group_label,
                )
            )
            group_label = next_group_label
            group_start = index

    if group_label is not None:
        group_end = len(weight_labels) - 1
        reliability_groups.append(
            WeightAxisGroup(
                start=group_start,
                end=group_end,
                center=(group_start + group_end) / 2.0,
                label=group_label,
            )
        )

    return WeightAxisSpec(
        dispersion_labels=tuple(dispersion_labels),
        reliability_groups=tuple(reliability_groups),
        separator_positions=tuple(separator_positions),
        current_index=current_index,
    )


def _save_figure(fig, output_dir: Path, stem: str) -> None:
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.clf()


def _remove_stale_figure(output_dir: Path, stem: str) -> None:
    for suffix in (".pdf", ".png"):
        path = output_dir / f"{stem}{suffix}"
        if path.exists():
            path.unlink()


def _annotate_heatmap(
    ax,
    data,
    *,
    cmap,
    norm,
    decimals: int | None = None,
    significant_figures: int | None = None,
    color_data=None,
    suffix: str = "",
    signed: bool = False,
    fontsize: int = 8,
) -> None:
    color_values = data if color_data is None else color_data
    for row_index in range(data.shape[0]):
        for column_index in range(data.shape[1]):
            value = data[row_index, column_index]
            if getattr(value, "mask", False):
                continue
            color_value = color_values[row_index, column_index]
            numeric_value = float(value)
            if getattr(color_value, "mask", False):
                text_color = "black"
            else:
                red, green, blue, _ = cmap(norm(float(color_value)))
                luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                text_color = "black" if luminance > 0.55 else "white"
            ax.text(
                column_index,
                row_index,
                format_heatmap_label(
                    numeric_value,
                    decimals=decimals,
                    significant_figures=significant_figures,
                    suffix=suffix,
                    signed=signed,
                ),
                ha="center",
                va="center",
                color=text_color,
                fontsize=fontsize,
            )


def _academic_axes(ax) -> None:
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_color("black")
    ax.tick_params(axis="both", length=3, width=0.8, color="black")


def group_separator_top_y(*, row_count: int) -> float:
    scaled_extension = max(0.0, row_count) * GROUP_SEPARATOR_TOP_EXTENSION_FRACTION
    return -0.5 - min(GROUP_SEPARATOR_TOP_EXTENSION, scaled_extension)


def _apply_grouped_weight_axis(
    ax, weight_labels: Sequence[str], *, row_count: int
) -> None:
    spec = weight_axis_spec(weight_labels)
    ax.set_xticks(range(len(weight_labels)), spec.dispersion_labels)
    ax.tick_params(axis="x", labelrotation=0)
    ax.set_xlabel("Dispersion/shape weight, d")

    top_axis = ax.secondary_xaxis("top")
    top_axis.set_xticks([group.center for group in spec.reliability_groups])
    top_axis.set_xticklabels([group.label for group in spec.reliability_groups])
    top_axis.set_xlabel("Reliability weight, r")
    top_axis.tick_params(axis="x", length=0, pad=4)
    for spine in top_axis.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_color("black")

    if row_count > 0:
        x_limits = ax.get_xlim()
        y_limits = ax.get_ylim()
        top_y = group_separator_top_y(row_count=row_count)
        bottom_y = row_count - 0.5
        for separator_position in spec.separator_positions:
            ax.plot(
                [separator_position, separator_position],
                [bottom_y, top_y],
                color=GROUP_SEPARATOR_COLOR,
                linewidth=GROUP_SEPARATOR_LINEWIDTH,
                zorder=4,
                clip_on=False,
                solid_capstyle="butt",
            )
        ax.set_xlim(x_limits)
        ax.set_ylim(y_limits)


def _diverging_norm(values: Sequence[float], colors):
    max_abs = max((abs(value) for value in values), default=1.0)
    if max_abs == 0.0:
        max_abs = 1.0
    return colors.TwoSlopeNorm(vmin=-max_abs, vcenter=0.0, vmax=max_abs)


def _write_total_loss_heatmap(
    output_dir: Path, result: ComparisonResult, plt, colors, np
) -> None:
    reliabilities = sorted(
        {float(row["reliabilityWeight"]) for row in result.weight_rows}
    )
    dispersions = sorted(
        {float(row["dispersionShapeWeight"]) for row in result.weight_rows}
    )
    matrix = np.full((len(reliabilities), len(dispersions)), np.nan)
    for row in result.weight_rows:
        row_index = reliabilities.index(float(row["reliabilityWeight"]))
        column_index = dispersions.index(float(row["dispersionShapeWeight"]))
        matrix[row_index, column_index] = float(row["lossPctDelta"])

    masked = np.ma.masked_invalid(matrix)
    cmap = plt.colormaps[TOTAL_LOSS_HEATMAP_COLORMAP].copy()
    cmap.set_bad("#E6E6E6")
    norm = _diverging_norm(
        [float(row["lossPctDelta"]) for row in result.weight_rows], colors
    )
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    image = ax.imshow(masked, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(dispersions)), [f"{value:g}" for value in dispersions])
    ax.set_yticks(range(len(reliabilities)), [f"{value:g}" for value in reliabilities])
    ax.set_xlabel("Dispersion/shape weight")
    ax.set_ylabel("Reliability weight")
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label(TOTAL_LOSS_COLORBAR_LABEL)
    _annotate_heatmap(
        ax,
        masked,
        significant_figures=TOTAL_LOSS_SIGNIFICANT_FIGURES,
        cmap=cmap,
        norm=norm,
        suffix="%",
        signed=True,
    )
    _academic_axes(ax)
    fig.tight_layout()
    _save_figure(fig, output_dir, "total_loss_heatmap")
    plt.close(fig)


def _write_metric_delta_heatmap(
    output_dir: Path, result: ComparisonResult, plt, colors, np
) -> None:
    weight_labels = sorted(
        {str(row["weightLabel"]) for row in result.metric_delta_by_weight},
        key=_weight_sort_key,
    )
    current_pct_deltas = {
        str(row["metricId"]): float(row["lossPctDelta"])
        for row in result.metric_delta_by_weight
        if row["weightLabel"] == CURRENT_WEIGHT_LABEL
        and row["lossPctDelta"] is not None
    }
    metric_labels_by_id = {
        str(row["metricId"]): str(row["metricLabel"])
        for row in result.metric_delta_by_weight
    }
    metric_ids = sorted(
        current_pct_deltas, key=lambda metric_id: current_pct_deltas[metric_id]
    )
    pct_matrix = np.full((len(metric_ids), len(weight_labels)), np.nan)
    sign_matrix = np.full((len(metric_ids), len(weight_labels)), np.nan)
    pct_values_by_key = {
        (str(row["metricId"]), str(row["weightLabel"])): (
            float(row["lossPctDelta"]) if row["lossPctDelta"] is not None else np.nan
        )
        for row in result.metric_delta_by_weight
    }
    sign_values_by_key = {
        (str(row["metricId"]), str(row["weightLabel"])): sign_score(
            float(row["lossDelta"])
        )
        for row in result.metric_delta_by_weight
    }
    for row_index, metric_id in enumerate(metric_ids):
        for column_index, weight_label in enumerate(weight_labels):
            key = (metric_id, weight_label)
            pct_matrix[row_index, column_index] = pct_values_by_key[key]
            sign_score_value = sign_values_by_key[key]
            sign_matrix[row_index, column_index] = (
                np.nan if sign_score_value == 0 else sign_score_value
            )

    masked_pct = np.ma.masked_invalid(pct_matrix)
    masked_sign = np.ma.masked_invalid(sign_matrix)
    cmap = colors.ListedColormap(METRIC_DELTA_SIGN_COLORS, name=SIGN_HEATMAP_COLORMAP)
    cmap.set_bad(SIGN_HEATMAP_BAD_COLOR)
    norm = colors.BoundaryNorm(SIGN_HEATMAP_BOUNDARIES, cmap.N)
    fig_height = max(6.0, 0.34 * len(metric_ids))
    fig, ax = plt.subplots(figsize=(9.5, fig_height))
    image = ax.imshow(masked_sign, cmap=cmap, norm=norm, aspect="auto")
    _apply_grouped_weight_axis(ax, weight_labels, row_count=len(metric_ids))
    ax.set_yticks(
        range(len(metric_ids)),
        [metric_labels_by_id[metric_id] for metric_id in metric_ids],
    )
    ax.set_ylabel("Validation metric")
    colorbar = fig.colorbar(
        image,
        ax=ax,
        ticks=SIGN_HEATMAP_TICKS,
        shrink=METRIC_DELTA_COLORBAR_SHRINK,
        fraction=METRIC_DELTA_COLORBAR_FRACTION,
        pad=METRIC_DELTA_COLORBAR_PAD,
    )
    colorbar.ax.set_yticklabels(SIGN_HEATMAP_TICK_LABELS)
    colorbar.ax.tick_params(labelsize=8, length=0)
    colorbar.set_label(METRIC_DELTA_COLORBAR_LABEL, fontsize=9)
    _annotate_heatmap(
        ax,
        masked_pct,
        decimals=1,
        cmap=cmap,
        norm=norm,
        color_data=masked_sign,
        suffix="%",
        signed=True,
        fontsize=METRIC_DELTA_ANNOTATION_FONTSIZE,
    )
    _academic_axes(ax)
    fig.tight_layout()
    _save_figure(fig, output_dir, "metric_delta_heatmap")
    plt.close(fig)


def _write_rank_stability_heatmap(
    output_dir: Path, result: ComparisonResult, plt, np
) -> None:
    rank_rows = list(result.rank_stability)
    if not rank_rows:
        return
    versions = ["v0", "v0o7"]
    model_labels = {"v0": ORIGINAL_MODEL_LABEL, "v0o7": OPTIMISED_MODEL_LABEL}
    weight_labels = sorted(
        {str(row["weightLabel"]) for row in rank_rows}, key=_weight_sort_key
    )
    matrix = np.full((len(versions), len(weight_labels)), np.nan)
    values_by_key = {
        (str(row["version"]), str(row["weightLabel"])): float(row["spearman"])
        for row in rank_rows
    }
    for row_index, version in enumerate(versions):
        for column_index, weight_label in enumerate(weight_labels):
            matrix[row_index, column_index] = values_by_key[(version, weight_label)]

    masked = np.ma.masked_invalid(matrix)
    cmap = plt.colormaps[RANK_STABILITY_COLORMAP].copy()
    fig, ax = plt.subplots(figsize=(9.5, 2.8))
    image = ax.imshow(masked, cmap=cmap, vmin=0.75, vmax=1.0, aspect="auto")
    _apply_grouped_weight_axis(ax, weight_labels, row_count=len(versions))
    ax.set_yticks(range(len(versions)), [model_labels[version] for version in versions])
    ax.set_ylabel("Model")
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("Per-metric rank correlation (ρ)")
    _annotate_heatmap(ax, masked, decimals=RANK_STABILITY_DECIMALS, cmap=cmap, norm=image.norm)
    _academic_axes(ax)
    fig.tight_layout()
    _save_figure(fig, output_dir, "rank_stability_heatmap")
    plt.close(fig)


def run_analysis(
    *,
    baseline_path: Path,
    candidate_path: Path,
    output_dir: Path,
    weights: Sequence[WeightSpec] | None = None,
) -> ComparisonResult:
    selected_weights = list(weights) if weights is not None else default_weight_grid()
    baseline = load_summary(baseline_path)
    candidate = load_summary(candidate_path)
    validate_expected_summary(baseline, expected_version="v0")
    validate_expected_summary(candidate, expected_version="v0o7")
    result = compare_summaries(
        baseline=baseline, candidate=candidate, weights=selected_weights
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "weight_summary.csv", result.weight_rows)
    write_csv(output_dir / "metric_delta_by_weight.csv", result.metric_delta_by_weight)
    write_csv(output_dir / "metric_delta_stability.csv", result.metric_delta_stability)
    write_csv(output_dir / "rank_stability.csv", result.rank_stability)
    write_report(
        output_dir / "report.md", baseline=baseline, candidate=candidate, result=result
    )
    write_figures(output_dir, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rescore cached v0/v0o7 2011 validation summaries under alternative generic loss weights."
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_analysis(
        baseline_path=args.baseline,
        candidate_path=args.candidate,
        output_dir=args.output_dir,
    )
    all_candidate_lower = all(bool(row["candidateLower"]) for row in result.weight_rows)
    unstable_metric_count = sum(
        1 for row in result.metric_delta_stability if not bool(row["stableSign"])
    )
    print(f"wrote sensitivity artifacts to {args.output_dir}")
    print(f"candidate_lower_all_weights={all_candidate_lower}")
    print(f"metric_delta_sign_flips={unstable_metric_count}")


if __name__ == "__main__":
    main()
