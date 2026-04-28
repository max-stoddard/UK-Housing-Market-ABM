# GOVERNMENT_MONTHLY_INCOME_SUPPORT v4.13 Evidence Bundle
Author: Max Stoddard

## Purpose
- This bundle retains the downloaded GOV.UK 2024/25 benefit-rates page used to recalibrate `GOVERNMENT_MONTHLY_INCOME_SUPPORT` for `v4.13`.
- The model stores this value monthly and annualizes it internally by multiplying by 12.
- `v4.13` therefore converts the weekly source rate with `52 / 12`, rather than treating one month as four weeks.

## Chosen Method
- Source section: `Income Support`
- Source row: `Both 18 or over`
- Source column: `Rates 2024/25`
- Weekly source rate: `142.25`
- Chosen monthly scalar: `142.25 * 52 / 12 = 616.4166666667`

## Improvement Over v4.12
- `v4.12` used a 2025/26 source rate and the four-week-month calculation `144.65 * 4 = 578.6`.
- `v4.13` uses the 2024/25 source year and preserves the annual value implied by 52 weekly payments: `142.25 * 52 = 7397.0`.
- This is more accurate for the model because the Java code annualizes the monthly input as `GOVERNMENT_MONTHLY_INCOME_SUPPORT * 12`.

## Contents
- `benefit-and-pension-rates-2024-to-2025.html`
  - downloaded GOV.UK source page artifact
- `GovIncomeSupport2024SourceValues.csv`
  - machine-readable extracted source value and calculation
- `GovIncomeSupport2024Summary.json`
  - selected config value, method rationale, and v4.12 comparison

## Reproduction
```bash
python3 -m scripts.python.calibration.official.gov_income_support_2024 \
  --output-dir input-data-versions/calibration-evidence/gov-income-support-v4.13
```
