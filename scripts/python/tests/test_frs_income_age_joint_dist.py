from __future__ import annotations

import csv
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.python.calibration.frs.age_dist import (
    HHAGEGR4_COLUMN,
    HHAGEGRP_COLUMN,
    WEIGHT_COLUMN,
)
from scripts.python.calibration.frs.income_age_joint_dist import (
    ANNUALISATION_FACTOR,
    DERIVED_RENTAL_INCOME_COLUMN,
    GROSS_NON_RENT_INCOME_COLUMN,
    INCOME_COLUMN,
    INCOME_TRIM_PERCENTILE,
    LOG_ANNUAL_INCOME_COLUMN,
    OUTPUT_FILE_NAME,
    RENTAL_INCOME_COLUMN,
    SOURCE_VALUES_FILE_NAME,
    SUBLET_COLUMN,
    SUMMARY_FILE_NAME,
    build_arg_parser,
    compute_income_age_joint_distribution,
    prepare_valid_income_age_rows,
    run_income_age_joint_distribution,
    validate_dictionary_contracts,
)


class TestFrsIncomeAgeJointDistribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.module_name = "scripts.python.calibration.frs.income_age_joint_dist"

    def test_parser_defaults(self) -> None:
        args = build_arg_parser().parse_args([])

        self.assertIsNone(args.household_csv)
        self.assertIsNone(args.dictionary_txt)
        self.assertIsNone(args.output_dir)
        self.assertIsNone(args.evidence_dir)

    def test_validate_dictionary_contracts_accepts_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dictionary_path = Path(tmp_dir) / "dictionary.txt"
            self._write_dictionary(dictionary_path)

            contracts = validate_dictionary_contracts(dictionary_path)

            self.assertEqual(
                [contract["variable"] for contract in contracts],
                [
                    WEIGHT_COLUMN,
                    INCOME_COLUMN,
                    SUBLET_COLUMN,
                    RENTAL_INCOME_COLUMN,
                    HHAGEGRP_COLUMN,
                    HHAGEGR4_COLUMN,
                ],
            )

    def test_validate_dictionary_contracts_rejects_wrong_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dictionary_path = Path(tmp_dir) / "dictionary.txt"
            self._write_dictionary(dictionary_path, hhinc_measurement="NOMINAL")

            with self.assertRaisesRegex(ValueError, "measurement mismatch"):
                validate_dictionary_contracts(dictionary_path)

    def test_prepare_valid_income_age_rows_filters_every_required_measure(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1, 1, 1, 1, 1, 1, 2, 99, 3],
                HHAGEGR4_COLUMN: [1, 1, 1, 1, 1, 1, 2, 1, 3],
                INCOME_COLUMN: [100.0, 0.0, -1.0, "bad", float("inf"), 100.0, 100.0, 100.0, 100.0],
                SUBLET_COLUMN: [2.0] * 9,
                RENTAL_INCOME_COLUMN: ["A"] * 9,
                WEIGHT_COLUMN: [2.0, 2.0, 2.0, 2.0, 2.0, float("inf"), 0.0, 2.0, 3.0],
            }
        )

        valid, _, age_column, diagnostics = prepare_valid_income_age_rows(raw)

        self.assertEqual(age_column, HHAGEGRP_COLUMN)
        self.assertEqual(len(valid), 2)
        self.assertEqual(valid[GROSS_NON_RENT_INCOME_COLUMN].tolist(), [100.0, 100.0])
        self.assertEqual(valid[WEIGHT_COLUMN].tolist(), [2.0, 3.0])
        self.assertEqual(diagnostics["incomeFilter"]["totalIncomeNonNumericRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["totalIncomeMissingCodeRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["nonPositiveRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["totalIncomeNonFiniteRows"], 1)
        self.assertEqual(diagnostics["weightFilter"]["nonFiniteRowsAfterAgeFilter"], 1)

    def test_prepare_valid_income_age_rows_coerces_non_subletter_subrent_to_zero(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1, 1, 1, 1, 1, 1, 1, 1],
                HHAGEGR4_COLUMN: [1, 1, 1, 1, 1, 1, 1, 1],
                INCOME_COLUMN: [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0],
                SUBLET_COLUMN: [2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 9.0, "bad"],
                RENTAL_INCOME_COLUMN: ["A", 50.0, -1.0, "bad", -0.5, float("inf"), 0.0, 0.0],
                WEIGHT_COLUMN: [1.0] * 8,
            }
        )

        valid, _, _, diagnostics = prepare_valid_income_age_rows(raw)

        self.assertEqual(valid[DERIVED_RENTAL_INCOME_COLUMN].tolist(), [0.0, 50.0])
        self.assertEqual(valid[GROSS_NON_RENT_INCOME_COLUMN].tolist(), [100.0, 100.0])
        self.assertEqual(diagnostics["incomeFilter"]["nonSubletterRentalIncomeCoercedRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["rentalIncomeMissingCodeRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["rentalIncomeNonNumericRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["rentalIncomeNegativeRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["rentalIncomeNonFiniteRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["subletterInvalidRentalIncomeRows"], 4)
        self.assertEqual(diagnostics["incomeFilter"]["subletInvalidCodeRows"], 1)
        self.assertEqual(diagnostics["incomeFilter"]["subletNonNumericRows"], 1)

    def test_prepare_valid_income_age_rows_uses_age_dist_fallback(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: ["A", "A"],
                HHAGEGR4_COLUMN: [13, 1],
                INCOME_COLUMN: [100.0, 200.0],
                SUBLET_COLUMN: [2.0, 2.0],
                RENTAL_INCOME_COLUMN: ["A", "A"],
                WEIGHT_COLUMN: [80.0, 20.0],
            }
        )

        valid, band_scheme, age_column, diagnostics = prepare_valid_income_age_rows(raw)

        self.assertEqual(age_column, HHAGEGR4_COLUMN)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(band_scheme), 15)
        self.assertIn("hhagegrp is anonymized", diagnostics["fallbackReason"])

    def test_prepare_valid_income_age_rows_annualises_weekly_income_before_log(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1],
                HHAGEGR4_COLUMN: [1],
                INCOME_COLUMN: [100.0],
                SUBLET_COLUMN: [1.0],
                RENTAL_INCOME_COLUMN: [25.0],
                WEIGHT_COLUMN: [2.0],
            }
        )

        valid, _, _, _ = prepare_valid_income_age_rows(raw)

        self.assertEqual(valid.iloc[0][GROSS_NON_RENT_INCOME_COLUMN], 75.0)
        self.assertEqual(valid.iloc[0]["annual_income"], 75.0 * ANNUALISATION_FACTOR)
        self.assertAlmostEqual(
            valid.iloc[0][LOG_ANNUAL_INCOME_COLUMN],
            math.log(75.0 * ANNUALISATION_FACTOR),
        )

    def test_prepare_valid_income_age_rows_filters_positive_before_was_style_trim(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1] * 303,
                HHAGEGR4_COLUMN: [1] * 303,
                INCOME_COLUMN: [0.0, 1.0] + [100.0 + i for i in range(300)] + [10000.0],
                SUBLET_COLUMN: [2.0] * 303,
                RENTAL_INCOME_COLUMN: ["A"] * 303,
                WEIGHT_COLUMN: [1.0] * 303,
            }
        )

        valid, _, _, diagnostics = prepare_valid_income_age_rows(raw)

        self.assertEqual(diagnostics["incomeFilter"]["nonPositiveRows"], 1)
        self.assertEqual(diagnostics["positiveIncomeRows"], 302)
        self.assertEqual(diagnostics["incomeTrim"]["droppedRows"], 5)
        self.assertEqual(len(valid), 297)
        self.assertGreater(float(valid[GROSS_NON_RENT_INCOME_COLUMN].min()), 1.0)
        self.assertLess(float(valid[GROSS_NON_RENT_INCOME_COLUMN].max()), 10000.0)
        self.assertEqual(diagnostics["incomeTrim"]["percentile"], INCOME_TRIM_PERCENTILE)

    def test_compute_income_age_joint_distribution_row_normalises_by_frs_age_bin(self) -> None:
        raw = pd.DataFrame(
            {
                HHAGEGRP_COLUMN: [1, 2, 3, 3],
                HHAGEGR4_COLUMN: [1, 2, 3, 3],
                INCOME_COLUMN: [100.0, 200.0, 100.0, 400.0],
                SUBLET_COLUMN: [2.0, 2.0, 2.0, 2.0],
                RENTAL_INCOME_COLUMN: ["A", "A", "A", "A"],
                WEIGHT_COLUMN: [1.0, 3.0, 2.0, 2.0],
            }
        )
        valid, band_scheme, age_column, _ = prepare_valid_income_age_rows(raw)
        income_edges = np.log(np.asarray([50.0, 150.0, 300.0, 500.0]) * ANNUALISATION_FACTOR)

        rows, _, _, diagnostics = compute_income_age_joint_distribution(
            valid,
            band_scheme,
            age_column,
            income_bin_edges=income_edges,
        )

        first_age_rows = [row for row in rows if row.age_lower_edge == 16.0 and row.age_upper_edge == 20.0]
        second_age_rows = [row for row in rows if row.age_lower_edge == 20.0 and row.age_upper_edge == 25.0]
        third_age_rows = [row for row in rows if row.age_lower_edge == 25.0 and row.age_upper_edge == 30.0]
        empty_age_rows = [row for row in rows if row.age_lower_edge == 30.0 and row.age_upper_edge == 35.0]

        self.assertEqual([row.probability for row in first_age_rows], [1.0, 0.0, 0.0])
        self.assertEqual([row.probability for row in second_age_rows], [0.0, 1.0, 0.0])
        self.assertEqual([row.probability for row in third_age_rows], [0.5, 0.0, 0.5])
        self.assertEqual([row.probability for row in empty_age_rows], [0.5, 0.0, 0.5])
        self.assertAlmostEqual(diagnostics["ageBinProbabilitySums"]["16-20"], 1.0)
        self.assertAlmostEqual(diagnostics["ageBinProbabilitySums"]["20-25"], 1.0)
        self.assertAlmostEqual(diagnostics["ageBinProbabilitySums"]["25-30"], 1.0)
        self.assertEqual(diagnostics["ageBinEdges"][:4], [16.0, 20.0, 25.0, 30.0])
        self.assertEqual(diagnostics["zeroBinCounts"]["30-35"], 1)
        self.assertEqual(diagnostics["emptyAgeBinProbabilitySources"]["30-35"], "25-30")

    def test_run_income_age_joint_distribution_writes_csv_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_csv = temp_root / "househol.csv"
            dictionary_path = temp_root / "dictionary.txt"
            output_dir = temp_root / "output"
            evidence_dir = temp_root / "evidence"
            self._write_household_csv(
                input_csv,
                [
                    {
                        HHAGEGRP_COLUMN: "A",
                        HHAGEGR4_COLUMN: "1",
                        INCOME_COLUMN: "100",
                        SUBLET_COLUMN: "2",
                        RENTAL_INCOME_COLUMN: "A",
                        WEIGHT_COLUMN: "2",
                    },
                    {
                        HHAGEGRP_COLUMN: "A",
                        HHAGEGR4_COLUMN: "13",
                        INCOME_COLUMN: "200",
                        SUBLET_COLUMN: "1",
                        RENTAL_INCOME_COLUMN: "50",
                        WEIGHT_COLUMN: "8",
                    },
                ],
            )
            self._write_dictionary(dictionary_path)

            result = run_income_age_joint_distribution(
                household_csv=input_csv,
                dictionary_txt=dictionary_path,
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
            self.assertEqual(
                lines[0],
                "# Age (lower edge), Age (upper edge), Log Gross Income (lower edge), Log Gross Income (upper edge), Probability",
            )
            self.assertEqual(len(lines), 376)
            loaded_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded_summary["columns"]["selectedAge"], HHAGEGR4_COLUMN)
            self.assertEqual(loaded_summary["columns"]["totalIncome"], INCOME_COLUMN)
            self.assertEqual(loaded_summary["columns"]["subletIndicator"], SUBLET_COLUMN)
            self.assertEqual(loaded_summary["columns"]["rentalIncome"], RENTAL_INCOME_COLUMN)
            self.assertEqual(loaded_summary["columns"]["derivedRentalIncome"], DERIVED_RENTAL_INCOME_COLUMN)
            self.assertEqual(loaded_summary["columns"]["income"], GROSS_NON_RENT_INCOME_COLUMN)
            self.assertEqual(
                loaded_summary["diagnostics"]["ageBinEdges"],
                [16.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 95.0],
            )
            self.assertIn("zeroBinCounts", loaded_summary["diagnostics"])

    def test_cli_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            input_csv = temp_root / "househol.csv"
            dictionary_path = temp_root / "dictionary.txt"
            output_dir = temp_root / "output"
            evidence_dir = temp_root / "evidence"
            self._write_household_csv(
                input_csv,
                [
                    {
                        HHAGEGRP_COLUMN: "1",
                        HHAGEGR4_COLUMN: "1",
                        INCOME_COLUMN: "100",
                        SUBLET_COLUMN: "2",
                        RENTAL_INCOME_COLUMN: "A",
                        WEIGHT_COLUMN: "2",
                    },
                    {
                        HHAGEGRP_COLUMN: "2",
                        HHAGEGR4_COLUMN: "2",
                        INCOME_COLUMN: "200",
                        SUBLET_COLUMN: "2",
                        RENTAL_INCOME_COLUMN: "A",
                        WEIGHT_COLUMN: "8",
                    },
                ],
            )
            self._write_dictionary(dictionary_path)

            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.module_name,
                    "--household-csv",
                    str(input_csv),
                    "--dictionary-txt",
                    str(dictionary_path),
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
            self.assertIn("DATA_INCOME_GIVEN_AGE = src/main/resources/AgeGrossIncomeJointDist.csv", result.stdout)
            self.assertIn("Selected age column: hhagegrp", result.stdout)
            self.assertTrue((output_dir / OUTPUT_FILE_NAME).exists())
            self.assertTrue((evidence_dir / SUMMARY_FILE_NAME).exists())

    @staticmethod
    def _write_household_csv(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    HHAGEGRP_COLUMN,
                    HHAGEGR4_COLUMN,
                    INCOME_COLUMN,
                    SUBLET_COLUMN,
                    RENTAL_INCOME_COLUMN,
                    WEIGHT_COLUMN,
                ],
            )
            writer.writeheader()
            for row in rows:
                output = {
                    HHAGEGRP_COLUMN: "",
                    HHAGEGR4_COLUMN: "",
                    INCOME_COLUMN: "",
                    SUBLET_COLUMN: "2",
                    RENTAL_INCOME_COLUMN: "A",
                    WEIGHT_COLUMN: "",
                }
                output.update(row)
                writer.writerow(output)

    @staticmethod
    def _write_dictionary(path: Path, *, hhinc_measurement: str = "SCALE") -> None:
        entries = [
            (254, WEIGHT_COLUMN, "Grossing variable", "SCALE"),
            (273, INCOME_COLUMN, "HH - Total Household income", hhinc_measurement),
            (199, SUBLET_COLUMN, "Whether have formal sublet arrangement", "NOMINAL"),
            (201, RENTAL_INCOME_COLUMN, "Amount of rent from subletting", "SCALE"),
            (295, HHAGEGRP_COLUMN, "Age of HRP (Pub)", "NOMINAL"),
            (297, HHAGEGR4_COLUMN, "Age of HRP - 5 Year Age Bands - Anon", "NOMINAL"),
        ]
        text = ""
        for position, variable, label, measurement in entries:
            text += (
                f"Pos. = {position}\tVariable = {variable}\tVariable label = {label}\n"
                f"This variable is  numeric, the SPSS measurement level is {measurement}\n"
                "SPSS user missing values = -9.0 thru -1.0\n"
                f"\tValue label information for {variable}\n\n"
            )
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
