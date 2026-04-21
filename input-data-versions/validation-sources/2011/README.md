# 2011 Validation Sources

Author: Max Stoddard

This folder contains the tracked source artifacts required to review and reproduce
the v0-only 2011 validation profile without relying on ignored `private-datasets/`
paths, except for WAS Wave 3 which remains the private household-validation
dataset.

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

These files are tracked because they are the authoritative 2011 source snapshots
referenced by:
- `scripts/python/validation/model/validation_catalog_2011.py`
- `docs/validation/validation-catalog-2011-review.md`
- `input-data-versions/validation/v0.json`

WAS Wave 3 is intentionally not duplicated here. The v0-only household realism
metrics continue to read the private `W3` dataset via the existing WAS helper
code, while this folder covers every non-WAS public source used by the 2011
profile.
