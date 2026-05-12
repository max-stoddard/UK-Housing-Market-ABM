# House Prices v4.20 Evidence
Author: Max Stoddard

This bundle records derived metadata for the `v4.20` recalibration of
`HOUSE_PRICES_SCALE` and `HOUSE_PRICES_SHAPE`.

No raw private Price Paid Data rows are retained here. The source CSVs remain in
`private-datasets/ppd/`.

## Reproduction Check

The existing `v4.19` values were reproduced exactly from the 2025 PPD file:

```bash
python3 -m scripts.python.calibration.ppd.house_price_lognormal_fit \
  private-datasets/ppd/pp-2025.csv \
  --method focused_repro_default \
  --target-year 2025
```

Result:

- `HOUSE_PRICES_SCALE = 12.5485368828`
- `HOUSE_PRICES_SHAPE = 0.6805162153`

## v4.20 Calibration

The promoted `v4.20` values use the same focused status-A population-moment
lognormal fit on the annual 2024 PPD file:

```bash
python3 -m scripts.python.calibration.ppd.house_price_lognormal_fit \
  private-datasets/ppd/pp-2024.csv \
  --method focused_repro_default \
  --target-year 2024
```

Result:

- `HOUSE_PRICES_SCALE = 12.5351947066`
- `HOUSE_PRICES_SHAPE = 0.7743402838`

The `--target-year` argument is metadata for the current production method; the
annual `pp-2024.csv` source file already constrains the sample to 2024
transactions.

## Validation

Canonical validation command:

```bash
bash input-data-versions/validate.sh v4.20 --output-dir tmp/validation/v4.20 --workers 20
```

Tracked summary:

- `input-data-versions/validation/v4.20.json`
- `overallCompositeLoss = 0.6045043981851204`
- Current `v4.19` comparison loss: `0.5833322259841027`
- Delta versus `v4.19`: `+0.021172172201017636`
- Metric status changes versus `v4.19`: none
