from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.python.calibration.nmg.nmg_hpa_expectation_fit import (
    DEFAULT_PAIRING_RULE_NAME,
    DEFAULT_SIGNAL_METHOD_NAME,
    DEFAULT_SURVEY_METHOD_NAME,
    build_arg_parser,
    run_calibration,
)


class TestNmgHpaExpectationFit(unittest.TestCase):
    def _write_nmg_csv(self, rows: list[list[object]]) -> Path:
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
            writer.writerows(rows)
        return Path(handle.name)

    def _write_ppd_csv(self, rows: list[list[object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            suffix=".csv",
            delete=False,
            newline="",
            encoding="utf-8",
        )
        with handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
        return Path(handle.name)

    def test_parser_defaults_to_locked_method_family(self) -> None:
        args = build_arg_parser().parse_args(
            ["nmg-2014.csv", "nmg-2024.csv", "pp-2011.csv", "pp-2012.csv", "pp-2022.csv", "pp-2024.csv"]
        )

        self.assertEqual(args.target_year, 2024)
        self.assertEqual(DEFAULT_PAIRING_RULE_NAME, "previous_available")
        self.assertEqual(DEFAULT_SURVEY_METHOD_NAME, "midpoint_rounded")
        self.assertEqual(DEFAULT_SIGNAL_METHOD_NAME, "annual_mean_annualised")

    def test_run_calibration_uses_locked_methods_with_synthetic_inputs(self) -> None:
        nmg_2014 = self._write_nmg_csv([[1.0, 6]])
        nmg_2024 = self._write_nmg_csv([[1.0, 5]])
        ppd_2011 = self._write_ppd_csv(
            [["{A}", "100", "2011-01-15 00:00", "AA1 1AA", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"]]
        )
        ppd_2012 = self._write_ppd_csv(
            [["{B}", "121", "2012-01-15 00:00", "AA1 1AB", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"]]
        )
        ppd_2022 = self._write_ppd_csv(
            [["{C}", "100", "2022-01-15 00:00", "AA1 1AC", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"]]
        )
        ppd_2024 = self._write_ppd_csv(
            [["{D}", "121", "2024-01-15 00:00", "AA1 1AD", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"]]
        )
        try:
            result = run_calibration(
                nmg_paths={2014: nmg_2014, 2024: nmg_2024},
                ppd_paths=[ppd_2011, ppd_2012, ppd_2022, ppd_2024],
            )
        finally:
            for path in (nmg_2014, nmg_2024, ppd_2011, ppd_2012, ppd_2022, ppd_2024):
                path.unlink(missing_ok=True)

        self.assertAlmostEqual(result.factor, 0.36363636363636365, places=12)
        self.assertAlmostEqual(result.const, -0.03636363636363637, places=12)
        self.assertEqual(result.pairing_rule_name, "previous_available")
        self.assertEqual(result.survey_method_name, "midpoint_rounded")
        self.assertEqual(result.signal_method_name, "annual_mean_annualised")


if __name__ == "__main__":
    unittest.main()
