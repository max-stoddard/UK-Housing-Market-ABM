# 2011 Validation Catalog Review

Author: Max Stoddard

This note documents how the v0-only 2011 reference overlay is reproduced from
repo-local source artifacts and rescored from the tracked 8-seed `v0`
validation outputs.

The main tracked validation publication now ships as an 8-seed dashboard-facing
summary for the 2024 profile. The 2011 view is separate: it is the
`v0-2011` reference overlay used to audit the 2011 source definitions and the
displayed 2011 comparison set.

Reviewed files:
- `scripts/python/validation/model/validation_catalog_2011.py`
- `input-data-versions/validation-sources/2011/**`
- `input-data-versions/validation-overlays/v0-2011.json`
- `tmp/validation/v0/seed-*/**`
- `tmp/validation/v0/reference-2011/**`

## Source families
- `boe/`: repo-local 2011 series extracted from the tracked Bank of England
  housing-tools workbook for mortgage approvals, housing transactions, household
  debt to income, house price growth, house price to disposable income, and
  interest-rate spread. These are the audited source-faithful 2011 macro
  metrics in the overlay.
- `hmlr/`: repo-local UK-only HPI series through `2011-12` used to reproduce HPI
  mean and HPI cycle period, plus the documented cross-year exception for
  `core_hpiStd` which reuses the 2024 official std benchmark
- `mlar/` + `ons/`: repo-local component snapshots used to reconstruct the 2011
  owner-occupier debt-to-income quarterly values
- `cml/`: public release evidence for 2011 annual first-time buyer, home-mover,
  and buy-to-let house-purchase totals. These remain weak proxy metrics because
  the bundle quotes CML totals through contemporaneous public reports rather
  than a clean primary CML source file.
- `bm/`: public release evidence for the 2011 UK average gross buy-to-let rental
  yield. This remains a weak proxy because the tracked archive does not expose a
  clean 2011 UK quarterly series comparable with the 2024 UK Finance data.

## Locked methodology
- `core_mortgageApprovals`, `core_housingTransactions`, `core_debtToIncome`,
  `core_priceToIncome`, `core_housePriceGrowth`, and `core_interestRateSpread`
  are the audited 2011 macro definitions. Each one uses the 2011 source series
  annual mean and the observed 2011 monthly or quarterly range as the target
  band.
- `core_advancesToFTB`, `core_advancesToHM`, and `core_advancesToBTL` convert the
  2011 annual totals to monthly thousand-count means and apply a fixed `+/-5%`
  tolerance band. These remain explicitly labeled secondary-source proxies:
  they are annual purchase-loan totals, not a primary CML release, and the BTL
  figure is the house-purchase count rather than total BTL lending.
- `core_rentalYield` uses the 2011 annual BM Solutions UK yield with a fixed
  `+/-5%` tolerance because there is no clean tracked UK quarterly archive
  equivalent to the 2024 UK Finance series. This is the intended dashboard
  proxy, not a quarterly apples-to-apples equivalent.
- `core_hpiMean` and `core_hpiCyclePeriod` reuse the existing HPI helper
  methodology on the source series through `2011-12`.
- `core_hpiStd` is a deliberate exception. It reuses the same official
  `2005-01 .. 2024-12` UK `IndexSA` std scalar and `+/-5%` target band as the
  2024 framework instead of a 2011-anchored std target.
- The fixed `+/-5%` width is inherited from the 2024 validation-method enhancement:
  the observed-range positive-valued 2024 target bands average about `+/-4.27%`
  of the corresponding source value, so `+/-5%` is the rounded conservative
  fixed-band rule.
- `core_ooDebtToIncome` reuses the 2024 reconstruction formula with 2011 MLAR
  balances and a trailing four-quarter QWND denominator built from `2010Q2` to
  `2011Q4`.
- `income_distribution_jsd`, `housing_wealth_distribution_jsd`, and
  `financial_wealth_distribution_jsd` keep the existing JSD acceptance band
  `[0.0, 0.12]` but switch the validation dataset from WAS Round 8 to WAS Wave 3.
- Loss-family metadata is inherited from the 2024 catalog. The 2011 overlay
  therefore uses log-ratio scoring for positive-level metrics, additive scoring
  for signed/zero-crossing metrics such as house price growth and interest-rate
  spread, and bounded low-is-better scoring for the JSD metrics.

## Review summary
- The 2011 source bundle is intentionally minimal. It stores only the rows and
  values needed to rebuild the v0-only 2011 targets.
- The source publication date may be later than 2011 where a later frozen public
  release contains the required 2011 history more cleanly than an original 2011
  publication.
- All tracked validation summaries, including `v0`, remain on the 2024 profile
  and are published through the 8-seed summary flow.
- The 2011 target year is reserved for the separate `v0` reference overlay
  published to `input-data-versions/validation-overlays/v0-2011.json` and
  mirrored under `<output-dir>/reference-2011/**` when `v0` validation is run.
  The dashboard-visible 2011 view is therefore a reference overlay, not a
  replacement for the main 2024 validation summary.
- The v0-family 2011 overlays are schema-4 summaries and can be rescored from
  cached JSON with:
  `python3 -m scripts.python.validation.model.rescore_validation_summaries --versions all --include-overlays --write`.
- Residual non-equivalences remain for the weak CML/BM proxy metrics and for
  `core_hpiStd`, which is intentionally cross-year-normalized to the 2024
  official std benchmark rather than anchored to 2011.
