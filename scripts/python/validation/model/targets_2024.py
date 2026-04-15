"""Compatibility wrapper for the locked 2024 validation target catalog.

@author: Max Stoddard
"""

from __future__ import annotations

from scripts.python.validation.model.validation_catalog_2024 import (
    FAMILY_DEFINITIONS,
    FAMILY_WEIGHTS,
    TARGET_CATALOG,
    TARGETS_BY_ID,
)

__all__ = [
    "FAMILY_DEFINITIONS",
    "FAMILY_WEIGHTS",
    "TARGET_CATALOG",
    "TARGETS_BY_ID",
]
