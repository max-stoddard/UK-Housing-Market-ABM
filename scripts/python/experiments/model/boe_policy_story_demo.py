#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screen, select, and visualise policy stories for the Bank of England demo.

Supports smoke-style screen-only comparisons and final dense sweeps.

Latest findings:
  - Refined dense rerun: `python3 -m scripts.python.experiments.model.boe_policy_story_demo --output-dir tmp/boe_policy_story_demo_v41_2 --reuse-output-dir tmp/boe_policy_story_demo_v41_2 --reuse-output-dir tmp/boe_policy_story_demo_v41 --story-ids affordability_cap,lti_flow_limit_bundle --versions v0,v4.1 --final-seeds 1,2,3,4,5,6 --workers 20`
  - Comparison: `v0` versus `v4.1`, six seeds, affordability dense grid `0.26,0.28,0.30,0.32,0.34,0.36,0.38` with baseline `0.32`, reusing `156` exact-match cached final runs from `tmp/boe_policy_story_demo_v41_2` and `tmp/boe_policy_story_demo_v41`.
  - Story 1 (`affordability_cap`): tightening from `0.32` to `0.26` moved mortgage debt-to-income by `-13.471` in `v4.1` versus `-4.711` in `v0`; Story 2 (`lti_flow_limit_bundle`): loosening from `0.15` to `0.30` moved mortgage debt-to-income by `+7.537` versus `+1.227`.
  - Interpretation: the refined affordability sweep keeps the clearer `.32` baseline while trimming to evenly spaced presentation points; only the new `0.26` affordability runs were executed fresh and the shared high-LTI flow story remained unchanged.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from scripts.python.experiments.model.policy_story_catalog import (
    BindingEvaluation,
    PolicyStoryDefinition,
    build_story_method_audits,
    eligible_stories_by_binding,
    get_policy_story_catalog,
    story_binding_details,
    story_lookup,
)
from scripts.python.experiments.model.policy_story_evidence import (
    get_story_evidence_reviews,
    recommend_story,
)
from scripts.python.experiments.model.policy_story_reporting import (
    plot_story_figure,
    plot_story_split_figures,
    write_binding_validation_csv,
    write_binding_validation_json,
    write_evidence_review_markdown,
    write_method_audit_csv,
    write_method_audit_json,
    write_method_audit_markdown,
    write_recommendation_markdown,
    write_report_markdown,
    write_screen_summary_csv,
    write_screen_summary_json,
    write_selected_stories_json,
    write_sources_markdown,
    write_story_csv,
)
from scripts.python.experiments.model.policy_story_scoring import (
    build_selection_results,
    canonical_selection_policy,
    score_story_screening,
    validate_selection_policy,
)
from scripts.python.helpers.common.abm_policy_sweep import (
    AggregatedStoryResults,
    ensure_project_compiled,
    resolve_maven_bin,
    run_story_sweep,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir

METHODOLOGY_NOTE = (
    "Bank-coupled stories are run as aligned bank + central-bank sweeps so no tested central-bank point is masked "
    "by a tighter `BANK_*` threshold; structurally weak stories are audited but excluded from shortlist selection."
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Policy-story sweep orchestrator for the BoE demo.",
    )
    parser.add_argument(
        "--versions",
        default="v0,v4.1",
        help="Comma-separated input-data versions to compare (default: v0,v4.1).",
    )
    parser.add_argument(
        "--screen-seeds",
        default="1,2,3,4",
        help="Comma-separated seeds used for story screening (default: 1,2,3,4).",
    )
    parser.add_argument(
        "--final-seeds",
        default="1,2,3,4,5,6",
        help="Comma-separated seeds used for final dense sweeps (default: 1,2,3,4,5,6).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=20,
        help="Maximum parallel model runs (default: 20).",
    )
    parser.add_argument(
        "--output-dir",
        default="tmp/boe_policy_story_demo_v41",
        help="Output directory for artifacts and temporary runs.",
    )
    parser.add_argument(
        "--reuse-output-dir",
        action="append",
        default=[],
        help="Optional prior output directory whose dense final caches should be copied into this run before rerunning. Repeat to set fallback cache sources.",
    )
    parser.add_argument(
        "--story-ids",
        default=None,
        help="Optional comma-separated story ids to force, skipping automatic selection.",
    )
    parser.add_argument(
        "--screen-only",
        action="store_true",
        help="Run the screening stage only and stop after ranking candidates.",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore cached run_metrics.json files and rerun model outputs.",
    )
    parser.add_argument(
        "--maven-bin",
        default=None,
        help="Maven executable override (default: repo-local ./mvnw).",
    )
    parser.add_argument(
        "--selection-policy",
        default="ranking_only",
        help="Story-selection policy: demo_legacy, ranking_only, or compare_both.",
    )
    parser.add_argument(
        "--smoke-selection",
        default="tmp/boe_policy_story_demo_v41_smoke/selected_stories.json",
        help=(
            "Optional path to a prior smoke `selected_stories.json`; when used for a dense run, "
            "the canonical shortlist is loaded from this file and screening is skipped."
        ),
    )
    return parser


def parse_csv_list(raw: str) -> list[str]:
    values = [token.strip() for token in raw.split(",") if token.strip()]
    if not values:
        raise SystemExit("Expected a non-empty comma-separated list.")
    return values


def parse_seed_list(raw: str) -> list[int]:
    values = [int(token) for token in parse_csv_list(raw)]
    if any(value <= 0 for value in values):
        raise SystemExit("Seeds must be positive integers.")
    return values


def validate_versions(raw_versions: list[str]) -> list[str]:
    """Validate the fixed baseline-plus-modern comparison contract."""

    if len(raw_versions) != 2:
        raise SystemExit(
            "This workflow requires exactly two versions: baseline `v0` and one modern snapshot."
        )
    if raw_versions[0] != "v0":
        raise SystemExit("This workflow requires `v0` as the first comparison version.")
    if raw_versions[1] == "v0":
        raise SystemExit(
            "The second comparison version must be a modern snapshot, not `v0`."
        )
    return raw_versions


def select_catalog_subset(
    all_stories: list[PolicyStoryDefinition],
    requested_story_ids: list[str] | None,
) -> list[PolicyStoryDefinition]:
    if requested_story_ids is None:
        return all_stories
    lookup = story_lookup(all_stories)
    missing = [story_id for story_id in requested_story_ids if story_id not in lookup]
    if missing:
        raise SystemExit(f"Unknown story ids: {missing}")
    return [lookup[story_id] for story_id in requested_story_ids]


def run_screening_stage(
    *,
    repo_root: Path,
    screen_root: Path,
    stories: list[PolicyStoryDefinition],
    versions: list[str],
    screen_seeds: list[int],
    workers: int,
    force_rerun: bool,
    maven_bin: str,
) -> tuple[list[tuple[PolicyStoryDefinition, AggregatedStoryResults]], list]:
    screening_outputs: list[tuple[PolicyStoryDefinition, AggregatedStoryResults]] = []
    scores = []
    for story in stories:
        _, aggregated = run_story_sweep(
            repo_root=repo_root,
            output_root=screen_root,
            stage_name="screen",
            story_id=story.story_id,
            versions=versions,
            seeds=screen_seeds,
            points=story.build_points("screen", aligned=True),
            indicator_ids=sorted(
                set((*story.primary_outputs, *story.secondary_outputs))
            ),
            workers=workers,
            force_rerun=force_rerun,
            maven_bin=maven_bin,
        )
        screening_outputs.append((story, aggregated))
        scores.append(score_story_screening(story, aggregated))
    return screening_outputs, scores


def run_final_stage(
    *,
    repo_root: Path,
    final_root: Path,
    stories: list[PolicyStoryDefinition],
    versions: list[str],
    final_seeds: list[int],
    workers: int,
    force_rerun: bool,
    maven_bin: str,
) -> dict[str, AggregatedStoryResults]:
    """Run or reuse the dense final sweeps for the selected stories."""

    final_aggregated: dict[str, AggregatedStoryResults] = {}
    for story in stories:
        _, aggregated = run_story_sweep(
            repo_root=repo_root,
            output_root=final_root,
            stage_name="final",
            story_id=story.story_id,
            versions=versions,
            seeds=final_seeds,
            points=story.build_points("final", aligned=True),
            indicator_ids=sorted(
                set((*story.primary_outputs, *story.secondary_outputs))
            ),
            workers=workers,
            force_rerun=force_rerun,
            maven_bin=maven_bin,
        )
        final_aggregated[story.story_id] = aggregated
    return final_aggregated


def clear_previous_story_artifacts(output_dir: Path) -> None:
    """Remove stale top-level story files before writing a new final selection."""

    for pattern in ("story_[0-9]*.csv", "story_[0-9]*.png"):
        for path in output_dir.glob(pattern):
            if path.is_file():
                path.unlink()


def build_binding_details(
    stories: list[PolicyStoryDefinition],
    *,
    repo_root: Path,
    versions: list[str],
) -> dict[str, dict[str, BindingEvaluation]]:
    """Build the per-story binding audit for the requested versions."""

    return {
        story.story_id: story_binding_details(
            story,
            repo_root=repo_root,
            versions=versions,
        )
        for story in stories
    }


def load_story_ids_from_smoke_selection(path: Path) -> list[str]:
    """Load the canonical shortlist from a prior smoke `selected_stories.json` file."""

    if not path.exists():
        raise SystemExit(f"Smoke selection file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical_policy = payload.get("canonical_policy")
    selected_stories = payload.get("selected_stories")
    selection_results = payload.get("selection_results")

    if isinstance(selected_stories, list) and selected_stories:
        story_ids = [item["story_id"] for item in selected_stories]
    elif isinstance(canonical_policy, str) and isinstance(selection_results, dict) and canonical_policy in selection_results:
        story_ids = [item["story_id"] for item in selection_results[canonical_policy]]
    else:
        raise SystemExit(f"Smoke selection file is missing a canonical shortlist: {path}")

    if not story_ids:
        raise SystemExit(f"Smoke selection file contained no story ids: {path}")
    return story_ids


def _paths_match(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)


def resolve_run_output_dir(
    output_dir: Path,
    reuse_output_dirs: list[Path],
) -> tuple[Path, bool]:
    """Return the directory to write into, using staging when needed."""

    if any(_paths_match(output_dir, reuse_output_dir) for reuse_output_dir in reuse_output_dirs):
        return output_dir.parent / f"{output_dir.name}__staging", True
    return output_dir, False


def finalize_output_dir(
    *,
    requested_output_dir: Path,
    runtime_output_dir: Path,
    used_staging: bool,
) -> None:
    """Replace the requested output with the staged output after a successful run."""

    if not used_staging:
        return
    if requested_output_dir.exists():
        shutil.rmtree(requested_output_dir)
    shutil.move(str(runtime_output_dir), str(requested_output_dir))


def _x_value_key(value: float) -> str:
    """Normalize a sweep x-value for exact cache matching."""

    return format_float(float(value))


def _resolve_cached_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else repo_root / path


def _build_reuse_metrics_lookup(
    *,
    repo_root: Path,
    reuse_output_dirs: list[Path],
    stories: list[PolicyStoryDefinition],
    versions: list[str],
    final_seeds: list[int],
) -> dict[tuple[str, str, int, str], list[Path]]:
    """Index reusable dense final-run metrics by story/version/seed/x-value."""

    lookup: dict[tuple[str, str, int, str], list[Path]] = {}
    for reuse_output_dir in reuse_output_dirs:
        if not reuse_output_dir.exists():
            continue
        for story in stories:
            for version in versions:
                for seed in final_seeds:
                    seed_dir = (
                        reuse_output_dir
                        / "final"
                        / story.story_id
                        / "runs"
                        / "final"
                        / version
                        / f"seed-{seed}"
                    )
                    if not seed_dir.exists():
                        continue
                    for metrics_path in seed_dir.glob("point_*/run_metrics.json"):
                        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                        key = (story.story_id, version, seed, _x_value_key(payload["x_value"]))
                        lookup.setdefault(key, []).append(metrics_path)
    return lookup


def _seed_reused_final_run(
    *,
    repo_root: Path,
    final_root: Path,
    source_metrics_path: Path,
    story: PolicyStoryDefinition,
    version: str,
    seed: int,
    point: object,
) -> bool:
    """Copy one reusable run into the new dense final-run cache tree."""

    payload = json.loads(source_metrics_path.read_text(encoding="utf-8"))
    source_run_dir = _resolve_cached_path(repo_root, payload["output_dir"])
    if not source_run_dir.exists():
        return False

    source_config_path = _resolve_cached_path(repo_root, payload["config_path"])
    target_story_root = final_root / story.story_id
    target_run_dir = (
        target_story_root
        / "runs"
        / "final"
        / version
        / f"seed-{seed}"
        / point.point_id
    )
    target_config_path = (
        target_story_root
        / "configs"
        / "final"
        / version
        / f"{point.point_id}-seed-{seed}.properties"
    )
    if target_run_dir.exists():
        return False

    target_run_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_run_dir, target_run_dir)
    if source_config_path.exists():
        target_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_config_path, target_config_path)

    payload["point_id"] = point.point_id
    payload["point_index"] = point.point_index
    payload["point_label"] = point.label
    payload["x_value"] = point.x_value
    payload["updates"] = dict(point.updates)
    payload["is_baseline"] = point.is_baseline
    payload["output_dir"] = str(target_run_dir)
    payload["config_path"] = str(target_config_path)
    payload["cached"] = True
    (target_run_dir / "run_metrics.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def seed_final_run_caches_from_previous_output(
    *,
    repo_root: Path,
    reuse_output_dirs: list[Path],
    final_root: Path,
    stories: list[PolicyStoryDefinition],
    versions: list[str],
    final_seeds: list[int],
) -> int:
    """Seed the dense final-run cache tree from a prior output directory."""

    if not reuse_output_dirs:
        return 0

    reusable_metrics = _build_reuse_metrics_lookup(
        repo_root=repo_root,
        reuse_output_dirs=reuse_output_dirs,
        stories=stories,
        versions=versions,
        final_seeds=final_seeds,
    )
    reused = 0
    for story in stories:
        for version in versions:
            for seed in final_seeds:
                for point in story.build_points("final", aligned=True):
                    source_metrics_paths = reusable_metrics.get(
                        (story.story_id, version, seed, _x_value_key(point.x_value))
                    )
                    if source_metrics_paths is None:
                        continue
                    for source_metrics_path in source_metrics_paths:
                        if _seed_reused_final_run(
                            repo_root=repo_root,
                            final_root=final_root,
                            source_metrics_path=source_metrics_path,
                            story=story,
                            version=version,
                            seed=seed,
                            point=point,
                        ):
                            reused += 1
                            break
    return reused


def build_reproduce_command(args: argparse.Namespace) -> str:
    """Build a reproducible module invocation for the current run configuration."""

    command_parts = [
        "python3 -m scripts.python.experiments.model.boe_policy_story_demo",
        f"--output-dir {args.output_dir}",
    ]
    for reuse_output_dir in args.reuse_output_dir:
        command_parts.append(f"--reuse-output-dir {reuse_output_dir}")
    if args.story_ids:
        command_parts.append(f"--story-ids {args.story_ids}")
    command_parts.append(f"--versions {args.versions}")
    if args.screen_only:
        command_parts.append("--screen-only")
    else:
        command_parts.append(f"--final-seeds {args.final_seeds}")
    command_parts.append(f"--workers {args.workers}")
    if args.force_rerun:
        command_parts.append("--force-rerun")
    if args.maven_bin:
        command_parts.append(f"--maven-bin {args.maven_bin}")
    if args.selection_policy != "ranking_only":
        command_parts.append(f"--selection-policy {args.selection_policy}")
    return " \\\n  ".join(command_parts) + "\n"


def write_reproduce_command(path: Path, args: argparse.Namespace) -> None:
    """Write the exact module invocation needed to reproduce the run."""

    path.write_text(build_reproduce_command(args), encoding="utf-8")


def main() -> None:
    args = build_arg_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[4]
    maven_bin = resolve_maven_bin(repo_root, args.maven_bin)
    requested_output_dir = Path(args.output_dir)
    smoke_selection_path = Path(args.smoke_selection)
    reuse_output_dirs = [Path(raw_path) for raw_path in args.reuse_output_dir]
    runtime_output_dir, uses_staging = resolve_run_output_dir(
        requested_output_dir,
        reuse_output_dirs,
    )

    if not args.screen_only and args.story_ids is None and smoke_selection_path.exists():
        args.story_ids = ",".join(load_story_ids_from_smoke_selection(smoke_selection_path))

    if runtime_output_dir.exists():
        if uses_staging or not args.screen_only:
            shutil.rmtree(runtime_output_dir)
    output_dir = ensure_output_dir(runtime_output_dir)
    screen_root = output_dir / "screen"
    final_root = output_dir / "final"

    versions = validate_versions(parse_csv_list(args.versions))
    screen_seeds = parse_seed_list(args.screen_seeds)
    final_seeds = parse_seed_list(args.final_seeds)
    requested_story_ids = parse_csv_list(args.story_ids) if args.story_ids else None
    selection_policy = validate_selection_policy(args.selection_policy)
    canonical_policy = canonical_selection_policy(selection_policy)

    all_stories = get_policy_story_catalog()
    method_audits = build_story_method_audits(
        all_stories,
        repo_root=repo_root,
        versions=versions,
    )
    binding_details = build_binding_details(
        all_stories, repo_root=repo_root, versions=versions
    )
    candidate_stories = select_catalog_subset(all_stories, requested_story_ids)
    candidate_stories, binding_matrix = eligible_stories_by_binding(
        candidate_stories,
        repo_root=repo_root,
        versions=versions,
    )
    if not candidate_stories:
        raise SystemExit("No candidate stories remained after binding checks.")

    catalog_lookup = story_lookup(candidate_stories)
    full_story_lookup = story_lookup(all_stories)
    evidence_reviews = get_story_evidence_reviews()
    skip_screening = requested_story_ids is not None and not args.screen_only

    selection_candidate_stories = [
        story
        for story in candidate_stories
        if method_audits[story.story_id].shortlist_eligible
    ]
    if requested_story_ids is None and not selection_candidate_stories:
        raise SystemExit("No shortlist-eligible stories remained after method audit.")

    if skip_screening:
        selected_story_order = [
            catalog_lookup[story_id] for story_id in requested_story_ids
        ]
        ensure_project_compiled(repo_root, maven_bin=maven_bin)
        if reuse_output_dirs and not args.force_rerun:
            reused = seed_final_run_caches_from_previous_output(
                repo_root=repo_root,
                reuse_output_dirs=reuse_output_dirs,
                final_root=final_root,
                stories=selected_story_order,
                versions=versions,
                final_seeds=final_seeds,
            )
            if reused > 0:
                print(
                    f"[policy-sweep] seeded final cache entries={reused} from "
                    + ", ".join(str(path) for path in reuse_output_dirs)
                )
        final_aggregated = run_final_stage(
            repo_root=repo_root,
            final_root=final_root,
            stories=selected_story_order,
            versions=versions,
            final_seeds=final_seeds,
            workers=args.workers,
            force_rerun=args.force_rerun,
            maven_bin=maven_bin,
        )
        screen_scores = [
            score_story_screening(story, final_aggregated[story.story_id])
            for story in selected_story_order
        ]
        selection_results = {canonical_policy: screen_scores}
        selected_scores = selection_results[canonical_policy]
    else:
        ensure_project_compiled(repo_root, maven_bin=maven_bin)

        _, screen_scores = run_screening_stage(
            repo_root=repo_root,
            screen_root=screen_root,
            stories=candidate_stories,
            versions=versions,
            screen_seeds=screen_seeds,
            workers=args.workers,
            force_rerun=args.force_rerun,
            maven_bin=maven_bin,
        )
        shortlist_score_lookup = {score.story_id: score for score in screen_scores}
        if requested_story_ids is not None:
            selection_results = {
                canonical_policy: [
                    next(score for score in screen_scores if score.story_id == story_id)
                    for story_id in requested_story_ids
                ]
            }
        else:
            selection_results = build_selection_results(
                [shortlist_score_lookup[story.story_id] for story in selection_candidate_stories],
                selection_candidate_stories,
                selection_policy=selection_policy,
            )
        selected_scores = selection_results[canonical_policy]

        if args.screen_only:
            recommendation = recommend_story(
                story_scores=[shortlist_score_lookup[story.story_id] for story in selection_candidate_stories],
                stories=full_story_lookup,
                evidence_reviews=evidence_reviews,
            )
            write_screen_summary_csv(
                output_dir / "story_candidates_screen.csv",
                screen_scores,
                selection_policy=selection_policy,
            )
            write_screen_summary_json(
                output_dir / "story_candidates_screen.json",
                screen_scores,
                binding_matrix,
                selection_policy=selection_policy,
            )
            write_selected_stories_json(
                output_dir / "selected_stories.json",
                selection_results,
                selection_policy=selection_policy,
                canonical_policy=canonical_policy,
            )
            write_method_audit_csv(
                output_dir / "story_method_audit.csv",
                method_audits=method_audits,
                versions=versions,
            )
            write_method_audit_json(
                output_dir / "story_method_audit.json",
                method_audits=method_audits,
            )
            write_method_audit_markdown(
                output_dir / "story_method_audit.md",
                method_audits=method_audits,
                versions=versions,
            )
            write_binding_validation_csv(
                output_dir / "story_binding_validation.csv",
                stories=all_stories,
                binding_details=binding_details,
                versions=versions,
            )
            write_binding_validation_json(
                output_dir / "story_binding_validation.json",
                stories=all_stories,
                binding_details=binding_details,
                versions=versions,
            )
            write_evidence_review_markdown(
                output_dir / "story_evidence_review.md",
                story_scores=screen_scores,
                stories=full_story_lookup,
                evidence_reviews=evidence_reviews,
            )
            write_recommendation_markdown(
                output_dir / "story_recommendation.md",
                recommendation=recommendation,
                evidence_reviews=evidence_reviews,
                story_lookup=full_story_lookup,
            )
            write_report_markdown(
                output_dir / "boe_policy_story_report.md",
                selected_scores=selected_scores,
                selection_results=selection_results,
                story_lookup=full_story_lookup,
                screening_scores=screen_scores,
                versions=versions,
                selection_policy=selection_policy,
                canonical_policy=canonical_policy,
                methodology_note=METHODOLOGY_NOTE,
            )
            write_sources_markdown(
                output_dir / "boe_policy_story_sources.md",
                selected_scores=selected_scores,
                story_lookup=full_story_lookup,
                selection_policy=selection_policy,
            )
            write_reproduce_command(output_dir / "reproduce_command.txt", args)
            finalize_output_dir(
                requested_output_dir=requested_output_dir,
                runtime_output_dir=output_dir,
                used_staging=uses_staging,
            )
            return

        selected_story_order = [catalog_lookup[score.story_id] for score in selected_scores]
        if reuse_output_dirs and not args.force_rerun:
            reused = seed_final_run_caches_from_previous_output(
                repo_root=repo_root,
                reuse_output_dirs=reuse_output_dirs,
                final_root=final_root,
                stories=selected_story_order,
                versions=versions,
                final_seeds=final_seeds,
            )
            if reused > 0:
                print(
                    f"[policy-sweep] seeded final cache entries={reused} from "
                    + ", ".join(str(path) for path in reuse_output_dirs)
                )
        final_aggregated = run_final_stage(
            repo_root=repo_root,
            final_root=final_root,
            stories=selected_story_order,
            versions=versions,
            final_seeds=final_seeds,
            workers=args.workers,
            force_rerun=args.force_rerun,
            maven_bin=maven_bin,
        )

    recommendation = recommend_story(
        story_scores=selected_scores,
        stories=full_story_lookup,
        evidence_reviews=evidence_reviews,
    )
    write_screen_summary_csv(
        output_dir / "story_candidates_screen.csv",
        screen_scores,
        selection_policy=selection_policy,
    )
    write_screen_summary_json(
        output_dir / "story_candidates_screen.json",
        screen_scores,
        binding_matrix,
        selection_policy=selection_policy,
    )
    write_selected_stories_json(
        output_dir / "selected_stories.json",
        selection_results,
        selection_policy=selection_policy,
        canonical_policy=canonical_policy,
    )
    write_method_audit_csv(
        output_dir / "story_method_audit.csv",
        method_audits=method_audits,
        versions=versions,
    )
    write_method_audit_json(
        output_dir / "story_method_audit.json",
        method_audits=method_audits,
    )
    write_method_audit_markdown(
        output_dir / "story_method_audit.md",
        method_audits=method_audits,
        versions=versions,
    )
    write_binding_validation_csv(
        output_dir / "story_binding_validation.csv",
        stories=all_stories,
        binding_details=binding_details,
        versions=versions,
    )
    write_binding_validation_json(
        output_dir / "story_binding_validation.json",
        stories=all_stories,
        binding_details=binding_details,
        versions=versions,
    )
    write_evidence_review_markdown(
        output_dir / "story_evidence_review.md",
        story_scores=screen_scores,
        stories=full_story_lookup,
        evidence_reviews=evidence_reviews,
    )
    write_recommendation_markdown(
        output_dir / "story_recommendation.md",
        recommendation=recommendation,
        evidence_reviews=evidence_reviews,
        story_lookup=full_story_lookup,
    )

    clear_previous_story_artifacts(output_dir)

    for index, score in enumerate(selected_scores, start=1):
        story = catalog_lookup[score.story_id]
        aggregated = final_aggregated[story.story_id]
        write_story_csv(
            output_dir / f"story_{index}_{story.story_id}.csv", story, aggregated
        )
        plot_story_figure(
            path=output_dir / f"story_{index}_{story.story_id}.png",
            story=story,
            aggregated=aggregated,
        )
        plot_story_split_figures(
            path_prefix=output_dir / f"story_{index}_{story.story_id}",
            story=story,
            aggregated=aggregated,
        )

    write_report_markdown(
        output_dir / "boe_policy_story_report.md",
        selected_scores=selected_scores,
        selection_results=selection_results,
        story_lookup=full_story_lookup,
        screening_scores=screen_scores,
        versions=versions,
        selection_policy=selection_policy,
        canonical_policy=canonical_policy,
        methodology_note=METHODOLOGY_NOTE,
    )
    write_sources_markdown(
        output_dir / "boe_policy_story_sources.md",
        selected_scores=selected_scores,
        story_lookup=full_story_lookup,
        selection_policy=selection_policy,
    )
    write_reproduce_command(output_dir / "reproduce_command.txt", args)
    finalize_output_dir(
        requested_output_dir=requested_output_dir,
        runtime_output_dir=output_dir,
        used_staging=uses_staging,
    )


if __name__ == "__main__":
    main()
