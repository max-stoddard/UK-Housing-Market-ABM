"""Compatibility wrapper for June 2024 FPC validation metadata.

@author: Max Stoddard
"""

from __future__ import annotations

from scripts.python.validation.model.validation_catalog_2024 import (
    FPC_SOURCE_2024_BY_METRIC_ID,
    SUPPORTED_FPC_METRIC_IDS,
    UNSUPPORTED_FPC_METRIC_IDS,
)

__all__ = [
    "FPC_SOURCE_2024_BY_METRIC_ID",
    "SUPPORTED_FPC_METRIC_IDS",
    "UNSUPPORTED_FPC_METRIC_IDS",
]
