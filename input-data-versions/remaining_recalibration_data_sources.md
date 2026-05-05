# Remaining Recalibration Data Sources For Current `v4.18` Baseline
Author: Max Stoddard

This maintained note tracks which scoped parameters in the current `input-data-versions/v4.18/config.properties` baseline still lack post-2020 recalibration or source-confirmation work. Scope follows the recalibration-status definition in `input-data-versions/AGENTS.md`: Central Bank policy, input-calibrated parameters, and output-calibrated parameters are in scope; user-set and legacy parameters are out of scope. Use the live calibration ledgers in `input-data-versions/dashboard-input-version-history.json` and `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md` as the canonical source for promoted recalibrations, then keep this note aligned with whichever parameters still remain.

Maintenance note:
- If a recalibration or validation task recalibrates, newly confirms, or otherwise removes a parameter from the remaining set, update this file in the same change.
- The same change must also update `input-data-versions/dashboard-input-version-history.json`, `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md`, and the recalibration-status progress counts in `input-data-versions/AGENTS.md`.

Total remaining parameters: `20`

Audit note:
- This note has been updated for the current `v4.18` baseline after the promotion of `BANK_ICR_HARD_MIN`, a consistency correction for the already-promoted `v4.1` hard-LTV alignment parameters in the version-history and calibration-changelog ledgers, the `v4.14o` BTL probability multiplier output calibration, the `v4.14oo` four-parameter ESMDA output calibration, the `v4.15` EHS tenancy-length support-bound calibration, the `v4.16` Bank of England central-bank LTI flow-limit source confirmation, the `v4.17` Bank of England central-bank affordability-test withdrawal source confirmation, and the `v4.18` residual central-bank policy source confirmation for the LTI rolling window and ICR hard floor.
- `ESSENTIAL_CONSUMPTION_FRACTION` and `MAXIMUM_CONSUMPTION_FRACTION` are now removed from the remaining set after the `v4.12` LCFS 2023/24 weighted consumption-fraction recalibration.
- `DATA_INCOME_GIVEN_AGE` remains outside the remaining set after the `v4.14` FRS 2023/24 gross-non-rent income-age recalibration; this does not change the remaining count because the parameter was already post-2020-backed before `v4.14`.
- `DOWNPAYMENT_BTL_MEAN` and `DOWNPAYMENT_BTL_EPSILON` are now outside this remaining set because the current config classifies them under `LEGACY PARAMETERS`.
- `DOWNPAYMENT_BTL_SCALE`, `DOWNPAYMENT_BTL_SHAPE`, and `BTL_ALTERNATIVE_RETURN` are now inside this remaining set because the current scoped config keeps them as TODO placeholders for default-off BTL modes.
- The grouping below was cross-checked against the current `input-data-versions/v4.18/config.properties`, `input-data-versions/dashboard-input-version-history.json`, and `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md`.
- `BTL_PROBABILITY_MULTIPLIER` is now removed from the remaining set after the refreshed `v4.14o` output calibration against the weighted WAS R8 positive-gross-rental-income prevalence target. The expanded search brackets the target and selects the closest interior candidate, with a small residual target gap rather than an exact hit.
- `PSYCHOLOGICAL_COST_OF_RENTING`, `SENSITIVITY_RENT_OR_PURCHASE`, `BTL_CHOICE_INTENSITY`, and `MARKET_AVERAGE_PRICE_DECAY` are now removed from the remaining set after the `v4.14oo` four-parameter ESMDA output calibration against the 2024 validation profile. The canonical 8-seed tracked validation improves `overallCompositeLoss` from `0.658907` in `v4.14o` to `0.607765` in `v4.14oo`, while several market-level metrics remain outside target bands.
- `HPA_YEARS_TO_CHECK` is now removed from the remaining set as a status correction: the current config already records it as a design decision with robustness analysis before and after full model calibration, and the unchanged value `2` remains the documented calibrated setting.
- `TENANCY_LENGTH_MIN` and `TENANCY_LENGTH_MAX` are now removed from the remaining set after the `v4.15` EHS 2023-24 Annex Table 2.10 tenancy-length support-bound calibration. v4.15 is intentionally cloned from `v4.14`, excluding the later `v4.14o` and `v4.14oo` output-calibration branches.
- `CENTRAL_BANK_LTI_SOFT_MAX_FTB`, `CENTRAL_BANK_LTI_SOFT_MAX_HM`, `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB`, and `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM` are now removed from the remaining set after the `v4.16` Bank of England November 2024 FPC Record source confirmation. The official policy is aggregate across new residential mortgages, while the model stores separate FTB and HM parameters; v4.16 sets both borrower groups to the same source-backed values and leaves the lender-size de minimis threshold out of scope because the model has no lender-size threshold parameter.
- `CENTRAL_BANK_AFFORDABILITY_HARD_MAX` is now removed from the remaining set after the `v4.17` Bank of England June 2022 FPC news release source confirmation. The FPC withdrew its mortgage-market affordability-test Recommendation effective `2022-08-01`; v4.17 sets the central-bank cap to the non-binding sentinel `0.9999` while retaining the representative-bank affordability cap at `0.4`.
- `CENTRAL_BANK_LTI_MONTHS_TO_CHECK` and `CENTRAL_BANK_ICR_HARD_MIN` are now removed from the remaining set after the `v4.18` residual central-bank policy source confirmation. The 12-month LTI window maps the PRA four-quarter rolling implementation to the model's monthly time step, and `CENTRAL_BANK_ICR_HARD_MIN = 0.0` encodes no separate FPC hard ICR Direction while leaving the representative-bank `BANK_ICR_HARD_MIN = 1.25` floor binding.

## Explicit Source-Backed Groups

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

### Zoopla data (raw collated listings) from 2003 to 2015 and RPI data. BLOCKED.
1 parameter
- `DATA_INITIAL_RENT_MARKUP_DIST`

### Literature: Philippe Bracke (Bank of England) paper matching Zoopla and Land Registry data plus ARLA's annual report for 2013. BLOCKED.
1 parameter
- `RENT_GROSS_YIELD`

### PSD data for 2011 (99 percentile). BLOCKED.
3 parameters
- `BANK_LTI_HARD_MAX_FTB`
- `BANK_LTI_HARD_MAX_HM`
- `BANK_AFFORDABILITY_HARD_MAX`

## Parameters With No Explicit External Source Note

### TODO placeholder with no explicit external source
3 parameters
- `DOWNPAYMENT_BTL_SCALE`
- `DOWNPAYMENT_BTL_SHAPE`
- `BTL_ALTERNATIVE_RETURN`

### Design decision note with no explicit external source
3 parameters
- `BTL_INCOME_DRIVEN_CAP_GAIN_COEFF`
- `BTL_CAPITAL_DRIVEN_CAP_GAIN_COEFF`
- `BTL_MIX_DRIVEN_CAP_GAIN_COEFF`
