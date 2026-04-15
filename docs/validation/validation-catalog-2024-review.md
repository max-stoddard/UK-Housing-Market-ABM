# Validation Catalog 2024 Review

Author: Max Stoddard

This note documents how the semantically meaningful values in `scripts/python/validation/model/validation_catalog_2024.py` are reviewed and reproduced from repo-local sources.

The review is backed by:
- `scripts/python/validation/model/catalog_review_2024.py`
- `scripts/python/validation/model/validation_catalog_2024_review.json`

## Provenance Classes

- `direct_source`: the value is read directly from a repo-local frozen source snapshot.
- `derived_from_source`: the value is recomputed from repo-local source snapshots using a fixed formula.
- `methodology_constant`: the value is a validation-framework choice and is not an official source value.

The key distinction is that `sourceValue` is evidence, while `targetBand` may be a methodology-owned scoring choice.

## Repo-Local Source Snapshots

- FPC macro evidence: `input-data-versions/validation-sources/2024/cis/fpc-core-indicators-june-2024.txt`
- UK Finance advances evidence: `input-data-versions/validation-sources/2024/ukf/household-finance-review-2024-q4-validation-evidence.txt`
- UK Finance BTL advances evidence: `input-data-versions/validation-sources/2024/ukf/btl-mortgage-market-update-2024-validation-evidence.txt`
- UK Finance rental-yield evidence: `input-data-versions/validation-sources/2024/ukf/btl-rental-yield-2024-validation-evidence.txt`
- BOE spread workbook: `input-data-versions/validation-sources/2024/boe/housing-tools.xlsx`
- MLAR workbook: `input-data-versions/validation-sources/2024/mlar/mlar-longrun-detailed.xlsx`
- ONS QWND local snapshot: `input-data-versions/validation-sources/2024/ons/qwnd-household-gross-disposable-income-2023q2-2024q4.json`

The ONS snapshot is intentionally minimal. It vendors only the quarterly values needed to reconstruct the 2024 trailing-four-quarter denominator for owner-occupier debt-to-income.

## Metric Review

### FPC-backed Macro Source Values

- `core_mortgageApprovals`, `core_housingTransactions`, `core_debtToIncome`, `core_housePriceGrowth`, `core_priceToIncome`, and the FPC comparison value for `core_interestRateSpread` are reviewed as `direct_source` values from Table A.2 in the June 2024 FPC text snapshot.
- Count metrics are normalized to `thousand count/month` by dividing by `1,000`.
- The checker uses fixed regexes against the frozen text extraction aid because the OCR ordering in the text snapshot is imperfect but stable.

### UK Finance Advances Metrics

- `core_advancesToFTB` and `core_advancesToHM` use annual totals from `Household Finance Review 2024 Q4`, converted to monthly means with:
  `annual_total / 12 / 1,000`
- `core_advancesToBTL` uses the annual sum of the four quarterly house-purchase counts from the Q1-Q4 BTL market updates, then converts with:
  `sum(q1..q4) / 12 / 1,000`
- The acceptance bands for all three advances metrics are `derived_from_source` using the locked methodology rule:
  `official_monthly_mean * (1 ± 0.15)`
- Rounding is fixed to three decimal places using `Decimal(..., ROUND_HALF_UP)`.

### Market-Derived Metrics

- `core_interestRateSpread` is reconstructed from the 2024 monthly BOE housing-tools workbook series, grouped into contiguous quarterly means, then reduced to:
  - annual mean
  - observed quarterly range target band
- `core_rentalYield` is reconstructed from the four quarterly UK Finance summary-panel values, then reduced to:
  - annual mean
  - observed quarterly range target band
- `core_ooDebtToIncome` is reconstructed from:
  - MLAR sheet `1.11` row `33`
  - MLAR sheet `1.33` rows `41`, `53`, `91`, `95`
  - the repo-local ONS QWND snapshot

The owner-occupier debt-to-income quarterly formula is:

```text
btl_unsecuritised = regulated_total * regulated_btl_share / 100
                  + nonregulated_total * nonregulated_btl_share / 100
oo_share = 1 - (btl_unsecuritised / (regulated_total + nonregulated_total))
oo_balance = aggregate_debt_secured_on_dwellings * oo_share
oo_dti = 100 * oo_balance / trailing_4q_qwnd
```

### Household JSD Metrics

- `income_distribution_jsd`
- `housing_wealth_distribution_jsd`
- `financial_wealth_distribution_jsd`

These are not single official source-table values. They are reviewed as:
- source provenance: `WAS Round 8`
- extraction mechanics: the fixed histogram/bin/filter methodology in `scripts/python/validation/model/extractors.py`
- acceptance band: methodology-owned `TargetBand(lower=0.0, upper=0.12)`

The shared `0.12` upper bound is treated as an explicit methodology constant for the permanent 2024 framework. It is justified by the framework design choice to use a common JSD acceptance band across the household realism metrics, which all share the same fixed distribution-comparison semantics.

## Methodology-Owned Bands

The following are explicitly reviewed as methodology constants, not official source values:

- FPC-backed macro acceptance bands:
  - `core_mortgageApprovals`: `[57.0, 63.0]`
  - `core_housingTransactions`: `[84.2, 100.0]`
  - `core_debtToIncome`: `[125.0, 145.0]`
  - `core_priceToIncome`: `[5.4, 9.0]`
  - `core_housePriceGrowth`: `[0.0, 2.0]`
- Household JSD acceptance band:
  - all three household realism metrics use `[0.0, 0.12]`

These bands are reviewed separately from the official evidence values so the audit never implies that the source and the scoring rule are the same thing.

## Review Contract

`python3 -m scripts.python.validation.model.catalog_review_2024` must fail when:
- a reviewed value no longer matches the catalog
- a reviewed value cannot be recomputed from repo-local sources and repo-local methodology notes
- a review ledger entry is missing
- a metric is not covered by the review ledger
- a source-backed metric is not covered by a source review entry

The review is therefore both documentation and an executable reproducibility guard.
