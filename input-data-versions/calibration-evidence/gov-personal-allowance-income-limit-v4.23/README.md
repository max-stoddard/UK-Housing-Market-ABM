# GOVERNMENT_INCOME_LIMIT_FOR_PERSONAL_ALLOWANCE v4.23 Evidence Bundle
Author: Max Stoddard

## Purpose
- Retains the official GOV.UK 2024/25 source used to source-confirm `GOVERNMENT_INCOME_LIMIT_FOR_PERSONAL_ALLOWANCE` for `v4.23`.
- This fixes the prior 2025/26 source-year wording while preserving the same numeric value because the 2024/25 income limit is also `100000.0`.

## Chosen Method
- Source: GOV.UK Spring Budget 2024 Annex A: rates and allowances.
- Source table: Income Tax allowances, Personal Allowance.
- Source row: Income limit for Personal Allowance.
- Source year: tax year 2024 to 2025.
- Selected config value: `100000.0`.

## Contents
- `spring-budget-2024-annex-a-rates-and-allowances.html`
  - downloaded GOV.UK source page artifact
- `GovPersonalAllowanceIncomeLimitV423SourceValues.csv`
  - machine-readable selected source value and source metadata
- `GovPersonalAllowanceIncomeLimitV423Summary.json`
  - selected config value and method rationale

## Reproduction
```bash
curl -L -o input-data-versions/calibration-evidence/gov-personal-allowance-income-limit-v4.23/spring-budget-2024-annex-a-rates-and-allowances.html https://www.gov.uk/government/publications/spring-budget-2024-overview-of-tax-legislation-and-rates-ootlar/annex-a-rates-and-allowances
```
