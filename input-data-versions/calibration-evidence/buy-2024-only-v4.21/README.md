# BUY 2024-Only v4.21 Evidence
Author: Max Stoddard

This bundle records derived metadata for the forced `v4.21` recalibration of
`BUY_SCALE`, `BUY_EXPONENT`, `BUY_MU`, and `BUY_SIGMA`.

No raw private PSD or Price Paid Data rows are retained here. The source CSVs
remain in `private-datasets/`.

## Calibration

The selected candidate uses PSD 2024 and PPD 2024 only:

```bash
python3 -m scripts.python.calibration.psd.psd_buy_budget_calibration_v2 \
  --quarterly-csv private-datasets/psd/2024/psd-quarterly-2024.csv \
  --ppd-csv-2024 private-datasets/ppd/pp-2024.csv \
  --target-year-psd 2024 \
  --ppd-status-mode a_only \
  --year-policy 2024_only \
  --guardrail-mode fail \
  --hard-p95-cap 15 \
  --exponent-max 1.0 \
  --median-target-curve 25000:6.5,50000:6.0,100000:5.4,150000:5.0,200000:4.8 \
  --tail-family pareto \
  --pareto-alpha-grid 1.8 \
  --objective-weight-grid-profile minimal \
  --fit-degradation-max 0.10 \
  --within-bin-points 11 \
  --quantile-grid-size 4000 \
  --ppd-mean-anchor-weight 4.0 \
  --fixed-exponent 1.0 \
  --income-open-upper-k 200 \
  --property-open-upper-k 2000 \
  --workers 1 \
  --output-dir tmp/buy-2024-only-v4.21/calibration
```

Result:

- `BUY_SCALE = 4.3957479837`
- `BUY_EXPONENT = 1`
- `BUY_MU = 0`
- `BUY_SIGMA = 0.2`
- `source_year_psd = 2024`
- `source_year_ppd = 2024`
- `ppd_2025_loaded = 0`
- `guardrails_passed = true`

## Evidence Files

- `PsdBuyBudgetCalibrationV421.csv`
- `PsdBuyBudgetCalibrationV421Summary.json`

## Validation

Canonical validation command:

```bash
bash input-data-versions/validate.sh v4.21 --output-dir tmp/buy-2024-only-v4.21/validation/v4.21 --workers 20
```

The version is promoted by explicit request even if the downstream validation
comparison is not model-improving.

Tracked summary:

- `input-data-versions/validation/v4.21.json`
- `overallCompositeLoss = 0.573916720919496`
- Current `v4.20` comparison loss: `0.6045043981851204`
- Delta versus `v4.20`: `-0.03058767726562439`
- HPI Mean metric loss: `0.4671213798746696 -> 0.29732111653870075`
- HPI Std metric loss: `1.4987466529102156 -> 0.2561351239522241`
- HPI Cycle Period metric loss: `0.5373901292495852 -> 0.794483541872788`
- Combined HPI metric loss: `2.5032581620344705 -> 1.347939782363713`
- Required status changes versus `v4.20`: Household Debt to Income `fail->pass`,
  HPI Mean `fail->warn`, HPI Std `fail->warn`
