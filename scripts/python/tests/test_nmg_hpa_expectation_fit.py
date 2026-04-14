from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.python.calibration.nmg.nmg_hpa_expectation_fit import (
    LOCKED_SIGNAL_METHOD,
    LOCKED_SURVEY_METHOD,
    PRODUCTION_YEARS,
    build_arg_parser,
    main,
    run_calibration,
)


class TestNmgHpaExpectationFit(unittest.TestCase):
    def _write_nmg_csv(self, expectation_mean: float) -> Path:
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

    def test_parser_accepts_modern_nmg_window_and_ppd_inputs(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "nmg-2018.csv",
                "nmg-2019.csv",
                "nmg-2020.csv",
                "nmg-2021.csv",
                "nmg-2022.csv",
                "nmg-2023.csv",
                "nmg-2024.csv",
                "--ppd",
                "pp-2011.csv",
                "pp-2012.csv",
                "pp-2018.csv",
                "pp-2019.csv",
                "pp-2020.csv",
                "pp-2021.csv",
                "pp-2022.csv",
                "pp-2023.csv",
                "pp-2024.csv",
            ]
        )

        self.assertEqual(args.target_year, 2024)
        self.assertEqual(LOCKED_SURVEY_METHOD, "midpoint_exact")
        self.assertEqual(PRODUCTION_YEARS, (2018, 2019, 2020, 2021, 2022, 2023, 2024))
        self.assertEqual(LOCKED_SIGNAL_METHOD, "annual_mean_annualised")

    def test_run_calibration_uses_category_a_filter(self) -> None:
        signal_values = {
            2018: 0.02,
            2019: 0.03,
            2020: 0.04,
            2021: 0.05,
            2022: 0.06,
            2023: 0.07,
            2024: 0.08,
        }
        category_a_prices = self._build_two_year_price_series(signal_values)
        category_b_prices = {
            2016: 400.0,
            2017: 400.0,
            2018: 196.0,
            2019: 169.0,
            2020: 121.0,
            2021: 100.0,
            2022: 81.0,
            2023: 64.0,
            2024: 49.0,
        }
        nmg_paths = {
            year: self._write_nmg_csv((0.2 * signal_values[year]) + 0.01)
            for year in PRODUCTION_YEARS
        }
        ppd_path = self._write_ppd_csv({"A": category_a_prices, "B": category_b_prices})
        try:
            result = run_calibration(
                nmg_paths=nmg_paths,
                ppd_paths=[ppd_path],
            )
        finally:
            for path in [*nmg_paths.values(), ppd_path]:
                path.unlink(missing_ok=True)

        self.assertIn(result.classification.label, {"preferred", "admissible"})
        self.assertEqual(sorted(result.survey_means), [2018, 2019, 2020, 2021, 2022, 2023, 2024])
        self.assertEqual(result.category_types, {"A"})
        self.assertEqual(result.survey_method_name, LOCKED_SURVEY_METHOD)
        self.assertEqual(result.signal_method_name, LOCKED_SIGNAL_METHOD)
        self.assertAlmostEqual(result.signal_values[2024], signal_values[2024], places=12)

    def test_main_fails_when_fit_is_inadmissible(self) -> None:
        signal_values = {
            2018: 0.02,
            2019: 0.03,
            2020: 0.04,
            2021: 0.05,
            2022: 0.06,
            2023: 0.07,
            2024: 0.08,
        }
        category_a_prices = self._build_two_year_price_series(signal_values)
        nmg_paths = {
            year: self._write_nmg_csv(0.025 - (0.1 * signal))
            for year, signal in signal_values.items()
        }
        ppd_path = self._write_ppd_csv({"A": category_a_prices})
        argv = [
            "nmg_hpa_expectation_fit.py",
            *(str(nmg_paths[year]) for year in PRODUCTION_YEARS),
            "--ppd",
            str(ppd_path),
        ]
        try:
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(SystemExit, "inadmissible"):
                    main()
        finally:
            for path in [*nmg_paths.values(), ppd_path]:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
