# BoE Bank Parameter `v4.3`-`v4.6` Calibration Design

**Author:** Max Stoddard
**Date:** 2026-04-15
**Status:** Implemented
**Scope:** `scripts/python/helpers/boe/`, `scripts/python/experiments/boe/`, `scripts/python/calibration/boe/`, `input-data-versions/`

## Summary

This workflow recalibrates four scalar bank parameters using BoE and ONS source series, then promotes them across a cumulative version chain:

- `v4.3`: `CENTRAL_BANK_INITIAL_BASE_RATE`
- `v4.4`: `BANK_INITIAL_RATE`
- `v4.5`: `BANK_D_INTEREST_D_DEMAND`
- `v4.6`: `BANK_INITIAL_CREDIT_SUPPLY`

The release path is intentionally cumulative from `v4.2`, and the static startup parameters use full-year `2024` constant proxies rather than single-month snapshots.

## Locked Inputs

- Bank Rate history:
  - `private-datasets/boe/BoE - Bank Rate history and data.csv`
- Mortgage spread workbook:
  - `private-datasets/boe/housing-tools.xlsx`
  - sheet: `8. Spreads new mortgage lending`
  - series: owner-occupier `2-year` `75%` `LTV` spread
- Gross lending:
  - official VTUZ CSV export saved as
    `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv`
- Households denominator:
  - ONS `Families and households in the UK: 2024`
  - locked value: `28,600,000`

## Locked Formulas

### `CENTRAL_BANK_INITIAL_BASE_RATE`

- Build the Bank Rate monthly series from the change-history CSV by daily-weighting each calendar month in `2024`.
- Choose the full-year mean of the `2024` monthly series.

Chosen value:

- `0.051083333333333335`

### `BANK_INITIAL_RATE`

- For each `2024` month:
  - `mortgage_rate_proxy_t = bank_rate_monthly_t + spread_t / 100`
- Choose the full-year mean of the monthly mortgage-rate proxy.

Chosen value:

- `0.05649531436698348`

### `BANK_INITIAL_CREDIT_SUPPLY`

- Convert each VTUZ monthly observation to pounds per household:
  - `C_t = VTUZ_t * 1_000_000 / 28_600_000`
- Choose the full-year mean of the `2024` monthly per-household series.

Chosen value:

- `704.9388111888112`

### `BANK_D_INTEREST_D_DEMAND`

- Use spread-only monthly changes rather than total mortgage-rate changes.
- Build the full overlapping monthly panel ending `2024-12`.
- Convert spreads to fractions:
  - `S_t = spread_t / 100`
- Convert credit to pounds per household:
  - `C_t = VTUZ_t * 1_000_000 / 28_600_000`
- Fit the through-origin slope:
  - `Delta S_t = beta * Delta C_t`

Chosen value:

- `5.471987263431394e-07`

Rejected diagnostic:

- `2024`-only through-origin fit:
  - `-5.91912917550825e-06`

This rejection is intentional. The `2024` window alone yields a negative coefficient, so the defensible production estimate uses the longer pre-`2025` overlap.

## Evidence Bundle

Canonical evidence folder:

- `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/`

Key evidence files:

- `BoEBankRateHistoryInput.csv`
- `BoEBankRate2024Monthly.csv`
- `BoEHousingToolsSpreadMonthly.csv`
- `BoEHousingToolsSpread2024Monthly.csv`
- `BoEMortgageRateProxy2024Monthly.csv`
- `BoEVTUZGrossLendingInput.csv`
- `BoEVTUZCreditSupplyPerHousehold2024Monthly.csv`
- `BoEVTUZSpreadAlignedDeltas1995To2024.csv`
- `BoEVTUZSpreadAlignedDeltas2024.csv`
- `OnsHouseholds2024.csv`
- `BoeBankParameterMethodSearch.csv`
- `BoeBankParameterCalibrationSummary.csv`
- `BoeBankParameterCalibrationSummary.json`

## Versioning Notes

- `v4.3` is intentionally a partial startup-rate recalibration step. It updates the base rate but leaves the bank initial rate unchanged, so the startup spread is not yet economically coherent.
- `v4.4` restores startup-rate coherence by promoting the new `BANK_INITIAL_RATE`.
- `v4.5` promotes the new demand-response coefficient.
- `v4.6` promotes the new initial credit-supply level.

## Reproduction Commands

Fetch and save VTUZ:

```bash
curl -L -o input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv \
  'https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/1995&Dateto=31/Dec/2024&SeriesCodes=LPMVTUZ&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N'
```

For repo-local reruns, reuse the checked-in `BoEVTUZGrossLendingInput.csv` evidence file and skip the network fetch.

Run method search:

```bash
python3 -m scripts.python.experiments.boe.boe_bank_parameter_method_search \
  --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' \
  --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx \
  --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv \
  --ons-households 28600000 \
  --target-year 2024 \
  --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6
```

Run locked production calibration:

```bash
python3 -m scripts.python.calibration.boe.boe_bank_parameter_calibration \
  --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' \
  --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx \
  --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv \
  --ons-households 28600000 \
  --target-year 2024 \
  --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6
```
