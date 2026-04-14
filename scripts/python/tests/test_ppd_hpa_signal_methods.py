from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.python.helpers.ppd.hpa_signal_methods import (
    PpdSaleRow,
    build_hpa_signal,
    build_yearly_hpa_signals,
    load_ppd_rows,
    resolve_base_year,
)


class TestPpdHpaSignalMethods(unittest.TestCase):
    def _write_ppd_csv(self, rows: list[list[object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w",
            suffix=".csv",
            delete=False,
            newline="",
            encoding="utf-8",
        )
        with handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
        return Path(handle.name)

    def test_load_ppd_rows_parses_years_and_months_from_csv(self) -> None:
        csv_path = self._write_ppd_csv(
            [
                ["{A}", "100000", "2012-02-01 00:00", "AA1 1AA", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"],
                ["{B}", "121000", "2014-11-15 00:00", "AA1 1AB", "T", "N", "F", "2", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"],
            ]
        )
        try:
            rows, stats = load_ppd_rows([csv_path])
        finally:
            csv_path.unlink(missing_ok=True)

        self.assertEqual(stats.total_rows, 2)
        self.assertEqual(stats.rows_loaded, 2)
        self.assertEqual(rows[0].transfer_year, 2012)
        self.assertEqual(rows[0].transfer_month, 2)
        self.assertEqual(rows[1].transfer_year, 2014)
        self.assertEqual(rows[1].transfer_month, 11)

    def test_load_ppd_rows_can_filter_to_category_a_only(self) -> None:
        csv_path = self._write_ppd_csv(
            [
                ["{A}", "100000", "2020-10-15 00:00", "AA1 1AA", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"],
                ["{B}", "125000", "2020-10-15 00:00", "AA1 1AB", "T", "N", "F", "2", "", "STREET", "", "TOWN", "DIST", "COUNTY", "B", "A"],
            ]
        )
        try:
            rows, stats = load_ppd_rows([csv_path], category_types={"A"})
        finally:
            csv_path.unlink(missing_ok=True)

        self.assertEqual(len(rows), 1)
        self.assertEqual(stats.rows_loaded, 1)
        self.assertEqual(rows[0].transfer_year, 2020)
        self.assertEqual(rows[0].transfer_month, 10)

    def test_annual_mean_annualised_signal_uses_anchor_gap_years(self) -> None:
        rows = [
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=1),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=1),
        ]

        signal = build_hpa_signal(
            rows,
            anchor_year=2014,
            base_year=2012,
            method_name="annual_mean_annualised",
        )

        self.assertAlmostEqual(signal.value, 0.10, places=12)
        self.assertEqual(signal.diagnostics["anchor_year"], 2014)
        self.assertEqual(signal.diagnostics["base_year"], 2012)

    def test_annual_mean_cumulative_signal_uses_ratio_minus_one(self) -> None:
        rows = [
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=1),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=1),
        ]

        signal = build_hpa_signal(
            rows,
            anchor_year=2014,
            base_year=2012,
            method_name="annual_mean_cumulative",
        )

        self.assertAlmostEqual(signal.value, 0.21, places=12)

    def test_java_like_signal_uses_last_three_months_of_anchor_year(self) -> None:
        rows = [
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=10),
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=11),
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=12),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=10),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=11),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=12),
        ]

        signal = build_hpa_signal(
            rows,
            anchor_year=2014,
            base_year=2012,
            method_name="java_like_annualised",
        )

        self.assertAlmostEqual(signal.value, 0.10, places=12)
        self.assertEqual(signal.diagnostics["months_used_recent"], [10, 11, 12])
        self.assertEqual(signal.diagnostics["months_used_base"], [10, 11, 12])

    def test_java_like_signal_requires_all_recent_and_base_months(self) -> None:
        rows = [
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=10),
            PpdSaleRow(price=100.0, transfer_year=2012, transfer_month=11),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=10),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=11),
            PpdSaleRow(price=121.0, transfer_year=2014, transfer_month=12),
        ]

        with self.assertRaisesRegex(ValueError, "requires data for months"):
            build_hpa_signal(
                rows,
                anchor_year=2014,
                base_year=2012,
                method_name="java_like_annualised",
            )

    def test_resolve_base_year_prefers_two_year_gap_and_falls_back_to_nearest_prior(self) -> None:
        available_years = {2011, 2012, 2018, 2022, 2023, 2024, 2025}

        self.assertEqual(resolve_base_year(available_years, anchor_year=2024), 2022)
        self.assertEqual(resolve_base_year(available_years, anchor_year=2018), 2012)
        self.assertEqual(resolve_base_year(available_years, anchor_year=2012), 2011)

    def test_build_hpa_signal_accepts_same_year_anchor_with_two_year_base(self) -> None:
        rows = [
            PpdSaleRow(price=100.0, transfer_year=2018, transfer_month=1),
            PpdSaleRow(price=121.0, transfer_year=2020, transfer_month=1),
        ]

        signal = build_hpa_signal(
            rows,
            anchor_year=2020,
            base_year=2018,
            method_name="annual_mean_annualised",
        )

        self.assertEqual(signal.anchor_year, 2020)
        self.assertEqual(signal.base_year, 2018)

    def test_build_yearly_hpa_signals_uses_two_year_base_for_each_anchor(self) -> None:
        rows = [
            PpdSaleRow(price=90.0, transfer_year=2018, transfer_month=1),
            PpdSaleRow(price=100.0, transfer_year=2019, transfer_month=1),
            PpdSaleRow(price=121.0, transfer_year=2020, transfer_month=1),
            PpdSaleRow(price=144.0, transfer_year=2021, transfer_month=1),
        ]

        signals = build_yearly_hpa_signals(
            rows,
            anchor_years=[2020, 2021],
            method_name="annual_mean_annualised",
        )

        self.assertEqual(signals[2020].base_year, 2018)
        self.assertEqual(signals[2021].base_year, 2019)

    def test_build_yearly_hpa_signals_ignores_category_b_rows_when_category_a_filter_is_active(self) -> None:
        csv_path = self._write_ppd_csv(
            [
                ["{A-2018}", "100", "2018-10-15 00:00", "AA1 1AA", "T", "N", "F", "1", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"],
                ["{B-2018}", "400", "2018-10-15 00:00", "AA1 1AB", "T", "N", "F", "2", "", "STREET", "", "TOWN", "DIST", "COUNTY", "B", "A"],
                ["{A-2020}", "121", "2020-10-15 00:00", "AA1 1AC", "T", "N", "F", "3", "", "STREET", "", "TOWN", "DIST", "COUNTY", "A", "A"],
                ["{B-2020}", "324", "2020-10-15 00:00", "AA1 1AD", "T", "N", "F", "4", "", "STREET", "", "TOWN", "DIST", "COUNTY", "B", "A"],
            ]
        )
        try:
            rows, _stats = load_ppd_rows([csv_path], category_types={"A"})
        finally:
            csv_path.unlink(missing_ok=True)

        signals = build_yearly_hpa_signals(
            rows,
            anchor_years=[2020],
            method_name="annual_mean_annualised",
        )

        self.assertEqual(signals[2020].anchor_year, 2020)
        self.assertAlmostEqual(signals[2020].value, 0.10, places=12)


if __name__ == "__main__":
    unittest.main()
