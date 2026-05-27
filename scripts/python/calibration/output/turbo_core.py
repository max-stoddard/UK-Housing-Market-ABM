"""TuRBO-1 helpers for output-parameter calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import numpy as np

from scripts.python.calibration.output.esmda import DEFAULT_PARAMETER_SPECS, ParameterSpec
from scripts.python.calibration.output.validation_bridge import (
    HPI_CONSTRAINED_METRIC_IDS,
    MemberValidationResult,
    hpi_metric_loss_deltas,
    overall_composite_loss,
)

try:
    from scipy.stats import qmc

    HAVE_SCIPY_QMC = True
except Exception:
    qmc = None
    HAVE_SCIPY_QMC = False


DEFAULT_INITIAL_POINTS = 20
DEFAULT_MAX_EVALUATIONS = 120
DEFAULT_RNG_SEED = 20260525
DEFAULT_HPI_PENALTY_WEIGHT = 1.0
DEFAULT_NOISE_VARIANCE_FLOOR = 1.0e-6
DEFAULT_TRUST_REGION_LENGTH = 0.8
DEFAULT_TRUST_REGION_LENGTH_MIN = 0.5**7
DEFAULT_TRUST_REGION_LENGTH_MAX = 1.6
DEFAULT_SUCCESS_TOLERANCE = 10


@dataclass(frozen=True)
class TurboDependencyBundle:
    torch: object
    botorch: object
    gpytorch: object
    versions: dict[str, str]


@dataclass(frozen=True)
class TurboState:
    length: float = DEFAULT_TRUST_REGION_LENGTH
    success_counter: int = 0
    failure_counter: int = 0
    restart_triggered: bool = False
    best_score: float = -math.inf
    evaluated_candidate_count: int = 0


def load_turbo_dependencies() -> TurboDependencyBundle:
    missing: list[str] = []
    modules: dict[str, object] = {}
    for name in ("torch", "botorch", "gpytorch"):
        try:
            modules[name] = importlib.import_module(name)
        except Exception:
            missing.append(name)
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Missing TuRBO optimizer dependencies: "
            f"{joined}. Install them in the ignored campaign venv with "
            "`python3 -m venv tmp/output-turbo-venv`, "
            "`tmp/output-turbo-venv/bin/python -m pip install --upgrade torch --index-url "
            "https://download.pytorch.org/whl/cu128`, and "
            "`tmp/output-turbo-venv/bin/python -m pip install --upgrade botorch gpytorch`."
        )
    return TurboDependencyBundle(
        torch=modules["torch"],
        botorch=modules["botorch"],
        gpytorch=modules["gpytorch"],
        versions={
            "torch": str(getattr(modules["torch"], "__version__", "unknown")),
            "botorch": str(getattr(modules["botorch"], "__version__", "unknown")),
            "gpytorch": str(getattr(modules["gpytorch"], "__version__", "unknown")),
        },
    )


def select_torch_device(torch_module: object) -> str:
    cuda = getattr(torch_module, "cuda")
    return "cuda" if bool(cuda.is_available()) else "cpu"


def normalized_points_to_parameter_dicts(
    normalized_points: np.ndarray,
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> list[dict[str, float]]:
    points = np.asarray(normalized_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != len(specs):
        raise ValueError("normalized_points shape does not match parameter specs")
    if np.any(points < 0.0) or np.any(points > 1.0):
        raise ValueError("normalized_points must be inside [0, 1]")

    parameter_sets: list[dict[str, float]] = []
    for row in points:
        values: dict[str, float] = {}
        for value, spec in zip(row, specs, strict=True):
            lower, upper = spec.transformed_prior_bounds()
            transformed_value = lower + float(value) * (upper - lower)
            values[spec.name] = spec.inverse_transform_value(transformed_value)
        parameter_sets.append(values)
    return parameter_sets


def parameter_dicts_to_normalized_points(
    parameter_sets: Sequence[Mapping[str, float]],
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> np.ndarray:
    points = np.zeros((len(parameter_sets), len(specs)), dtype=float)
    for row_index, parameters in enumerate(parameter_sets):
        for column_index, spec in enumerate(specs):
            lower, upper = spec.transformed_prior_bounds()
            width = upper - lower
            if width <= 0.0:
                raise ValueError(f"{spec.name}: transformed prior width must be positive")
            transformed = spec.transform_value(float(parameters[spec.name]))
            points[row_index, column_index] = min(1.0, max(0.0, (transformed - lower) / width))
    return points


def generate_initial_normalized_design(
    *,
    initial_points: int,
    dimensions: int,
    rng_seed: int,
) -> np.ndarray:
    if initial_points <= 0:
        raise ValueError("initial_points must be positive")
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")
    if HAVE_SCIPY_QMC and qmc is not None:
        m_power = int(math.ceil(math.log2(initial_points)))
        sampler = qmc.Sobol(d=dimensions, scramble=True, seed=rng_seed)
        return sampler.random_base2(m=m_power)[:initial_points]
    rng = np.random.default_rng(rng_seed)
    return rng.random((initial_points, dimensions))


def resolve_candidate_batch_size(
    *,
    requested: int | None,
    workers: int,
    seed_count: int,
) -> int:
    if workers <= 0:
        raise ValueError("workers must be positive")
    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    if workers < seed_count:
        raise ValueError("workers must be at least the number of seeds")
    max_candidate_batch_size = max(1, workers // seed_count)
    if requested is None:
        return max_candidate_batch_size
    if requested <= 0:
        raise ValueError("candidate-batch-size must be positive")
    if requested > max_candidate_batch_size:
        raise ValueError(
            "candidate-batch-size exceeds available worker capacity: "
            f"{requested} > {max_candidate_batch_size} for workers={workers} and seed_count={seed_count}"
        )
    return requested


def hpi_regression_penalty(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
    penalty_weight: float = DEFAULT_HPI_PENALTY_WEIGHT,
) -> float:
    if penalty_weight < 0.0:
        raise ValueError("penalty_weight must be non-negative")
    deltas = hpi_metric_loss_deltas(member, baseline_member=baseline_member)
    return penalty_weight * sum(max(0.0, float(deltas[metric_id])) for metric_id in HPI_CONSTRAINED_METRIC_IDS)


def optimizer_score(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
    penalty_weight: float = DEFAULT_HPI_PENALTY_WEIGHT,
) -> tuple[float, float, float]:
    raw_loss = overall_composite_loss(member)
    penalty = hpi_regression_penalty(
        member,
        baseline_member=baseline_member,
        penalty_weight=penalty_weight,
    )
    return -raw_loss - penalty, raw_loss, penalty


def estimate_objective_noise_variance(
    per_seed_losses: Sequence[float],
    *,
    seed_count: int,
    floor: float = DEFAULT_NOISE_VARIANCE_FLOOR,
) -> float:
    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    if floor <= 0.0:
        raise ValueError("floor must be positive")
    losses = np.asarray([float(value) for value in per_seed_losses], dtype=float)
    if len(losses) <= 1:
        return floor
    sample_variance = float(np.var(losses, ddof=1))
    return max(floor, sample_variance / float(seed_count))


def default_failure_tolerance(*, dimensions: int, batch_size: int) -> int:
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return int(math.ceil(max(4.0 / float(batch_size), float(dimensions) / float(batch_size))))


def update_turbo_state(
    state: TurboState,
    *,
    batch_best_score: float,
    batch_evaluation_count: int,
    success_tolerance: int = DEFAULT_SUCCESS_TOLERANCE,
    failure_tolerance: int,
    length_min: float = DEFAULT_TRUST_REGION_LENGTH_MIN,
    length_max: float = DEFAULT_TRUST_REGION_LENGTH_MAX,
) -> TurboState:
    if success_tolerance <= 0:
        raise ValueError("success_tolerance must be positive")
    if failure_tolerance <= 0:
        raise ValueError("failure_tolerance must be positive")
    if batch_evaluation_count <= 0:
        raise ValueError("batch_evaluation_count must be positive")

    improved = float(batch_best_score) > state.best_score + 1.0e-12
    best_score = max(state.best_score, float(batch_best_score))
    success_counter = state.success_counter + 1 if improved else 0
    failure_counter = 0 if improved else state.failure_counter + 1
    length = state.length

    if success_counter >= success_tolerance:
        length = min(length_max, 2.0 * length)
        success_counter = 0
    elif failure_counter >= failure_tolerance:
        length = 0.5 * length
        failure_counter = 0

    return replace(
        state,
        length=length,
        success_counter=success_counter,
        failure_counter=failure_counter,
        restart_triggered=length < length_min,
        best_score=best_score,
        evaluated_candidate_count=state.evaluated_candidate_count + batch_evaluation_count,
    )


def propose_turbo_candidates(
    *,
    train_x: np.ndarray,
    train_y: np.ndarray,
    train_yvar: np.ndarray,
    state: TurboState,
    batch_size: int,
    rng_seed: int,
    dependencies: TurboDependencyBundle,
    device: str,
) -> np.ndarray:
    """Fit a trust-region GP model and propose normalized candidate coordinates."""

    train_x_array = np.asarray(train_x, dtype=float)
    train_y_array = np.asarray(train_y, dtype=float)
    train_yvar_array = np.asarray(train_yvar, dtype=float)
    if train_x_array.ndim != 2:
        raise ValueError("train_x must be a two-dimensional array")
    if train_y_array.shape != (train_x_array.shape[0], 1):
        raise ValueError("train_y must have shape (n, 1)")
    if train_yvar_array.shape != (train_x_array.shape[0], 1):
        raise ValueError("train_yvar must have shape (n, 1)")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if np.any(train_x_array < 0.0) or np.any(train_x_array > 1.0):
        raise ValueError("train_x must be inside [0, 1]")

    torch = dependencies.torch
    SingleTaskGP = dependencies.botorch.models.SingleTaskGP
    Standardize = dependencies.botorch.models.transforms.outcome.Standardize
    fit_gpytorch_mll = dependencies.botorch.fit.fit_gpytorch_mll
    qNoisyExpectedImprovement = dependencies.botorch.acquisition.monte_carlo.qNoisyExpectedImprovement
    optimize_acqf = dependencies.botorch.optim.optimize.optimize_acqf
    ExactMarginalLogLikelihood = dependencies.gpytorch.mlls.ExactMarginalLogLikelihood

    torch.manual_seed(int(rng_seed))
    torch_device = torch.device(device)
    train_x_tensor = torch.as_tensor(train_x_array, dtype=torch.double, device=torch_device)
    train_y_tensor = torch.as_tensor(train_y_array, dtype=torch.double, device=torch_device)
    train_yvar_tensor = torch.as_tensor(train_yvar_array, dtype=torch.double, device=torch_device)

    model = SingleTaskGP(
        train_x_tensor,
        train_y_tensor,
        train_Yvar=train_yvar_tensor,
        outcome_transform=Standardize(m=1),
    )
    mll = ExactMarginalLogLikelihood(model.likelihood, model)
    fit_gpytorch_mll(mll)

    best_index = int(torch.argmax(train_y_tensor).item())
    center = train_x_tensor[best_index]
    half_length = state.length / 2.0
    lower = torch.clamp(center - half_length, min=0.0, max=1.0)
    upper = torch.clamp(center + half_length, min=0.0, max=1.0)
    bounds = torch.stack([lower, upper])

    acquisition_name = "qNoisyExpectedImprovement"
    acquisition_cls = qNoisyExpectedImprovement
    logei_module = getattr(getattr(dependencies.botorch, "acquisition", object()), "logei", None)
    if logei_module is not None and hasattr(logei_module, "qLogNoisyExpectedImprovement"):
        acquisition_cls = getattr(logei_module, "qLogNoisyExpectedImprovement")
        acquisition_name = "qLogNoisyExpectedImprovement"
    setattr(propose_turbo_candidates, "last_acquisition_function_name", acquisition_name)

    acquisition = acquisition_cls(model=model, X_baseline=train_x_tensor)
    candidates, _ = optimize_acqf(
        acq_function=acquisition,
        bounds=bounds,
        q=batch_size,
        num_restarts=10,
        raw_samples=128,
        options={"batch_limit": 5, "maxiter": 200},
    )
    return torch.clamp(candidates.detach(), 0.0, 1.0).cpu().numpy()
