from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.psd.psd_lti_hard_max_method_search import (
    LtiMethodResult,
    LtiMethodSpec,
    LtiSearchOutput,
)
from scripts.python.experiments.psd.psd_v48_lti_reproduction import (
    RESULTS_FILE_NAME,
    SUMMARY_FILE_NAME,
    build_summary_markdown,
    run_v48_lti_reproduction,
    write_results_csv,
    write_summary_markdown,
)


class TestPsdV48LtiReproduction(unittest.TestCase):
    def _build_search_output(self) -> LtiSearchOutput:
        return LtiSearchOutput(
            results=[
                LtiMethodResult(
                    method=LtiMethodSpec(
                        ftb_source="ftb_joint",
                        hm_source="hm_subtracted",
                        quantile=0.99,
                        open_top_upper=6.0,
                        interpolation="linear",
                    ),
                    ftb_estimate_raw=5.3862737034,
                    hm_estimate_raw=5.5926900167,
                    ftb_estimate_rounded=5.4,
                    hm_estimate_rounded=5.6,
                    distance_rounded=0.0,
                    distance_raw=0.0155514332,
                ),
                LtiMethodResult(
                    method=LtiMethodSpec(
                        ftb_source="ftb_joint",
                        hm_source="all_combined",
                        quantile=0.99,
                        open_top_upper=6.0,
                        interpolation="linear",
                    ),
                    ftb_estimate_raw=5.3862737034,
                    hm_estimate_raw=5.5798214286,
                    ftb_estimate_rounded=5.4,
                    hm_estimate_rounded=5.6,
                    distance_rounded=0.0,
                    distance_raw=0.02440463,
                ),
            ],
            target_ftb=5.4,
            target_hm=5.6,
        )

    def _build_output(self):
        search_output = self._build_search_output()
        from unittest.mock import patch

        with patch(
            "scripts.python.experiments.psd.psd_v48_lti_reproduction.run_lti_search",
            return_value=search_output,
        ):
            return run_v48_lti_reproduction(
                p3_csv=Path("private-datasets/psd/2005-2013/p3.csv"),
                p6_csv=Path("private-datasets/psd/2005-2013/p6.csv"),
                config_path=Path("input-data-versions/v4.8/config.properties"),
                target_year=2011,
                top_k=20,
                output_dir_display="tmp/recalibration-recalculation-summaries",
            )

    def test_wrapper_writes_expected_file_names_and_csv_schema(self) -> None:
        output = self._build_output()
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = write_results_csv(output, tmp_dir)
            summary_path = write_summary_markdown(output, tmp_dir)

            self.assertEqual(csv_path.name, RESULTS_FILE_NAME)
            self.assertEqual(summary_path.name, SUMMARY_FILE_NAME)
            self.assertTrue(csv_path.exists())
            self.assertTrue(summary_path.exists())

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows[0],
            [
                "rank",
                "is_default_method",
                "method_id",
                "target_ftb",
                "target_hm",
                "ftb_raw",
                "hm_raw",
                "ftb_rounded_1dp",
                "hm_rounded_1dp",
                "distance_rounded",
                "distance_raw",
            ],
        )
        self.assertEqual(rows[1][1], "yes")
        self.assertEqual(rows[2][1], "no")

    def test_summary_contains_sections_command_rounding_and_scope_note(self) -> None:
        output = self._build_output()
        summary = build_summary_markdown(output)

        self.assertIn("# PSD v4.8 LTI Reproduction Summary", summary)
        self.assertIn("## BANK_LTI_HARD_MAX_FTB", summary)
        self.assertIn("## BANK_LTI_HARD_MAX_HM", summary)
        self.assertIn(
            "`python3 -m scripts.python.experiments.psd.psd_v48_lti_reproduction",
            summary,
        )
        self.assertIn("- Raw estimate: `5.3862737034`", summary)
        self.assertIn("- Rounded 1dp estimate: `5.4`", summary)
        self.assertIn("- Pass against v4.8 target: `pass` (target `5.4`)", summary)
        self.assertIn("BANK_AFFORDABILITY_HARD_MAX", summary)
        self.assertIn("excluded by revised task requirements", summary)

    def test_wrapper_uses_default_method_and_1dp_pass_logic(self) -> None:
        output = self._build_output()

        self.assertEqual(output.default_result.method.ftb_source, "ftb_joint")
        self.assertEqual(output.default_result.method.hm_source, "hm_subtracted")
        self.assertEqual(output.default_result.method.quantile, 0.99)
        self.assertEqual(output.default_result.method.open_top_upper, 6.0)
        self.assertEqual(output.default_result.method.interpolation, "linear")
        self.assertTrue(output.ftb.passes_target)
        self.assertTrue(output.hm.passes_target)
        self.assertEqual(output.ftb.rounded_estimate, 5.4)
        self.assertEqual(output.hm.rounded_estimate, 5.6)


if __name__ == "__main__":
    unittest.main()
