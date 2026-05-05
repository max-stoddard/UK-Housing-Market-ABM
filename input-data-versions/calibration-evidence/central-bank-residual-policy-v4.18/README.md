# Central-Bank Residual Policy Evidence for v4.18
Author: Max Stoddard

This bundle retains source artifacts used to resolve the two remaining current-baseline central-bank policy notes:

- `CENTRAL_BANK_LTI_MONTHS_TO_CHECK = 12`
- `CENTRAL_BANK_ICR_HARD_MIN = 0.0`

## Sources

The LTI window uses two linked sources. The existing v4.16 Bank of England November 2024 FPC Record confirms the active LTI flow-limit policy: no more than `15%` of total new residential mortgages should be at LTI ratios at or greater than `4.5`. The 2017 PRA policy statement confirms the flow limit is applied on a four-quarter rolling basis. The model runs monthly, so four quarters maps to `12` monthly model steps.

The central-bank ICR value uses the Bank of England Quarterly Bulletin article published on 25 September 2024. It states that the FPC has powers over residential mortgage LTV and DTI limits, including ICRs for buy-to-let lending, but has not yet used its powers of Direction over LTV or DTI/ICR limits for owner-occupier or buy-to-let mortgages. Therefore `CENTRAL_BANK_ICR_HARD_MIN = 0.0` is used as a non-binding central-bank floor. The lender-side floor remains `BANK_ICR_HARD_MIN = 1.25` from the v4.10 public-proxy lender evidence bundle.

## Retained Artifacts

- `bank-of-england-fpc-contribution-financial-stability-2024.html`
  - URL: `https://www.bankofengland.co.uk/quarterly-bulletin/2024/2024/the-contribution-of-the-fpc-to-uk-financial-stability`
  - SHA256: `dd59c978facc034d2bada2991024d5f0aae0576e153dcdd55b2c2825f641fec0`
- `bank-of-england-pra-lti-four-quarter-rolling-2017.html`
  - URL: `https://www.bankofengland.co.uk/prudential-regulation/publication/2016/amendments-to-the-pras-rules-on-loan-to-income-ratios-in-mortgage-lending-november-2016`
  - SHA256: `8399cf28d61c749db1a1b6a434d64cb8ce9885c945abdb1f872249e0cec68339`

Referenced existing artifacts:

- `input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/`
- `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/`

## Reproduction

```bash
curl -L https://www.bankofengland.co.uk/quarterly-bulletin/2024/2024/the-contribution-of-the-fpc-to-uk-financial-stability \
  -o input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-fpc-contribution-financial-stability-2024.html

curl -L https://www.bankofengland.co.uk/prudential-regulation/publication/2016/amendments-to-the-pras-rules-on-loan-to-income-ratios-in-mortgage-lending-november-2016 \
  -o input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-pra-lti-four-quarter-rolling-2017.html

sha256sum \
  input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-fpc-contribution-financial-stability-2024.html \
  input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-pra-lti-four-quarter-rolling-2017.html
```
