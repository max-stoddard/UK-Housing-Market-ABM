from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from scripts.python.helpers.nmg.hpa_expectation import load_nmg_wave_csv
from scripts.python.helpers.nmg.linkage import (
    build_matched_panel_row_indices,
    load_pid_subsid_linkage,
    normalize_linkage_wave_label,
)


class TestNmgLinkage(unittest.TestCase):
    def _write_nmg_csv(self, filename: str, rows: list[dict[str, object]]) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _write_linkage_workbook(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        handle.close()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "2011-2025 PID-SUBSID"
        sheet.append(["respid", "wave", "subsidn", "pid"])
        sheet.append([1, "Bank of England September 2018 - Weighted", 1001, 2001])
        sheet.append([2, "Bank of England September 2018 - Weighted", 1002, 2002])
        sheet.append([1, "Bank of England September 2019 - Weighted", None, 2001])
        sheet.append([2, "Bank of England September 2019 - Weighted", None, 2002])
        workbook.save(handle.name)
        workbook.close()
        return Path(handle.name)

    def test_normalize_linkage_wave_label_maps_2025_splits(self) -> None:
        self.assertEqual(normalize_linkage_wave_label("Bank of England March 2025 - Weighted"), "2025-pt1")
        self.assertEqual(normalize_linkage_wave_label("Bank of England September 2025 - Weighted"), "2025-pt2")

    def test_load_pid_subsid_linkage_and_build_matched_panel_rows(self) -> None:
        linkage_path = self._write_linkage_workbook()
        wave_2018_path = self._write_nmg_csv(
            "nmg-2018.csv",
            [
                {"we_factor": "1.0", "subsid": "1001", "boe39": "6"},
                {"we_factor": "1.0", "subsid": "1002", "boe39": "7"},
                {"we_factor": "1.0", "subsid": "9999", "boe39": "5"},
            ],
        )
        wave_2019_path = self._write_nmg_csv(
            "nmg-2019.csv",
            [
                {"we_factor": "1.0", "pid": "2001", "boe39": "6"},
                {"we_factor": "1.0", "pid": "2002", "boe39": "7"},
                {"we_factor": "1.0", "pid": "8888", "boe39": "5"},
            ],
        )
        try:
            linkage = load_pid_subsid_linkage(linkage_path)
            waves = {
                "2018": load_nmg_wave_csv(wave_2018_path),
                "2019": load_nmg_wave_csv(wave_2019_path),
            }
            matched = build_matched_panel_row_indices(
                waves,
                required_wave_labels=("2018", "2019"),
                linkage=linkage,
            )
        finally:
            linkage_path.unlink(missing_ok=True)
            wave_2018_path.unlink(missing_ok=True)
            wave_2018_path.parent.rmdir()
            wave_2019_path.unlink(missing_ok=True)
            wave_2019_path.parent.rmdir()

        self.assertEqual(matched["2018"], {0, 1})
        self.assertEqual(matched["2019"], {0, 1})


if __name__ == "__main__":
    unittest.main()
