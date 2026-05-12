"""Tests for bulk 2024 validation refresh orchestration.

@author: Max Stoddard
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.python.helpers.common.abm_policy_sweep import default_maven_bin
from scripts.python.validation.model.validate_all_input_data_versions import (
    list_versions,
    parse_version_parts,
    resolve_versions,
    run_validation_campaign,
)
from scripts.python.validation.model.rescore_validation_summaries import rescore_summary_payload
from scripts.python.validation.model.validation_profiles import resolve_validation_profile


class TestValidationFrameworkBulk(unittest.TestCase):
    def test_version_sorting_supports_repeated_output_suffixes(self) -> None:
        unsorted_versions = ["v4.14oo", "v0oo", "v4.14", "v0", "v4.14o", "v0o"]

        self.assertEqual(parse_version_parts("v0oo"), [0, 2])
        self.assertEqual(parse_version_parts("v4.14oo"), [4, 14, 2])
        self.assertEqual(
            sorted(unsorted_versions, key=parse_version_parts),
            ["v0", "v0o", "v0oo", "v4.14", "v4.14o", "v4.14oo"],
        )

    def test_list_versions_discovers_repeated_output_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            input_data_dir = repo_root / "input-data-versions"
            input_data_dir.mkdir()
            for version in ["v0oo", "v0", "v0o", "v4.14oo", "v4.14o", "v4.14"]:
                version_dir = input_data_dir / version
                version_dir.mkdir()
                (version_dir / "config.properties").write_text("", encoding="utf-8")
            ignored_dir = input_data_dir / "v0ooo-draft"
            ignored_dir.mkdir()
            (ignored_dir / "config.properties").write_text("", encoding="utf-8")

            self.assertEqual(
                list_versions(repo_root),
                ["v0", "v0o", "v0oo", "v4.14", "v4.14o", "v4.14oo"],
            )
            self.assertEqual(
                resolve_versions(repo_root, "v4.14oo,v0oo,v0o"),
                ["v0o", "v0oo", "v4.14oo"],
            )

    def test_run_validation_campaign_requires_positive_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            with self.assertRaisesRegex(ValueError, "workers must be positive"):
                run_validation_campaign(
                    repo_root=repo_root,
                    versions=["v-test"],
                    seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                    workers=0,
                    output_root=repo_root / "tmp" / "validation-history",
                )

    def test_run_validation_campaign_publishes_only_complete_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            output_root = repo_root / "tmp" / "validation-history"
            published_calls: list[tuple[str, tuple[int, ...], tuple[int, ...]]] = []

            def fake_run_validation_seed(*, version: str, seed: int, **_: object) -> dict[str, object]:
                if version == "v2.0" and seed == 8:
                    raise RuntimeError("synthetic failure")
                return {
                    "seed": seed,
                    "outputDir": f"/tmp/{version}/seed-{seed}",
                    "metrics": {"core_mortgageApprovals": 60.0},
                }

            def fake_publish_validation_results(
                *,
                version: str,
                seeds: list[int],
                run_results: list[dict[str, object]],
                **_: object,
            ) -> dict[str, object]:
                published_calls.append(
                    (
                        version,
                        tuple(seeds),
                        tuple(sorted(int(result["seed"]) for result in run_results)),
                    )
                )
                return {"version": version}

            with (
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.ensure_project_compiled"
                ) as compile_mock,
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.resolve_was_data_root",
                    return_value=repo_root,
                ),
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.run_validation_seed",
                    side_effect=fake_run_validation_seed,
                ),
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.publish_validation_results",
                    side_effect=fake_publish_validation_results,
                ),
            ):
                published_versions, failures = run_validation_campaign(
                    repo_root=repo_root,
                    versions=["v1.0", "v2.0"],
                    seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                    workers=3,
                    output_root=output_root,
                )

            compile_mock.assert_called_once_with(repo_root, maven_bin=default_maven_bin(repo_root))
            self.assertEqual(published_versions, ["v1.0"])
            self.assertEqual(
                published_calls,
                [("v1.0", (1, 2, 3, 4, 5, 6, 7, 8), (1, 2, 3, 4, 5, 6, 7, 8))],
            )
            self.assertEqual(len(failures), 2)
            self.assertTrue(any("v2.0 seed=8: synthetic failure" in failure for failure in failures))
            self.assertTrue(
                any(
                    "v2.0: tracked publication skipped because not all seeds finished successfully" in failure
                    for failure in failures
                )
            )

    def test_run_validation_campaign_passes_tracked_2024_profile_for_all_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            output_root = repo_root / "tmp" / "validation-history"
            observed_profiles: dict[str, set[tuple[int, str]]] = {}

            def fake_run_validation_seed(
                *,
                version: str,
                seed: int,
                validation_profile,
                **_: object,
            ) -> dict[str, object]:
                observed_profiles.setdefault(version, set()).add(
                    (validation_profile.validation_target_year, validation_profile.was_dataset)
                )
                return {
                    "seed": seed,
                    "outputDir": f"/tmp/{version}/seed-{seed}",
                    "metrics": {"core_mortgageApprovals": 60.0},
                }

            with (
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.ensure_project_compiled"
                ),
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.resolve_was_data_root",
                    return_value=repo_root,
                ),
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.run_validation_seed",
                    side_effect=fake_run_validation_seed,
                ),
                patch(
                    "scripts.python.validation.model.validate_all_input_data_versions.publish_validation_results",
                    side_effect=lambda *, version, **_: {"version": version},
                ),
            ):
                published_versions, failures = run_validation_campaign(
                    repo_root=repo_root,
                    versions=["v0", "v1.0"],
                    seeds=[1],
                    workers=2,
                    output_root=output_root,
                )

            self.assertEqual(published_versions, ["v0", "v1.0"])
            self.assertEqual(failures, [])
            self.assertEqual(observed_profiles["v0"], {(2024, "R8")})
            self.assertEqual(observed_profiles["v1.0"], {(2024, "R8")})

    def test_rescore_summary_payload_upgrades_cached_summary_without_seed_outputs(self) -> None:
        summary = {
            "schemaVersion": 3,
            "version": "v-test",
            "validationTargetYear": 2024,
            "generatedAt": "2026-05-01T00:00:00Z",
            "seeds": [1, 2, 3, 4, 5, 6, 7, 8],
            "window": {"startIndex": 200, "endIndex": 2000},
            "overallCompositeLoss": 9.0,
            "metrics": [
                {
                    "metricId": "core_advancesToBTL",
                    "label": "Advances to BTL",
                    "requirement": "required",
                    "units": "count/month",
                    "sourceLabel": "source",
                    "targetBand": {"lower": 4.396, "upper": 5.947},
                    "seedMean": 17.45106215277778,
                    "p25": 17.17581777777778,
                    "p75": 17.730475555555557,
                    "insideRate": 0.0,
                    "sourceValue": 5.17125,
                    "metricLoss": 9.0,
                    "metricWeight": 1.0,
                    "status": "fail",
                }
            ],
        }

        rescored = rescore_summary_payload(summary=summary, validation_profile=resolve_validation_profile("v-test"))
        metric = rescored["metrics"][0]

        self.assertEqual(rescored["schemaVersion"], 4)
        self.assertEqual(metric["lossFamily"], "positive_level")
        self.assertAlmostEqual(metric["metricLoss"], 1.5844592470279106)
        self.assertAlmostEqual(rescored["overallCompositeLoss"], metric["metricLoss"])


if __name__ == "__main__":
    unittest.main()
