# Remaining Recalibration Data Sources For `v4.10`
Author: Max Stoddard

This maintained note tracks which `v4.10` parameters in `input-data-versions/v4.10/config.properties` still lack post-2020 recalibration or source-confirmation work. Use the live `v4.10` calibration ledgers in `input-data-versions/dashboard-input-version-history.json` and `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md` as the canonical source for promoted recalibrations, then keep this note aligned with whichever parameters still remain.

Maintenance note:
- If a recalibration or validation task recalibrates, newly confirms, or otherwise removes a parameter from the remaining set, update this file in the same change.
- The same change must also update `input-data-versions/dashboard-input-version-history.json`, `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md`, and the `v4.10` progress counts in `input-data-versions/AGENTS.md`.

Total remaining parameters: `34`

Audit note:
- This note has been updated for `v4.10` after the promotion of `BANK_ICR_HARD_MIN` and a consistency correction for the already-promoted `v4.1` hard-LTV alignment parameters in the version-history and calibration-changelog ledgers.
- `ESSENTIAL_CONSUMPTION_FRACTION` and `MAXIMUM_CONSUMPTION_FRACTION` are now removed from the remaining set after the `v4.12` LCFS 2023/24 weighted consumption-fraction recalibration.
- The grouping below was cross-checked against the current `input-data-versions/v4.10/config.properties`, `input-data-versions/dashboard-input-version-history.json`, and `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md`.
- One corrected point from that review: `BTL_PROBABILITY_MULTIPLIER` is source-backed by a WAS wave 3 note and is therefore grouped under `WAS wave 3 household data`.

## Explicit Source-Backed Groups

### CML - BTL data for 2014, statistics obtained from FSSR-MRD (David Seaward)
2 parameters
- `DOWNPAYMENT_BTL_MEAN`
- `DOWNPAYMENT_BTL_EPSILON`

### Zoopla data (raw collated listings) from 2003 to 2015 and Katie Low's HPI data. BLOCKED.
1 parameter
- `DATA_INITIAL_SALE_MARKUP_DIST`

### Zoopla B Raw Listings (collation) data from 2003 to 2015. BLOCKED.
2 parameters
- `P_SALE_PRICE_REDUCE`
- `P_RENT_PRICE_REDUCE`

### Zoopla A Raw Listings (daily) data from 2003 to 2015. BLOCKED.
6 parameters

`DAYS_UNDER_OFFER` is a design decision, but its note explicitly cites this source and is therefore grouped here.

- `REDUCTION_MU`
- `REDUCTION_SIGMA`
- `BIDUP`
- `DAYS_UNDER_OFFER`
- `RENT_REDUCTION_MU`
- `RENT_REDUCTION_SIGMA`

### ARLA annual report (ARLA Members Survey of the Private Rented Sector) for 2013 Q4
2 parameters
- `TENANCY_LENGTH_MIN`
- `TENANCY_LENGTH_MAX`

### Zoopla data (raw collated listings) from 2003 to 2015 and RPI data. BLOCKED.
1 parameter
- `DATA_INITIAL_RENT_MARKUP_DIST`

### Literature: Philippe Bracke (Bank of England) paper matching Zoopla and Land Registry data plus ARLA's annual report for 2013
1 parameter
- `RENT_GROSS_YIELD`

### PSD data for 2011 (99 percentile). BLOCKED.
3 parameters
- `BANK_LTI_HARD_MAX_FTB`
- `BANK_LTI_HARD_MAX_HM`
- `BANK_AFFORDABILITY_HARD_MAX`

### WAS wave 3 household data
1 parameter
- `BTL_PROBABILITY_MULTIPLIER`

## Parameters With No Explicit External Source Note

### Default or non-binding central-bank policy note
7 parameters
- `CENTRAL_BANK_LTI_SOFT_MAX_FTB`
- `CENTRAL_BANK_LTI_SOFT_MAX_HM`
- `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB`
- `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM`
- `CENTRAL_BANK_LTI_MONTHS_TO_CHECK`
- `CENTRAL_BANK_AFFORDABILITY_HARD_MAX`
- `CENTRAL_BANK_ICR_HARD_MIN`

### Design decision note with no explicit external source
4 parameters
- `HPA_YEARS_TO_CHECK`
- `BTL_INCOME_DRIVEN_CAP_GAIN_COEFF`
- `BTL_CAPITAL_DRIVEN_CAP_GAIN_COEFF`
- `BTL_MIX_DRIVEN_CAP_GAIN_COEFF`

### No explicit source note in output-calibrated block
4 parameters
- `PSYCHOLOGICAL_COST_OF_RENTING`
- `SENSITIVITY_RENT_OR_PURCHASE`
- `BTL_CHOICE_INTENSITY`
- `MARKET_AVERAGE_PRICE_DECAY`
