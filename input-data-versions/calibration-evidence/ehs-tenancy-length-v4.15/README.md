# EHS Tenancy-Length Calibration Evidence for v4.15
Author: Max Stoddard

This bundle retains the public English Housing Survey source artifact and the derived source extract used to recalibrate:

- `TENANCY_LENGTH_MIN = 6`
- `TENANCY_LENGTH_MAX = 18`

The source is English Housing Survey 2023-24 rented sectors, Chapter 2 annex table `AT2_10`, "Annex Table 2.10: Length of initial tenancy agreement, by tenancy type, two-years analysis, 2022-24".

Source page:
`https://www.gov.uk/government/statistics/english-housing-survey-2023-to-2024-rented-sectors`

Downloaded artifact:
`input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15/EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods`

Artifact URL:
`https://assets.publishing.service.gov.uk/media/6874f2a3730a1bf28e2f9321/EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods`

SHA256:
`7513d4e71f0bc44119185940de8f1bf03602b52284775c7268b3ddfc848ec228`

## Extracted Values

Population: private renters with assured shorthold tenancies who have lived at the current address for less than 3 years.

Exact EHS percentages:

- 6-month initial agreements: `23.6%` (`24%` rounded)
- 12-month initial agreements: `61.3%` (`61%` rounded)
- 18-month initial agreements: `3.8%` (`4%` rounded)
- Other initial agreement length: `11.3%` (`11%` rounded)

The Java model currently draws tenancy length from a uniform discrete distribution between `TENANCY_LENGTH_MIN` and `TENANCY_LENGTH_MAX`. v4.15 therefore promotes the explicit EHS month-category support bounds, `6` and `18`, while retaining the full empirical discrete distribution for audit rather than introducing a new multinomial tenancy-length model.

## Reproduction

```bash
python3 -m scripts.python.calibration.official.ehs_tenancy_length_2024 \
  --output-dir input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15
```

Outputs:

- `EhsTenancyLengthSourceValues.csv`
- `EhsTenancyLengthSummary.json`
