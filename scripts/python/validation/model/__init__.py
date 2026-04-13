"""2024 multi-seed model validation framework.

@author: Max Stoddard
"""

from scripts.python.validation.model.schema import (
    CANONICAL_VALIDATION_SEEDS,
    VALIDATION_SCHEMA_VERSION,
    VALIDATION_WINDOW_END,
    VALIDATION_WINDOW_START,
)
from scripts.python.validation.model.fpc_source_2024 import (
    FPC_SOURCE_2024_BY_METRIC_ID,
    SUPPORTED_FPC_METRIC_IDS,
    UNSUPPORTED_FPC_METRIC_IDS,
)
from scripts.python.validation.model.runner import build_validation_summary, run_validation_for_version
from scripts.python.validation.model.targets_2024 import FAMILY_DEFINITIONS, TARGET_CATALOG, TARGETS_BY_ID

__all__ = [
    "CANONICAL_VALIDATION_SEEDS",
    "FAMILY_DEFINITIONS",
    "FPC_SOURCE_2024_BY_METRIC_ID",
    "SUPPORTED_FPC_METRIC_IDS",
    "TARGET_CATALOG",
    "TARGETS_BY_ID",
    "UNSUPPORTED_FPC_METRIC_IDS",
    "VALIDATION_SCHEMA_VERSION",
    "VALIDATION_WINDOW_END",
    "VALIDATION_WINDOW_START",
    "build_validation_summary",
    "run_validation_for_version",
]
