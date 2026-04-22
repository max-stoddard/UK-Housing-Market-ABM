"""CLI entrypoint for bulk validation across input-data versions.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.python.helpers.common.abm_policy_sweep import ensure_project_compiled
from scripts.python.validation.model.runner import (
    load_reused_validation_results,
    publish_validation_results,
    resolve_was_data_root,
    run_validation_seed,
)
from scripts.python.validation.model.validation_profiles import resolve_validation_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run version-gated validation for multiple input-data versions."
    )
    parser.add_argument(
        "--versions", default="all", help="Comma-separated versions or 'all'"
    )
    parser.add_argument(
        "--seeds", default="1,2,3,4,5,6,7,8", help="Comma-separated seed list"
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Maximum parallel validation runs"
    )
    parser.add_argument(
        "--output-root", required=True, help="Transient output root directory"
    )
    parser.add_argument("--maven-bin", default="mvn", help="Maven executable")
    parser.add_argument(
        "--was-data-root", default=None, help="Optional WAS data root override"
    )
    parser.add_argument(
        "--reuse-existing-output",
        action="store_true",
        help="Reuse existing per-seed outputs under --output-root/<version> instead of rerunning the model",
    )
    return parser.parse_args()


def parse_seed_list(seed_text: str) -> list[int]:
    return [int(token.strip()) for token in seed_text.split(",") if token.strip()]


def parse_version_parts(version: str) -> list[int]:
    return [int(part) for part in version.lower().removeprefix("v").split(".")]


def compare_versions(left: str, right: str) -> int:
    left_parts = parse_version_parts(left)
    right_parts = parse_version_parts(right)
    max_length = max(len(left_parts), len(right_parts))
    for index in range(max_length):
        left_value = left_parts[index] if index < len(left_parts) else 0
        right_value = right_parts[index] if index < len(right_parts) else 0
        if left_value != right_value:
            return left_value - right_value
    if len(left_parts) != len(right_parts):
        return len(left_parts) - len(right_parts)
    return -1 if left < right else 1 if left > right else 0


def list_versions(repo_root: Path) -> list[str]:
    input_data_dir = repo_root / "input-data-versions"
    versions = [
        path.name
        for path in input_data_dir.iterdir()
        if path.is_dir()
        and path.name.startswith("v")
        and (path / "config.properties").exists()
    ]
    return sorted(versions, key=lambda version: parse_version_parts(version))


def resolve_versions(repo_root: Path, raw_versions: str) -> list[str]:
    if raw_versions == "all":
        return list_versions(repo_root)
    requested = [
        version.strip() for version in raw_versions.split(",") if version.strip()
    ]
    return sorted(requested, key=lambda version: parse_version_parts(version))


def run_validation_campaign(
    *,
    repo_root: Path,
    versions: list[str],
    seeds: list[int],
    workers: int,
    output_root: Path,
    maven_bin: str = "mvn",
    was_data_root: Path | None = None,
    reuse_existing_output: bool = False,
) -> tuple[list[str], list[str]]:
    """Run and publish a multi-version validation refresh."""

    if workers <= 0:
        raise ValueError("workers must be positive")

    resolved_was_data_root = resolve_was_data_root(
        repo_root=repo_root, explicit_root=was_data_root
    )
    profiles_by_version = {
        version: resolve_validation_profile(version) for version in versions
    }
    if reuse_existing_output:
        published_versions: list[str] = []
        failures: list[str] = []
        for version in versions:
            version_output_dir = output_root / version
            try:
                run_results = load_reused_validation_results(
                    output_dir=version_output_dir,
                    seeds=seeds,
                    was_data_root=resolved_was_data_root,
                    validation_profile=profiles_by_version[version],
                )
                publish_validation_results(
                    repo_root=repo_root,
                    version=version,
                    seeds=seeds,
                    output_dir=version_output_dir,
                    run_results=run_results,
                    validation_profile=profiles_by_version[version],
                    was_data_root=resolved_was_data_root,
                )
                published_versions.append(version)
                print(f"Published {version} from existing outputs")
            except Exception as error:
                failures.append(f"{version}: {error}")
                print(f"Failed {version} from existing outputs: {error}")
        return published_versions, failures

    ensure_project_compiled(repo_root, maven_bin=maven_bin)

    results_by_version: dict[str, list[dict[str, object]]] = {
        version: [] for version in versions
    }
    failures: list[str] = []
    future_to_request: dict[object, tuple[str, int]] = {}
    total_runs = len(versions) * len(seeds)
    completed_runs = 0

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="validation-worker") as executor:
        for version in versions:
            version_output_dir = output_root / version
            for seed in seeds:
                future = executor.submit(
                    run_validation_seed,
                    repo_root=repo_root,
                    version=version,
                    seed=seed,
                    output_dir=version_output_dir,
                    maven_bin=maven_bin,
                    was_data_root=resolved_was_data_root,
                    validation_profile=profiles_by_version[version],
                )
                future_to_request[future] = (version, seed)

        for future in as_completed(future_to_request):
            version, seed = future_to_request[future]
            completed_runs += 1
            try:
                results_by_version[version].append(future.result())
                print(
                    f"Completed {version} seed={seed} ({completed_runs}/{total_runs})"
                )
            except Exception as error:
                failures.append(f"{version} seed={seed}: {error}")
                print(
                    f"Failed {version} seed={seed} ({completed_runs}/{total_runs}): {error}"
                )

    published_versions: list[str] = []
    missing_versions: list[str] = []
    expected_seed_set = sorted(seeds)
    for version in versions:
        version_results = results_by_version[version]
        returned_seed_set = sorted(int(result["seed"]) for result in version_results)
        if returned_seed_set != expected_seed_set:
            missing_versions.append(version)
            continue
        publish_validation_results(
            repo_root=repo_root,
            version=version,
            seeds=seeds,
            output_dir=output_root / version,
            run_results=version_results,
            validation_profile=profiles_by_version[version],
            was_data_root=resolved_was_data_root,
        )
        published_versions.append(version)
        print(f"Published {version}")

    failures.extend(
        f"{version}: tracked publication skipped because not all seeds finished successfully"
        for version in missing_versions
    )
    return published_versions, failures


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[4]
    versions = resolve_versions(repo_root, args.versions)
    seeds = parse_seed_list(args.seeds)
    output_root = Path(args.output_root)
    _, failures = run_validation_campaign(
        repo_root=repo_root,
        versions=versions,
        seeds=seeds,
        workers=args.workers,
        output_root=output_root,
        maven_bin=args.maven_bin,
        was_data_root=Path(args.was_data_root) if args.was_data_root else None,
        reuse_existing_output=args.reuse_existing_output,
    )

    if failures:
        raise SystemExit("Validation failed for versions:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
