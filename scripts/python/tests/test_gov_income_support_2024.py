from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.python.calibration.official.gov_income_support_2024 import (
    GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY,
    SOURCE_VALUES_FILE_NAME,
    SUMMARY_FILE_NAME,
    build_arg_parser,
    extract_income_support,
    extract_weekly_rate,
    run_calibration,
)


class TestGovIncomeSupport2024(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.module_name = "scripts.python.calibration.official.gov_income_support_2024"

    def test_parser_defaults(self) -> None:
        args = build_arg_parser().parse_args([])

        self.assertIsNone(args.source_html)
        self.assertIsNone(args.output_dir)

    def test_extract_weekly_rate_reads_income_support_couple_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_html = Path(tmp_dir) / "gov.html"
            source_html.write_text(self._synthetic_html(), encoding="utf-8")

            weekly_rate, header_row, target_row = extract_weekly_rate(source_html)

        self.assertEqual(weekly_rate, 142.25)
        self.assertEqual(header_row, ["Personal allowances", "Rates 2023/24", "Rates 2024/25"])
        self.assertEqual(target_row, ["Both 18 or over", "133.30", "142.25"])

    def test_extract_income_support_uses_annualized_calendar_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_html = Path(tmp_dir) / "gov.html"
            source_html.write_text(self._synthetic_html(), encoding="utf-8")

            observation = extract_income_support(source_html)

        self.assertEqual(observation.weekly_rate, 142.25)
        self.assertEqual(observation.annual_equivalent, 7397.0)
        self.assertAlmostEqual(observation.monthly_equivalent, 142.25 * 52 / 12)
        self.assertEqual(observation.selected_config_value, 616.4166666667)

    def test_run_calibration_writes_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            source_html = temp_root / "gov.html"
            output_dir = temp_root / "output"
            source_html.write_text(self._synthetic_html(), encoding="utf-8")

            summary = run_calibration(source_html=source_html, output_dir=output_dir)

            source_values_path = output_dir / SOURCE_VALUES_FILE_NAME
            summary_path = output_dir / SUMMARY_FILE_NAME
            source_values_exists = source_values_path.exists()
            summary_exists = summary_path.exists()
            loaded_summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertTrue(source_values_exists)
        self.assertTrue(summary_exists)
        self.assertEqual(loaded_summary["selectedConfigValues"], summary["selectedConfigValues"])
        self.assertEqual(
            loaded_summary["selectedConfigValues"][GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY],
            616.4166666667,
        )
        self.assertEqual(
            loaded_summary["legacyComparison"]["four_week_month_value_from_2024_25_rate"],
            569.0,
        )

    def test_cli_writes_expected_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            source_html = temp_root / "gov.html"
            output_dir = temp_root / "output"
            source_html.write_text(self._synthetic_html(), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    self.module_name,
                    "--source-html",
                    str(source_html),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("GOVERNMENT_MONTHLY_INCOME_SUPPORT = 616.4166666667", result.stdout)

    @staticmethod
    def _synthetic_html() -> str:
        return """
        <html>
          <body>
            <h2 id="income-support">Income Support</h2>
            <table>
              <thead>
                <tr>
                  <th>Personal allowances</th>
                  <th>Rates 2023/24</th>
                  <th>Rates 2024/25</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Single under 25</td>
                  <td>67.20</td>
                  <td>71.70</td>
                </tr>
                <tr>
                  <td><strong>Couple</strong></td>
                  <td>&nbsp;</td>
                  <td>&nbsp;</td>
                </tr>
                <tr>
                  <td>Both 18 or over</td>
                  <td>133.30</td>
                  <td>142.25</td>
                </tr>
              </tbody>
            </table>
            <h2 id="jobseekers-allowance">Jobseeker's Allowance</h2>
          </body>
        </html>
        """


if __name__ == "__main__":
    unittest.main()
