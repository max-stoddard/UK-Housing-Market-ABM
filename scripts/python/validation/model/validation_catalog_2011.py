"""2011 reference validation catalog for the original `v0` output overlay.

This catalog intentionally preserves the modern metric ids, extractor kinds, and
file mappings while swapping in tracked 2011 targets and source provenance. The
2011 artifact is a separate reference overlay and is not the tracked validation
profile published under `input-data-versions/validation/`.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import replace
from statistics import fmean

from scripts.python.validation.model.schema import (
    MetricDefinition,
    MetricSourceMetadata,
    MetricSourceReference,
    TargetBand,
)
from scripts.python.validation.model.validation_catalog_2024 import (
    HPI_FULL_HISTORY_REBASED_STD,
    MARKET_SOURCE_2024_BY_METRIC_ID,
    TARGET_CATALOG as TARGET_CATALOG_2024,
)

WAS_WAVE_3_SOURCE_LABEL = "WAS Wave 3"

ADVANCES_TARGET_TOLERANCE = 0.15
HPI_TARGET_TOLERANCE = 0.15

BOE_2011_SNAPSHOT_PATH = "input-data-versions/validation-sources/2011/boe/housing-tools-2011-series.csv"
BOE_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/boe/housing-tools-2011-validation-evidence.txt"
CML_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/cml/mortgage-market-2011-validation-evidence.txt"
BM_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/bm/btl-rental-yield-2011-validation-evidence.txt"
HMLR_2011_SNAPSHOT_PATH = "input-data-versions/validation-sources/2011/hmlr/uk-hpi-uk-series-through-2011-12.csv"
HMLR_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/hmlr/hpi-2011-validation-evidence.txt"
HMLR_2011_DERIVED_VALUES_PATH = "input-data-versions/validation-sources/2011/hmlr/hpi-2011-derived-values.json"
FRS_TENURE_2011_DOCUMENT_PATH = "input-data-versions/validation-sources/2011/frs/frs-2010-11-report.pdf"
FRS_TENURE_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/frs/household-tenure-2011-validation-evidence.txt"
ONS_RPI_2011_DOCUMENT_PATH = "input-data-versions/validation-sources/2011/ons-rpi/priceindexofprivaterentsukhistoricalseries-2025-03-26.xlsx"
ONS_RPI_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/ons-rpi/rpi-2011-validation-evidence.txt"
MLAR_2011_COMPONENTS_PATH = "input-data-versions/validation-sources/2011/mlar/mlar-oo-debt-to-income-2011-components.csv"
MLAR_2011_TEXT_PATH = "input-data-versions/validation-sources/2011/mlar/oo-debt-to-income-2011-validation-evidence.txt"
ONS_QWND_2011_SNAPSHOT_PATH = (
    "input-data-versions/validation-sources/2011/ons/qwnd-household-gross-disposable-income-2010q2-2011q4.json"
)

MORTGAGE_APPROVALS_2011_MONTHLY_MEAN_THOUSANDS = 49.28633333333333
HOUSING_TRANSACTIONS_2011_MONTHLY_MEAN_THOUSANDS = 73.55166666666666
DEBT_TO_INCOME_2011_QUARTERLY_VALUES = (
    164.2259943729304,
    163.2704030065937,
    162.3849367588562,
    161.8704279215477,
)
PRICE_TO_INCOME_2011_QUARTERLY_VALUES = (
    4.268301630303742,
    4.240177339652872,
    4.225101341813285,
    4.226669954936595,
)
HOUSE_PRICE_GROWTH_2011_ANNUAL_MEAN = -0.3968031463238107
INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS = (
    2.3975732465696207,
    2.4522198715809957,
    2.443696005236189,
    2.626824733041048,
)
HPI_2011_REBASED_MEAN = 0.9922839506172839
HPI_2011_REBASED_STD = 0.06520815312915954
HPI_2011_CYCLE_PERIOD_MONTHS = 171.33333333333334
HOUSEHOLD_OWNING_SHARE_2011 = 66.0
HOUSEHOLD_RENTING_SHARE_2011 = 17.0
RPI_2011_GB_REBASED_MEAN = 1.010962279264232
RPI_2011_GB_REBASED_MONTHLY_VALUES = (
    1.0,
    1.001371191823,
    1.00324096718,
    1.005175896361,
    1.007316578688,
    1.008982007963,
    1.011082528627,
    1.013492871667,
    1.016491367996,
    1.018751610671,
    1.02120612216,
    1.024436208035,
)
OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES = (
    99.75341253849653,
    99.34683471171756,
    99.08730411317276,
    98.61909294397614,
)

FTB_2011_ANNUAL_LOANS = 193_000.0
HM_2011_ANNUAL_LOANS = 316_500.0
BTL_2011_ANNUAL_LOANS = 84_000.0
RENTAL_YIELD_2011_ANNUAL = 6.1


def _annual_mean(values: tuple[float, ...]) -> float:
    return float(fmean(values))


def _annual_total_to_monthly_thousands(raw_value: float) -> float:
    return raw_value / 12.0 / 1_000.0


def _plus_minus_tolerance_band(*, source_value: float, tolerance: float) -> TargetBand:
    return TargetBand(
        lower=source_value * (1.0 - tolerance),
        upper=source_value * (1.0 + tolerance),
    )


SOURCE_LABEL_2011_BY_METRIC_ID: dict[str, str] = {
    "core_mortgageApprovals": "Bank of England housing-tools workbook (repo-local 2011 monthly snapshot)",
    "core_housingTransactions": "Bank of England housing-tools workbook (repo-local 2011 monthly snapshot)",
    "core_advancesToFTB": "Best-available secondary-source proxy for 2011 CML purchase lending totals",
    "core_advancesToHM": "Best-available secondary-source proxy for 2011 CML purchase lending totals",
    "core_advancesToBTL": "Best-available secondary-source proxy for 2011 CML purchase lending totals",
    "core_debtToIncome": "Bank of England housing-tools workbook (repo-local 2011 quarterly snapshot)",
    "core_priceToIncome": "Bank of England housing-tools workbook (repo-local 2011 quarterly snapshot)",
    "core_housePriceGrowth": "Bank of England housing-tools workbook (repo-local 2011 monthly snapshot)",
    "core_hpiMean": "HM Land Registry UK HPI full history through 2011-12 (UK IndexSA rebased to January 2011)",
    "core_hpiStd": "HM Land Registry UK HPI full file December 2024 (shared official std benchmark over 2005-01 to 2024-12)",
    "core_hpiCyclePeriod": "HM Land Registry UK HPI full history through 2011-12 (UK Index history through 2011-12)",
    "rpi_mean": "ONS Price Index of Private Rents historical series (Great Britain rebased to January 2011)",
    "household_owning_share": "DWP Family Resources Survey 2010/11, UK household tenure table",
    "household_renting_share": "DWP Family Resources Survey 2010/11, UK household tenure table",
    "core_ooDebtToIncome": "MLAR long-run detailed tables plus ONS QWND (full-year 2011 reconstruction)",
    "core_rentalYield": "Best-available secondary-source proxy for 2011 BM Solutions UK rental yield",
    "core_interestRateSpread": "Bank of England housing-tools workbook (repo-local 2011 monthly spread series)",
    "income_distribution_jsd": WAS_WAVE_3_SOURCE_LABEL,
    "housing_wealth_distribution_jsd": WAS_WAVE_3_SOURCE_LABEL,
    "financial_wealth_distribution_jsd": WAS_WAVE_3_SOURCE_LABEL,
}


SOURCE_METADATA_2011_BY_METRIC_ID: dict[str, MetricSourceMetadata] = {
    "core_mortgageApprovals": MetricSourceMetadata(
        source_document_path=BOE_2011_SNAPSHOT_PATH,
        source_text_path=BOE_2011_TEXT_PATH,
        source_table="Repo-local 2011 Bank of England housing-tools snapshot",
        source_page=1,
        source_indicator_label="Mortgage approvals, 2011 annual mean",
        raw_source_value=MORTGAGE_APPROVALS_2011_MONTHLY_MEAN_THOUSANDS * 1_000.0,
        normalized_source_value=MORTGAGE_APPROVALS_2011_MONTHLY_MEAN_THOUSANDS,
        source_units="count/month",
        comparison_units="thousand count/month",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_monthly_range",
        band_notes=(
            "Uses the 2011 monthly mortgage-approvals series from the tracked Bank of England snapshot. "
            "The source value is the annual mean converted to thousand count/month, and the target band uses "
            "the observed 2011 monthly range."
        ),
    ),
    "core_housingTransactions": MetricSourceMetadata(
        source_document_path=BOE_2011_SNAPSHOT_PATH,
        source_text_path=BOE_2011_TEXT_PATH,
        source_table="Repo-local 2011 Bank of England housing-tools snapshot",
        source_page=1,
        source_indicator_label="Housing transactions, 2011 annual mean",
        raw_source_value=HOUSING_TRANSACTIONS_2011_MONTHLY_MEAN_THOUSANDS * 1_000.0,
        normalized_source_value=HOUSING_TRANSACTIONS_2011_MONTHLY_MEAN_THOUSANDS,
        source_units="count/month",
        comparison_units="thousand count/month",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_monthly_range",
        band_notes=(
            "Uses the 2011 monthly housing-transactions series from the tracked Bank of England snapshot. "
            "The source value is the annual mean converted to thousand count/month, and the target band uses "
            "the observed 2011 monthly range."
        ),
    ),
    "core_advancesToFTB": MetricSourceMetadata(
        source_document_path=CML_2011_TEXT_PATH,
        source_text_path=CML_2011_TEXT_PATH,
        source_table="Tracked public references quoting 2011 CML totals",
        source_page=1,
        source_indicator_label="First-time buyer purchase loans, 2011 annual total",
        raw_source_value=FTB_2011_ANNUAL_LOANS,
        normalized_source_value=_annual_total_to_monthly_thousands(FTB_2011_ANNUAL_LOANS),
        source_units="count/year",
        comparison_units="thousand count/month",
        source_as_of="2011 annual total reported Feb 2012",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_best_available_proxy_monthly_mean",
        band_notes=(
            "Best-available tracked 2011 proxy from public reports quoting CML statistics. "
            "The annual total is converted to thousand count/month using the same normalization logic as the 2024 "
            "metric, then scored with a fixed +/-15% band because no cleaner repo-local primary 2011 file is tracked."
        ),
        source_references=(
            MetricSourceReference(
                label="PropertyWire report quoting 2011 CML first-time-buyer total",
                source_document_path=CML_2011_TEXT_PATH,
                source_text_path=CML_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="First-time buyers",
                raw_source_value=FTB_2011_ANNUAL_LOANS,
                source_as_of="Published 13 Feb 2012",
                source_units="count/year",
                notes="Secondary-source report quoting the 2011 CML first-time-buyer total.",
            ),
            MetricSourceReference(
                label="Mortgage Finance Gazette cross-check quoting 2011 CML first-time-buyer total",
                source_document_path=CML_2011_TEXT_PATH,
                source_text_path=CML_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="First-time buyers",
                raw_source_value=FTB_2011_ANNUAL_LOANS,
                source_as_of="Published 13 Feb 2012",
                source_units="count/year",
                notes="Secondary-source cross-check on the same 2011 CML first-time-buyer total.",
            ),
        ),
    ),
    "core_advancesToHM": MetricSourceMetadata(
        source_document_path=CML_2011_TEXT_PATH,
        source_text_path=CML_2011_TEXT_PATH,
        source_table="Tracked public references quoting 2011 CML totals",
        source_page=1,
        source_indicator_label="Home-mover purchase loans, 2011 annual total",
        raw_source_value=HM_2011_ANNUAL_LOANS,
        normalized_source_value=_annual_total_to_monthly_thousands(HM_2011_ANNUAL_LOANS),
        source_units="count/year",
        comparison_units="thousand count/month",
        source_as_of="2011 annual total reported Feb 2012",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_best_available_proxy_monthly_mean",
        band_notes=(
            "Best-available tracked 2011 proxy from public reports quoting CML statistics. "
            "The annual total is converted to thousand count/month using the same normalization logic as the 2024 "
            "metric, then scored with a fixed +/-15% band because no cleaner repo-local primary 2011 file is tracked."
        ),
        source_references=(
            MetricSourceReference(
                label="PropertyWire report quoting 2011 CML home-mover total",
                source_document_path=CML_2011_TEXT_PATH,
                source_text_path=CML_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="Home movers",
                raw_source_value=HM_2011_ANNUAL_LOANS,
                source_as_of="Published 13 Feb 2012",
                source_units="count/year",
                notes="Secondary-source report quoting the 2011 CML home-mover total.",
            ),
            MetricSourceReference(
                label="Mortgage Finance Gazette cross-check quoting 2011 CML home-mover total",
                source_document_path=CML_2011_TEXT_PATH,
                source_text_path=CML_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="Home movers",
                raw_source_value=HM_2011_ANNUAL_LOANS,
                source_as_of="Published 13 Feb 2012",
                source_units="count/year",
                notes="Secondary-source cross-check on the same 2011 CML home-mover total.",
            ),
        ),
    ),
    "core_advancesToBTL": MetricSourceMetadata(
        source_document_path=CML_2011_TEXT_PATH,
        source_text_path=CML_2011_TEXT_PATH,
        source_table="Tracked public references quoting 2011 CML totals",
        source_page=1,
        source_indicator_label="Buy-to-let house-purchase loans, 2011 annual total",
        raw_source_value=BTL_2011_ANNUAL_LOANS,
        normalized_source_value=_annual_total_to_monthly_thousands(BTL_2011_ANNUAL_LOANS),
        source_units="count/year",
        comparison_units="thousand count/month",
        source_as_of="2011 annual total reported Feb 2012",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_best_available_proxy_monthly_mean",
        band_notes=(
            "Best-available tracked 2011 proxy from public reports quoting CML statistics. "
            "The tracked figure is the 2011 buy-to-let house-purchase total, not total BTL lending, matching the "
            "2024 metric definition. It is converted to thousand count/month before applying a fixed +/-15% band "
            "because no cleaner repo-local primary 2011 file is tracked."
        ),
        source_references=(
            MetricSourceReference(
                label="Mortgage Strategy report quoting 2011 CML buy-to-let house-purchase total",
                source_document_path=CML_2011_TEXT_PATH,
                source_text_path=CML_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="Buy-to-let house purchases",
                raw_source_value=BTL_2011_ANNUAL_LOANS,
                source_as_of="Published 9 Feb 2012",
                source_units="count/year",
                notes="Secondary-source report quoting the 2011 CML buy-to-let house-purchase total.",
            ),
        ),
    ),
    "core_debtToIncome": MetricSourceMetadata(
        source_document_path=BOE_2011_SNAPSHOT_PATH,
        source_text_path=BOE_2011_TEXT_PATH,
        source_table="Repo-local 2011 Bank of England housing-tools snapshot",
        source_page=1,
        source_indicator_label="Household debt to income ratio, 2011 annual mean",
        raw_source_value=_annual_mean(DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
        normalized_source_value=_annual_mean(DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
        source_units="%",
        comparison_units="%",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_quarterly_range",
        band_notes=(
            "Uses the observed 2011 quarterly Bank of England debt-to-income series. "
            "The source value is the 2011 annual mean and the target band uses the observed quarterly range."
        ),
    ),
    "core_priceToIncome": MetricSourceMetadata(
        source_document_path=BOE_2011_SNAPSHOT_PATH,
        source_text_path=BOE_2011_TEXT_PATH,
        source_table="Repo-local 2011 Bank of England housing-tools snapshot",
        source_page=1,
        source_indicator_label="House price to disposable income ratio, 2011 annual mean",
        raw_source_value=_annual_mean(PRICE_TO_INCOME_2011_QUARTERLY_VALUES),
        normalized_source_value=_annual_mean(PRICE_TO_INCOME_2011_QUARTERLY_VALUES),
        source_units="ratio",
        comparison_units="ratio",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_quarterly_range",
        band_notes=(
            "Uses the observed 2011 quarterly Bank of England price-to-income series. "
            "The source value is the 2011 annual mean and the target band uses the observed quarterly range."
        ),
    ),
    "core_housePriceGrowth": MetricSourceMetadata(
        source_document_path=BOE_2011_SNAPSHOT_PATH,
        source_text_path=BOE_2011_TEXT_PATH,
        source_table="Repo-local 2011 Bank of England housing-tools snapshot",
        source_page=1,
        source_indicator_label="House price growth, 2011 annual mean",
        raw_source_value=HOUSE_PRICE_GROWTH_2011_ANNUAL_MEAN,
        normalized_source_value=HOUSE_PRICE_GROWTH_2011_ANNUAL_MEAN,
        source_units="%",
        comparison_units="%",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_monthly_range",
        band_notes=(
            "Uses the observed 2011 monthly Bank of England house-price-growth series. "
            "The source value is the annual mean and the target band uses the observed monthly range."
        ),
    ),
    "core_hpiMean": MetricSourceMetadata(
        source_document_path=HMLR_2011_SNAPSHOT_PATH,
        source_text_path=HMLR_2011_TEXT_PATH,
        source_table="United Kingdom IndexSA rows for 2011-01 through 2011-12, rebased to 2011-01 = 1.0",
        source_page=1,
        source_indicator_label="Rebased UK seasonally adjusted HPI, 2011 annual mean",
        raw_source_value=HPI_2011_REBASED_MEAN,
        normalized_source_value=HPI_2011_REBASED_MEAN,
        source_units="rebased index",
        comparison_units="rebased index",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_value",
        band_notes=(
            "Derived from the tracked official-source UK HPI history through 2011-12. "
            "The UK IndexSA series is rebased to January 2011 = 1.0 before computing the annual mean, matching the "
            "2024 HPI-mean definition with the target year anchored to 2011."
        ),
        source_references=(
            MetricSourceReference(
                label="Repo-local HPI 2011 derived-value audit",
                source_document_path=HMLR_2011_DERIVED_VALUES_PATH,
                source_text_path=HMLR_2011_TEXT_PATH,
                source_table="hpiMean2011RebasedToJan2011",
                source_page=1,
                source_indicator_label="Rebased UK seasonally adjusted HPI annual mean",
                raw_source_value=HPI_2011_REBASED_MEAN,
                source_as_of="2011 annual mean",
                source_units="rebased index",
                notes="Derived from the tracked UK IndexSA snapshot through 2011-12.",
            ),
        ),
    ),
    "core_hpiStd": replace(
        MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiStd"],
        band_notes=(
            "Deliberate cross-year normalization exception for the 2011 overlay. "
            "This metric reuses the exact 2024 official-source std definition and scalar over 2005-01 through "
            "2024-12 so the 2011 baseline is benchmarked against the same official volatility standard as the "
            "2024 framework."
        ),
    ),
    "core_hpiCyclePeriod": MetricSourceMetadata(
        source_document_path=HMLR_2011_SNAPSHOT_PATH,
        source_text_path=HMLR_2011_TEXT_PATH,
        source_table=(
            "United Kingdom Index history through 2011-12; 12-month moving average, log transform, "
            "linear detrend, FFT dominant peak over 60..240 months"
        ),
        source_page=1,
        source_indicator_label="UK HPI dominant cycle period",
        raw_source_value=HPI_2011_CYCLE_PERIOD_MONTHS,
        normalized_source_value=HPI_2011_CYCLE_PERIOD_MONTHS,
        source_units="months",
        comparison_units="months",
        source_as_of="1968-04 to 2011-12 history",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_value",
        band_notes=(
            "Derived from the tracked official-source UK HPI history through 2011-12 using the locked 12-month "
            "moving-average, log-detrend, FFT peak-search method over 60..240 months. This matches the 2024 "
            "cycle-period definition with the available history anchored to December 2011."
        ),
        source_references=(
            MetricSourceReference(
                label="Repo-local HPI 2011 derived-value audit",
                source_document_path=HMLR_2011_DERIVED_VALUES_PATH,
                source_text_path=HMLR_2011_TEXT_PATH,
                source_table="hpiCyclePeriodMonthsThrough2011_12",
                source_page=1,
                source_indicator_label="UK HPI dominant cycle period",
                raw_source_value=HPI_2011_CYCLE_PERIOD_MONTHS,
                source_as_of="1968-04 to 2011-12 history",
                source_units="months",
                notes="Derived from the tracked UK Index history through 2011-12.",
            ),
        ),
    ),
    "rpi_mean": MetricSourceMetadata(
        source_document_path=ONS_RPI_2011_DOCUMENT_PATH,
        source_text_path=ONS_RPI_2011_TEXT_PATH,
        source_table="Table 1: Great Britain index rows for 2011-01 through 2011-12, rebased to 2011-01 = 1.0",
        source_page=1,
        source_indicator_label="Rebased Great Britain Rental Price Index, 2011 annual mean",
        raw_source_value=RPI_2011_GB_REBASED_MEAN,
        normalized_source_value=RPI_2011_GB_REBASED_MEAN,
        source_units="rebased index",
        comparison_units="rebased index",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_rebased_monthly_range",
        band_notes=(
            "Uses the ONS Price Index of Private Rents historical-series Great Britain index because the downloaded "
            "workbook marks the UK series as unavailable in 2011. Monthly values are rebased to January 2011 = 1.0; "
            "the target band is the observed 2011 rebased monthly min/max."
        ),
        source_references=(
            MetricSourceReference(
                label="ONS Price Index of Private Rents, UK: historical series",
                source_document_path=ONS_RPI_2011_DOCUMENT_PATH,
                source_text_path=ONS_RPI_2011_TEXT_PATH,
                source_table="Table 1",
                source_page=1,
                source_indicator_label="Great Britain rental price index",
                raw_source_value=RPI_2011_GB_REBASED_MEAN,
                source_as_of="2011 annual mean after rebasing to January 2011",
                source_units="rebased index",
                notes="Rental Price Index target; this is not Retail Prices Index.",
            ),
        ),
    ),
    "household_owning_share": MetricSourceMetadata(
        source_document_path=FRS_TENURE_2011_DOCUMENT_PATH,
        source_text_path=FRS_TENURE_2011_TEXT_PATH,
        source_table="Family Resources Survey 2010/11 table 3.1: Households by tenure, United Kingdom",
        source_page=40,
        source_indicator_label="Owner-occupied households, owned outright plus buying with a mortgage",
        raw_source_value=HOUSEHOLD_OWNING_SHARE_2011,
        normalized_source_value=HOUSEHOLD_OWNING_SHARE_2011,
        source_units="%",
        comparison_units="%",
        source_as_of="financial year 2010/11",
        mapping_status="derived_match",
        band_method="published_rounded_percentage_interval",
        band_notes=(
            "FRS table 3.1 publishes whole-percent household tenure shares. Target band is the rounded-value "
            "interval [65.5, 66.5] around the published 66% owner-occupied share."
        ),
        source_references=(
            MetricSourceReference(
                label="DWP Family Resources Survey 2010/11 table 3.1",
                source_document_path=FRS_TENURE_2011_DOCUMENT_PATH,
                source_text_path=FRS_TENURE_2011_TEXT_PATH,
                source_table="Table 3.1",
                source_page=40,
                source_indicator_label="All owners 66%",
                raw_source_value=HOUSEHOLD_OWNING_SHARE_2011,
                source_as_of="financial year 2010/11",
                source_units="%",
                notes="Owner-occupied share is published as 66%.",
            ),
        ),
    ),
    "household_renting_share": MetricSourceMetadata(
        source_document_path=FRS_TENURE_2011_DOCUMENT_PATH,
        source_text_path=FRS_TENURE_2011_TEXT_PATH,
        source_table="Family Resources Survey 2010/11 table 3.1: Households by tenure, United Kingdom",
        source_page=40,
        source_indicator_label="Private renting sector households",
        raw_source_value=HOUSEHOLD_RENTING_SHARE_2011,
        normalized_source_value=HOUSEHOLD_RENTING_SHARE_2011,
        source_units="%",
        comparison_units="%",
        source_as_of="financial year 2010/11",
        mapping_status="derived_match",
        band_method="published_rounded_percentage_interval",
        band_notes=(
            "FRS table 3.1 publishes whole-percent household tenure shares. Target band is the rounded-value "
            "interval [16.5, 17.5] around the published 17% private-rented-sector share. Social renting is excluded "
            "to match model HousingStatus == 1."
        ),
        source_references=(
            MetricSourceReference(
                label="DWP Family Resources Survey 2010/11 table 3.1",
                source_document_path=FRS_TENURE_2011_DOCUMENT_PATH,
                source_text_path=FRS_TENURE_2011_TEXT_PATH,
                source_table="Table 3.1",
                source_page=40,
                source_indicator_label="Rented privately 17%",
                raw_source_value=HOUSEHOLD_RENTING_SHARE_2011,
                source_as_of="financial year 2010/11",
                source_units="%",
                notes="Private renting is used because model HousingStatus == 1 excludes social housing.",
            ),
        ),
    ),
    "core_ooDebtToIncome": MetricSourceMetadata(
        source_document_path=MLAR_2011_COMPONENTS_PATH,
        source_text_path=MLAR_2011_TEXT_PATH,
        source_table="Repo-local 2011 MLAR component snapshot plus trailing four-quarter ONS QWND denominator",
        source_page=1,
        source_indicator_label="Owner-occupier mortgage debt to income ratio, 2011 annual mean",
        raw_source_value=_annual_mean(OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
        normalized_source_value=_annual_mean(OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
        source_units="%",
        comparison_units="%",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_quarterly_range",
        band_notes=(
            "Reuses the locked 2024 owner-occupier debt-to-income reconstruction with the tracked 2011 MLAR "
            "components and the repo-local 2010Q2-2011Q4 ONS QWND denominator snapshot. "
            "The target band uses the observed 2011 quarterly range."
        ),
        source_references=(
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2011 Q1",
                source_document_path=MLAR_2011_COMPONENTS_PATH,
                source_text_path=MLAR_2011_TEXT_PATH,
                source_table="Quarterly reconstruction",
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES[0],
                source_as_of="2011 Q1",
                source_units="%",
                notes="Derived from the tracked MLAR 2011 components and trailing four-quarter ONS QWND income.",
            ),
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2011 Q2",
                source_document_path=MLAR_2011_COMPONENTS_PATH,
                source_text_path=MLAR_2011_TEXT_PATH,
                source_table="Quarterly reconstruction",
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES[1],
                source_as_of="2011 Q2",
                source_units="%",
                notes="Derived from the tracked MLAR 2011 components and trailing four-quarter ONS QWND income.",
            ),
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2011 Q3",
                source_document_path=MLAR_2011_COMPONENTS_PATH,
                source_text_path=MLAR_2011_TEXT_PATH,
                source_table="Quarterly reconstruction",
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES[2],
                source_as_of="2011 Q3",
                source_units="%",
                notes="Derived from the tracked MLAR 2011 components and trailing four-quarter ONS QWND income.",
            ),
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2011 Q4",
                source_document_path=MLAR_2011_COMPONENTS_PATH,
                source_text_path=MLAR_2011_TEXT_PATH,
                source_table="Quarterly reconstruction",
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES[3],
                source_as_of="2011 Q4",
                source_units="%",
                notes="Derived from the tracked MLAR 2011 components and trailing four-quarter ONS QWND income.",
            ),
            MetricSourceReference(
                label="ONS UKEA QWND 2010Q2-2011Q4 snapshot",
                source_document_path=ONS_QWND_2011_SNAPSHOT_PATH,
                source_text_path=MLAR_2011_TEXT_PATH,
                source_indicator_label="HH & NPISH disposable income, gross (QWND)",
                source_as_of="2010 Q2 to 2011 Q4",
                source_units="£m",
                notes="Repo-local ONS snapshot used to build the trailing four-quarter denominator.",
            ),
        ),
    ),
    "core_rentalYield": MetricSourceMetadata(
        source_document_path=BM_2011_TEXT_PATH,
        source_text_path=BM_2011_TEXT_PATH,
        source_table="Tracked public references quoting BM Solutions rental yields",
        source_page=1,
        source_indicator_label="Average gross buy-to-let rental yield for the UK, 2011 annual average",
        raw_source_value=RENTAL_YIELD_2011_ANNUAL,
        normalized_source_value=RENTAL_YIELD_2011_ANNUAL,
        source_units="%",
        comparison_units="%",
        source_as_of="2011 annual average reported Mar 2012",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_best_available_annual_proxy",
        band_notes=(
            "Best-available tracked 2011 proxy based on public reports of BM Solutions rental-yield releases. "
            "The tracked public archive does not provide a clean UK quarterly series comparable with the 2024 UK Finance data, "
            "so this 2011 overlay uses the annual UK average with a fixed +/-15% band."
        ),
        source_references=(
            MetricSourceReference(
                label="PropertyWire report quoting the 2011 BM Solutions UK annual rental yield",
                source_document_path=BM_2011_TEXT_PATH,
                source_text_path=BM_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="UK average gross rental yield",
                raw_source_value=RENTAL_YIELD_2011_ANNUAL,
                source_as_of="Published 27 Mar 2012",
                source_units="%",
                notes="Secondary-source report quoting the 2011 BM Solutions UK annual average.",
            ),
            MetricSourceReference(
                label="PropertyWire mid-2012 cross-check quoting June 2011 BM Solutions UK rental yield",
                source_document_path=BM_2011_TEXT_PATH,
                source_text_path=BM_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="UK average gross rental yield",
                raw_source_value=6.0,
                source_as_of="June 2011 quoted in Aug 2012 archive",
                source_units="%",
                notes="Secondary-source cross-check confirming the annual average sits near the archived UK mid-year value.",
            ),
            MetricSourceReference(
                label="PropertyWire cross-check quoting Q4 2011 BM Solutions mainstream vanilla yield",
                source_document_path=BM_2011_TEXT_PATH,
                source_text_path=BM_2011_TEXT_PATH,
                source_table="Tracked public references",
                source_page=1,
                source_indicator_label="Mainstream vanilla buy-to-let yield",
                raw_source_value=6.1,
                source_as_of="Q4 2011 quoted in Apr 2012 archive",
                source_units="%",
                notes="Secondary-source cross-check consistent with the annual UK average used by the overlay.",
            ),
        ),
    ),
    "core_interestRateSpread": MetricSourceMetadata(
        source_document_path=BOE_2011_SNAPSHOT_PATH,
        source_text_path=BOE_2011_TEXT_PATH,
        source_table="Repo-local 2011 Bank of England housing-tools snapshot; quarterly means derived from Jan-Dec 2011 monthly values",
        source_page=1,
        source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads, 2011 annual mean",
        raw_source_value=2.4800784641069633,
        normalized_source_value=2.4800784641069633,
        source_units="percentage points",
        comparison_units="percentage points",
        source_as_of="2011 annual mean",
        mapping_status="derived_match",
        band_method="observed_2011_quarterly_range",
        band_notes=(
            "Quarterly means from the tracked Jan-Dec 2011 monthly spread values: "
            "Q1=2.397573, Q2=2.452220, Q3=2.443696, Q4=2.626825. "
            "The target band uses the observed quarterly-mean range."
        ),
        source_references=(
            MetricSourceReference(
                label="Bank of England housing tools 2011 Q1 spread mean",
                source_document_path=BOE_2011_SNAPSHOT_PATH,
                source_text_path=BOE_2011_TEXT_PATH,
                source_table="interestRateSpread",
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS[0],
                source_as_of="2011 Q1",
                source_units="percentage points",
                notes="Mean of Jan-Mar 2011 monthly values from the tracked Bank of England snapshot.",
            ),
            MetricSourceReference(
                label="Bank of England housing tools 2011 Q2 spread mean",
                source_document_path=BOE_2011_SNAPSHOT_PATH,
                source_text_path=BOE_2011_TEXT_PATH,
                source_table="interestRateSpread",
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS[1],
                source_as_of="2011 Q2",
                source_units="percentage points",
                notes="Mean of Apr-Jun 2011 monthly values from the tracked Bank of England snapshot.",
            ),
            MetricSourceReference(
                label="Bank of England housing tools 2011 Q3 spread mean",
                source_document_path=BOE_2011_SNAPSHOT_PATH,
                source_text_path=BOE_2011_TEXT_PATH,
                source_table="interestRateSpread",
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS[2],
                source_as_of="2011 Q3",
                source_units="percentage points",
                notes="Mean of Jul-Sep 2011 monthly values from the tracked Bank of England snapshot.",
            ),
            MetricSourceReference(
                label="Bank of England housing tools 2011 Q4 spread mean",
                source_document_path=BOE_2011_SNAPSHOT_PATH,
                source_text_path=BOE_2011_TEXT_PATH,
                source_table="interestRateSpread",
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS[3],
                source_as_of="2011 Q4",
                source_units="percentage points",
                notes="Mean of Oct-Dec 2011 monthly values from the tracked Bank of England snapshot.",
            ),
        ),
    ),
}


TARGET_BANDS_2011_BY_METRIC_ID: dict[str, TargetBand] = {
    "core_mortgageApprovals": TargetBand(lower=42.883, upper=52.93),
    "core_housingTransactions": TargetBand(lower=68.68, upper=77.16),
    "core_advancesToFTB": TargetBand(lower=13.671, upper=18.496),
    "core_advancesToHM": TargetBand(lower=22.419, upper=30.331),
    "core_advancesToBTL": TargetBand(lower=5.95, upper=8.05),
    "core_debtToIncome": TargetBand(
        lower=min(DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
        upper=max(DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
    ),
    "core_priceToIncome": TargetBand(
        lower=min(PRICE_TO_INCOME_2011_QUARTERLY_VALUES),
        upper=max(PRICE_TO_INCOME_2011_QUARTERLY_VALUES),
    ),
    "core_housePriceGrowth": TargetBand(lower=-0.9449694274597076, upper=0.1702610669693572),
    "core_hpiMean": _plus_minus_tolerance_band(
        source_value=HPI_2011_REBASED_MEAN,
        tolerance=HPI_TARGET_TOLERANCE,
    ),
    "core_hpiStd": _plus_minus_tolerance_band(
        source_value=HPI_FULL_HISTORY_REBASED_STD,
        tolerance=HPI_TARGET_TOLERANCE,
    ),
    "core_hpiCyclePeriod": _plus_minus_tolerance_band(
        source_value=HPI_2011_CYCLE_PERIOD_MONTHS,
        tolerance=HPI_TARGET_TOLERANCE,
    ),
    "rpi_mean": TargetBand(
        lower=min(RPI_2011_GB_REBASED_MONTHLY_VALUES),
        upper=max(RPI_2011_GB_REBASED_MONTHLY_VALUES),
    ),
    "household_owning_share": TargetBand(lower=65.5, upper=66.5),
    "household_renting_share": TargetBand(lower=16.5, upper=17.5),
    "core_ooDebtToIncome": TargetBand(
        lower=min(OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
        upper=max(OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES),
    ),
    "core_rentalYield": _plus_minus_tolerance_band(
        source_value=RENTAL_YIELD_2011_ANNUAL,
        tolerance=ADVANCES_TARGET_TOLERANCE,
    ),
    "core_interestRateSpread": TargetBand(
        lower=min(INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS),
        upper=max(INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS),
    ),
}


def _coerce_2011_metric(metric: MetricDefinition) -> MetricDefinition:
    metric_id = metric.metric_id
    return replace(
        metric,
        source_label=SOURCE_LABEL_2011_BY_METRIC_ID.get(metric_id, metric.source_label),
        source_metadata=SOURCE_METADATA_2011_BY_METRIC_ID.get(metric_id, metric.source_metadata),
        target_band=TARGET_BANDS_2011_BY_METRIC_ID.get(metric_id, metric.target_band),
    )


TARGET_CATALOG = tuple(_coerce_2011_metric(metric) for metric in TARGET_CATALOG_2024)
TARGETS_BY_ID = {metric.metric_id: metric for metric in TARGET_CATALOG}

__all__ = [
    "ADVANCES_TARGET_TOLERANCE",
    "FTB_2011_ANNUAL_LOANS",
    "HM_2011_ANNUAL_LOANS",
    "BTL_2011_ANNUAL_LOANS",
    "HPI_2011_CYCLE_PERIOD_MONTHS",
    "HPI_2011_REBASED_MEAN",
    "HPI_2011_REBASED_STD",
    "HOUSEHOLD_OWNING_SHARE_2011",
    "HOUSEHOLD_RENTING_SHARE_2011",
    "INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS",
    "OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES",
    "RENTAL_YIELD_2011_ANNUAL",
    "RPI_2011_GB_REBASED_MEAN",
    "RPI_2011_GB_REBASED_MONTHLY_VALUES",
    "SOURCE_METADATA_2011_BY_METRIC_ID",
    "TARGET_BANDS_2011_BY_METRIC_ID",
    "TARGET_CATALOG",
    "TARGETS_BY_ID",
    "WAS_WAVE_3_SOURCE_LABEL",
]
