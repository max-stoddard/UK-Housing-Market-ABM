"""Shared helpers for public-proxy BANK_ICR_HARD_MIN calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import fmean

from scripts.python.helpers.common.io_properties import read_properties
from scripts.python.helpers.common.paths import repo_root


BANK_ICR_HARD_MIN_KEY = "BANK_ICR_HARD_MIN"
BANK_INITIAL_RATE_KEY = "BANK_INITIAL_RATE"
DEFAULT_SOURCE_CSV = Path(
    "input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinPublicSources.csv"
)
DEFAULT_CONFIG_PATH = Path("input-data-versions/v4.9/config.properties")
DEFAULT_METHOD = "literal_standard_floor_125"
METHOD_CHOICES = (
    DEFAULT_METHOD,
    "stress_mapped_floor",
    "cross_segment_mean",
)
VALID_ROLES = ("decision", "context", "excluded")
REQUIRED_SOURCE_FIELDS = (
    "role",
    "document_path",
    "document_label",
    "source_as_of",
    "publisher",
    "segment",
    "icr_fraction",
    "stress_rate_fraction",
    "notes",
)


@dataclass(frozen=True)
class BankIcrHardMinSource:
    """One retained source row for the public-proxy ICR calibration."""

    role: str
    document_path: str
    document_label: str
    source_as_of: str
    publisher: str
    segment: str
    icr_fraction: float | None
    stress_rate_fraction: float | None
    notes: str


@dataclass(frozen=True)
class BankIcrHardMinCandidateResult:
    """One candidate mapping from retained evidence to a config scalar."""

    parameter_key: str
    candidate_id: str
    rank: int
    selected: bool
    raw_value: float
    value: float
    method_label: str
    rationale: str


@dataclass(frozen=True)
class BankIcrHardMinMethodSearchOutput:
    """Resolved retained evidence and ranked public-proxy candidates."""

    target_year: int
    source_path: str
    config_path: str
    bank_initial_rate: float
    representative_stress_rate_fraction: float
    sources: tuple[BankIcrHardMinSource, ...]
    decision_rows: tuple[BankIcrHardMinSource, ...]
    context_rows: tuple[BankIcrHardMinSource, ...]
    excluded_rows: tuple[BankIcrHardMinSource, ...]
    decision_icr_fractions: tuple[float, ...]
    context_icr_fractions: tuple[float, ...]
    candidates: tuple[BankIcrHardMinCandidateResult, ...]

    def selected_candidate(self) -> BankIcrHardMinCandidateResult:
        for candidate in self.candidates:
            if candidate.selected:
                return candidate
        raise KeyError("No selected BANK_ICR_HARD_MIN candidate.")

    def selected_value(self) -> float:
        return self.selected_candidate().value


def resolve_bank_icr_hard_min_source_csv_path(
    source_csv: str | None,
    *,
    root: Path | None = None,
    default_path: Path | None = None,
) -> Path:
    """Resolve the retained source CSV path."""

    if source_csv:
        resolved = Path(source_csv).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Missing BANK_ICR_HARD_MIN source CSV: {resolved}")
        return resolved.resolve()

    base_root = root if root is not None else repo_root()
    candidate = default_path if default_path is not None else DEFAULT_SOURCE_CSV
    resolved = candidate if candidate.is_absolute() else base_root / candidate
    if not resolved.exists():
        raise FileNotFoundError(
            f"Missing default BANK_ICR_HARD_MIN source CSV: {resolved}"
        )
    return resolved.resolve()


def resolve_bank_icr_hard_min_config_path(
    config_path: str | None,
    *,
    root: Path | None = None,
    default_path: Path | None = None,
) -> Path:
    """Resolve the config path used for BANK_INITIAL_RATE diagnostics."""

    if config_path:
        resolved = Path(config_path).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Missing BANK_ICR_HARD_MIN config path: {resolved}")
        return resolved.resolve()

    base_root = root if root is not None else repo_root()
    candidate = default_path if default_path is not None else DEFAULT_CONFIG_PATH
    resolved = candidate if candidate.is_absolute() else base_root / candidate
    if not resolved.exists():
        raise FileNotFoundError(
            f"Missing default BANK_ICR_HARD_MIN config path: {resolved}"
        )
    return resolved.resolve()


def _require_columns(fieldnames: list[str] | None) -> None:
    missing = [
        field for field in REQUIRED_SOURCE_FIELDS if fieldnames is None or field not in fieldnames
    ]
    if missing:
        raise ValueError(
            "BANK_ICR_HARD_MIN source CSV is missing required columns: "
            + ", ".join(missing)
        )


def _parse_optional_fraction(raw_value: str, field_name: str) -> float | None:
    stripped = raw_value.strip()
    if not stripped:
        return None
    try:
        value = float(stripped)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {raw_value!r}") from exc
    if value <= 0.0:
        raise ValueError(f"{field_name} must be positive when provided.")
    return value


def _parse_required_fraction(raw_value: str, field_name: str) -> float:
    parsed = _parse_optional_fraction(raw_value, field_name)
    if parsed is None:
        raise ValueError(f"{field_name} must not be blank.")
    return parsed


def load_bank_icr_hard_min_sources(csv_path: Path) -> tuple[BankIcrHardMinSource, ...]:
    """Load retained public-source rows for the BANK_ICR_HARD_MIN proxy calibration."""

    rows: list[BankIcrHardMinSource] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames)
        for row in reader:
            role = row["role"].strip()
            if role not in VALID_ROLES:
                raise ValueError(
                    "role must be one of: " + ", ".join(VALID_ROLES)
                )
            document_path = row["document_path"].strip()
            document_label = row["document_label"].strip()
            source_as_of = row["source_as_of"].strip()
            publisher = row["publisher"].strip()
            segment = row["segment"].strip()
            notes = row["notes"].strip()
            if not document_path:
                raise ValueError("document_path must not be blank.")
            if not document_label:
                raise ValueError("document_label must not be blank.")
            if not source_as_of:
                raise ValueError("source_as_of must not be blank.")
            if not publisher:
                raise ValueError("publisher must not be blank.")
            if not segment:
                raise ValueError("segment must not be blank.")
            icr_fraction = _parse_optional_fraction(row["icr_fraction"], "icr_fraction")
            stress_rate_fraction = _parse_optional_fraction(
                row["stress_rate_fraction"],
                "stress_rate_fraction",
            )
            if role == "decision":
                if icr_fraction is None:
                    raise ValueError("decision rows must define icr_fraction.")
                if stress_rate_fraction is None:
                    raise ValueError("decision rows must define stress_rate_fraction.")
            rows.append(
                BankIcrHardMinSource(
                    role=role,
                    document_path=document_path,
                    document_label=document_label,
                    source_as_of=source_as_of,
                    publisher=publisher,
                    segment=segment,
                    icr_fraction=icr_fraction,
                    stress_rate_fraction=stress_rate_fraction,
                    notes=notes,
                )
            )
    if not rows:
        raise ValueError(f"No BANK_ICR_HARD_MIN source rows found in: {csv_path}")
    return tuple(rows)


def load_bank_initial_rate(config_path: Path) -> float:
    """Read BANK_INITIAL_RATE from the target config.properties file."""

    properties = read_properties(config_path)
    if BANK_INITIAL_RATE_KEY not in properties:
        raise ValueError(
            f"Missing {BANK_INITIAL_RATE_KEY} in config path: {config_path}"
        )
    try:
        return float(properties[BANK_INITIAL_RATE_KEY])
    except ValueError as exc:
        raise ValueError(
            f"Invalid {BANK_INITIAL_RATE_KEY} value in config path: {config_path}"
        ) from exc


def _round_fraction(value: float, decimals: int = 2) -> float:
    quantum = "0." + ("0" * (decimals - 1)) + "1"
    return float(Decimal(str(value)).quantize(Decimal(quantum), rounding=ROUND_HALF_UP))


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root()))
    except ValueError:
        return str(path.resolve())


def build_bank_icr_hard_min_method_search_output(
    *,
    source_csv: Path,
    config_path: Path,
    target_year: int,
) -> BankIcrHardMinMethodSearchOutput:
    """Resolve the approved public-proxy BANK_ICR_HARD_MIN candidates."""

    if target_year <= 0:
        raise ValueError("target_year must be positive.")

    sources = load_bank_icr_hard_min_sources(source_csv)
    bank_initial_rate = load_bank_initial_rate(config_path)

    decision_rows = tuple(row for row in sources if row.role == "decision")
    context_rows = tuple(row for row in sources if row.role == "context")
    excluded_rows = tuple(row for row in sources if row.role == "excluded")
    if not decision_rows:
        raise ValueError("Expected at least one decision row.")
    if len(context_rows) != 4:
        raise ValueError("Expected exactly four UK Finance context rows.")
    if len(excluded_rows) != 1:
        raise ValueError("Expected exactly one excluded source row.")
    if any(row.publisher != "Paragon Bank" for row in decision_rows):
        raise ValueError("Decision rows must come from Paragon Bank.")
    if any(row.publisher != "UK Finance" for row in context_rows):
        raise ValueError("Context rows must come from UK Finance.")
    if excluded_rows[0].publisher != "CHL Mortgages":
        raise ValueError("Excluded row must identify the CHL Mortgages file mismatch.")

    decision_icr_fractions = tuple(
        _parse_required_fraction(str(row.icr_fraction), "icr_fraction")
        for row in decision_rows
    )
    context_icr_fractions = tuple(
        row.icr_fraction for row in context_rows if row.icr_fraction is not None
    )
    representative_stress_rate_fraction = fmean(
        _parse_required_fraction(str(row.stress_rate_fraction), "stress_rate_fraction")
        for row in decision_rows
    )

    literal_standard_floor = min(decision_icr_fractions)
    stress_mapped_floor = (
        literal_standard_floor
        * representative_stress_rate_fraction
        / bank_initial_rate
    )
    cross_segment_mean = fmean(decision_icr_fractions)

    candidates = (
        BankIcrHardMinCandidateResult(
            parameter_key=BANK_ICR_HARD_MIN_KEY,
            candidate_id=DEFAULT_METHOD,
            rank=1,
            selected=True,
            raw_value=literal_standard_floor,
            value=_round_fraction(literal_standard_floor),
            method_label="Literal minimum published decision-row ICR floor",
            rationale=(
                "Selected default: promote the literal 125% lender floor because it "
                "is the cleanest semantic match to the model's hard underwriting rule."
            ),
        ),
        BankIcrHardMinCandidateResult(
            parameter_key=BANK_ICR_HARD_MIN_KEY,
            candidate_id="stress_mapped_floor",
            rank=2,
            selected=False,
            raw_value=stress_mapped_floor,
            value=_round_fraction(stress_mapped_floor),
            method_label=(
                "Map 125% at the retained representative stress rate onto BANK_INITIAL_RATE"
            ),
            rationale=(
                "Rejected: this adds a rate-translation layer and makes the result "
                "depend on a diagnostic stress-rate choice rather than the published ratio."
            ),
        ),
        BankIcrHardMinCandidateResult(
            parameter_key=BANK_ICR_HARD_MIN_KEY,
            candidate_id="cross_segment_mean",
            rank=3,
            selected=False,
            raw_value=cross_segment_mean,
            value=_round_fraction(cross_segment_mean),
            method_label="Mean of retained cross-segment decision-row ICR thresholds",
            rationale=(
                "Rejected: equal-weighting visible segments invents a market mix and "
                "would likely over-tighten the representative bank."
            ),
        ),
    )

    return BankIcrHardMinMethodSearchOutput(
        target_year=target_year,
        source_path=_display_path(source_csv),
        config_path=_display_path(config_path),
        bank_initial_rate=bank_initial_rate,
        representative_stress_rate_fraction=representative_stress_rate_fraction,
        sources=sources,
        decision_rows=decision_rows,
        context_rows=context_rows,
        excluded_rows=excluded_rows,
        decision_icr_fractions=decision_icr_fractions,
        context_icr_fractions=context_icr_fractions,
        candidates=candidates,
    )


__all__ = [
    "BANK_ICR_HARD_MIN_KEY",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_METHOD",
    "DEFAULT_SOURCE_CSV",
    "METHOD_CHOICES",
    "BankIcrHardMinCandidateResult",
    "BankIcrHardMinMethodSearchOutput",
    "BankIcrHardMinSource",
    "build_bank_icr_hard_min_method_search_output",
    "load_bank_icr_hard_min_sources",
    "load_bank_initial_rate",
    "resolve_bank_icr_hard_min_config_path",
    "resolve_bank_icr_hard_min_source_csv_path",
]
