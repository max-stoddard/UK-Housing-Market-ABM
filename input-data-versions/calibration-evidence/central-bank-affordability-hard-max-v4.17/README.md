# Central-Bank Affordability Hard-Max Evidence for v4.17
Author: Max Stoddard

This bundle retains the official Bank of England June 2022 news release used to set:

- `CENTRAL_BANK_AFFORDABILITY_HARD_MAX = 0.9999`

The Bank of England Financial Policy Committee confirmed that it would withdraw the mortgage-market affordability-test Recommendation, effective `2022-08-01`. The release also states that the LTI flow limit would not be withdrawn and that lenders remain subject to FCA Mortgage Conduct of Business responsible-lending affordability assessments.

The model still retains the representative-bank affordability cap:

- `BANK_AFFORDABILITY_HARD_MAX = 0.4`

Because `housing.Bank#getHardMaxAffordability` applies the minimum of the representative-bank and central-bank affordability caps, the effective model cap remains `0.4`. The `0.9999` value is therefore a high non-binding sentinel for the absence of a separate central-bank hard affordability cap, not an observed household affordability threshold.

Source page:
`https://www.bankofengland.co.uk/news/2022/june/financial-policy-committee-confirms-withdrawal-of-mortgage-market-affordability-test`

Downloaded HTML artifact:
`input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/bank-of-england-fpc-withdrawal-affordability-test-2022.html`

HTML SHA256:
`6775a69a8a737c46f4003a6d1f2d88597dcb979d984eb9edb821f35bae665a1b`

## Selected Values

- Central-bank affordability hard maximum: `0.9999`
- Effective date of policy withdrawal: `2022-08-01`
- Representative-bank affordability hard maximum retained: `0.4`
- Effective model affordability hard maximum after applying the minimum rule: `0.4`

## Reproduction

```bash
curl -L https://www.bankofengland.co.uk/news/2022/june/financial-policy-committee-confirms-withdrawal-of-mortgage-market-affordability-test \
  -o input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/bank-of-england-fpc-withdrawal-affordability-test-2022.html

sha256sum \
  input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/bank-of-england-fpc-withdrawal-affordability-test-2022.html
```
