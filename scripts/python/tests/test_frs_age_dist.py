from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.python.calibration.frs.age_dist import (
    FRS_HHAGEGRP_BAND_BY_CODE,
    HHAGEGR4_COLUMN,
    HHAGEGRP_COLUMN,
    OUTPUT_FILE_NAME,
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    WEIGHT_COLUMN,
    build_arg_parser,
    compute_weighted_age_distribution,
    prepare_valid_age_rows,
    run_age_distribution,
)


class TestFrsAgeDistribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.module_name = "scripts.python.calibration.frs.age_dist"

    def test_parser_defaults(self) -> None:
        args = build_arg_parser().parse_args([])
        self.assertIsNone(args.household_csv)
        self.assertIsNone(args.output_dir)
        self.assertIsNone(args.evidence_dir)

    def test_hhagegrp_mapping_uses_requested_edges_and_midpoints(self) -> None:
        first = FRS_HHAGEGRP_BAND_BY_CODE[1]
        final = FRS_HHAGEGRP_BAND_BY_CODE[15]

        self.assertEqual((first.lower_edge, first.upper_edge, first.midpoint), (16.0, 20.0, 18.0))
        self.assertEqual((final.lower_edge, final.upper_edge, final.midpoint), (85.0, 95.0, 90.0))

    def test_filters_invalid_codes_and_weights(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1, 2, -1, 99, 3, 4, 5],
                WEIGHT_COLUMN: [10.0, 0.0, 5.0, 5.0, -1.0, None, 2.0],
            }
        )

        valid, band_scheme, age_column, diagnostics = prepare_valid_age_rows(raw)

        self.assertEqual(valid[HHAGEGRP_COLUMN].tolist(), [1, 5])
        self.assertEqual(valid[WEIGHT_COLUMN].tolist(), [10.0, 2.0])
        self.assertEqual(age_column, HHAGEGRP_COLUMN)
        self.assertEqual(len(band_scheme), 15)
        self.assertEqual(diagnostics["rawRows"], 7)
        self.assertEqual(diagnostics["validRows"], 2)
        self.assertEqual(diagnostics["droppedRows"], 5)

    def test_weighted_density_integrates_to_one(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1, 1, 2, 15],
                WEIGHT_COLUMN: [1.0, 1.0, 3.0, 5.0],
            }
        )
        valid, band_scheme, age_column, _ = prepare_valid_age_rows(raw)

        rows, total_weight = compute_weighted_age_distribution(valid, band_scheme, age_column)

        self.assertEqual(total_weight, 10.0)
        by_code = {row.age_code: row for row in rows}
        self.assertAlmostEqual(by_code[1].mass, 0.2)
        self.assertAlmostEqual(by_code[1].density, 0.2 / 4.0)
        self.assertAlmostEqual(by_code[2].mass, 0.3)
        self.assertAlmostEqual(by_code[2].density, 0.3 / 5.0)
        self.assertAlmostEqual(by_code[15].mass, 0.5)
        self.assertAlmostEqual(by_code[15].density, 0.5 / 10.0)
        self.assertAlmostEqual(
            sum(row.density * (row.upper_edge - row.lower_edge) for row in rows),
            1.0,
        )

    def test_missing_columns_fail_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            prepare_valid_age_rows(pd.DataFrame({HHAGEGRP_COLUMN: [1, 2]}))

    def test_hhagegr4_fallback_splits_75_plus_tail_uniformly(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: ["A", "A"],
                HHAGEGR4_COLUMN: [13, 1],
                WEIGHT_COLUMN: [80.0, 20.0],
            }
        )

        valid, band_scheme, age_column, diagnostics = prepare_valid_age_rows(raw)
        rows, total_weight = compute_weighted_age_distribution(valid, band_scheme, age_column)
        by_code = {row.age_code: row for row in rows}

        self.assertEqual(age_column, HHAGEGR4_COLUMN)
        self.assertEqual(total_weight, 100.0)
        self.assertIn("hhagegrp is anonymized", diagnostics["fallbackReason"])
        self.assertAlmostEqual(by_code[13].mass, 0.2)
        self.assertAlmostEqual(by_code[14].mass, 0.2)
        self.assertAlmostEqual(by_code[15].mass, 0.4)
        self.assertAlmostEqual(by_code[13].density, 0.04)
        self.assertAlmostEqual(by_code[14].density, 0.04)
        self.assertAlmostEqual(by_code[15].density, 0.04)

    def test_run_age_distribution_writes_csv_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_csv = temp_root / "househol.csv"
            output_dir = temp_root / "output"
            evidence_dir = temp_root / "evidence"
            self._write_household_csv(
                input_csv,
                [
                    {HHAGEGRP_COLUMN: "1", WEIGHT_COLUMN: "2"},
                    {HHAGEGRP_COLUMN: "2", WEIGHT_COLUMN: "3"},
                    {HHAGEGRP_COLUMN: "15", WEIGHT_COLUMN: "5"},
                ],
            )

            result = run_age_distribution(
                household_csv=input_csv,
                output_dir=output_dir,
                evidence_dir=evidence_dir,
            )

            output_path = output_dir / OUTPUT_FILE_NAME
            summary_path = evidence_dir / SUMMARY_FILE_NAME
            source_values_path = evidence_dir / SOURCE_VALUES_FILE_NAME

            self.assertEqual(result["output_file"], str(output_path))
            self.assertTrue(output_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(source_values_path.exists())
            lines = output_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(lines[0], "# Age (lower edge), Age (upper edge), Probability")
            self.assertEqual(len(lines), 16)
            loaded_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded_summary["diagnostics"]["validRows"], 3)

    def test_cli_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_csv = temp_root / "househol.csv"
            output_dir = temp_root / "output"
            evidence_dir = temp_root / "evidence"
            self._write_household_csv(
                input_csv,
                [
                    {HHAGEGRP_COLUMN: "1", WEIGHT_COLUMN: "2"},
                    {HHAGEGRP_COLUMN: "15", WEIGHT_COLUMN: "8"},
                ],
            )

            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.module_name,
                    "--household-csv",
                    str(input_csv),
                    "--output-dir",
                    str(output_dir),
                    "--evidence-dir",
                    str(evidence_dir),
                ],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            self.assertIn("DATA_AGE_DISTRIBUTION = src/main/resources/Age15-FRS-2023-24-Weighted.csv", result.stdout)
            self.assertTrue((output_dir / OUTPUT_FILE_NAME).exists())
            self.assertTrue((evidence_dir / SUMMARY_FILE_NAME).exists())

    @staticmethod
    def _write_household_csv(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[HHAGEGRP_COLUMN, HHAGEGR4_COLUMN, WEIGHT_COLUMN])
            writer.writeheader()
            for row in rows:
                output = {HHAGEGRP_COLUMN: "", HHAGEGR4_COLUMN: "", WEIGHT_COLUMN: ""}
                output.update(row)
                writer.writerow(output)


if __name__ == "__main__":
    unittest.main()
