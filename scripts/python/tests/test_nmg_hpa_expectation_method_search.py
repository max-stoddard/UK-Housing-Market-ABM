from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from scripts.python.experiments.nmg.nmg_hpa_expectation_method_search import (
    LEGACY_MODE,
    PRODUCTION_FIT_YEARS,
    PRODUCTION_MODE,
    build_arg_parser,
    main,
    run_method_search,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PRIVATE_PRODUCTION_PATHS = [
    REPO_ROOT / "private-datasets/nmg/nmg-2015.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2016.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2017.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2018.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2019.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2020.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2021.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2022.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2023.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2024.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2025-pt1.csv",
    REPO_ROOT / "private-datasets/nmg/nmg-2025-pt2.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2011.csv",
    REPO_ROOT / "private-datasets/ppd/pp.2012.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2018.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2019.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2020.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2021.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2022.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2023.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2024.csv",
    REPO_ROOT / "private-datasets/ppd/pp-2025.csv",
    REPO_ROOT / "private-datasets/nmg/boe-nmg-household-survey-data.xlsx",
]


class TestNmgHpaExpectationMethodSearch(unittest.TestCase):
    def _write_nmg_csv(self, filename: str, expectation_mean: float, *, include_subsid: bool = False, include_pid: bool = False) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / filename
        share_code_6 = max(min(expectation_mean / 0.035, 1.0), 0.0)
        fieldnames = ["we_factor", "boe39", "dhousing"]
        if include_subsid:
            fieldnames.append("subsid")
        if include_pid:
            fieldnames.append("pid")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            first = {"we_factor": f"{1.0 - share_code_6}", "boe39": "5", "dhousing": "1"}
            second = {"we_factor": f"{share_code_6}", "boe39": "6", "dhousing": "2"}
            if include_subsid:
                first["subsid"] = "1001"
                second["subsid"] = "1002"
            if include_pid:
                first["pid"] = "2001"
                second["pid"] = "2002"
            writer.writerow(first)
            writer.writerow(second)
        return path

    def _build_two_year_price_series(
        self,
        yearly_signals: dict[int, float],
        *,
        base_2011: float = 90.0,
        base_2012: float = 100.0,
    ) -> dict[int, float]:
        prices = {2011: base_2011, 2012: base_2012}
        for year in sorted(yearly_signals):
            if year - 2 not in prices:
                prices[year - 2] = base_2012
            prices[year] = prices[year - 2] * ((1.0 + yearly_signals[year]) ** 2)
        return prices

    def _write_ppd_csv(self, filename: str, category_price_series: dict[str, dict[int, float]]) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            for category_type, yearly_prices in category_price_series.items():
                for year, price in sorted(yearly_prices.items()):
                    for month in (10, 11, 12):
                        writer.writerow(
                            [
                                f"{{{category_type}-{year}-{month}}}",
                                f"{price}",
                                f"{year}-{month:02d}-15 00:00",
                                "AA1 1AA",
                                "T",
                                "N",
                                "F",
                                "1",
                                "",
                                "STREET",
                                "",
                                "TOWN",
                                "DIST",
                                "COUNTY",
                                category_type,
                                "A",
                            ]
                        )
        return path

    def _write_linkage_workbook(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        handle.close()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "2011-2025 PID-SUBSID"
        sheet.append(["respid", "wave", "subsidn", "pid"])
        for year in range(2018, 2025):
            sheet.append([1, f"Bank of England September {year} - Weighted", 1001 if year == 2018 else None, 2001])
            sheet.append([2, f"Bank of England September {year} - Weighted", 1002 if year == 2018 else None, 2002])
        workbook.save(handle.name)
        workbook.close()
        return Path(handle.name)

    def _build_production_fixture(self) -> tuple[dict[str, Path], list[Path], Path]:
        signal_values = {
            2018: 0.02,
            2019: 0.03,
            2020: 0.04,
            2021: 0.05,
            2022: 0.06,
            2023: 0.07,
            2024: 0.08,
            2025: 0.09,
        }
        category_a_prices = self._build_two_year_price_series(signal_values)
        category_b_prices = {year: 400.0 for year in category_a_prices}
        nmg_paths = {
            "2015": self._write_nmg_csv("nmg-2015.csv", 0.01),
            "2016": self._write_nmg_csv("nmg-2016.csv", 0.012),
            "2017": self._write_nmg_csv("nmg-2017.csv", 0.013),
            "2018": self._write_nmg_csv("nmg-2018.csv", 0.014, include_subsid=True),
            "2019": self._write_nmg_csv("nmg-2019.csv", (0.2 * signal_values[2019]) + 0.01, include_pid=True),
            "2020": self._write_nmg_csv("nmg-2020.csv", (0.2 * signal_values[2020]) + 0.01, include_pid=True),
            "2021": self._write_nmg_csv("nmg-2021.csv", (0.2 * signal_values[2021]) + 0.01, include_pid=True),
            "2022": self._write_nmg_csv("nmg-2022.csv", (0.2 * signal_values[2022]) + 0.01, include_pid=True),
            "2023": self._write_nmg_csv("nmg-2023.csv", (0.2 * signal_values[2023]) + 0.01, include_pid=True),
            "2024": self._write_nmg_csv("nmg-2024.csv", (0.2 * signal_values[2024]) + 0.01, include_pid=True),
            "2025-pt1": self._write_nmg_csv("nmg-2025-pt1.csv", 0.028, include_pid=True),
            "2025-pt2": self._write_nmg_csv("nmg-2025-pt2.csv", 0.019, include_pid=True),
        }
        ppd_paths = [
            self._write_ppd_csv("pp-2011.csv", {"A": {2011: category_a_prices[2011]}, "B": {2011: category_b_prices[2011]}}),
            self._write_ppd_csv("pp.2012.csv", {"A": {2012: category_a_prices[2012]}, "B": {2012: category_b_prices[2012]}}),
        ]
        for year in range(2018, 2026):
            ppd_paths.append(
                self._write_ppd_csv(
                    f"pp-{year}.csv",
                    {"A": {year: category_a_prices[year]}, "B": {year: category_b_prices[year]}},
                )
            )
        linkage_path = self._write_linkage_workbook()
        return nmg_paths, ppd_paths, linkage_path

    def _build_legacy_fixture(self) -> tuple[dict[str, Path], list[Path]]:
        expectations = {
            "2014": 0.036,
            "2015": 0.033,
            "2016": 0.011,
            "2017": 0.013,
            "2018": -0.0015,
        }
        nmg_paths = {
            wave_label: self._write_nmg_csv(f"nmg-{wave_label}.csv", expectation)
            for wave_label, expectation in expectations.items()
        }
        ppd_paths = [
            self._write_ppd_csv("pp-2011.csv", {"A": {2011: 100.0}, "B": {2011: 120.0}}),
            self._write_ppd_csv("pp.2012.csv", {"A": {2012: 110.0}, "B": {2012: 130.0}}),
            self._write_ppd_csv("pp-2018.csv", {"A": {2018: 180.0}, "B": {2018: 220.0}}),
        ]
        return nmg_paths, ppd_paths

    def _cleanup_paths(self, *paths: Path) -> None:
        for path in paths:
            if path.is_file():
                path.unlink(missing_ok=True)
            if path.parent.is_dir():
                try:
                    path.parent.rmdir()
                except OSError:
                    pass

    def test_parser_supports_legacy_and_production_modes(self) -> None:
        parser = build_arg_parser()
        production_args = parser.parse_args(
            [
                PRODUCTION_MODE,
                "--nmg-wave",
                "2018=nmg-2018.csv",
                "--nmg-wave",
                "2019=nmg-2019.csv",
                "--nmg-wave",
                "2020=nmg-2020.csv",
                "--nmg-wave",
                "2021=nmg-2021.csv",
                "--nmg-wave",
                "2022=nmg-2022.csv",
                "--nmg-wave",
                "2023=nmg-2023.csv",
                "--nmg-wave",
                "2024=nmg-2024.csv",
                "--ppd",
                "pp-2018.csv",
            ]
        )
        legacy_args = parser.parse_args(
            [
                LEGACY_MODE,
                "--nmg-wave",
                "2014=nmg-2014.csv",
                "--nmg-wave",
                "2015=nmg-2015.csv",
                "--nmg-wave",
                "2016=nmg-2016.csv",
                "--nmg-wave",
                "2017=nmg-2017.csv",
                "--nmg-wave",
                "2018=nmg-2018.csv",
                "--ppd",
                "pp-2011.csv",
            ]
        )

        self.assertEqual(production_args.fit_years, "2018,2019,2020,2021,2022,2023,2024")
        self.assertEqual(legacy_args.legacy_target_factor, 0.44)

    def test_run_method_search_production_default_surface_is_narrowed_to_defended_family(self) -> None:
        nmg_paths, ppd_paths, linkage_path = self._build_production_fixture()
        try:
            output = run_method_search(
                mode=PRODUCTION_MODE,
                nmg_wave_paths=nmg_paths,
                ppd_paths=ppd_paths,
                linkage_xlsx_path=linkage_path,
                fit_years=PRODUCTION_FIT_YEARS,
            )
        finally:
            self._cleanup_paths(*nmg_paths.values(), *ppd_paths, linkage_path)

        self.assertEqual(output.selected_result.candidate_spec.survey_target_spec.family_name, "national_cross_section")
        self.assertEqual({result.signal_method_name for result in output.ranked_results}, {"annual_mean_annualised"})
        self.assertEqual({result.category_key for result in output.ranked_results}, {"A"})
        self.assertEqual({result.candidate_spec.survey_target_spec.family_name for result in output.ranked_results}, {"national_cross_section"})
        self.assertEqual({result.regression_type for result in output.ranked_results}, {"ols", "huber"})
        self.assertEqual(output.fit_wave_labels, tuple(str(year) for year in PRODUCTION_FIT_YEARS))

    @unittest.skipUnless(all(path.exists() for path in PRIVATE_PRODUCTION_PATHS), "requires private production datasets")
    def test_real_data_production_cli_selects_midpoint_exact_huber_default(self) -> None:
        artifact_handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        artifact_handle.close()
        argv = [
            "nmg_hpa_expectation_method_search.py",
            PRODUCTION_MODE,
            "--artifact-output",
            artifact_handle.name,
        ]
        for wave_label in ("2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025-pt1", "2025-pt2"):
            argv.extend(["--nmg-wave", f"{wave_label}=private-datasets/nmg/nmg-{wave_label}.csv"])
        for ppd_name in ("pp-2011.csv", "pp.2012.csv", "pp-2018.csv", "pp-2019.csv", "pp-2020.csv", "pp-2021.csv", "pp-2022.csv", "pp-2023.csv", "pp-2024.csv", "pp-2025.csv"):
            argv.extend(["--ppd", f"private-datasets/ppd/{ppd_name}"])
        argv.extend(["--linkage-xlsx", "private-datasets/nmg/boe-nmg-household-survey-data.xlsx"])
        try:
            with patch.object(sys, "argv", argv):
                main()
            payload = json.loads(Path(artifact_handle.name).read_text(encoding="utf-8"))
        finally:
            Path(artifact_handle.name).unlink(missing_ok=True)

        selected = payload["selected_result"]
        spec = selected["candidate_spec"]
        self.assertEqual(
            spec["name"],
            "national_cross_section__midpoint_exact__annual_mean_annualised__A__huber__same_year_two_year_base",
        )
        self.assertAlmostEqual(selected["factor"], 0.2887897073, places=10)
        self.assertAlmostEqual(selected["const"], -0.0059593352, places=10)

    def test_run_method_search_legacy_reports_gap_for_missing_pre_2018_ppd_years(self) -> None:
        nmg_paths, ppd_paths = self._build_legacy_fixture()
        try:
            output = run_method_search(
                mode=LEGACY_MODE,
                nmg_wave_paths=nmg_paths,
                ppd_paths=ppd_paths,
            )
        finally:
            self._cleanup_paths(*nmg_paths.values(), *ppd_paths)

        self.assertTrue(output.gap_report)
        self.assertIn("2013, 2014, 2015, 2016, 2017", output.gap_report[0])
        self.assertIsNotNone(output.selected_result.legacy_distance)

    def test_production_cli_writes_artifact(self) -> None:
        nmg_paths, ppd_paths, linkage_path = self._build_production_fixture()
        artifact_handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        artifact_handle.close()
        argv = [
            "nmg_hpa_expectation_method_search.py",
            PRODUCTION_MODE,
        ]
        for wave_label, path in nmg_paths.items():
            argv.extend(["--nmg-wave", f"{wave_label}={path}"])
        for path in ppd_paths:
            argv.extend(["--ppd", str(path)])
        argv.extend(["--linkage-xlsx", str(linkage_path), "--artifact-output", artifact_handle.name])
        try:
            with patch.object(sys, "argv", argv):
                main()
            payload = json.loads(Path(artifact_handle.name).read_text(encoding="utf-8"))
        finally:
            self._cleanup_paths(*nmg_paths.values(), *ppd_paths, linkage_path, Path(artifact_handle.name))

        self.assertEqual(payload["mode"], PRODUCTION_MODE)
        self.assertIn("selected_result", payload)
        self.assertEqual(payload["fit_wave_labels"], [str(year) for year in PRODUCTION_FIT_YEARS])

    def test_legacy_cli_writes_artifact(self) -> None:
        nmg_paths, ppd_paths = self._build_legacy_fixture()
        artifact_handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        artifact_handle.close()
        argv = [
            "nmg_hpa_expectation_method_search.py",
            LEGACY_MODE,
        ]
        for wave_label, path in nmg_paths.items():
            argv.extend(["--nmg-wave", f"{wave_label}={path}"])
        for path in ppd_paths:
            argv.extend(["--ppd", str(path)])
        argv.extend(["--artifact-output", artifact_handle.name])
        try:
            with patch.object(sys, "argv", argv):
                main()
            payload = json.loads(Path(artifact_handle.name).read_text(encoding="utf-8"))
        finally:
            self._cleanup_paths(*nmg_paths.values(), *ppd_paths, Path(artifact_handle.name))

        self.assertEqual(payload["mode"], LEGACY_MODE)
        self.assertTrue(payload["gap_report"])


if __name__ == "__main__":
    unittest.main()
