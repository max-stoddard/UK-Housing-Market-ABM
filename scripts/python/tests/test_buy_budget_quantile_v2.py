from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.python.helpers.psd.buy_budget_quantile_v2 import (
    DEFAULT_INCOME_CHECKPOINTS,
    GUARDRAIL_MODE_WARN,
    PPD_STATUS_A_ONLY,
    PPD_STATUS_BOTH,
    QuantileFitSpec,
    TAIL_FAMILY_PARETO,
    YEAR_POLICY_2024_ONLY,
    YEAR_POLICY_BOTH,
    build_objective_weight_profiles,
    budget_median_multiple,
    evaluate_guardrails,
    evaluate_variants,
    fit_years_from_policy,
    select_production_variant,
)


class TestBuyBudgetQuantileV2(unittest.TestCase):
    def _write_csv(self, rows: list[list[object]]) -> Path:
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

    def _ppd_row(self, identifier: str, price: int, date: str, status: str = "A") -> list[object]:
        return [
            identifier,
            str(price),
            date,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            status,
            "A",
        ]

    def _synthetic_quarterly(self) -> Path:
        rows = [
            ["Mortgages Grouped By", "Category", "Postcode Region", "Date", "Number of Sales"],
            ["Number of sales by gross income bands", "£0 - £50,000", "East Midlands", "2024 Q1", "130"],
            ["Number of sales by gross income bands", "£50,001 - £100,000", "East Midlands", "2024 Q1", "150"],
            ["Number of sales by gross income bands", "£100,001 +", "East Midlands", "2024 Q1", "50"],
            ["Number of sales by property value bands", "£0 - £150,000", "East Midlands", "2024 Q1", "70"],
            ["Number of sales by property value bands", "£150,001 - £300,000", "East Midlands", "2024 Q1", "175"],
            ["Number of sales by property value bands", "£300,001 +", "East Midlands", "2024 Q1", "85"],
            ["Median loan amounts (£)", "All borrowers", "East Midlands", "2024 Q1", "190000"],
            ["Median loan-to-value (LTV) ratios (%)", "All borrowers", "East Midlands", "2024 Q1", "74"],
            ["Number of sales by loan amount bands", "£0 - £50,000", "East Midlands", "2024 Q1", "40"],
            ["Number of sales by loan-to-value (LTV) ratio", ">90% - <=95%", "East Midlands", "2024 Q1", "15"],
            ["Number of sales by type of borrower", "First time buyer", "East Midlands", "2024 Q1", "95"],
        ]
        return self._write_csv(rows)

    def _synthetic_ppd_2024(self) -> Path:
        rows = [
            self._ppd_row("id24a", 180000, "2024-01-02 00:00", "A"),
            self._ppd_row("id24b", 220000, "2024-03-10 00:00", "A"),
            self._ppd_row("id24c", 280000, "2024-05-14 00:00", "A"),
            self._ppd_row("id24d", 350000, "2024-09-11 00:00", "A"),
            self._ppd_row("id24e", 450000, "2024-11-01 00:00", "B"),
        ]
        return self._write_csv(rows)

    def _synthetic_ppd_2025(self) -> Path:
        rows = [
            self._ppd_row("id25a", 210000, "2025-01-08 00:00", "A"),
            self._ppd_row("id25b", 260000, "2025-02-19 00:00", "A"),
            self._ppd_row("id25c", 320000, "2025-04-22 00:00", "A"),
            self._ppd_row("id25d", 420000, "2025-07-17 00:00", "A"),
            self._ppd_row("id25e", 500000, "2025-10-25 00:00", "B"),
        ]
        return self._write_csv(rows)

    def test_guardrail_logic_and_budget_multiple(self) -> None:
        multiple = budget_median_multiple(buy_scale=1.5, buy_exponent=1.0, income=100_000)
        self.assertGreater(multiple, 1.0)

        ok = evaluate_guardrails(
            buy_scale=2.5,
            buy_exponent=0.95,
            buy_mu=0.0,
            buy_sigma=0.35,
            hard_p95_cap=15.0,
            exponent_max=1.0,
            sigma_warning_low=0.2,
            sigma_warning_high=0.6,
            income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
        )
        self.assertTrue(ok.passed)

        bad_p95 = evaluate_guardrails(
            buy_scale=12.0,
            buy_exponent=0.9,
            buy_mu=0.0,
            buy_sigma=0.8,
            hard_p95_cap=15.0,
            exponent_max=1.0,
            sigma_warning_low=0.2,
            sigma_warning_high=0.6,
            income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
        )
        self.assertFalse(bad_p95.passed)
        self.assertTrue(any("P95 budget multiple" in item for item in bad_p95.hard_failures))

        bad_exponent = evaluate_guardrails(
            buy_scale=2.5,
            buy_exponent=1.05,
            buy_mu=0.0,
            buy_sigma=0.35,
            hard_p95_cap=15.0,
            exponent_max=1.0,
            sigma_warning_low=0.2,
            sigma_warning_high=0.6,
            income_checkpoints=DEFAULT_INCOME_CHECKPOINTS,
        )
        self.assertFalse(bad_exponent.passed)
        self.assertTrue(any("BUY_EXPONENT" in item for item in bad_exponent.hard_failures))

    def test_2024_only_year_policy(self) -> None:
        self.assertEqual(fit_years_from_policy(YEAR_POLICY_2024_ONLY), (2024,))

    def test_evaluate_variants_mu_locked_and_pareto_alpha_changes_tail(self) -> None:
        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        ppd_2025 = self._synthetic_ppd_2025()
        try:
            results = evaluate_variants(
                quarterly_csv=quarterly,
                target_year_psd=2024,
                ppd_paths=(ppd_2024, ppd_2025),
                status_mode=PPD_STATUS_A_ONLY,
                year_policy=YEAR_POLICY_BOTH,
                guardrail_mode=GUARDRAIL_MODE_WARN,
                spec=QuantileFitSpec(within_bin_points=9, quantile_grid_size=500, ppd_mean_anchor_weight=3.0),
                objective_weight_profiles=build_objective_weight_profiles(
                    w_anchor_values=(12.0,),
                    w_p95_values=(20.0,),
                    w_sigma_values=(4.0,),
                    w_curve_values=(12.0,),
                ),
                tail_family=TAIL_FAMILY_PARETO,
                pareto_alpha_values=(1.2, 3.0),
                income_open_upper_k=180.0,
                property_open_upper_k=900.0,
            )
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)
            ppd_2025.unlink(missing_ok=True)

        self.assertGreaterEqual(len(results), 2)
        for item in results:
            self.assertEqual(item.buy_mu, 0.0)

        by_alpha = {item.selected_alpha: item for item in results}
        self.assertIn(1.2, by_alpha)
        self.assertIn(3.0, by_alpha)

        tail_max_low_alpha = max(by_alpha[1.2].tail_income_values)
        tail_max_high_alpha = max(by_alpha[3.0].tail_income_values)
        self.assertGreater(tail_max_low_alpha, tail_max_high_alpha)

    def test_2024_only_raked_estimator_uses_no_2025_ppd(self) -> None:
        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        try:
            results = evaluate_variants(
                quarterly_csv=quarterly,
                target_year_psd=2024,
                ppd_paths=(ppd_2024,),
                status_mode=PPD_STATUS_A_ONLY,
                year_policy=YEAR_POLICY_2024_ONLY,
                guardrail_mode=GUARDRAIL_MODE_WARN,
                spec=QuantileFitSpec(
                    within_bin_points=9,
                    quantile_grid_size=500,
                    ppd_mean_anchor_weight=3.0,
                    fixed_exponent=1.0,
                ),
                objective_weight_profiles=build_objective_weight_profiles(
                    w_anchor_values=(1.0,),
                    w_p95_values=(1.0,),
                    w_sigma_values=(1.0,),
                    w_curve_values=(1.0,),
                ),
                tail_family=TAIL_FAMILY_PARETO,
                pareto_alpha_values=(1.8,),
                income_open_upper_k=180.0,
                property_open_upper_k=900.0,
            )
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)

        self.assertEqual(len(results), 1)
        selected = results[0]
        self.assertTrue(selected.guardrails.passed, selected.guardrails.hard_failures)
        self.assertEqual(selected.year_policy, YEAR_POLICY_2024_ONLY)
        self.assertEqual(selected.fit_years, (2024,))
        self.assertEqual(selected.buy_mu, 0.0)
        self.assertEqual(selected.buy_exponent, 1.0)
        self.assertGreater(selected.buy_scale, 0.0)
        self.assertGreaterEqual(selected.buy_sigma, 0.1)
        self.assertLessEqual(selected.buy_sigma, 0.8)
        self.assertEqual(selected.diagnostics["source_year_psd"], 2024.0)
        self.assertEqual(selected.diagnostics["source_year_ppd"], 2024.0)
        self.assertEqual(selected.diagnostics["ppd_2025_loaded"], 0.0)

    def test_2024_only_rejects_when_2025_ppd_loaded(self) -> None:
        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        ppd_2025 = self._synthetic_ppd_2025()
        try:
            results = evaluate_variants(
                quarterly_csv=quarterly,
                target_year_psd=2024,
                ppd_paths=(ppd_2024, ppd_2025),
                status_mode=PPD_STATUS_A_ONLY,
                year_policy=YEAR_POLICY_2024_ONLY,
                guardrail_mode=GUARDRAIL_MODE_WARN,
                spec=QuantileFitSpec(
                    within_bin_points=9,
                    quantile_grid_size=500,
                    ppd_mean_anchor_weight=3.0,
                    fixed_exponent=1.0,
                ),
                objective_weight_profiles=build_objective_weight_profiles(
                    w_anchor_values=(1.0,),
                    w_p95_values=(1.0,),
                    w_sigma_values=(1.0,),
                    w_curve_values=(1.0,),
                ),
                tail_family=TAIL_FAMILY_PARETO,
                pareto_alpha_values=(1.8,),
                income_open_upper_k=180.0,
                property_open_upper_k=900.0,
            )
            with self.assertRaises(ValueError):
                select_production_variant(results)
            self.assertTrue(any("PPD 2025" in failure for failure in results[0].guardrails.hard_failures))
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)
            ppd_2025.unlink(missing_ok=True)

    def test_method_search_script_creates_artifacts(self) -> None:
        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        ppd_2025 = self._synthetic_ppd_2025()
        output_dir = Path(tempfile.mkdtemp(prefix="buy_v2_search_"))
        try:
            cmd = [
                sys.executable,
                "-m",
                "scripts.python.experiments.psd.psd_buy_budget_quantile_method_search_v2",
                "--quarterly-csv",
                str(quarterly),
                "--ppd-csv-2024",
                str(ppd_2024),
                "--ppd-csv-2025",
                str(ppd_2025),
                "--ppd-status-mode",
                "both",
                "--year-policy",
                "both",
                "--guardrail-mode",
                "warn",
                "--objective-weight-grid-profile",
                "minimal",
                "--pareto-alpha-grid",
                "1.8",
                "--no-plot-overlays",
                "--within-bin-points",
                "9",
                "--quantile-grid-size",
                "500",
                "--ppd-mean-anchor-weight",
                "3.0",
                "--income-open-upper-k",
                "180",
                "--property-open-upper-k",
                "900",
                "--output-dir",
                str(output_dir),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            self.assertTrue((output_dir / "PsdBuyBudgetMethodSearchV2.csv").exists())
            self.assertTrue((output_dir / "PsdBuyBudgetMethodSearchV2Summary.json").exists())
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)
            ppd_2025.unlink(missing_ok=True)

    def test_calibration_script_creates_artifacts(self) -> None:
        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        ppd_2025 = self._synthetic_ppd_2025()
        output_dir = Path(tempfile.mkdtemp(prefix="buy_v2_calibration_"))
        try:
            cmd = [
                sys.executable,
                "-m",
                "scripts.python.calibration.psd.psd_buy_budget_calibration_v2",
                "--quarterly-csv",
                str(quarterly),
                "--ppd-csv-2024",
                str(ppd_2024),
                "--ppd-csv-2025",
                str(ppd_2025),
                "--ppd-status-mode",
                "both",
                "--year-policy",
                "both",
                "--guardrail-mode",
                "warn",
                "--objective-weight-grid-profile",
                "minimal",
                "--pareto-alpha-grid",
                "1.8",
                "--fit-degradation-max",
                "2.0",
                "--within-bin-points",
                "9",
                "--quantile-grid-size",
                "500",
                "--ppd-mean-anchor-weight",
                "3.0",
                "--income-open-upper-k",
                "180",
                "--property-open-upper-k",
                "900",
                "--output-dir",
                str(output_dir),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            csv_path = output_dir / "PsdBuyBudgetCalibrationV2.csv"
            json_path = output_dir / "PsdBuyBudgetCalibrationV2Summary.json"
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            text = csv_path.read_text(encoding="utf-8")
            self.assertIn("BUY_MU,0", text)
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)
            ppd_2025.unlink(missing_ok=True)

    def test_calibration_script_2024_only_does_not_require_2025_ppd(self) -> None:
        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        output_dir = Path(tempfile.mkdtemp(prefix="buy_v2_2024_only_calibration_"))
        try:
            cmd = [
                sys.executable,
                "-m",
                "scripts.python.calibration.psd.psd_buy_budget_calibration_v2",
                "--quarterly-csv",
                str(quarterly),
                "--ppd-csv-2024",
                str(ppd_2024),
                "--ppd-status-mode",
                "a_only",
                "--year-policy",
                "2024_only",
                "--guardrail-mode",
                "fail",
                "--objective-weight-grid-profile",
                "minimal",
                "--pareto-alpha-grid",
                "1.8",
                "--fit-degradation-max",
                "2.0",
                "--within-bin-points",
                "9",
                "--quantile-grid-size",
                "500",
                "--ppd-mean-anchor-weight",
                "3.0",
                "--fixed-exponent",
                "1.0",
                "--income-open-upper-k",
                "180",
                "--property-open-upper-k",
                "900",
                "--output-dir",
                str(output_dir),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            json_path = output_dir / "PsdBuyBudgetCalibrationV2Summary.json"
            self.assertTrue(json_path.exists())
            text = json_path.read_text(encoding="utf-8")
            self.assertIn('"year_policy": "2024_only"', text)
            self.assertIn('"buy_mu": 0.0', text)
            self.assertIn('"ppd_2025_loaded": 0.0', text)
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)

    def test_method_search_plot_outputs_when_matplotlib_available(self) -> None:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib not available")

        quarterly = self._synthetic_quarterly()
        ppd_2024 = self._synthetic_ppd_2024()
        ppd_2025 = self._synthetic_ppd_2025()
        output_dir = Path(tempfile.mkdtemp(prefix="buy_v2_plot_"))
        try:
            cmd = [
                sys.executable,
                "-m",
                "scripts.python.experiments.psd.psd_buy_budget_quantile_method_search_v2",
                "--quarterly-csv",
                str(quarterly),
                "--ppd-csv-2024",
                str(ppd_2024),
                "--ppd-csv-2025",
                str(ppd_2025),
                "--ppd-status-mode",
                "both",
                "--year-policy",
                "both",
                "--guardrail-mode",
                "warn",
                "--objective-weight-grid-profile",
                "minimal",
                "--pareto-alpha-grid",
                "1.8",
                "--plot-overlays",
                "--plot-pareto-ccdf",
                "--plot-top-k",
                "1",
                "--within-bin-points",
                "9",
                "--quantile-grid-size",
                "400",
                "--ppd-mean-anchor-weight",
                "3.0",
                "--income-open-upper-k",
                "180",
                "--property-open-upper-k",
                "900",
                "--output-dir",
                str(output_dir),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            plots = list((output_dir / "plots").glob("*.png"))
            self.assertGreater(len(plots), 0)
            self.assertTrue(any("pareto_ccdf" in path.name for path in plots))
        finally:
            quarterly.unlink(missing_ok=True)
            ppd_2024.unlink(missing_ok=True)
            ppd_2025.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
