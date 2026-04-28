#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate GOVERNMENT_MONTHLY_INCOME_SUPPORT from the GOV.UK 2024/25 rates page.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir, repo_root


GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY = "GOVERNMENT_MONTHLY_INCOME_SUPPORT"
SOURCE_URL = (
    "https://www.gov.uk/government/publications/benefit-and-pension-rates-2024-to-2025/"
    "benefit-and-pension-rates-2024-to-2025"
)
DEFAULT_SOURCE_HTML = Path(
    "input-data-versions/calibration-evidence/gov-income-support-v4.13/"
    "benefit-and-pension-rates-2024-to-2025.html"
)
SOURCE_SECTION_ID = "income-support"
SOURCE_SECTION_LABEL = "Income Support"
TARGET_ROW_LABEL = "Both 18 or over"
TARGET_RATE_COLUMN = "Rates 2024/25"
SOURCE_VALUES_FILE_NAME = "GovIncomeSupport2024SourceValues.csv"
SUMMARY_FILE_NAME = "GovIncomeSupport2024Summary.json"
MONTHS_IN_YEAR = 12
WEEKS_IN_YEAR = 52


@dataclass(frozen=True)
class IncomeSupportObservation:
    parameter_key: str
    weekly_rate: float
    annual_equivalent: float
    monthly_equivalent: float
    selected_config_value: float
    source_path: str
    source_url: str
    source_section: str
    row_label: str
    rate_column: str
    calculation: str
    notes: str


class IncomeSupportTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._active_section = False
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_cell_parts: list[str] = []
        self._current_row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "h2":
            section_id = attributes.get("id")
            if section_id == SOURCE_SECTION_ID:
                self._active_section = True
            elif self._active_section:
                self._active_section = False
                self._in_table = False
        elif tag == "table" and self._active_section:
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag in {"th", "td"} and self._in_row:
            self._in_cell = True
            self._current_cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._in_cell:
            self._current_row.append(_clean_string(" ".join(self._current_cell_parts)))
            self._current_cell_parts = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = []
            self._in_row = False
        elif tag == "table" and self._in_table:
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell_parts.append(data)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract the 2024/25 Income Support couple rate from the downloaded "
            "GOV.UK benefit and pension rates page."
        )
    )
    parser.add_argument(
        "--source-html",
        default=None,
        help=(
            "Path to the downloaded GOV.UK rates HTML. Defaults to the v4.13 "
            "calibration-evidence artifact."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Optional output directory for "
            f"{SOURCE_VALUES_FILE_NAME} and {SUMMARY_FILE_NAME}."
        ),
    )
    return parser


def resolve_source_html(source_html: str | None) -> Path:
    if source_html:
        resolved = Path(source_html).expanduser()
    else:
        resolved = repo_root() / DEFAULT_SOURCE_HTML
    if not resolved.exists():
        raise FileNotFoundError(f"Missing GOV.UK source HTML: {resolved}")
    return resolved.resolve()


def _clean_string(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def _parse_float(value: str) -> float:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        raise ValueError("Expected a numeric rate, found blank text.")
    return float(cleaned)


def _extract_income_support_rows(source_html: Path) -> list[list[str]]:
    parser = IncomeSupportTableParser()
    parser.feed(source_html.read_text(encoding="utf-8"))
    parser.close()
    if not parser.rows:
        raise ValueError(f"Could not find the {SOURCE_SECTION_LABEL!r} table in {source_html}.")
    return parser.rows


def _find_rate_column(header_row: list[str]) -> int:
    for index, cell in enumerate(header_row):
        if _clean_string(cell).lower() == TARGET_RATE_COLUMN.lower():
            return index
    raise ValueError(f"Could not find column {TARGET_RATE_COLUMN!r}.")


def extract_weekly_rate(source_html: Path) -> tuple[float, list[str], list[str]]:
    rows = _extract_income_support_rows(source_html)
    header_row = next(
        (
            row
            for row in rows
            if row
            and _clean_string(row[0]).lower() == "personal allowances"
            and any(_clean_string(cell).lower() == TARGET_RATE_COLUMN.lower() for cell in row)
        ),
        None,
    )
    if header_row is None:
        raise ValueError("Could not find the Income Support personal-allowances header row.")

    rate_column = _find_rate_column(header_row)
    target_row = next(
        (row for row in rows if row and _clean_string(row[0]).lower() == TARGET_ROW_LABEL.lower()),
        None,
    )
    if target_row is None:
        raise ValueError(f"Could not find row {TARGET_ROW_LABEL!r}.")
    if rate_column >= len(target_row):
        raise ValueError(f"Row {TARGET_ROW_LABEL!r} has no value for {TARGET_RATE_COLUMN!r}.")
    return _parse_float(target_row[rate_column]), header_row, target_row


def extract_income_support(source_html: Path) -> IncomeSupportObservation:
    weekly_rate, _, _ = extract_weekly_rate(source_html)
    annual_equivalent = weekly_rate * WEEKS_IN_YEAR
    monthly_equivalent = annual_equivalent / MONTHS_IN_YEAR
    selected_config_value = round(monthly_equivalent, 10)
    return IncomeSupportObservation(
        parameter_key=GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY,
        weekly_rate=weekly_rate,
        annual_equivalent=annual_equivalent,
        monthly_equivalent=monthly_equivalent,
        selected_config_value=selected_config_value,
        source_path=str(source_html),
        source_url=SOURCE_URL,
        source_section=SOURCE_SECTION_LABEL,
        row_label=TARGET_ROW_LABEL,
        rate_column=TARGET_RATE_COLUMN,
        calculation=f"{weekly_rate} * {WEEKS_IN_YEAR} / {MONTHS_IN_YEAR}",
        notes=(
            "The model stores this support floor as a monthly value and later annualizes it by "
            "multiplying by 12. Converting the weekly GOV.UK rate with 52 / 12 preserves the "
            "official annual entitlement implied by 52 weekly payments, unlike the old four-week "
            "month convention."
        ),
    )


def build_calibration_summary(source_html: Path) -> dict[str, object]:
    observation = extract_income_support(source_html)
    four_week_value = observation.weekly_rate * 4
    return {
        "sourceUrl": SOURCE_URL,
        "sourcePath": str(source_html),
        "sourceSection": observation.source_section,
        "method": "weekly-source-rate-annualized-to-calendar-month",
        "methodRationale": observation.notes,
        "selectedConfigValues": {
            GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY: observation.selected_config_value,
        },
        "observation": asdict(observation),
        "legacyComparison": {
            "v4_12_config_value": 578.6,
            "v4_12_source_year": "2025/26",
            "four_week_month_value_from_2024_25_rate": round(four_week_value, 10),
            "selected_minus_four_week_value": round(observation.selected_config_value - four_week_value, 10),
            "annualized_selected_value": round(observation.annual_equivalent, 10),
            "annualized_four_week_value": round(four_week_value * MONTHS_IN_YEAR, 10),
        },
    }


def write_evidence(output_dir: Path, summary: dict[str, object]) -> None:
    observation = summary["observation"]
    if not isinstance(observation, dict):
        raise TypeError("Expected observation to be a dictionary.")

    source_values_path = output_dir / SOURCE_VALUES_FILE_NAME
    with source_values_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "parameter_key",
            "weekly_rate",
            "annual_equivalent",
            "monthly_equivalent",
            "selected_config_value",
            "source_path",
            "source_url",
            "source_section",
            "row_label",
            "rate_column",
            "calculation",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(observation)

    summary_path = output_dir / SUMMARY_FILE_NAME
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def run_calibration(
    *,
    source_html: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    resolved_source_html = resolve_source_html(str(source_html) if source_html is not None else None)
    summary = build_calibration_summary(resolved_source_html)
    if output_dir is not None:
        write_evidence(ensure_output_dir(output_dir), summary)
    return summary


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = run_calibration(source_html=args.source_html, output_dir=args.output_dir)
    value = summary["selectedConfigValues"][GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY]  # type: ignore[index]
    print(f"{GOVERNMENT_MONTHLY_INCOME_SUPPORT_KEY} = {format_float(float(value))}")


if __name__ == "__main__":
    main()
