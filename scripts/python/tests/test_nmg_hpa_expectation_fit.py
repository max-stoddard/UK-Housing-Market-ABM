from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.python.calibration.nmg.nmg_hpa_expectation_fit import (
    LOCKED_ANCHOR_POLICY,
    LOCKED_CATEGORY_KEY,
    LOCKED_REGRESSION_TYPE,
    LOCKED_SIGNAL_METHOD,
    LOCKED_SURVEY_TARGET,
    build_arg_parser,
    main,
    run_calibration,
)
from scripts.python.experiments.nmg.nmg_hpa_expectation_method_search import (
    PRODUCTION_MODE,
    candidate_spec_to_dict,
)
from scripts.python.helpers.nmg.hpa_expectation import HpaExpectationCandidateSpec, SurveyTargetSpec


class TestNmgHpaExpectationFit(unittest.TestCase):
    def _write_nmg_csv(self, filename: str, expectation_mean: float) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / filename
        share_code_6 = max(min((expectation_mean + 0.035) / 0.07, 1.0), 0.0)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["we_factor", "boe39", "dhousing"])
            writer.writeheader()
            writer.writerow({"we_factor": f"{1.0 - share_code_6}", "boe39": "4", "dhousing": "1"})
            writer.writerow({"we_factor": f"{share_code_6}", "boe39": "6", "dhousing": "2"})
        return path

    def _build_production_price_series(
        self,
        yearly_signals: dict[int, float],
        *,
        base_2012: float = 100.0,
    ) -> dict[int, float]:
        prices = {2011: 90.0, 2012: base_2012}
        prices[2018] = base_2012 * ((1.0 + yearly_signals[2018]) ** 6)
        prices[2019] = prices[2018] * (1.0 + yearly_signals[2019])
        prices[2020] = prices[2018] * ((1.0 + yearly_signals[2020]) ** 2)
        prices[2021] = prices[2019] * ((1.0 + yearly_signals[2021]) ** 2)
        prices[2022] = prices[2020] * ((1.0 + yearly_signals[2022]) ** 2)
        prices[2023] = prices[2021] * ((1.0 + yearly_signals[2023]) ** 2)
        prices[2024] = prices[2022] * ((1.0 + yearly_signals[2024]) ** 2)
        return prices

    def _write_ppd_csv(self, filename: str, yearly_prices: dict[int, float]) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            for year, price in sorted(yearly_prices.items()):
                for month in (10, 11, 12):
                    writer.writerow(
                        [
                            f"{{A-{year}-{month}}}",
                            f"{price}",
                            f"{year}-{month:02d}-15 00:00",
                            "AA1 1AA",
                            "T",
                            "N",
                            "F",
                            "1",
                            "",
                            "STREET",
                            "",
                            "TOWN",
                            "DIST",
                            "COUNTY",
                            "A",
                            "A",
                        ]
                    )
        return path

    def _write_production_artifact(
        self,
        *,
        artifact_path: Path,
        nmg_paths: dict[str, Path],
        ppd_paths: list[Path],
        candidate_spec: HpaExpectationCandidateSpec,
        fit_wave_labels: list[str],
    ) -> None:
        payload = {
            "mode": PRODUCTION_MODE,
            "nmg_input_paths": {wave_label: str(path) for wave_label, path in nmg_paths.items()},
            "ppd_input_paths": [str(path) for path in ppd_paths],
            "linkage_xlsx_path": None,
            "fit_wave_labels": fit_wave_labels,
            "diagnostic_wave_labels": [],
            "selected_result": {
                "candidate_spec": candidate_spec_to_dict(candidate_spec),
                "factor": 0.0,
                "const": 0.0,
                "classification": {
                    "label": "admissible",
                    "is_admissible": True,
                    "is_preferred": False,
                },
                "core_rmse": 0.0,
                "leave_one_out_rmse": 0.0,
                "legacy_distance": None,
                "fit_points": [
                    {
                        "survey_wave_label": wave_label,
                        "survey_year": int(wave_label),
                        "survey_target": 0.0,
                        "signal_value": 0.0,
                        "signal_method_name": candidate_spec.signal_method_name,
                        "signal_anchor_year": int(wave_label),
                        "signal_base_year": (
                            2012
                            if wave_label == "2018"
                            else 2018
                            if wave_label == "2019"
                            else int(wave_label) - 2
                        ),
                    }
                    for wave_label in fit_wave_labels
                ],
            },
            "baseline_result": None,
            "complexity_override_applied": False,
            "complexity_override_reason": None,
            "gap_report": [],
            "panel_notes": [],
            "ranked_results": [],
        }
        artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _cleanup_paths(self, *paths: Path) -> None:
        for path in paths:
            if path.is_file():
                path.unlink(missing_ok=True)
            if path.parent.is_dir():
                try:
                    path.parent.rmdir()
                except OSError:
                    pass

    def test_parser_accepts_search_artifact(self) -> None:
        args = build_arg_parser().parse_args(["tmp/production-search.json"])

        self.assertEqual(args.search_artifact, "tmp/production-search.json")
        self.assertEqual(args.target_year, 2024)

    def test_run_calibration_recomputes_coefficients_from_locked_artifact(self) -> None:
        target_factor = 0.2887897073
        target_const = -0.0059593352
        signal_values = {
            2018: 0.02,
            2019: 0.03,
            2020: 0.04,
            2021: 0.05,
            2022: 0.06,
            2023: 0.07,
            2024: 0.08,
        }
        nmg_paths = {
            str(year): self._write_nmg_csv(f"nmg-{year}.csv", (target_factor * signal) + target_const)
            for year, signal in signal_values.items()
        }
        yearly_prices = self._build_production_price_series(signal_values)
        ppd_paths = [
            self._write_ppd_csv("pp-2011.csv", {2011: yearly_prices[2011]}),
            self._write_ppd_csv("pp.2012.csv", {2012: yearly_prices[2012]}),
            *(self._write_ppd_csv(f"pp-{year}.csv", {year: yearly_prices[year]}) for year in range(2018, 2025)),
        ]
        artifact_handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        artifact_handle.close()
        candidate_spec = HpaExpectationCandidateSpec(
            name="national_cross_section__midpoint_exact__annual_mean_annualised__A__huber__same_year_two_year_base",
            survey_target_spec=SurveyTargetSpec(
                name=LOCKED_SURVEY_TARGET,
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name=LOCKED_SIGNAL_METHOD,
            category_key=LOCKED_CATEGORY_KEY,
            regression_type=LOCKED_REGRESSION_TYPE,
            anchor_policy_name=LOCKED_ANCHOR_POLICY,
        )
        self._write_production_artifact(
            artifact_path=Path(artifact_handle.name),
            nmg_paths=nmg_paths,
            ppd_paths=ppd_paths,
            candidate_spec=candidate_spec,
            fit_wave_labels=[str(year) for year in range(2018, 2025)],
        )
        try:
            result = run_calibration(search_artifact_path=Path(artifact_handle.name))
        finally:
            self._cleanup_paths(*nmg_paths.values(), *ppd_paths, Path(artifact_handle.name))

        self.assertEqual(result.selected_candidate.signal_method_name, "annual_mean_annualised")
        self.assertTrue(result.classification.is_admissible)
        self.assertAlmostEqual(result.factor, target_factor, places=10)
        self.assertAlmostEqual(result.const, target_const, places=10)

    def test_main_fails_when_recomputed_fit_is_inadmissible(self) -> None:
        signal_values = {
            2018: 0.02,
            2019: 0.03,
            2020: 0.04,
            2021: 0.05,
            2022: 0.06,
            2023: 0.07,
            2024: 0.08,
        }
        nmg_paths = {
            str(year): self._write_nmg_csv(f"nmg-{year}.csv", 0.025 - (0.1 * signal))
            for year, signal in signal_values.items()
        }
        yearly_prices = self._build_production_price_series(signal_values)
        ppd_paths = [
            self._write_ppd_csv("pp-2011.csv", {2011: yearly_prices[2011]}),
            self._write_ppd_csv("pp.2012.csv", {2012: yearly_prices[2012]}),
            *(self._write_ppd_csv(f"pp-{year}.csv", {year: yearly_prices[year]}) for year in range(2018, 2025)),
        ]
        artifact_handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        artifact_handle.close()
        candidate_spec = HpaExpectationCandidateSpec(
            name="national_cross_section__midpoint_exact__annual_mean_annualised__A__huber__same_year_two_year_base",
            survey_target_spec=SurveyTargetSpec(
                name=LOCKED_SURVEY_TARGET,
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name=LOCKED_SIGNAL_METHOD,
            category_key=LOCKED_CATEGORY_KEY,
            regression_type=LOCKED_REGRESSION_TYPE,
            anchor_policy_name=LOCKED_ANCHOR_POLICY,
        )
        self._write_production_artifact(
            artifact_path=Path(artifact_handle.name),
            nmg_paths=nmg_paths,
            ppd_paths=ppd_paths,
            candidate_spec=candidate_spec,
            fit_wave_labels=[str(year) for year in range(2018, 2025)],
        )
        argv = ["nmg_hpa_expectation_fit.py", artifact_handle.name]
        try:
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(SystemExit, "inadmissible"):
                    main()
        finally:
            self._cleanup_paths(*nmg_paths.values(), *ppd_paths, Path(artifact_handle.name))


if __name__ == "__main__":
    unittest.main()
