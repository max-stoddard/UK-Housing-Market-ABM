#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate BUY* parameters (v2.1) from modern PSD 2024 + PPD.

This production script uses realism-constrained quantile fitting with:
- BUY_MU hard lock to 0,
- hard p95 multiple cap,
- BUY_EXPONENT cap,
- deterministic Pareto/weight-grid variant search,
- mandatory anchor term from PSD median loan + median LTV,
- promotion gate on fit degradation versus unconstrained baseline.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
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
    GUARDRAIL_MODE_FAIL,
    HARD_P95_MULTIPLE_CAP,
    P95_SOFT_CAP_DEFAULT,
    PPD_STATUS_A_ONLY,
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
    apply_fit_degradation,
    build_objective_weight_profiles,
    evaluate_baseline_best_fit,
    evaluate_variants,
    rank_variants,
    reference_budget_rows,
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

    return build_objective_weight_profiles(
        w_anchor_values=w_anchor,
        w_p95_values=w_p95,
        w_sigma_values=w_sigma,
        w_curve_values=w_curve,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate BUY* parameters (v2.1) using realism-constrained quantile fit.",
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
        default=PPD_STATUS_A_ONLY,
        choices=PPD_STATUS_CHOICES,
        help="PPD status mode variants to evaluate (default: a_only).",
    )
    parser.add_argument(
        "--year-policy",
        default=YEAR_POLICY_2024_ONLY,
        choices=YEAR_POLICY_CHOICES,
        help="Year policy variants to evaluate (default: 2024_only).",
    )
    parser.add_argument(
        "--guardrail-mode",
        default=GUARDRAIL_MODE_FAIL,
        choices=GUARDRAIL_MODE_CHOICES,
        help="Guardrail mode for candidate filtering (default: fail).",
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
        "--fit-degradation-max",
        type=float,
        default=0.10,
        help="Maximum allowed fit degradation vs unconstrained baseline (default: 0.10).",
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
        help="Optional output directory for CSV/JSON export.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Parallel workers for variant evaluation (default: 16).",
    )
    return parser


def _write_csv(*, output_dir: str, selected, eligible, rejected, baseline_best_fit: float, fit_degradation_max: float) -> Path:
    output_root = ensure_output_dir(output_dir)
    output_path = output_root / "PsdBuyBudgetCalibrationV2.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "value", "variant_id"])
        writer.writerow(["BUY_SCALE", format_float(selected.buy_scale), selected.variant_id])
        writer.writerow(["BUY_EXPONENT", format_float(selected.buy_exponent), selected.variant_id])
        writer.writerow(["BUY_MU", format_float(selected.buy_mu), selected.variant_id])
        writer.writerow(["BUY_SIGMA", format_float(selected.buy_sigma), selected.variant_id])

        writer.writerow([])
        writer.writerow(["diagnostic", "value", ""])
        writer.writerow(["selected_variant", selected.variant_id, ""])
        writer.writerow(["selected_alpha", format_float(selected.selected_alpha), ""])
        writer.writerow(["selected_weight_profile", selected.weight_profile_id, ""])
        writer.writerow(["selected_worst_year_fit_distance", format_float(selected.worst_year_fit_distance), ""])
        writer.writerow(["selected_fit_distance_2024", format_float(selected.yearly_fit_distance.get(2024, float('inf'))), ""])
        writer.writerow(["selected_fit_distance_2025", format_float(selected.yearly_fit_distance.get(2025, float('inf'))), ""])
        writer.writerow(["baseline_best_fit_distance", format_float(baseline_best_fit), ""])
        writer.writerow(["fit_degradation_max", format_float(fit_degradation_max), ""])
        writer.writerow(["selected_fit_degradation_vs_baseline", format_float(selected.fit_degradation_vs_baseline or float('nan')), ""])
        writer.writerow(["eligible_variant_count", str(len(eligible)), ""])
        writer.writerow(["rejected_variant_count", str(len(rejected)), ""])
        writer.writerow(["guardrails_passed", str(selected.guardrails.passed), ""])
        writer.writerow(["anchor_price_implied_psd", format_float(selected.anchor.implied_price), ""])
        writer.writerow(["anchor_price_error", format_float(selected.diagnostics.get("anchor_price_error", float("nan"))), ""])
        writer.writerow(["unknown_income_share", format_float(selected.diagnostics.get("unknown_income_share", float("nan")), 8), ""])
        writer.writerow(["objective_total", format_float(selected.objective.objective_total), ""])
        writer.writerow(["objective_fit", format_float(selected.objective.objective_fit), ""])
        writer.writerow(["objective_anchor", format_float(selected.objective.objective_anchor), ""])
        writer.writerow(["objective_p95", format_float(selected.objective.objective_p95), ""])
        writer.writerow(["objective_sigma", format_float(selected.objective.objective_sigma), ""])
        writer.writerow(["objective_median_curve", format_float(selected.objective.objective_median_curve), ""])

        for income in DEFAULT_INCOME_CHECKPOINTS:
            key = int(income)
            writer.writerow([f"median_x_income_{key}", format_float(selected.guardrails.median_budget_multiples[key], 6), ""])
            writer.writerow([f"p95_x_income_{key}", format_float(selected.guardrails.p95_budget_multiples[key], 6), ""])

        writer.writerow([])
        writer.writerow(
            [
                "rank",
                "variant_id",
                "status_mode",
                "year_policy",
                "selected_alpha",
                "weight_profile_id",
                "guardrails_passed",
                "fit_degradation_vs_baseline",
                "within_fit_degradation_gate",
                "worst_year_fit_distance",
                "buy_scale",
                "buy_exponent",
                "buy_mu",
                "buy_sigma",
                "objective_total",
            ]
        )
        for rank, item in enumerate(eligible + rejected, start=1):
            degradation = item.fit_degradation_vs_baseline
            within_gate = degradation is not None and degradation <= fit_degradation_max
            writer.writerow(
                [
                    rank,
                    item.variant_id,
                    item.status_mode,
                    item.year_policy,
                    item.selected_alpha,
                    item.weight_profile_id,
                    str(item.guardrails.passed),
                    degradation,
                    str(within_gate),
                    item.worst_year_fit_distance,
                    item.buy_scale,
                    item.buy_exponent,
                    item.buy_mu,
                    item.buy_sigma,
                    item.objective.objective_total,
                ]
            )

    return output_path


def _write_summary_json(*, output_dir: str, selected, eligible, rejected, baseline_best_fit: float, fit_degradation_max: float) -> Path:
    output_root = ensure_output_dir(output_dir)
    path = output_root / "PsdBuyBudgetCalibrationV2Summary.json"
    payload = {
        "baseline_best_fit_distance": baseline_best_fit,
        "fit_degradation_max": fit_degradation_max,
        "selected": {
            "variant_id": selected.variant_id,
            "status_mode": selected.status_mode,
            "year_policy": selected.year_policy,
            "selected_alpha": selected.selected_alpha,
            "weight_profile_id": selected.weight_profile_id,
            "buy_scale": selected.buy_scale,
            "buy_exponent": selected.buy_exponent,
            "buy_mu": selected.buy_mu,
            "buy_sigma": selected.buy_sigma,
            "worst_year_fit_distance": selected.worst_year_fit_distance,
            "fit_distance_2024": selected.yearly_fit_distance.get(2024),
            "fit_distance_2025": selected.yearly_fit_distance.get(2025),
            "fit_degradation_vs_baseline": selected.fit_degradation_vs_baseline,
            "guardrails_passed": selected.guardrails.passed,
            "guardrail_failures": list(selected.guardrails.hard_failures),
            "guardrail_warnings": list(selected.guardrails.warnings),
            "anchor_price_implied_psd": selected.anchor.implied_price,
            "anchor_price_error": selected.diagnostics.get("anchor_price_error"),
            "objective_total": selected.objective.objective_total,
            "objective_fit": selected.objective.objective_fit,
            "objective_anchor": selected.objective.objective_anchor,
            "objective_p95": selected.objective.objective_p95,
            "objective_sigma": selected.objective.objective_sigma,
            "objective_median_curve": selected.objective.objective_median_curve,
            "unknown_income_share": selected.diagnostics.get("unknown_income_share"),
            "source_year_psd": selected.diagnostics.get("source_year_psd"),
            "source_year_ppd": selected.diagnostics.get("source_year_ppd"),
            "ppd_2025_loaded": selected.diagnostics.get("ppd_2025_loaded"),
            "ppd_rows_used_raked": selected.diagnostics.get("ppd_rows_used_raked"),
            "quantile_residuals_log": [
                {
                    "level": level,
                    "targetPrice": target,
                    "modelPrice": model,
                    "residualLogPrice": math.log(target) - math.log(model),
                }
                for level, target, model in zip(
                    selected.diagnostics.get("quantile_levels", []),
                    selected.observed_price_quantiles,
                    selected.modeled_median_quantiles,
                )
            ],
        },
        "eligible_variant_count": len(eligible),
        "rejected_variant_count": len(rejected),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return path


def _reference_rows() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
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
        out[label] = reference_budget_rows(
            buy_scale=float(props["BUY_SCALE"]),
            buy_exponent=float(props["BUY_EXPONENT"]),
            buy_mu=float(props["BUY_MU"]),
            buy_sigma=float(props["BUY_SIGMA"]),
            income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
        )
    return out


def _resolve_ppd_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    ppd_2024 = Path(args.ppd_csv_2024)
    if args.year_policy == YEAR_POLICY_2024_ONLY:
        return (ppd_2024,)
    if args.ppd_csv_2025 is None:
        raise SystemExit(f"--ppd-csv-2025 is required when --year-policy {args.year_policy}.")
    return (ppd_2024, Path(args.ppd_csv_2025))


def _print_near_miss_candidates(results, fit_degradation_max: float, limit: int = 5) -> None:
    ordered = rank_variants(results)
    print("Top near-miss variants:")
    for item in ordered[:limit]:
        deg = item.fit_degradation_vs_baseline
        fit_gate = deg is not None and deg <= fit_degradation_max
        print(
            f"- {item.variant_id} | pass_guardrails={item.guardrails.passed} "
            f"| fit_degradation={format_float(deg if deg is not None else float('nan'))} "
            f"| within_fit_gate={fit_gate} "
            f"| objective={format_float(item.objective.objective_total)} "
            f"| worst_year_fit={format_float(item.worst_year_fit_distance)}"
        )
        if item.guardrails.hard_failures:
            print(f"  failures: {' | '.join(item.guardrails.hard_failures)}")


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
    if args.workers <= 0:
        raise SystemExit("workers must be positive.")
    if args.hard_p95_cap <= 1.0:
        raise SystemExit("hard-p95-cap must be > 1.")
    if args.exponent_max <= 0.0:
        raise SystemExit("exponent-max must be positive.")
    if args.fit_degradation_max < 0.0:
        raise SystemExit("fit-degradation-max must be >= 0.")

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

    print("[stage] Starting v2.1 production calibration", flush=True)
    print("[stage] Running unconstrained baseline best-fit search", flush=True)
    baseline_start = time.monotonic()

    baseline = evaluate_baseline_best_fit(
        quarterly_csv=quarterly_path,
        target_year_psd=args.target_year_psd,
        ppd_paths=ppd_paths,
        status_mode=args.ppd_status_mode,
        year_policy=args.year_policy,
        spec=spec,
        tail_family=args.tail_family,
        pareto_alpha_values=pareto_alpha_values,
        income_open_upper_k=args.income_open_upper_k,
        property_open_upper_k=args.property_open_upper_k,
        workers=args.workers,
    )
    if not baseline:
        raise SystemExit("Baseline evaluation returned no variants.")
    baseline_best_fit = min(item.worst_year_fit_distance for item in baseline)
    baseline_elapsed = time.monotonic() - baseline_start
    print(
        f"[stage] Baseline complete in {baseline_elapsed:.1f}s (best worst-year fit={baseline_best_fit:.6f})",
        flush=True,
    )

    print("[stage] Running realism-constrained variant search", flush=True)
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

    constrained = evaluate_variants(
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
    if not constrained:
        raise SystemExit("No constrained variants were evaluated.")

    results = apply_fit_degradation(results=constrained, baseline_best_fit=baseline_best_fit)
    elapsed = time.monotonic() - start
    print(f"[stage] Constrained search complete in {elapsed:.1f}s", flush=True)

    fit_max = args.fit_degradation_max
    eligible = [
        item
        for item in results
        if item.guardrails.passed
        and item.fit_degradation_vs_baseline is not None
        and item.fit_degradation_vs_baseline <= fit_max
    ]
    rejected = [item for item in results if item not in eligible]

    if not eligible:
        _print_near_miss_candidates(results, fit_max, limit=5)
        raise SystemExit(
            "No production-eligible BUY* variant found: all candidates failed hard realism gates "
            f"and/or fit degradation gate (max {fit_max:.2%})."
        )

    selected = rank_variants(eligible)[0]

    print("PSD BUY* production calibration (v2.1)")
    print(f"Quarterly PSD: {args.quarterly_csv}")
    print(f"PPD 2024: {args.ppd_csv_2024}")
    print(f"PPD 2025: {args.ppd_csv_2025 if args.ppd_csv_2025 is not None else 'not loaded'}")
    print(f"Target year PSD: {args.target_year_psd}")
    print(f"Status mode: {args.ppd_status_mode}")
    print(f"Year policy: {args.year_policy}")
    print(f"Guardrail mode: {args.guardrail_mode}")
    print(f"Tail family: {args.tail_family}")
    print(f"Pareto alpha grid: {args.pareto_alpha_grid}")
    print(f"Weight grid profile: {args.objective_weight_grid_profile}")
    print("")
    print(f"Eligible variants: {len(eligible)}")
    print(f"Rejected variants: {len(rejected)}")

    print("\nSelected variant")
    print(f"Variant: {selected.variant_id}")
    print(f"BUY_SCALE = {format_float(selected.buy_scale)}")
    print(f"BUY_EXPONENT = {format_float(selected.buy_exponent)}")
    print(f"BUY_MU = {format_float(selected.buy_mu)}")
    print(f"BUY_SIGMA = {format_float(selected.buy_sigma)}")
    print(f"Selected alpha = {format_float(selected.selected_alpha)}")
    print(f"Weight profile = {selected.weight_profile_id}")
    print(f"Worst-year fit distance = {format_float(selected.worst_year_fit_distance)}")
    print(f"Fit distance 2024 = {format_float(selected.yearly_fit_distance.get(2024, float('inf')))}")
    print(f"Fit distance 2025 = {format_float(selected.yearly_fit_distance.get(2025, float('inf')))}")
    print(f"Baseline best fit = {format_float(baseline_best_fit)}")
    print(f"Fit degradation vs baseline = {format_float(selected.fit_degradation_vs_baseline or float('nan'))}")
    print(
        f"Anchor implied PSD price = {format_float(selected.anchor.implied_price)} ; "
        f"Anchor error = {format_float(selected.diagnostics.get('anchor_price_error', float('nan')))}"
    )

    print("\nIncome spot checks (selected)")
    for income in DEFAULT_INCOME_CHECKPOINTS:
        key = int(income)
        median = selected.guardrails.median_budget_multiples[key]
        p95 = selected.guardrails.p95_budget_multiples[key]
        print(f"income={key}: median={format_float(median, 5)}x, p95={format_float(p95, 5)}x")

    refs = _reference_rows()
    candidate_ref = reference_budget_rows(
        buy_scale=selected.buy_scale,
        buy_exponent=selected.buy_exponent,
        buy_mu=selected.buy_mu,
        buy_sigma=selected.buy_sigma,
        income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
    )

    print("\nBudget-multiple comparison rows")
    for label in ("old_v0", "new_v40", "candidate"):
        row = refs.get(label) if label != "candidate" else candidate_ref
        if row is None:
            print(f"{label}: missing")
            continue
        parts = []
        for income in DEFAULT_INCOME_CHECKPOINTS:
            key = int(income)
            parts.append(
                f"{key//1000}k median={format_float(row[f'median_x_income_{key}'], 4)}x "
                f"p95={format_float(row[f'p95_x_income_{key}'], 4)}x"
            )
        print(f"{label}: " + " | ".join(parts))

    if args.output_dir is not None:
        csv_path = _write_csv(
            output_dir=args.output_dir,
            selected=selected,
            eligible=eligible,
            rejected=rejected,
            baseline_best_fit=baseline_best_fit,
            fit_degradation_max=fit_max,
        )
        summary_path = _write_summary_json(
            output_dir=args.output_dir,
            selected=selected,
            eligible=eligible,
            rejected=rejected,
            baseline_best_fit=baseline_best_fit,
            fit_degradation_max=fit_max,
        )
        print(f"\nCSV output: {csv_path}")
        print(f"Summary JSON: {summary_path}")


if __name__ == "__main__":
    main()
