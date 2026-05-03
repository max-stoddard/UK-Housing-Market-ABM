# Central-Bank LTI Soft-Max Evidence for v4.16
Author: Max Stoddard

This bundle retains the official Bank of England November 2024 Financial Policy Committee Record artifacts used to align:

- `CENTRAL_BANK_LTI_SOFT_MAX_FTB = 4.5`
- `CENTRAL_BANK_LTI_SOFT_MAX_HM = 4.5`
- `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB = 0.15`
- `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM = 0.15`

The FPC Record states that the loan-to-income flow limit should prevent mortgage lenders from extending more than `15%` of their total number of new residential mortgages at LTI ratios at or greater than `4.5`.

Source page:
`https://www.bankofengland.co.uk/financial-policy-summary-and-record/2024/november-2024`

Downloaded HTML artifact:
`input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/bank-of-england-fpc-record-november-2024.html`

HTML SHA256:
`c61d8a32b44ecde57ea862facdbf8dadb18c33e65d9785d72a00140a78c90157`

PDF artifact URL:
`https://www.bankofengland.co.uk/-/media/boe/files/financial-policy-summary-and-record/2024/fpc-record-november-2024.pdf`

Downloaded PDF artifact:
`input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/fpc-record-november-2024.pdf`

PDF SHA256:
`0e567364b9f671c1d1857e5b982217412295c74a0762a112807a468acf6799de`

## Selected Values

- Soft LTI threshold: `4.5`
- Flow-limit fraction: `0.15`
- Borrower segmentation: the official FPC policy is aggregate across new residential mortgages; the model exposes separate FTB and HM parameters, so v4.16 sets both borrower groups to the same value.
- De minimis threshold: the FPC recommended raising the lender-size threshold from GBP 100 million to GBP 150 million annual residential mortgage lending. The housing model has no lender-size threshold parameter, so this threshold is retained for audit but not encoded in `config.properties`.

## Reproduction

```bash
curl -L https://www.bankofengland.co.uk/financial-policy-summary-and-record/2024/november-2024 \
  -o input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/bank-of-england-fpc-record-november-2024.html

curl -L https://www.bankofengland.co.uk/-/media/boe/files/financial-policy-summary-and-record/2024/fpc-record-november-2024.pdf \
  -o input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/fpc-record-november-2024.pdf

sha256sum \
  input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/bank-of-england-fpc-record-november-2024.html \
  input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/fpc-record-november-2024.pdf
```
