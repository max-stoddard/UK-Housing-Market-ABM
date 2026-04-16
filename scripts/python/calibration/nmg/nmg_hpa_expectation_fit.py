#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the locked HPA expectation calibration method selected by the search artifact.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.nmg.hpa_expectation import (
    HpaExpectationCandidateResult,
    HpaExpectationCandidateSpec,
    HpaExpectationFitClassification,
    HpaExpectationFitPoint,
    build_survey_target_result,
    evaluate_candidate_fit,
    load_nmg_wave_csv,
)
from scripts.python.helpers.nmg.linkage import (
    build_matched_panel_row_indices,
    load_pid_subsid_linkage,
)
from scripts.python.helpers.ppd.hpa_signal_methods import build_ppd_signal_index, load_ppd_rows
from scripts.python.helpers.ppd.hpa_signal_methods import build_hpa_signal_from_index
from scripts.python.experiments.nmg.nmg_hpa_expectation_method_search import (
    PRODUCTION_MODE,
    candidate_spec_from_dict,
)

LOCKED_SURVEY_TARGET = "national_cross_section__midpoint_exact"
LOCKED_SIGNAL_METHOD = "annual_mean_annualised"
LOCKED_CATEGORY_KEY = "A"
LOCKED_REGRESSION_TYPE = "huber"
LOCKED_ANCHOR_POLICY = "same_year_two_year_base"


@dataclass(frozen=True)
class CalibrationOutput:
    selected_candidate: HpaExpectationCandidateSpec
    factor: float
    const: float
    classification: HpaExpectationFitClassification
    core_rmse: float
    leave_one_out_rmse: float
    fit_points: tuple[HpaExpectationFitPoint, ...]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the locked HPA expectation calibration from a production search artifact.",
    )
    parser.add_argument(
        "search_artifact",
        help="Path to the production search artifact JSON emitted by nmg_hpa_expectation_method_search.py",
    )
    parser.add_argument(
        "--target-year",
        type=int,
        default=2024,
        help="Production target survey year (default: 2024).",
    )
    return parser


def _load_search_artifact(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("mode") != PRODUCTION_MODE:
        raise ValueError(f"Search artifact is not a production-mode artifact: {path}")
    return payload


def _result_from_artifact(payload: dict[str, object]) -> HpaExpectationCandidateResult:
    selected_result_data = dict(payload["selected_result"])
    candidate_spec = candidate_spec_from_dict(dict(selected_result_data["candidate_spec"]))
    classification_data = dict(selected_result_data["classification"])
    fit_points = tuple(
        HpaExpectationFitPoint(
            survey_wave_label=str(point["survey_wave_label"]),
            survey_year=int(point["survey_year"]),
            survey_target=float(point["survey_target"]),
            signal_value=float(point["signal_value"]),
            signal_method_name=str(point["signal_method_name"]),
            signal_anchor_year=int(point["signal_anchor_year"]),
            signal_base_year=int(point["signal_base_year"]),
            signal_months=(
                tuple(int(month) for month in point["signal_months"])
                if point.get("signal_months") is not None
                else None
            ),
        )
        for point in selected_result_data["fit_points"]
    )
    return HpaExpectationCandidateResult(
        candidate_spec=candidate_spec,
        factor=float(selected_result_data["factor"]),
        const=float(selected_result_data["const"]),
        classification=HpaExpectationFitClassification(
            label=str(classification_data["label"]),
            is_admissible=bool(classification_data["is_admissible"]),
            is_preferred=bool(classification_data["is_preferred"]),
        ),
        core_rmse=float(selected_result_data["core_rmse"]),
        leave_one_out_rmse=float(selected_result_data["leave_one_out_rmse"]),
        legacy_distance=(
            float(selected_result_data["legacy_distance"])
            if selected_result_data.get("legacy_distance") is not None
            else None
        ),
        fit_points=fit_points,
    )


def _verify_selected_method(candidate_spec: HpaExpectationCandidateSpec) -> None:
    if candidate_spec.survey_target_spec.name != LOCKED_SURVEY_TARGET:
        raise ValueError(
            "Search artifact selected an unexpected survey target: "
            f"{candidate_spec.survey_target_spec.name}"
        )
    if candidate_spec.signal_method_name != LOCKED_SIGNAL_METHOD:
        raise ValueError(
            "Search artifact selected an unexpected signal method: "
            f"{candidate_spec.signal_method_name}"
        )
    if candidate_spec.category_key != LOCKED_CATEGORY_KEY:
        raise ValueError(
            "Search artifact selected an unexpected category key: "
            f"{candidate_spec.category_key}"
        )
    if candidate_spec.regression_type != LOCKED_REGRESSION_TYPE:
        raise ValueError(
            "Search artifact selected an unexpected regression type: "
            f"{candidate_spec.regression_type}"
        )
    if candidate_spec.anchor_policy_name != LOCKED_ANCHOR_POLICY:
        raise ValueError(
            "Search artifact selected an unexpected anchor policy: "
            f"{candidate_spec.anchor_policy_name}"
        )


def run_calibration(*, search_artifact_path: Path) -> CalibrationOutput:
    payload = _load_search_artifact(search_artifact_path)
    selected_result = _result_from_artifact(payload)
    candidate_spec = selected_result.candidate_spec
    _verify_selected_method(candidate_spec)
    fit_wave_labels = tuple(str(value) for value in payload["fit_wave_labels"])
    nmg_input_paths = {wave_label: Path(path) for wave_label, path in dict(payload["nmg_input_paths"]).items()}
    ppd_input_paths = [Path(path) for path in payload["ppd_input_paths"]]
    linkage_xlsx_path = payload.get("linkage_xlsx_path")

    waves = {
        wave_label: load_nmg_wave_csv(path, wave_label=wave_label)
        for wave_label, path in nmg_input_paths.items()
    }
    all_ppd_rows, _stats = load_ppd_rows(ppd_input_paths)
    signal_index = build_ppd_signal_index(
        all_ppd_rows,
        category_key=candidate_spec.category_key,
        category_types={"A"} if candidate_spec.category_key == "A" else None,
    )

    matched_row_indices = None
    if candidate_spec.survey_target_spec.use_matched_panel:
        if linkage_xlsx_path is None:
            raise ValueError("Selected candidate requires linkage data, but the artifact does not include a linkage path.")
        linkage = load_pid_subsid_linkage(Path(str(linkage_xlsx_path)))
        matched_row_indices = build_matched_panel_row_indices(
            waves,
            required_wave_labels=fit_wave_labels,
            linkage=linkage,
        )

    survey_results = {}
    for wave_label in fit_wave_labels:
        survey_results[wave_label] = build_survey_target_result(
            waves[wave_label],
            candidate_spec.survey_target_spec,
            matched_row_indices=matched_row_indices.get(wave_label) if matched_row_indices else None,
        )

    fit_points = []
    for point in selected_result.fit_points:
        survey_result = survey_results[point.survey_wave_label]
        signal = build_hpa_signal_from_index(
            signal_index,
            anchor_year=point.signal_anchor_year,
            base_year=point.signal_base_year,
            method_name=candidate_spec.signal_method_name,
        )
        fit_points.append(
            HpaExpectationFitPoint(
                survey_wave_label=point.survey_wave_label,
                survey_year=survey_result.survey_year,
                survey_target=survey_result.expectation_mean,
                signal_value=signal.value,
                signal_method_name=signal.method_name,
                signal_anchor_year=signal.anchor_year,
                signal_base_year=signal.base_year,
                signal_months=point.signal_months,
            )
        )

    recalculated_result = evaluate_candidate_fit(
        candidate_spec,
        fit_points,
    )

    return CalibrationOutput(
        selected_candidate=candidate_spec,
        factor=recalculated_result.factor,
        const=recalculated_result.const,
        classification=recalculated_result.classification,
        core_rmse=recalculated_result.core_rmse,
        leave_one_out_rmse=recalculated_result.leave_one_out_rmse,
        fit_points=tuple(fit_points),
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.target_year != 2024:
        raise SystemExit("This calibration entrypoint is currently locked to target-year 2024.")
    artifact_path = Path(args.search_artifact)
    if not artifact_path.exists():
        raise SystemExit(f"Missing search artifact: {artifact_path}")

    result = run_calibration(search_artifact_path=artifact_path)
    if not result.classification.is_admissible:
        raise SystemExit("Selected production HPA calibration produced an inadmissible fit.")

    print("NMG HPA expectation production calibration")
    print(f"search-artifact: {artifact_path}")
    print(f"survey-target: {result.selected_candidate.survey_target_spec.name}")
    print(f"signal-method: {result.selected_candidate.signal_method_name}")
    print(f"category: {result.selected_candidate.category_key}")
    print(f"regression: {result.selected_candidate.regression_type}")
    print(f"anchor-policy: {result.selected_candidate.anchor_policy_name}")
    print(f"plausibility: {result.classification.label}")
    print(f"core-rmse: {format_float(result.core_rmse)}")
    print(f"leave-one-out-rmse: {format_float(result.leave_one_out_rmse)}")
    for point in result.fit_points:
        print(
            f"{point.survey_wave_label}: expectation={format_float(point.survey_target)} "
            f"ppd-anchor={point.signal_anchor_year} ppd-base={point.signal_base_year} "
            f"signal={format_float(point.signal_value)}"
        )
    print(f"HPA_EXPECTATION_FACTOR = {format_float(result.factor)}")
    print(f"HPA_EXPECTATION_CONST = {format_float(result.const)}")


__all__ = [
    "CalibrationOutput",
    "LOCKED_ANCHOR_POLICY",
    "LOCKED_CATEGORY_KEY",
    "LOCKED_REGRESSION_TYPE",
    "LOCKED_SIGNAL_METHOD",
    "LOCKED_SURVEY_TARGET",
    "build_arg_parser",
    "run_calibration",
]


if __name__ == "__main__":
    main()
