"""Tests for bulk 2024 validation refresh orchestration.

@author: Max Stoddard
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.python.validation.model.validate_all_input_data_versions import run_validation_campaign


class TestValidationFrameworkBulk(unittest.TestCase):
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

            compile_mock.assert_called_once_with(repo_root, maven_bin="mvn")
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


if __name__ == "__main__":
    unittest.main()
