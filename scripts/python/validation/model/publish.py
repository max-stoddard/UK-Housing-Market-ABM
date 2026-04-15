"""Publish validation summaries and transient artifacts.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Sequence


def write_validation_summary(*, repo_root: Path, summary: dict) -> Path:
    """Write the tracked dashboard-facing validation summary JSON."""

    validation_dir = repo_root / "input-data-versions" / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    output_path = validation_dir / f"{summary['version']}.json"
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return output_path


def write_transient_artifacts(*, output_dir: Path, summary: dict, seed_results: Sequence[dict]) -> None:
    """Write transient validation artifacts for manual inspection."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    _write_metrics_csv(output_dir / "validation_metrics.csv", summary["metrics"])
    _write_seed_results_csv(output_dir / "validation_seed_results.csv", seed_results)
    _write_summary_markdown(output_dir / "validation_summary.md", summary)


def _write_metrics_csv(path: Path, metrics: Sequence[dict]) -> None:
    fieldnames = [
        "metricId",
        "familyId",
        "label",
        "requirement",
        "status",
        "units",
        "sourceLabel",
        "sourceIndicatorLabel",
        "sourceDocumentPath",
        "sourceTextPath",
        "sourceTable",
        "sourcePage",
        "rawSourceValue",
        "sourceValue",
        "sourceAsOf",
        "sourceUnits",
        "comparisonUnits",
        "mappingStatus",
        "bandMethod",
        "bandNotes",
        "sourceReferencesJson",
        "targetLower",
        "targetUpper",
        "seedMean",
        "p25",
        "p75",
        "insideRate",
        "normalizedDistance",
        "normalizedIqr",
        "metricLoss",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for metric in metrics:
            target_band = metric.get("targetBand") or {}
            writer.writerow(
                {
                    "metricId": metric["metricId"],
                    "familyId": metric["familyId"],
                    "label": metric["label"],
                    "requirement": metric["requirement"],
                    "status": metric["status"],
                    "units": metric["units"],
                    "sourceLabel": metric["sourceLabel"],
                    "sourceIndicatorLabel": metric.get("sourceIndicatorLabel"),
                    "sourceDocumentPath": metric.get("sourceDocumentPath"),
                    "sourceTextPath": metric.get("sourceTextPath"),
                    "sourceTable": metric.get("sourceTable"),
                    "sourcePage": metric.get("sourcePage"),
                    "rawSourceValue": metric.get("rawSourceValue"),
                    "sourceValue": metric.get("sourceValue"),
                    "sourceAsOf": metric.get("sourceAsOf"),
                    "sourceUnits": metric.get("sourceUnits"),
                    "comparisonUnits": metric.get("comparisonUnits"),
                    "mappingStatus": metric.get("mappingStatus"),
                    "bandMethod": metric.get("bandMethod"),
                    "bandNotes": metric.get("bandNotes"),
                    "sourceReferencesJson": json.dumps(metric.get("sourceReferences", []), sort_keys=False),
                    "targetLower": target_band.get("lower"),
                    "targetUpper": target_band.get("upper"),
                    "seedMean": metric.get("seedMean"),
                    "p25": metric.get("p25"),
                    "p75": metric.get("p75"),
                    "insideRate": metric.get("insideRate"),
                    "normalizedDistance": metric.get("normalizedDistance"),
                    "normalizedIqr": metric.get("normalizedIqr"),
                    "metricLoss": metric.get("metricLoss"),
                }
            )


def _write_seed_results_csv(path: Path, seed_results: Sequence[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["seed", "metricId", "value", "outputDir"])
        writer.writeheader()
        for seed_result in seed_results:
            metrics = seed_result["metrics"]
            for metric_id, value in metrics.items():
                writer.writerow(
                    {
                        "seed": seed_result["seed"],
                        "metricId": metric_id,
                        "value": value,
                        "outputDir": seed_result.get("outputDir", ""),
                    }
                )


def _write_summary_markdown(path: Path, summary: dict) -> None:
    lines = [
        f"# Validation Summary: {summary['version']}",
        "",
        f"- Generated at: {summary['generatedAt']}",
        f"- Seeds: {', '.join(str(seed) for seed in summary['seeds'])}",
        f"- Overall composite loss: {summary['overallCompositeLoss']:.6f}",
        "",
        "## Families",
    ]
    for family in summary["familySummaries"]:
        counts = family["statusCounts"]
        lines.append(
            f"- {family['label']}: loss={family['loss']:.6f}, "
            f"pass={counts['pass']}, warn={counts['warn']}, fail={counts['fail']}, unsupported={counts['unsupported']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
