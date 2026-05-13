# DATA_NATIONAL_INSURANCE_RATES v4.25 Evidence Bundle
Author: Max Stoddard

## Purpose
- Retains the official GOV.UK 2024/25 source used to recalibrate `DATA_NATIONAL_INSURANCE_RATES` for `v4.25`.
- This replaces the stale 12% employee main rate and legacy 52-times-weekly threshold convention with official 2024/25 annual Class 1 employee Category A thresholds and rates.

## Chosen Method
- Source: GOV.UK Rates and thresholds for employers 2024 to 2025.
- Source section: Class 1 National Insurance thresholds and employee primary contribution rates.
- Selected rows:
  - `12570, 0.08`
  - `50270, 0.02`
- The model applies this table to annual gross income, so v4.25 uses the official annual Primary Threshold and Upper Earnings Limit rather than reconstructing annual thresholds from weekly values.

## Contents
- `rates-and-thresholds-for-employers-2024-to-2025.html`
  - downloaded GOV.UK source page artifact
- `GovNationalInsuranceRatesV425SourceValues.csv`
  - machine-readable selected source values and source metadata
- `GovNationalInsuranceRatesV425Summary.json`
  - selected table rows and method rationale

## Reproduction
```bash
curl -L -o input-data-versions/calibration-evidence/gov-ni-class1-employee-v4.25/rates-and-thresholds-for-employers-2024-to-2025.html https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2024-to-2025
```
