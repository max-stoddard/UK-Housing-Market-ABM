#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the LTV-by-group debt-to-income sensitivity workflow.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.python.experiments.model.boe_policy_ltv_by_group import (
    BTL_GRID,
    FTB_GRID,
    HM_GRID,
    PLOT_FILE_NAMES,
    PLOT_INDICATOR_ID,
    build_arg_parser,
    build_ltv_sensitivity_stories,
    build_reproduce_command,
    main,
    write_aggregated_results_csv,
)
from scripts.python.helpers.common.abm_policy_sweep import (
    AggregateStat,
    AggregatedIndicator,
    AggregatedPoint,
    AggregatedStoryResults,
)


class TestBoePolicyLtvByGroup(unittest.TestCase):
    def test_cli_defaults_match_ltv_by_group_contract(self) -> None:
        args = build_arg_parser().parse_args([])

        self.assertEqual(args.versions, "v0,v4.1")
        self.assertEqual(args.seeds, "1,2,3,4")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.output_dir, "tmp/boe_policy_story_ltv_by_group")
        self.assertFalse(args.force_rerun)
        self.assertIsNone(args.maven_bin)

    def test_story_grids_are_centered_on_v41_defaults_and_aligned(self) -> None:
        stories = {story.story_id: story for story in build_ltv_sensitivity_stories()}
        expected = {
            "ftb_ltv_cap": (FTB_GRID, "CENTRAL_BANK_LTV_HARD_MAX_FTB", "BANK_LTV_HARD_MAX_FTB", "0.95"),
            "hm_ltv_cap": (HM_GRID, "CENTRAL_BANK_LTV_HARD_MAX_HM", "BANK_LTV_HARD_MAX_HM", "0.95"),
            "btl_ltv_cap": (BTL_GRID, "CENTRAL_BANK_LTV_HARD_MAX_BTL", "BANK_LTV_HARD_MAX_BTL", "0.85"),
        }

        for story_id, (grid, central_key, bank_key, baseline_label) in expected.items():
            story = stories[story_id]
            self.assertEqual(story.final_values, grid)
            self.assertEqual(story.screen_values, grid)
            self.assertEqual(story.primary_outputs, (PLOT_INDICATOR_ID,))
            self.assertEqual(story.secondary_outputs, ())
            self.assertEqual(story.figure_indicator_ids, (PLOT_INDICATOR_ID,))
            self.assertEqual(story.figure_headline_indicator_id, PLOT_INDICATOR_ID)

            points = story.build_points("final", aligned=True)
            self.assertEqual([point.label for point in points if point.is_baseline], [baseline_label])
            for point in points:
                self.assertEqual(point.updates[central_key], point.updates[bank_key])

    def test_build_reproduce_command_tracks_effective_defaults(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--output-dir",
                "tmp/boe_policy_story_ltv_by_group_test",
                "--versions",
                "v0,v4.1",
                "--seeds",
                "1,2,3,4",
                "--workers",
                "20",
            ]
        )

        self.assertEqual(
            build_reproduce_command(args),
            "python3 -m scripts.python.experiments.model.boe_policy_ltv_by_group \\\n"
            "  --output-dir tmp/boe_policy_story_ltv_by_group_test \\\n"
            "  --versions v0,v4.1 \\\n"
            "  --seeds 1,2,3,4 \\\n"
            "  --workers 20\n",
        )

    def test_write_aggregated_results_csv_captures_all_versions_points_and_indicator(self) -> None:
        stories = build_ltv_sensitivity_stories()
        aggregated_by_story_id = {
            story.story_id: self._build_synthetic_aggregated_results(
                story_id=story.story_id,
                x_values=story.final_values,
                baseline_value=story.baseline_value,
            )
            for story in stories
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "aggregated_results.csv"
            write_aggregated_results_csv(
                output_path,
                stories=stories,
                aggregated_by_story_id=aggregated_by_story_id,
                versions=("v0", "v4.1"),
            )

            with output_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 30)
        self.assertEqual({row["version"] for row in rows}, {"v0", "v4.1"})
        self.assertEqual({row["indicator_id"] for row in rows}, {PLOT_INDICATOR_ID})
        self.assertEqual({row["raw_n"] for row in rows}, {"4"})
        self.assertEqual({row["delta_n"] for row in rows}, {"4"})

        ftb_rows = [row for row in rows if row["story_id"] == "ftb_ltv_cap" and row["version"] == "v4.1"]
        self.assertEqual([row["point_label"] for row in ftb_rows], ["0.9", "0.925", "0.95", "0.975", "1"])
        self.assertEqual([row["is_baseline"] for row in ftb_rows], ["false", "false", "true", "false", "false"])

    def test_main_writes_expected_pngs_and_summary_files(self) -> None:
        stories = build_ltv_sensitivity_stories()
        synthetic = {
            story.story_id: self._build_synthetic_aggregated_results(
                story_id=story.story_id,
                x_values=story.final_values,
                baseline_value=story.baseline_value,
            )
            for story in stories
        }
        run_calls: list[dict[str, object]] = []

        def fake_run_story_sweep(**kwargs):
            run_calls.append(kwargs)
            story_id = kwargs["story_id"]
            return [], synthetic[story_id]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "boe_policy_story_ltv_by_group"
            argv = [
                "boe_policy_ltv_by_group.py",
                "--output-dir",
                str(output_dir),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch(
                "scripts.python.experiments.model.boe_policy_ltv_by_group.ensure_project_compiled"
            ), mock.patch(
                "scripts.python.experiments.model.boe_policy_ltv_by_group.run_story_sweep",
                side_effect=fake_run_story_sweep,
            ):
                main()

            for file_name in PLOT_FILE_NAMES.values():
                path = output_dir / file_name
                self.assertTrue(path.exists(), msg=f"missing plot {path}")
                self.assertGreater(path.stat().st_size, 0)

            self.assertTrue((output_dir / "aggregated_results.csv").exists())
            self.assertTrue((output_dir / "reproduce_command.txt").exists())

        self.assertEqual(len(run_calls), 3)
        self.assertTrue(all(call["workers"] == 20 for call in run_calls))
        self.assertTrue(all(call["indicator_ids"] == [PLOT_INDICATOR_ID] for call in run_calls))
        self.assertTrue(all(Path(call["output_root"]).name == "model_runs" for call in run_calls))

    def _build_synthetic_aggregated_results(
        self,
        *,
        story_id: str,
        x_values: tuple[float, ...],
        baseline_value: float,
    ) -> AggregatedStoryResults:
        versions = {}
        for version, multiplier in (("v0", 0.6), ("v4.1", 1.4)):
            points = []
            for index, x_value in enumerate(x_values):
                delta = (x_value - baseline_value) * 100.0 * multiplier
                label = f"{x_value:.3f}".rstrip("0").rstrip(".")
                points.append(
                    AggregatedPoint(
                        point_id=f"point_{index:02d}_{label.replace('.', 'p')}",
                        point_index=index,
                        label=label,
                        x_value=x_value,
                        updates={"SYNTHETIC_KEY": label},
                        is_baseline=abs(x_value - baseline_value) < 1e-9,
                        indicators={PLOT_INDICATOR_ID: self._indicator_bundle(85.0 + delta)},
                        delta_indicators={PLOT_INDICATOR_ID: self._indicator_bundle(delta)},
                    )
                )
            versions[version] = points
        return AggregatedStoryResults(
            stage_name="ltv_by_group",
            story_id=story_id,
            versions=versions,
        )

    def _indicator_bundle(self, mean_value: float) -> AggregatedIndicator:
        stat = AggregateStat(
            mean=mean_value,
            stdev=0.5,
            ci_low=mean_value - 0.25,
            ci_high=mean_value + 0.25,
            n=4,
        )
        return AggregatedIndicator(mean=stat, cv=None, annualised_trend=None, range=None)


if __name__ == "__main__":
    unittest.main()
