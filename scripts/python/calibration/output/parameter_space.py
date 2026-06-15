"""Reusable output-calibration parameter spaces.

@author: Max Stoddard
"""

from __future__ import annotations

import itertools
from typing import Mapping, Sequence

from scripts.python.calibration.output.esmda import (
    BTL_CHOICE_INTENSITY,
    BTL_PROBABILITY_MULTIPLIER,
    MARKET_AVERAGE_PRICE_DECAY,
    OUTPUT_ESMDA_PARAMETER_NAMES,
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
    TRANSFORM_BOUNDED_LOGIT,
    TRANSFORM_LOG10,
    ParameterSpec,
)

ORIGINAL_SMM_GRID_VALUES: dict[str, tuple[float, ...]] = {
    PSYCHOLOGICAL_COST_OF_RENTING: (0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
    SENSITIVITY_RENT_OR_PURCHASE: (0.00001, 0.00003162, 0.0001, 0.0003162, 0.001, 0.003162, 0.01, 0.03162, 0.1),
    BTL_PROBABILITY_MULTIPLIER: (1.6, 1.62, 1.64, 1.66, 1.68, 1.7, 1.72, 1.74, 1.76, 1.78, 1.8),
    BTL_CHOICE_INTENSITY: (0.1, 0.3162, 1.0, 3.162, 10.0, 31.62, 100.0, 316.2, 1000.0),
    MARKET_AVERAGE_PRICE_DECAY: (0.1, 0.3, 0.5, 0.7, 0.9),
}

ORIGINAL_SMM_SELECTED_VALUES: dict[str, float] = {
    PSYCHOLOGICAL_COST_OF_RENTING: 0.4,
    SENSITIVITY_RENT_OR_PURCHASE: 0.001,
    BTL_PROBABILITY_MULTIPLIER: 1.76,
    BTL_CHOICE_INTENSITY: 100.0,
    MARKET_AVERAGE_PRICE_DECAY: 0.5,
}

ORIGINAL_SMM_PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        name=PSYCHOLOGICAL_COST_OF_RENTING,
        lower=0.0,
        upper=0.5,
        prior_lower=0.0,
        prior_upper=0.5,
        transform=TRANSFORM_BOUNDED_LOGIT,
    ),
    ParameterSpec(
        name=SENSITIVITY_RENT_OR_PURCHASE,
        lower=0.00001,
        upper=0.1,
        prior_lower=0.00001,
        prior_upper=0.1,
        transform=TRANSFORM_LOG10,
    ),
    ParameterSpec(
        name=BTL_PROBABILITY_MULTIPLIER,
        lower=1.6,
        upper=1.8,
        prior_lower=1.6,
        prior_upper=1.8,
        transform=TRANSFORM_LOG10,
    ),
    ParameterSpec(
        name=BTL_CHOICE_INTENSITY,
        lower=0.1,
        upper=1000.0,
        prior_lower=0.1,
        prior_upper=1000.0,
        transform=TRANSFORM_LOG10,
    ),
    ParameterSpec(
        name=MARKET_AVERAGE_PRICE_DECAY,
        lower=0.1,
        upper=0.9,
        prior_lower=0.1,
        prior_upper=0.9,
        transform=TRANSFORM_BOUNDED_LOGIT,
    ),
)


def original_smm_grid_index_tuples() -> list[tuple[int, ...]]:
    """Return lexicographic index tuples for the original full SMM grid."""

    return list(
        itertools.product(
            *[range(len(ORIGINAL_SMM_GRID_VALUES[name])) for name in OUTPUT_ESMDA_PARAMETER_NAMES]
        )
    )


def original_smm_parameter_set(level_indices: Sequence[int]) -> dict[str, float]:
    """Return one original-grid parameter set from a tuple of level indices."""

    if len(level_indices) != len(OUTPUT_ESMDA_PARAMETER_NAMES):
        raise ValueError("level_indices length does not match output parameter count")
    return {
        name: ORIGINAL_SMM_GRID_VALUES[name][int(index)]
        for name, index in zip(OUTPUT_ESMDA_PARAMETER_NAMES, level_indices, strict=True)
    }


def original_smm_center_indices() -> tuple[int, ...]:
    """Return original-grid indices for the paper-selected v0 parameter values."""

    return tuple(
        ORIGINAL_SMM_GRID_VALUES[name].index(ORIGINAL_SMM_SELECTED_VALUES[name])
        for name in OUTPUT_ESMDA_PARAMETER_NAMES
    )


def grid_center_distance(level_indices: Sequence[int], *, center_indices: Sequence[int] | None = None) -> int:
    """Return Manhattan distance from the original paper-selected grid point."""

    center = tuple(center_indices) if center_indices is not None else original_smm_center_indices()
    if len(level_indices) != len(center):
        raise ValueError("level_indices length does not match center_indices length")
    return sum(abs(int(index) - int(center_index)) for index, center_index in zip(level_indices, center, strict=True))


def parameter_specs_by_name(specs: Sequence[ParameterSpec] = ORIGINAL_SMM_PARAMETER_SPECS) -> dict[str, ParameterSpec]:
    """Return parameter specs keyed by config property name."""

    return {spec.name: spec for spec in specs}


def parameter_values_payload(values: Mapping[str, Sequence[float]]) -> dict[str, list[float]]:
    """Return JSON-serializable parameter-grid values."""

    return {name: [float(value) for value in values[name]] for name in OUTPUT_ESMDA_PARAMETER_NAMES}
