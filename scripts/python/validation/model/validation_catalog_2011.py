"""Version-gated 2011 validation catalog for the original v0 baseline.

Macro source constants that still need a 2011 audit intentionally inherit the
locked 2024 metric definitions for now. Keep future 2011 replacements in this
module so the runner/profile wiring does not need to change again.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import replace

from scripts.python.validation.model.validation_catalog_2024 import (
    TARGET_CATALOG as TARGET_CATALOG_2024,
)

WAS_WAVE_3_SOURCE_LABEL = "WAS Wave 3"


def _coerce_2011_metric(metric):
    if metric.kind == "household_jsd":
        return replace(metric, source_label=WAS_WAVE_3_SOURCE_LABEL)
    return replace(metric)


TARGET_CATALOG = tuple(_coerce_2011_metric(metric) for metric in TARGET_CATALOG_2024)
TARGETS_BY_ID = {metric.metric_id: metric for metric in TARGET_CATALOG}

__all__ = [
    "TARGET_CATALOG",
    "TARGETS_BY_ID",
    "WAS_WAVE_3_SOURCE_LABEL",
]
