from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.python.calibration.btl.bank_icr_hard_min_calibration import (
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    build_arg_parser as build_calibration_arg_parser,
    run_calibration,
)
from scripts.python.experiments.btl.bank_icr_hard_min_method_search import (
    METHOD_SEARCH_FILE_NAME,
    build_arg_parser as build_experiment_arg_parser,
)
from scripts.python.helpers.btl.bank_icr_hard_min import (
    DEFAULT_METHOD,
    build_bank_icr_hard_min_method_search_output,
    load_bank_icr_hard_min_sources,
    load_bank_initial_rate,
    resolve_bank_icr_hard_min_config_path,
    resolve_bank_icr_hard_min_source_csv_path,
)


class TestBankIcrHardMinCalibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.calibration_module = (
            "scripts.python.calibration.btl.bank_icr_hard_min_calibration"
        )
        cls.experiment_module = (
            "scripts.python.experiments.btl.bank_icr_hard_min_method_search"
        )

    def test_experiment_parser_defaults(self) -> None:
        args = build_experiment_arg_parser().parse_args([])
        self.assertIsNone(args.source_csv)
        self.assertIsNone(args.config_path)
        self.assertEqual(args.target_year, 2024)
        self.assertIsNone(args.output_dir)

    def test_calibration_parser_defaults(self) -> None:
        args = build_calibration_arg_parser().parse_args([])
        self.assertIsNone(args.source_csv)
        self.assertIsNone(args.config_path)
        self.assertEqual(args.target_year, 2024)
        self.assertEqual(args.method, DEFAULT_METHOD)
        self.assertIsNone(args.output_dir)

    def test_resolve_default_paths_from_root_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            source_csv = temp_root / "sources.csv"
            config_path = temp_root / "config.properties"
            source_csv.write_text("placeholder", encoding="utf-8")
            config_path.write_text("BANK_INITIAL_RATE = 0.0564953144\n", encoding="utf-8")

            resolved_source = resolve_bank_icr_hard_min_source_csv_path(
                None,
                root=temp_root,
                default_path=Path("sources.csv"),
            )
            resolved_config = resolve_bank_icr_hard_min_config_path(
                None,
                root=temp_root,
                default_path=Path("config.properties"),
            )

        self.assertEqual(resolved_source, source_csv.resolve())
        self.assertEqual(resolved_config, config_path.resolve())

    def test_missing_required_columns_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "sources.csv"
            csv_path.write_text(
                "role,document_path,document_label,source_as_of,publisher,segment,icr_fraction,notes\n"
                "decision,doc.pdf,Doc,2024-05-15,Paragon,SSC basic,1.25,Example\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_bank_icr_hard_min_sources(csv_path)

    def test_missing_bank_initial_rate_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.properties"
            config_path.write_text("SEED = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing BANK_INITIAL_RATE"):
                load_bank_initial_rate(config_path)

    def test_exact_candidate_calculations_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            csv_path = temp_root / "sources.csv"
            config_path = temp_root / "config.properties"
            self._write_default_sources_csv(csv_path)
            config_path.write_text(
                "BANK_INITIAL_RATE = 0.0564953144\n",
                encoding="utf-8",
            )

            output = build_bank_icr_hard_min_method_search_output(
                source_csv=csv_path,
                config_path=config_path,
                target_year=2024,
            )

        self.assertEqual(len(output.decision_rows), 8)
        self.assertEqual(len(output.context_rows), 4)
        self.assertEqual(len(output.excluded_rows), 1)
        self.assertEqual(
            output.decision_icr_fractions,
            (1.25, 1.25, 1.3, 1.3, 1.4, 1.4, 1.45, 1.45),
        )
        self.assertEqual(output.context_icr_fractions, (1.91, 1.96, 1.95, 2.01))
        self.assertAlmostEqual(output.representative_stress_rate_fraction, 0.055, places=12)
        self.assertAlmostEqual(output.bank_initial_rate, 0.0564953144, places=12)
        by_id = {candidate.candidate_id: candidate for candidate in output.candidates}
        self.assertEqual(by_id[DEFAULT_METHOD].value, 1.25)
        self.assertAlmostEqual(by_id["stress_mapped_floor"].raw_value, 1.2169150792441648, places=12)
        self.assertEqual(by_id["stress_mapped_floor"].value, 1.22)
        self.assertAlmostEqual(by_id["cross_segment_mean"].raw_value, 1.35, places=12)
        self.assertEqual(by_id["cross_segment_mean"].value, 1.35)
        self.assertEqual(output.selected_candidate().candidate_id, DEFAULT_METHOD)
        self.assertEqual(output.selected_value(), 1.25)

    def test_run_calibration_writes_expected_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            csv_path = temp_root / "sources.csv"
            config_path = temp_root / "config.properties"
            output_dir = temp_root / "evidence"
            self._write_default_sources_csv(csv_path)
            config_path.write_text(
                "BANK_INITIAL_RATE = 0.0564953144\n",
                encoding="utf-8",
            )

            summary = run_calibration(
                source_csv=csv_path,
                config_path=config_path,
                target_year=2024,
                method=DEFAULT_METHOD,
                output_dir=output_dir,
            )

            loaded_summary = json.loads(
                (output_dir / SUMMARY_FILE_NAME).read_text(encoding="utf-8")
            )
            self.assertTrue((output_dir / SOURCE_VALUES_FILE_NAME).exists())
            self.assertEqual(
                loaded_summary["selectedConfigValues"]["BANK_ICR_HARD_MIN"],
                1.25,
            )
            self.assertEqual(summary["selectedConfigValues"]["BANK_ICR_HARD_MIN"], 1.25)

    def test_production_cli_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            csv_path = temp_root / "sources.csv"
            config_path = temp_root / "config.properties"
            output_dir = temp_root / "evidence"
            self._write_default_sources_csv(csv_path)
            config_path.write_text(
                "BANK_INITIAL_RATE = 0.0564953144\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.calibration_module,
                    "--source-csv",
                    str(csv_path),
                    "--config-path",
                    str(config_path),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            self.assertIn("BANK_ICR_HARD_MIN = 1.25", result.stdout)
            self.assertTrue((output_dir / SOURCE_VALUES_FILE_NAME).exists())
            self.assertTrue((output_dir / SUMMARY_FILE_NAME).exists())

            experiment = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.experiment_module,
                    "--source-csv",
                    str(csv_path),
                    "--config-path",
                    str(config_path),
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
                    "role",
                    "document_path",
                    "document_label",
                    "source_as_of",
                    "publisher",
                    "segment",
                    "icr_fraction",
                    "stress_rate_fraction",
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
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "SSC basic-rate taxpayer (20%)",
                    "icr_fraction": "1.25",
                    "stress_rate_fraction": "0.055",
                    "notes": "Selected default lower-bound row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "SSC limited company",
                    "icr_fraction": "1.25",
                    "stress_rate_fraction": "0.055",
                    "notes": "Selected default lower-bound row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "HMO/multi-unit/all other basic-rate taxpayer (20%)",
                    "icr_fraction": "1.30",
                    "stress_rate_fraction": "0.055",
                    "notes": "Cross-segment mean diagnostic row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "HMO/multi-unit/all other limited company",
                    "icr_fraction": "1.30",
                    "stress_rate_fraction": "0.055",
                    "notes": "Cross-segment mean diagnostic row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "SSC higher-rate taxpayer (40%)",
                    "icr_fraction": "1.40",
                    "stress_rate_fraction": "0.055",
                    "notes": "Rejected higher-tax segment row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "SSC additional-rate taxpayer (45%)",
                    "icr_fraction": "1.40",
                    "stress_rate_fraction": "0.055",
                    "notes": "Rejected higher-tax segment row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "HMO/multi-unit/all other higher-rate taxpayer (40%)",
                    "icr_fraction": "1.45",
                    "stress_rate_fraction": "0.055",
                    "notes": "Rejected higher-tax specialist row.",
                },
                {
                    "role": "decision",
                    "document_path": "private-datasets/misc/Paragon Portfolio buy-to-let product guide.pdf",
                    "document_label": "Paragon portfolio guide",
                    "source_as_of": "2024-05-15",
                    "publisher": "Paragon Bank",
                    "segment": "HMO/multi-unit/all other additional-rate taxpayer (45%)",
                    "icr_fraction": "1.45",
                    "stress_rate_fraction": "0.055",
                    "notes": "Rejected higher-tax specialist row.",
                },
                {
                    "role": "context",
                    "document_path": "private-datasets/ukf/Buy to let Mortgage Market Update Q1.pdf",
                    "document_label": "UK Finance Buy to let Mortgage Market Update Q1 2024",
                    "source_as_of": "2024 Q1",
                    "publisher": "UK Finance",
                    "segment": "Average observed market ICR",
                    "icr_fraction": "1.91",
                    "stress_rate_fraction": "",
                    "notes": "Context-only outcome measure.",
                },
                {
                    "role": "context",
                    "document_path": "private-datasets/ukf/Buy to let Mortgage Market Update Q2.pdf",
                    "document_label": "UK Finance Buy to let Mortgage Market Update Q2 2024",
                    "source_as_of": "2024 Q2",
                    "publisher": "UK Finance",
                    "segment": "Average observed market ICR",
                    "icr_fraction": "1.96",
                    "stress_rate_fraction": "",
                    "notes": "Context-only outcome measure.",
                },
                {
                    "role": "context",
                    "document_path": "private-datasets/ukf/Buy to let Mortgage Market Update Q3.pdf",
                    "document_label": "UK Finance Buy to let Mortgage Market Update Q3 2024",
                    "source_as_of": "2024 Q3",
                    "publisher": "UK Finance",
                    "segment": "Average observed market ICR",
                    "icr_fraction": "1.95",
                    "stress_rate_fraction": "",
                    "notes": "Context-only outcome measure.",
                },
                {
                    "role": "context",
                    "document_path": "private-datasets/ukf/Buy to let Mortgage Market Update Q4.pdf",
                    "document_label": "UK Finance Buy to let Mortgage Market Update Q4 2024",
                    "source_as_of": "2024 Q4",
                    "publisher": "UK Finance",
                    "segment": "Average observed market ICR",
                    "icr_fraction": "2.01",
                    "stress_rate_fraction": "",
                    "notes": "Context-only outcome measure.",
                },
                {
                    "role": "excluded",
                    "document_path": "private-datasets/misc/CMI-BTL-ProductGuide.pdf",
                    "document_label": "CMI-BTL-ProductGuide.pdf",
                    "source_as_of": "2022-05-30",
                    "publisher": "CHL Mortgages",
                    "segment": "Excluded file mismatch",
                    "icr_fraction": "",
                    "stress_rate_fraction": "",
                    "notes": "On-disk file mismatch excluded from the proxy decision.",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()

