"""Shared helpers for public-proxy BANK_AGE_LIMIT calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, multimode

from scripts.python.helpers.common.paths import repo_root


BANK_AGE_LIMIT_KEY = "BANK_AGE_LIMIT"
DEFAULT_SOURCE_CSV = Path(
    "input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitPublicSources.csv"
)
DEFAULT_METHOD = "conservative_mainstream_mode"
METHOD_CHOICES = (
    DEFAULT_METHOD,
    "hybrid_midpoint_round",
    "repay_cap_mean_round",
)
REQUIRED_SOURCE_FIELDS = (
    "provider",
    "application_age_cap",
    "repay_by_cap",
    "source_url",
    "source_as_of",
    "notes",
)


@dataclass(frozen=True)
class BankAgeLimitSource:
    """One retained public source row for the proxy calibration."""

    provider: str
    application_age_cap: int | None
    repay_by_cap: int
    source_url: str
    source_as_of: str
    notes: str


@dataclass(frozen=True)
class BankAgeLimitCandidateResult:
    """One candidate mapping from retained public evidence to a config scalar."""

    parameter_key: str
    candidate_id: str
    rank: int
    selected: bool
    raw_value: float
    value: int
    method_label: str
    rationale: str


@dataclass(frozen=True)
class BankAgeLimitMethodSearchOutput:
    """Resolved retained evidence and ranked public-proxy candidates."""

    target_year: int
    source_path: str
    sources: tuple[BankAgeLimitSource, ...]
    explicit_origination_caps: tuple[int, ...]
    explicit_repay_caps: tuple[int, ...]
    origination_cap_mean: float
    repay_cap_mean: float
    hybrid_midpoint_raw: float
    combined_explicit_thresholds: tuple[int, ...]
    candidates: tuple[BankAgeLimitCandidateResult, ...]

    def selected_candidate(self) -> BankAgeLimitCandidateResult:
        for candidate in self.candidates:
            if candidate.selected:
                return candidate
        raise KeyError("No selected BANK_AGE_LIMIT candidate.")

    def selected_value(self) -> int:
        return self.selected_candidate().value


def resolve_bank_age_limit_source_csv_path(
    source_csv: str | None,
    *,
    root: Path | None = None,
    default_path: Path | None = None,
) -> Path:
    """Resolve the retained public-source CSV path."""

    if source_csv:
        resolved = Path(source_csv).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Missing BANK_AGE_LIMIT source CSV: {resolved}")
        return resolved.resolve()

    base_root = root if root is not None else repo_root()
    candidate = default_path if default_path is not None else DEFAULT_SOURCE_CSV
    resolved = candidate if candidate.is_absolute() else base_root / candidate
    if not resolved.exists():
        raise FileNotFoundError(f"Missing default BANK_AGE_LIMIT source CSV: {resolved}")
    return resolved.resolve()


def _require_columns(fieldnames: list[str] | None) -> None:
    missing = [field for field in REQUIRED_SOURCE_FIELDS if fieldnames is None or field not in fieldnames]
    if missing:
        raise ValueError(
            "BANK_AGE_LIMIT source CSV is missing required columns: "
            + ", ".join(missing)
        )


def _parse_optional_cap(raw_value: str, field_name: str) -> int | None:
    stripped = raw_value.strip()
    if not stripped:
        return None
    try:
        value = int(stripped)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {raw_value!r}") from exc
    if value <= 0:
        raise ValueError(f"{field_name} must be positive when provided.")
    return value


def _parse_required_cap(raw_value: str, field_name: str) -> int:
    parsed = _parse_optional_cap(raw_value, field_name)
    if parsed is None:
        raise ValueError(f"{field_name} must not be blank.")
    return parsed


def load_bank_age_limit_sources(csv_path: Path) -> tuple[BankAgeLimitSource, ...]:
    """Load retained public-source rows for the BANK_AGE_LIMIT proxy calibration."""

    rows: list[BankAgeLimitSource] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames)
        for row in reader:
            provider = row["provider"].strip()
            source_url = row["source_url"].strip()
            source_as_of = row["source_as_of"].strip()
            notes = row["notes"].strip()
            if not provider:
                raise ValueError("provider must not be blank.")
            if not source_url:
                raise ValueError("source_url must not be blank.")
            if not source_as_of:
                raise ValueError("source_as_of must not be blank.")
            rows.append(
                BankAgeLimitSource(
                    provider=provider,
                    application_age_cap=_parse_optional_cap(
                        row["application_age_cap"],
                        "application_age_cap",
                    ),
                    repay_by_cap=_parse_required_cap(
                        row["repay_by_cap"],
                        "repay_by_cap",
                    ),
                    source_url=source_url,
                    source_as_of=source_as_of,
                    notes=notes,
                )
            )
    if not rows:
        raise ValueError(f"No BANK_AGE_LIMIT source rows found in: {csv_path}")
    return tuple(rows)


def _round_half_up(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _unique_mode(values: tuple[int, ...]) -> int:
    modes = multimode(values)
    if len(modes) != 1:
        raise ValueError(
            "Expected a unique mode for the explicit public thresholds, "
            f"found: {modes}"
        )
    return int(modes[0])


def build_bank_age_limit_method_search_output(
    *,
    source_csv: Path,
    target_year: int,
) -> BankAgeLimitMethodSearchOutput:
    """Resolve the approved public-proxy BANK_AGE_LIMIT candidates."""

    if target_year <= 0:
        raise ValueError("target_year must be positive.")

    sources = load_bank_age_limit_sources(source_csv)
    explicit_origination_caps = tuple(
        source.application_age_cap
        for source in sources
        if source.application_age_cap is not None
    )
    if not explicit_origination_caps:
        raise ValueError("Expected at least one explicit application-age cap.")

    explicit_repay_caps = tuple(source.repay_by_cap for source in sources)
    combined_explicit_thresholds = explicit_origination_caps + explicit_repay_caps

    origination_cap_mean = fmean(explicit_origination_caps)
    repay_cap_mean = fmean(explicit_repay_caps)
    hybrid_midpoint_raw = (origination_cap_mean + repay_cap_mean) / 2.0

    conservative_mode = _unique_mode(combined_explicit_thresholds)
    hybrid_midpoint_round = _round_half_up(hybrid_midpoint_raw)
    repay_cap_mean_round = _round_half_up(repay_cap_mean)

    candidates = (
        BankAgeLimitCandidateResult(
            parameter_key=BANK_AGE_LIMIT_KEY,
            candidate_id=DEFAULT_METHOD,
            rank=1,
            selected=True,
            raw_value=float(conservative_mode),
            value=conservative_mode,
            method_label="Mode of explicit origination and repay-side public thresholds",
            rationale=(
                "Selected default: the unique mode across explicit public thresholds "
                "keeps the overloaded scalar at the conservative mainstream benchmark."
            ),
        ),
        BankAgeLimitCandidateResult(
            parameter_key=BANK_AGE_LIMIT_KEY,
            candidate_id="hybrid_midpoint_round",
            rank=2,
            selected=False,
            raw_value=hybrid_midpoint_raw,
            value=hybrid_midpoint_round,
            method_label="Midpoint of origination-cap mean and repay-cap mean, rounded",
            rationale=(
                "Rejected: this adds an extra averaging layer while providing no "
                "practical advantage over the selected conservative benchmark."
            ),
        ),
        BankAgeLimitCandidateResult(
            parameter_key=BANK_AGE_LIMIT_KEY,
            candidate_id="repay_cap_mean_round",
            rank=3,
            selected=False,
            raw_value=repay_cap_mean,
            value=repay_cap_mean_round,
            method_label="Mean of non-BTL repay-by caps, rounded",
            rationale=(
                "Rejected: repay-side-only averaging pushes the single scalar above "
                "the conservative benchmark for a parameter that also gates origination."
            ),
        ),
    )

    return BankAgeLimitMethodSearchOutput(
        target_year=target_year,
        source_path=str(source_csv),
        sources=sources,
        explicit_origination_caps=explicit_origination_caps,
        explicit_repay_caps=explicit_repay_caps,
        origination_cap_mean=origination_cap_mean,
        repay_cap_mean=repay_cap_mean,
        hybrid_midpoint_raw=hybrid_midpoint_raw,
        combined_explicit_thresholds=combined_explicit_thresholds,
        candidates=candidates,
    )


__all__ = [
    "BANK_AGE_LIMIT_KEY",
    "DEFAULT_METHOD",
    "DEFAULT_SOURCE_CSV",
    "METHOD_CHOICES",
    "BankAgeLimitCandidateResult",
    "BankAgeLimitMethodSearchOutput",
    "BankAgeLimitSource",
    "build_bank_age_limit_method_search_output",
    "load_bank_age_limit_sources",
    "resolve_bank_age_limit_source_csv_path",
]
