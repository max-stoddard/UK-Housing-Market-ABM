"""Snapshot-local runner and summary builder for 2024 validation.

@author: Max Stoddard
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from scripts.python.helpers.common.abm_policy_sweep import build_snapshot_local_config_text, ensure_project_compiled
from scripts.python.validation.model.extractors import extract_core_indicator_mean, extract_household_metric_from_results
from scripts.python.validation.model.publish import write_transient_artifacts, write_validation_summary
from scripts.python.validation.model.schema import (
    CANONICAL_VALIDATION_SEEDS,
    FAMILY_HOUSEHOLD_DISTRIBUTION_REALISM,
    FAMILY_MACRO_CREDIT_ACTIVITY,
    FAMILY_MACRO_PRICES_LEVERAGE_AFFORDABILITY,
    VALIDATION_SCHEMA_VERSION,
    VALIDATION_WINDOW_END,
    VALIDATION_WINDOW_START,
    MetricDefinition,
    MetricSourceMetadata,
    MetricSourceReference,
)
from scripts.python.validation.model.scoring import (
    classify_metric_status,
    compute_metric_loss,
    compute_outside_distance,
    compute_overall_composite_loss,
    normalize_by_loss_scale,
    resolve_loss_scale,
)
from scripts.python.validation.model.validation_catalog_2024 import FAMILY_DEFINITIONS, TARGETS_BY_ID

VALIDATION_RECORDING_OVERRIDES = {
    "recordTransactions": "false",
    "recordNBidUpFrequency": "false",
    "recordCoreIndicators": "true",
    "recordQualityBandPrice": "false",
    "recordHouseholdID": "false",
    "recordEmploymentIncome": "true",
    "recordRentalIncome": "false",
    "recordBankBalance": "true",
    "recordHousingWealth": "true",
    "recordNHousesOwned": "false",
    "recordAge": "false",
    "recordSavingRate": "false",
}


def run_validation_for_version(
    *,
    repo_root: Path,
    version: str,
    seeds: list[int],
    output_dir: Path,
    maven_bin: str = "mvn",
    was_data_root: Path | None = None,
    allow_test_override: bool = False,
) -> dict:
    """Run canonical validation for one input-data version and publish artifacts."""

    canonical_seeds = list(CANONICAL_VALIDATION_SEEDS)
    if seeds != canonical_seeds and not allow_test_override:
        raise ValueError("Canonical validation requires seeds 1..8 unless an explicit test-only override is used")

    resolved_was_data_root = resolve_was_data_root(repo_root=repo_root, explicit_root=was_data_root)
    run_results = run_snapshot_local_validation(
        repo_root=repo_root,
        version=version,
        seeds=seeds,
        output_dir=output_dir,
        maven_bin=maven_bin,
        was_data_root=resolved_was_data_root,
    )
    return publish_validation_results(
        repo_root=repo_root,
        version=version,
        seeds=seeds,
        output_dir=output_dir,
        run_results=run_results,
    )


def publish_validation_results(
    *,
    repo_root: Path,
    version: str,
    seeds: Sequence[int],
    output_dir: Path,
    run_results: Sequence[dict[str, object]],
) -> dict:
    """Publish tracked and transient outputs after all seed runs succeed."""

    returned_seeds = sorted(int(result["seed"]) for result in run_results)
    if returned_seeds != sorted(seeds):
        raise ValueError("Tracked publication requires 8/8 successful seeds before publishing tracked JSON")

    summary = build_validation_summary(version=version, seed_results=run_results, seeds=seeds)
    write_transient_artifacts(output_dir=output_dir, summary=summary, seed_results=run_results)
    write_validation_summary(repo_root=repo_root, summary=summary)
    return summary


def run_snapshot_local_validation(
    *,
    repo_root: Path,
    version: str,
    seeds: Sequence[int],
    output_dir: Path,
    maven_bin: str,
    was_data_root: Path,
) -> list[dict[str, object]]:
    """Execute the Java model snapshot-locally for each seed and extract metrics."""

    version_config_path = repo_root / "input-data-versions" / version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    ensure_project_compiled(repo_root, maven_bin=maven_bin)
    seed_results: list[dict[str, object]] = []
    configs_dir = output_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    for seed in seeds:
        seed_results.append(
            run_validation_seed(
                repo_root=repo_root,
                version=version,
                seed=seed,
                output_dir=output_dir,
                maven_bin=maven_bin,
                was_data_root=was_data_root,
            )
        )

    return seed_results


def run_validation_seed(
    *,
    repo_root: Path,
    version: str,
    seed: int,
    output_dir: Path,
    maven_bin: str,
    was_data_root: Path,
) -> dict[str, object]:
    """Run one snapshot-local validation seed and return its extracted metrics."""

    version_config_path = repo_root / "input-data-versions" / version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    configs_dir = output_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    seed_output_dir = output_dir / f"seed-{seed}"
    if seed_output_dir.exists():
        shutil.rmtree(seed_output_dir)
    seed_output_dir.mkdir(parents=True, exist_ok=True)

    overrides = dict(VALIDATION_RECORDING_OVERRIDES)
    overrides["SEED"] = str(seed)
    config_text = build_snapshot_local_config_text(version_config_path, overrides)
    config_path = configs_dir / f"seed-{seed}.properties"
    config_path.write_text(config_text, encoding="utf-8")

    exec_args = f'-configFile "{config_path}" -outputFolder "{seed_output_dir}" -dev'
    proc = subprocess.run(
        [maven_bin, "-q", "exec:java", f"-Dexec.args={exec_args}"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Model validation run failed.\n"
            f"version={version} seed={seed}\n"
            f"Output tail:\n{proc.stdout[-3000:]}"
        )

    return {
        "seed": seed,
        "outputDir": str(seed_output_dir),
        "metrics": _extract_seed_metrics(seed_output_dir=seed_output_dir, was_data_root=was_data_root),
    }


def resolve_was_data_root(*, repo_root: Path, explicit_root: Path | None) -> Path:
    """Resolve a usable WAS data root for a normal checkout or a git worktree."""

    if explicit_root is not None:
        return explicit_root

    candidates = [repo_root]
    candidates.extend(repo_root.parents[:3])
    for candidate in candidates:
        if (candidate / "private-datasets" / "was" / "was_round_8_hhold_eul_may_2025.privdata").exists():
            return candidate
    return repo_root


def build_validation_summary(
    *,
    version: str,
    seed_results: Sequence[dict[str, object]],
    seeds: Sequence[int],
    targets_by_id: Mapping[str, object] | None = None,
) -> dict:
    """Build the dashboard-facing summary JSON from per-seed metric values."""

    if len(seed_results) != len(seeds):
        raise ValueError("Tracked publication requires 8/8 successful seeds before publishing tracked JSON")

    target_lookup = targets_by_id or TARGETS_BY_ID
    metric_ids = _ordered_metric_ids(seed_results=seed_results, target_lookup=target_lookup)
    summary_metrics: list[dict] = []
    family_status_counts: dict[str, dict[str, int]] = {
        family.family_id: {"pass": 0, "warn": 0, "fail": 0, "unsupported": 0}
        for family in FAMILY_DEFINITIONS
    }
    family_required_losses: dict[str, list[float]] = {family.family_id: [] for family in FAMILY_DEFINITIONS}

    for metric_id in metric_ids:
        target = _coerce_target_definition(metric_id, target_lookup.get(metric_id))
        seed_values = _metric_seed_values(metric_id=metric_id, seed_results=seed_results)
        seed_mean = float(np.mean(seed_values))
        p25 = float(np.percentile(seed_values, 25))
        p75 = float(np.percentile(seed_values, 75))

        metric_summary = {
            "metricId": target.metric_id,
            "familyId": target.family_id,
            "label": target.label,
            "requirement": target.requirement,
            "units": target.units,
            "sourceLabel": target.source_label,
            "sourceIndicatorLabel": None,
            "sourceDocumentPath": None,
            "sourceTextPath": None,
            "sourceTable": None,
            "sourcePage": None,
            "rawSourceValue": None,
            "sourceValue": None,
            "sourceAsOf": None,
            "sourceUnits": None,
            "comparisonUnits": None,
            "mappingStatus": None,
            "bandMethod": None,
            "bandNotes": None,
            "sourceReferences": [],
            "targetBand": None,
            "seedMean": seed_mean,
            "p25": p25,
            "p75": p75,
            "insideRate": None,
            "lossScale": None,
            "lossScaleBasis": None,
            "normalizedDistance": None,
            "normalizedIqr": None,
            "metricLoss": None,
            "status": "unsupported",
        }
        if target.source_metadata is not None:
            metric_summary.update(
                {
                    "sourceIndicatorLabel": target.source_metadata.source_indicator_label,
                    "sourceDocumentPath": target.source_metadata.source_document_path,
                    "sourceTextPath": target.source_metadata.source_text_path,
                    "sourceTable": target.source_metadata.source_table,
                    "sourcePage": target.source_metadata.source_page,
                    "rawSourceValue": target.source_metadata.raw_source_value,
                    "sourceValue": target.source_metadata.normalized_source_value,
                    "sourceAsOf": target.source_metadata.source_as_of,
                    "sourceUnits": target.source_metadata.source_units,
                    "comparisonUnits": target.source_metadata.comparison_units,
                    "mappingStatus": target.source_metadata.mapping_status,
                    "bandMethod": target.source_metadata.band_method,
                    "bandNotes": target.source_metadata.band_notes,
                    "sourceReferences": [
                        _serialize_source_reference(reference)
                        for reference in target.source_metadata.source_references
                    ],
                }
            )

        if target.target_band is None:
            if target.requirement == "required":
                raise RuntimeError(f"Missing target metadata for required metric {target.metric_id}")
        else:
            inside_rate = _inside_rate(seed_values=seed_values, lower=target.target_band.lower, upper=target.target_band.upper)
            loss_scale, loss_scale_basis = resolve_loss_scale(
                source_value=target.source_metadata.normalized_source_value if target.source_metadata else None,
                lower_bound=target.target_band.lower,
                upper_bound=target.target_band.upper,
            )
            normalized_distance = normalize_by_loss_scale(
                raw_value=compute_outside_distance(
                    seed_mean=seed_mean,
                    lower_bound=target.target_band.lower,
                    upper_bound=target.target_band.upper,
                ),
                loss_scale=loss_scale,
            )
            normalized_iqr = normalize_by_loss_scale(raw_value=p75 - p25, loss_scale=loss_scale)
            metric_loss = compute_metric_loss(
                seed_mean=seed_mean,
                p25=p25,
                p75=p75,
                lower_bound=target.target_band.lower,
                upper_bound=target.target_band.upper,
                inside_rate=inside_rate,
                loss_scale=loss_scale,
            )
            metric_summary.update(
                {
                    "targetBand": {"lower": target.target_band.lower, "upper": target.target_band.upper},
                    "insideRate": inside_rate,
                    "lossScale": loss_scale,
                    "lossScaleBasis": loss_scale_basis,
                    "normalizedDistance": normalized_distance,
                    "normalizedIqr": normalized_iqr,
                    "metricLoss": metric_loss,
                    "status": classify_metric_status(
                        seed_mean=seed_mean,
                        lower_bound=target.target_band.lower,
                        upper_bound=target.target_band.upper,
                        inside_rate=inside_rate,
                    ),
                }
            )
            if target.requirement == "required":
                family_required_losses[target.family_id].append(metric_loss)

        family_status_counts[target.family_id][metric_summary["status"]] += 1
        summary_metrics.append(metric_summary)

    family_summaries = []
    family_losses: dict[str, float] = {}
    for family in FAMILY_DEFINITIONS:
        losses = family_required_losses[family.family_id]
        if not losses:
            raise RuntimeError(f"Missing required metrics for family {family.family_id}")
        family_loss = float(np.mean(losses))
        family_losses[family.family_id] = family_loss
        family_summaries.append(
            {
                "familyId": family.family_id,
                "label": family.label,
                "loss": family_loss,
                "statusCounts": family_status_counts[family.family_id],
            }
        )

    return {
        "schemaVersion": VALIDATION_SCHEMA_VERSION,
        "version": version,
        "generatedAt": _utc_now_iso(),
        "seeds": list(seeds),
        "window": {
            "startIndex": VALIDATION_WINDOW_START,
            "endIndex": VALIDATION_WINDOW_END,
        },
        "overallCompositeLoss": compute_overall_composite_loss(
            macro_credit_activity_loss=family_losses[FAMILY_MACRO_CREDIT_ACTIVITY],
            macro_prices_leverage_affordability_loss=family_losses[FAMILY_MACRO_PRICES_LEVERAGE_AFFORDABILITY],
            household_distribution_realism_loss=family_losses[FAMILY_HOUSEHOLD_DISTRIBUTION_REALISM],
        ),
        "familySummaries": family_summaries,
        "metrics": summary_metrics,
    }


def _extract_seed_metrics(*, seed_output_dir: Path, was_data_root: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for metric in TARGETS_BY_ID.values():
        if metric.kind == "core_indicator":
            if not metric.file_name:
                raise RuntimeError(f"Missing core-indicator file mapping for {metric.metric_id}")
            metrics[metric.metric_id] = extract_core_indicator_mean(
                seed_output_dir / metric.file_name,
                scale=metric.scale,
            )
        elif metric.kind == "household_jsd":
            metrics[metric.metric_id] = extract_household_metric_from_results(
                metric_id=metric.metric_id,
                results_dir=seed_output_dir,
                was_data_root=was_data_root,
            )
        else:
            raise RuntimeError(f"Unsupported metric kind for {metric.metric_id}: {metric.kind}")
    return metrics


def _metric_seed_values(*, metric_id: str, seed_results: Sequence[dict[str, object]]) -> list[float]:
    values: list[float] = []
    for seed_result in seed_results:
        metrics = seed_result["metrics"]
        if metric_id not in metrics:
            raise RuntimeError(f"Missing metric {metric_id} in seed {seed_result['seed']}")
        values.append(float(metrics[metric_id]))
    return values


def _ordered_metric_ids(*, seed_results: Sequence[dict[str, object]], target_lookup: Mapping[str, object]) -> list[str]:
    seen = set()
    ordered = []
    for metric in TARGETS_BY_ID.values():
        if metric.metric_id in target_lookup:
            ordered.append(metric.metric_id)
            seen.add(metric.metric_id)
    for seed_result in seed_results:
        for metric_id in seed_result["metrics"].keys():
            if metric_id not in seen:
                if metric_id not in target_lookup:
                    raise RuntimeError(f"Missing target metadata for required metric {metric_id}")
                ordered.append(metric_id)
                seen.add(metric_id)
    return ordered


def _coerce_target_definition(metric_id: str, raw_target: object | None) -> MetricDefinition:
    if raw_target is None:
        raise RuntimeError(f"Missing target metadata for required metric {metric_id}")
    if isinstance(raw_target, MetricDefinition):
        return raw_target
    if not isinstance(raw_target, Mapping):
        raise RuntimeError(f"Missing target metadata for required metric {metric_id}")

    required_fields = {"metric_id", "family_id", "label", "requirement", "units", "source_label", "kind"}
    missing_fields = sorted(field for field in required_fields if field not in raw_target)
    if missing_fields:
        raise RuntimeError(f"Missing target metadata for required metric {metric_id}: {missing_fields}")

    target_band = raw_target.get("target_band")
    return MetricDefinition(
        metric_id=str(raw_target["metric_id"]),
        family_id=str(raw_target["family_id"]),
        label=str(raw_target["label"]),
        requirement=str(raw_target["requirement"]),
        units=str(raw_target["units"]),
        source_label=str(raw_target["source_label"]),
        kind=str(raw_target["kind"]),
        source_metadata=_coerce_source_metadata(raw_target.get("source_metadata")),
        target_band=target_band,
        file_name=raw_target.get("file_name"),
        legacy_validation_module=raw_target.get("legacy_validation_module"),
    )


def _inside_rate(*, seed_values: Sequence[float], lower: float, upper: float) -> float:
    inside = sum(1 for value in seed_values if lower <= value <= upper)
    return inside / len(seed_values)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_source_metadata(raw_source_metadata: object | None) -> MetricSourceMetadata | None:
    if raw_source_metadata is None:
        return None
    if isinstance(raw_source_metadata, MetricSourceMetadata):
        return raw_source_metadata
    if not isinstance(raw_source_metadata, Mapping):
        raise RuntimeError("Invalid source metadata object")
    return MetricSourceMetadata(
        source_document_path=str(raw_source_metadata["source_document_path"]),
        source_text_path=str(raw_source_metadata["source_text_path"]),
        source_table=str(raw_source_metadata["source_table"]),
        source_page=int(raw_source_metadata["source_page"]),
        source_indicator_label=str(raw_source_metadata["source_indicator_label"]),
        raw_source_value=(
            None if raw_source_metadata.get("raw_source_value") is None else float(raw_source_metadata["raw_source_value"])
        ),
        normalized_source_value=(
            None
            if raw_source_metadata.get("normalized_source_value") is None
            else float(raw_source_metadata["normalized_source_value"])
        ),
        source_units=str(raw_source_metadata["source_units"]),
        comparison_units=str(raw_source_metadata["comparison_units"]),
        source_as_of=(
            None if raw_source_metadata.get("source_as_of") is None else str(raw_source_metadata["source_as_of"])
        ),
        mapping_status=str(raw_source_metadata["mapping_status"]),
        band_method=(
            None if raw_source_metadata.get("band_method") is None else str(raw_source_metadata["band_method"])
        ),
        band_notes=None if raw_source_metadata.get("band_notes") is None else str(raw_source_metadata["band_notes"]),
        source_references=tuple(
            _coerce_source_reference(raw_source_reference)
            for raw_source_reference in raw_source_metadata.get("source_references", ())
        ),
    )


def _coerce_source_reference(raw_source_reference: object) -> MetricSourceReference:
    if isinstance(raw_source_reference, MetricSourceReference):
        return raw_source_reference
    if not isinstance(raw_source_reference, Mapping):
        raise RuntimeError("Invalid source reference object")
    return MetricSourceReference(
        label=str(raw_source_reference["label"]),
        source_document_path=str(raw_source_reference["source_document_path"]),
        source_text_path=(
            None
            if raw_source_reference.get("source_text_path") is None
            else str(raw_source_reference["source_text_path"])
        ),
        source_table=(
            None if raw_source_reference.get("source_table") is None else str(raw_source_reference["source_table"])
        ),
        source_page=(
            None if raw_source_reference.get("source_page") is None else int(raw_source_reference["source_page"])
        ),
        source_indicator_label=(
            None
            if raw_source_reference.get("source_indicator_label") is None
            else str(raw_source_reference["source_indicator_label"])
        ),
        raw_source_value=(
            None if raw_source_reference.get("raw_source_value") is None else float(raw_source_reference["raw_source_value"])
        ),
        source_as_of=(
            None if raw_source_reference.get("source_as_of") is None else str(raw_source_reference["source_as_of"])
        ),
        source_units=(
            None if raw_source_reference.get("source_units") is None else str(raw_source_reference["source_units"])
        ),
        notes=None if raw_source_reference.get("notes") is None else str(raw_source_reference["notes"]),
    )


def _serialize_source_reference(reference: MetricSourceReference) -> dict[str, object]:
    return {
        "label": reference.label,
        "sourceDocumentPath": reference.source_document_path,
        "sourceTextPath": reference.source_text_path,
        "sourceTable": reference.source_table,
        "sourcePage": reference.source_page,
        "sourceIndicatorLabel": reference.source_indicator_label,
        "rawSourceValue": reference.raw_source_value,
        "sourceAsOf": reference.source_as_of,
        "sourceUnits": reference.source_units,
        "notes": reference.notes,
    }
