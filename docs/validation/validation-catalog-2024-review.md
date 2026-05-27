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
- BOE housing-tools workbook: `input-data-versions/validation-sources/2024/boe/housing-tools.xlsx`
- MLAR workbook: `input-data-versions/validation-sources/2024/mlar/mlar-longrun-detailed.xlsx`
- ONS QWND local snapshot: `input-data-versions/validation-sources/2024/ons/qwnd-household-gross-disposable-income-2023q2-2024q4.json`

The ONS snapshot is intentionally minimal. It vendors only the quarterly values needed to reconstruct the 2024 trailing-four-quarter denominator for owner-occupier debt-to-income.

## Metric Review

### FPC Point-in-Time Macro Context

- The June 2024 FPC Table A.2 values remain reviewed as frozen point-in-time context from the repo-local text snapshot.
- `core_mortgageApprovals`, `core_housingTransactions`, `core_debtToIncome`, `core_housePriceGrowth`, and `core_priceToIncome` no longer use those FPC values as active 2024 validation source metadata or target bands.
- The active validation source for those five metrics is now the full-year 2024 Bank of England housing-tools workbook.
- Count metrics are normalized to `thousand count/month` by dividing by `1,000`.
- The checker uses fixed regexes against the frozen text extraction aid because the OCR ordering in the text snapshot is imperfect but stable.

### UK Finance Advances Metrics

- `core_advancesToFTB` and `core_advancesToHM` use annual totals from `Household Finance Review 2024 Q4`, converted to monthly means with:
  `annual_total / 12 / 1,000`
- `core_advancesToBTL` uses the annual sum of the four quarterly house-purchase counts from the Q1-Q4 BTL market updates, then converts with:
  `sum(q1..q4) / 12 / 1,000`
- The acceptance bands for all three advances metrics are `derived_from_source` using the locked methodology rule:
  `official_monthly_mean * (1 ± 0.05)`
- Rounding is fixed to three decimal places using `Decimal(..., ROUND_HALF_UP)`.
- This fixed `±5%` rule is a validation-method enhancement: for positive-valued validation metrics whose target bands
  are derived directly from observed 2024 variation, the average target-band half-width is approximately `±4.27%` of
  the corresponding source value, so `±5%` is a rounded conservative rule that aligns fixed bands more closely with
  the empirical observed-range widths while remaining simple to audit.

### Market-Derived Metrics

- `core_mortgageApprovals` is reconstructed from the Jan-Dec 2024 monthly BOE housing-tools workbook series, then reduced to:
  - annual mean in thousand count/month
  - observed monthly range target band
- `core_housingTransactions` is reconstructed from the Jan-Dec 2024 monthly BOE housing-tools workbook series, then reduced to:
  - annual mean in thousand count/month
  - observed monthly range target band
- `core_debtToIncome` is reconstructed from the Q1-Q4 2024 quarterly BOE housing-tools workbook series, then reduced to:
  - annual mean
  - observed quarterly range target band
- `core_housePriceGrowth` is reconstructed from the Jan-Dec 2024 monthly BOE housing-tools workbook series, then reduced to:
  - annual mean
  - observed monthly range target band
- `core_priceToIncome` is reconstructed from the Q1-Q4 2024 quarterly BOE housing-tools workbook series, then reduced to:
  - annual mean
  - observed quarterly range target band
- `core_hpiMean` is reconstructed from the archived HMLR full-file UK `IndexSA` series for `2024-01 .. 2024-12`, rebased to `2024-01 = 1.0`, then reduced to:
  - annual mean
  - `±5%` target band around that annual mean
- `core_hpiStd` is reconstructed from the archived HMLR full-file UK `IndexSA` series for `2005-01 .. 2024-12`, rebased to `2005-01 = 1.0`, then reduced to:
  - long-run population std
  - `±5%` target band around that long-run std
- `core_hpiCyclePeriod` is reconstructed from the archived HMLR full-file UK `Index` history through `2024-12`, then reduced to:
  - dominant cycle period
  - `±5%` target band around that derived cycle period
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

## Metric Weighting

The tracked validation contract now uses metric-only weighting:

- every scored validation metric publishes `metricWeight = 1`
- `overallCompositeLoss` is the weighted mean of scored `metricLoss` values
- the tracked JSON and dashboard contract do not publish family/category summaries

This means the composite is driven directly by the full set of scored metrics rather than by intermediate category aggregates.

## Validation Status and Loss Taxonomy

Schema version `4` separates pass/fail status from metric loss:

- `pass`: `seedMean` is inside the target band and `insideRate >= 0.75`
- `warn`: band-width-normalized outside distance is at most `0.50` and `insideRate >= 0.50`
- `fail`: otherwise

Target bands therefore define acceptance status. Metric loss is a separate ranking signal used to compare misses across
metrics without letting narrow target bands dominate the composite by construction.

Every catalog metric has an explicit `loss_family`; the framework does not infer the family from units:

- `positive_level`: strictly positive counts, flows, levels, and ratios use log-ratio distance to the nearest target-band
  edge. This makes a 3x overshoot comparable with a one-third undershoot. If a model value is non-positive, the distance
  component uses the conservative floor penalty `log(100)`.
- `signed_additive`: signed or zero-crossing metrics use robust additive normalization with
  `max(abs(sourceValue), abs(lower), abs(upper), (upper - lower) / 2, 1e-9)`.
- `bounded_low_is_better`: JSD realism metrics preserve the target-band status rule while adding an in-band level
  component, so lower divergence is rewarded even when both runs pass.

The published metric audit fields are:

- `lossFamily` and `lossTransform`
- `lossScale` / `lossScaleBasis` where a bounded score uses the band upper bound
- `additiveScale` / `additiveScaleBasis` where signed additive or fallback additive spread is used
- `normalizedDistance`, `normalizedIqr`, `distanceComponent`, `spreadComponent`, `levelComponent`, and
  `insideRateComponent`

The composite remains:

```text
overallCompositeLoss = weighted_mean(required metricLoss values, metricWeight = 1)
```

Cached tracked summaries can be upgraded without rerunning Java/Maven:

```bash
python3 -m scripts.python.validation.model.rescore_validation_summaries --versions all --include-overlays --write
```

The rescoring command preserves cached `seedMean`, `p25`, `p75`, `insideRate`, target-band, and source metadata, then
recomputes `metricLoss`, audit fields, and `overallCompositeLoss` under the current schema.

ES-MDA calibration now exposes a separate validation objective. `family_aware_metric_loss` is the default and assimilates
zero ideal per-metric schema-4 losses. `target_normalized_additive` preserves the old-compatible additive target-normalized
observation/member vectors and covariance for reproducibility. Both modes still publish schema-4 validation summaries for
member diagnostics.

## Methodology-Owned Bands

The following are explicitly reviewed as methodology constants, not official source values:

- Fixed tolerance acceptance bands:
  - UK Finance advances and HPI-derived scalar metrics use fixed `±5%` bands around the source value.
- Household JSD acceptance band:
  - all three household realism metrics use `[0.0, 0.12]`

The BOE housing-tools bands for `core_mortgageApprovals`, `core_housingTransactions`, `core_debtToIncome`,
`core_housePriceGrowth`, and `core_priceToIncome` are source-derived observed 2024 ranges, not methodology-owned
FPC bands.

## Review Contract

`python3 -m scripts.python.validation.model.catalog_review_2024` must fail when:
- a reviewed value no longer matches the catalog
- a reviewed value cannot be recomputed from repo-local sources and repo-local methodology notes
- a review ledger entry is missing
- a metric is not covered by the review ledger
- a source-backed metric is not covered by a source review entry

The review is therefore both documentation and an executable reproducibility guard.
