"""CLI entrypoint for validating one input-data version.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.python.validation.model.runner import run_validation_for_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 2024 validation for one input-data version.")
    parser.add_argument("--version", required=True, help="Input-data version folder name, for example v4.1")
    parser.add_argument("--seeds", default="1,2,3,4,5,6,7,8", help="Comma-separated seed list")
    parser.add_argument("--output-dir", required=True, help="Transient validation output directory")
    parser.add_argument("--maven-bin", default="mvn", help="Maven executable")
    parser.add_argument("--was-data-root", default=None, help="Optional WAS data root override")
    return parser.parse_args()


def parse_seed_list(seed_text: str) -> list[int]:
    return [int(token.strip()) for token in seed_text.split(",") if token.strip()]


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[4]
    summary = run_validation_for_version(
        repo_root=repo_root,
        version=args.version,
        seeds=parse_seed_list(args.seeds),
        output_dir=Path(args.output_dir),
        maven_bin=args.maven_bin,
        was_data_root=Path(args.was_data_root) if args.was_data_root else None,
    )
    print(
        f"Published validation summary for {summary['version']} "
        f"with overallCompositeLoss={summary['overallCompositeLoss']:.6f}"
    )


if __name__ == "__main__":
    main()
