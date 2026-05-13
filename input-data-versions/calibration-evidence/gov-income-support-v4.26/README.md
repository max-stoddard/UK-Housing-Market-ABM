# GOVERNMENT_MONTHLY_INCOME_SUPPORT v4.26 Evidence Bundle
Author: Max Stoddard

## Purpose
- Retains a v4.26-local copy of the official GOV.UK 2024/25 benefit-rates page used to confirm `GOVERNMENT_MONTHLY_INCOME_SUPPORT`.
- The selected value matches the earlier v4.13 correction, but this bundle makes the v4.26 version chain self-contained and avoids carrying the stale live runtime value.

## Chosen Method
- Source: GOV.UK Benefit and pension rates 2024 to 2025.
- Source section: Income Support.
- Source row: Both 18 or over.
- Source column: Rates 2024/25.
- Weekly source rate: `142.25`.
- Selected monthly scalar: `142.25 * 52 / 12 = 616.4166666667`.

## Contents
- `benefit-and-pension-rates-2024-to-2025.html`
  - downloaded GOV.UK source page artifact
- `GovIncomeSupportV426SourceValues.csv`
  - machine-readable selected source value and calculation
- `GovIncomeSupportV426Summary.json`
  - selected config value and method rationale

## Reproduction
```bash
curl -L -o input-data-versions/calibration-evidence/gov-income-support-v4.26/benefit-and-pension-rates-2024-to-2025.html https://www.gov.uk/government/publications/benefit-and-pension-rates-2024-to-2025/benefit-and-pension-rates-2024-to-2025
```
