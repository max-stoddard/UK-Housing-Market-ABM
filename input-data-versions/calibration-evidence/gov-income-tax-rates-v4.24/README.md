# DATA_TAX_RATES v4.24 Evidence Bundle
Author: Max Stoddard

## Purpose
- Retains the official GOV.UK 2024/25 source used to source-confirm `DATA_TAX_RATES` for `v4.24`.
- The model stores taxable-income band starts after Personal Allowance and applies Personal Allowance separately in config.
- The 2024/25 England, Wales, and Northern Ireland main-rate rows are numerically unchanged from the prior file, but the source year and provenance now match the 2024 calibration objective.

## Chosen Method
- Source: GOV.UK Income Tax rates and allowances for current and previous tax years.
- Source table: England, Northern Ireland and Wales tax rates and bands.
- Selected rows:
  - `0, 0.20`
  - `37700, 0.40`
  - `125140, 0.45`
- Scotland has separate 2024/25 rates; the current model has a single tax table, so this bundle documents the existing England/Wales/Northern Ireland main-rate simplification rather than changing model structure.

## Contents
- `income-tax-rates-and-allowances-current-and-past.html`
  - downloaded GOV.UK source page artifact
- `GovIncomeTaxRatesV424SourceValues.csv`
  - machine-readable selected source values and source metadata
- `GovIncomeTaxRatesV424Summary.json`
  - selected table rows and method rationale

## Reproduction
```bash
curl -L -o input-data-versions/calibration-evidence/gov-income-tax-rates-v4.24/income-tax-rates-and-allowances-current-and-past.html https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past
```
