"""CLI entrypoint for bulk 2024 validation across input-data versions.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.python.validation.model.runner import run_validation_for_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 2024 validation for multiple input-data versions.")
    parser.add_argument("--versions", default="all", help="Comma-separated versions or 'all'")
    parser.add_argument("--seeds", default="1,2,3,4,5,6,7,8", help="Comma-separated seed list")
    parser.add_argument("--output-root", required=True, help="Transient output root directory")
    parser.add_argument("--maven-bin", default="mvn", help="Maven executable")
    parser.add_argument("--was-data-root", default=None, help="Optional WAS data root override")
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
        if path.is_dir() and path.name.startswith("v") and (path / "config.properties").exists()
    ]
    return sorted(versions, key=lambda version: parse_version_parts(version))


def resolve_versions(repo_root: Path, raw_versions: str) -> list[str]:
    if raw_versions == "all":
        return list_versions(repo_root)
    requested = [version.strip() for version in raw_versions.split(",") if version.strip()]
    return sorted(requested, key=lambda version: parse_version_parts(version))


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[4]
    versions = resolve_versions(repo_root, args.versions)
    seeds = parse_seed_list(args.seeds)
    output_root = Path(args.output_root)
    failures: list[str] = []

    for version in versions:
        try:
            run_validation_for_version(
                repo_root=repo_root,
                version=version,
                seeds=seeds,
                output_dir=output_root / version,
                maven_bin=args.maven_bin,
                was_data_root=Path(args.was_data_root) if args.was_data_root else None,
            )
            print(f"Published {version}")
        except Exception as error:  # pragma: no cover - CLI reporting path
            failures.append(f"{version}: {error}")
            print(f"Failed {version}: {error}")

    if failures:
        raise SystemExit("Validation failed for versions:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
