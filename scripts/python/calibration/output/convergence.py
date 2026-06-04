#!/usr/bin/env python3
"""Export output-calibration best-so-far convergence evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

CONVERGENCE_FILENAME = "method_convergence.csv"
SUMMARY_FILENAME = "method_summary.csv"


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
    (output_dir / "method_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
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


def _first_evaluation_below(rows: Sequence[Mapping[str, object]], threshold: float | None) -> int | None:
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
    parser.add_argument("--output-dir", required=True, help="Directory for convergence CSV and plot outputs.")
    parser.add_argument("--baseline-loss", type=float, help="Original-model baseline validation loss reference.")
    parser.add_argument("--baseline-label", default="Original model", help="Label for --baseline-loss.")
    parser.add_argument("--target-loss", type=float, help="Target selected validation loss reference.")
    parser.add_argument("--target-label", default="TuRBO Optimised Model", help="Label for --target-loss.")
    parser.add_argument("--no-plot", action="store_true", help="Write CSV outputs only.")
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
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError("matplotlib is required for plots; rerun with --no-plot for CSV-only export") from exc

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
        ax.axhline(float(baseline_loss), color="#595959", linestyle="--", linewidth=1.2, label=baseline_label)
    if target_loss is not None:
        ax.axhline(float(target_loss), color="#B45309", linestyle=":", linewidth=1.4, label=target_label)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


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
    print(f"[convergence] wrote {len(result['convergenceRows'])} rows to {result['outputDir']}")


if __name__ == "__main__":
    main()
