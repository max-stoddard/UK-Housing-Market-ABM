from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.python.calibration.boe.boe_bank_age_limit_calibration import (
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    build_arg_parser as build_calibration_arg_parser,
    run_calibration,
)
from scripts.python.experiments.boe.boe_bank_age_limit_method_search import (
    METHOD_SEARCH_FILE_NAME,
    build_arg_parser as build_experiment_arg_parser,
)
from scripts.python.helpers.boe.bank_age_limit import (
    DEFAULT_METHOD,
    METHOD_CHOICES,
    build_bank_age_limit_method_search_output,
    load_bank_age_limit_sources,
    resolve_bank_age_limit_source_csv_path,
)


class TestBoeBankAgeLimitCalibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.calibration_module = "scripts.python.calibration.boe.boe_bank_age_limit_calibration"
        cls.experiment_module = "scripts.python.experiments.boe.boe_bank_age_limit_method_search"

    def test_experiment_parser_defaults(self) -> None:
        args = build_experiment_arg_parser().parse_args([])
        self.assertIsNone(args.source_csv)
        self.assertEqual(args.target_year, 2024)
        self.assertIsNone(args.output_dir)

    def test_calibration_parser_defaults(self) -> None:
        args = build_calibration_arg_parser().parse_args([])
        self.assertIsNone(args.source_csv)
        self.assertEqual(args.target_year, 2024)
        self.assertEqual(args.method, DEFAULT_METHOD)
        self.assertIsNone(args.output_dir)

    def test_resolve_source_csv_path_uses_default_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            default_path = temp_root / "bank-age-limit.csv"
            default_path.write_text("placeholder", encoding="utf-8")

            resolved = resolve_bank_age_limit_source_csv_path(
                None,
                root=temp_root,
                default_path=Path("bank-age-limit.csv"),
            )

        self.assertEqual(resolved, default_path.resolve())

    def test_missing_required_columns_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "sources.csv"
            csv_path.write_text(
                "provider,application_age_cap,source_url,source_as_of,notes\n"
                "Santander,75,https://example.com,2024-04-17,Example\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_bank_age_limit_sources(csv_path)

    def test_invalid_cap_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "sources.csv"
            self._write_sources_csv(
                csv_path,
                [
                    {
                        "provider": "Santander",
                        "application_age_cap": "seventy-five",
                        "repay_by_cap": "75",
                        "source_url": "https://example.com",
                        "source_as_of": "2024-04-17",
                        "notes": "Example",
                    }
                ],
            )
            with self.assertRaisesRegex(ValueError, "Invalid application_age_cap"):
                load_bank_age_limit_sources(csv_path)

    def test_exact_candidate_calculations_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "sources.csv"
            self._write_default_sources_csv(csv_path)

            output = build_bank_age_limit_method_search_output(
                source_csv=csv_path,
                target_year=2024,
            )

        self.assertEqual(output.explicit_origination_caps, (70, 75, 75))
        self.assertEqual(output.explicit_repay_caps, (80, 75, 75, 75, 80))
        self.assertAlmostEqual(output.origination_cap_mean, 73.33333333333333, places=10)
        self.assertAlmostEqual(output.repay_cap_mean, 77.0, places=10)
        self.assertAlmostEqual(output.hybrid_midpoint_raw, 75.16666666666666, places=10)
        by_id = {candidate.candidate_id: candidate for candidate in output.candidates}
        self.assertEqual(by_id["repay_cap_mean_round"].value, 77)
        self.assertEqual(by_id["hybrid_midpoint_round"].value, 75)
        self.assertEqual(by_id[DEFAULT_METHOD].value, 75)
        self.assertEqual(output.selected_candidate().candidate_id, DEFAULT_METHOD)
        self.assertEqual(output.selected_value(), 75)

    def test_run_calibration_writes_expected_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            csv_path = temp_root / "sources.csv"
            output_dir = temp_root / "evidence"
            self._write_default_sources_csv(csv_path)

            summary = run_calibration(
                source_csv=csv_path,
                target_year=2024,
                method=DEFAULT_METHOD,
                output_dir=output_dir,
            )

            loaded_summary = json.loads((output_dir / SUMMARY_FILE_NAME).read_text(encoding="utf-8"))
            self.assertTrue((output_dir / SOURCE_VALUES_FILE_NAME).exists())
            self.assertEqual(
                loaded_summary["selectedConfigValues"][ "BANK_AGE_LIMIT"],
                75,
            )
            self.assertEqual(summary["selectedConfigValues"]["BANK_AGE_LIMIT"], 75)

    def test_production_cli_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            csv_path = temp_root / "sources.csv"
            output_dir = temp_root / "evidence"
            self._write_default_sources_csv(csv_path)

            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.calibration_module,
                    "--source-csv",
                    str(csv_path),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            self.assertIn("BANK_AGE_LIMIT = 75", result.stdout)
            self.assertTrue((output_dir / SOURCE_VALUES_FILE_NAME).exists())
            self.assertTrue((output_dir / SUMMARY_FILE_NAME).exists())

            experiment = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.experiment_module,
                    "--source-csv",
                    str(csv_path),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(experiment.returncode, 0, msg=experiment.stderr + experiment.stdout)
            self.assertIn(DEFAULT_METHOD, experiment.stdout)
            self.assertTrue((output_dir / METHOD_SEARCH_FILE_NAME).exists())

    @staticmethod
    def _write_sources_csv(csv_path: Path, rows: list[dict[str, str]]) -> None:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "provider",
                    "application_age_cap",
                    "repay_by_cap",
                    "source_url",
                    "source_as_of",
                    "notes",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_default_sources_csv(self, csv_path: Path) -> None:
        self._write_sources_csv(
            csv_path,
            [
                {
                    "provider": "Lloyds Banking Group (Lloyds Bank)",
                    "application_age_cap": "",
                    "repay_by_cap": "80",
                    "source_url": "https://www.lloydsbank.com/example",
                    "source_as_of": "accessed 2026-04-17",
                    "notes": "Repay-side only on the cited public page.",
                },
                {
                    "provider": "Nationwide Building Society",
                    "application_age_cap": "70",
                    "repay_by_cap": "75",
                    "source_url": "https://www.nationwide.example",
                    "source_as_of": "accessed 2026-04-17",
                    "notes": "Approved origination-side proxy from public criteria.",
                },
                {
                    "provider": "NatWest Group (NatWest)",
                    "application_age_cap": "75",
                    "repay_by_cap": "75",
                    "source_url": "https://www.natwest.example",
                    "source_as_of": "accessed 2026-04-17",
                    "notes": "Mainstream 75 benchmark on both sides.",
                },
                {
                    "provider": "Santander UK",
                    "application_age_cap": "75",
                    "repay_by_cap": "75",
                    "source_url": "https://www.santander.example",
                    "source_as_of": "2024-04-17",
                    "notes": "Press release states maximum lending age is 75.",
                },
                {
                    "provider": "Barclays",
                    "application_age_cap": "",
                    "repay_by_cap": "80",
                    "source_url": "https://www.barclays.example",
                    "source_as_of": "accessed 2026-04-17",
                    "notes": "Repay-side only on the cited public page.",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
