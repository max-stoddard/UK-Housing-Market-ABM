#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search legacy and production HPA-expectation method variants.

Latest findings (private datasets, 2026-04-16):
- Legacy mode now recovers the historical coefficients at printed config precision with an explicit legacy-only search surface.
- The recovered legacy method is `owner_occupier_cross_section + midpoint_exact_cap35 + rolling_quarter_cumulative + Category A + explicit legacy per-wave pairing`.
- On the current private datasets this yields `HPA_EXPECTATION_FACTOR = 0.4407356112` and `HPA_EXPECTATION_CONST = -0.0066328562`, which reproduce the historical `0.44 / -0.007` values at printed precision.
- The promoted 2024 production default is `national_cross_section + midpoint_exact + annual_mean_annualised + Category A + Huber + same_year_two_year_base`.
- On the current private datasets this yields `HPA_EXPECTATION_FACTOR = 0.2887897073` and `HPA_EXPECTATION_CONST = -0.0059593352`.
- Interpretation: the legacy recovery now depends on explicit per-wave pairing and survey-aligned rolling-quarter windows, while the production default remains the best defended 2024 national method.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.nmg.hpa_expectation import (
    DEFAULT_EXPECTATION_METHOD_NAMES,
    DEFAULT_PRODUCTION_EXPECTATION_METHOD_NAMES,
    HpaExpectationCandidateResult,
    HpaExpectationCandidateSpec,
    HpaExpectationFitPoint,
    LEGACY_TARGET_CONST,
    LEGACY_TARGET_FACTOR,
    LEGACY_CONST_PRINT_DECIMALS,
    LEGACY_FACTOR_PRINT_DECIMALS,
    NmgWaveData,
    ProductionSelection,
    SurveyTargetResult,
    SurveyTargetSpec,
    build_default_survey_target_specs,
    build_survey_target_result,
    evaluate_candidate_fit,
    load_nmg_wave_csv,
    matches_legacy_printed_precision,
    rank_legacy_candidates,
    select_production_candidate,
)
from scripts.python.helpers.nmg.linkage import (
    build_matched_panel_row_indices,
    load_pid_subsid_linkage,
)
from scripts.python.helpers.ppd.hpa_signal_methods import (
    HpaSignal,
    PpdSignalIndex,
    build_hpa_signal_from_index,
    build_ppd_signal_index,
    load_ppd_rows,
    resolve_base_year,
)

LEGACY_MODE = "legacy"
PRODUCTION_MODE = "production"
LEGACY_PRIMARY_FIT_WAVE_LABELS = ("2014", "2018")
LEGACY_DIAGNOSTIC_WAVE_LABELS = ("2015", "2016", "2017")
PRODUCTION_FIT_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
PRODUCTION_DIAGNOSTIC_WAVE_LABELS = ("2015", "2016", "2017", "2025-pt1", "2025-pt2")
DEFAULT_PRODUCTION_FIT_YEARS = ",".join(str(year) for year in PRODUCTION_FIT_YEARS)
LEGACY_WAVE_LABELS = ("2014", "2015", "2016", "2017", "2018")
LEGACY_EXISTING_SIGNAL_METHODS = (
    "java_like_annualised",
    "annual_mean_annualised",
    "annual_mean_cumulative",
)
LEGACY_ROLLING_QUARTER_SIGNAL_METHODS = (
    "rolling_quarter_annualised",
    "rolling_quarter_cumulative",
)
LEGACY_ROLLING_QUARTER_MONTH_CHOICES = tuple(
    tuple(range(start_month, start_month + 3))
    for start_month in range(1, 11)
)
DEFAULT_PRODUCTION_SIGNAL_METHODS = ("annual_mean_annualised",)
DEFAULT_PRODUCTION_CATEGORY_KEYS = ("A",)
DEFAULT_PRODUCTION_REGRESSION_TYPES = ("huber", "ols")
PRODUCTION_SIGNAL_METHODS = (
    "java_like_annualised",
    "annual_mean_annualised",
    "annual_mean_cumulative",
)
PRODUCTION_CATEGORY_KEYS = ("A", "all_transactions")
PRODUCTION_REGRESSION_TYPES = ("ols", "huber")
PRODUCTION_SIGNAL_CATEGORY_TYPES = {
    "A": {"A"},
    "all_transactions": None,
}
DEFAULT_LINKAGE_XLSX = Path("private-datasets/nmg/boe-nmg-household-survey-data.xlsx")
DEFAULT_PRODUCTION_ARTIFACT_OUTPUT = Path("tmp/nmg_hpa_expectation_production_search.json")
DEFAULT_LEGACY_ARTIFACT_OUTPUT = Path("tmp/nmg_hpa_expectation_legacy_search.json")


@dataclass(frozen=True)
class ExplicitSignalSpec:
    anchor_year: int
    base_year: int
    signal_months: tuple[int, ...] | None = None


@dataclass(frozen=True)
class SearchCandidateDefinition:
    candidate_spec: HpaExpectationCandidateSpec
    fit_wave_labels: tuple[str, ...]
    explicit_signal_specs_by_wave_label: dict[str, ExplicitSignalSpec] | None = None


@dataclass(frozen=True)
class MethodSearchOutput:
    mode: str
    nmg_input_paths: dict[str, Path]
    ppd_input_paths: tuple[Path, ...]
    linkage_xlsx_path: Path | None
    fit_wave_labels: tuple[str, ...]
    diagnostic_wave_labels: tuple[str, ...]
    survey_results: dict[str, dict[str, SurveyTargetResult]]
    ranked_results: list[HpaExpectationCandidateResult]
    selected_result: HpaExpectationCandidateResult
    baseline_result: HpaExpectationCandidateResult | None
    complexity_override_applied: bool
    complexity_override_reason: str | None
    gap_report: tuple[str, ...]
    panel_notes: tuple[str, ...]
    panel_row_indices_by_wave_label: dict[str, set[int]]
    signal_indexes: dict[str, PpdSignalIndex]
    exact_precision_matches: tuple[HpaExpectationCandidateResult, ...]


def _parse_wave_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"Expected wave argument in LABEL=PATH form: {value}")
    label, raw_path = value.split("=", 1)
    stripped_label = label.strip()
    stripped_path = raw_path.strip()
    if not stripped_label or not stripped_path:
        raise ValueError(f"Invalid wave argument: {value}")
    return stripped_label, Path(stripped_path)


def _parse_years(value: str) -> tuple[int, ...]:
    years = tuple(int(token.strip()) for token in value.split(",") if token.strip())
    if len(years) < 2:
        raise ValueError("At least two fit years are required.")
    return years


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search legacy and production HPA expectation methods.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    def add_common_arguments(target: argparse.ArgumentParser, *, default_artifact_output: Path) -> None:
        target.add_argument(
            "--nmg-wave",
            action="append",
            required=True,
            help="Wave/path mapping in LABEL=PATH form, e.g. 2015=private-datasets/nmg/nmg-2015.csv",
        )
        target.add_argument(
            "--ppd",
            action="append",
            required=True,
            help="Path to a PPD CSV. Repeat for multiple files.",
        )
        target.add_argument(
            "--artifact-output",
            default=str(default_artifact_output),
            help=f"JSON artifact output path (default: {default_artifact_output})",
        )
        target.add_argument(
            "--top-k",
            type=int,
            default=20,
            help="Top ranked methods to print (default: 20).",
        )

    legacy_parser = subparsers.add_parser(LEGACY_MODE, help="Search legacy-reconstruction hypotheses.")
    add_common_arguments(legacy_parser, default_artifact_output=DEFAULT_LEGACY_ARTIFACT_OUTPUT)
    legacy_parser.add_argument(
        "--legacy-target-factor",
        type=float,
        default=LEGACY_TARGET_FACTOR,
        help=f"Legacy target factor (default: {LEGACY_TARGET_FACTOR}).",
    )
    legacy_parser.add_argument(
        "--legacy-target-const",
        type=float,
        default=LEGACY_TARGET_CONST,
        help=f"Legacy target const (default: {LEGACY_TARGET_CONST}).",
    )

    production_parser = subparsers.add_parser(PRODUCTION_MODE, help="Search 2024 production-recalibration candidates.")
    add_common_arguments(production_parser, default_artifact_output=DEFAULT_PRODUCTION_ARTIFACT_OUTPUT)
    production_parser.add_argument(
        "--fit-years",
        default=DEFAULT_PRODUCTION_FIT_YEARS,
        help=f"Comma-separated production fit years (default: {DEFAULT_PRODUCTION_FIT_YEARS}).",
    )
    production_parser.add_argument(
        "--linkage-xlsx",
        default=str(DEFAULT_LINKAGE_XLSX),
        help=f"Optional PID/SUBSID linkage workbook (default: {DEFAULT_LINKAGE_XLSX}).",
    )
    production_parser.add_argument(
        "--skip-panel",
        action="store_true",
        help="Skip matched-panel candidates even if linkage data is available.",
    )
    production_parser.add_argument(
        "--include-production-sensitivity-surface",
        action="store_true",
        help="Include broader production sensitivity candidates beyond the defended default family.",
    )
    return parser


def survey_target_spec_to_dict(spec: SurveyTargetSpec) -> dict[str, object]:
    return {
        "name": spec.name,
        "expectation_method_name": spec.expectation_method_name,
        "family_name": spec.family_name,
        "housing_codes": sorted(spec.housing_codes) if spec.housing_codes is not None else None,
        "use_matched_panel": spec.use_matched_panel,
    }


def survey_target_spec_from_dict(data: dict[str, object]) -> SurveyTargetSpec:
    housing_codes_raw = data.get("housing_codes")
    housing_codes = None
    if housing_codes_raw is not None:
        housing_codes = frozenset(str(value) for value in housing_codes_raw)
    return SurveyTargetSpec(
        name=str(data["name"]),
        expectation_method_name=str(data["expectation_method_name"]),
        family_name=str(data["family_name"]),
        housing_codes=housing_codes,
        use_matched_panel=bool(data.get("use_matched_panel", False)),
    )


def candidate_spec_to_dict(spec: HpaExpectationCandidateSpec) -> dict[str, object]:
    return {
        "name": spec.name,
        "survey_target_spec": survey_target_spec_to_dict(spec.survey_target_spec),
        "signal_method_name": spec.signal_method_name,
        "category_key": spec.category_key,
        "regression_type": spec.regression_type,
        "anchor_policy_name": spec.anchor_policy_name,
        "hypothesis_name": spec.hypothesis_name,
    }


def candidate_spec_from_dict(data: dict[str, object]) -> HpaExpectationCandidateSpec:
    return HpaExpectationCandidateSpec(
        name=str(data["name"]),
        survey_target_spec=survey_target_spec_from_dict(dict(data["survey_target_spec"])),
        signal_method_name=str(data["signal_method_name"]),
        category_key=str(data["category_key"]),
        regression_type=str(data["regression_type"]),
        anchor_policy_name=str(data["anchor_policy_name"]),
        hypothesis_name=str(data["hypothesis_name"]) if data.get("hypothesis_name") is not None else None,
    )


def _result_to_dict(result: HpaExpectationCandidateResult) -> dict[str, object]:
    return {
        "candidate_spec": candidate_spec_to_dict(result.candidate_spec),
        "factor": result.factor,
        "const": result.const,
        "classification": {
            "label": result.classification.label,
            "is_admissible": result.classification.is_admissible,
            "is_preferred": result.classification.is_preferred,
        },
        "core_rmse": result.core_rmse,
        "leave_one_out_rmse": result.leave_one_out_rmse,
        "legacy_distance": result.legacy_distance,
        "fit_points": [
            {
                "survey_wave_label": point.survey_wave_label,
                "survey_year": point.survey_year,
                "survey_target": point.survey_target,
                "signal_value": point.signal_value,
                "signal_method_name": point.signal_method_name,
                "signal_anchor_year": point.signal_anchor_year,
                "signal_base_year": point.signal_base_year,
                "signal_months": list(point.signal_months) if point.signal_months is not None else None,
            }
            for point in result.fit_points
        ],
    }


def _format_status(result: HpaExpectationCandidateResult) -> str:
    if result.is_preferred:
        return "preferred"
    if result.is_admissible:
        return "admissible"
    return "inadmissible"


def _load_nmg_waves(nmg_wave_specs: dict[str, Path]) -> dict[str, NmgWaveData]:
    waves: dict[str, NmgWaveData] = {}
    for wave_label, path in sorted(
        nmg_wave_specs.items(),
        key=lambda item: (int("".join(char for char in item[0] if char.isdigit())[:4]), item[0]),
    ):
        if not path.exists():
            raise ValueError(f"Missing NMG CSV for wave {wave_label}: {path}")
        waves[wave_label] = load_nmg_wave_csv(path, wave_label=wave_label)
    return waves


def _build_signal_indexes(ppd_paths: Sequence[Path]) -> dict[str, PpdSignalIndex]:
    for path in ppd_paths:
        if not path.exists():
            raise ValueError(f"Missing PPD CSV: {path}")
    all_rows, _stats = load_ppd_rows(ppd_paths)
    return {
        category_key: build_ppd_signal_index(
            all_rows,
            category_key=category_key,
            category_types=category_types,
        )
        for category_key, category_types in PRODUCTION_SIGNAL_CATEGORY_TYPES.items()
    }


def _build_survey_results(
    *,
    waves: dict[str, NmgWaveData],
    survey_target_specs: Sequence[SurveyTargetSpec],
    panel_row_indices_by_wave_label: dict[str, set[int]] | None = None,
) -> dict[str, dict[str, SurveyTargetResult]]:
    survey_results: dict[str, dict[str, SurveyTargetResult]] = {}
    for spec in survey_target_specs:
        per_wave: dict[str, SurveyTargetResult] = {}
        for wave_label, wave in waves.items():
            try:
                per_wave[wave_label] = build_survey_target_result(
                    wave,
                    spec,
                    matched_row_indices=(
                        panel_row_indices_by_wave_label.get(wave_label)
                        if panel_row_indices_by_wave_label is not None
                        else None
                    ),
                )
            except ValueError:
                continue
        if per_wave:
            survey_results[spec.name] = per_wave
    return survey_results


def _resolve_anchor_year(
    *,
    survey_year: int,
    available_ppd_years: Iterable[int],
    anchor_policy_name: str,
    explicit_anchor_year: int | None = None,
) -> int:
    available_years = tuple(sorted(set(int(year) for year in available_ppd_years)))
    if not available_years:
        raise ValueError("No PPD years are available.")
    if anchor_policy_name == "same_year_two_year_base":
        if survey_year not in available_years:
            raise ValueError(f"No same-year PPD anchor is available for survey year {survey_year}.")
        return survey_year
    if anchor_policy_name == "literal_2014_2018_comment":
        if explicit_anchor_year is None:
            raise ValueError("literal_2014_2018_comment requires explicit anchor years.")
        return explicit_anchor_year
    if anchor_policy_name == "latest_prior_or_same":
        candidates = [year for year in available_years if year <= survey_year]
        if not candidates:
            raise ValueError(f"No latest-prior PPD anchor is available for survey year {survey_year}.")
        return candidates[-1]
    if anchor_policy_name == "nearest_future_or_same":
        candidates = [year for year in available_years if year >= survey_year]
        if not candidates:
            raise ValueError(f"No nearest-future PPD anchor is available for survey year {survey_year}.")
        return candidates[0]
    if anchor_policy_name == "nearest_available":
        return min(
            available_years,
            key=lambda year: (abs(year - survey_year), year > survey_year, year),
        )
    raise ValueError(f"Unsupported anchor policy: {anchor_policy_name}")


def _build_fit_points(
    *,
    candidate_definition: SearchCandidateDefinition,
    survey_results: dict[str, dict[str, SurveyTargetResult]],
    signal_indexes: dict[str, PpdSignalIndex],
) -> tuple[HpaExpectationFitPoint, ...]:
    survey_target_results = survey_results[candidate_definition.candidate_spec.survey_target_spec.name]
    signal_index = signal_indexes[candidate_definition.candidate_spec.category_key]
    fit_points: list[HpaExpectationFitPoint] = []
    for wave_label in candidate_definition.fit_wave_labels:
        survey_target_result = survey_target_results[wave_label]
        explicit_signal_spec = None
        if candidate_definition.explicit_signal_specs_by_wave_label is not None:
            explicit_signal_spec = candidate_definition.explicit_signal_specs_by_wave_label.get(wave_label)
        if explicit_signal_spec is not None:
            signal = build_hpa_signal_from_index(
                signal_index,
                anchor_year=explicit_signal_spec.anchor_year,
                base_year=explicit_signal_spec.base_year,
                method_name=candidate_definition.candidate_spec.signal_method_name,
                months=explicit_signal_spec.signal_months,
            )
        else:
            anchor_year = _resolve_anchor_year(
                survey_year=survey_target_result.survey_year,
                available_ppd_years=signal_index.available_years,
                anchor_policy_name=candidate_definition.candidate_spec.anchor_policy_name,
            )
            base_year = resolve_base_year(signal_index.available_years, anchor_year=anchor_year)
            signal = build_hpa_signal_from_index(
                signal_index,
                anchor_year=anchor_year,
                base_year=base_year,
                method_name=candidate_definition.candidate_spec.signal_method_name,
            )
        fit_points.append(
            HpaExpectationFitPoint(
                survey_wave_label=wave_label,
                survey_year=survey_target_result.survey_year,
                survey_target=survey_target_result.expectation_mean,
                signal_value=signal.value,
                signal_method_name=signal.method_name,
                signal_anchor_year=signal.anchor_year,
                signal_base_year=signal.base_year,
                signal_months=tuple(signal.diagnostics["months_used_recent"])
                if "months_used_recent" in signal.diagnostics
                else None,
            )
        )
    return tuple(fit_points)


def _iter_explicit_anchor_base_pairs(
    *,
    available_years: Sequence[int],
    max_anchor_year: int,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (int(anchor_year), int(base_year))
        for anchor_year in available_years
        for base_year in available_years
        if base_year < anchor_year and anchor_year <= max_anchor_year
    )


def _build_legacy_candidate_name(
    *,
    survey_target_spec: SurveyTargetSpec,
    signal_method_name: str,
    category_key: str,
    signal_specs_by_wave_label: dict[str, ExplicitSignalSpec],
) -> str:
    wave_tokens: list[str] = []
    for wave_label in LEGACY_PRIMARY_FIT_WAVE_LABELS:
        signal_spec = signal_specs_by_wave_label[wave_label]
        month_token = ""
        if signal_spec.signal_months is not None:
            month_token = "__m" + "-".join(str(month) for month in signal_spec.signal_months)
        wave_tokens.append(
            f"{wave_label}_a{signal_spec.anchor_year}_b{signal_spec.base_year}{month_token}"
        )
    return (
        f"legacy_explicit_pair__{survey_target_spec.name}__{signal_method_name}__{category_key}"
        f"__{'__'.join(wave_tokens)}__ols"
    )


def _build_legacy_candidate_definitions(
    survey_target_specs: Sequence[SurveyTargetSpec],
    *,
    signal_indexes: dict[str, PpdSignalIndex],
    signal_method_names: Sequence[str],
) -> list[SearchCandidateDefinition]:
    definitions: list[SearchCandidateDefinition] = []
    for survey_target_spec in survey_target_specs:
        for signal_method_name in signal_method_names:
            month_choices: tuple[tuple[int, ...] | None, ...]
            if signal_method_name in LEGACY_ROLLING_QUARTER_SIGNAL_METHODS:
                month_choices = tuple(LEGACY_ROLLING_QUARTER_MONTH_CHOICES)
            else:
                month_choices = (None,)
            for category_key in PRODUCTION_CATEGORY_KEYS:
                available_years = signal_indexes[category_key].available_years
                pairs_2014 = _iter_explicit_anchor_base_pairs(
                    available_years=available_years,
                    max_anchor_year=2014,
                )
                pairs_2018 = _iter_explicit_anchor_base_pairs(
                    available_years=available_years,
                    max_anchor_year=2018,
                )
                for anchor14, base14 in pairs_2014:
                    for anchor18, base18 in pairs_2018:
                        for months_2014 in month_choices:
                            for months_2018 in month_choices:
                                signal_specs_by_wave_label = {
                                    "2014": ExplicitSignalSpec(
                                        anchor_year=anchor14,
                                        base_year=base14,
                                        signal_months=months_2014,
                                    ),
                                    "2018": ExplicitSignalSpec(
                                        anchor_year=anchor18,
                                        base_year=base18,
                                        signal_months=months_2018,
                                    ),
                                }
                                anchor_policy_name = (
                                    "explicit_rolling_quarter_pair"
                                    if signal_method_name in LEGACY_ROLLING_QUARTER_SIGNAL_METHODS
                                    else "explicit_pair"
                                )
                                candidate_spec = HpaExpectationCandidateSpec(
                                    name=_build_legacy_candidate_name(
                                        survey_target_spec=survey_target_spec,
                                        signal_method_name=signal_method_name,
                                        category_key=category_key,
                                        signal_specs_by_wave_label=signal_specs_by_wave_label,
                                    ),
                                    survey_target_spec=survey_target_spec,
                                    signal_method_name=signal_method_name,
                                    category_key=category_key,
                                    regression_type="ols",
                                    anchor_policy_name=anchor_policy_name,
                                    hypothesis_name=anchor_policy_name,
                                )
                                definitions.append(
                                    SearchCandidateDefinition(
                                        candidate_spec=candidate_spec,
                                        fit_wave_labels=LEGACY_PRIMARY_FIT_WAVE_LABELS,
                                        explicit_signal_specs_by_wave_label=signal_specs_by_wave_label,
                                    )
                                )
    return definitions


def _build_production_candidate_definitions(
    survey_target_specs: Sequence[SurveyTargetSpec],
    *,
    fit_wave_labels: tuple[str, ...],
    signal_method_names: Sequence[str],
    category_keys: Sequence[str],
    regression_types: Sequence[str],
) -> list[SearchCandidateDefinition]:
    definitions: list[SearchCandidateDefinition] = []
    for survey_target_spec in survey_target_specs:
        for signal_method_name in signal_method_names:
            for category_key in category_keys:
                for regression_type in regression_types:
                    candidate_spec = HpaExpectationCandidateSpec(
                        name=(
                            f"{survey_target_spec.name}__{signal_method_name}__{category_key}"
                            f"__{regression_type}__same_year_two_year_base"
                        ),
                        survey_target_spec=survey_target_spec,
                        signal_method_name=signal_method_name,
                        category_key=category_key,
                        regression_type=regression_type,
                        anchor_policy_name="same_year_two_year_base",
                    )
                    definitions.append(
                        SearchCandidateDefinition(
                            candidate_spec=candidate_spec,
                            fit_wave_labels=fit_wave_labels,
                        )
                    )
    return definitions


def _evaluate_candidate_definitions(
    *,
    candidate_definitions: Sequence[SearchCandidateDefinition],
    survey_results: dict[str, dict[str, SurveyTargetResult]],
    signal_indexes: dict[str, PpdSignalIndex],
    legacy_target: tuple[float, float] | None = None,
) -> list[HpaExpectationCandidateResult]:
    evaluation_results: list[HpaExpectationCandidateResult] = []
    for candidate_definition in candidate_definitions:
        if not all(
            wave_label in survey_results.get(candidate_definition.candidate_spec.survey_target_spec.name, {})
            for wave_label in candidate_definition.fit_wave_labels
        ):
            continue
        try:
            fit_points = _build_fit_points(
                candidate_definition=candidate_definition,
                survey_results=survey_results,
                signal_indexes=signal_indexes,
            )
        except ValueError:
            continue
        try:
            evaluation_results.append(
                evaluate_candidate_fit(
                    candidate_definition.candidate_spec,
                    fit_points,
                    legacy_target=legacy_target,
                )
            )
        except ValueError:
            continue
    return evaluation_results


def _collect_exact_precision_matches(
    results: Sequence[HpaExpectationCandidateResult],
) -> tuple[HpaExpectationCandidateResult, ...]:
    return tuple(
        result
        for result in results
        if matches_legacy_printed_precision(result.factor, result.const)
    )


def _nearest_fit_point_for_diagnostic_wave(
    *,
    diagnostic_wave_label: str,
    fit_points: Sequence[HpaExpectationFitPoint],
) -> HpaExpectationFitPoint:
    diagnostic_year = int("".join(char for char in diagnostic_wave_label if char.isdigit())[:4])
    return min(
        fit_points,
        key=lambda point: (
            abs(point.survey_year - diagnostic_year),
            point.survey_year > diagnostic_year,
            point.survey_year,
        ),
    )


def _build_legacy_diagnostic_rmse_map(
    *,
    exact_precision_matches: Sequence[HpaExpectationCandidateResult],
    diagnostic_wave_labels: Sequence[str],
    survey_results: dict[str, dict[str, SurveyTargetResult]],
    signal_indexes: dict[str, PpdSignalIndex],
) -> dict[str, float]:
    diagnostic_rmse_by_candidate_name: dict[str, float] = {}
    for result in exact_precision_matches:
        selected_spec = result.candidate_spec.survey_target_spec
        signal_index = signal_indexes[result.candidate_spec.category_key]
        squared_errors: list[float] = []
        for wave_label in diagnostic_wave_labels:
            survey_result = survey_results.get(selected_spec.name, {}).get(wave_label)
            if survey_result is None:
                continue
            source_fit_point = _nearest_fit_point_for_diagnostic_wave(
                diagnostic_wave_label=wave_label,
                fit_points=result.fit_points,
            )
            try:
                signal = build_hpa_signal_from_index(
                    signal_index,
                    anchor_year=source_fit_point.signal_anchor_year,
                    base_year=source_fit_point.signal_base_year,
                    method_name=result.signal_method_name,
                    months=source_fit_point.signal_months,
                )
            except ValueError:
                continue
            predicted = (result.factor * signal.value) + result.const
            squared_errors.append((predicted - survey_result.expectation_mean) ** 2)
        diagnostic_rmse_by_candidate_name[result.candidate_spec.name] = (
            (sum(squared_errors) / len(squared_errors)) ** 0.5
            if squared_errors
            else float("inf")
        )
    return diagnostic_rmse_by_candidate_name


def _build_legacy_gap_report(
    *,
    ranked_results: Sequence[HpaExpectationCandidateResult],
    signal_indexes: dict[str, PpdSignalIndex],
    exact_precision_matches: Sequence[HpaExpectationCandidateResult],
    used_extended_signal_surface: bool,
) -> tuple[str, ...]:
    report: list[str] = []
    available_ppd_years = set(signal_indexes["all_transactions"].available_years)
    missing_pre_2018_years = [year for year in range(2013, 2018) if year not in available_ppd_years]
    if missing_pre_2018_years:
        report.append(
            "Repo-local PPD slices are missing pre-2018 anchor years: "
            + ", ".join(str(year) for year in missing_pre_2018_years)
            + "."
        )
    if exact_precision_matches:
        report.append(
            f"Recovered the historical 0.44 / -0.007 coefficients at printed precision with "
            f"{len(exact_precision_matches)} explicit legacy candidate(s)."
        )
        if used_extended_signal_surface:
            report.append(
                "Recovery required the legacy rolling-quarter search surface after the existing annual signal family "
                "produced no printed-precision match."
            )
        return tuple(report)
    best_result = ranked_results[0]
    if best_result.legacy_distance is not None and best_result.legacy_distance > 0.10:
        report.append(
            "No repo-local candidate recovered the historical 0.44 / -0.007 point closely; the gap likely reflects "
            "missing Land Registry vintages and/or an unrecorded historical transform or anchor rule."
        )
    return tuple(report)


def run_method_search(
    *,
    mode: str,
    nmg_wave_paths: dict[str, Path],
    ppd_paths: list[Path],
    linkage_xlsx_path: Path | None = None,
    fit_years: tuple[int, ...] = PRODUCTION_FIT_YEARS,
    legacy_target: tuple[float, float] = (LEGACY_TARGET_FACTOR, LEGACY_TARGET_CONST),
    include_production_sensitivity_surface: bool = False,
) -> MethodSearchOutput:
    if mode not in {LEGACY_MODE, PRODUCTION_MODE}:
        raise ValueError(f"Unsupported mode: {mode}")

    waves = _load_nmg_waves(nmg_wave_paths)
    signal_indexes = _build_signal_indexes(ppd_paths)
    ranked_results: list[HpaExpectationCandidateResult]
    selected_result: HpaExpectationCandidateResult
    baseline_result = None
    complexity_override_applied = False
    complexity_override_reason = None
    gap_report: tuple[str, ...] = ()
    panel_notes: list[str] = []
    panel_row_indices_by_wave_label: dict[str, set[int]] = {}
    exact_precision_matches: tuple[HpaExpectationCandidateResult, ...] = ()

    if mode == LEGACY_MODE:
        fit_wave_labels = tuple(
            wave_label for wave_label in LEGACY_PRIMARY_FIT_WAVE_LABELS if wave_label in waves
        )
        if fit_wave_labels != LEGACY_PRIMARY_FIT_WAVE_LABELS:
            raise ValueError("Legacy mode requires both the 2014 and 2018 NMG waves.")
        diagnostic_wave_labels = tuple(
            wave_label for wave_label in LEGACY_DIAGNOSTIC_WAVE_LABELS if wave_label in waves
        )
        if DEFAULT_LINKAGE_XLSX.exists() and DEFAULT_LINKAGE_XLSX.is_file():
            try:
                linkage = load_pid_subsid_linkage(DEFAULT_LINKAGE_XLSX)
                panel_row_indices_by_wave_label = build_matched_panel_row_indices(
                    {wave_label: waves[wave_label] for wave_label in fit_wave_labels},
                    required_wave_labels=fit_wave_labels,
                    linkage=linkage,
                )
            except ValueError as exc:
                panel_notes.append(str(exc))
        else:
            panel_notes.append(f"Legacy linkage workbook not available: {DEFAULT_LINKAGE_XLSX}")

        survey_target_specs = build_default_survey_target_specs(
            include_owner_occupier=True,
            include_matched_panel=bool(panel_row_indices_by_wave_label),
        )
        survey_results = _build_survey_results(
            waves=waves,
            survey_target_specs=survey_target_specs,
            panel_row_indices_by_wave_label=panel_row_indices_by_wave_label,
        )
        candidate_definitions = _build_legacy_candidate_definitions(
            survey_target_specs,
            signal_indexes=signal_indexes,
            signal_method_names=LEGACY_EXISTING_SIGNAL_METHODS,
        )
        evaluation_results = _evaluate_candidate_definitions(
            candidate_definitions=candidate_definitions,
            survey_results=survey_results,
            signal_indexes=signal_indexes,
            legacy_target=legacy_target,
        )
        ranked_results = rank_legacy_candidates(evaluation_results)
        exact_precision_matches = _collect_exact_precision_matches(ranked_results)
        used_extended_signal_surface = False
        if not exact_precision_matches:
            used_extended_signal_surface = True
            rolling_candidate_definitions = _build_legacy_candidate_definitions(
                survey_target_specs,
                signal_indexes=signal_indexes,
                signal_method_names=LEGACY_ROLLING_QUARTER_SIGNAL_METHODS,
            )
            candidate_definitions = [*candidate_definitions, *rolling_candidate_definitions]
            evaluation_results = [
                *evaluation_results,
                *_evaluate_candidate_definitions(
                    candidate_definitions=rolling_candidate_definitions,
                    survey_results=survey_results,
                    signal_indexes=signal_indexes,
                    legacy_target=legacy_target,
                ),
            ]
            ranked_results = rank_legacy_candidates(evaluation_results)
            exact_precision_matches = _collect_exact_precision_matches(ranked_results)
        if len(exact_precision_matches) > 1:
            diagnostic_rmse_by_candidate_name = _build_legacy_diagnostic_rmse_map(
                exact_precision_matches=exact_precision_matches,
                diagnostic_wave_labels=diagnostic_wave_labels,
                survey_results=survey_results,
                signal_indexes=signal_indexes,
            )
            ranked_results = rank_legacy_candidates(
                evaluation_results,
                diagnostic_rmse_by_candidate_name=diagnostic_rmse_by_candidate_name,
            )
            exact_precision_matches = _collect_exact_precision_matches(ranked_results)
        if not ranked_results:
            raise ValueError("Legacy mode did not produce any valid candidate fits.")
        selected_result = ranked_results[0]
        gap_report = _build_legacy_gap_report(
            ranked_results=ranked_results,
            signal_indexes=signal_indexes,
            exact_precision_matches=exact_precision_matches,
            used_extended_signal_surface=used_extended_signal_surface,
        )
    else:
        fit_wave_labels = tuple(str(year) for year in fit_years)
        diagnostic_wave_labels = tuple(
            wave_label for wave_label in PRODUCTION_DIAGNOSTIC_WAVE_LABELS if wave_label in waves
        )
        for wave_label in fit_wave_labels:
            if wave_label not in waves:
                raise ValueError(f"Missing required production fit wave {wave_label}.")
        if linkage_xlsx_path is not None and linkage_xlsx_path.exists():
            if linkage_xlsx_path.is_file():
                try:
                    linkage = load_pid_subsid_linkage(linkage_xlsx_path)
                    panel_row_indices_by_wave_label = build_matched_panel_row_indices(
                        waves,
                        required_wave_labels=fit_wave_labels,
                        linkage=linkage,
                    )
                except ValueError as exc:
                    panel_notes.append(str(exc))
            else:
                panel_notes.append(f"Linkage path is not a file: {linkage_xlsx_path}")
        else:
            panel_notes.append(f"Linkage workbook not available: {linkage_xlsx_path}")

        if include_production_sensitivity_surface:
            survey_target_specs = build_default_survey_target_specs(
                include_owner_occupier=True,
                include_matched_panel=bool(panel_row_indices_by_wave_label),
            )
            signal_method_names = PRODUCTION_SIGNAL_METHODS
            category_keys = PRODUCTION_CATEGORY_KEYS
            regression_types = PRODUCTION_REGRESSION_TYPES
        else:
            survey_target_specs = build_default_survey_target_specs(
                expectation_method_names=DEFAULT_PRODUCTION_EXPECTATION_METHOD_NAMES,
                include_owner_occupier=False,
                include_matched_panel=False,
            )
            signal_method_names = DEFAULT_PRODUCTION_SIGNAL_METHODS
            category_keys = DEFAULT_PRODUCTION_CATEGORY_KEYS
            regression_types = DEFAULT_PRODUCTION_REGRESSION_TYPES
        survey_results = _build_survey_results(
            waves=waves,
            survey_target_specs=survey_target_specs,
            panel_row_indices_by_wave_label=panel_row_indices_by_wave_label,
        )
        candidate_definitions = _build_production_candidate_definitions(
            survey_target_specs=survey_target_specs,
            fit_wave_labels=fit_wave_labels,
            signal_method_names=signal_method_names,
            category_keys=category_keys,
            regression_types=regression_types,
        )
        evaluation_results = []
        for candidate_definition in candidate_definitions:
            if not all(
                wave_label in survey_results.get(candidate_definition.candidate_spec.survey_target_spec.name, {})
                for wave_label in candidate_definition.fit_wave_labels
            ):
                continue
            try:
                fit_points = _build_fit_points(
                    candidate_definition=candidate_definition,
                    survey_results=survey_results,
                    signal_indexes=signal_indexes,
                )
            except ValueError:
                continue
            try:
                evaluation_results.append(
                    evaluate_candidate_fit(
                        candidate_definition.candidate_spec,
                        fit_points,
                    )
                )
            except ValueError:
                continue
        selection = select_production_candidate(evaluation_results)
        ranked_results = list(selection.ranked_results)
        selected_result = selection.selected_result
        baseline_result = selection.baseline_result
        complexity_override_applied = selection.complexity_override_applied
        complexity_override_reason = selection.complexity_override_reason

    return MethodSearchOutput(
        mode=mode,
        nmg_input_paths={wave_label: wave.input_path for wave_label, wave in waves.items()},
        ppd_input_paths=tuple(ppd_paths),
        linkage_xlsx_path=linkage_xlsx_path,
        fit_wave_labels=fit_wave_labels,
        diagnostic_wave_labels=diagnostic_wave_labels,
        survey_results=survey_results,
        ranked_results=ranked_results,
        selected_result=selected_result,
        baseline_result=baseline_result,
        complexity_override_applied=complexity_override_applied,
        complexity_override_reason=complexity_override_reason,
        gap_report=gap_report,
        panel_notes=tuple(panel_notes),
        panel_row_indices_by_wave_label=panel_row_indices_by_wave_label,
        signal_indexes=signal_indexes,
        exact_precision_matches=exact_precision_matches,
    )


def _build_diagnostic_points(
    output: MethodSearchOutput,
) -> list[tuple[str, float | None, HpaSignal | None]]:
    selected_spec = output.selected_result.candidate_spec.survey_target_spec
    signal_index = output.signal_indexes[output.selected_result.candidate_spec.category_key]
    diagnostics: list[tuple[str, float | None, HpaSignal | None]] = []
    for wave_label in output.diagnostic_wave_labels:
        survey_result = output.survey_results.get(selected_spec.name, {}).get(wave_label)
        if survey_result is None:
            diagnostics.append((wave_label, None, None))
            continue
        try:
            if output.mode == LEGACY_MODE:
                source_fit_point = _nearest_fit_point_for_diagnostic_wave(
                    diagnostic_wave_label=wave_label,
                    fit_points=output.selected_result.fit_points,
                )
                signal = build_hpa_signal_from_index(
                    signal_index,
                    anchor_year=source_fit_point.signal_anchor_year,
                    base_year=source_fit_point.signal_base_year,
                    method_name=output.selected_result.candidate_spec.signal_method_name,
                    months=source_fit_point.signal_months,
                )
            else:
                anchor_year = _resolve_anchor_year(
                    survey_year=survey_result.survey_year,
                    available_ppd_years=signal_index.available_years,
                    anchor_policy_name=output.selected_result.candidate_spec.anchor_policy_name,
                )
                signal = build_hpa_signal_from_index(
                    signal_index,
                    anchor_year=anchor_year,
                    base_year=resolve_base_year(signal_index.available_years, anchor_year=anchor_year),
                    method_name=output.selected_result.candidate_spec.signal_method_name,
                )
        except ValueError:
            diagnostics.append((wave_label, survey_result.expectation_mean, None))
            continue
        diagnostics.append((wave_label, survey_result.expectation_mean, signal))
    return diagnostics


def _format_months(months: Sequence[int] | None) -> str:
    if not months:
        return "year"
    month_names = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }
    if len(months) == 3 and all((later - earlier) == 1 for earlier, later in zip(months, months[1:])):
        return f"{month_names[months[0]]}-{month_names[months[-1]]}"
    return ",".join(month_names[month] for month in months)


def _legacy_summary_line(result: HpaExpectationCandidateResult) -> str:
    fit_points_by_wave = {point.survey_wave_label: point for point in result.fit_points}
    point_2014 = fit_points_by_wave["2014"]
    point_2018 = fit_points_by_wave["2018"]
    return (
        f"{result.candidate_spec.survey_target_spec.family_name} with "
        f"{result.candidate_spec.survey_target_spec.expectation_method_name} and {result.category_key} "
        f"{result.signal_method_name} uses { _format_months(point_2014.signal_months) } "
        f"{point_2014.signal_anchor_year} over {point_2014.signal_base_year} for 2014 and "
        f"{ _format_months(point_2018.signal_months) } {point_2018.signal_anchor_year} over "
        f"{point_2018.signal_base_year} for 2018, reproducing 0.44 / -0.007 at printed precision."
    )


def _write_artifact(output: MethodSearchOutput, artifact_output_path: Path) -> None:
    artifact_output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": output.mode,
        "nmg_input_paths": {wave_label: str(path) for wave_label, path in output.nmg_input_paths.items()},
        "ppd_input_paths": [str(path) for path in output.ppd_input_paths],
        "linkage_xlsx_path": str(output.linkage_xlsx_path) if output.linkage_xlsx_path is not None else None,
        "fit_wave_labels": list(output.fit_wave_labels),
        "diagnostic_wave_labels": list(output.diagnostic_wave_labels),
        "selected_result": _result_to_dict(output.selected_result),
        "baseline_result": _result_to_dict(output.baseline_result) if output.baseline_result is not None else None,
        "complexity_override_applied": output.complexity_override_applied,
        "complexity_override_reason": output.complexity_override_reason,
        "gap_report": list(output.gap_report),
        "panel_notes": list(output.panel_notes),
        "exact_precision_matches": [_result_to_dict(result) for result in output.exact_precision_matches],
        "ranked_results": [_result_to_dict(result) for result in output.ranked_results],
    }
    artifact_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _print_ranked_results(results: Sequence[HpaExpectationCandidateResult], *, top_k: int, mode: str) -> None:
    if mode == LEGACY_MODE:
        print("Rank\tDistance\tLOO_RMSE\tStatus\tExact\tHypothesis\tSurveyTarget\tSignal\tCategory\tFactor\tConst")
        for rank, result in enumerate(results[:top_k], start=1):
            print(
                f"{rank}\t{format_float(result.legacy_distance or 0.0)}\t"
                f"{format_float(result.leave_one_out_rmse)}\t{_format_status(result)}\t"
                f"{'yes' if matches_legacy_printed_precision(result.factor, result.const) else 'no'}\t"
                f"{result.candidate_spec.hypothesis_name}\t{result.candidate_spec.survey_target_spec.name}\t"
                f"{result.signal_method_name}\t{result.category_key}\t"
                f"{format_float(result.factor)}\t{format_float(result.const)}"
            )
    else:
        print("Rank\tCore_RMSE\tLOO_RMSE\tStatus\tSurveyTarget\tSignal\tCategory\tRegression\tFactor\tConst")
        for rank, result in enumerate(results[:top_k], start=1):
            print(
                f"{rank}\t{format_float(result.core_rmse)}\t{format_float(result.leave_one_out_rmse)}\t"
                f"{_format_status(result)}\t{result.candidate_spec.survey_target_spec.name}\t"
                f"{result.signal_method_name}\t{result.category_key}\t{result.regression_type}\t"
                f"{format_float(result.factor)}\t{format_float(result.const)}"
            )


def _print_output(output: MethodSearchOutput, *, top_k: int, artifact_output_path: Path) -> None:
    print("NMG HPA expectation method search")
    print(f"mode = {output.mode}")
    print("NMG inputs = " + ", ".join(f"{wave}:{path}" for wave, path in output.nmg_input_paths.items()))
    print("PPD inputs = " + ", ".join(str(path) for path in output.ppd_input_paths))
    if output.linkage_xlsx_path is not None:
        print(f"linkage-xlsx = {output.linkage_xlsx_path}")
    print(f"fit-waves = {', '.join(output.fit_wave_labels)}")
    if output.diagnostic_wave_labels:
        print(f"diagnostic-waves = {', '.join(output.diagnostic_wave_labels)}")
    print(f"artifact-output = {artifact_output_path}")
    if output.panel_notes:
        print("")
        print("Panel notes")
        for note in output.panel_notes:
            print(f"- {note}")
    if output.mode == LEGACY_MODE and output.exact_precision_matches:
        print("")
        print("Exact printed-precision matches")
        for result in output.exact_precision_matches:
            points_by_wave = {point.survey_wave_label: point for point in result.fit_points}
            print(
                f"- {result.candidate_spec.survey_target_spec.name} | {result.signal_method_name} | "
                f"{result.category_key} | 2014 anchor/base={points_by_wave['2014'].signal_anchor_year}/"
                f"{points_by_wave['2014'].signal_base_year} months={_format_months(points_by_wave['2014'].signal_months)} | "
                f"2018 anchor/base={points_by_wave['2018'].signal_anchor_year}/"
                f"{points_by_wave['2018'].signal_base_year} months={_format_months(points_by_wave['2018'].signal_months)} | "
                f"factor={format_float(result.factor)} | const={format_float(result.const)}"
            )
    print("")
    _print_ranked_results(output.ranked_results, top_k=top_k, mode=output.mode)

    print("")
    print("Selected candidate")
    selected = output.selected_result
    print(f"name: {selected.candidate_spec.name}")
    if selected.candidate_spec.hypothesis_name is not None:
        print(f"hypothesis: {selected.candidate_spec.hypothesis_name}")
    print(f"survey-target: {selected.candidate_spec.survey_target_spec.name}")
    print(f"signal-method: {selected.signal_method_name}")
    print(f"category: {selected.category_key}")
    print(f"regression: {selected.regression_type}")
    print(f"anchor-policy: {selected.candidate_spec.anchor_policy_name}")
    print(f"plausibility: {_format_status(selected)}")
    print(f"core-rmse: {format_float(selected.core_rmse)}")
    print(f"leave-one-out-rmse: {format_float(selected.leave_one_out_rmse)}")
    if selected.legacy_distance is not None:
        print(f"legacy-distance: {format_float(selected.legacy_distance)}")
    print(f"factor: {format_float(selected.factor)}")
    print(f"const: {format_float(selected.const)}")
    if output.mode == LEGACY_MODE:
        print(
            "legacy-printed-match: "
            + (
                f"{selected.factor:.{LEGACY_FACTOR_PRINT_DECIMALS}f} / "
                f"{selected.const:.{LEGACY_CONST_PRINT_DECIMALS}f}"
                if matches_legacy_printed_precision(selected.factor, selected.const)
                else "no"
            )
        )
    print("")
    print("Fit-point diagnostics")
    for point in selected.fit_points:
        month_note = _format_months(point.signal_months)
        print(
            f"{point.survey_wave_label}: expectation={format_float(point.survey_target)} "
            f"signal={format_float(point.signal_value)} anchor={point.signal_anchor_year} "
            f"base={point.signal_base_year} months={month_note}"
        )

    if output.mode == PRODUCTION_MODE:
        if output.baseline_result is not None:
            print("")
            print("Complexity baseline")
            print(f"name: {output.baseline_result.candidate_spec.name}")
            print(f"core-rmse: {format_float(output.baseline_result.core_rmse)}")
            print(f"leave-one-out-rmse: {format_float(output.baseline_result.leave_one_out_rmse)}")
        if output.complexity_override_reason:
            print(f"complexity-rule: {output.complexity_override_reason}")
        diagnostic_points = _build_diagnostic_points(output)
        if diagnostic_points:
            print("")
            print("Diagnostic-only waves")
            for wave_label, expectation, signal in diagnostic_points:
                if expectation is None:
                    print(f"{wave_label}: expectation=unavailable signal=unavailable")
                    continue
                if signal is None:
                    print(f"{wave_label}: expectation={format_float(expectation)} signal=unavailable")
                    continue
                predicted = (selected.factor * signal.value) + selected.const
                month_note = _format_months(
                    tuple(signal.diagnostics["months_used_recent"])
                    if "months_used_recent" in signal.diagnostics
                    else None
                )
                print(
                    f"{wave_label}: expectation={format_float(expectation)} signal={format_float(signal.value)} "
                    f"predicted={format_float(predicted)} anchor={signal.anchor_year} base={signal.base_year} "
                    f"months={month_note}"
                )
    else:
        diagnostic_points = _build_diagnostic_points(output)
        if diagnostic_points:
            print("")
            print("Diagnostic-only waves")
            for wave_label, expectation, signal in diagnostic_points:
                if expectation is None:
                    print(f"{wave_label}: expectation=unavailable signal=unavailable")
                    continue
                if signal is None:
                    print(f"{wave_label}: expectation={format_float(expectation)} signal=unavailable")
                    continue
                predicted = (selected.factor * signal.value) + selected.const
                month_note = _format_months(
                    tuple(signal.diagnostics["months_used_recent"])
                    if "months_used_recent" in signal.diagnostics
                    else None
                )
                print(
                    f"{wave_label}: expectation={format_float(expectation)} signal={format_float(signal.value)} "
                    f"predicted={format_float(predicted)} anchor={signal.anchor_year} base={signal.base_year} "
                    f"months={month_note}"
                )
        if output.gap_report:
            print("")
            print("Gap report")
            for line in output.gap_report:
                print(f"- {line}")
        if output.exact_precision_matches:
            print("")
            print("Summary")
            print(_legacy_summary_line(selected))


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.top_k <= 0:
        raise SystemExit("top-k must be positive.")

    try:
        nmg_wave_paths = dict(_parse_wave_arg(value) for value in args.nmg_wave)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    ppd_paths = [Path(path) for path in args.ppd]
    artifact_output_path = Path(args.artifact_output)

    if args.mode == LEGACY_MODE:
        output = run_method_search(
            mode=LEGACY_MODE,
            nmg_wave_paths=nmg_wave_paths,
            ppd_paths=ppd_paths,
            legacy_target=(args.legacy_target_factor, args.legacy_target_const),
        )
    else:
        output = run_method_search(
            mode=PRODUCTION_MODE,
            nmg_wave_paths=nmg_wave_paths,
            ppd_paths=ppd_paths,
            linkage_xlsx_path=None if args.skip_panel else Path(args.linkage_xlsx),
            fit_years=_parse_years(args.fit_years),
            include_production_sensitivity_surface=args.include_production_sensitivity_surface,
        )

    _write_artifact(output, artifact_output_path)
    _print_output(output, top_k=args.top_k, artifact_output_path=artifact_output_path)


__all__ = [
    "DEFAULT_EXPECTATION_METHOD_NAMES",
    "DEFAULT_LINKAGE_XLSX",
    "DEFAULT_PRODUCTION_ARTIFACT_OUTPUT",
    "LEGACY_MODE",
    "LEGACY_TARGET_CONST",
    "LEGACY_TARGET_FACTOR",
    "PRODUCTION_FIT_YEARS",
    "PRODUCTION_MODE",
    "SearchCandidateDefinition",
    "MethodSearchOutput",
    "build_arg_parser",
    "candidate_spec_from_dict",
    "candidate_spec_to_dict",
    "run_method_search",
]


if __name__ == "__main__":
    main()
