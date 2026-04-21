"""Validation-profile resolution for version-gated target years.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from scripts.python.helpers.was.config import ROUND_8_DATA, WAVE_3_DATA
from scripts.python.validation.model.schema import MetricDefinition
from scripts.python.validation.model.validation_catalog_2011 import (
    TARGET_CATALOG as TARGET_CATALOG_2011,
    TARGETS_BY_ID as TARGETS_BY_ID_2011,
)
from scripts.python.validation.model.validation_catalog_2024 import (
    TARGET_CATALOG as TARGET_CATALOG_2024,
    TARGETS_BY_ID as TARGETS_BY_ID_2024,
)


@dataclass(frozen=True)
class ValidationProfile:
    """Resolved validation settings for one family of input-data versions."""

    profile_id: str
    validation_target_year: int
    was_dataset: str
    target_catalog: Sequence[MetricDefinition]
    targets_by_id: Mapping[str, MetricDefinition]
    initial_calibration_reference_version: str | None = None
    initial_calibration_reference_label: str | None = None


VALIDATION_PROFILE_2024 = ValidationProfile(
    profile_id="validation-2024",
    validation_target_year=2024,
    was_dataset=ROUND_8_DATA,
    target_catalog=TARGET_CATALOG_2024,
    targets_by_id=TARGETS_BY_ID_2024,
)

VALIDATION_PROFILE_V0_2011 = ValidationProfile(
    profile_id="validation-v0-2011",
    validation_target_year=2011,
    was_dataset=WAVE_3_DATA,
    target_catalog=TARGET_CATALOG_2011,
    targets_by_id=TARGETS_BY_ID_2011,
    initial_calibration_reference_version="v0",
    initial_calibration_reference_label="Original v0 tracked summary rescored against the v0->2011 validation profile",
)


def resolve_validation_profile(version: str) -> ValidationProfile:
    """Resolve the validation profile for one tracked input-data version."""

    normalized_version = version.strip().lower()
    if normalized_version == "v0":
        return VALIDATION_PROFILE_V0_2011
    return VALIDATION_PROFILE_2024


__all__ = [
    "ValidationProfile",
    "VALIDATION_PROFILE_2024",
    "VALIDATION_PROFILE_V0_2011",
    "resolve_validation_profile",
]
