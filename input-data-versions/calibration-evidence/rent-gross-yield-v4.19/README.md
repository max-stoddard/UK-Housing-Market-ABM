# RENT_GROSS_YIELD v4.19 Evidence Bundle
Author: Max Stoddard

## Purpose
- This bundle retains the downloaded December 2024 ONS PIPR and HM Land Registry UK HPI artifacts used to recalibrate `RENT_GROSS_YIELD` for `v4.19`.
- The model stores `RENT_GROSS_YIELD` as a fraction, not a percentage.
- The selected value is `0.0581338503`.

## Chosen Method
- Formula: `12 * mean(PIPR Great Britain monthly rent) / mean(HMLR UK HPI AveragePrice)`.
- Rent numerator: ONS PIPR `Table 1`, `Area name = Great Britain`, `Rental price`, January-November 2024.
- Price denominator: HM Land Registry UK HPI full file, `RegionName = United Kingdom`, `AveragePrice`, January-December 2024.
- Calculation: `12 * 1271.1818181818 / 262397.5833333333 = 0.05813385026036566`.
- Config value: `0.0581338503`.

## Source-Choice Notes
- The requested December 2024 PIPR workbook marks UK and Northern Ireland rent-price levels as `[x]`, so a literal UK monthly-rent numerator is unavailable in that artifact.
- Great Britain is the selected numerator because it is the highest available ONS PIPR aggregate with numeric rent-price levels in the requested workbook.
- `UK-HPI-full-file-2024-12.csv` is selected over `Average-prices-2024-12.csv` because the full file is the richer auditable source shape and matches the repository's validation-source convention.
- No additional transaction-volume weighting is applied to the monthly HPI denominator because `RENT_GROSS_YIELD` needs a price-level denominator rather than a transaction-flow-weighted denominator.

## Contents
- `priceindexofprivaterentsukmonthlypricestatistics.xlsx`
  - downloaded ONS PIPR December 2024 monthly price statistics workbook
- `UK-HPI-full-file-2024-12.csv`
  - downloaded HM Land Registry December 2024 UK HPI full file
- `Average-prices-2024-12.csv`
  - downloaded HM Land Registry December 2024 average-prices comparator
- `RentGrossYield2024SourceValues.csv`
  - machine-readable extracted rent, house-price, unavailable-rent, and selected-value rows
- `RentGrossYield2024Summary.json`
  - selected config value, method rationale, source artifact checksums, and rejected comparisons

## Reproduction
```bash
python3 -m scripts.python.calibration.official.rent_gross_yield_2024 \
  --pipr-xlsx input-data-versions/calibration-evidence/rent-gross-yield-v4.19/priceindexofprivaterentsukmonthlypricestatistics.xlsx \
  --hpi-full-csv input-data-versions/calibration-evidence/rent-gross-yield-v4.19/UK-HPI-full-file-2024-12.csv \
  --average-prices-csv input-data-versions/calibration-evidence/rent-gross-yield-v4.19/Average-prices-2024-12.csv \
  --output-dir input-data-versions/calibration-evidence/rent-gross-yield-v4.19
```
