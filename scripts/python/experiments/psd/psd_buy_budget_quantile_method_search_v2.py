#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Constrained quantile BUY* method search (v2.1) for PSD 2024 + PPD 2024/2025.

Latest findings (real-data smoke run on February 25, 2026):
  - Command:
    - python3 -m scripts.python.experiments.psd.psd_buy_budget_quantile_method_search_v2 \
      --ppd-status-mode both \
      --year-policy both \
      --guardrail-mode warn \
      --objective-weight-grid-profile minimal \
      --pareto-alpha-grid 1.8 \
      --workers 16 \
      --no-plot-overlays
  - Result:
    - Best variant:
      - `status=all|year_policy=pooled_2024_2025|alpha=1.8|weights=a12_p20_s4_c12`
      - `BUY_SCALE ~= 7.6238412132`
      - `BUY_EXPONENT ~= 1.0028939531`
      - `BUY_MU = 0`
      - `BUY_SIGMA ~= 0.4326188972`
    - Guardrails:
      - failed `BUY_EXPONENT <= 1.0` and `p95/income < 15` (about `15.99x` to `16.09x`).
    - Interpretation:
      - objective/anchor fit is reasonable, but current v2.1 settings still do
        not produce a production-eligible candidate without further tightening.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.io_properties import read_properties
from scripts.python.helpers.common.paths import ensure_output_dir
from scripts.python.helpers.psd.buy_budget_quantile_v2 import (
    DEFAULT_INCOME_CHECKPOINTS,
    DEFAULT_MEDIAN_TARGET_CURVE,
    DEFAULT_PARETO_ALPHA_GRID,
    EXPONENT_MAX_DEFAULT,
    GUARDRAIL_MODE_CHOICES,
    GUARDRAIL_MODE_WARN,
    HARD_P95_MULTIPLE_CAP,
    P95_SOFT_CAP_DEFAULT,
    PPD_STATUS_BOTH,
    PPD_STATUS_CHOICES,
    QuantileFitSpec,
    SIGMA_WARNING_HIGH,
    SIGMA_WARNING_LOW,
    SoftTargetCurve,
    TAIL_FAMILY_CHOICES,
    TAIL_FAMILY_PARETO,
    YEAR_POLICY_2024_ONLY,
    YEAR_POLICY_BOTH,
    YEAR_POLICY_CHOICES,
    build_objective_weight_profiles,
    evaluate_variants,
    reference_budget_rows,
    write_overlay_plots,
)


def _default_curve_cli() -> str:
    ordered = sorted(DEFAULT_MEDIAN_TARGET_CURVE.items())
    return ",".join(f"{income}:{target}" for income, target in ordered)


def _default_alpha_grid_cli() -> str:
    return ",".join(str(value) for value in DEFAULT_PARETO_ALPHA_GRID)


def _parse_float_grid(raw: str, *, flag_name: str) -> tuple[float, ...]:
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        raise SystemExit(f"{flag_name} must contain at least one numeric value.")
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError as exc:
            raise SystemExit(f"Invalid numeric token '{token}' for {flag_name}.") from exc
    return tuple(values)


def _parse_median_target_curve(raw: str) -> SoftTargetCurve:
    pairs = [token.strip() for token in raw.split(",") if token.strip()]
    if not pairs:
        raise SystemExit("--median-target-curve must provide at least one income:multiple pair.")

    checkpoints: list[int] = []
    max_multiples: list[float] = []
    for item in pairs:
        if ":" not in item:
            raise SystemExit(
                f"Invalid median-target entry '{item}'. Use income:multiple, e.g. 100000:5.4"
            )
        income_token, multiple_token = item.split(":", 1)
        try:
            income = int(float(income_token.strip()))
            multiple = float(multiple_token.strip())
        except ValueError as exc:
            raise SystemExit(f"Invalid median-target entry '{item}'.") from exc
        if income <= 0 or multiple <= 0.0:
            raise SystemExit(f"Median target entry must be positive: '{item}'.")
        checkpoints.append(income)
        max_multiples.append(multiple)

    ordered = sorted(zip(checkpoints, max_multiples), key=lambda pair: pair[0])
    return SoftTargetCurve(
        checkpoints=tuple(item[0] for item in ordered),
        max_multiples=tuple(item[1] for item in ordered),
    )


def _resolve_weight_grids(args: argparse.Namespace):
    profile = args.objective_weight_grid_profile
    if profile == "balanced":
        w_anchor = (8.0, 12.0, 16.0)
        w_p95 = (12.0, 20.0)
        w_sigma = (2.0, 4.0)
        w_curve = (8.0, 12.0)
    elif profile == "realism_heavy":
        w_anchor = (12.0, 16.0, 20.0)
        w_p95 = (20.0, 28.0, 36.0)
        w_sigma = (3.0, 5.0)
        w_curve = (12.0, 16.0, 20.0)
    elif profile == "minimal":
        w_anchor = (12.0,)
        w_p95 = (20.0,)
        w_sigma = (4.0,)
        w_curve = (12.0,)
    else:
        w_anchor = _parse_float_grid(args.w_anchor_grid, flag_name="--w-anchor-grid")
        w_p95 = _parse_float_grid(args.w_p95_grid, flag_name="--w-p95-grid")
        w_sigma = _parse_float_grid(args.w_sigma_grid, flag_name="--w-sigma-grid")
        w_curve = _parse_float_grid(args.w_curve_grid, flag_name="--w-curve-grid")

    profiles = build_objective_weight_profiles(
        w_anchor_values=w_anchor,
        w_p95_values=w_p95,
        w_sigma_values=w_sigma,
        w_curve_values=w_curve,
    )
    return profiles


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Constrained quantile BUY* method search (v2.1) for modern PSD/PPD.",
    )
    parser.add_argument(
        "--quarterly-csv",
        default="private-datasets/psd/2024/psd-quarterly-2024.csv",
        help="Path to PSD quarterly long-format CSV.",
    )
    parser.add_argument(
        "--ppd-csv-2024",
        default="private-datasets/ppd/pp-2024.csv",
        help="Path to PPD 2024 CSV.",
    )
    parser.add_argument(
        "--ppd-csv-2025",
        default=None,
        help="Path to PPD 2025 CSV. Required only for 2025_only, pooled_2024_2025, or both year policies.",
    )
    parser.add_argument(
        "--target-year-psd",
        type=int,
        default=2024,
        help="Target PSD year for modern marginals (default: 2024).",
    )
    parser.add_argument(
        "--ppd-status-mode",
        default=PPD_STATUS_BOTH,
        choices=PPD_STATUS_CHOICES,
        help="PPD status filter mode.",
    )
    parser.add_argument(
        "--year-policy",
        default=YEAR_POLICY_2024_ONLY,
        choices=YEAR_POLICY_CHOICES,
        help="PPD year policy for fit anchoring (default: 2024_only).",
    )
    parser.add_argument(
        "--guardrail-mode",
        default=GUARDRAIL_MODE_WARN,
        choices=GUARDRAIL_MODE_CHOICES,
        help="Guardrail enforcement mode for this experiment.",
    )
    parser.add_argument(
        "--hard-p95-cap",
        type=float,
        default=HARD_P95_MULTIPLE_CAP,
        help="Hard cap for p95 budget multiple gate (default: 15).",
    )
    parser.add_argument(
        "--exponent-max",
        type=float,
        default=EXPONENT_MAX_DEFAULT,
        help="Hard upper cap for BUY_EXPONENT (default: 1.0).",
    )
    parser.add_argument(
        "--p95-soft-cap",
        type=float,
        default=P95_SOFT_CAP_DEFAULT,
        help="Soft p95 cap used by objective hinge penalty (default: 14).",
    )
    parser.add_argument(
        "--sigma-warning-low",
        type=float,
        default=SIGMA_WARNING_LOW,
        help="Lower bound of sigma warning band (default: 0.2).",
    )
    parser.add_argument(
        "--sigma-warning-high",
        type=float,
        default=SIGMA_WARNING_HIGH,
        help="Upper bound of sigma warning band (default: 0.6).",
    )
    parser.add_argument(
        "--median-target-curve",
        default=_default_curve_cli(),
        help=(
            "Soft realism target curve as comma-separated income:multiple pairs "
            f"(default: {_default_curve_cli()})."
        ),
    )
    parser.add_argument(
        "--tail-family",
        default=TAIL_FAMILY_PARETO,
        choices=TAIL_FAMILY_CHOICES,
        help="Top-income-bin tail family (default: pareto).",
    )
    parser.add_argument(
        "--pareto-alpha-grid",
        default=_default_alpha_grid_cli(),
        help="Comma-separated Pareto alpha candidates.",
    )
    parser.add_argument(
        "--objective-weight-grid-profile",
        default="balanced",
        choices=("balanced", "realism_heavy", "minimal", "custom"),
        help="Deterministic objective weight grid profile.",
    )
    parser.add_argument(
        "--w-anchor-grid",
        default="8,12,16",
        help="Custom anchor-weight grid (comma-separated). Used when profile=custom.",
    )
    parser.add_argument(
        "--w-p95-grid",
        default="12,20",
        help="Custom p95-penalty weight grid. Used when profile=custom.",
    )
    parser.add_argument(
        "--w-sigma-grid",
        default="2,4",
        help="Custom sigma-penalty weight grid. Used when profile=custom.",
    )
    parser.add_argument(
        "--w-curve-grid",
        default="8,12",
        help="Custom median-curve-penalty weight grid. Used when profile=custom.",
    )
    parser.add_argument(
        "--plot-overlays",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate overlay plots (default: true).",
    )
    parser.add_argument(
        "--plot-pareto-ccdf",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate Pareto CCDF diagnostics when plotting overlays (default: true).",
    )
    parser.add_argument(
        "--plot-top-k",
        type=int,
        default=5,
        help="When plotting, render overlays for top-k ranked variants (default: 5).",
    )
    parser.add_argument(
        "--within-bin-points",
        type=int,
        default=11,
        help="Within-bin expansion points (default: 11).",
    )
    parser.add_argument(
        "--quantile-grid-size",
        type=int,
        default=4000,
        help="Quantile grid for deterministic generated-price series (default: 4000).",
    )
    parser.add_argument(
        "--ppd-mean-anchor-weight",
        type=float,
        default=4.0,
        help="Weight of PPD mean anchor in constrained quantile fit (default: 4.0).",
    )
    parser.add_argument(
        "--fixed-exponent",
        type=float,
        default=1.0,
        help="Fixed BUY_EXPONENT for 2024_only raked-quantile fitting (default: 1.0).",
    )
    parser.add_argument(
        "--income-open-upper-k",
        type=float,
        default=200.0,
        help="Fallback upper cap for open income bins in thousand GBP (default: 200).",
    )
    parser.add_argument(
        "--property-open-upper-k",
        type=float,
        default=2000.0,
        help="Open-top assumption for PSD property bins in thousand GBP (default: 2000).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory for CSV/JSON/plot exports.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top-ranked variants to print (default: 10).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Parallel workers for variant evaluation (default: 16).",
    )
    return parser


def _resolve_ppd_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    ppd_2024 = Path(args.ppd_csv_2024)
    if args.year_policy == YEAR_POLICY_2024_ONLY:
        return (ppd_2024,)
    if args.ppd_csv_2025 is None:
        raise SystemExit(f"--ppd-csv-2025 is required when --year-policy {args.year_policy}.")
    return (ppd_2024, Path(args.ppd_csv_2025))


def _load_reference_rows() -> dict[str, dict[str, float]]:
    refs: dict[str, dict[str, float]] = {}
    for label, path in (
        ("old_v0", Path("input-data-versions/v0/config.properties")),
        ("new_v40", Path("input-data-versions/v4.0/config.properties")),
    ):
        if not path.exists():
            continue
        props = read_properties(path)
        required = ("BUY_SCALE", "BUY_EXPONENT", "BUY_MU", "BUY_SIGMA")
        if not all(key in props for key in required):
            continue
        refs[label] = reference_budget_rows(
            buy_scale=float(props["BUY_SCALE"]),
            buy_exponent=float(props["BUY_EXPONENT"]),
            buy_mu=float(props["BUY_MU"]),
            buy_sigma=float(props["BUY_SIGMA"]),
            income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
        )
    return refs


def _write_csv(results, output_dir: str) -> Path:
    output_root = ensure_output_dir(output_dir)
    output_path = output_root / "PsdBuyBudgetMethodSearchV2.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "variant_id",
                "status_mode",
                "year_policy",
                "selected_alpha",
                "weight_profile_id",
                "buy_scale",
                "buy_exponent",
                "buy_mu",
                "buy_sigma",
                "guardrails_passed",
                "sigma_warning",
                "guardrail_failures",
                "guardrail_warnings",
                "worst_year_fit_distance",
                "fit_distance_2024",
                "fit_distance_2025",
                "fit_mean_error_2024",
                "fit_mean_error_2025",
                "fit_std_error_2024",
                "fit_std_error_2025",
                "anchor_price_implied_psd",
                "anchor_price_error",
                "objective_total",
                "objective_fit",
                "objective_anchor",
                "objective_p95",
                "objective_sigma",
                "objective_median_curve",
                "unknown_income_share",
                "fit_degradation_vs_baseline",
            ]
        )
        for rank, item in enumerate(results, start=1):
            writer.writerow(
                [
                    rank,
                    item.variant_id,
                    item.status_mode,
                    item.year_policy,
                    item.selected_alpha,
                    item.weight_profile_id,
                    item.buy_scale,
                    item.buy_exponent,
                    item.buy_mu,
                    item.buy_sigma,
                    str(item.guardrails.passed),
                    str(item.sigma_warning),
                    " | ".join(item.guardrails.hard_failures),
                    " | ".join(item.guardrails.warnings),
                    item.worst_year_fit_distance,
                    item.yearly_fit_distance.get(2024, float("inf")),
                    item.yearly_fit_distance.get(2025, float("inf")),
                    item.yearly_fit_mean_error.get(2024, float("inf")),
                    item.yearly_fit_mean_error.get(2025, float("inf")),
                    item.yearly_fit_std_error.get(2024, float("inf")),
                    item.yearly_fit_std_error.get(2025, float("inf")),
                    item.anchor.implied_price,
                    item.diagnostics.get("anchor_price_error"),
                    item.objective.objective_total,
                    item.objective.objective_fit,
                    item.objective.objective_anchor,
                    item.objective.objective_p95,
                    item.objective.objective_sigma,
                    item.objective.objective_median_curve,
                    item.diagnostics.get("unknown_income_share"),
                    item.fit_degradation_vs_baseline,
                ]
            )
    return output_path


def _write_summary_json(results, output_dir: str, plot_paths: list[str], args: argparse.Namespace) -> Path:
    output_root = ensure_output_dir(output_dir)
    summary_path = output_root / "PsdBuyBudgetMethodSearchV2Summary.json"
    top = results[0]
    payload = {
        "candidate_count": len(results),
        "policy": {
            "status_mode": args.ppd_status_mode,
            "year_policy": args.year_policy,
            "guardrail_mode": args.guardrail_mode,
            "tail_family": args.tail_family,
            "pareto_alpha_grid": args.pareto_alpha_grid,
            "objective_weight_grid_profile": args.objective_weight_grid_profile,
            "hard_p95_cap": args.hard_p95_cap,
            "exponent_max": args.exponent_max,
            "median_target_curve": args.median_target_curve,
        },
        "best": {
            "variant_id": top.variant_id,
            "status_mode": top.status_mode,
            "year_policy": top.year_policy,
            "selected_alpha": top.selected_alpha,
            "weight_profile_id": top.weight_profile_id,
            "buy_scale": top.buy_scale,
            "buy_exponent": top.buy_exponent,
            "buy_mu": top.buy_mu,
            "buy_sigma": top.buy_sigma,
            "guardrails_passed": top.guardrails.passed,
            "guardrail_failures": list(top.guardrails.hard_failures),
            "guardrail_warnings": list(top.guardrails.warnings),
            "worst_year_fit_distance": top.worst_year_fit_distance,
            "fit_distance_2024": top.yearly_fit_distance.get(2024),
            "fit_distance_2025": top.yearly_fit_distance.get(2025),
            "anchor_price_implied_psd": top.anchor.implied_price,
            "anchor_price_error": top.diagnostics.get("anchor_price_error"),
            "objective_total": top.objective.objective_total,
            "objective_fit": top.objective.objective_fit,
            "objective_anchor": top.objective.objective_anchor,
            "objective_p95": top.objective.objective_p95,
            "objective_sigma": top.objective.objective_sigma,
            "objective_median_curve": top.objective.objective_median_curve,
            "unknown_income_share": top.diagnostics.get("unknown_income_share"),
        },
        "plots": plot_paths,
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return summary_path


def _print_reference_rows(result) -> None:
    references = _load_reference_rows()
    candidate = reference_budget_rows(
        buy_scale=result.buy_scale,
        buy_exponent=result.buy_exponent,
        buy_mu=result.buy_mu,
        buy_sigma=result.buy_sigma,
        income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
    )

    print("\nBudget-multiple comparison rows (old vs v4.0 vs candidate)")
    labels = ["old_v0", "new_v40", "candidate"]
    rows = {
        "old_v0": references.get("old_v0"),
        "new_v40": references.get("new_v40"),
        "candidate": candidate,
    }

    for label in labels:
        row = rows.get(label)
        if row is None:
            print(f"{label}: missing")
            continue
        summary_parts = []
        for income in DEFAULT_INCOME_CHECKPOINTS:
            key = int(income)
            median_key = f"median_x_income_{key}"
            p95_key = f"p95_x_income_{key}"
            summary_parts.append(
                f"{key//1000}k median={format_float(row[median_key], 4)}x p95={format_float(row[p95_key], 4)}x"
            )
        print(f"{label}: " + " | ".join(summary_parts))


def main() -> None:
    args = build_arg_parser().parse_args()

    quarterly_path = Path(args.quarterly_csv)
    ppd_paths = _resolve_ppd_paths(args)
    missing = [str(path) for path in (quarterly_path, *ppd_paths) if not path.exists()]
    if missing:
        raise SystemExit("Missing input file(s): " + ", ".join(missing))

    if args.within_bin_points <= 0:
        raise SystemExit("within-bin-points must be positive.")
    if args.quantile_grid_size <= 0:
        raise SystemExit("quantile-grid-size must be positive.")
    if args.ppd_mean_anchor_weight < 0.0:
        raise SystemExit("ppd-mean-anchor-weight must be non-negative.")
    if args.fixed_exponent <= 0.0:
        raise SystemExit("fixed-exponent must be positive.")
    if args.top_k <= 0:
        raise SystemExit("top-k must be positive.")
    if args.plot_top_k <= 0:
        raise SystemExit("plot-top-k must be positive.")
    if args.workers <= 0:
        raise SystemExit("workers must be positive.")
    if args.hard_p95_cap <= 1.0:
        raise SystemExit("hard-p95-cap must be > 1.")
    if args.exponent_max <= 0.0:
        raise SystemExit("exponent-max must be positive.")

    median_target_curve = _parse_median_target_curve(args.median_target_curve)
    pareto_alpha_values = _parse_float_grid(args.pareto_alpha_grid, flag_name="--pareto-alpha-grid")
    weight_profiles = _resolve_weight_grids(args)

    spec = QuantileFitSpec(
        within_bin_points=args.within_bin_points,
        quantile_grid_size=args.quantile_grid_size,
        ppd_mean_anchor_weight=args.ppd_mean_anchor_weight,
        hard_p95_cap=args.hard_p95_cap,
        exponent_max=args.exponent_max,
        p95_soft_cap=args.p95_soft_cap,
        sigma_warning_low=args.sigma_warning_low,
        sigma_warning_high=args.sigma_warning_high,
        median_target_curve=median_target_curve,
        fixed_exponent=args.fixed_exponent if args.year_policy == YEAR_POLICY_2024_ONLY else None,
    )

    print("[stage] Starting v2.1 constrained-quantile search", flush=True)
    print(
        f"[stage] Evaluating status={args.ppd_status_mode}, year_policy={args.year_policy}, "
        f"alphas={len(pareto_alpha_values)}, weight_profiles={len(weight_profiles)}",
        flush=True,
    )
    start = time.monotonic()

    def progress_callback(processed: int, total: int, variant_id: str) -> None:
        elapsed = time.monotonic() - start
        rate = processed / elapsed if elapsed > 0.0 else 0.0
        print(
            "[progress] "
            f"{processed}/{total} "
            f"variant={variant_id} "
            f"elapsed={elapsed:.1f}s "
            f"rate={rate:.2f}/s",
            flush=True,
        )

    results = evaluate_variants(
        quarterly_csv=quarterly_path,
        target_year_psd=args.target_year_psd,
        ppd_paths=ppd_paths,
        status_mode=args.ppd_status_mode,
        year_policy=args.year_policy,
        guardrail_mode=args.guardrail_mode,
        spec=spec,
        objective_weight_profiles=weight_profiles,
        tail_family=args.tail_family,
        pareto_alpha_values=pareto_alpha_values,
        income_open_upper_k=args.income_open_upper_k,
        property_open_upper_k=args.property_open_upper_k,
        workers=args.workers,
        progress_callback=progress_callback,
    )

    elapsed = time.monotonic() - start
    print(f"[stage] Variant evaluation complete in {elapsed:.1f}s", flush=True)

    if not results:
        raise SystemExit("No candidate variants were evaluated.")

    print("PSD BUY* constrained quantile method search (v2.1)")
    print(f"Quarterly PSD: {args.quarterly_csv}")
    print(f"PPD 2024: {args.ppd_csv_2024}")
    print(f"PPD 2025: {args.ppd_csv_2025}")
    print(f"Target year PSD: {args.target_year_psd}")
    print(f"Status mode: {args.ppd_status_mode}")
    print(f"Year policy: {args.year_policy}")
    print(f"Guardrail mode: {args.guardrail_mode}")
    print(f"Tail family: {args.tail_family}")
    print(f"Pareto alpha grid: {args.pareto_alpha_grid}")
    print(f"Weight grid profile: {args.objective_weight_grid_profile}")
    print("")

    print("Rank\tObj\tWorstYearErr\tErr2024\tErr2025\tPassed\tAlpha\tScale\tExponent\tSigma\tVariant")
    for rank, item in enumerate(results[: args.top_k], start=1):
        print(
            f"{rank}\t{format_float(item.objective.objective_total)}\t{format_float(item.worst_year_fit_distance)}\t"
            f"{format_float(item.yearly_fit_distance.get(2024, float('inf')))}\t"
            f"{format_float(item.yearly_fit_distance.get(2025, float('inf')))}\t"
            f"{item.guardrails.passed}\t{format_float(item.selected_alpha)}\t"
            f"{format_float(item.buy_scale)}\t{format_float(item.buy_exponent)}\t"
            f"{format_float(item.buy_sigma)}\t{item.variant_id}"
        )

    best = results[0]
    print("\nBest candidate")
    print(f"Variant: {best.variant_id}")
    print(f"BUY_SCALE = {format_float(best.buy_scale)}")
    print(f"BUY_EXPONENT = {format_float(best.buy_exponent)}")
    print(f"BUY_MU = {format_float(best.buy_mu)}")
    print(f"BUY_SIGMA = {format_float(best.buy_sigma)}")
    print(f"Selected alpha = {format_float(best.selected_alpha)}")
    print(f"Guardrails passed: {best.guardrails.passed}")
    print(f"Objective total = {format_float(best.objective.objective_total)}")
    print(
        "Objective components = "
        f"fit:{format_float(best.objective.objective_fit)} "
        f"anchor:{format_float(best.objective.objective_anchor)} "
        f"p95:{format_float(best.objective.objective_p95)} "
        f"sigma:{format_float(best.objective.objective_sigma)} "
        f"curve:{format_float(best.objective.objective_median_curve)}"
    )
    print(
        f"Anchor implied PSD price = {format_float(best.anchor.implied_price)} ; "
        f"Anchor error = {format_float(best.diagnostics.get('anchor_price_error', float('nan')))}"
    )
    print(f"Unknown income share = {format_float(best.diagnostics.get('unknown_income_share', float('nan')), 6)}")

    if best.guardrails.hard_failures:
        print("Guardrail failures:")
        for item in best.guardrails.hard_failures:
            print(f"- {item}")
    if best.guardrails.warnings:
        print("Guardrail warnings:")
        for item in best.guardrails.warnings:
            print(f"- {item}")

    print("\nIncome spot checks (candidate)")
    for income in DEFAULT_INCOME_CHECKPOINTS:
        key = int(income)
        print(
            f"income={key}: median={format_float(best.guardrails.median_budget_multiples[key], 5)}x, "
            f"p95={format_float(best.guardrails.p95_budget_multiples[key], 5)}x"
        )

    _print_reference_rows(best)

    if args.output_dir is not None:
        csv_path = _write_csv(results, args.output_dir)
        print(f"\nCSV output: {csv_path}")

        plot_paths: list[str] = []
        if args.plot_overlays:
            plots_root = ensure_output_dir(args.output_dir) / "plots"
            plot_subset = results[: min(args.plot_top_k, len(results))]
            for item in plot_subset:
                plot_paths.extend(
                    str(path)
                    for path in write_overlay_plots(
                        result=item,
                        output_dir=plots_root,
                        year_for_distribution=2025,
                        plot_pareto_ccdf=args.plot_pareto_ccdf,
                    )
                )
            print(f"Overlay plots: {plots_root}")

        summary_path = _write_summary_json(results, args.output_dir, plot_paths, args)
        print(f"Summary JSON: {summary_path}")


if __name__ == "__main__":
    main()
