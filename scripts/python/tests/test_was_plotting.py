"""Tests for WAS validation plotting helpers.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

import matplotlib.pyplot as plt

from scripts.python.helpers.was.plotting import (
    apply_axis_grid,
    compact_currency_log_ticks,
    format_compact_currency_value,
)


class TestWasPlottingHelpers(unittest.TestCase):
    def test_compact_currency_formatter_uses_pounds_and_half_decade_labels(self) -> None:
        cases = {
            500.0: "£500",
            1_000.0: "£1k",
            5_000.0: "£5k",
            10_000.0: "£10k",
            50_000.0: "£50k",
            100_000.0: "£100k",
            500_000.0: "£500k",
            1_000_000.0: "£1m",
            5_000_000.0: "£5m",
            10_000_000.0: "£10m",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(format_compact_currency_value(value), expected)

    def test_compact_currency_log_ticks_include_half_decades_in_range(self) -> None:
        self.assertEqual(
            compact_currency_log_ticks(500.0, 10_000_000.0),
            [
                500.0,
                1_000.0,
                5_000.0,
                10_000.0,
                50_000.0,
                100_000.0,
                500_000.0,
                1_000_000.0,
                5_000_000.0,
                10_000_000.0,
            ],
        )

    def test_compact_currency_log_ticks_can_keep_major_decades_only(self) -> None:
        self.assertEqual(
            compact_currency_log_ticks(
                500.0,
                10_000_000.0,
                include_half_decades=False,
            ),
            [
                1_000.0,
                10_000.0,
                100_000.0,
                1_000_000.0,
                10_000_000.0,
            ],
        )

    def test_apply_axis_grid_can_enable_major_and_minor_gridlines(self) -> None:
        figure, axes = plt.subplots()
        try:
            axes.set_xscale("log")
            axes.set_xlim(1_000.0, 10_000_000.0)
            apply_axis_grid(
                axes,
                axis="x",
                which="both",
                major_alpha=0.35,
                minor_alpha=0.18,
            )
            figure.canvas.draw()

            self.assertTrue(any(line.get_visible() for line in axes.xaxis.get_gridlines()))
            self.assertTrue(
                any(tick.gridline.get_visible() for tick in axes.xaxis.get_minor_ticks())
            )
        finally:
            plt.close(figure)


if __name__ == "__main__":
    unittest.main()
