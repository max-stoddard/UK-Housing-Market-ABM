from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.python.calibration.lcfs.consumption_fractions import (
    DEFAULT_METHOD,
    ESSENTIAL_CONSUMPTION_FRACTION_KEY,
    MAXIMUM_CONSUMPTION_FRACTION_KEY,
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    build_arg_parser,
    compute_estimates,
    load_lcfs_data,
    method_spec,
    run_calibration,
    weighted_quantile,
)


class TestLcfsConsumptionFractions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.module_name = "scripts.python.calibration.lcfs.consumption_fractions"

    def test_parser_defaults(self) -> None:
        args = build_arg_parser().parse_args([])

        self.assertEqual(args.dataset_year, 2024)
        self.assertIsNone(args.input_tab)
        self.assertEqual(args.method, DEFAULT_METHOD)
        self.assertIsNone(args.output_json)
        self.assertIsNone(args.evidence_dir)

    def test_column_resolution_for_2011_and_2024(self) -> None:
        modern_2011 = method_spec("weighted-modern", 2011)
        literal_2011 = method_spec("transparent-literal", 2011)
        modern_2024 = method_spec("weighted-modern", 2024)
        legacy_2024 = method_spec("legacy-match", 2024)

        self.assertEqual((modern_2011.income_column, modern_2011.consumption_column), ("p344p", "P600t"))
        self.assertEqual((literal_2011.income_column, literal_2011.consumption_column), ("incanon", "P600"))
        self.assertEqual((modern_2024.income_column, modern_2024.consumption_column), ("p344p", "p600t"))
        self.assertEqual((legacy_2024.income_column, legacy_2024.consumption_column), ("anon_income", "p600t"))
        self.assertEqual((modern_2024.essential_income_lower, modern_2024.essential_income_upper), (520.0, 640.0))
        self.assertEqual(modern_2024.annual_income_support_floor, 7400.0)
        self.assertEqual((literal_2011.essential_income_lower, literal_2011.essential_income_upper), (400.0, 480.0))
        self.assertEqual(literal_2011.annual_income_support_floor, 5900.0)
        self.assertEqual((legacy_2024.essential_income_lower, legacy_2024.essential_income_upper), (400.0, 480.0))
        self.assertEqual(legacy_2024.annual_income_support_floor, 5900.0)

    def test_weighted_quantile_matches_expected_step_interpolation(self) -> None:
        values = pd.Series([1.0, 2.0, 4.0])
        weights = pd.Series([1.0, 1.0, 2.0])

        self.assertAlmostEqual(weighted_quantile(values, weights, 0.5), 2.0)
        self.assertAlmostEqual(weighted_quantile(values, weights, 0.75), 3.0)

    def test_weighted_modern_uses_weighted_median_and_p99(self) -> None:
        spec = method_spec("weighted-modern", 2024)
        data = pd.DataFrame(
            {
                "p344p": [530.0, 600.0, 1000.0, 1000.0, 1000.0],
                "p600t": [265.0, 600.0, 600.0, 1200.0, 2400.0],
                "weighta": [1.0, 3.0, 1.0, 1.0, 1.0],
            }
        )

        estimates, diagnostics = compute_estimates(data, spec)
        by_key = {estimate.key: estimate for estimate in estimates}

        self.assertEqual(diagnostics["validRows"], 5)
        self.assertAlmostEqual(by_key[ESSENTIAL_CONSUMPTION_FRACTION_KEY].value, 2.0 / 3.0)
        self.assertAlmostEqual(
            by_key[MAXIMUM_CONSUMPTION_FRACTION_KEY].value,
            weighted_quantile(
                pd.Series([265.0 / (12.0 * 530.0), 600.0 / (12.0 * 600.0), 0.05, 0.1, 0.2]),
                pd.Series([1.0, 3.0, 1.0, 1.0, 1.0]),
                0.99,
            ),
        )
        self.assertEqual(
            by_key[ESSENTIAL_CONSUMPTION_FRACTION_KEY].filter_description,
            "p344p between 520 and 640 weekly",
        )
        self.assertEqual(
            by_key[MAXIMUM_CONSUMPTION_FRACTION_KEY].filter_description,
            "p344p * 52 > 7400",
        )

    def test_legacy_match_historical_output_and_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_tab = temp_root / "lcfs2011.tab"
            self._write_rows(
                input_tab,
                ["p344p", "incanon", "P600t", "P600", "weighta"],
                [
                    {"p344p": "410", "incanon": "410", "P600t": "205", "P600": "205", "weighta": "1"},
                    {"p344p": "420", "incanon": "420", "P600t": "277.2", "P600": "277.2", "weighta": "1"},
                    {"p344p": "430", "incanon": "430", "P600t": "430", "P600": "430", "weighta": "1"},
                    {"p344p": "100", "incanon": "100", "P600t": "60", "P600": "60", "weighta": "1"},
                    {"p344p": "1000", "incanon": "1000", "P600t": "600", "P600": "600", "weighta": "1"},
                    {"p344p": "1000", "incanon": "1000", "P600t": "1200", "P600": "1200", "weighta": "1"},
                    {"p344p": "1000", "incanon": "1000", "P600t": "2400", "P600": "2400", "weighta": "1"},
                ],
            )

            result = run_calibration(
                dataset_year=2011,
                input_tab=input_tab,
                method="legacy-match",
            )

        self.assertIn("98.7th percentile", result["methodRationale"])
        self.assertEqual(set(result["selectedConfigValues"]), {
            ESSENTIAL_CONSUMPTION_FRACTION_KEY,
            MAXIMUM_CONSUMPTION_FRACTION_KEY,
        })
        self.assertAlmostEqual(
            result["selectedConfigValues"][ESSENTIAL_CONSUMPTION_FRACTION_KEY],
            0.66,
        )

    def test_missing_columns_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_tab = Path(tmp_dir) / "lcfs.tab"
            self._write_rows(input_tab, ["p344p", "weighta"], [{"p344p": "400", "weighta": "1"}])

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_lcfs_data(input_tab, ["p344p", "p600t", "weighta"])

    def test_run_calibration_writes_stable_json_and_evidence_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_tab = temp_root / "lcfs2024.tab"
            output_json = temp_root / "summary.json"
            evidence_dir = temp_root / "evidence"
            self._write_rows(
                input_tab,
                ["p344p", "anon_income", "p600t", "p600", "weighta"],
                [
                    {"p344p": "530", "anon_income": "410", "p600t": "265", "p600": "205", "weighta": "1"},
                    {"p344p": "600", "anon_income": "420", "p600t": "600", "p600": "420", "weighta": "3"},
                    {"p344p": "100", "anon_income": "100", "p600t": "60", "p600": "60", "weighta": "1"},
                    {"p344p": "1000", "anon_income": "1000", "p600t": "1200", "p600": "1200", "weighta": "1"},
                    {"p344p": "1000", "anon_income": "1000", "p600t": "2400", "p600": "2400", "weighta": "1"},
                ],
            )

            result = run_calibration(
                dataset_year=2024,
                input_tab=input_tab,
                output_json=output_json,
                evidence_dir=evidence_dir,
            )

            loaded = json.loads(output_json.read_text(encoding="utf-8"))
            evidence_summary_exists = (evidence_dir / SUMMARY_FILE_NAME).exists()
            evidence_source_values_exists = (evidence_dir / SOURCE_VALUES_FILE_NAME).exists()

        self.assertEqual(loaded["method"], "weighted-modern")
        self.assertEqual(loaded["selectedConfigValues"], result["selectedConfigValues"])
        self.assertIn("methodComparison", loaded)
        self.assertIn("diagnostics", loaded)
        self.assertEqual(
            loaded["estimates"][0]["filter_description"],
            "p344p between 520 and 640 weekly",
        )
        self.assertEqual(
            loaded["estimates"][1]["filter_description"],
            "p344p * 52 > 7400",
        )
        self.assertTrue(evidence_summary_exists)
        self.assertTrue(evidence_source_values_exists)

    def test_cli_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_tab = temp_root / "lcfs2024.tab"
            output_json = temp_root / "summary.json"
            evidence_dir = temp_root / "evidence"
            self._write_rows(
                input_tab,
                ["p344p", "anon_income", "p600t", "p600", "weighta"],
                [
                    {"p344p": "530", "anon_income": "410", "p600t": "265", "p600": "205", "weighta": "1"},
                    {"p344p": "600", "anon_income": "420", "p600t": "600", "p600": "420", "weighta": "3"},
                    {"p344p": "100", "anon_income": "100", "p600t": "60", "p600": "60", "weighta": "1"},
                    {"p344p": "1000", "anon_income": "1000", "p600t": "1200", "p600": "1200", "weighta": "1"},
                    {"p344p": "1000", "anon_income": "1000", "p600t": "2400", "p600": "2400", "weighta": "1"},
                ],
            )

            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.module_name,
                    "--input-tab",
                    str(input_tab),
                    "--output-json",
                    str(output_json),
                    "--evidence-dir",
                    str(evidence_dir),
                ],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            output_json_exists = output_json.exists()
            evidence_summary_exists = (evidence_dir / SUMMARY_FILE_NAME).exists()

        self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
        self.assertIn(ESSENTIAL_CONSUMPTION_FRACTION_KEY, result.stdout)
        self.assertTrue(output_json_exists)
        self.assertTrue(evidence_summary_exists)

    @staticmethod
    def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)


if __name__ == "__main__":
    unittest.main()
