# UK Housing Stock Calibration Evidence (`v4.7`)
Author: Max Stoddard

This bundle retains the official 2024 artifacts used to calibrate `UK_HOUSEHOLDS` and `UK_DWELLINGS` for `input-data-versions/v4.7`.

## Source Artifacts
- `ons-families-and-households-uk-2024.xlsx`
  - Source URL: `https://www.ons.gov.uk/file?uri=%2Fpeoplepopulationandcommunity%2Fbirthsdeathsandmarriages%2Ffamilies%2Fdatasets%2Ffamiliesandhouseholdsfamiliesandhouseholds%2Fcurrent%2Ffamiliesandhouseholdsuk2024.xlsx`
  - Publication date: `2025-07-23`
  - Extraction: workbook sheet `5`, row `All households`, column `2024 Estimate`
  - Precision note: published in `thousands`, so `28609` becomes `28,609,000`
- `england-live-table-100-2024.ods`
  - Source URL: `https://assets.publishing.service.gov.uk/media/682deb00b33f68eaba95391b/LiveTable100.ods`
  - Publication date: `2025-05-22`
  - Extraction: table `2024`, row `England`, column `Total`
  - Precision note: the downloadable ODS publishes `25,617,413`; the rounded public headline `25.62 million` is not used as the calibration value
- `wales-dwelling-stock-estimates-2024.csv`
  - Source URL: `https://stats.gov.wales/en-GB/6476cc20-ddeb-46a5-be64-10a23c8a159f`
  - Most recent update from metadata: `2026-01-15`
  - Extraction: CSV row with `Local authority=Wales`, `Period=31/03/2024`, `Tenure=All tenures (Number)`
  - Precision note: StatsWales metadata states that the figures are rounded to the nearest `100`
- `wales-dwelling-stock-estimates-2024-metadata.csv`
  - Source URL: `https://stats.gov.wales/en-GB/6476cc20-ddeb-46a5-be64-10a23c8a159f/download/metadata`
  - Purpose: retained official metadata supporting the Wales publication/update date and rounding note
- `scotland-households-and-dwellings-2024.xlsx`
  - Source URL: `https://www.nrscotland.gov.uk/media/nvcaoksr/house-est-24-data.xlsx`
  - Publication date: `2025-06-26`
  - Extraction: workbook sheet `Table2`, row `Scotland`, column `2024`
  - Precision note: workbook notes say figures are rounded to the nearest whole number
- `northern-ireland-housing-stock-2008-2025.xlsx`
  - Source URL: `https://www.finance-ni.gov.uk/sites/default/files/2025-06/Housing%20Stock%20Tables%202008%20-%202025.xlsx`
  - Publication date: `2025-06-04`
  - Extraction: workbook sheet `Table 1.17`, row `Northern Ireland`, column `Total Housing Stock`

## Selected Calibration
- `UK_HOUSEHOLDS = 28,609,000`
  - Chosen from the ONS workbook's published `28609` thousand households
- `UK_DWELLINGS = 30,676,974`
  - Chosen as the source-native sum of:
    - England `25,617,413`
    - Wales `1,482,600`
    - Scotland `2,740,973`
    - Northern Ireland `835,988`

## Rejected Comparators
- `UK_HOUSEHOLDS = 28,600,000`
  - Rejected because it is a rounded headline comparator, not the workbook table value
- `UK_DWELLINGS = 30,679,588`
  - Rejected because it mixes rounded England `25,620,000` and Scotland `2,741,000` headline values with the more granular Wales and Northern Ireland downloadable values
  - Difference from the selected source-native total: `2,614`

## Generated Evidence
- `UkHousingStockTotals2024SourceValues.csv`
  - Source observations, selected totals, and rejected comparators
- `UkHousingStockTotals2024CalibrationSummary.json`
  - Machine-readable summary written by `scripts/python/calibration/official/uk_housing_stock_totals_2024.py`
- `uk-housing-stock-v4.7-sources.bib`
  - Reviewed BibTeX references for the official source artifacts used by this evidence bundle
