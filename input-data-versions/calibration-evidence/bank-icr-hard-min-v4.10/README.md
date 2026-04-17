# BANK_ICR_HARD_MIN v4.10 Evidence Bundle
Author: Max Stoddard

## Purpose
- This bundle retains the public-source extract used to recalibrate `BANK_ICR_HARD_MIN` for `v4.10`.
- The live model parameter is a hard buy-to-let underwriting floor rather than an observed market-average outcome.
- No public lender-weighted 2024 threshold distribution was available for this task, so `v4.10` uses the approved public-proxy route instead of claiming a market-wide estimate.

## Chosen Method
- Default method: `literal_standard_floor_125`
- Retained Paragon 2024 decision thresholds: `1.25, 1.25, 1.30, 1.30, 1.40, 1.40, 1.45, 1.45`
- Context-only UK Finance observed 2024 ICRs: `1.91, 1.96, 1.95, 2.01`
- Chosen scalar: minimum retained decision threshold = `1.25`

## Rejected Alternatives
- `stress_mapped_floor = 1.22`
  - rejected because it adds a rate-translation layer based on a representative stress-rate diagnostic rather than the published ICR ratio itself
- `cross_segment_mean = 1.35`
  - rejected because equal-weighting visible segments invents a market mix and would over-tighten the representative bank

## Excluded Source
- `private-datasets/misc/CMI-BTL-ProductGuide.pdf`
  - retained only as an excluded-row note because the on-disk file appears to be a 30 May 2022 CHL Mortgages guide rather than a 2024 CMI artifact

## Contents
- `BankIcrHardMinPublicSources.csv`
  - retained machine-readable source extract used as the default script input
- `BankIcrHardMinMethodSearch.csv`
  - emitted by `scripts.python.experiments.btl.bank_icr_hard_min_method_search`
- `BankIcrHardMinCalibrationSourceValues.csv`
  - emitted by `scripts.python.calibration.btl.bank_icr_hard_min_calibration`
- `BankIcrHardMinCalibrationSummary.json`
  - emitted by `scripts.python.calibration.btl.bank_icr_hard_min_calibration`

## Reproduction
```bash
python3 -m scripts.python.experiments.btl.bank_icr_hard_min_method_search \
  --output-dir input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10

python3 -m scripts.python.calibration.btl.bank_icr_hard_min_calibration \
  --output-dir input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10
```

