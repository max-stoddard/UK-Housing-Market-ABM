# JFR Method Breakdown
Author: Max Stoddard

This report is derived from existing JFR `jdk.ExecutionSample` recordings.
Percentages are sample-share estimates, not exact stopwatch timings.

Note: these recordings are historical v4.1 smoke profiles. They remain useful hotspot evidence, but they are not the current canonical v0 benchmark baselines.

## Core Minimal 10K

- Profile id: `core-minimal-10k`
- JFR source: `tmp/model-speed/benchmarks-smoke/v4.1/core-minimal-10k/20260307T021546Z/median-jfr/profile.jfr`
- Whole-run `ExecutionSample` count: `1363`
- `modelStep()`-anchored sample count: `1355`
- JSON companion: `core-minimal-10k-methods.json`
- CSV companion: `core-minimal-10k-methods.csv`

### Whole-Run Hot Methods

| Rank | Method | Samples | Percent |
| ---: | --- | ---: | ---: |
| 1 | `housing.Household.getAnnualFinanceCosts` | 120 | 8.80% |
| 2 | `java.util.TreeMap.getFirstEntry` | 108 | 7.92% |
| 3 | `java.util.TreeMap.successor` | 71 | 5.21% |
| 4 | `housing.HousingMarketRecord$PQComparator.XCompare` | 68 | 4.99% |
| 5 | `org.apache.commons.math3.util.FastMath.log` | 63 | 4.62% |
| 6 | `housing.HouseholdBehaviour.updateDesiredPurchasePrice` | 58 | 4.26% |
| 7 | `java.util.TreeMap.getFloorEntry` | 58 | 4.26% |
| 8 | `java.util.TreeMap.getEntryUsingComparator` | 54 | 3.96% |
| 9 | `housing.Household.step` | 53 | 3.89% |
| 10 | `housing.HousingMarket.matchBidsWithOffers` | 49 | 3.60% |
| 11 | `java.util.TreeMap.put` | 49 | 3.60% |
| 12 | `collectors.HouseholdStats.record` | 40 | 2.93% |
| 13 | `housing.HousingMarket.clearMatches` | 37 | 2.71% |
| 14 | `housing.Household.getNProperties` | 32 | 2.35% |
| 15 | `org.apache.commons.math3.random.BitsStreamGenerator.nextGaussian` | 29 | 2.13% |
| 16 | `java.util.Arrays.copyOf` | 25 | 1.83% |
| 17 | `org.apache.commons.math3.util.FastMath.pow` | 25 | 1.83% |
| 18 | `collectors.HousingMarketStats.preClearingRecord` | 22 | 1.61% |
| 19 | `housing.Household.getMonthlyGrossRentalIncome` | 22 | 1.61% |
| 20 | `java.util.TimSort.countRunAndMakeAscending` | 22 | 1.61% |
| 21 | `Other` | 358 | 26.27% |

### `modelStep()`-Only Hot Methods

| Rank | Method | Samples | Percent |
| ---: | --- | ---: | ---: |
| 1 | `housing.Household.getAnnualFinanceCosts` | 120 | 8.86% |
| 2 | `java.util.TreeMap.getFirstEntry` | 108 | 7.97% |
| 3 | `java.util.TreeMap.successor` | 71 | 5.24% |
| 4 | `housing.HousingMarketRecord$PQComparator.XCompare` | 68 | 5.02% |
| 5 | `org.apache.commons.math3.util.FastMath.log` | 63 | 4.65% |
| 6 | `housing.HouseholdBehaviour.updateDesiredPurchasePrice` | 58 | 4.28% |
| 7 | `java.util.TreeMap.getFloorEntry` | 58 | 4.28% |
| 8 | `java.util.TreeMap.getEntryUsingComparator` | 54 | 3.99% |
| 9 | `housing.Household.step` | 53 | 3.91% |
| 10 | `housing.HousingMarket.matchBidsWithOffers` | 49 | 3.62% |
| 11 | `java.util.TreeMap.put` | 49 | 3.62% |
| 12 | `collectors.HouseholdStats.record` | 40 | 2.95% |
| 13 | `housing.HousingMarket.clearMatches` | 37 | 2.73% |
| 14 | `housing.Household.getNProperties` | 32 | 2.36% |
| 15 | `org.apache.commons.math3.random.BitsStreamGenerator.nextGaussian` | 29 | 2.14% |
| 16 | `java.util.Arrays.copyOf` | 25 | 1.85% |
| 17 | `org.apache.commons.math3.util.FastMath.pow` | 25 | 1.85% |
| 18 | `collectors.HousingMarketStats.preClearingRecord` | 22 | 1.62% |
| 19 | `housing.Household.getMonthlyGrossRentalIncome` | 22 | 1.62% |
| 20 | `java.util.TimSort.countRunAndMakeAscending` | 22 | 1.62% |
| 21 | `Other` | 350 | 25.83% |

### Direct `modelStep()` Child Breakdown

| modelStep line | Phase | Samples | Percent |
| ---: | --- | ---: | ---: |
| 185 | `demographics.step()` | 42 | 3.10% |
| 187 | `construction.step()` | 1 | 0.07% |
| 189 | `household loop` | 701 | 51.73% |
| 191 | `creditSupply.preClearingResetCounters()` | 0 | 0.00% |
| 193 | `housingMarketStats.preClearingRecord()` | 14 | 1.03% |
| 195 | `houseSaleMarket.clearMarket()` | 53 | 3.91% |
| 197 | `housingMarketStats.postClearingRecord()` | 2 | 0.15% |
| 199 | `rentalMarketStats.preClearingRecord()` | 10 | 0.74% |
| 201 | `houseRentalMarket.clearMarket()` | 333 | 24.58% |
| 203 | `rentalMarketStats.postClearingRecord()` | 2 | 0.15% |
| 205 | `householdStats.record()` | 172 | 12.69% |
| 207 | `creditSupply.postClearingRecord()` | 22 | 1.62% |
| 209 | `bank.step()` | 3 | 0.22% |
| 211 | `centralBank.step()` | 0 | 0.00% |

### Interpretation

- Dominant `modelStep()` phase: `household loop` at 51.7% of modelStep samples.
- Second-largest `modelStep()` phase: `houseRentalMarket.clearMarket()` at 24.6% of modelStep samples.
- Dominant sampled hot method inside this view: `housing.Household.getAnnualFinanceCosts` at 8.9% of modelStep samples.

## E2E Default 10K

- Profile id: `e2e-default-10k`
- JFR source: `tmp/model-speed/benchmarks-smoke/v4.1/e2e-default-10k/20260307T020626Z/median-jfr/profile.jfr`
- Whole-run `ExecutionSample` count: `1705`
- `modelStep()`-anchored sample count: `1693`
- JSON companion: `e2e-default-10k-methods.json`
- CSV companion: `e2e-default-10k-methods.csv`

### Whole-Run Hot Methods

| Rank | Method | Samples | Percent |
| ---: | --- | ---: | ---: |
| 1 | `housing.Household.getAnnualFinanceCosts` | 246 | 14.43% |
| 2 | `housing.HousingMarket.matchBidsWithOffers` | 117 | 6.86% |
| 3 | `collectors.HouseholdStats.record` | 91 | 5.34% |
| 4 | `housing.Household.step` | 88 | 5.16% |
| 5 | `java.util.TreeMap.successor` | 87 | 5.10% |
| 6 | `java.util.TreeMap.getFloorEntry` | 82 | 4.81% |
| 7 | `housing.HouseholdBehaviour.updateDesiredPurchasePrice` | 72 | 4.22% |
| 8 | `java.util.TreeMap.getFirstEntry` | 71 | 4.16% |
| 9 | `org.apache.commons.math3.util.FastMath.log` | 64 | 3.75% |
| 10 | `java.util.TreeMap.getEntryUsingComparator` | 49 | 2.87% |
| 11 | `housing.HousingMarket.clearMatches` | 45 | 2.64% |
| 12 | `org.apache.commons.math3.random.BitsStreamGenerator.nextGaussian` | 31 | 1.82% |
| 13 | `java.util.TreeMap.put` | 26 | 1.52% |
| 14 | `housing.Household.getNProperties` | 25 | 1.47% |
| 15 | `java.io.BufferedWriter.write` | 25 | 1.47% |
| 16 | `java.util.TimSort.countRunAndMakeAscending` | 25 | 1.47% |
| 17 | `org.apache.commons.math3.util.FastMath.pow` | 25 | 1.47% |
| 18 | `java.util.TimSort.binarySort` | 22 | 1.29% |
| 19 | `java.util.TreeMap.compare` | 22 | 1.29% |
| 20 | `housing.Demographics.implementDeaths` | 21 | 1.23% |
| 21 | `Other` | 471 | 27.62% |

### `modelStep()`-Only Hot Methods

| Rank | Method | Samples | Percent |
| ---: | --- | ---: | ---: |
| 1 | `housing.Household.getAnnualFinanceCosts` | 246 | 14.53% |
| 2 | `housing.HousingMarket.matchBidsWithOffers` | 117 | 6.91% |
| 3 | `collectors.HouseholdStats.record` | 91 | 5.38% |
| 4 | `housing.Household.step` | 88 | 5.20% |
| 5 | `java.util.TreeMap.successor` | 87 | 5.14% |
| 6 | `java.util.TreeMap.getFloorEntry` | 82 | 4.84% |
| 7 | `housing.HouseholdBehaviour.updateDesiredPurchasePrice` | 72 | 4.25% |
| 8 | `java.util.TreeMap.getFirstEntry` | 71 | 4.19% |
| 9 | `org.apache.commons.math3.util.FastMath.log` | 64 | 3.78% |
| 10 | `java.util.TreeMap.getEntryUsingComparator` | 49 | 2.89% |
| 11 | `housing.HousingMarket.clearMatches` | 45 | 2.66% |
| 12 | `org.apache.commons.math3.random.BitsStreamGenerator.nextGaussian` | 31 | 1.83% |
| 13 | `java.util.TreeMap.put` | 26 | 1.54% |
| 14 | `housing.Household.getNProperties` | 25 | 1.48% |
| 15 | `java.io.BufferedWriter.write` | 25 | 1.48% |
| 16 | `java.util.TimSort.countRunAndMakeAscending` | 25 | 1.48% |
| 17 | `org.apache.commons.math3.util.FastMath.pow` | 25 | 1.48% |
| 18 | `java.util.TimSort.binarySort` | 22 | 1.30% |
| 19 | `java.util.TreeMap.compare` | 22 | 1.30% |
| 20 | `housing.Demographics.implementDeaths` | 21 | 1.24% |
| 21 | `Other` | 459 | 27.11% |

### Direct `modelStep()` Child Breakdown

| modelStep line | Phase | Samples | Percent |
| ---: | --- | ---: | ---: |
| 185 | `demographics.step()` | 49 | 2.89% |
| 187 | `construction.step()` | 0 | 0.00% |
| 189 | `household loop` | 768 | 45.36% |
| 191 | `creditSupply.preClearingResetCounters()` | 0 | 0.00% |
| 193 | `housingMarketStats.preClearingRecord()` | 13 | 0.77% |
| 195 | `houseSaleMarket.clearMarket()` | 79 | 4.67% |
| 197 | `housingMarketStats.postClearingRecord()` | 4 | 0.24% |
| 199 | `rentalMarketStats.preClearingRecord()` | 11 | 0.65% |
| 201 | `houseRentalMarket.clearMarket()` | 382 | 22.56% |
| 203 | `rentalMarketStats.postClearingRecord()` | 0 | 0.00% |
| 205 | `householdStats.record()` | 364 | 21.50% |
| 207 | `creditSupply.postClearingRecord()` | 23 | 1.36% |
| 209 | `bank.step()` | 0 | 0.00% |
| 211 | `centralBank.step()` | 0 | 0.00% |

### Interpretation

- Dominant `modelStep()` phase: `household loop` at 45.4% of modelStep samples.
- Second-largest `modelStep()` phase: `houseRentalMarket.clearMarket()` at 22.6% of modelStep samples.
- Dominant sampled hot method inside this view: `housing.Household.getAnnualFinanceCosts` at 14.5% of modelStep samples.
