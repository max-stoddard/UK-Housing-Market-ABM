#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the v4.1 results mean summary command.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import statistics
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestModelSpeedResultsSummary(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.command_path = cls.repo_root / "scripts" / "model" / "print-v41-simulation-means.sh"

    def _run_summary(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.command_path), *args],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_output_file(self, run_dir: Path, sale_prices: list[float], *, include_sale_column: bool = True) -> None:
        header = ["Model time"]
        if include_sale_column:
            header.append("Sale AvSalePrice")
        header.append("Unused")
        with (run_dir / "Output-run1.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(header)
            for index, sale_price in enumerate(sale_prices):
                row = [index]
                if include_sale_column:
                    row.append(f"{sale_price:.6f}")
                row.append("0")
                writer.writerow(row)

    def _write_core_file(self, run_dir: Path, file_name: str, values: list[float]) -> None:
        rendered = "; ".join(f"{value:.6f}" for value in values) + "\n"
        (run_dir / file_name).write_text(rendered, encoding="utf-8")

    def _write_run_dir(
        self,
        run_dir: Path,
        *,
        sale_prices: list[float],
        housing_transactions: list[float],
        mortgage_approvals: list[float],
        debt_to_income: list[float],
        include_sale_column: bool = True,
    ) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        self._write_output_file(run_dir, sale_prices, include_sale_column=include_sale_column)
        self._write_core_file(run_dir, "coreIndicator-housingTransactions.csv", housing_transactions)
        self._write_core_file(run_dir, "coreIndicator-mortgageApprovals.csv", mortgage_approvals)
        self._write_core_file(run_dir, "coreIndicator-debtToIncome.csv", debt_to_income)

    def _parse_summary_stdout(self, stdout: str) -> tuple[list[str], dict[str, float]]:
        lines = [line.strip() for line in stdout.strip().splitlines() if line.strip()]
        values: dict[str, float] = {}
        for line in lines[2:]:
            label, raw_value = line.rsplit(": ", 1)
            values[label] = float(raw_value)
        return lines, values

    def test_results_summary_uses_post_200_window_and_expected_output_order(self) -> None:
        base_values = [float(index) for index in range(2001)]
        price_values = [value * 1000.0 for value in base_values]
        housing_values = [value * 2000.0 for value in base_values]
        mortgage_values = [value * 3000.0 for value in base_values]
        debt_values = [value * 4.0 for value in base_values]

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self._write_run_dir(
                run_dir,
                sale_prices=price_values,
                housing_transactions=housing_values,
                mortgage_approvals=mortgage_values,
                debt_to_income=debt_values,
            )

            result = self._run_summary("--run-dir", str(run_dir))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        lines, values = self._parse_summary_stdout(result.stdout)
        self.assertEqual(lines[0], f"Run directory: {run_dir.resolve()}")
        self.assertEqual(lines[1], "Window: indices 200:2000 (periods 200..1999 inclusive, 1800 values)")
        self.assertEqual(
            [line.rsplit(": ", 1)[0] for line in lines[2:]],
            [
                "Average house prices (£1,000)",
                "Housing transactions (1,000)",
                "Mortgage approvals (1,000)",
                "Mortgage debt-to-income ratio (%)",
            ],
        )

        self.assertAlmostEqual(
            values["Average house prices (£1,000)"],
            statistics.mean(value / 1000.0 for value in price_values[200:2000]),
            places=6,
        )
        self.assertAlmostEqual(
            values["Housing transactions (1,000)"],
            statistics.mean(value / 1000.0 for value in housing_values[200:2000]),
            places=6,
        )
        self.assertAlmostEqual(
            values["Mortgage approvals (1,000)"],
            statistics.mean(value / 1000.0 for value in mortgage_values[200:2000]),
            places=6,
        )
        self.assertAlmostEqual(
            values["Mortgage debt-to-income ratio (%)"],
            statistics.mean(debt_values[200:2000]),
            places=6,
        )

    def test_results_summary_ignores_appended_output_columns(self) -> None:
        base_values = [float(index) for index in range(2001)]
        housing_values = [value * 2000.0 for value in base_values]
        mortgage_values = [value * 3000.0 for value in base_values]
        debt_values = [value * 4.0 for value in base_values]
        extra_values = [value * 5.0 for value in base_values]

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            with (run_dir / "Output-run1.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Model time", "Sale AvSalePrice", "NetHousingWealth", "Unused"])
                for index, (sale_price, extra_value) in enumerate(zip(base_values, extra_values)):
                    writer.writerow([index, f"{sale_price:.6f}", f"{extra_value:.6f}", "0"])
            self._write_core_file(run_dir, "coreIndicator-housingTransactions.csv", housing_values)
            self._write_core_file(run_dir, "coreIndicator-mortgageApprovals.csv", mortgage_values)
            self._write_core_file(run_dir, "coreIndicator-debtToIncome.csv", debt_values)

            result = self._run_summary("--run-dir", str(run_dir))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        _, values = self._parse_summary_stdout(result.stdout)
        self.assertAlmostEqual(
            values["Average house prices (£1,000)"],
            statistics.mean(value / 1000.0 for value in base_values[200:2000]),
            places=6,
        )

    def test_results_summary_fails_when_sale_price_column_is_missing(self) -> None:
        values = [float(index) for index in range(2001)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self._write_run_dir(
                run_dir,
                sale_prices=values,
                housing_transactions=values,
                mortgage_approvals=values,
                debt_to_income=values,
                include_sale_column=False,
            )

            result = self._run_summary("--run-dir", str(run_dir))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required output column 'Sale AvSalePrice'", result.stderr)

    def test_results_summary_fails_when_a_required_file_is_missing(self) -> None:
        values = [float(index) for index in range(2001)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self._write_output_file(run_dir, values)
            self._write_core_file(run_dir, "coreIndicator-mortgageApprovals.csv", values)
            self._write_core_file(run_dir, "coreIndicator-debtToIncome.csv", values)

            result = self._run_summary("--run-dir", str(run_dir))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required file:", result.stderr)
        self.assertIn("coreIndicator-housingTransactions.csv", result.stderr)

    def test_results_summary_fails_when_window_does_not_yield_1800_values(self) -> None:
        long_values = [float(index) for index in range(2001)]
        short_values = [float(index) for index in range(1999)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self._write_run_dir(
                run_dir,
                sale_prices=long_values,
                housing_transactions=long_values,
                mortgage_approvals=short_values,
                debt_to_income=long_values,
            )

            result = self._run_summary("--run-dir", str(run_dir))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Mortgage approvals (1,000): expected 1800 values", result.stderr)

    def test_results_summary_default_command_matches_current_v41_output(self) -> None:
        expected_run_dir = (self.repo_root / "Results" / "v4.1-output").resolve()
        if not expected_run_dir.is_dir():
            self.skipTest(f"tracked benchmark fixture missing: {expected_run_dir}")

        result = self._run_summary()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        lines, values = self._parse_summary_stdout(result.stdout)
        self.assertEqual(lines[0], f"Run directory: {expected_run_dir}")
        self.assertEqual(lines[1], "Window: indices 200:2000 (periods 200..1999 inclusive, 1800 values)")
        self.assertAlmostEqual(values["Average house prices (£1,000)"], 269.873268, places=6)
        self.assertAlmostEqual(values["Housing transactions (1,000)"], 93.888863, places=6)
        self.assertAlmostEqual(values["Mortgage approvals (1,000)"], 50.936898, places=6)
        self.assertAlmostEqual(values["Mortgage debt-to-income ratio (%)"], 138.782999, places=6)


if __name__ == "__main__":
    unittest.main()
