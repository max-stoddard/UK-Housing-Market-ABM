from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import warnings
from pathlib import Path

from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

from scripts.python.calibration.official.ehs_tenancy_length_2024 import (
    DEFAULT_ODS_CANDIDATES,
    DEFAULT_TABLE_NAME,
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    TENANCY_LENGTH_MAX_KEY,
    TENANCY_LENGTH_MIN_KEY,
    build_arg_parser,
    extract_observations_from_rows,
    extract_tenancy_length_calibration,
    resolve_ods_path,
    run_calibration,
)

warnings.simplefilter("ignore", ResourceWarning)


def _add_ods_row(table: Table, values: list[object]) -> None:
    row = TableRow()
    for value in values:
        cell = TableCell()
        if value is not None:
            cell.addElement(P(text=str(value)))
        row.addElement(cell)
    table.addElement(row)


class TestEhsTenancyLength2024(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.module_name = "scripts.python.calibration.official.ehs_tenancy_length_2024"

    def _run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "-m", self.module_name, *args],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_parser_defaults(self) -> None:
        args = build_arg_parser().parse_args([])
        self.assertIsNone(args.ods_path)
        self.assertEqual(args.table, DEFAULT_TABLE_NAME)
        self.assertIsNone(args.output_dir)

    def test_resolve_ods_path_uses_fallback_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            fallback_path = temp_root / "fallback.ods"
            fallback_path.write_text("placeholder", encoding="utf-8")

            resolved = resolve_ods_path(
                None,
                candidate_paths=(Path("missing.ods"), Path("fallback.ods")),
                root=temp_root,
            )

        self.assertEqual(resolved, fallback_path.resolve())

    def test_extract_observations_from_rows_reads_ast_distribution(self) -> None:
        observations = extract_observations_from_rows(self._synthetic_rows())
        percentages = {observation.agreement_length: observation.percentage for observation in observations}

        self.assertEqual(percentages["6 months"], 23.6)
        self.assertEqual(percentages["12 months"], 61.3)
        self.assertEqual(percentages["18 months"], 3.8)
        self.assertEqual(percentages["other"], 11.3)

    def test_extract_tenancy_length_calibration_reads_synthetic_ods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ods_path = Path(tmp_dir) / "ehs.ods"
            self._write_synthetic_ods(ods_path, table_name=DEFAULT_TABLE_NAME, rows=self._synthetic_rows())

            calibration = extract_tenancy_length_calibration(ods_path)

        self.assertEqual(calibration.tenancy_length_min, 6)
        self.assertEqual(calibration.tenancy_length_max, 18)
        self.assertEqual(calibration.table_name, DEFAULT_TABLE_NAME)
        self.assertEqual(len(calibration.source_sha256), 64)

    def test_run_calibration_writes_source_values_and_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            ods_path = temp_root / "ehs.ods"
            output_dir = temp_root / "output"
            self._write_synthetic_ods(ods_path, table_name=DEFAULT_TABLE_NAME, rows=self._synthetic_rows())

            summary = run_calibration(ods_path=ods_path, output_dir=output_dir)

            source_values_path = output_dir / SOURCE_VALUES_FILE_NAME
            summary_path = output_dir / SUMMARY_FILE_NAME
            self.assertTrue(source_values_path.exists())
            self.assertTrue(summary_path.exists())
            loaded_summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(
            loaded_summary["selectedConfigValues"],
            {
                TENANCY_LENGTH_MIN_KEY: 6,
                TENANCY_LENGTH_MAX_KEY: 18,
            },
        )
        self.assertEqual(loaded_summary["selectedConfigValues"], summary["selectedConfigValues"])

    def test_missing_explicit_ods_path_fails_fast(self) -> None:
        with self.assertRaises(FileNotFoundError):
            resolve_ods_path("missing-ehs-tenancy-length.ods")

    def test_missing_table_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ods_path = Path(tmp_dir) / "ehs.ods"
            self._write_synthetic_ods(ods_path, table_name="OTHER", rows=self._synthetic_rows())

            with self.assertRaisesRegex(ValueError, "Could not find table"):
                extract_tenancy_length_calibration(ods_path)

    def test_unexpected_percentage_fails_fast(self) -> None:
        rows = self._synthetic_rows()
        rows[13][1] = "24.7"

        with self.assertRaisesRegex(ValueError, "Unexpected percentage"):
            extract_observations_from_rows(rows)

    @unittest.skipUnless(
        any((Path(__file__).resolve().parents[3] / candidate).exists() for candidate in DEFAULT_ODS_CANDIDATES),
        "requires retained EHS ODS",
    )
    def test_default_cli_extracts_tenancy_lengths_from_retained_ods(self) -> None:
        result = self._run_script()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("TENANCY_LENGTH_MIN = 6", result.stdout)
        self.assertIn("TENANCY_LENGTH_MAX = 18", result.stdout)

    @staticmethod
    def _synthetic_rows() -> list[list[object]]:
        return [
            ["", "Annex Table 2.10: Length of initial tenancy agreement, by tenancy type, two-years analysis, 2022-24"],
            ["", "all private renters who have lived at the current address for less than 3 years"],
            ["", "assured shorthold", "other letting", "all tenancies"],
            ["", "", "thousands of households"],
            ["length of agreement"],
            ["6 months", "812", "90", "902"],
            ["12 months", "2,111", "251", "2,362"],
            ["18 months", "129", "48", "178"],
            ["other", "391", "382", "773"],
            ["total", "3,443", "771", "4,214"],
            ["", "", "percentages"],
            ["length of agreement"],
            ["6 months", "23.6", "11.6", "21.4"],
            ["12 months", "61.3", "32.5", "56.0"],
            ["18 months", "3.8", "6.3", "4.2"],
            ["other", "11.3", "49.6", "18.3"],
            ["total", "100.0", "100.0", "100.0"],
        ]

    @staticmethod
    def _write_synthetic_ods(ods_path: Path, *, table_name: str, rows: list[list[object]]) -> None:
        document = OpenDocumentSpreadsheet()
        table = Table(name=table_name)
        for row in rows:
            _add_ods_row(table, row)
        document.spreadsheet.addElement(table)
        document.save(str(ods_path))


if __name__ == "__main__":
    unittest.main()
