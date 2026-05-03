"""ES-MDA helpers for four-parameter output calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

try:  # pragma: no cover - exercised indirectly when SciPy is unavailable
    from scipy.stats import qmc

    HAVE_SCIPY_QMC = True
except Exception:  # pragma: no cover
    qmc = None
    HAVE_SCIPY_QMC = False


PSYCHOLOGICAL_COST_OF_RENTING = "PSYCHOLOGICAL_COST_OF_RENTING"
SENSITIVITY_RENT_OR_PURCHASE = "SENSITIVITY_RENT_OR_PURCHASE"
BTL_CHOICE_INTENSITY = "BTL_CHOICE_INTENSITY"
MARKET_AVERAGE_PRICE_DECAY = "MARKET_AVERAGE_PRICE_DECAY"

FOUR_PARAMETER_NAMES = (
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
    BTL_CHOICE_INTENSITY,
    MARKET_AVERAGE_PRICE_DECAY,
)

TRANSFORM_BOUNDED_LOGIT = "bounded_logit"
TRANSFORM_LOG10 = "log10"
TRANSFORM_LINEAR = "linear"


@dataclass(frozen=True)
class ParameterSpec:
    """Bounded parameter definition for transformed-space ES-MDA updates."""

    name: str
    lower: float
    upper: float
    prior_lower: float
    prior_upper: float
    transform: str
    final_snap: float | None = None
    final_sigfigs: int | None = None

    def __post_init__(self) -> None:
        if self.lower >= self.upper:
            raise ValueError(f"{self.name}: lower bound must be less than upper bound")
        if not (self.lower <= self.prior_lower <= self.prior_upper <= self.upper):
            raise ValueError(f"{self.name}: prior range must be inside hard bounds")
        if self.transform == TRANSFORM_LOG10 and self.lower <= 0.0:
            raise ValueError(f"{self.name}: log10 transform requires positive lower bound")
        if self.transform not in {TRANSFORM_BOUNDED_LOGIT, TRANSFORM_LOG10, TRANSFORM_LINEAR}:
            raise ValueError(f"{self.name}: unsupported transform {self.transform!r}")

    def clip(self, value: float) -> float:
        """Clip a physical parameter value to hard bounds."""

        return min(self.upper, max(self.lower, float(value)))

    def transform_value(self, value: float) -> float:
        """Map a physical value into the unconstrained ES-MDA update space."""

        clipped = self.clip(value)
        if self.transform == TRANSFORM_LINEAR:
            return clipped
        if self.transform == TRANSFORM_LOG10:
            return math.log10(clipped)

        width = self.upper - self.lower
        eps = max(width * 1.0e-12, 1.0e-15)
        bounded = min(self.upper - eps, max(self.lower + eps, clipped))
        probability = (bounded - self.lower) / width
        return math.log(probability / (1.0 - probability))

    def inverse_transform_value(self, transformed_value: float) -> float:
        """Map an ES-MDA transformed value back to the physical parameter space."""

        transformed = float(transformed_value)
        if self.transform == TRANSFORM_LINEAR:
            return self.clip(transformed)
        if self.transform == TRANSFORM_LOG10:
            return self.clip(10.0**transformed)

        if transformed >= 0.0:
            exp_neg = math.exp(-transformed)
            probability = 1.0 / (1.0 + exp_neg)
        else:
            exp_pos = math.exp(transformed)
            probability = exp_pos / (1.0 + exp_pos)
        return self.clip(self.lower + probability * (self.upper - self.lower))

    def transformed_prior_bounds(self) -> tuple[float, float]:
        """Return prior bounds in transformed space."""

        return (
            self.transform_value(self.prior_lower),
            self.transform_value(self.prior_upper),
        )

    def transformed_hard_bounds(self) -> tuple[float, float]:
        """Return hard bounds in transformed space."""

        return (
            self.transform_value(self.lower),
            self.transform_value(self.upper),
        )

    def normalized_source_movement(self, source_value: float, candidate_value: float) -> float:
        """Distance from source to candidate as a fraction of transformed prior width."""

        prior_lower, prior_upper = self.transformed_prior_bounds()
        width = prior_upper - prior_lower
        if width <= 0.0:
            raise ValueError(f"{self.name}: transformed prior width must be positive")
        return abs(self.transform_value(candidate_value) - self.transform_value(source_value)) / width

    def snap_value(self, value: float) -> float:
        """Snap a selected physical value to the parameter's practical precision."""

        clipped = self.clip(value)
        if self.final_sigfigs is not None:
            return self.clip(_round_sigfigs(clipped, self.final_sigfigs))
        if self.final_snap is not None:
            return self.clip(round(clipped / self.final_snap) * self.final_snap)
        return clipped


DEFAULT_PARAMETER_SPECS = (
    ParameterSpec(
        name=PSYCHOLOGICAL_COST_OF_RENTING,
        lower=0.0,
        upper=0.8,
        prior_lower=0.2,
        prior_upper=0.6,
        transform=TRANSFORM_BOUNDED_LOGIT,
        final_snap=0.05,
    ),
    ParameterSpec(
        name=SENSITIVITY_RENT_OR_PURCHASE,
        lower=0.0001,
        upper=0.002,
        prior_lower=0.0005,
        prior_upper=0.0015,
        transform=TRANSFORM_LOG10,
        final_sigfigs=2,
    ),
    ParameterSpec(
        name=BTL_CHOICE_INTENSITY,
        lower=25.0,
        upper=250.0,
        prior_lower=50.0,
        prior_upper=150.0,
        transform=TRANSFORM_LOG10,
        final_snap=10.0,
    ),
    ParameterSpec(
        name=MARKET_AVERAGE_PRICE_DECAY,
        lower=0.25,
        upper=0.85,
        prior_lower=0.4,
        prior_upper=0.7,
        transform=TRANSFORM_BOUNDED_LOGIT,
        final_snap=0.02,
    ),
)


def specs_by_name(specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS) -> dict[str, ParameterSpec]:
    """Return parameter specs keyed by config property name."""

    return {spec.name: spec for spec in specs}


def make_alpha_schedule(n_assimilations: int, *, inverse_weight_ratio: float = 0.7) -> np.ndarray:
    """Build deterministic ES-MDA inflation factors with ``sum(1 / alpha) == 1``."""

    if n_assimilations <= 0:
        raise ValueError("n_assimilations must be positive")
    if inverse_weight_ratio <= 0.0:
        raise ValueError("inverse_weight_ratio must be positive")

    inverse_weights = np.array(
        [inverse_weight_ratio**index for index in range(n_assimilations)],
        dtype=float,
    )
    inverse_weights /= float(inverse_weights.sum())
    alphas = 1.0 / inverse_weights
    if not np.isclose(float(np.sum(1.0 / alphas)), 1.0):
        raise RuntimeError("ES-MDA alpha schedule failed normalization")
    return alphas


def generate_initial_ensemble(
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
    ensemble_size: int,
    rng_seed: int,
) -> np.ndarray:
    """Generate a deterministic prior ensemble in transformed space."""

    if ensemble_size <= 1:
        raise ValueError("ensemble_size must be greater than one")
    if not specs:
        raise ValueError("At least one parameter spec is required")

    unit_samples = _unit_hypercube_samples(
        ensemble_size=ensemble_size,
        dimensions=len(specs),
        rng_seed=rng_seed,
    )
    ensemble = np.zeros((ensemble_size, len(specs)), dtype=float)
    for column, spec in enumerate(specs):
        lower, upper = spec.transformed_prior_bounds()
        ensemble[:, column] = lower + unit_samples[:, column] * (upper - lower)
    return ensemble


def transformed_matrix_to_parameter_dicts(
    transformed_ensemble: np.ndarray,
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
    snap: bool = False,
) -> list[dict[str, float]]:
    """Convert a transformed ensemble matrix to physical parameter dictionaries."""

    matrix = np.asarray(transformed_ensemble, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(specs):
        raise ValueError("Transformed ensemble shape does not match parameter specs")

    parameter_sets: list[dict[str, float]] = []
    for row in matrix:
        values: dict[str, float] = {}
        for value, spec in zip(row, specs, strict=True):
            physical = spec.inverse_transform_value(float(value))
            values[spec.name] = spec.snap_value(physical) if snap else physical
        parameter_sets.append(values)
    return parameter_sets


def parameter_dicts_to_transformed_matrix(
    parameter_sets: Sequence[Mapping[str, float]],
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> np.ndarray:
    """Convert physical parameter dictionaries to a transformed ensemble matrix."""

    matrix = np.zeros((len(parameter_sets), len(specs)), dtype=float)
    for row_index, parameters in enumerate(parameter_sets):
        for column_index, spec in enumerate(specs):
            if spec.name not in parameters:
                raise KeyError(f"Missing parameter {spec.name!r}")
            matrix[row_index, column_index] = spec.transform_value(float(parameters[spec.name]))
    return matrix


def clip_transformed_ensemble_to_bounds(
    transformed_ensemble: np.ndarray,
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> np.ndarray:
    """Clip an ensemble by converting through physical hard bounds."""

    parameter_sets = transformed_matrix_to_parameter_dicts(transformed_ensemble, specs=specs)
    return parameter_dicts_to_transformed_matrix(parameter_sets, specs=specs)


def esmda_update(
    *,
    transformed_parameters: np.ndarray,
    simulated_observations: np.ndarray,
    observed_vector: np.ndarray,
    observation_error_covariance: np.ndarray,
    alpha: float,
    rng_seed: int,
    perturb_observations: bool = True,
    svd_rcond: float = 1.0e-10,
    ridge: float = 1.0e-10,
) -> np.ndarray:
    """Run one stabilized transformed-space ES-MDA update."""

    x_matrix = np.asarray(transformed_parameters, dtype=float)
    y_matrix = np.asarray(simulated_observations, dtype=float)
    observed = np.asarray(observed_vector, dtype=float)
    covariance = np.asarray(observation_error_covariance, dtype=float)

    if x_matrix.ndim != 2:
        raise ValueError("transformed_parameters must be a 2D matrix")
    if y_matrix.ndim != 2:
        raise ValueError("simulated_observations must be a 2D matrix")
    if x_matrix.shape[0] != y_matrix.shape[0]:
        raise ValueError("Parameter and observation ensembles must have the same row count")
    if y_matrix.shape[1] != observed.shape[0]:
        raise ValueError("Observed vector length does not match simulated observation columns")
    if covariance.shape != (observed.shape[0], observed.shape[0]):
        raise ValueError("Observation covariance shape is inconsistent with observed vector")
    if alpha <= 0.0:
        raise ValueError("alpha must be positive")

    ensemble_size = x_matrix.shape[0]
    if ensemble_size <= 1:
        raise ValueError("ES-MDA update requires at least two ensemble members")

    x_anomalies = x_matrix - np.mean(x_matrix, axis=0)
    y_anomalies = y_matrix - np.mean(y_matrix, axis=0)
    c_xy = x_anomalies.T @ y_anomalies / float(ensemble_size - 1)
    c_yy = y_anomalies.T @ y_anomalies / float(ensemble_size - 1)
    inflated_covariance = c_yy + alpha * covariance
    inflated_covariance += np.eye(inflated_covariance.shape[0]) * ridge
    gain = c_xy @ _stable_pseudo_inverse(inflated_covariance, rcond=svd_rcond)

    if perturb_observations:
        rng = np.random.default_rng(rng_seed)
        perturbations = rng.multivariate_normal(
            mean=np.zeros(observed.shape[0]),
            cov=alpha * covariance,
            size=ensemble_size,
        )
    else:
        perturbations = np.zeros((ensemble_size, observed.shape[0]), dtype=float)

    innovations = observed[None, :] + perturbations - y_matrix
    return x_matrix + innovations @ gain.T


def normalized_source_movement(
    *,
    source_parameters: Mapping[str, float],
    candidate_parameters: Mapping[str, float],
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> float:
    """Compute average transformed-prior movement from source to candidate."""

    movements = [
        spec.normalized_source_movement(
            source_value=float(source_parameters[spec.name]),
            candidate_value=float(candidate_parameters[spec.name]),
        )
        for spec in specs
    ]
    return float(np.mean(movements))


def snap_parameter_set(
    parameters: Mapping[str, float],
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> dict[str, float]:
    """Snap a parameter set to practical reporting precision."""

    return {spec.name: spec.snap_value(float(parameters[spec.name])) for spec in specs}


def _unit_hypercube_samples(*, ensemble_size: int, dimensions: int, rng_seed: int) -> np.ndarray:
    if HAVE_SCIPY_QMC and qmc is not None:
        m_power = int(math.ceil(math.log2(ensemble_size)))
        sampler = qmc.Sobol(d=dimensions, scramble=True, seed=rng_seed)
        return sampler.random_base2(m=m_power)[:ensemble_size]

    rng = np.random.default_rng(rng_seed)
    return rng.random((ensemble_size, dimensions))


def _stable_pseudo_inverse(matrix: np.ndarray, *, rcond: float) -> np.ndarray:
    u_matrix, singular_values, vh_matrix = np.linalg.svd(matrix, full_matrices=False)
    cutoff = rcond * max(matrix.shape) * float(np.max(singular_values))
    inverse_values = np.array(
        [0.0 if value <= cutoff else 1.0 / value for value in singular_values],
        dtype=float,
    )
    return (vh_matrix.T * inverse_values) @ u_matrix.T


def _round_sigfigs(value: float, sigfigs: int) -> float:
    if sigfigs <= 0:
        raise ValueError("sigfigs must be positive")
    if value == 0.0:
        return 0.0
    return round(value, sigfigs - int(math.floor(math.log10(abs(value)))) - 1)


__all__ = [
    "BTL_CHOICE_INTENSITY",
    "DEFAULT_PARAMETER_SPECS",
    "FOUR_PARAMETER_NAMES",
    "MARKET_AVERAGE_PRICE_DECAY",
    "PSYCHOLOGICAL_COST_OF_RENTING",
    "SENSITIVITY_RENT_OR_PURCHASE",
    "ParameterSpec",
    "clip_transformed_ensemble_to_bounds",
    "esmda_update",
    "generate_initial_ensemble",
    "make_alpha_schedule",
    "normalized_source_movement",
    "parameter_dicts_to_transformed_matrix",
    "snap_parameter_set",
    "specs_by_name",
    "transformed_matrix_to_parameter_dicts",
]
