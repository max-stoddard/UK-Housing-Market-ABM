# BANK_AGE_LIMIT v4.9 Evidence Bundle
Author: Max Stoddard

## Purpose
- This bundle retains the public-source extract used to recalibrate `BANK_AGE_LIMIT` for `v4.9`.
- The live model parameter is overloaded:
  - for non-BTL it acts as a repay-by age cap
  - for BTL it acts as an approval-age cap
- No direct 2024 public homeowner `age mortgage term ends` table was available for this task, so `v4.9` uses the approved public-proxy route instead of a blocked member-only maturity-age distribution.

## Chosen Method
- Default method: `conservative_mainstream_mode`
- Explicit origination caps: `70, 75, 75`
- Explicit non-BTL repay-by caps: `80, 75, 75, 75, 80`
- Chosen scalar: mode of all explicit public thresholds = `75`

## Rejected Alternatives
- `repay_cap_mean_round = 77`
  - rejected because it maps only the repay-side of a parameter that also gates origination
- `hybrid_midpoint_round = 75`
  - rejected because it adds an extra averaging layer without improving the selected conservative benchmark

## Contents
- `BankAgeLimitPublicSources.csv`
  - retained machine-readable source extract used as the default script input
- `BankAgeLimitMethodSearch.csv`
  - emitted by `scripts.python.experiments.boe.boe_bank_age_limit_method_search`
- `BankAgeLimitCalibrationSourceValues.csv`
  - emitted by `scripts.python.calibration.boe.boe_bank_age_limit_calibration`
- `BankAgeLimitCalibrationSummary.json`
  - emitted by `scripts.python.calibration.boe.boe_bank_age_limit_calibration`

## Reproduction
```bash
python3 -m scripts.python.experiments.boe.boe_bank_age_limit_method_search \
  --output-dir input-data-versions/calibration-evidence/bank-age-limit-v4.9

python3 -m scripts.python.calibration.boe.boe_bank_age_limit_calibration \
  --output-dir input-data-versions/calibration-evidence/bank-age-limit-v4.9
```
