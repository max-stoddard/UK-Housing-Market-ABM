# 2011 Validation Sources

Author: Max Stoddard

This folder contains the tracked source artifacts required to review and reproduce
the v0-only 2011 reference overlay without relying on ignored `private-datasets/`
paths, except for WAS Wave 3 which remains the private household-validation
dataset.

The dashboard-facing 2011 view is a separate reference overlay, not the main
8-seed 2024 validation publication. These source notes document the audited 2011
metric definitions and the remaining proxy/non-equivalence cases for that view.

Contents:
- `boe/`: minimal 2011 Bank of England housing-tools series snapshot plus evidence
  note for mortgage approvals, housing transactions, household debt to income,
  house price growth, house price to disposable income, and interest-rate spread
- `hmlr/`: minimal United Kingdom HPI series snapshot through `2011-12` plus the
  derived-value audit note for HPI mean, HPI std, and HPI cycle period
- `mlar/`: minimal 2011 MLAR component snapshot plus owner-occupier
  debt-to-income reconstruction note
- `ons/`: minimal repo-local QWND snapshot for `2010Q2` to `2011Q4` used in the
  owner-occupier debt-to-income denominator
- `cml/`: evidence note for 2011 first-time buyer, home-mover, and buy-to-let
  annual mortgage totals sourced from public reports quoting CML statistics
- `bm/`: evidence note for the 2011 UK average gross buy-to-let rental yield
  sourced from BM Solutions reporting
- `frs/`: Family Resources Survey 2010/11 report and evidence note for
  owner-occupied and private-rented household shares
- `ons-rpi/`: ONS Price Index of Private Rents historical-series workbook and
  Rental Price Index evidence note

These files are tracked because they are the authoritative 2011 source snapshots
referenced by:
- `scripts/python/validation/model/validation_catalog_2011.py`
- `docs/validation/validation-catalog-2011-review.md`
- `input-data-versions/validation-overlays/v0-2011.json`
- `<output-dir>/reference-2011/**` when the live `v0` validation flow is run

WAS Wave 3 is intentionally not duplicated here. The v0-only household realism
metrics continue to read the private `W3` dataset via the existing WAS helper
code, while this folder covers every non-WAS public source used by the 2011
profile.

Metric coverage:
- Source-faithful macro metrics: `core_mortgageApprovals`,
  `core_housingTransactions`, `core_debtToIncome`, `core_priceToIncome`,
  `core_housePriceGrowth`, and `core_interestRateSpread`.
- Deliberate cross-year-normalized exception: `core_hpiStd`, which reuses the
  official `2005-01 .. 2024-12` HPI std benchmark from the 2024 framework.
- Reconstructed historical metric: `core_ooDebtToIncome`.
- Source-backed tenure/Rental Price Index metrics: `household_owning_share`,
  `household_renting_share`, and `rpi_mean`.
- Weak proxy metrics with explicit non-equivalences: `core_advancesToFTB`,
  `core_advancesToHM`, `core_advancesToBTL`, and `core_rentalYield`.

The `ons-rpi/` source uses RPI to mean Rental Price Index, not Retail Prices Index.
