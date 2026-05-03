"""CLI entrypoint for validating one input-data version.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.python.validation.model.runner import publish_reference_validation_only, run_validation_for_version
from scripts.python.validation.model.validation_profiles import resolve_validation_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run version-gated validation for one input-data version.")
    parser.add_argument("--version", required=True, help="Input-data version folder name, for example v4.1")
    parser.add_argument("--seeds", default="1,2,3,4,5,6,7,8", help="Comma-separated seed list")
    parser.add_argument("--output-dir", required=True, help="Transient validation output directory")
    parser.add_argument("--workers", type=int, default=20, help="Maximum parallel workers for per-seed validation runs")
    parser.add_argument("--maven-bin", default="mvn", help="Maven executable")
    parser.add_argument("--was-data-root", default=None, help="Optional WAS data root override")
    parser.add_argument(
        "--reuse-existing-output",
        action="store_true",
        help="Reuse existing per-seed outputs from --output-dir instead of rerunning the model",
    )
    parser.add_argument(
        "--reference-only",
        action="store_true",
        help="Publish only the optional 2011 reference overlay from existing per-seed outputs.",
    )
    return parser.parse_args()


def parse_seed_list(seed_text: str) -> list[int]:
    return [int(token.strip()) for token in seed_text.split(",") if token.strip()]


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[4]
    seeds = parse_seed_list(args.seeds)
    was_data_root = Path(args.was_data_root) if args.was_data_root else None
    if args.reference_only:
        summary = publish_reference_validation_only(
            repo_root=repo_root,
            version=args.version,
            seeds=seeds,
            output_dir=Path(args.output_dir),
            was_data_root=was_data_root,
        )
        print(
            f"Published reference validation overlay for {summary['version']} "
            f"(targetYear={summary['validationTargetYear']}) "
            f"with overallCompositeLoss={summary['overallCompositeLoss']:.6f}"
        )
        return

    validation_profile = resolve_validation_profile(args.version)
    summary = run_validation_for_version(
        repo_root=repo_root,
        version=args.version,
        seeds=seeds,
        output_dir=Path(args.output_dir),
        maven_bin=args.maven_bin,
        workers=args.workers,
        was_data_root=was_data_root,
        reuse_existing_output=args.reuse_existing_output,
    )
    print(
        f"Published validation summary for {summary['version']} "
        f"(targetYear={validation_profile.validation_target_year}) "
        f"with overallCompositeLoss={summary['overallCompositeLoss']:.6f}"
    )


if __name__ == "__main__":
    main()
