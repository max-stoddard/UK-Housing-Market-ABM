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

from scripts.python.calibration.official.ehs_hold_period_2024 import (
    DEFAULT_ODS_CANDIDATES,
    DEFAULT_ROW_LABEL,
    DEFAULT_TABLE_NAME,
    DEFAULT_YEAR,
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    build_arg_parser,
    extract_hold_period,
    extract_value_from_rows,
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


class TestEhsHoldPeriod2024(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.module_name = "scripts.python.calibration.official.ehs_hold_period_2024"
        cls.private_ods_paths = tuple((cls.repo_root / path).resolve() for path in DEFAULT_ODS_CANDIDATES)

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
        self.assertEqual(args.row_label, DEFAULT_ROW_LABEL)
        self.assertEqual(args.year, DEFAULT_YEAR)
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

    def test_extract_value_from_rows_reads_target_cell(self) -> None:
        rows = [
            ["", "Annex Table 3.6"],
            ["", "", "2010-11", "2011-12", "2023-24"],
            ["", "all owner occupiers", "16.7", "17.1", "17.2"],
        ]

        value = extract_value_from_rows(
            rows,
            row_label="all owner occupiers",
            year="2023-24",
        )

        self.assertEqual(value, 17.2)

    def test_extract_hold_period_reads_value_from_synthetic_ods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ods_path = Path(tmp_dir) / "ehs.ods"
            self._write_synthetic_ods(
                ods_path,
                table_name="AT3_6",
                rows=[
                    ["", "Annex Table 3.6"],
                    ["", "", "2010-11", "2011-12", "2023-24"],
                    ["", "all owner occupiers", "16.7", "17.1", "17.2"],
                ],
            )

            observation = extract_hold_period(ods_path)

        self.assertEqual(observation.config_value, 17.2)
        self.assertEqual(observation.table_name, "AT3_6")
        self.assertEqual(observation.row_label, "all owner occupiers")
        self.assertEqual(observation.year, "2023-24")

    def test_run_calibration_writes_source_values_and_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            ods_path = temp_root / "ehs.ods"
            output_dir = temp_root / "output"
            self._write_synthetic_ods(
                ods_path,
                table_name="AT3_6",
                rows=[
                    ["", "Annex Table 3.6"],
                    ["", "", "2010-11", "2011-12", "2023-24"],
                    ["", "all owner occupiers", "16.7", "17.1", "17.2"],
                ],
            )

            summary = run_calibration(ods_path=ods_path, output_dir=output_dir)

            source_values_path = output_dir / SOURCE_VALUES_FILE_NAME
            summary_path = output_dir / SUMMARY_FILE_NAME
            self.assertTrue(source_values_path.exists())
            self.assertTrue(summary_path.exists())
            loaded_summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded_summary["selectedConfigValues"], summary["selectedConfigValues"])

    def test_missing_explicit_ods_path_fails_fast(self) -> None:
        with self.assertRaises(FileNotFoundError):
            resolve_ods_path("missing-ehs-hold-period.ods")

    def test_missing_table_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ods_path = Path(tmp_dir) / "ehs.ods"
            self._write_synthetic_ods(
                ods_path,
                table_name="OTHER",
                rows=[
                    ["", "", "2023-24"],
                    ["", "all owner occupiers", "17.2"],
                ],
            )

            with self.assertRaisesRegex(ValueError, "Could not find table"):
                extract_hold_period(ods_path)

    def test_missing_row_label_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ods_path = Path(tmp_dir) / "ehs.ods"
            self._write_synthetic_ods(
                ods_path,
                table_name="AT3_6",
                rows=[
                    ["", "", "2023-24"],
                    ["", "private renters", "4.6"],
                ],
            )

            with self.assertRaisesRegex(ValueError, "Could not find row label"):
                extract_hold_period(ods_path)

    def test_missing_year_column_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ods_path = Path(tmp_dir) / "ehs.ods"
            self._write_synthetic_ods(
                ods_path,
                table_name="AT3_6",
                rows=[
                    ["", "", "2010-11", "2011-12"],
                    ["", "all owner occupiers", "16.7", "17.1"],
                ],
            )

            with self.assertRaisesRegex(ValueError, "Could not find column"):
                extract_hold_period(ods_path)

    @unittest.skipUnless(
        any(path.exists() for path in (Path(__file__).resolve().parents[3] / candidate for candidate in DEFAULT_ODS_CANDIDATES)),
        "requires private EHS ODS",
    )
    def test_default_cli_extracts_hold_period_from_private_ods(self) -> None:
        result = self._run_script()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("HOLD_PERIOD = 17.2", result.stdout)

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
