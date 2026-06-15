#!/usr/bin/env python3
"""Export output-calibration best-so-far convergence evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from pathlib import Path
from typing import Mapping, Sequence

CONVERGENCE_FILENAME = "method_convergence.csv"
SUMMARY_FILENAME = "method_summary.csv"
LIVE_CONVERGENCE_FILENAME = "method_convergence_live.csv"
LIVE_AGGREGATE_FILENAME = "method_convergence_aggregate_live.csv"
LIVE_SUMMARY_FILENAME = "method_summary_live.csv"
DEFAULT_MATPLOTLIB_CONFIG_DIRNAME = "uk-housing-matplotlib-cache"
LIVE_REFERENCE_X_COLOR = "#C92828"
LIVE_REFERENCE_Y_COLOR = "#1AC969"


def configure_matplotlib_environment(
    *, default_config_root: Path | None = None
) -> Path:
    """Set safe matplotlib defaults for terminal-only, threaded long runs."""

    root = default_config_root if default_config_root is not None else Path("/tmp")
    config_dir = root / DEFAULT_MATPLOTLIB_CONFIG_DIRNAME
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("MPLCONFIGDIR", str(config_dir))
    return Path(os.environ["MPLCONFIGDIR"])


configure_matplotlib_environment()


def ensure_noninteractive_matplotlib_backend() -> str:
    """Force a file-rendering backend before importing pyplot."""

    configure_matplotlib_environment()
    import matplotlib

    matplotlib.use("Agg", force=True)
    return str(matplotlib.get_backend())


def build_best_so_far_rows(*, method: str, member_csv: Path) -> list[dict[str, object]]:
    """Build 1-indexed best-so-far rows from a member-results CSV."""

    with member_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No member rows found: {member_csv}")

    output: list[dict[str, object]] = []
    best_loss: float | None = None
    best_evaluation: int | None = None
    best_iteration: int | None = None
    best_member_id: int | None = None
    for evaluation, row in enumerate(rows, start=1):
        loss = float(row["overallCompositeLoss"])
        iteration = int(float(row.get("iteration", 0)))
        member_id = int(float(row["memberId"]))
        if best_loss is None or loss < best_loss:
            best_loss = loss
            best_evaluation = evaluation
            best_iteration = iteration
            best_member_id = member_id
        assert best_loss is not None
        assert best_evaluation is not None
        assert best_iteration is not None
        assert best_member_id is not None
        output.append(
            {
                "method": method,
                "evaluation": evaluation,
                "iteration": iteration,
                "memberId": member_id,
                "overallCompositeLoss": loss,
                "bestSoFarLoss": best_loss,
                "bestEvaluation": best_evaluation,
                "bestIteration": best_iteration,
                "bestMemberId": best_member_id,
            }
        )
    return output


def build_live_best_so_far_rows(
    records: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Build best-so-far rows for method/replicate/evaluation records."""

    grouped: dict[tuple[str, int], list[Mapping[str, object]]] = {}
    for record in records:
        method = str(record["method"])
        replicate = int(record["replicate"])
        grouped.setdefault((method, replicate), []).append(record)

    output: list[dict[str, object]] = []
    for (method, replicate), rows in sorted(grouped.items()):
        best_loss: float | None = None
        best_evaluation: int | None = None
        best_member_id: int | None = None
        for row in sorted(rows, key=lambda item: int(item["evaluation"])):
            evaluation = int(row["evaluation"])
            member_id = int(row["memberId"])
            loss = float(row["overallCompositeLoss"])
            if best_loss is None or loss < best_loss:
                best_loss = loss
                best_evaluation = evaluation
                best_member_id = member_id
            assert best_loss is not None
            assert best_evaluation is not None
            assert best_member_id is not None
            output.append(
                {
                    "method": method,
                    "replicate": replicate,
                    "evaluation": evaluation,
                    "iteration": int(row.get("iteration", evaluation)),
                    "memberId": member_id,
                    "overallCompositeLoss": loss,
                    "bestSoFarLoss": best_loss,
                    "bestEvaluation": best_evaluation,
                    "bestMemberId": best_member_id,
                }
            )
    return output


def build_live_aggregate_rows(
    best_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Aggregate live best-so-far rows to method-level median and IQR curves."""

    grouped: dict[tuple[str, int], list[float]] = {}
    for row in best_rows:
        grouped.setdefault((str(row["method"]), int(row["evaluation"])), []).append(
            float(row["bestSoFarLoss"])
        )

    aggregate_rows: list[dict[str, object]] = []
    for (method, evaluation), values in sorted(grouped.items()):
        ordered = sorted(values)
        aggregate_rows.append(
            {
                "method": method,
                "evaluation": evaluation,
                "replicateCount": len(ordered),
                "medianBestSoFarLoss": _percentile(ordered, 50.0),
                "p25BestSoFarLoss": _percentile(ordered, 25.0),
                "p75BestSoFarLoss": _percentile(ordered, 75.0),
                "minBestSoFarLoss": min(ordered),
                "maxBestSoFarLoss": max(ordered),
            }
        )
    return aggregate_rows


def build_live_summary_rows(
    best_rows: Sequence[Mapping[str, object]],
    *,
    checkpoint_evaluations: Sequence[int] = (),
) -> list[dict[str, object]]:
    """Summarize each method's latest replicate-level best-so-far state."""

    by_method_replicate: dict[tuple[str, int], list[Mapping[str, object]]] = {}
    for row in best_rows:
        by_method_replicate.setdefault(
            (str(row["method"]), int(row["replicate"])), []
        ).append(row)

    methods = sorted({method for method, _ in by_method_replicate})
    summary_rows: list[dict[str, object]] = []
    for method in methods:
        replicate_rows = [
            sorted(rows, key=lambda item: int(item["evaluation"]))
            for (row_method, _), rows in by_method_replicate.items()
            if row_method == method
        ]
        final_rows = [rows[-1] for rows in replicate_rows if rows]
        if not final_rows:
            continue
        final_losses = [float(row["bestSoFarLoss"]) for row in final_rows]
        row: dict[str, object] = {
            "method": method,
            "replicateCount": len(final_rows),
            "latestMinEvaluation": min(int(row["evaluation"]) for row in final_rows),
            "latestMaxEvaluation": max(int(row["evaluation"]) for row in final_rows),
            "medianFinalBestLoss": statistics.median(final_losses),
            "minFinalBestLoss": min(final_losses),
            "maxFinalBestLoss": max(final_losses),
        }
        for checkpoint in checkpoint_evaluations:
            checkpoint_losses = []
            for rows in replicate_rows:
                matching = [
                    candidate
                    for candidate in rows
                    if int(candidate["evaluation"]) <= int(checkpoint)
                ]
                if matching:
                    checkpoint_losses.append(float(matching[-1]["bestSoFarLoss"]))
            if checkpoint_losses:
                row[f"medianBestLossAt{checkpoint}"] = statistics.median(
                    checkpoint_losses
                )
                row[f"replicateCountAt{checkpoint}"] = len(checkpoint_losses)
        summary_rows.append(row)
    return summary_rows


def write_live_convergence_artifacts(
    *,
    records: Sequence[Mapping[str, object]],
    output_dir: Path,
    checkpoint_evaluations: Sequence[int] = (),
    write_plot: bool = True,
    html_refresh_seconds: int = 15,
    x_minor_step: float | None = None,
    y_minor_step: float | None = None,
    reference_x: float | None = None,
    reference_x_label: str | None = None,
    reference_y_loss: float | None = None,
    reference_y_label: str | None = None,
) -> dict[str, object]:
    """Write live convergence CSVs, optional plot, and auto-refresh HTML."""

    output_dir.mkdir(parents=True, exist_ok=True)
    best_rows = build_live_best_so_far_rows(records)
    aggregate_rows = build_live_aggregate_rows(best_rows)
    summary_rows = build_live_summary_rows(
        best_rows, checkpoint_evaluations=checkpoint_evaluations
    )
    _write_csv(output_dir / LIVE_CONVERGENCE_FILENAME, best_rows)
    _write_csv(output_dir / LIVE_AGGREGATE_FILENAME, aggregate_rows)
    _write_csv(output_dir / LIVE_SUMMARY_FILENAME, summary_rows)
    plot_path = output_dir / "method_convergence_live.png"
    if write_plot:
        _write_live_convergence_plot(
            plot_path,
            aggregate_rows,
            x_minor_step=x_minor_step,
            y_minor_step=y_minor_step,
            reference_x=reference_x,
            reference_x_label=reference_x_label,
            reference_y_loss=reference_y_loss,
            reference_y_label=reference_y_label,
        )
    _write_live_html(
        output_dir / "live.html",
        plot_path=plot_path if write_plot else None,
        refresh_seconds=html_refresh_seconds,
    )
    return {
        "bestRows": best_rows,
        "aggregateRows": aggregate_rows,
        "summaryRows": summary_rows,
        "outputDir": str(output_dir),
    }


def run_convergence_export(
    *,
    series: Mapping[str, Path],
    output_dir: Path,
    baseline_loss: float | None = None,
    baseline_label: str = "Original model",
    target_loss: float | None = None,
    target_label: str = "TuRBO Optimised Model",
    write_plot: bool = True,
) -> dict[str, object]:
    """Write combined convergence and summary CSVs for one or more methods."""

    if not series:
        raise ValueError("At least one method series is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    convergence_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for method, member_csv in series.items():
        method_rows = build_best_so_far_rows(method=method, member_csv=member_csv)
        convergence_rows.extend(method_rows)
        final = method_rows[-1]
        first_baseline = _first_evaluation_below(method_rows, baseline_loss)
        first_target = _first_evaluation_below(method_rows, target_loss)
        summary_rows.append(
            {
                "method": method,
                "evaluations": len(method_rows),
                "bestLoss": float(final["bestSoFarLoss"]),
                "bestEvaluation": int(final["bestEvaluation"]),
                "bestIteration": int(final["bestIteration"]),
                "bestMemberId": int(final["bestMemberId"]),
                "finalBestLoss": float(final["bestSoFarLoss"]),
                "firstEvaluationBeatingBaseline": first_baseline,
                "beatsBaseline": first_baseline is not None,
                "firstEvaluationBeatingTarget": first_target,
                "beatsTarget": first_target is not None,
            }
        )

    _write_csv(output_dir / CONVERGENCE_FILENAME, convergence_rows)
    _write_csv(output_dir / SUMMARY_FILENAME, summary_rows)
    comparison = {
        "baselineLabel": baseline_label,
        "baselineLoss": baseline_loss,
        "targetLabel": target_label,
        "targetLoss": target_loss,
        "methods": summary_rows,
    }
    (output_dir / "method_comparison.json").write_text(
        json.dumps(comparison, indent=2) + "\n", encoding="utf-8"
    )
    if write_plot:
        _write_convergence_plot(
            output_dir / "method_convergence.png",
            convergence_rows,
            baseline_loss=baseline_loss,
            baseline_label=baseline_label,
            target_loss=target_loss,
            target_label=target_label,
        )
    return {
        "convergenceRows": convergence_rows,
        "summaryRows": summary_rows,
        "comparison": comparison,
        "outputDir": str(output_dir),
    }


def _first_evaluation_below(
    rows: Sequence[Mapping[str, object]], threshold: float | None
) -> int | None:
    if threshold is None:
        return None
    for row in rows:
        if float(row["bestSoFarLoss"]) <= threshold:
            return int(row["evaluation"])
    return None


def parse_series(raw_series: Sequence[str]) -> dict[str, Path]:
    """Parse CLI METHOD=CSV series arguments."""

    series: dict[str, Path] = {}
    for raw in raw_series:
        if "=" not in raw:
            raise ValueError(f"Series must use METHOD=CSV format: {raw!r}")
        method, raw_path = raw.split("=", 1)
        method = method.strip()
        if not method:
            raise ValueError("Series method label must be non-empty")
        series[method] = Path(raw_path).expanduser()
    return series


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export best-so-far convergence curves from output-calibration member CSVs.",
    )
    parser.add_argument(
        "--member-csv",
        action="append",
        required=True,
        help="Method series in METHOD=CSV format. Repeat for each method.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for convergence CSV and plot outputs.",
    )
    parser.add_argument(
        "--baseline-loss",
        type=float,
        help="Original-model baseline validation loss reference.",
    )
    parser.add_argument(
        "--baseline-label", default="Original model", help="Label for --baseline-loss."
    )
    parser.add_argument(
        "--target-loss", type=float, help="Target selected validation loss reference."
    )
    parser.add_argument(
        "--target-label",
        default="TuRBO Optimised Model",
        help="Label for --target-loss.",
    )
    parser.add_argument(
        "--no-plot", action="store_true", help="Write CSV outputs only."
    )
    return parser


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_convergence_plot(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    baseline_loss: float | None = None,
    baseline_label: str = "Original model",
    target_loss: float | None = None,
    target_label: str = "TuRBO Optimised Model",
) -> None:
    try:
        ensure_noninteractive_matplotlib_backend()
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "matplotlib is required for plots; rerun with --no-plot for CSV-only export"
        ) from exc

    by_method: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        by_method.setdefault(str(row["method"]), []).append(row)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for method, method_rows in by_method.items():
        ax.plot(
            [int(row["evaluation"]) for row in method_rows],
            [float(row["bestSoFarLoss"]) for row in method_rows],
            label=method,
            linewidth=2.0,
        )
    ax.set_xlabel("Model evaluations")
    ax.set_ylabel("Best-so-far validation loss")
    ax.grid(alpha=0.25)
    if baseline_loss is not None:
        ax.axhline(
            float(baseline_loss),
            color="#595959",
            linestyle="--",
            linewidth=1.2,
            label=baseline_label,
        )
    if target_loss is not None:
        ax.axhline(
            float(target_loss),
            color="#B45309",
            linestyle=":",
            linewidth=1.4,
            label=target_label,
        )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _write_live_convergence_plot(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    x_minor_step: float | None = None,
    y_minor_step: float | None = None,
    reference_x: float | None = None,
    reference_x_label: str | None = None,
    reference_y_loss: float | None = None,
    reference_y_label: str | None = None,
) -> None:
    try:
        ensure_noninteractive_matplotlib_backend()
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MultipleLocator
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "matplotlib is required for live plots; rerun with --no-plot for CSV-only export"
        ) from exc

    by_method: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        by_method.setdefault(str(row["method"]), []).append(row)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for method, method_rows in by_method.items():
        ordered = sorted(method_rows, key=lambda item: int(item["evaluation"]))
        xs = [int(row["evaluation"]) for row in ordered]
        medians = [float(row["medianBestSoFarLoss"]) for row in ordered]
        p25 = [float(row["p25BestSoFarLoss"]) for row in ordered]
        p75 = [float(row["p75BestSoFarLoss"]) for row in ordered]
        ax.plot(xs, medians, label=method, linewidth=2.0)
        ax.fill_between(xs, p25, p75, alpha=0.18)
    ax.set_xlabel("Model evaluations per replicate")
    ax.set_ylabel("Best-so-far validation loss")
    ax.grid(True, which="major", alpha=0.25)
    if x_minor_step is not None:
        ax.xaxis.set_minor_locator(MultipleLocator(float(x_minor_step)))
        ax.grid(True, axis="x", which="minor", alpha=0.14, linewidth=0.6)
    if y_minor_step is not None:
        ax.yaxis.set_minor_locator(MultipleLocator(float(y_minor_step)))
        ax.grid(True, axis="y", which="minor", alpha=0.14, linewidth=0.6)
    if reference_x is not None:
        ax.axvline(
            float(reference_x),
            color=LIVE_REFERENCE_X_COLOR,
            linestyle=":",
            linewidth=1.1,
            alpha=0.5,
            label=reference_x_label,
        )
    if reference_y_loss is not None:
        ax.axhline(
            float(reference_y_loss),
            color=LIVE_REFERENCE_Y_COLOR,
            linestyle=":",
            linewidth=1.1,
            alpha=0.5,
            label=reference_y_label,
        )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _write_live_html(
    path: Path, *, plot_path: Path | None, refresh_seconds: int
) -> None:
    image_html = (
        f'<img src="{plot_path.name}" alt="Live method convergence plot" style="max-width:100%;height:auto">'
        if plot_path is not None
        else "<p>Plot disabled. CSV artifacts are still updating.</p>"
    )
    path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html>",
                "<head>",
                '  <meta charset="utf-8">',
                f'  <meta http-equiv="refresh" content="{int(refresh_seconds)}">',
                "  <title>Output Calibration Method Comparison</title>",
                "</head>",
                "<body>",
                "  <h1>Output Calibration Method Comparison</h1>",
                f"  {image_html}",
                f'  <p><a href="{LIVE_CONVERGENCE_FILENAME}">replicate convergence CSV</a></p>',
                f'  <p><a href="{LIVE_AGGREGATE_FILENAME}">aggregate convergence CSV</a></p>',
                f'  <p><a href="{LIVE_SUMMARY_FILENAME}">method summary CSV</a></p>',
                "</body>",
                "</html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("At least one value is required")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * (float(percentile) / 100.0)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    return (
        float(sorted_values[lower_index]) * (1.0 - fraction)
        + float(sorted_values[upper_index]) * fraction
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    result = run_convergence_export(
        series=parse_series(args.member_csv),
        output_dir=Path(args.output_dir),
        baseline_loss=args.baseline_loss,
        baseline_label=args.baseline_label,
        target_loss=args.target_loss,
        target_label=args.target_label,
        write_plot=not args.no_plot,
    )
    print(
        f"[convergence] wrote {len(result['convergenceRows'])} rows to {result['outputDir']}"
    )


if __name__ == "__main__":
    main()
