"""Locked June 2024 FPC source snapshot for validation metrics.

@author: Max Stoddard
"""

from __future__ import annotations

from scripts.python.validation.model.schema import MetricSourceMetadata

FPC_SOURCE_DOCUMENT_PATH = "private-datasets/cis/fpc-core-indicators-june-2024.pdf"
FPC_SOURCE_TEXT_PATH = "private-datasets/cis/fpc-core-indicators-june-2024.txt"
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
