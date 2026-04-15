"""Schema types for the 2024 validation framework.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ValidationStatus = Literal["pass", "warn", "fail", "unsupported"]
MetricRequirement = Literal["required", "diagnostic"]
MetricKind = Literal["core_indicator", "household_jsd"]
MappingStatus = Literal["exact_match", "derived_match", "unsupported"]

VALIDATION_SCHEMA_VERSION = 1
VALIDATION_WINDOW_START = 200
VALIDATION_WINDOW_END = 2000
CANONICAL_VALIDATION_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)

FAMILY_MACRO_CREDIT_ACTIVITY = "macro_credit_activity"
FAMILY_MACRO_PRICES_LEVERAGE_AFFORDABILITY = "macro_prices_leverage_affordability"
FAMILY_HOUSEHOLD_DISTRIBUTION_REALISM = "household_distribution_realism"


@dataclass(frozen=True)
class TargetBand:
    """An acceptable 2024 target interval for one metric."""

    lower: float
    upper: float

    def width(self) -> float:
        width = self.upper - self.lower
        if width <= 0.0:
            raise ValueError(f"Target band must have positive width, got {self.lower}..{self.upper}")
        return width


@dataclass(frozen=True)
class MetricDefinition:
    """One metric in the locked 2024 validation catalog."""

    metric_id: str
    family_id: str
    label: str
    requirement: MetricRequirement
    units: str
    source_label: str
    kind: MetricKind
    source_metadata: "MetricSourceMetadata | None" = None
    target_band: TargetBand | None = None
    file_name: str | None = None
    legacy_validation_module: str | None = None
    scale: float = 1.0


@dataclass(frozen=True)
class FamilyDefinition:
    """One scored family in the validation framework."""

    family_id: str
    label: str
    weight: float


@dataclass(frozen=True)
class MetricSourceMetadata:
    """Locked provenance for one validation target."""

    source_document_path: str
    source_text_path: str
    source_table: str
    source_page: int
    source_indicator_label: str
    raw_source_value: float | None
    normalized_source_value: float | None
    source_units: str
    comparison_units: str
    source_as_of: str | None
    mapping_status: MappingStatus
    band_method: str | None = None
    band_notes: str | None = None
    source_references: tuple["MetricSourceReference", ...] = ()


@dataclass(frozen=True)
class MetricSourceReference:
    """One concrete supporting source reference for a validation target."""

    label: str
    source_document_path: str
    source_text_path: str | None = None
    source_table: str | None = None
    source_page: int | None = None
    source_indicator_label: str | None = None
    raw_source_value: float | None = None
    source_as_of: str | None = None
    source_units: str | None = None
    notes: str | None = None
