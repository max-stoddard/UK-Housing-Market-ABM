"""Canonical 2024 validation catalog and provenance metadata.

@author: Max Stoddard
"""

from __future__ import annotations

from statistics import fmean

from scripts.python.validation.model.schema import (
    MetricDefinition,
    MetricSourceMetadata,
    MetricSourceReference,
    TargetBand,
)

FPC_SOURCE_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/cis/fpc-core-indicators-june-2024.pdf"
FPC_SOURCE_TEXT_PATH = "input-data-versions/validation-sources/2024/cis/fpc-core-indicators-june-2024.txt"
FPC_TABLE_LTV_DTI_LIMITS = "Table A.2: Core indicator set for LTV and DTI limits"

SUPPORTED_FPC_METRIC_IDS = (
    "core_mortgageApprovals",
    "core_housingTransactions",
    "core_debtToIncome",
    "core_housePriceGrowth",
    "core_priceToIncome",
    "core_interestRateSpread",
)

UNSUPPORTED_FPC_METRIC_IDS = (
    "core_advancesToFTB",
    "core_advancesToHM",
    "core_advancesToBTL",
    "core_hpiMean",
    "core_hpiStd",
    "core_hpiCyclePeriod",
    "core_ooDebtToIncome",
    "core_rentalYield",
)

FPC_SOURCE_2024_BY_METRIC_ID: dict[str, MetricSourceMetadata] = {
    "core_mortgageApprovals": MetricSourceMetadata(
        source_document_path=FPC_SOURCE_DOCUMENT_PATH,
        source_text_path=FPC_SOURCE_TEXT_PATH,
        source_table=FPC_TABLE_LTV_DTI_LIMITS,
        source_page=5,
        source_indicator_label="Mortgage approvals",
        raw_source_value=61325.0,
        normalized_source_value=61.325,
        source_units="count/month",
        comparison_units="thousand count/month",
        source_as_of="Mar 2024",
        mapping_status="exact_match",
    ),
    "core_housingTransactions": MetricSourceMetadata(
        source_document_path=FPC_SOURCE_DOCUMENT_PATH,
        source_text_path=FPC_SOURCE_TEXT_PATH,
        source_table=FPC_TABLE_LTV_DTI_LIMITS,
        source_page=5,
        source_indicator_label="Housing transactions",
        raw_source_value=84200.0,
        normalized_source_value=84.2,
        source_units="count/month",
        comparison_units="thousand count/month",
        source_as_of="Mar 2024",
        mapping_status="exact_match",
    ),
    "core_debtToIncome": MetricSourceMetadata(
        source_document_path=FPC_SOURCE_DOCUMENT_PATH,
        source_text_path=FPC_SOURCE_TEXT_PATH,
        source_table=FPC_TABLE_LTV_DTI_LIMITS,
        source_page=5,
        source_indicator_label="Household debt to income ratio",
        raw_source_value=133.8,
        normalized_source_value=133.8,
        source_units="%",
        comparison_units="%",
        source_as_of="2023Q4",
        mapping_status="derived_match",
    ),
    "core_housePriceGrowth": MetricSourceMetadata(
        source_document_path=FPC_SOURCE_DOCUMENT_PATH,
        source_text_path=FPC_SOURCE_TEXT_PATH,
        source_table=FPC_TABLE_LTV_DTI_LIMITS,
        source_page=5,
        source_indicator_label="House price growth",
        raw_source_value=1.1,
        normalized_source_value=1.1,
        source_units="%",
        comparison_units="%",
        source_as_of="Mar 2024",
        mapping_status="exact_match",
    ),
    "core_priceToIncome": MetricSourceMetadata(
        source_document_path=FPC_SOURCE_DOCUMENT_PATH,
        source_text_path=FPC_SOURCE_TEXT_PATH,
        source_table=FPC_TABLE_LTV_DTI_LIMITS,
        source_page=5,
        source_indicator_label="House price to household disposable income ratio",
        raw_source_value=5.4,
        normalized_source_value=5.4,
        source_units="ratio",
        comparison_units="ratio",
        source_as_of="2023Q4",
        mapping_status="derived_match",
    ),
    "core_interestRateSpread": MetricSourceMetadata(
        source_document_path=FPC_SOURCE_DOCUMENT_PATH,
        source_text_path=FPC_SOURCE_TEXT_PATH,
        source_table=FPC_TABLE_LTV_DTI_LIMITS,
        source_page=5,
        source_indicator_label="Spreads on new owner-occupier mortgages with 2-year fix and 75% LTV",
        raw_source_value=0.53,
        normalized_source_value=0.53,
        source_units="percentage points",
        comparison_units="percentage points",
        source_as_of="Mar 2024",
        mapping_status="derived_match",
    ),
}

UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/ukf/Household Finance Review 2024 Q4.pdf"
UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TEXT_PATH = (
    "input-data-versions/validation-sources/2024/ukf/household-finance-review-2024-q4-validation-evidence.txt"
)
UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TABLE = "Table 1: Key annual mortgage figures"

UKF_BTL_Q1_2024_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q1.pdf"
UKF_BTL_Q2_2024_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q2.pdf"
UKF_BTL_Q3_2024_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q3.pdf"
UKF_BTL_Q4_2024_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q4.pdf"
UKF_BTL_2024_TEXT_PATH = "input-data-versions/validation-sources/2024/ukf/btl-mortgage-market-update-2024-validation-evidence.txt"
UKF_BTL_2024_TABLE = "Latest 2024 Q* summary panels"

ADVANCES_TARGET_TOLERANCE = 0.15
HPI_TARGET_TOLERANCE = 0.15

FTB_ANNUAL_LOANS = 334_000.0
HM_ANNUAL_LOANS = 288_000.0
BTL_HOUSE_PURCHASE_Q1 = 12_422.0
BTL_HOUSE_PURCHASE_Q2 = 14_955.0
BTL_HOUSE_PURCHASE_Q3 = 16_410.0
BTL_HOUSE_PURCHASE_Q4 = 18_268.0
BTL_ANNUAL_LOANS = BTL_HOUSE_PURCHASE_Q1 + BTL_HOUSE_PURCHASE_Q2 + BTL_HOUSE_PURCHASE_Q3 + BTL_HOUSE_PURCHASE_Q4


def _annual_total_to_monthly_thousands(raw_value: float) -> float:
    return raw_value / 12.0 / 1_000.0


def _plus_minus_tolerance_band(*, source_value: float, tolerance: float) -> TargetBand:
    return TargetBand(
        lower=source_value * (1.0 - tolerance),
        upper=source_value * (1.0 + tolerance),
    )


UKF_SOURCE_2024_BY_METRIC_ID: dict[str, MetricSourceMetadata] = {
    "core_advancesToFTB": MetricSourceMetadata(
        source_document_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_DOCUMENT_PATH,
        source_text_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TEXT_PATH,
        source_table=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TABLE,
        source_page=6,
        source_indicator_label="Number of residential purchase loans: First-time buyers",
        raw_source_value=FTB_ANNUAL_LOANS,
        normalized_source_value=_annual_total_to_monthly_thousands(FTB_ANNUAL_LOANS),
        source_units="count/year",
        comparison_units="thousand count/month",
        source_as_of="2024 annual total",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_monthly_mean",
        band_notes="Converted 2024 annual total to monthly mean: 334,000 / 12 / 1,000 = 27.833.",
        source_references=(
            MetricSourceReference(
                label="UK Finance Household Finance Review 2024 Q4",
                source_document_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_DOCUMENT_PATH,
                source_text_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TEXT_PATH,
                source_table=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TABLE,
                source_page=6,
                source_indicator_label="First-time buyers",
                raw_source_value=FTB_ANNUAL_LOANS,
                source_as_of="2024 annual total",
                source_units="count/year",
                notes="Annual total converted to monthly mean for validation.",
            ),
        ),
    ),
    "core_advancesToHM": MetricSourceMetadata(
        source_document_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_DOCUMENT_PATH,
        source_text_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TEXT_PATH,
        source_table=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TABLE,
        source_page=6,
        source_indicator_label="Number of residential purchase loans: Homemovers",
        raw_source_value=HM_ANNUAL_LOANS,
        normalized_source_value=_annual_total_to_monthly_thousands(HM_ANNUAL_LOANS),
        source_units="count/year",
        comparison_units="thousand count/month",
        source_as_of="2024 annual total",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_monthly_mean",
        band_notes="Converted 2024 annual total to monthly mean: 288,000 / 12 / 1,000 = 24.000.",
        source_references=(
            MetricSourceReference(
                label="UK Finance Household Finance Review 2024 Q4",
                source_document_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_DOCUMENT_PATH,
                source_text_path=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TEXT_PATH,
                source_table=UKF_HOUSEHOLD_FINANCE_REVIEW_Q4_2024_TABLE,
                source_page=6,
                source_indicator_label="Homemovers",
                raw_source_value=HM_ANNUAL_LOANS,
                source_as_of="2024 annual total",
                source_units="count/year",
                notes="Annual total converted to monthly mean for validation.",
            ),
        ),
    ),
    "core_advancesToBTL": MetricSourceMetadata(
        source_document_path=UKF_BTL_Q4_2024_DOCUMENT_PATH,
        source_text_path=UKF_BTL_2024_TEXT_PATH,
        source_table="2024 house-purchase BTL counts aggregated from Q1-Q4 summary panels",
        source_page=2,
        source_indicator_label="House purchase BTL loans, annual sum of 2024 quarterly counts",
        raw_source_value=BTL_ANNUAL_LOANS,
        normalized_source_value=_annual_total_to_monthly_thousands(BTL_ANNUAL_LOANS),
        source_units="count/year",
        comparison_units="thousand count/month",
        source_as_of="2024 annualized monthly mean",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_monthly_mean",
        band_notes=(
            "Quarterly house-purchase counts 12,422 + 14,955 + 16,410 + 18,268 converted to "
            "monthly mean: 62,055 / 12 / 1,000 = 5.171."
        ),
        source_references=(
            MetricSourceReference(
                label="UK Finance BTL Mortgage Market Update Q1 2024",
                source_document_path=UKF_BTL_Q1_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_2024_TEXT_PATH,
                source_table="Latest 2024 Q1 summary panel",
                source_page=2,
                source_indicator_label="House purchase",
                raw_source_value=BTL_HOUSE_PURCHASE_Q1,
                source_as_of="Q1 2024",
                source_units="count/quarter",
                notes="Quarterly house-purchase BTL count used in the 2024 annual sum.",
            ),
            MetricSourceReference(
                label="UK Finance BTL Mortgage Market Update Q2 2024",
                source_document_path=UKF_BTL_Q2_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_2024_TEXT_PATH,
                source_table="Latest 2024 Q2 summary panel",
                source_page=2,
                source_indicator_label="House purchase",
                raw_source_value=BTL_HOUSE_PURCHASE_Q2,
                source_as_of="Q2 2024",
                source_units="count/quarter",
                notes="Quarterly house-purchase BTL count used in the 2024 annual sum.",
            ),
            MetricSourceReference(
                label="UK Finance BTL Mortgage Market Update Q3 2024",
                source_document_path=UKF_BTL_Q3_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_2024_TEXT_PATH,
                source_table="Latest 2024 Q3 summary panel",
                source_page=2,
                source_indicator_label="House purchase",
                raw_source_value=BTL_HOUSE_PURCHASE_Q3,
                source_as_of="Q3 2024",
                source_units="count/quarter",
                notes="Quarterly house-purchase BTL count used in the 2024 annual sum.",
            ),
            MetricSourceReference(
                label="UK Finance BTL Mortgage Market Update Q4 2024",
                source_document_path=UKF_BTL_Q4_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_2024_TEXT_PATH,
                source_table="Latest 2024 Q4 summary panel",
                source_page=2,
                source_indicator_label="House purchase",
                raw_source_value=BTL_HOUSE_PURCHASE_Q4,
                source_as_of="Q4 2024",
                source_units="count/quarter",
                notes="Quarterly house-purchase BTL count used in the 2024 annual sum.",
            ),
        ),
    ),
}

BOE_HOUSING_TOOLS_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/boe/housing-tools.xlsx"
BOE_HOUSING_TOOLS_TEXT_PATH = "input-data-versions/validation-sources/2024/boe/housing-tools-2024-validation-evidence.txt"
BOE_HOUSING_TOOLS_SPREAD_TABLE = "Sheet 8. Spreads new mortgage lending"
HMLR_HPI_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/hmlr/UK-HPI-full-file-2024-12.csv"
HMLR_HPI_TEXT_PATH = "input-data-versions/validation-sources/2024/hmlr/hpi-2024-validation-evidence.txt"

UKF_BTL_RENTAL_YIELD_TEXT_PATH = "input-data-versions/validation-sources/2024/ukf/btl-rental-yield-2024-validation-evidence.txt"
UKF_BTL_RENTAL_YIELD_TABLE = "Page 2 summary panels"

MLAR_LONGRUN_DETAILED_DOCUMENT_PATH = "input-data-versions/validation-sources/2024/mlar/mlar-longrun-detailed.xlsx"
MLAR_OO_DTI_TEXT_PATH = "input-data-versions/validation-sources/2024/mlar/oo-debt-to-income-2024-validation-evidence.txt"
MLAR_OO_DTI_TABLE = "Sheet 1.11 row 33 and sheet 1.33 rows 41, 53, 91, 95"
ONS_QWND_2024_SNAPSHOT_PATH = "input-data-versions/validation-sources/2024/ons/qwnd-household-gross-disposable-income-2023q2-2024q4.json"

INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS = (
    0.45451643114650303,
    0.5779458190668597,
    0.7203665256287551,
    0.41196363761794147,
)
HPI_2024_REBASED_MEAN = 1.0196877121520707
HPI_2024_REBASED_STD = 0.013499008027934953
HPI_FULL_HISTORY_REBASED_STD = 0.2766701944903836
HPI_2024_CYCLE_PERIOD_MONTHS = 167.5
RENTAL_YIELD_2024_QUARTERLY_VALUES = (6.88, 6.90, 6.93, 7.00)
OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES = (
    80.29246428438624,
    79.53408125437869,
    78.19382253716438,
    77.16710908000836,
)


def _annual_mean(values: tuple[float, ...]) -> float:
    return float(fmean(values))


MARKET_SOURCE_2024_BY_METRIC_ID: dict[str, MetricSourceMetadata] = {
    "core_hpiMean": MetricSourceMetadata(
        source_document_path=HMLR_HPI_DOCUMENT_PATH,
        source_text_path=HMLR_HPI_TEXT_PATH,
        source_table="United Kingdom IndexSA rows for 2024-01 through 2024-12, rebased to 2024-01 = 1.0",
        source_page=1,
        source_indicator_label="Rebased UK seasonally adjusted HPI, 2024 annual mean",
        raw_source_value=HPI_2024_REBASED_MEAN,
        normalized_source_value=HPI_2024_REBASED_MEAN,
        source_units="rebased index",
        comparison_units="rebased index",
        source_as_of="2024 annual mean",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_value",
        band_notes=(
            "2024 UK IndexSA values rebased to January 2024 = 1.0 before computing the annual mean. "
            "Target band is +/-15% around the official rebased mean."
        ),
        source_references=(
            MetricSourceReference(
                label="HM Land Registry UK HPI full file December 2024",
                source_document_path=HMLR_HPI_DOCUMENT_PATH,
                source_text_path=HMLR_HPI_TEXT_PATH,
                source_table="United Kingdom IndexSA rows for 2024-01 through 2024-12",
                source_page=1,
                source_indicator_label="UK HPI IndexSA",
                raw_source_value=HPI_2024_REBASED_MEAN,
                source_as_of="2024 annual mean after rebasing to January 2024",
                source_units="rebased index",
                notes="Official IndexSA values are rebased to January 2024 = 1.0 before computing the 2024 mean.",
            ),
        ),
    ),
    "core_hpiStd": MetricSourceMetadata(
        source_document_path=HMLR_HPI_DOCUMENT_PATH,
        source_text_path=HMLR_HPI_TEXT_PATH,
        source_table="United Kingdom IndexSA rows for 2005-01 through 2024-12, rebased to 2005-01 = 1.0",
        source_page=1,
        source_indicator_label="Rebased UK seasonally adjusted HPI, 2005-01 to 2024-12 population std",
        raw_source_value=HPI_FULL_HISTORY_REBASED_STD,
        normalized_source_value=HPI_FULL_HISTORY_REBASED_STD,
        source_units="rebased index",
        comparison_units="rebased index",
        source_as_of="2005-01 to 2024-12 population std",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_value",
        band_notes=(
            "United Kingdom IndexSA values from 2005-01 through 2024-12 are rebased to January 2005 = 1.0 before "
            "computing the long-run population standard deviation. Target band is +/-15% around the official rebased std."
        ),
        source_references=(
            MetricSourceReference(
                label="HM Land Registry UK HPI full file December 2024",
                source_document_path=HMLR_HPI_DOCUMENT_PATH,
                source_text_path=HMLR_HPI_TEXT_PATH,
                source_table="United Kingdom IndexSA rows for 2005-01 through 2024-12",
                source_page=1,
                source_indicator_label="UK HPI IndexSA",
                raw_source_value=HPI_FULL_HISTORY_REBASED_STD,
                source_as_of="2005-01 to 2024-12 population std after rebasing to January 2005",
                source_units="rebased index",
                notes=(
                    "Official IndexSA values from 2005-01 through 2024-12 are rebased to January 2005 = 1.0 before "
                    "computing the long-run population std."
                ),
            ),
        ),
    ),
    "core_interestRateSpread": MetricSourceMetadata(
        source_document_path=BOE_HOUSING_TOOLS_DOCUMENT_PATH,
        source_text_path=BOE_HOUSING_TOOLS_TEXT_PATH,
        source_table=f"{BOE_HOUSING_TOOLS_SPREAD_TABLE}; quarterly means derived from Jan-Dec 2024 monthly values",
        source_page=1,
        source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads, 2024 annual mean",
        raw_source_value=_annual_mean(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS),
        normalized_source_value=_annual_mean(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS),
        source_units="percentage points",
        comparison_units="percentage points",
        source_as_of="2024 annual mean",
        mapping_status="derived_match",
        band_method="observed_2024_quarterly_range",
        band_notes=(
            "Quarterly means from 2024 monthly values: "
            "Q1=0.454516, Q2=0.577946, Q3=0.720367, Q4=0.411964. "
            "Target band uses the observed quarterly range."
        ),
        source_references=(
            MetricSourceReference(
                label="Bank of England housing tools 2024 Q1 spread mean",
                source_document_path=BOE_HOUSING_TOOLS_DOCUMENT_PATH,
                source_text_path=BOE_HOUSING_TOOLS_TEXT_PATH,
                source_table=BOE_HOUSING_TOOLS_SPREAD_TABLE,
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS[0],
                source_as_of="2024 Q1",
                source_units="percentage points",
                notes="Mean of Jan-Mar 2024 monthly values from the workbook series.",
            ),
            MetricSourceReference(
                label="Bank of England housing tools 2024 Q2 spread mean",
                source_document_path=BOE_HOUSING_TOOLS_DOCUMENT_PATH,
                source_text_path=BOE_HOUSING_TOOLS_TEXT_PATH,
                source_table=BOE_HOUSING_TOOLS_SPREAD_TABLE,
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS[1],
                source_as_of="2024 Q2",
                source_units="percentage points",
                notes="Mean of Apr-Jun 2024 monthly values from the workbook series.",
            ),
            MetricSourceReference(
                label="Bank of England housing tools 2024 Q3 spread mean",
                source_document_path=BOE_HOUSING_TOOLS_DOCUMENT_PATH,
                source_text_path=BOE_HOUSING_TOOLS_TEXT_PATH,
                source_table=BOE_HOUSING_TOOLS_SPREAD_TABLE,
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS[2],
                source_as_of="2024 Q3",
                source_units="percentage points",
                notes="Mean of Jul-Sep 2024 monthly values from the workbook series.",
            ),
            MetricSourceReference(
                label="Bank of England housing tools 2024 Q4 spread mean",
                source_document_path=BOE_HOUSING_TOOLS_DOCUMENT_PATH,
                source_text_path=BOE_HOUSING_TOOLS_TEXT_PATH,
                source_table=BOE_HOUSING_TOOLS_SPREAD_TABLE,
                source_page=1,
                source_indicator_label="Mortgage 2-year 75% LTV owner-occupier spreads",
                raw_source_value=INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS[3],
                source_as_of="2024 Q4",
                source_units="percentage points",
                notes="Mean of Oct-Dec 2024 monthly values from the workbook series.",
            ),
        ),
    ),
    "core_hpiCyclePeriod": MetricSourceMetadata(
        source_document_path=HMLR_HPI_DOCUMENT_PATH,
        source_text_path=HMLR_HPI_TEXT_PATH,
        source_table=(
            "United Kingdom Index history through 2024-12; 12-month moving average, log transform, "
            "linear detrend, FFT dominant peak over 60..240 months"
        ),
        source_page=1,
        source_indicator_label="UK HPI dominant cycle period",
        raw_source_value=HPI_2024_CYCLE_PERIOD_MONTHS,
        normalized_source_value=HPI_2024_CYCLE_PERIOD_MONTHS,
        source_units="months",
        comparison_units="months",
        source_as_of="1968-04 to 2024-12 history, December 2024 release",
        mapping_status="derived_match",
        band_method="fixed_plus_minus_15pct_around_official_value",
        band_notes=(
            "Cycle period is derived from the archived United Kingdom Index history through December 2024 using the "
            "locked 12-month moving-average, log-detrend, FFT peak-search method over 60..240 months. "
            "Target band is +/-15% around the official derived period."
        ),
        source_references=(
            MetricSourceReference(
                label="HM Land Registry UK HPI full file December 2024",
                source_document_path=HMLR_HPI_DOCUMENT_PATH,
                source_text_path=HMLR_HPI_TEXT_PATH,
                source_table="United Kingdom Index history through 2024-12",
                source_page=1,
                source_indicator_label="UK HPI Index",
                raw_source_value=HPI_2024_CYCLE_PERIOD_MONTHS,
                source_as_of="1968-04 to 2024-12 history",
                source_units="months",
                notes="Derived with a 12-month moving average, log transform, linear detrend, and FFT peak search over 60..240 months.",
            ),
        ),
    ),
    "core_rentalYield": MetricSourceMetadata(
        source_document_path=UKF_BTL_Q4_2024_DOCUMENT_PATH,
        source_text_path=UKF_BTL_RENTAL_YIELD_TEXT_PATH,
        source_table="Average gross buy-to-let rental yield for the UK aggregated across 2024 Q1-Q4",
        source_page=2,
        source_indicator_label="Average gross buy-to-let rental yield for the UK, 2024 annual mean",
        raw_source_value=_annual_mean(RENTAL_YIELD_2024_QUARTERLY_VALUES),
        normalized_source_value=_annual_mean(RENTAL_YIELD_2024_QUARTERLY_VALUES),
        source_units="%",
        comparison_units="%",
        source_as_of="2024 annual mean",
        mapping_status="derived_match",
        band_method="observed_2024_quarterly_range",
        band_notes=(
            "Quarterly values from UK Finance page 2 summary panels: "
            "Q1=6.88, Q2=6.90, Q3=6.93, Q4=7.00. "
            "Target band uses the observed quarterly range."
        ),
        source_references=(
            MetricSourceReference(
                label="UK Finance Buy to let Mortgage Market Update Q1 2024",
                source_document_path=UKF_BTL_Q1_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_RENTAL_YIELD_TEXT_PATH,
                source_table=UKF_BTL_RENTAL_YIELD_TABLE,
                source_page=2,
                source_indicator_label="Average gross buy-to-let rental yield for the UK",
                raw_source_value=RENTAL_YIELD_2024_QUARTERLY_VALUES[0],
                source_as_of="2024 Q1",
                source_units="%",
                notes="Quarterly rental-yield value from the UK Finance summary panel.",
            ),
            MetricSourceReference(
                label="UK Finance Buy to let Mortgage Market Update Q2 2024",
                source_document_path=UKF_BTL_Q2_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_RENTAL_YIELD_TEXT_PATH,
                source_table=UKF_BTL_RENTAL_YIELD_TABLE,
                source_page=2,
                source_indicator_label="Average gross buy-to-let rental yield for the UK",
                raw_source_value=RENTAL_YIELD_2024_QUARTERLY_VALUES[1],
                source_as_of="2024 Q2",
                source_units="%",
                notes="Quarterly rental-yield value from the UK Finance summary panel.",
            ),
            MetricSourceReference(
                label="UK Finance Buy to let Mortgage Market Update Q3 2024",
                source_document_path=UKF_BTL_Q3_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_RENTAL_YIELD_TEXT_PATH,
                source_table=UKF_BTL_RENTAL_YIELD_TABLE,
                source_page=2,
                source_indicator_label="Average gross buy-to-let rental yield for the UK",
                raw_source_value=RENTAL_YIELD_2024_QUARTERLY_VALUES[2],
                source_as_of="2024 Q3",
                source_units="%",
                notes="Quarterly rental-yield value from the UK Finance summary panel.",
            ),
            MetricSourceReference(
                label="UK Finance Buy to let Mortgage Market Update Q4 2024",
                source_document_path=UKF_BTL_Q4_2024_DOCUMENT_PATH,
                source_text_path=UKF_BTL_RENTAL_YIELD_TEXT_PATH,
                source_table=UKF_BTL_RENTAL_YIELD_TABLE,
                source_page=2,
                source_indicator_label="Average gross buy-to-let rental yield for the UK",
                raw_source_value=RENTAL_YIELD_2024_QUARTERLY_VALUES[3],
                source_as_of="2024 Q4",
                source_units="%",
                notes="Quarterly rental-yield value from the UK Finance summary panel.",
            ),
        ),
    ),
    "core_ooDebtToIncome": MetricSourceMetadata(
        source_document_path=MLAR_LONGRUN_DETAILED_DOCUMENT_PATH,
        source_text_path=MLAR_OO_DTI_TEXT_PATH,
        source_table=f"{MLAR_OO_DTI_TABLE}; denominator from ONS QWND trailing four-quarter gross disposable income",
        source_page=1,
        source_indicator_label="Owner-occupier mortgage debt to income ratio, 2024 annual mean",
        raw_source_value=_annual_mean(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES),
        normalized_source_value=_annual_mean(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES),
        source_units="%",
        comparison_units="%",
        source_as_of="2024 annual mean",
        mapping_status="derived_match",
        band_method="observed_2024_quarterly_range",
        band_notes=(
            "Quarterly reconstruction using MLAR balance totals and BTL balance shares with "
            "ONS QWND trailing four-quarter income: "
            "Q1=80.292464, Q2=79.534081, Q3=78.193823, Q4=77.167109. "
            "Target band uses the observed quarterly range."
        ),
        source_references=(
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2024 Q1",
                source_document_path=MLAR_LONGRUN_DETAILED_DOCUMENT_PATH,
                source_text_path=MLAR_OO_DTI_TEXT_PATH,
                source_table=MLAR_OO_DTI_TABLE,
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES[0],
                source_as_of="2024 Q1",
                source_units="%",
                notes=(
                    "Uses MLAR 1.11 row 33, MLAR 1.33 rows 41, 53, 91, 95 and trailing four-quarter "
                    "ONS QWND gross disposable income."
                ),
            ),
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2024 Q2",
                source_document_path=MLAR_LONGRUN_DETAILED_DOCUMENT_PATH,
                source_text_path=MLAR_OO_DTI_TEXT_PATH,
                source_table=MLAR_OO_DTI_TABLE,
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES[1],
                source_as_of="2024 Q2",
                source_units="%",
                notes=(
                    "Uses MLAR 1.11 row 33, MLAR 1.33 rows 41, 53, 91, 95 and trailing four-quarter "
                    "ONS QWND gross disposable income."
                ),
            ),
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2024 Q3",
                source_document_path=MLAR_LONGRUN_DETAILED_DOCUMENT_PATH,
                source_text_path=MLAR_OO_DTI_TEXT_PATH,
                source_table=MLAR_OO_DTI_TABLE,
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES[2],
                source_as_of="2024 Q3",
                source_units="%",
                notes=(
                    "Uses MLAR 1.11 row 33, MLAR 1.33 rows 41, 53, 91, 95 and trailing four-quarter "
                    "ONS QWND gross disposable income."
                ),
            ),
            MetricSourceReference(
                label="Owner-occupier debt-to-income reconstruction 2024 Q4",
                source_document_path=MLAR_LONGRUN_DETAILED_DOCUMENT_PATH,
                source_text_path=MLAR_OO_DTI_TEXT_PATH,
                source_table=MLAR_OO_DTI_TABLE,
                source_page=1,
                source_indicator_label="Owner-occupier mortgage debt to income ratio",
                raw_source_value=OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES[3],
                source_as_of="2024 Q4",
                source_units="%",
                notes=(
                    "Uses MLAR 1.11 row 33, MLAR 1.33 rows 41, 53, 91, 95 and trailing four-quarter "
                    "ONS QWND gross disposable income."
                ),
            ),
            MetricSourceReference(
                label="ONS UKEA QWND 2023Q2-2024Q4 snapshot",
                source_document_path=ONS_QWND_2024_SNAPSHOT_PATH,
                source_text_path=MLAR_OO_DTI_TEXT_PATH,
                source_indicator_label="HH & NPISH disposable income, gross (QWND)",
                source_as_of="2023 Q2 to 2024 Q4",
                source_units="£m",
                notes="Repo-local quarterly gross disposable income snapshot used to build the trailing four-quarter denominator.",
            ),
        ),
    ),
}

TARGET_CATALOG: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        metric_id="core_mortgageApprovals",
        label="Mortgage Approvals",
        requirement="required",
        units="count/month",
        source_label="Bank of England FPC core indicators, June 2024",
        kind="core_indicator",
        source_metadata=FPC_SOURCE_2024_BY_METRIC_ID["core_mortgageApprovals"],
        target_band=TargetBand(lower=57.0, upper=63.0),
        file_name="coreIndicator-mortgageApprovals.csv",
        scale=0.001,
    ),
    MetricDefinition(
        metric_id="core_housingTransactions",
        label="Housing Transactions",
        requirement="required",
        units="count/month",
        source_label="Bank of England FPC core indicators, June 2024",
        kind="core_indicator",
        source_metadata=FPC_SOURCE_2024_BY_METRIC_ID["core_housingTransactions"],
        target_band=TargetBand(lower=84.2, upper=100.0),
        file_name="coreIndicator-housingTransactions.csv",
        scale=0.001,
    ),
    MetricDefinition(
        metric_id="core_advancesToFTB",
        label="Advances to FTB",
        requirement="required",
        units="count/month",
        source_label="UK Finance Household Finance Review 2024 Q4",
        kind="core_indicator",
        source_metadata=UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToFTB"],
        target_band=TargetBand(lower=23.658, upper=32.008),
        file_name="coreIndicator-advancesToFTB.csv",
        scale=0.001,
    ),
    MetricDefinition(
        metric_id="core_advancesToHM",
        label="Advances to Home Movers",
        requirement="required",
        units="count/month",
        source_label="UK Finance Household Finance Review 2024 Q4",
        kind="core_indicator",
        source_metadata=UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToHM"],
        target_band=TargetBand(lower=20.400, upper=27.600),
        file_name="coreIndicator-advancesToHM.csv",
        scale=0.001,
    ),
    MetricDefinition(
        metric_id="core_advancesToBTL",
        label="Advances to BTL",
        requirement="required",
        units="count/month",
        source_label="UK Finance BTL Mortgage Market Update 2024 (Q1-Q4)",
        kind="core_indicator",
        source_metadata=UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToBTL"],
        target_band=TargetBand(lower=4.396, upper=5.947),
        file_name="coreIndicator-advancesToBTL.csv",
        scale=0.001,
    ),
    MetricDefinition(
        metric_id="core_debtToIncome",
        label="Household Debt to Income",
        requirement="required",
        units="%",
        source_label="Bank of England FPC core indicators, June 2024",
        kind="core_indicator",
        source_metadata=FPC_SOURCE_2024_BY_METRIC_ID["core_debtToIncome"],
        target_band=TargetBand(lower=125.0, upper=145.0),
        file_name="coreIndicator-debtToIncome.csv",
    ),
    MetricDefinition(
        metric_id="core_priceToIncome",
        label="House Price to Household Disposable Income",
        requirement="required",
        units="ratio",
        source_label="Bank of England FPC core indicators, June 2024",
        kind="core_indicator",
        source_metadata=FPC_SOURCE_2024_BY_METRIC_ID["core_priceToIncome"],
        target_band=TargetBand(lower=5.4, upper=9.0),
        file_name="coreIndicator-priceToIncome.csv",
    ),
    MetricDefinition(
        metric_id="core_housePriceGrowth",
        label="House Price Growth",
        requirement="required",
        units="%",
        source_label="Bank of England FPC core indicators, June 2024",
        kind="core_indicator",
        source_metadata=FPC_SOURCE_2024_BY_METRIC_ID["core_housePriceGrowth"],
        target_band=TargetBand(lower=0.0, upper=2.0),
        file_name="coreIndicator-housePriceGrowth.csv",
    ),
    MetricDefinition(
        metric_id="core_hpiMean",
        label="HPI Mean",
        requirement="required",
        units="rebased index",
        source_label="HM Land Registry UK HPI full file December 2024 (UK IndexSA rebased to January 2024)",
        kind="output_series",
        source_metadata=MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiMean"],
        target_band=_plus_minus_tolerance_band(
            source_value=HPI_2024_REBASED_MEAN,
            tolerance=HPI_TARGET_TOLERANCE,
        ),
        file_name="Output-run1.csv",
    ),
    MetricDefinition(
        metric_id="core_hpiStd",
        label="HPI Std",
        requirement="required",
        units="rebased index",
        source_label=(
            "HM Land Registry UK HPI full file December 2024 "
            "(UK IndexSA rebased to January 2005 over 2005-01 to 2024-12)"
        ),
        kind="output_series",
        source_metadata=MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiStd"],
        target_band=_plus_minus_tolerance_band(
            source_value=HPI_FULL_HISTORY_REBASED_STD,
            tolerance=HPI_TARGET_TOLERANCE,
        ),
        file_name="Output-run1.csv",
    ),
    MetricDefinition(
        metric_id="core_hpiCyclePeriod",
        label="HPI Cycle Period",
        requirement="required",
        units="months",
        source_label="HM Land Registry UK HPI full file December 2024 (UK Index history through 2024-12)",
        kind="output_series",
        source_metadata=MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiCyclePeriod"],
        target_band=_plus_minus_tolerance_band(
            source_value=HPI_2024_CYCLE_PERIOD_MONTHS,
            tolerance=HPI_TARGET_TOLERANCE,
        ),
        file_name="Output-run1.csv",
    ),
    MetricDefinition(
        metric_id="core_ooDebtToIncome",
        label="Owner-Occupier Debt to Income",
        requirement="required",
        units="%",
        source_label="MLAR long-run detailed tables plus ONS QWND (full-year 2024 reconstruction)",
        kind="core_indicator",
        source_metadata=MARKET_SOURCE_2024_BY_METRIC_ID["core_ooDebtToIncome"],
        target_band=TargetBand(
            lower=min(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES),
            upper=max(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES),
        ),
        file_name="coreIndicator-ooDebtToIncome.csv",
    ),
    MetricDefinition(
        metric_id="core_rentalYield",
        label="Rental Yield",
        requirement="required",
        units="%",
        source_label="UK Finance Buy to let Mortgage Market Update 2024 (Q1-Q4)",
        kind="core_indicator",
        source_metadata=MARKET_SOURCE_2024_BY_METRIC_ID["core_rentalYield"],
        target_band=TargetBand(
            lower=min(RENTAL_YIELD_2024_QUARTERLY_VALUES),
            upper=max(RENTAL_YIELD_2024_QUARTERLY_VALUES),
        ),
        file_name="coreIndicator-rentalYield.csv",
    ),
    MetricDefinition(
        metric_id="core_interestRateSpread",
        label="Interest Rate Spread",
        requirement="required",
        units="percentage points",
        source_label="Bank of England housing-tools workbook (full-year 2024 monthly spread series)",
        kind="core_indicator",
        source_metadata=MARKET_SOURCE_2024_BY_METRIC_ID["core_interestRateSpread"],
        target_band=TargetBand(
            lower=min(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS),
            upper=max(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS),
        ),
        file_name="coreIndicator-interestRateSpread.csv",
    ),
    MetricDefinition(
        metric_id="income_distribution_jsd",
        label="Income Distribution Realism",
        requirement="required",
        units="JSD",
        source_label="WAS Round 8",
        kind="household_jsd",
        target_band=TargetBand(lower=0.0, upper=0.12),
        legacy_validation_module="income_dist",
    ),
    MetricDefinition(
        metric_id="housing_wealth_distribution_jsd",
        label="Housing Wealth Distribution Realism",
        requirement="required",
        units="JSD",
        source_label="WAS Round 8",
        kind="household_jsd",
        target_band=TargetBand(lower=0.0, upper=0.12),
        legacy_validation_module="housing_wealth_dist",
    ),
    MetricDefinition(
        metric_id="financial_wealth_distribution_jsd",
        label="Financial Wealth Distribution Realism",
        requirement="required",
        units="JSD",
        source_label="WAS Round 8",
        kind="household_jsd",
        target_band=TargetBand(lower=0.0, upper=0.12),
        legacy_validation_module="financial_wealth_dist",
    ),
)

TARGETS_BY_ID = {metric.metric_id: metric for metric in TARGET_CATALOG}

__all__ = [
    "ADVANCES_TARGET_TOLERANCE",
    "FPC_SOURCE_2024_BY_METRIC_ID",
    "HPI_2024_CYCLE_PERIOD_MONTHS",
    "HPI_2024_REBASED_MEAN",
    "HPI_2024_REBASED_STD",
    "HPI_FULL_HISTORY_REBASED_STD",
    "HPI_TARGET_TOLERANCE",
    "INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS",
    "MARKET_SOURCE_2024_BY_METRIC_ID",
    "OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES",
    "RENTAL_YIELD_2024_QUARTERLY_VALUES",
    "SUPPORTED_FPC_METRIC_IDS",
    "TARGET_CATALOG",
    "TARGETS_BY_ID",
    "UKF_SOURCE_2024_BY_METRIC_ID",
    "UNSUPPORTED_FPC_METRIC_IDS",
]
