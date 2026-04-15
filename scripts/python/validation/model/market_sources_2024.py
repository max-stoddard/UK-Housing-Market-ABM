"""Compatibility wrapper for 2024 market validation metadata.

@author: Max Stoddard
"""

from __future__ import annotations

from scripts.python.validation.model.validation_catalog_2024 import (
    INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS,
    MARKET_SOURCE_2024_BY_METRIC_ID,
    OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES,
    RENTAL_YIELD_2024_QUARTERLY_VALUES,
)

__all__ = [
    "INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS",
    "MARKET_SOURCE_2024_BY_METRIC_ID",
    "OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES",
    "RENTAL_YIELD_2024_QUARTERLY_VALUES",
]
