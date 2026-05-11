"""Snapshot-local runner and summary builder for tracked validation and references.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from scripts.python.helpers.common.abm_policy_sweep import (
    build_snapshot_local_config_text,
    ensure_project_compiled,
    resolve_maven_bin,
)
from scripts.python.validation.model.extractors import (
    extract_core_indicator_mean,
    extract_household_metric_from_results,
    extract_output_series_metric_from_results,
)
from scripts.python.validation.model.publish import (
    write_transient_artifacts,
    write_validation_overlay_summary,
    write_validation_summary,
)
from scripts.python.validation.model.schema import (
    CANONICAL_VALIDATION_SEEDS,
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
from scripts.python.validation.model.validation_profiles import (
    ValidationProfile,
    resolve_reference_validation_profile,
    resolve_validation_profile,
)

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

REFERENCE_ARTIFACT_DIRNAME = "reference-2011"
REFERENCE_OVERLAY_SUFFIX = "2011"


def reference_overlay_name(version: str) -> str:
    """Return the dashboard overlay name for one v0-family 2011 reference summary."""

    normalized_version = version.strip().lower()
    if not normalized_version:
        raise ValueError("version must not be empty")
    return f"{normalized_version}-{REFERENCE_OVERLAY_SUFFIX}"


def _reference_artifact_label(version: str) -> str:
    return f"Tracked 8-seed {version} validation outputs rescored against the v0-only 2011 reference catalog"


def run_validation_for_version(
    *,
    repo_root: Path,
    version: str,
    seeds: list[int],
    output_dir: Path,
    maven_bin: str | None = None,
    was_data_root: Path | None = None,
    reuse_existing_output: bool = False,
    workers: int = 20,
    allow_test_override: bool = False,
) -> dict:
    """Run canonical validation for one input-data version and publish artifacts."""

    canonical_seeds = list(CANONICAL_VALIDATION_SEEDS)
    if seeds != canonical_seeds and not allow_test_override:
        raise ValueError("Canonical validation requires seeds 1..8 unless an explicit test-only override is used")
    if workers <= 0:
        raise ValueError("workers must be positive")

    validation_profile = resolve_validation_profile(version)
    resolved_was_data_root = resolve_was_data_root(repo_root=repo_root, explicit_root=was_data_root)
    if reuse_existing_output:
        run_results = load_reused_validation_results(
            output_dir=output_dir,
            seeds=seeds,
            was_data_root=resolved_was_data_root,
            validation_profile=validation_profile,
        )
    else:
        resolved_maven_bin = resolve_maven_bin(repo_root, maven_bin)
        run_results = run_snapshot_local_validation(
            repo_root=repo_root,
            version=version,
            seeds=seeds,
            output_dir=output_dir,
            maven_bin=resolved_maven_bin,
            was_data_root=resolved_was_data_root,
            validation_profile=validation_profile,
            workers=workers,
        )
    return publish_validation_results(
        repo_root=repo_root,
        version=version,
        seeds=seeds,
        output_dir=output_dir,
        run_results=run_results,
        validation_profile=validation_profile,
        was_data_root=resolved_was_data_root,
    )


def publish_reference_validation_only(
    *,
    repo_root: Path,
    version: str,
    seeds: Sequence[int],
    output_dir: Path,
    was_data_root: Path | None = None,
) -> dict:
    """Publish only the optional 2011 reference overlay from existing seed output directories."""

    reference_profile = resolve_reference_validation_profile(version)
    if reference_profile is None:
        raise RuntimeError(f"No 2011 reference validation profile is available for {version}")

    resolved_was_data_root = resolve_was_data_root(repo_root=repo_root, explicit_root=was_data_root)
    reference_seed_results = _extract_reference_seed_results_from_output_dir(
        output_dir=output_dir,
        seeds=seeds,
        was_data_root=resolved_was_data_root,
        reference_profile=reference_profile,
    )
    return _write_reference_validation_artifacts(
        repo_root=repo_root,
        version=version,
        output_dir=output_dir,
        reference_seed_results=reference_seed_results,
        reference_profile=reference_profile,
    )


def publish_validation_results(
    *,
    repo_root: Path,
    version: str,
    seeds: Sequence[int],
    output_dir: Path,
    run_results: Sequence[dict[str, object]],
    validation_profile: ValidationProfile | None = None,
    was_data_root: Path | None = None,
) -> dict:
    """Publish tracked and transient outputs after all seed runs succeed."""

    returned_seeds = sorted(int(result["seed"]) for result in run_results)
    if returned_seeds != sorted(seeds):
        raise ValueError("Tracked publication requires 8/8 successful seeds before publishing tracked JSON")

    resolved_profile = validation_profile or resolve_validation_profile(version)
    summary = build_validation_summary(
        version=version,
        seed_results=run_results,
        seeds=seeds,
        validation_profile=resolved_profile,
    )
    write_transient_artifacts(output_dir=output_dir, summary=summary, seed_results=run_results)
    write_validation_summary(repo_root=repo_root, summary=summary)
    publish_reference_validation_artifacts(
        repo_root=repo_root,
        version=version,
        output_dir=output_dir,
        run_results=run_results,
        was_data_root=was_data_root,
    )
    return summary


def run_snapshot_local_validation(
    *,
    repo_root: Path,
    version: str,
    seeds: Sequence[int],
    output_dir: Path,
    maven_bin: str,
    was_data_root: Path,
    validation_profile: ValidationProfile,
    workers: int,
) -> list[dict[str, object]]:
    """Execute the Java model snapshot-locally for each seed and extract metrics."""

    version_config_path = repo_root / "input-data-versions" / version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    ensure_project_compiled(repo_root, maven_bin=maven_bin)
    configs_dir = output_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    if workers <= 1:
        seed_results: list[dict[str, object]] = []
        for seed in seeds:
            seed_results.append(
                run_validation_seed(
                    repo_root=repo_root,
                    version=version,
                    seed=seed,
                    output_dir=output_dir,
                    maven_bin=maven_bin,
                    was_data_root=was_data_root,
                    validation_profile=validation_profile,
                )
            )
        return seed_results

    worker_results: dict[int, dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="validation-worker") as executor:
        futures = {
            executor.submit(
                run_validation_seed,
                repo_root=repo_root,
                version=version,
                seed=seed,
                output_dir=output_dir,
                maven_bin=maven_bin,
                was_data_root=was_data_root,
                validation_profile=validation_profile,
            ): seed
            for seed in seeds
        }

        for future in as_completed(futures):
            seed = futures[future]
            worker_results[seed] = future.result()

    return [worker_results[seed] for seed in seeds]


def run_validation_seed(
    *,
    repo_root: Path,
    version: str,
    seed: int,
    output_dir: Path,
    maven_bin: str,
    was_data_root: Path,
    validation_profile: ValidationProfile,
) -> dict[str, object]:

    """Run one snapshot-local validation seed and return its extracted metrics."""

    version_config_path = repo_root / "input-data-versions" / version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    seed_output_dir = output_dir / f"seed-{seed}"
    if seed_output_dir.exists():
        shutil.rmtree(seed_output_dir)
    seed_output_dir.mkdir(parents=True, exist_ok=True)
    configs_dir = output_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    overrides = dict(VALIDATION_RECORDING_OVERRIDES)
    overrides["SEED"] = str(seed)
    config_text = build_snapshot_local_config_text(version_config_path, overrides)
    config_path = configs_dir / f"seed-{seed}.properties"
    config_path.write_text(config_text, encoding="utf-8")

    exec_args = f'-configFile "{config_path}" -outputFolder "{seed_output_dir}" -dev'
    _log_validation_run_start(
        version=version,
        seed=seed,
    )
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
        "metrics": _extract_seed_metrics(
            seed_output_dir=seed_output_dir,
            was_data_root=was_data_root,
            validation_profile=validation_profile,
        ),
    }



def load_reused_validation_results(
    *,
    output_dir: Path,
    seeds: Sequence[int],
    was_data_root: Path,
    validation_profile: ValidationProfile,
) -> list[dict[str, object]]:
    """Reuse existing per-seed outputs instead of rerunning the model."""

    cached_seed_results = _load_cached_seed_results(output_dir)
    seed_results: list[dict[str, object]] = []
    for seed in seeds:
        seed_output_dir = output_dir / f"seed-{seed}"
        if not seed_output_dir.exists():
            raise RuntimeError(f"Missing existing validation output directory: {seed_output_dir}")
        cached_entry = cached_seed_results.get(seed)
        metrics = dict(cached_entry["metrics"]) if cached_entry is not None else {}
        missing_metric_ids = [
            metric_id for metric_id in validation_profile.targets_by_id if metric_id not in metrics
        ]
        if missing_metric_ids:
            metrics.update(
                _extract_seed_metrics(
                    seed_output_dir=seed_output_dir,
                    was_data_root=was_data_root,
                    metric_ids=missing_metric_ids,
                    validation_profile=validation_profile,
                )
            )
        seed_results.append(
            {
                "seed": seed,
                "outputDir": cached_entry["outputDir"] if cached_entry is not None else str(seed_output_dir),
                "metrics": metrics,
            }
        )
    return seed_results




def _log_validation_run_start(
    *,
    version: str,
    seed: int,
) -> None:
    worker_name = threading.current_thread().name
    print(
        f"[validation] version={version} seed={seed} worker={worker_name}",
        flush=True,
    )


def resolve_was_data_root(*, repo_root: Path, explicit_root: Path | None) -> Path:
    """Resolve a usable WAS data root for a normal checkout or a git worktree."""

    if explicit_root is not None:
        return explicit_root

    dataset_candidates = (
        Path("private-datasets/was/was_round_8_hhold_eul_may_2025.privdata"),
        Path("private-datasets/was/was_wave_3_hhold_eul_final.dta"),
    )
    candidates = [repo_root]
    candidates.extend(repo_root.parents[:3])
    for candidate in candidates:
        if any((candidate / dataset_path).exists() for dataset_path in dataset_candidates):
            return candidate
    return repo_root


def build_validation_summary(
    *,
    version: str,
    seed_results: Sequence[dict[str, object]],
    seeds: Sequence[int],
    validation_profile: ValidationProfile | None = None,
    targets_by_id: Mapping[str, object] | None = None,
) -> dict:
    """Build the dashboard-facing summary JSON from per-seed metric values."""

    if len(seed_results) != len(seeds):
        raise ValueError("Tracked publication requires 8/8 successful seeds before publishing tracked JSON")

    resolved_profile = validation_profile or resolve_validation_profile(version)
    target_lookup = targets_by_id or resolved_profile.targets_by_id
    metric_ids = _ordered_metric_ids(
        seed_results=seed_results,
        target_lookup=target_lookup,
        target_catalog=resolved_profile.target_catalog,
    )
    summary_metrics: list[dict] = []
    scored_metric_losses: list[float] = []
    scored_metric_weights: list[float] = []

    for metric_id in metric_ids:
        target = _coerce_target_definition(metric_id, target_lookup.get(metric_id))
        seed_values = _metric_seed_values(metric_id=metric_id, seed_results=seed_results)
        seed_mean = float(np.mean(seed_values))
        p25 = float(np.percentile(seed_values, 25))
        p75 = float(np.percentile(seed_values, 75))

        metric_summary = {
            "metricId": target.metric_id,
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
            "metricWeight": 0.0,
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
                metric_summary["metricWeight"] = 1.0
                scored_metric_losses.append(metric_loss)
                scored_metric_weights.append(1.0)

        summary_metrics.append(metric_summary)

    if not scored_metric_losses:
        raise RuntimeError("Missing required metric losses for overall composite scoring")

    summary = {
        "schemaVersion": VALIDATION_SCHEMA_VERSION,
        "version": version,
        "validationTargetYear": resolved_profile.validation_target_year,
        "generatedAt": _utc_now_iso(),
        "seeds": list(seeds),
        "window": {
            "startIndex": VALIDATION_WINDOW_START,
            "endIndex": VALIDATION_WINDOW_END,
        },
        "overallCompositeLoss": compute_overall_composite_loss(
            metric_losses=scored_metric_losses,
            metric_weights=scored_metric_weights,
        ),
        "metrics": summary_metrics,
    }
    return summary


def _extract_seed_metrics(
    *,
    seed_output_dir: Path,
    was_data_root: Path,
    validation_profile: ValidationProfile,
    metric_ids: Sequence[str] | None = None,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    selected_metric_ids = (
        list(metric_ids) if metric_ids is not None else list(validation_profile.targets_by_id.keys())
    )
    for metric_id in selected_metric_ids:
        metric = validation_profile.targets_by_id[metric_id]
        if metric.kind == "core_indicator":
            if not metric.file_name:
                raise RuntimeError(f"Missing core-indicator file mapping for {metric.metric_id}")
            metrics[metric.metric_id] = extract_core_indicator_mean(
                seed_output_dir / metric.file_name,
                scale=metric.scale,
            )
        elif metric.kind == "output_series":
            metrics[metric.metric_id] = extract_output_series_metric_from_results(
                metric_id=metric.metric_id,
                results_dir=seed_output_dir,
                trailing_months=validation_profile.output_series_trailing_months_by_metric.get(metric.metric_id),
            )
        elif metric.kind == "household_jsd":
            metrics[metric.metric_id] = extract_household_metric_from_results(
                metric_id=metric.metric_id,
                results_dir=seed_output_dir,
                was_data_root=was_data_root,
                was_dataset=validation_profile.was_dataset,
            )
        else:
            raise RuntimeError(f"Unsupported metric kind for {metric.metric_id}: {metric.kind}")
    return metrics


def _load_cached_seed_results(output_dir: Path) -> dict[int, dict[str, object]]:
    seed_results_path = output_dir / "validation_seed_results.csv"
    if not seed_results_path.exists():
        return {}

    cached: dict[int, dict[str, object]] = {}
    with seed_results_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            seed = int(row["seed"])
            cached.setdefault(
                seed,
                {
                    "outputDir": row.get("outputDir") or str(output_dir / f"seed-{seed}"),
                    "metrics": {},
                },
            )
            cached[seed]["metrics"][row["metricId"]] = float(row["value"])
    return cached


def _metric_seed_values(*, metric_id: str, seed_results: Sequence[dict[str, object]]) -> list[float]:
    values: list[float] = []
    for seed_result in seed_results:
        metrics = seed_result["metrics"]
        if metric_id not in metrics:
            raise RuntimeError(f"Missing metric {metric_id} in seed {seed_result['seed']}")
        values.append(float(metrics[metric_id]))
    return values


def score_existing_summary_against_targets(
    *,
    summary: Mapping[str, object],
    targets_by_id: Mapping[str, object],
    target_catalog: Sequence[MetricDefinition] | None = None,
) -> float:
    """Rescore an existing tracked summary against the supplied validation targets."""

    raw_metrics = summary.get("metrics")
    if not isinstance(raw_metrics, Sequence):
        raise RuntimeError("Existing validation summary is missing metrics")

    metrics_by_id = {
        str(metric["metricId"]): metric for metric in raw_metrics if isinstance(metric, Mapping) and "metricId" in metric
    }
    metric_ids = _ordered_metric_ids(
        seed_results=(),
        target_lookup=targets_by_id,
        target_catalog=target_catalog,
        metrics_by_id=metrics_by_id,
    )
    scored_metric_losses: list[float] = []
    scored_metric_weights: list[float] = []

    for metric_id in metric_ids:
        target = _coerce_target_definition(metric_id, targets_by_id.get(metric_id))
        if target.requirement != "required":
            continue
        if target.target_band is None:
            raise RuntimeError(f"Missing target metadata for required metric {target.metric_id}")

        existing_metric = metrics_by_id.get(metric_id)
        if existing_metric is None:
            raise RuntimeError(f"Existing validation summary is missing metric {metric_id}")

        if existing_metric.get("insideRate") is None:
            raise RuntimeError(f"Existing validation summary is missing insideRate for {metric_id}")

        loss_scale, _ = resolve_loss_scale(
            source_value=target.source_metadata.normalized_source_value if target.source_metadata else None,
            lower_bound=target.target_band.lower,
            upper_bound=target.target_band.upper,
        )
        scored_metric_losses.append(
            compute_metric_loss(
                seed_mean=float(existing_metric["seedMean"]),
                p25=float(existing_metric["p25"]),
                p75=float(existing_metric["p75"]),
                lower_bound=target.target_band.lower,
                upper_bound=target.target_band.upper,
                inside_rate=float(existing_metric["insideRate"]),
                loss_scale=loss_scale,
            )
        )
        scored_metric_weights.append(1.0)

    return compute_overall_composite_loss(
        metric_losses=scored_metric_losses,
        metric_weights=scored_metric_weights,
    )


def publish_reference_validation_artifacts(
    *,
    repo_root: Path,
    version: str,
    output_dir: Path,
    run_results: Sequence[dict[str, object]],
    was_data_root: Path | None = None,
) -> dict | None:
    """Publish the tracked v0-family 2011 reference overlay plus transient audit artifacts."""

    reference_profile = resolve_reference_validation_profile(version)
    if reference_profile is None:
        return None

    resolved_was_data_root = resolve_was_data_root(repo_root=repo_root, explicit_root=was_data_root)
    reference_seed_results = _extract_reference_seed_results_from_run_results(
        repo_root=repo_root,
        run_results=run_results,
        was_data_root=resolved_was_data_root,
        reference_profile=reference_profile,
    )
    return _write_reference_validation_artifacts(
        repo_root=repo_root,
        version=version,
        output_dir=output_dir,
        reference_seed_results=reference_seed_results,
        reference_profile=reference_profile,
    )


def _extract_reference_seed_results_from_run_results(
    *,
    repo_root: Path,
    run_results: Sequence[dict[str, object]],
    was_data_root: Path,
    reference_profile: ValidationProfile,
) -> list[dict[str, object]]:
    reference_seed_results: list[dict[str, object]] = []
    for tracked_seed_result in run_results:
        seed = int(tracked_seed_result["seed"])
        seed_output_dir = _resolve_output_dir_path(
            repo_root=repo_root,
            raw_path=str(tracked_seed_result["outputDir"]),
        )
        if not seed_output_dir.exists():
            raise RuntimeError(f"Missing tracked seed output directory for 2011 reference publication: {seed_output_dir}")
        reference_seed_results.append(
            {
                "seed": seed,
                "outputDir": str(seed_output_dir),
                "metrics": _extract_seed_metrics(
                    seed_output_dir=seed_output_dir,
                    was_data_root=was_data_root,
                    validation_profile=reference_profile,
                ),
            }
        )
    return reference_seed_results


def _extract_reference_seed_results_from_output_dir(
    *,
    output_dir: Path,
    seeds: Sequence[int],
    was_data_root: Path,
    reference_profile: ValidationProfile,
) -> list[dict[str, object]]:
    reference_seed_results: list[dict[str, object]] = []
    for seed in seeds:
        seed_output_dir = output_dir / f"seed-{seed}"
        if not seed_output_dir.exists():
            raise RuntimeError(f"Missing existing validation output directory: {seed_output_dir}")
        reference_seed_results.append(
            {
                "seed": seed,
                "outputDir": str(seed_output_dir),
                "metrics": _extract_seed_metrics(
                    seed_output_dir=seed_output_dir,
                    was_data_root=was_data_root,
                    validation_profile=reference_profile,
                ),
            }
        )
    return reference_seed_results


def _write_reference_validation_artifacts(
    *,
    repo_root: Path,
    version: str,
    output_dir: Path,
    reference_seed_results: Sequence[dict[str, object]],
    reference_profile: ValidationProfile,
) -> dict:
    seeds = [int(seed_result["seed"]) for seed_result in reference_seed_results]
    summary = build_validation_summary(
        version=version,
        seed_results=reference_seed_results,
        seeds=seeds,
        validation_profile=reference_profile,
    )
    summary["artifactType"] = "reference_overlay"
    summary["artifactLabel"] = _reference_artifact_label(version)
    summary["referenceSourceOutputDir"] = _display_repo_relative_path(
        repo_root=repo_root,
        path=output_dir,
    )
    write_transient_artifacts(
        output_dir=output_dir / REFERENCE_ARTIFACT_DIRNAME,
        summary=summary,
        seed_results=reference_seed_results,
    )
    write_validation_overlay_summary(
        repo_root=repo_root,
        overlay_name=reference_overlay_name(version),
        summary=summary,
    )
    return summary


def _ordered_metric_ids(
    *,
    seed_results: Sequence[dict[str, object]],
    target_lookup: Mapping[str, object],
    target_catalog: Sequence[MetricDefinition] | None = None,
    metrics_by_id: Mapping[str, object] | None = None,
) -> list[str]:
    seen = set()
    ordered = []
    catalog = target_catalog or tuple(
        _coerce_target_definition(metric_id, raw_target) for metric_id, raw_target in target_lookup.items()
    )
    for metric in catalog:
        if metric.metric_id in target_lookup:
            ordered.append(metric.metric_id)
            seen.add(metric.metric_id)
    if metrics_by_id is not None:
        metric_id_iterables = [metrics_by_id.keys()]
    else:
        metric_id_iterables = [seed_result["metrics"].keys() for seed_result in seed_results]
    for metric_ids in metric_id_iterables:
        for metric_id in metric_ids:
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

    required_fields = {"metric_id", "label", "requirement", "units", "source_label", "kind"}
    missing_fields = sorted(field for field in required_fields if field not in raw_target)
    if missing_fields:
        raise RuntimeError(f"Missing target metadata for required metric {metric_id}: {missing_fields}")

    target_band = raw_target.get("target_band")
    return MetricDefinition(
        metric_id=str(raw_target["metric_id"]),
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


def _display_repo_relative_path(*, repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_output_dir_path(*, repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return repo_root / path
