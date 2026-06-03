"""Script-level tests for WAS validation modules.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestWasValidationScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.modules = [
            ("scripts.python.validation.was.income_dist", "Income"),
            ("scripts.python.validation.was.housing_wealth_dist", "Housing wealth"),
            ("scripts.python.validation.was.financial_wealth_dist", "Financial wealth"),
        ]
        cls.base_income_annual = [2000.0, 5000.0, 9000.0]
        cls.base_housing_wealth = [120000.0, 250000.0, 400000.0]
        cls.base_liq_financial_wealth = [5000.0, 20000.0, 80000.0]

    def _column_map(self, dataset: str) -> dict[str, str]:
        if dataset == "R8":
            return {
                "weight": "R8xshhwgt",
                "gross_income": "DVTotGIRR8",
                "net_income": "DVTotInc_BHCR8",
                "gross_rent_income": "DVGrsRentAmtAnnualR8_aggr",
                "net_rent_income": "DVNetRentAmtAnnualR8_aggr",
                "total_property_wealth": "HPropWR8",
                "property_value_sum": "DVPropertyR8",
                "main_residence": "DVHValueR8",
                "other_houses": "DVHseValR8_sum",
                "btl_houses": "DVBltValR8_sum",
                "gross_financial_wealth": "HFINWR8_SUM",
                "net_financial_wealth": "HFINWNTR8_Sum",
                "national_savings": "DVFNSValR8_aggr",
                "child_trust_fund": "DVCACTvR8_aggr",
                "child_other_savings": "DVCASVVR8_aggr",
                "savings_accounts": "DVSaValR8_aggr",
                "cash_isa": "DVCISAVR8_aggr",
                "current_account_credit": "DVCaCrValR8_aggr",
                "formal_financial_assets": "DVFFAssetsR8_aggr",
            }
        if dataset == "W3":
            return {
                "weight": "w3xswgt",
                "gross_income": "DVTotGIRw3",
                "net_income": "DVTotNIRw3",
                "gross_rent_income": "DVGrsRentAmtAnnualw3_aggr",
                "net_rent_income": "DVNetRentAmtAnnualw3_aggr",
                "total_property_wealth": "HPROPWW3",
                "property_value_sum": "DVPropertyW3",
                "main_residence": "DVHValueW3",
                "other_houses": "DVHseValW3_sum",
                "btl_houses": "DVBltValW3_sum",
                "gross_financial_wealth": "HFINWW3_sum",
                "net_financial_wealth": "HFINWNTw3_sum",
                "national_savings": "DVFNSValW3_aggr",
                "child_trust_fund": "DVCACTvW3_aggr",
                "child_other_savings": "DVCASVVW3_aggr",
                "savings_accounts": "DVSaValW3_aggr",
                "cash_isa": "DVCISAVW3_aggr",
                "current_account_credit": "DVCaCrValW3_aggr",
                "formal_financial_assets": "DVFFAssetsW3_aggr",
            }
        raise ValueError(f"Unsupported dataset {dataset!r}")

    def _dataset_file(self, dataset: str) -> tuple[str, str]:
        if dataset == "R8":
            return ("private-datasets/was/was_round_8_hhold_eul_may_2025.privdata", "\t")
        if dataset == "W3":
            return ("private-datasets/was/was_wave_3_hhold_eul_final.dta", ",")
        raise ValueError(f"Unsupported dataset {dataset!r}")

    def _build_data_row(
        self,
        income_annual: float,
        housing_wealth: float,
        liq_financial_wealth: float,
    ) -> dict[str, float]:
        return {
            "weight": 1.0,
            "gross_income": income_annual,
            "net_income": 0.8 * income_annual,
            "gross_rent_income": 0.0,
            "net_rent_income": 0.0,
            "total_property_wealth": housing_wealth,
            "property_value_sum": housing_wealth,
            "main_residence": 0.7 * housing_wealth,
            "other_houses": 0.2 * housing_wealth,
            "btl_houses": 0.1 * housing_wealth,
            "gross_financial_wealth": 1.2 * liq_financial_wealth,
            "net_financial_wealth": liq_financial_wealth,
            "national_savings": 0.2 * liq_financial_wealth,
            "child_trust_fund": 0.05 * liq_financial_wealth,
            "child_other_savings": 0.05 * liq_financial_wealth,
            "savings_accounts": 0.3 * liq_financial_wealth,
            "cash_isa": 0.1 * liq_financial_wealth,
            "current_account_credit": 0.1 * liq_financial_wealth,
            "formal_financial_assets": 0.2 * liq_financial_wealth,
        }

    def _write_was_data_file(
        self,
        root: Path,
        dataset: str,
        rows: list[dict[str, float]],
    ) -> None:
        relative_path, delimiter = self._dataset_file(dataset)
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = self._column_map(dataset)
        header = list(columns.values())
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerow(header)
            for row in rows:
                writer.writerow([row[key] for key in columns])

    def _write_results_file(self, path: Path, values: list[float]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = "1000;" + ";".join(f"{value:.6f}" for value in values) + "\n"
        path.write_text(line, encoding="utf-8")

    def _create_fixture(
        self,
        root: Path,
        dataset: str,
        fixture_name: str,
        add_income_filtered: bool = False,
        add_housing_filtered: bool = False,
        add_financial_filtered: bool = False,
    ) -> str:
        rows = [
            self._build_data_row(income, housing, financial)
            for income, housing, financial in zip(
                self.base_income_annual,
                self.base_housing_wealth,
                self.base_liq_financial_wealth,
            )
        ]

        income_model = [value / 12.0 for value in self.base_income_annual]
        housing_model = list(self.base_housing_wealth)
        financial_model = list(self.base_liq_financial_wealth)

        if add_income_filtered:
            rows.append(self._build_data_row(500.0, 150000.0, 10000.0))
            rows.append(self._build_data_row(-500.0, 180000.0, 12000.0))
            income_model.extend([500.0 / 12.0, -500.0 / 12.0])

        if add_housing_filtered:
            rows.append(self._build_data_row(3000.0, 0.0, 5000.0))
            rows.append(self._build_data_row(3500.0, -1000.0, 7000.0))
            housing_model.extend([0.0, -1000.0])

        if add_financial_filtered:
            rows.append(self._build_data_row(3500.0, 180000.0, 0.0))
            rows.append(self._build_data_row(4000.0, 200000.0, -1000.0))
            financial_model.extend([0.0, -1000.0])

        self._write_was_data_file(root, dataset, rows)

        results_subdir = f"Results/{fixture_name}"
        results_dir = root / results_subdir
        self._write_results_file(results_dir / "MonthlyGrossEmploymentIncome-run1.csv", income_model)
        self._write_results_file(results_dir / "HousingWealth-run1.csv", housing_model)
        self._write_results_file(results_dir / "BankBalance-run1.csv", financial_model)
        return results_subdir

    def _run_validation_module(
        self,
        module_name: str,
        dataset: str,
        root: Path,
        results_subdir: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "WAS_DATASET": dataset,
                "WAS_DATA_ROOT": str(root),
                "WAS_RESULTS_ROOT": str(root),
                "WAS_RESULTS_RUN_SUBDIR": results_subdir,
                "WAS_VALIDATION_PLOTS": "0",
                "MPLBACKEND": "Agg",
            }
        )
        if extra_env is not None:
            env.update(extra_env)
        return subprocess.run(
            ["python3", "-m", module_name],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def _extract_total_diff(self, output: str, label: str) -> float:
        pattern = re.compile(rf"{re.escape(label)} total diff:\s*([-+0-9.eE]+)\s*%")
        match = pattern.search(output)
        if not match:
            self.fail(f"Could not find total diff line for {label!r} in output:\n{output}")
        return float(match.group(1))

    def _assert_zero_diff_run(
        self,
        module_name: str,
        label: str,
        dataset: str,
        root: Path,
        results_subdir: str,
    ) -> None:
        result = self._run_validation_module(module_name, dataset, root, results_subdir)
        combined = result.stdout + result.stderr
        self.assertEqual(
            result.returncode,
            0,
            msg=f"Module failed: {module_name}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn(f"{label} total diff:", combined)
        self.assertAlmostEqual(self._extract_total_diff(combined, label), 0.0, places=9)

    def test_r8_happy_path_all_validation_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(root, "R8", "r8-happy")
            for module_name, label in self.modules:
                self._assert_zero_diff_run(
                    module_name,
                    label,
                    "R8",
                    root,
                    results_subdir,
                )

    def test_w3_happy_path_all_validation_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(root, "W3", "w3-happy")
            for module_name, label in self.modules:
                self._assert_zero_diff_run(
                    module_name,
                    label,
                    "W3",
                    root,
                    results_subdir,
                )

    def test_income_filtering_ignores_below_minimum_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(
                root,
                "R8",
                "income-filtered",
                add_income_filtered=True,
            )
            self._assert_zero_diff_run(
                "scripts.python.validation.was.income_dist",
                "Income",
                "R8",
                root,
                results_subdir,
            )

    def test_housing_filtering_ignores_non_positive_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(
                root,
                "R8",
                "housing-filtered",
                add_housing_filtered=True,
            )
            self._assert_zero_diff_run(
                "scripts.python.validation.was.housing_wealth_dist",
                "Housing wealth",
                "R8",
                root,
                results_subdir,
            )

    def test_financial_filtering_ignores_non_positive_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(
                root,
                "R8",
                "financial-filtered",
                add_financial_filtered=True,
            )
            self._assert_zero_diff_run(
                "scripts.python.validation.was.financial_wealth_dist",
                "Financial wealth",
                "R8",
                root,
                results_subdir,
            )

    def test_missing_results_file_fails_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(root, "R8", "missing-housing")
            missing_file = root / results_subdir / "HousingWealth-run1.csv"
            missing_file.unlink()
            result = self._run_validation_module(
                "scripts.python.validation.was.housing_wealth_dist",
                "R8",
                root,
                results_subdir,
            )
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("HousingWealth-run1.csv", combined)

    def test_invalid_dataset_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results_subdir = self._create_fixture(root, "R8", "invalid-dataset")
            result = self._run_validation_module(
                "scripts.python.validation.was.income_dist",
                "BAD",
                root,
                results_subdir,
            )
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WAS_DATASET must be", combined)

    def test_housing_wealth_plot_exports_multiseed_average(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_was_data_file(
                root,
                "R8",
                [
                    self._build_data_row(3000.0, 120000.0, 5000.0),
                    self._build_data_row(3500.0, 250000.0, 20000.0),
                    self._build_data_row(4000.0, 400000.0, 80000.0),
                ],
            )
            results_root = root / "Results" / "multiseed"
            self._write_results_file(
                results_root / "seed-1" / "HousingWealth-run1.csv",
                [120000.0, 250000.0, 400000.0],
            )
            self._write_results_file(
                results_root / "seed-2" / "HousingWealth-run1.csv",
                [150000.0, 300000.0, 500000.0],
            )
            output_path = root / "plot.png"

            result = self._run_validation_module(
                "scripts.python.validation.was.housing_wealth_dist",
                "R8",
                root,
                "Results/multiseed/seed-1",
                extra_env={
                    "WAS_VALIDATION_PLOTS": "1",
                    "WAS_RESULTS_FILE_GLOB": str(
                        results_root / "seed-*" / "HousingWealth-run1.csv"
                    ),
                    "WAS_PLOT_OUTPUT_PATH": str(output_path),
                    "WAS_MODEL_LABEL": "2024 Model Output (10-seed average)",
                    "WAS_DATA_LABEL": "Validation data (WAS Round 8)",
                },
            )
            combined = result.stdout + result.stderr

            self.assertEqual(
                result.returncode,
                0,
                msg=f"Module failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertIn("Averaged 2 model result files", combined)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_income_plot_exports_v0_v5o3_multiseed_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_was_data_file(
                root,
                "R8",
                [
                    self._build_data_row(3000.0, 120000.0, 5000.0),
                    self._build_data_row(6000.0, 250000.0, 20000.0),
                    self._build_data_row(12000.0, 400000.0, 80000.0),
                ],
            )
            results_root = root / "Results" / "income-comparison"
            self._write_results_file(
                results_root
                / "v0"
                / "seed-1"
                / "MonthlyGrossEmploymentIncome-run1.csv",
                [250.0, 500.0, 1000.0],
            )
            self._write_results_file(
                results_root
                / "v0"
                / "seed-2"
                / "MonthlyGrossEmploymentIncome-run1.csv",
                [300.0, 550.0, 1100.0],
            )
            self._write_results_file(
                results_root
                / "v5o3"
                / "seed-1"
                / "MonthlyGrossEmploymentIncome-run1.csv",
                [350.0, 650.0, 1200.0],
            )
            self._write_results_file(
                results_root
                / "v5o3"
                / "seed-2"
                / "MonthlyGrossEmploymentIncome-run1.csv",
                [400.0, 700.0, 1300.0],
            )
            output_path = root / "income-comparison.png"

            result = self._run_validation_module(
                "scripts.python.validation.was.income_dist",
                "R8",
                root,
                "Results/income-comparison/v0/seed-1",
                extra_env={
                    "WAS_VALIDATION_PLOTS": "1",
                    "WAS_2011_RESULTS_FILE_GLOB": str(
                        results_root
                        / "v0"
                        / "seed-*"
                        / "MonthlyGrossEmploymentIncome-run1.csv"
                    ),
                    "WAS_2024_RESULTS_FILE_GLOB": str(
                        results_root
                        / "v5o3"
                        / "seed-*"
                        / "MonthlyGrossEmploymentIncome-run1.csv"
                    ),
                    "WAS_PLOT_OUTPUT_PATH": str(output_path),
                },
            )
            combined = result.stdout + result.stderr

            self.assertEqual(
                result.returncode,
                0,
                msg=f"Module failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertIn("Averaged 2 2011 model result files", combined)
            self.assertIn("Averaged 2 2024 model result files", combined)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
