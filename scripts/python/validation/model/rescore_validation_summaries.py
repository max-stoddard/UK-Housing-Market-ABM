"""Rescore cached validation summaries under the current validation-loss schema.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from scripts.python.validation.model.runner import _coerce_target_definition
from scripts.python.validation.model.schema import VALIDATION_SCHEMA_VERSION, MetricDefinition
from scripts.python.validation.model.scoring import classify_metric_status, compute_metric_loss_audit, compute_overall_composite_loss
from scripts.python.validation.model.validate_all_input_data_versions import list_versions, resolve_versions
from scripts.python.validation.model.validation_profiles import (
    ValidationProfile,
    resolve_reference_validation_profile,
    resolve_validation_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rescore cached validation summaries without rerunning the model.")
    parser.add_argument("--versions", default="all", help="Comma-separated tracked versions or 'all'.")
    parser.add_argument("--include-overlays", action="store_true", help="Also rescore validation-overlays/*.json.")
    parser.add_argument("--write", action="store_true", help="Write upgraded JSON in place. Without this, dry-run only.")
    return parser.parse_args()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _source_value(*, metric: Mapping[str, object], target: MetricDefinition) -> float | None:
    if metric.get("sourceValue") is not None:
        return float(metric["sourceValue"])
    if target.source_metadata is not None:
        return target.source_metadata.normalized_source_value
    return None


def _target_band(metric: Mapping[str, object], target: MetricDefinition) -> tuple[float, float] | None:
    raw_band = metric.get("targetBand")
    if isinstance(raw_band, Mapping):
        return float(raw_band["lower"]), float(raw_band["upper"])
    if target.target_band is None:
        return None
    return target.target_band.lower, target.target_band.upper


def rescore_summary_payload(*, summary: Mapping[str, object], validation_profile: ValidationProfile) -> dict[str, object]:
    """Return a schema-upgraded summary with cached metric values rescored in place."""

    raw_metrics = summary.get("metrics")
    if not isinstance(raw_metrics, Sequence):
        raise RuntimeError("Validation summary is missing metrics")

    scored_metric_losses: list[float] = []
    scored_metric_weights: list[float] = []
    rescored_metrics: list[dict[str, object]] = []

    for raw_metric in raw_metrics:
        if not isinstance(raw_metric, Mapping):
            raise RuntimeError("Validation summary contains an invalid metric entry")
        metric = dict(raw_metric)
        metric_id = str(metric["metricId"])
        target = _coerce_target_definition(metric_id, validation_profile.targets_by_id.get(metric_id))
        band = _target_band(metric, target)
        metric["lossFamily"] = target.loss_family

        if band is None or target.requirement != "required":
            metric.update(
                {
                    "lossTransform": None,
                    "lossScale": None,
                    "lossScaleBasis": None,
                    "additiveScale": None,
                    "additiveScaleBasis": None,
                    "normalizedDistance": None,
                    "normalizedIqr": None,
                    "distanceComponent": None,
                    "spreadComponent": None,
                    "levelComponent": None,
                    "insideRateComponent": None,
                    "metricLoss": None,
                    "metricWeight": 0.0,
                    "status": "unsupported",
                }
            )
            rescored_metrics.append(metric)
            continue

        if metric.get("insideRate") is None:
            raise RuntimeError(f"Validation summary is missing insideRate for {metric_id}")
        lower, upper = band
        loss_audit = compute_metric_loss_audit(
            loss_family=target.loss_family,
            seed_mean=float(metric["seedMean"]),
            p25=float(metric["p25"]),
            p75=float(metric["p75"]),
            lower_bound=lower,
            upper_bound=upper,
            inside_rate=float(metric["insideRate"]),
            source_value=_source_value(metric=metric, target=target),
        )
        metric.update(
            {
                "lossFamily": loss_audit.loss_family,
                "lossTransform": loss_audit.loss_transform,
                "lossScale": loss_audit.loss_scale,
                "lossScaleBasis": loss_audit.loss_scale_basis,
                "additiveScale": loss_audit.additive_scale,
                "additiveScaleBasis": loss_audit.additive_scale_basis,
                "normalizedDistance": loss_audit.normalized_distance,
                "normalizedIqr": loss_audit.normalized_iqr,
                "distanceComponent": loss_audit.distance_component,
                "spreadComponent": loss_audit.spread_component,
                "levelComponent": loss_audit.level_component,
                "insideRateComponent": loss_audit.inside_rate_component,
                "metricLoss": loss_audit.metric_loss,
                "metricWeight": 1.0,
                "status": classify_metric_status(
                    seed_mean=float(metric["seedMean"]),
                    lower_bound=lower,
                    upper_bound=upper,
                    inside_rate=float(metric["insideRate"]),
                ),
            }
        )
        scored_metric_losses.append(loss_audit.metric_loss)
        scored_metric_weights.append(1.0)
        rescored_metrics.append(metric)

    if not scored_metric_losses:
        raise RuntimeError("Missing required metric losses for overall composite scoring")

    payload = dict(summary)
    payload["schemaVersion"] = VALIDATION_SCHEMA_VERSION
    payload["overallCompositeLoss"] = compute_overall_composite_loss(
        metric_losses=scored_metric_losses,
        metric_weights=scored_metric_weights,
    )
    payload["metrics"] = rescored_metrics
    return payload


def _profile_for_summary(summary: Mapping[str, object]) -> ValidationProfile:
    version = str(summary["version"])
    validation_target_year = int(summary.get("validationTargetYear") or 2024)
    if validation_target_year == 2011:
        profile = resolve_reference_validation_profile(version)
        if profile is None:
            raise RuntimeError(f"No 2011 reference validation profile is available for {version}")
        return profile
    return resolve_validation_profile(version)


def _summary_paths_for_versions(repo_root: Path, versions: Sequence[str]) -> list[Path]:
    return [repo_root / "input-data-versions" / "validation" / f"{version}.json" for version in versions]


def _overlay_paths(repo_root: Path) -> list[Path]:
    overlays_dir = repo_root / "input-data-versions" / "validation-overlays"
    if not overlays_dir.exists():
        return []
    return sorted(path for path in overlays_dir.glob("*.json") if path.is_file())


def rescore_paths(*, paths: Sequence[Path], write: bool) -> list[str]:
    messages: list[str] = []
    for path in paths:
        summary = json.loads(path.read_text(encoding="utf-8"))
        rescored = rescore_summary_payload(summary=summary, validation_profile=_profile_for_summary(summary))
        if write:
            path.write_text(json.dumps(rescored, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        messages.append(
            f"{'rescored' if write else 'would rescore'} {path.as_posix()} "
            f"schemaVersion={rescored['schemaVersion']} overallCompositeLoss={rescored['overallCompositeLoss']:.6f}"
        )
    return messages


def main() -> None:
    args = parse_args()
    repo_root = _repo_root()
    versions = list_versions(repo_root) if args.versions == "all" else resolve_versions(repo_root, args.versions)
    paths = _summary_paths_for_versions(repo_root, versions)
    if args.include_overlays:
        paths.extend(_overlay_paths(repo_root))
    for message in rescore_paths(paths=paths, write=args.write):
        print(message)


if __name__ == "__main__":
    main()
