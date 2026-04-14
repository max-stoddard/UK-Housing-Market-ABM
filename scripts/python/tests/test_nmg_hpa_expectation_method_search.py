from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.nmg.nmg_hpa_expectation_method_search import (
    CandidateEvaluation,
    DIAGNOSTIC_YEARS,
    PRODUCTION_FIT_YEARS,
    RMSE_TIE_TOLERANCE,
    build_arg_parser,
    rank_results,
    run_method_search,
)


class TestNmgHpaExpectationMethodSearch(unittest.TestCase):
    def _write_nmg_csv(self, boe39_code: int) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            suffix=".csv",
            delete=False,
            newline="",
            encoding="utf-8",
        )
        with handle:
            writer = csv.writer(handle)
            writer.writerow(["we_factor", "boe39"])
            writer.writerow([1.0, boe39_code])
        return Path(handle.name)

    def _write_nmg_csv_for_expectation(self, expectation_mean: float) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            suffix=".csv",
            delete=False,
            newline="",
            encoding="utf-8",
        )
        share_code_6 = expectation_mean / 0.04
        with handle:
            writer = csv.writer(handle)
            writer.writerow(["we_factor", "boe39"])
            writer.writerow([1.0 - share_code_6, 5])
            writer.writerow([share_code_6, 6])
        return Path(handle.name)

    def _build_two_year_price_series(
        self,
        yearly_signals: dict[int, float],
        *,
        base_2016: float = 100.0,
        base_2017: float = 100.0,
    ) -> dict[int, float]:
        prices = {2016: base_2016, 2017: base_2017}
        for year in sorted(yearly_signals):
            prices[year] = prices[year - 2] * ((1.0 + yearly_signals[year]) ** 2)
        return prices

    def _write_ppd_csv(self, category_price_series: dict[str, dict[int, float]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            suffix=".csv",
            delete=False,
            newline="",
            encoding="utf-8",
        )
        with handle:
            writer = csv.writer(handle)
            for category_type, yearly_prices in category_price_series.items():
                for year, price in sorted(yearly_prices.items()):
                    for month in (10, 11, 12):
                        writer.writerow(
                            [
                                f"{{{category_type}-{year}-{month}}}",
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
                                category_type,
                                "A",
                            ]
                        )
        return Path(handle.name)

    def _build_search_fixture(self) -> tuple[dict[int, Path], Path]:
        category_a_signals = {
            2018: 0.02,
            2019: 0.03,
            2020: 0.04,
            2021: 0.05,
            2022: 0.06,
            2023: 0.07,
            2024: 0.08,
        }
        category_a_prices = self._build_two_year_price_series(category_a_signals)
        category_b_prices = {
            2016: 100.0,
            2017: 100.0,
            2018: 400.0,
            2019: 400.0,
            2020: 100.0,
            2021: 100.0,
            2022: 25.0,
            2023: 25.0,
            2024: 9.0,
        }
        nmg_paths = {
            2014: self._write_nmg_csv_for_expectation(0.018),
            2016: self._write_nmg_csv_for_expectation(0.016),
            **{
                year: self._write_nmg_csv_for_expectation((0.2 * signal) + 0.01)
                for year, signal in category_a_signals.items()
            },
        }
        ppd_path = self._write_ppd_csv(
            {
                "A": category_a_prices,
                "B": category_b_prices,
            }
        )
        return nmg_paths, ppd_path

    def _cleanup_fixture(self, nmg_paths: dict[int, Path], ppd_path: Path) -> None:
        for path in [*nmg_paths.values(), ppd_path]:
            path.unlink(missing_ok=True)

    def test_parser_defaults_use_modern_fit_window(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "nmg-2014.csv",
                "nmg-2016.csv",
                "nmg-2018.csv",
                "nmg-2019.csv",
                "nmg-2020.csv",
                "nmg-2021.csv",
                "nmg-2022.csv",
                "nmg-2023.csv",
                "nmg-2024.csv",
                "pp-2018.csv",
                "pp-2019.csv",
                "pp-2020.csv",
                "pp-2021.csv",
                "pp-2022.csv",
                "pp-2023.csv",
                "pp-2024.csv",
            ]
        )

        self.assertEqual(args.fit_years, "2018,2019,2020,2021,2022,2023,2024")
        self.assertEqual(PRODUCTION_FIT_YEARS, (2018, 2019, 2020, 2021, 2022, 2023, 2024))

    def test_ranking_prefers_preferred_band_before_lower_rmse_outside_band(self) -> None:
        preferred = CandidateEvaluation(
            survey_method_name="midpoint_rounded",
            signal_method_name="java_like_annualised",
            factor=0.44,
            const=-0.007,
            is_admissible=True,
            is_preferred=True,
            rmse=0.012,
            survey_simplicity_rank=0,
            signal_simplicity_rank=0,
        )
        admissible_only = CandidateEvaluation(
            survey_method_name="midpoint_exact",
            signal_method_name="annual_mean_annualised",
            factor=1.0,
            const=0.02,
            is_admissible=True,
            is_preferred=False,
            rmse=0.011,
            survey_simplicity_rank=1,
            signal_simplicity_rank=1,
        )

        ranked = rank_results([admissible_only, preferred])

        self.assertTrue(ranked[0].is_preferred)

    def test_ranking_uses_simplicity_only_when_rmse_is_effectively_tied(self) -> None:
        simpler = CandidateEvaluation(
            survey_method_name="midpoint_rounded",
            signal_method_name="java_like_annualised",
            factor=0.44,
            const=-0.007,
            is_admissible=True,
            is_preferred=True,
            rmse=0.0100000,
            survey_simplicity_rank=0,
            signal_simplicity_rank=0,
        )
        less_simple = CandidateEvaluation(
            survey_method_name="midpoint_exact",
            signal_method_name="annual_mean_annualised",
            factor=0.44,
            const=-0.007,
            is_admissible=True,
            is_preferred=True,
            rmse=0.0100004,
            survey_simplicity_rank=1,
            signal_simplicity_rank=1,
        )

        self.assertLess(abs(less_simple.rmse - simpler.rmse), RMSE_TIE_TOLERANCE)

        ranked = rank_results([less_simple, simpler])

        self.assertEqual(ranked[0].survey_method_name, simpler.survey_method_name)
        self.assertEqual(ranked[0].signal_method_name, simpler.signal_method_name)

    def test_method_search_uses_category_a_filter_for_ranked_production_candidates(self) -> None:
        nmg_paths, ppd_path = self._build_search_fixture()
        try:
            output = run_method_search(
                nmg_paths=nmg_paths,
                ppd_paths=[ppd_path],
                fit_years=PRODUCTION_FIT_YEARS,
            )
        finally:
            self._cleanup_fixture(nmg_paths, ppd_path)

        self.assertEqual(output.production_category_types, {"A"})
        self.assertEqual(output.production_signal_method_name, "annual_mean_annualised")
        self.assertEqual({result.signal_method_name for result in output.ranked_results}, {"annual_mean_annualised"})

    def test_method_search_reports_all_transactions_comparison_as_diagnostic_only(self) -> None:
        nmg_paths, ppd_path = self._build_search_fixture()
        try:
            output = run_method_search(
                nmg_paths=nmg_paths,
                ppd_paths=[ppd_path],
                fit_years=PRODUCTION_FIT_YEARS,
            )
        finally:
            self._cleanup_fixture(nmg_paths, ppd_path)

        self.assertIn("all_transactions", output.comparison_results)
        self.assertEqual(output.comparison_results["all_transactions"].signal_method_name, "annual_mean_annualised")
        self.assertFalse(output.comparison_results["all_transactions"].is_admissible)

    def test_method_search_reports_strict_2020_to_2024_sensitivity(self) -> None:
        nmg_paths, ppd_path = self._build_search_fixture()
        try:
            output = run_method_search(
                nmg_paths=nmg_paths,
                ppd_paths=[ppd_path],
                fit_years=PRODUCTION_FIT_YEARS,
            )
        finally:
            self._cleanup_fixture(nmg_paths, ppd_path)

        self.assertEqual(output.strict_window_years, (2020, 2021, 2022, 2023, 2024))
        self.assertEqual({result.signal_method_name for result in output.strict_window_results}, {"annual_mean_annualised"})

    def test_run_method_search_reports_unavailable_diagnostic_years_without_failing(self) -> None:
        nmg_paths = {
            2014: self._write_nmg_csv(6),
            2016: self._write_nmg_csv(6),
            2018: self._write_nmg_csv(6),
            2019: self._write_nmg_csv(6),
            2020: self._write_nmg_csv(6),
            2021: self._write_nmg_csv(6),
            2022: self._write_nmg_csv(6),
            2023: self._write_nmg_csv(6),
            2024: self._write_nmg_csv(6),
        }
        ppd_path = self._write_ppd_csv(
            {
                "A": {
                    2016: 100.0,
                    2017: 100.0,
                    2018: 121.0,
                    2019: 121.0,
                    2020: 144.0,
                    2021: 144.0,
                    2022: 169.0,
                    2023: 169.0,
                    2024: 196.0,
                }
            }
        )
        try:
            output = run_method_search(
                nmg_paths=nmg_paths,
                ppd_paths=[ppd_path],
                fit_years=PRODUCTION_FIT_YEARS,
            )
        finally:
            for path in [*nmg_paths.values(), ppd_path]:
                path.unlink(missing_ok=True)

        self.assertEqual(output.unavailable_diagnostic_years, set(DIAGNOSTIC_YEARS))
        self.assertTrue(output.ranked_results)


if __name__ == "__main__":
    unittest.main()
