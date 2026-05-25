# Calibration Parameter Changelog
Author: Max Stoddard

## Purpose And Maintenance Rule
This is the canonical agent-readable calibration provenance ledger for Python-driven and related parameter updates.
`input-data-versions/dashboard-input-version-history.json` remains the dashboard-facing machine-readable history; this
Markdown file carries the fuller reproduction narrative, commands, and method rationale for agents and maintainers.

Maintenance requirements:
- Update this file in the same change whenever non-legacy calibration outputs, defaults, methods, or script paths change.
- Keep this file append-only in the version-history section.
- Each script entry must include:
  - script path
  - outputs/keys produced
  - exact runnable command
  - expected-result snippet
  - method chosen
  - method-selection decision logic
  - rationale category
  - evidence links
  - version(s) affected

## Method-Selection Rationale Framework (Prerequisite For New Entries)
Before adding any new or updated script entry to this file, record a brief
decision-logic line using this framework:
- Primary objective:
  - `target reproduction`, or
  - `stability/robustness`, or
  - `backward compatibility`
  - `direct method justification` (diagnostic or policy-choice experiments)
- Why this method wins under the chosen objective.
- What key tradeoff is accepted (for example: slight reproduction error in
  exchange for better robustness or compatibility).

Required entry field format:
- Method-selection decision logic:
  - `Objective=<...>; Why=<...>; Tradeoff=<...>`

## Validation Catalog Metric Additions

### 2026-05-14: tenure shares and Rental Price Index mean
- Metric ids added to the 2024 validation catalog and the v0-family 2011 reference overlay:
  - `household_owning_share`
  - `household_renting_share`
  - `rpi_mean`
- Source/evidence artifacts:
  - `input-data-versions/validation-sources/2024/frs/`
  - `input-data-versions/validation-sources/2011/frs/`
  - `input-data-versions/validation-sources/2024/ons-rpi/`
  - `input-data-versions/validation-sources/2011/ons-rpi/`
- Implementation notes:
  - Tenure shares use `HousingStatus-run1.csv` stock snapshots, with owner-occupied as `HousingStatus == 2` and private renting as `HousingStatus == 1`.
  - `rpi_mean` reads `Output-run1.csv` column `Rental HPI`, rebased to the first validation-window value = `1.0`.
  - RPI means Rental Price Index, not Retail Prices Index.
  - Tenure-share loss uses bounded-domain-normalized percentage-point distance over the 0..100 percentage-point share domain; the rounded FRS source bands remain the status bands, not the loss denominator.
  - `household_btl_investing_share` remains excluded from this metric-list update because no acceptable public/source evidence artifact has been checked in for both 2011 and 2024.

## Current Reproducible Commands (Latest Baseline: `input-data-versions/v4.21`)

### `scripts/python/calibration/was/age_dist.py`
- Outputs/keys produced:
  - `Age8-R8-Weighted.csv`
- Command:
```bash
python3 -m scripts.python.calibration.was.age_dist --dataset R8 --output-dir input-data-versions/v3.6
```
- Expected-result snippet:
  - file exists: `input-data-versions/v3.6/Age8-R8-Weighted.csv`
- Source dataset window:
  - WAS Round 8 household data collected between April 2020 and March 2022
- Method chosen:
  - weighted WAS age histogram with R8 compatibility final bin `75-95`
- Method-selection decision logic:
  - `Objective=backward compatibility; Why=R8 age-bin convention 75-95 preserves downstream model compatibility; Tradeoff=keeps legacy-shaped bins instead of redesigning age segmentation.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/was/age_distribution_comparison.py`
- Version(s) affected:
  - `v1.3`

### `scripts/python/calibration/was/btl_probability_per_income_percentile_bin.py`
- Outputs/keys produced:
  - `BTLProbabilityPerIncomePercentileBin-R8.csv`
- Command:
```bash
python3 -m scripts.python.calibration.was.btl_probability_per_income_percentile_bin --dataset R8 --output-dir tmp/was_v36 && cp tmp/was_v36/BTLProbabilityPerIncomePercentileBin.csv input-data-versions/v3.6/BTLProbabilityPerIncomePercentileBin-R8.csv
```
- Expected-result snippet:
  - file exists: `input-data-versions/v3.6/BTLProbabilityPerIncomePercentileBin-R8.csv`
- Source dataset window:
  - WAS Round 8 household data collected between April 2020 and March 2022
- Method chosen:
  - gross non-rent income percentile bins with BTL flag from positive gross rental income
- Method-selection decision logic:
  - `Objective=target reproduction; Why=direct percentile-bin estimator matches required output schema and calibration use; Tradeoff=simpler semantic estimator over richer model fitting.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `scripts/python/experiments/was/btl_probability_per_income_percentile_comparison.py`
- Version(s) affected:
  - `v1.2`

### `scripts/python/calibration/was/income_age_joint_prob_dist.py`
- Outputs/keys produced:
  - `AgeGrossIncomeJointDist.csv`
  - `AgeNetIncomeJointDist.csv`
- Command:
```bash
python3 -m scripts.python.calibration.was.income_age_joint_prob_dist --dataset R8 --output-dir input-data-versions/v3.6
```
- Expected-result snippet:
  - file exists: `input-data-versions/v3.6/AgeGrossIncomeJointDist.csv`
- Source dataset window:
  - WAS Round 8 household data collected between April 2020 and March 2022
- Method chosen:
  - filtered positive non-rent incomes, trimmed tails, weighted 2D histogram by age/income bins
- Method-selection decision logic:
  - `Objective=stability/robustness; Why=positive filtering plus tail trimming reduces outlier-driven bin distortion; Tradeoff=extreme-tail observations are intentionally excluded.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/was/age_gross_income_joint_dist_comparison.py`
- Version(s) affected:
  - `v1.0`

### `scripts/python/calibration/was/wealth_income_joint_prob_dist.py`
- Outputs/keys produced:
  - `GrossIncomeGrossWealthJointDist.csv`
  - `GrossIncomeNetWealthJointDist.csv`
  - `GrossIncomeLiqWealthJointDist.csv`
  - `NetIncomeGrossWealthJointDist.csv`
  - `NetIncomeNetWealthJointDist.csv`
  - `NetIncomeLiqWealthJointDist.csv`
- Command:
```bash
python3 -m scripts.python.calibration.was.wealth_income_joint_prob_dist --dataset R8 --output-dir input-data-versions/v3.6
```
- Expected-result snippet:
  - file exists: `input-data-versions/v3.6/GrossIncomeNetWealthJointDist.csv`
- Source dataset window:
  - WAS Round 8 household data collected between April 2020 and March 2022
- Method chosen:
  - positive-and-trimmed non-rent income filtering and positive wealth filtering, weighted log-space joint distributions
- Method-selection decision logic:
  - `Objective=stability/robustness; Why=income filtering plus positive wealth constraints produce stable log-space joint densities; Tradeoff=rows with non-positive wealth are excluded from fit.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/was/gross_income_net_wealth_joint_dist_comparison.py`
- Version(s) affected:
  - `v1.1`

### `scripts/python/calibration/nmg/nmg_rental_lognormal_fit.py`
- Outputs/keys produced:
  - `RENTAL_PRICES_SCALE`
  - `RENTAL_PRICES_SHAPE`
- Command:
```bash
python3 -m scripts.python.calibration.nmg.nmg_rental_lognormal_fit private-datasets/nmg/nmg-2024.csv --qhousing-values 3,4
```
- Expected-result snippet:
  - `RENTAL_PRICES_SCALE = 6.4882696353`
  - `RENTAL_PRICES_SHAPE = 0.8031833339`
- Method chosen:
  - weighted lognormal fit with `qhousing in {3,4}`
- Method-selection decision logic:
  - `Objective=target reproduction; Why=weighted qhousing {3,4} variant is closest/exact at displayed precision in method search; Tradeoff=method remains tied to private-renter subset definition.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_rental_parameter_search.py`
- Version(s) affected:
  - `v3.1`

### `scripts/python/calibration/nmg/nmg_desired_rent_power_fit.py`
- Outputs/keys produced:
  - `DESIRED_RENT_SCALE`
  - `DESIRED_RENT_EXPONENT`
- Command:
```bash
python3 -m scripts.python.calibration.nmg.nmg_desired_rent_power_fit private-datasets/nmg/nmg-2024.csv --qhousing-values 3,4,5 --income-source incomev2comb_mid --rent-source spq07_mid --fit-method log_weighted
```
- Expected-result snippet:
  - `DESIRED_RENT_SCALE = 18.1279304158`
  - `DESIRED_RENT_EXPONENT = 0.3371001138`
- Method chosen:
  - midpoint mapped income/rent with weighted log-space regression
- Method-selection decision logic:
  - `Objective=target reproduction; Why=midpoint mappings + log_weighted fit reproduce targets while avoiding upper-bound inflation and high-rent domination; Tradeoff=does not optimize level-space squared error.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_desired_rent_method_search.py`
- Version(s) affected:
  - `v3.2`

### `scripts/python/calibration/nmg/nmg_btl_strategy_probabilities.py`
- Outputs/keys produced:
  - `BTL_P_INCOME_DRIVEN`
  - `BTL_P_CAPITAL_DRIVEN`
- Command:
```bash
python3 -m scripts.python.calibration.nmg.nmg_btl_strategy_probabilities private-datasets/nmg/nmg-2024.csv --method legacy_weighted --target-year 2024
```
- Expected-result snippet:
  - `BTL_P_INCOME_DRIVEN = 0.4018574757`
  - `BTL_P_CAPITAL_DRIVEN = 0.2093026372`
- Method chosen:
  - `legacy_weighted` with schema auto-detection and weighted aggregation
- Method-selection decision logic:
  - `Objective=backward compatibility; Why=legacy_weighted keeps continuity with historical strategy semantics while supporting 2024 proxy schema fallback; Tradeoff=classification semantics stay anchored to legacy design.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_btl_strategy_method_search.py`
- Version(s) affected:
  - `v3.3`

### `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Outputs/keys produced:
  - `HPA_EXPECTATION_FACTOR`
  - `HPA_EXPECTATION_CONST`
- Command:
```bash
python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search production \
  --nmg-wave 2015=private-datasets/nmg/nmg-2015.csv \
  --nmg-wave 2016=private-datasets/nmg/nmg-2016.csv \
  --nmg-wave 2017=private-datasets/nmg/nmg-2017.csv \
  --nmg-wave 2018=private-datasets/nmg/nmg-2018.csv \
  --nmg-wave 2019=private-datasets/nmg/nmg-2019.csv \
  --nmg-wave 2020=private-datasets/nmg/nmg-2020.csv \
  --nmg-wave 2021=private-datasets/nmg/nmg-2021.csv \
  --nmg-wave 2022=private-datasets/nmg/nmg-2022.csv \
  --nmg-wave 2023=private-datasets/nmg/nmg-2023.csv \
  --nmg-wave 2024=private-datasets/nmg/nmg-2024.csv \
  --nmg-wave 2025-pt1=private-datasets/nmg/nmg-2025-pt1.csv \
  --nmg-wave 2025-pt2=private-datasets/nmg/nmg-2025-pt2.csv \
  --ppd private-datasets/ppd/pp-2011.csv \
  --ppd private-datasets/ppd/pp.2012.csv \
  --ppd private-datasets/ppd/pp-2018.csv \
  --ppd private-datasets/ppd/pp-2019.csv \
  --ppd private-datasets/ppd/pp-2020.csv \
  --ppd private-datasets/ppd/pp-2021.csv \
  --ppd private-datasets/ppd/pp-2022.csv \
  --ppd private-datasets/ppd/pp-2023.csv \
  --ppd private-datasets/ppd/pp-2024.csv \
  --ppd private-datasets/ppd/pp-2025.csv \
  --linkage-xlsx private-datasets/nmg/boe-nmg-household-survey-data.xlsx

python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit \
  tmp/nmg_hpa_expectation_production_search.json \
  --target-year 2024
```
- Expected-result snippet:
  - selected production default:
    - `survey-target: national_cross_section__midpoint_exact`
    - `signal-method: annual_mean_annualised`
    - `category: A`
    - `regression: huber`
    - `plausibility: preferred`
    - `HPA_EXPECTATION_FACTOR = 0.2887897073`
    - `HPA_EXPECTATION_CONST = -0.0059593352`
- Method chosen:
  - `national_cross_section` + `midpoint_exact` + `annual_mean_annualised` + `Category A` + `huber`
- Method-selection decision logic:
  - `Objective=defensible 2024 recalibration; Why=the narrowed production search keeps the method national and transparent while promoting the midpoint_exact + Category A + annual_mean_annualised Huber fit because it lands in the preferred plausibility band and better resists unstable survey years than the simpler OLS alternatives; Tradeoff=the selected coefficients are not the lowest-RMSE OLS fit and they move materially away from the earlier admissible-but-weak OLS slope.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  - `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
  - `scripts/python/helpers/nmg/hpa_expectation.py`
  - `scripts/python/helpers/nmg/linkage.py`
- Version(s) affected:
  - `v4.2`

### `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Outputs/keys produced:
  - legacy printed-precision recovery metadata for `HPA_EXPECTATION_FACTOR`
  - legacy printed-precision recovery metadata for `HPA_EXPECTATION_CONST`
  - production search artifact for `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Command:
```bash
python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search legacy \
  --nmg-wave 2014=private-datasets/nmg/nmg-2014.csv \
  --nmg-wave 2015=private-datasets/nmg/nmg-2015.csv \
  --nmg-wave 2016=private-datasets/nmg/nmg-2016.csv \
  --nmg-wave 2017=private-datasets/nmg/nmg-2017.csv \
  --nmg-wave 2018=private-datasets/nmg/nmg-2018.csv \
  --ppd private-datasets/ppd/pp-2011.csv \
  --ppd private-datasets/ppd/pp.2012.csv \
  --ppd private-datasets/ppd/pp-2014-part1.csv \
  --ppd private-datasets/ppd/pp-2014-part2.csv \
  --ppd private-datasets/ppd/pp-2018.csv \
  --artifact-output tmp/nmg_hpa_expectation_legacy_search.json
```
- Expected-result snippet:
  - selected printed-precision legacy recovery:
    - `survey-target: owner_occupier_cross_section__midpoint_exact_cap35`
    - `signal-method: rolling_quarter_cumulative`
    - `category: A`
    - `2014 anchor/base/months: 2014 / 2012 / Aug-Oct`
    - `2018 anchor/base/months: 2012 / 2011 / Mar-May`
    - `HPA_EXPECTATION_FACTOR = 0.4407356112`
    - `HPA_EXPECTATION_CONST = -0.0066328562`
    - `legacy-printed-match: 0.44 / -0.007`
- Method chosen:
  - `owner_occupier_cross_section + midpoint_exact_cap35 + rolling_quarter_cumulative + Category A + explicit legacy per-wave pairing`
- Method-selection decision logic:
  - `Objective=target reproduction; Why=explicit per-wave pairing plus survey-aligned rolling-quarter cumulative Category-A owner-occupier signals is the only on-disk candidate that reproduces 0.44 / -0.007 at printed config precision; Tradeoff=the recovered legacy pairing remains historically opaque and intentionally legacy-only rather than becoming the production default.`
- Rationale category:
  - target reproduction
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  - `scripts/python/helpers/nmg/hpa_expectation.py`
  - `scripts/python/helpers/ppd/hpa_signal_methods.py`
  - `scripts/python/helpers/nmg/linkage.py`
- Version(s) affected:
  - `v0` to `v4.1`

### `scripts/python/calibration/ppd/house_price_lognormal_fit.py`
- Outputs/keys produced:
  - `HOUSE_PRICES_SCALE`
  - `HOUSE_PRICES_SHAPE`
- Command:
```bash
python3 -m scripts.python.calibration.ppd.house_price_lognormal_fit private-datasets/ppd/pp-2025.csv --method focused_repro_default --target-year 2025
```
- Expected-result snippet:
  - `HOUSE_PRICES_SCALE = 12.5485368828`
  - `HOUSE_PRICES_SHAPE = 0.6805162153`
- Method chosen:
  - `focused_repro_default` (status A only, population std, no trim)
- Method-selection decision logic:
  - `Objective=stability/robustness; Why=focused status-A + population-std method is cleaner and stable under current data quality assumptions; Tradeoff=small residual mismatch vs older legacy targets may remain due to data drift.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/ppd/ppd_house_price_lognormal_method_search.py`
- Version(s) affected:
  - `v3.0`

### `scripts/python/calibration/psd/psd_2024_pure_direct_calibration.py`
- Outputs/keys produced:
  - `MORTGAGE_DURATION_YEARS`
  - `DOWNPAYMENT_FTB_SCALE`
  - `DOWNPAYMENT_FTB_SHAPE`
  - `DOWNPAYMENT_OO_SCALE`
  - `DOWNPAYMENT_OO_SHAPE`
- Command:
```bash
scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh
```
- Expected-result snippet:
  - `MORTGAGE_DURATION_YEARS = 32`
  - `DOWNPAYMENT_FTB_SCALE = 10.656633574`
  - `DOWNPAYMENT_FTB_SHAPE = 1.0525063644`
  - `DOWNPAYMENT_OO_SCALE = 11.6262593749`
  - `DOWNPAYMENT_OO_SHAPE = 0.8751065769`
- Method chosen:
  - `median_anchored_nonftb_independent` downpayment method and `modal_midpoint_round` term method
- Method-selection decision logic:
  - `Objective=stability/robustness; Why=modal_midpoint term and median_anchored_nonftb_independent downpayment methods were chosen via stability/robustness ranking constraints; Tradeoff=not always the absolute nearest method by raw distance alone.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
  - `scripts/python/experiments/psd/psd_mortgage_duration_method_search.py`
  - `scripts/python/experiments/psd/psd_downpayment_lognormal_method_search.py`
- Version(s) affected:
  - `v3.4`, `v3.5`, `v3.6`

### `scripts/python/experiments/psd/psd_buy_budget_method_search.py`
- Outputs/keys produced:
  - ranked BUY* reproduction candidates:
    - `BUY_SCALE`
    - `BUY_EXPONENT`
    - `BUY_MU`
    - `BUY_SIGMA`
- Command:
```bash
scripts/psd/run_psd_buy_budget_method_search_parallel.sh
```
- Expected-result snippet:
  - best-ranked method:
    - `family=psd_log_ols_robust_mu|loan_to_income=comonotonic|income_to_price=comonotonic|loan_open_k=500|lti_open=10|lti_floor=2.5|income_open_k=100|property_open_k=10000|trim=0|within_bin_points=11|grid=4000|mu_hi_trim=0.0063`
  - best estimates:
    - `BUY_SCALE ~= 43.0647528622`
    - `BUY_EXPONENT ~= 0.8115853517`
    - `BUY_MU ~= -0.0178564659`
    - `BUY_SIGMA ~= 0.4083763694`
    - `Distance(norm) ~= 0.0292602479`
- Method chosen:
  - reproduction-first normalized-distance ranking over PSD 2011 + PPD 2011 candidate grid
- Method-selection decision logic:
  - `Objective=target reproduction; Why=the selected robust_mu method minimized normalized 4-key distance to BUY* targets in the configured search grid; Tradeoff=BUY_EXPONENT remains the dominant residual mismatch versus legacy targets despite strong scale/mu/sigma alignment.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/helpers/psd/buy_budget_methods.py`
  - `tmp/psd_buy_budget_shards_repro/PsdBuyBudgetMethodSearchMerged.csv`
- Version(s) affected:
  - `v3.8`

### `scripts/python/calibration/psd/psd_buy_budget_calibration.py`
- Outputs/keys produced:
  - `BUY_SCALE`
  - `BUY_EXPONENT`
  - `BUY_MU`
  - `BUY_SIGMA`
- Command:
```bash
python3 -m scripts.python.calibration.psd.psd_buy_budget_calibration --quarterly-csv private-datasets/psd/2024/psd-quarterly-2024.csv --ppd-csv private-datasets/ppd/pp-2025.csv --target-year-psd 2024 --target-year-ppd 2025 --method 'family=psd_log_ols_robust_mu|loan_to_income=comonotonic|income_to_price=comonotonic|loan_open_k=500|lti_open=10|lti_floor=2.5|income_open_k=100|property_open_k=10000|trim=0|within_bin_points=11|grid=4000|mu_hi_trim=0.0063' --output-dir tmp/psd_buy_budget_v38
```
- Expected-result snippet:
  - `BUY_SCALE = 0.0061771819`
  - `BUY_EXPONENT = 1.7577643641`
  - `BUY_MU = -0.0161667809`
  - `BUY_SIGMA = 0.9016848332`
- Method chosen:
  - use 2011-selected default method on production-year pairing PSD 2024 + PPD 2025
- Method-selection decision logic:
  - `Objective=target reproduction; Why=the production method is pinned to the top robust 2011 reproduction candidate (distance ~= 0.02926) before applying to modern data, preserving blueprint decision order; Tradeoff=modern BUY* values are method-driven candidates and are not gated by validation thresholds.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/psd/psd_buy_budget_method_search.py`
  - `tmp/psd_buy_budget_v38/PsdBuyBudgetCalibration.csv`
- Version(s) affected:
  - `v3.8`

### Experimental Entry: `scripts/python/experiments/was/personal_allowance.py`
- Outputs/keys produced:
  - diagnostic stdout:
    - single-allowance log difference
    - double-allowance log difference
- Command:
```bash
python3 -m scripts.python.experiments.was.personal_allowance
```
- Expected-result snippet:
  - single-allowance metric is lower than double-allowance metric
- Method chosen:
  - compare observed net income fit under single vs double allowance assumptions
- Method-selection decision logic:
  - `Objective=direct method justification; Why=single allowance yields lower log-squared error than double allowance on current WAS pipeline; Tradeoff=diagnostic evidence, not a standalone full-policy optimizer.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `scripts/python/experiments/was/personal_allowance.py`
- Version(s) affected:
  - `v2.2` context

### `scripts/python/calibration/boe/boe_bank_parameter_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_parameter_method_search.py`
- Shared helper path: `scripts/python/helpers/boe/bank_parameters.py`
- Outputs/keys produced: `CENTRAL_BANK_INITIAL_BASE_RATE`, `BANK_INITIAL_RATE`, `BANK_D_INTEREST_D_DEMAND`, `BANK_INITIAL_CREDIT_SUPPLY`
- Command:
```bash
curl -L -o input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv 'https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/1995&Dateto=31/Dec/2024&SeriesCodes=LPMVTUZ&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N'

python3 -m scripts.python.experiments.boe.boe_bank_parameter_method_search --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv --ons-households 28600000 --target-year 2024 --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6

python3 -m scripts.python.calibration.boe.boe_bank_parameter_calibration --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv --ons-households 28600000 --target-year 2024 --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6
```
- Replay note:
  - The `curl` step is a one-time evidence acquisition step. Repo-local reruns should reuse the checked-in `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv` file and can skip the network fetch.
- Expected-result snippet:
  - `CENTRAL_BANK_INITIAL_BASE_RATE = 0.0510833333`
  - `BANK_INITIAL_RATE = 0.0564953144`
  - `BANK_D_INTEREST_D_DEMAND = 0.0000005472`
  - `BANK_INITIAL_CREDIT_SUPPLY = 704.9388111888`
  - rejected diagnostic:
    - `BANK_D_INTEREST_D_DEMAND 2024-only fit = -0.0000059191`
- Method chosen:
  - Daily-weighted `2024` Bank Rate monthly mean for `CENTRAL_BANK_INITIAL_BASE_RATE`, monthly Bank Rate plus monthly housing-tools spread mean for `BANK_INITIAL_RATE`, through-origin `Delta spread_fraction = beta * Delta credit_per_household` fit on the full `1995-2024` overlap for `BANK_D_INTEREST_D_DEMAND`, and full-year `2024` VTUZ-per-household mean for `BANK_INITIAL_CREDIT_SUPPLY`.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the locked workflow keeps the static startup parameters aligned to the full-year 2024 validation window and uses the longer pre-2025 overlap for the demand-response coefficient because the 2024-only fit is negative under the model-consistent delta equation; Tradeoff=the promoted beta is much smaller than the legacy coefficient and the cumulative version chain intentionally passes through a transient v4.3 partial-step state before startup-rate coherence is restored in v4.4.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `scripts/python/experiments/boe/boe_bank_parameter_method_search.py`
  - `scripts/python/calibration/boe/boe_bank_parameter_calibration.py`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoeBankParameterMethodSearch.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoeBankParameterCalibrationSummary.csv`
  - `docs/superpowers/specs/2026-04-15-boe-bank-parameter-v4.3-v4.6-calibration.md`
- Version(s) affected:
  - `v4.3`
  - `v4.4`
  - `v4.5`
  - `v4.6`

### `scripts/python/calibration/boe/boe_bank_age_limit_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_age_limit_method_search.py`
- Shared helper path: `scripts/python/helpers/boe/bank_age_limit.py`
- Outputs/keys produced: `BANK_AGE_LIMIT`
- Command:
```bash
python3 -m scripts.python.experiments.boe.boe_bank_age_limit_method_search --output-dir input-data-versions/calibration-evidence/bank-age-limit-v4.9

python3 -m scripts.python.calibration.boe.boe_bank_age_limit_calibration --output-dir input-data-versions/calibration-evidence/bank-age-limit-v4.9
```
- Expected-result snippet:
  - `BANK_AGE_LIMIT = 75`
  - rejected diagnostics:
    - `hybrid_midpoint_round = 75`
    - `repay_cap_mean_round = 77`
- Method chosen:
  - `conservative_mainstream_mode` = mode of explicit origination caps `70, 75, 75` and repay-by caps `80, 75, 75, 75, 80`
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the unique mode across explicit public origination and repay-side thresholds is the least misleading conservative proxy for the overloaded single-scalar model parameter; Tradeoff=public lender criteria do not provide a direct 2024 market-wide maturity-age distribution, so the promoted value is a proxy rather than a direct observation.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `scripts/python/experiments/boe/boe_bank_age_limit_method_search.py`
  - `scripts/python/calibration/boe/boe_bank_age_limit_calibration.py`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/README.md`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitPublicSources.csv`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitMethodSearch.csv`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitCalibrationSummary.json`
- Version(s) affected:
  - `v4.9`

### `scripts/python/calibration/btl/bank_icr_hard_min_calibration.py`
- Companion experiment path: `scripts/python/experiments/btl/bank_icr_hard_min_method_search.py`
- Shared helper path: `scripts/python/helpers/btl/bank_icr_hard_min.py`
- Outputs/keys produced: `BANK_ICR_HARD_MIN`
- Command:
```bash
python3 -m scripts.python.experiments.btl.bank_icr_hard_min_method_search --output-dir input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10

python3 -m scripts.python.calibration.btl.bank_icr_hard_min_calibration --output-dir input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10
```
- Expected-result snippet:
  - `BANK_ICR_HARD_MIN = 1.25`
  - rejected diagnostics:
    - `stress_mapped_floor = 1.22`
    - `cross_segment_mean = 1.35`
- Method chosen:
  - `literal_standard_floor_125` = minimum retained Paragon 2024 decision threshold across `1.25, 1.25, 1.30, 1.30, 1.40, 1.40, 1.45, 1.45`
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the literal 125% lender floor is the cleanest semantic match to the model's hard BTL underwriting rule while UK Finance Q1-Q4 ICRs stay context-only; Tradeoff=public sources do not provide a weighted 2024 market-wide threshold and the model keeps the existing live-rate denominator rather than a stressed-rate translation.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `scripts/python/experiments/btl/bank_icr_hard_min_method_search.py`
  - `scripts/python/calibration/btl/bank_icr_hard_min_calibration.py`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/README.md`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinPublicSources.csv`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinMethodSearch.csv`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinCalibrationSummary.json`
- Version(s) affected:
  - `v4.10`

## Per-Version Changelog Entries (Append-Only)

### v1.0
- Script path: `scripts/python/calibration/was/income_age_joint_prob_dist.py`
- Outputs/keys produced: `DATA_INCOME_GIVEN_AGE` via `AgeGrossIncomeJointDist.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.income_age_joint_prob_dist --dataset R8 --output-dir input-data-versions/v1.0`
- Expected result snippet: output file generated with weighted age-income density rows.
- Source dataset window: WAS Round 8 household data collected between April 2020 and March 2022.
- Method chosen: weighted log-income by age joint distribution with positive-and-trimmed income filtering.
- Method-selection decision logic: `Objective=stability/robustness; Why=positive filtering and tail trimming stabilize bin estimates; Tradeoff=extreme tails are removed from calibration support.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/was/age_gross_income_joint_dist_comparison.py`
- Version(s) affected: `v1.0`

### v1.1
- Script path: `scripts/python/calibration/was/wealth_income_joint_prob_dist.py`
- Outputs/keys produced: `DATA_WEALTH_GIVEN_INCOME` via `GrossIncomeNetWealthJointDist.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.wealth_income_joint_prob_dist --dataset R8 --output-dir input-data-versions/v1.1`
- Expected result snippet: `GrossIncomeNetWealthJointDist.csv` generated.
- Source dataset window: WAS Round 8 household data collected between April 2020 and March 2022.
- Method chosen: weighted joint distribution for gross income vs net wealth in log space.
- Method-selection decision logic: `Objective=stability/robustness; Why=positive wealth constraints and filtered income support stable log-space joint densities; Tradeoff=non-positive wealth rows are excluded.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/was/gross_income_net_wealth_joint_dist_comparison.py`
- Version(s) affected: `v1.1`

### v1.2
- Script path: `scripts/python/calibration/was/btl_probability_per_income_percentile_bin.py`
- Outputs/keys produced: `DATA_BTL_PROBABILITY` via `BTLProbabilityPerIncomePercentileBin-R8.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.btl_probability_per_income_percentile_bin --dataset R8`
- Expected result snippet: 100 percentile-bin rows plus BTL probability values.
- Source dataset window: WAS Round 8 household data collected between April 2020 and March 2022.
- Method chosen: percentile binning over gross non-rent income and rental-income positivity as BTL marker.
- Method-selection decision logic: `Objective=target reproduction; Why=direct percentile-bin estimator aligns with required output table shape; Tradeoff=keeps a simple semantic indicator instead of model-heavy inference.`
- Rationale category: direct method justification.
- Evidence links: `scripts/python/experiments/was/btl_probability_per_income_percentile_comparison.py`
- Version(s) affected: `v1.2`

### v1.3
- Script path: `scripts/python/calibration/was/age_dist.py`
- Outputs/keys produced: `DATA_AGE_DISTRIBUTION` via `Age8-R8-Weighted.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.age_dist --dataset R8`
- Expected result snippet: final bin uses `75-95` compatibility convention.
- Source dataset window: WAS Round 8 household data collected between April 2020 and March 2022.
- Method chosen: weighted age histogram by WAS age bands.
- Method-selection decision logic: `Objective=backward compatibility; Why=R8 75-95 convention preserves downstream compatibility while updating dataset coverage; Tradeoff=retains legacy-style age-band structure.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/was/age_distribution_comparison.py`
- Version(s) affected: `v1.3`

### v2.0
- Script path: `N/A (manual source-data update)`
- Outputs/keys produced: `DATA_NATIONAL_INSURANCE_RATES`
- Exact run command: `N/A (manual update from public NI table source)`
- Expected result snippet: `NationalInsuranceRates.csv` updated and referenced in config.
- Method chosen: direct table update from source data.
- Method-selection decision logic: `Objective=target reproduction; Why=policy-table parameters are direct-source values rather than inferred estimates; Tradeoff=depends on source table update cadence.`
- Rationale category: direct method justification.
- Evidence links: `input-data-versions/dashboard-input-version-history.json`
- Version(s) affected: `v2.0`

### v2.1
- Script path: `N/A (manual source-data update)`
- Outputs/keys produced: `DATA_TAX_RATES`
- Exact run command: `N/A (manual update from public tax-rate table source)`
- Expected result snippet: `TaxRates.csv` updated and referenced in config.
- Method chosen: direct table update from source data.
- Method-selection decision logic: `Objective=target reproduction; Why=tax bands/rates are direct-source values and should not be statistically fitted; Tradeoff=depends on source table update cadence.`
- Rationale category: direct method justification.
- Evidence links: `input-data-versions/dashboard-input-version-history.json`
- Version(s) affected: `v2.1`

### v2.2
- Script path: `scripts/python/experiments/was/personal_allowance.py`
- Outputs/keys produced: `GOVERNMENT_GENERAL_PERSONAL_ALLOWANCE`, `GOVERNMENT_MONTHLY_INCOME_SUPPORT`
- Exact run command: `python3 -m scripts.python.experiments.was.personal_allowance`
- Expected result snippet: single allowance fit error lower than double allowance fit error.
- Method chosen: compare log-squared fit to observed net incomes under two allowance assumptions.
- Method-selection decision logic: `Objective=direct method justification; Why=single allowance minimizes fit error vs observed net incomes under current pipeline; Tradeoff=diagnostic comparison, not a full fiscal-policy model.`
- Rationale category: direct method justification.
- Evidence links: `scripts/python/experiments/was/personal_allowance.py`
- Version(s) affected: `v2.2`

### v3.0
- Script path: `scripts/python/calibration/ppd/house_price_lognormal_fit.py`
- Outputs/keys produced: `HOUSE_PRICES_SCALE`, `HOUSE_PRICES_SHAPE`
- Exact run command: `python3 -m scripts.python.calibration.ppd.house_price_lognormal_fit private-datasets/ppd/pp-2025.csv --method focused_repro_default --target-year 2025`
- Expected result snippet: `HOUSE_PRICES_SCALE = 12.5485368828`, `HOUSE_PRICES_SHAPE = 0.6805162153`.
- Method chosen: focused status-A method with population standard deviation.
- Method-selection decision logic: `Objective=stability/robustness; Why=status-A filtering and population moments provide cleaner, stable estimates under current data assumptions; Tradeoff=small residual mismatch vs legacy targets may persist from data drift.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/ppd/ppd_house_price_lognormal_method_search.py`
- Version(s) affected: `v3.0`

### v3.1
- Script path: `scripts/python/calibration/nmg/nmg_rental_lognormal_fit.py`
- Outputs/keys produced: `RENTAL_PRICES_SCALE`, `RENTAL_PRICES_SHAPE`
- Exact run command: `python3 -m scripts.python.calibration.nmg.nmg_rental_lognormal_fit private-datasets/nmg/nmg-2024.csv --qhousing-values 3,4`
- Expected result snippet: `RENTAL_PRICES_SCALE = 6.4882696353`, `RENTAL_PRICES_SHAPE = 0.8031833339`.
- Method chosen: weighted lognormal fit over private renter qhousing values.
- Method-selection decision logic: `Objective=target reproduction; Why=weighted qhousing {3,4} variant is closest/exact at displayed precision in search results; Tradeoff=ties method to private-renter subset definition.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/nmg/nmg_rental_parameter_search.py`
- Version(s) affected: `v3.1`

### v3.2
- Script path: `scripts/python/calibration/nmg/nmg_desired_rent_power_fit.py`
- Outputs/keys produced: `DESIRED_RENT_SCALE`, `DESIRED_RENT_EXPONENT`
- Exact run command: `python3 -m scripts.python.calibration.nmg.nmg_desired_rent_power_fit private-datasets/nmg/nmg-2024.csv --qhousing-values 3,4,5 --income-source incomev2comb_mid --rent-source spq07_mid --fit-method log_weighted`
- Expected result snippet: `DESIRED_RENT_SCALE = 18.1279304158`, `DESIRED_RENT_EXPONENT = 0.3371001138`.
- Method chosen: midpoint mappings with weighted log-space regression.
- Method-selection decision logic: `Objective=target reproduction; Why=midpoint mappings with log-weighted fitting reproduce targets while reducing upper-bound and high-rent bias; Tradeoff=not optimized for level-space SSE.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/nmg/nmg_desired_rent_method_search.py`
- Version(s) affected: `v3.2`

### v3.3
- Script path: `scripts/python/calibration/nmg/nmg_btl_strategy_probabilities.py`
- Outputs/keys produced: `BTL_P_INCOME_DRIVEN`, `BTL_P_CAPITAL_DRIVEN`
- Exact run command: `python3 -m scripts.python.calibration.nmg.nmg_btl_strategy_probabilities private-datasets/nmg/nmg-2024.csv --method legacy_weighted --target-year 2024`
- Expected result snippet: `BTL_P_INCOME_DRIVEN = 0.4018574757`, `BTL_P_CAPITAL_DRIVEN = 0.2093026372`.
- Method chosen: legacy-weighted strategy aggregation with schema auto-detection.
- Method-selection decision logic: `Objective=backward compatibility; Why=legacy_weighted preserves historical strategy semantics while supporting 2024 schema fallback; Tradeoff=keeps legacy classification structure.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/nmg/nmg_btl_strategy_method_search.py`
- Version(s) affected: `v3.3`

### v3.4
- Script path: `scripts/python/calibration/psd/psd_2024_pure_direct_calibration.py`
- Outputs/keys produced: `MORTGAGE_DURATION_YEARS`
- Exact run command: `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
- Expected result snippet: `MORTGAGE_DURATION_YEARS = 32`.
- Method chosen: `modal_midpoint_round` with open-top year assumption `45`.
- Method-selection decision logic: `Objective=stability/robustness; Why=modal midpoint was top-ranked for rounded quarter-to-quarter stability; Tradeoff=not always minimum raw-distance estimator.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links:
  - `scripts/python/experiments/psd/psd_mortgage_duration_method_search.py`
  - `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
- Version(s) affected: `v3.4`

### v3.5
- Script path: `scripts/python/calibration/psd/psd_2024_pure_direct_calibration.py`
- Outputs/keys produced: `DOWNPAYMENT_FTB_SCALE`, `DOWNPAYMENT_FTB_SHAPE`
- Exact run command: `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
- Expected result snippet: `DOWNPAYMENT_FTB_SCALE = 10.656633574`, `DOWNPAYMENT_FTB_SHAPE = 1.0525063644`.
- Method chosen: `median_anchored_nonftb_independent` with within-bin integration points `11`.
- Method-selection decision logic: `Objective=stability/robustness; Why=median anchoring and within-bin integration improved robust reproducibility across candidate tails; Tradeoff=not always the closest method by raw error in expanded grids.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links:
  - `scripts/python/experiments/psd/psd_downpayment_lognormal_method_search.py`
  - `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
- Version(s) affected: `v3.5`

### v3.6
- Script path: `scripts/python/calibration/psd/psd_2024_pure_direct_calibration.py`
- Outputs/keys produced: `DOWNPAYMENT_OO_SCALE`, `DOWNPAYMENT_OO_SHAPE`
- Exact run command: `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
- Expected result snippet: `DOWNPAYMENT_OO_SCALE = 11.6262593749`, `DOWNPAYMENT_OO_SHAPE = 0.8751065769`.
- Method chosen: `median_anchored_nonftb_independent` with non-FTB proxy from all-minus-FTB bins.
- Method-selection decision logic: `Objective=stability/robustness; Why=non-FTB proxy with constrained physical tail assumptions gave robust production estimates; Tradeoff=accepts proxy contamination risk vs unavailable direct OO observables.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links:
  - `scripts/python/experiments/psd/psd_downpayment_lognormal_method_search.py`
  - `scripts/psd/run_psd_2024_reproduce_v3_4_to_v3_6_values.sh`
- Version(s) affected: `v3.6`

### v3.8
- Script path: `scripts/python/calibration/psd/psd_buy_budget_calibration.py`
- Outputs/keys produced: `BUY_SCALE`, `BUY_EXPONENT`, `BUY_MU`, `BUY_SIGMA`
- Exact run command:
  - `scripts/psd/run_psd_buy_budget_method_search_parallel.sh`
  - `python3 -m scripts.python.calibration.psd.psd_buy_budget_calibration --quarterly-csv private-datasets/psd/2024/psd-quarterly-2024.csv --ppd-csv private-datasets/ppd/pp-2025.csv --target-year-psd 2024 --target-year-ppd 2025 --method 'family=psd_log_ols_robust_mu|loan_to_income=comonotonic|income_to_price=comonotonic|loan_open_k=500|lti_open=10|lti_floor=2.5|income_open_k=100|property_open_k=10000|trim=0|within_bin_points=11|grid=4000|mu_hi_trim=0.0063' --output-dir tmp/psd_buy_budget_v38`
- Expected result snippet:
  - `BUY_SCALE = 0.0061771819`
  - `BUY_EXPONENT = 1.7577643641`
  - `BUY_MU = -0.0161667809`
  - `BUY_SIGMA = 0.9016848332`
- Method chosen:
  - `family=psd_log_ols_robust_mu|loan_to_income=comonotonic|income_to_price=comonotonic|loan_open_k=500|lti_open=10|lti_floor=2.5|income_open_k=100|property_open_k=10000|trim=0|within_bin_points=11|grid=4000|mu_hi_trim=0.0063`
- Method-selection decision logic:
  - `Objective=target reproduction; Why=normalized reproduction-first ranking on PSD 2011 + PPD 2011 selected this robust method as closest to legacy BUY* targets (distance ~= 0.02926) before modern deployment; Tradeoff=modern outputs can shift materially when constrained to the historically selected method and are not blocked by a validation gate.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/psd/psd_buy_budget_method_search.py`
  - `tmp/psd_buy_budget_shards_repro/PsdBuyBudgetMethodSearchMerged.csv`
  - `tmp/psd_buy_budget_v38/PsdBuyBudgetCalibration.csv`
  - `input-data-versions/dashboard-input-version-history.json`
- Version(s) affected: `v3.8`

### v4.0
- Workflow: BUY v2 modern realism production calibration.
- Script path: `scripts/python/calibration/psd/psd_buy_budget_calibration_v2.py`
- Companion experiment path: `scripts/python/experiments/psd/psd_buy_budget_quantile_method_search_v2.py`
- Shared helper path: `scripts/python/helpers/psd/buy_budget_quantile_v2.py`
- Outputs/keys produced: `BUY_SCALE`, `BUY_EXPONENT`, `BUY_MU`, `BUY_SIGMA`
- Exact run command:
  - `scripts/psd/run_psd_buy_budget_method_search_v2.sh --output-dir tmp/psd_buy_budget_v2_1_search`
  - `scripts/psd/run_psd_buy_budget_calibration_v2.sh --output-dir tmp/psd_buy_budget_v2_1_calibration`
- Expected result snippet:
  - `BUY_MU = 0`
  - hard realism guardrails pass at incomes `25k,50k,100k,150k,200k`:
    - `1 < median budget multiple < 10`
    - `p95 budget multiple < 15`
    - `BUY_EXPONENT <= 1.0`
  - `BUY_SIGMA` warning emitted only when outside `[0.2, 0.6]`
  - production promotion gate:
    - `fit_degradation_vs_baseline <= 0.10`
- Method chosen:
  - constrained quantile fit with Pareto top-bin modeling, PSD anchor penalty, p95/sigma/curve penalties, and deterministic objective weight-grid search.
- Runtime controls:
  - variant evaluation supports `--workers` (default `16`) with live `[stage]`/`[progress]` logging.
  - additive CLI controls include:
    - `--hard-p95-cap`
    - `--exponent-max`
    - `--median-target-curve`
    - `--tail-family`
    - `--pareto-alpha-grid`
    - `--objective-weight-grid-profile`
    - `--fit-degradation-max` (calibration)
- Method-selection decision logic:
  - `Objective=direct method justification; Why=realism-first constrained optimization with explicit tail/exponent gates and baseline-degradation gate prevents implausible modern BUY* promotions while remaining data-anchored; Tradeoff=legacy 2011 closeness is comparison-only and no longer selection-driving.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `scripts/python/experiments/psd/psd_buy_budget_quantile_method_search_v2.py`
  - `scripts/python/calibration/psd/psd_buy_budget_calibration_v2.py`
  - `AGENT_BUY_CALIBRATION_PLAN.md`
- Version(s) affected:
  - `v4.0`

### v4.1
- Script path: `N/A (config-only policy-alignment update)`
- Outputs/keys produced: `BANK_LTV_HARD_MAX_FTB`, `BANK_LTV_HARD_MAX_HM`, `BANK_LTV_HARD_MAX_BTL`, `CENTRAL_BANK_LTV_HARD_MAX_FTB`, `CENTRAL_BANK_LTV_HARD_MAX_HM`, `CENTRAL_BANK_LTV_HARD_MAX_BTL`
- Exact run command: `N/A (direct config-only policy alignment in input-data-versions/v4.1/config.properties)`
- Expected result snippet:
  - `BANK_LTV_HARD_MAX_FTB = 0.95`
  - `BANK_LTV_HARD_MAX_HM = 0.95`
  - `BANK_LTV_HARD_MAX_BTL = 0.85`
  - `CENTRAL_BANK_LTV_HARD_MAX_FTB = 0.95`
  - `CENTRAL_BANK_LTV_HARD_MAX_HM = 0.95`
  - `CENTRAL_BANK_LTV_HARD_MAX_BTL = 0.85`
- Method chosen: direct config fork from `v4.0` with aligned representative-bank and central-bank hard LTV ceilings.
- Method-selection decision logic: `Objective=direct method justification; Why=aligned bank and central-bank hard LTV ceilings provide a clearer default policy baseline for FTB, HM, and BTL story work; Tradeoff=the cleaner aligned baseline modestly worsens several tracked credit and affordability metrics versus v4.0.`
- Rationale category: direct method justification.
- Evidence links:
  - `input-data-versions/dashboard-input-version-history.json`
  - `input-data-versions/validation/v4.1.json`
- Version(s) affected: `v4.1`

### v4.2
- Script path: `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Companion experiment path: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Outputs/keys produced: `HPA_EXPECTATION_FACTOR`, `HPA_EXPECTATION_CONST`
- Exact run command:
  - `python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search production --nmg-wave 2015=private-datasets/nmg/nmg-2015.csv --nmg-wave 2016=private-datasets/nmg/nmg-2016.csv --nmg-wave 2017=private-datasets/nmg/nmg-2017.csv --nmg-wave 2018=private-datasets/nmg/nmg-2018.csv --nmg-wave 2019=private-datasets/nmg/nmg-2019.csv --nmg-wave 2020=private-datasets/nmg/nmg-2020.csv --nmg-wave 2021=private-datasets/nmg/nmg-2021.csv --nmg-wave 2022=private-datasets/nmg/nmg-2022.csv --nmg-wave 2023=private-datasets/nmg/nmg-2023.csv --nmg-wave 2024=private-datasets/nmg/nmg-2024.csv --nmg-wave 2025-pt1=private-datasets/nmg/nmg-2025-pt1.csv --nmg-wave 2025-pt2=private-datasets/nmg/nmg-2025-pt2.csv --ppd private-datasets/ppd/pp-2011.csv --ppd private-datasets/ppd/pp.2012.csv --ppd private-datasets/ppd/pp-2018.csv --ppd private-datasets/ppd/pp-2019.csv --ppd private-datasets/ppd/pp-2020.csv --ppd private-datasets/ppd/pp-2021.csv --ppd private-datasets/ppd/pp-2022.csv --ppd private-datasets/ppd/pp-2023.csv --ppd private-datasets/ppd/pp-2024.csv --ppd private-datasets/ppd/pp-2025.csv --linkage-xlsx private-datasets/nmg/boe-nmg-household-survey-data.xlsx`
  - `python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit tmp/nmg_hpa_expectation_production_search.json --target-year 2024`
- Expected result snippet:
  - `HPA_EXPECTATION_FACTOR = 0.2887897073`
  - `HPA_EXPECTATION_CONST = -0.0059593352`
- Method chosen: `national_cross_section + midpoint_exact + annual_mean_annualised + Category A + Huber`
- Method-selection decision logic: `Objective=defensible 2024 recalibration; Why=the promoted Huber fit stays within the preferred plausibility band and becomes the artifact-locked default for both search and calculation; Tradeoff=the earlier simpler OLS v4.2 values are retained only as superseded history, not as the live default.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links:
  - `input-data-versions/dashboard-input-version-history.json`
  - `input-data-versions/validation/v4.2.json`
  - `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md`
- Version(s) affected: `v4.2`

#### HPA Expectation `v4.2` Production Calibration
- Script path: `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Companion experiment path: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Helper paths:
  - `scripts/python/helpers/nmg/hpa_expectation.py`
  - `scripts/python/helpers/nmg/linkage.py`
  - `scripts/python/helpers/ppd/hpa_signal_methods.py`
- Outputs/keys produced: `HPA_EXPECTATION_FACTOR`, `HPA_EXPECTATION_CONST`
- Exact run command:
  - `python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search production --nmg-wave 2015=private-datasets/nmg/nmg-2015.csv --nmg-wave 2016=private-datasets/nmg/nmg-2016.csv --nmg-wave 2017=private-datasets/nmg/nmg-2017.csv --nmg-wave 2018=private-datasets/nmg/nmg-2018.csv --nmg-wave 2019=private-datasets/nmg/nmg-2019.csv --nmg-wave 2020=private-datasets/nmg/nmg-2020.csv --nmg-wave 2021=private-datasets/nmg/nmg-2021.csv --nmg-wave 2022=private-datasets/nmg/nmg-2022.csv --nmg-wave 2023=private-datasets/nmg/nmg-2023.csv --nmg-wave 2024=private-datasets/nmg/nmg-2024.csv --nmg-wave 2025-pt1=private-datasets/nmg/nmg-2025-pt1.csv --nmg-wave 2025-pt2=private-datasets/nmg/nmg-2025-pt2.csv --ppd private-datasets/ppd/pp-2011.csv --ppd private-datasets/ppd/pp.2012.csv --ppd private-datasets/ppd/pp-2018.csv --ppd private-datasets/ppd/pp-2019.csv --ppd private-datasets/ppd/pp-2020.csv --ppd private-datasets/ppd/pp-2021.csv --ppd private-datasets/ppd/pp-2022.csv --ppd private-datasets/ppd/pp-2023.csv --ppd private-datasets/ppd/pp-2024.csv --ppd private-datasets/ppd/pp-2025.csv --linkage-xlsx private-datasets/nmg/boe-nmg-household-survey-data.xlsx`
  - `python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit tmp/nmg_hpa_expectation_production_search.json --target-year 2024`
- Expected result snippet:
  - `survey-target: national_cross_section__midpoint_exact`
  - `signal-method: annual_mean_annualised`
  - `category: A`
  - `regression: huber`
  - `HPA_EXPECTATION_FACTOR = 0.2887897073`
  - `HPA_EXPECTATION_CONST = -0.0059593352`
- Method chosen:
  - `national_cross_section + midpoint_exact + annual_mean_annualised + Category A + Huber`
- Method-selection decision logic:
  - `Objective=defensible 2024 recalibration; Why=the promoted Huber fit stays within the preferred plausibility band and becomes the artifact-locked default for both search and calculation; Tradeoff=the earlier simpler OLS v4.2 values are retained only as superseded history, not as the live default.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  - `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
  - `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md`
- Version(s) affected:
  - `v4.2`

### v4.3
- Script path: `scripts/python/calibration/boe/boe_bank_parameter_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_parameter_method_search.py`
- Outputs/keys produced: `CENTRAL_BANK_INITIAL_BASE_RATE`
- Exact run command:
  - `python3 -m scripts.python.calibration.boe.boe_bank_parameter_calibration --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv --ons-households 28600000 --target-year 2024 --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6`
- Expected result snippet:
  - `CENTRAL_BANK_INITIAL_BASE_RATE = 0.0510833333`
- Method chosen:
  - full-year `2024` mean of the daily-weighted monthly Bank Rate series
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the full-year 2024 daily-weighted mean matches the validation window more closely than January or December snapshots; Tradeoff=v4.3 is intentionally a partial startup-rate recalibration step and remains structurally inconsistent until BANK_INITIAL_RATE is promoted in v4.4.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEBankRate2024Monthly.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoeBankParameterCalibrationSummary.csv`
  - `input-data-versions/validation/v4.3.json`
- Version(s) affected: `v4.3`

### v4.4
- Script path: `scripts/python/calibration/boe/boe_bank_parameter_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_parameter_method_search.py`
- Outputs/keys produced: `BANK_INITIAL_RATE`
- Exact run command:
  - `python3 -m scripts.python.calibration.boe.boe_bank_parameter_calibration --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv --ons-households 28600000 --target-year 2024 --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6`
- Expected result snippet:
  - `BANK_INITIAL_RATE = 0.0564953144`
- Method chosen:
  - full-year `2024` mean of the monthly Bank Rate plus housing-tools spread mortgage-rate proxy
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the full-year 2024 mortgage-rate proxy keeps the startup lending rate aligned to the same validation window as the promoted base rate; Tradeoff=the resulting v4.4 snapshot restores startup-rate coherence but leaves house-price growth in the tracked validation warning band.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEMortgageRateProxy2024Monthly.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoeBankParameterCalibrationSummary.csv`
  - `input-data-versions/validation/v4.4.json`
- Version(s) affected: `v4.4`

### v4.5
- Script path: `scripts/python/calibration/boe/boe_bank_parameter_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_parameter_method_search.py`
- Outputs/keys produced: `BANK_D_INTEREST_D_DEMAND`
- Exact run command:
  - `python3 -m scripts.python.calibration.boe.boe_bank_parameter_calibration --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv --ons-households 28600000 --target-year 2024 --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6`
- Expected result snippet:
  - `BANK_D_INTEREST_D_DEMAND = 0.0000005472`
  - rejected diagnostic:
    - `2024-only fit = -0.0000059191`
- Method chosen:
  - through-origin fit on `Delta spread_fraction = beta * Delta credit_per_household` using the full `1995-2024` overlap
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the longer pre-2025 overlap yields a positive coefficient under the model-consistent delta equation while the 2024-only fit is negative and therefore not defensible as the live default; Tradeoff=the promoted coefficient is materially smaller than the legacy value and this intermediate version worsens several macro credit and affordability metrics versus v4.4.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZSpreadAlignedDeltas1995To2024.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZSpreadAlignedDeltas2024.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoeBankParameterMethodSearch.csv`
  - `input-data-versions/validation/v4.5.json`
- Version(s) affected: `v4.5`

### v4.6
- Script path: `scripts/python/calibration/boe/boe_bank_parameter_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_parameter_method_search.py`
- Outputs/keys produced: `BANK_INITIAL_CREDIT_SUPPLY`
- Exact run command:
  - `python3 -m scripts.python.calibration.boe.boe_bank_parameter_calibration --bank-rate-csv 'private-datasets/boe/BoE - Bank Rate history and data.csv' --housing-tools-xlsx private-datasets/boe/housing-tools.xlsx --vtuz-csv input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZGrossLendingInput.csv --ons-households 28600000 --target-year 2024 --output-dir input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6`
- Expected result snippet:
  - `BANK_INITIAL_CREDIT_SUPPLY = 704.9388111888`
- Method chosen:
  - full-year `2024` mean of monthly VTUZ gross lending converted to pounds per household using the locked ONS denominator
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the chosen per-household mean keeps the supply proxy aligned to the same 2024 window as the promoted startup-rate parameters and restores the best overall validation balance within the v4.3-v4.6 chain; Tradeoff=the direct data-aligned supply level still leaves mortgage approvals, HM advances, BTL advances, owner-occupier debt to income, and rental yield outside the required bands.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoEVTUZCreditSupplyPerHousehold2024Monthly.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/OnsHouseholds2024.csv`
  - `input-data-versions/calibration-evidence/boe-bank-v4.3-v4.6/BoeBankParameterCalibrationSummary.csv`
  - `input-data-versions/validation/v4.6.json`
- Version(s) affected: `v4.6`

### v4.7
- Script path: `scripts/python/calibration/official/uk_housing_stock_totals_2024.py`
- Outputs/keys produced: `UK_HOUSEHOLDS`, `UK_DWELLINGS`
- Exact run command:
  - `python3 -m scripts.python.calibration.official.uk_housing_stock_totals_2024 --ons-households-xlsx input-data-versions/calibration-evidence/uk-housing-stock-v4.7/ons-families-and-households-uk-2024.xlsx --england-dwellings-ods input-data-versions/calibration-evidence/uk-housing-stock-v4.7/england-live-table-100-2024.ods --wales-dwellings-csv input-data-versions/calibration-evidence/uk-housing-stock-v4.7/wales-dwelling-stock-estimates-2024.csv --scotland-dwellings-xlsx input-data-versions/calibration-evidence/uk-housing-stock-v4.7/scotland-households-and-dwellings-2024.xlsx --northern-ireland-dwellings-xlsx input-data-versions/calibration-evidence/uk-housing-stock-v4.7/northern-ireland-housing-stock-2008-2025.xlsx --output-dir input-data-versions/calibration-evidence/uk-housing-stock-v4.7`
- Expected result snippet:
  - `UK_HOUSEHOLDS = 28609000`
  - `UK_DWELLINGS = 30676974`
  - rejected comparators:
    - `UK_HOUSEHOLDS = 28600000`
    - `UK_DWELLINGS = 30679588`
- Method chosen:
  - source-native `2024` official artifact aggregation: ONS workbook households value in thousands converted to households, plus England ODS, Wales StatsWales CSV, Scotland workbook, and Northern Ireland workbook dwelling totals summed without mixing rounded public headlines
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the downloadable official artifacts provide the most auditable published 2024 totals and avoid mixed-precision drift from rounded release headlines; Tradeoff=the corrected stock totals materially raise the implied houses-per-household target from 0.855681 to 1.072284, which worsens v4.7 validation versus v4.6 and leaves the v4.6 BoE per-household denominator intentionally unresolved in this release.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/uk-housing-stock-v4.7/README.md`
  - `input-data-versions/calibration-evidence/uk-housing-stock-v4.7/UkHousingStockTotals2024SourceValues.csv`
  - `input-data-versions/calibration-evidence/uk-housing-stock-v4.7/UkHousingStockTotals2024CalibrationSummary.json`
  - `input-data-versions/validation/v4.7.json`
- Version(s) affected: `v4.7`

### v4.8
- Script path: `scripts/python/calibration/official/ehs_hold_period_2024.py`
- Outputs/keys produced: `HOLD_PERIOD`
- Exact run command:
  - `python3 -m scripts.python.calibration.official.ehs_hold_period_2024 --output-dir input-data-versions/calibration-evidence/ehs-hold-period-v4.8`
- Expected result snippet:
  - `Extracted value: 17.2`
  - `HOLD_PERIOD = 17.2`
- Method chosen:
  - published EHS annex-table extraction from `AT3_6 -> all owner occupiers -> 2023-24`
- Method-selection decision logic:
  - `Objective=direct method justification; Why=user chose the published 2023-24 EHS AT3_6 all-owner-occupier mean as the authoritative recalibration source; Tradeoff=this supersedes the earlier 17.0 value instead of reconstructing a legacy raw-row method.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/ehs-hold-period-v4.8/ehs_hold_period_source_values.csv`
  - `input-data-versions/calibration-evidence/ehs-hold-period-v4.8/ehs_hold_period_summary.json`
  - `input-data-versions/validation/v4.8.json`
- Version(s) affected:
  - `v4.8`

### v4.9
- Script path: `scripts/python/calibration/boe/boe_bank_age_limit_calibration.py`
- Companion experiment path: `scripts/python/experiments/boe/boe_bank_age_limit_method_search.py`
- Outputs/keys produced: `BANK_AGE_LIMIT`
- Exact run command:
  - `python3 -m scripts.python.calibration.boe.boe_bank_age_limit_calibration --output-dir input-data-versions/calibration-evidence/bank-age-limit-v4.9`
- Expected result snippet:
  - `BANK_AGE_LIMIT = 75`
  - rejected diagnostics:
    - `hybrid_midpoint_round = 75`
    - `repay_cap_mean_round = 77`
- Method chosen:
  - `conservative_mainstream_mode` = mode of explicit origination caps `70, 75, 75` and repay-by caps `80, 75, 75, 75, 80`
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the approved conservative mode keeps the overloaded scalar at the least misleading public mainstream benchmark after 65 is rejected by the retained 2024/near-2024 lender evidence; Tradeoff=this release uses a proxy built from public lender criteria rather than a direct market-wide 2024 maturity-age distribution, and the tracked validation regresses versus v4.8.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/README.md`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitPublicSources.csv`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitMethodSearch.csv`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitCalibrationSourceValues.csv`
  - `input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitCalibrationSummary.json`
  - `input-data-versions/validation/v4.9.json`
- Version(s) affected:
  - `v4.9`

### v4.10
- Script path: `scripts/python/calibration/btl/bank_icr_hard_min_calibration.py`
- Companion experiment path: `scripts/python/experiments/btl/bank_icr_hard_min_method_search.py`
- Shared helper path: `scripts/python/helpers/btl/bank_icr_hard_min.py`
- Outputs/keys produced: `BANK_ICR_HARD_MIN`
- Exact run command:
  - `python3 -m scripts.python.experiments.btl.bank_icr_hard_min_method_search --output-dir input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10`
  - `python3 -m scripts.python.calibration.btl.bank_icr_hard_min_calibration --output-dir input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10`
  - `bash input-data-versions/validate.sh v4.10 --output-dir tmp/validation/v4.10`
- Expected result snippet:
  - `BANK_ICR_HARD_MIN = 1.25`
  - rejected diagnostics:
    - `stress_mapped_floor = 1.22`
    - `cross_segment_mean = 1.35`
  - tracked validation:
    - `overallCompositeLoss = 0.601011`
- Method chosen:
  - `literal_standard_floor_125` = minimum retained Paragon 2024 decision threshold across `1.25, 1.25, 1.30, 1.30, 1.40, 1.40, 1.45, 1.45`, with `UK Finance` Q1-Q4 2024 ICRs retained as context only and `CENTRAL_BANK_ICR_HARD_MIN` left unchanged at `1.2`
- Method-selection decision logic:
  - `Objective=direct method justification; Why=promoting the literal 125% lender floor resolves the blocked legacy BANK_ICR_HARD_MIN note with the least assumption-heavy 2024 public proxy while keeping the effective live floor at max(1.25, 1.2) = 1.25; Tradeoff=the promoted value is not a weighted market-wide estimate, the tracked validation suite only checks downstream behaviour, and the stressed-rate versus live-rate mismatch remains a documented model limitation.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/README.md`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinPublicSources.csv`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinMethodSearch.csv`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinCalibrationSourceValues.csv`
  - `input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinCalibrationSummary.json`
  - `input-data-versions/validation/v4.10.json`
- Version(s) affected:
  - `v4.10`

### Compatibility Schema Backfill (2026-04-22)
- Scope:
  - `src/main/resources/config.properties`
  - every checked-in `input-data-versions/*/config.properties`
- Change:
  - backfilled default-off BTL feature toggles `enableBTLAmortizingMortgageMode`, `enableBTLDownpaymentLognormal`, and `enableBTLAlternativeReturn`
  - added required schema placeholders `DOWNPAYMENT_BTL_SCALE`, `DOWNPAYMENT_BTL_SHAPE`, and `BTL_ALTERNATIVE_RETURN` for strict config loading; snapshot placeholders reuse the snapshot-local owner-occupier scale/shape and `0.0`
  - moved legacy-only `DOWNPAYMENT_BTL_MEAN` and `DOWNPAYMENT_BTL_EPSILON` into `LEGACY PARAMETERS`
- Rationale:
  - backward-compatible schema backfill for opt-in BTL features; all checked-in snapshots keep legacy behaviour because every new toggle defaults to `false`

### v4.11
- Script path: `scripts/python/calibration/frs/age_dist.py`
- Outputs/keys produced: `DATA_AGE_DISTRIBUTION` via `Age15-FRS-2023-24-Weighted.csv`
- Exact run command:
  - `python3 -m scripts.python.calibration.frs.age_dist --output-dir input-data-versions/v4.11 --evidence-dir input-data-versions/calibration-evidence/frs-age-distribution-v4.11`
  - `bash input-data-versions/validate.sh v4.11 --output-dir tmp/validation/v4.11 --workers 20`
- Expected result snippet:
  - `DATA_AGE_DISTRIBUTION = src/main/resources/Age15-FRS-2023-24-Weighted.csv`
  - `Valid rows: 16754`
  - `Density integral: 1.000000000000`
  - tracked validation: `overallCompositeLoss = 0.559981`
- Method chosen:
  - Weighted FRS 2023-24 household HRP age-density file using `gross4` weights and the populated `hhageGR4` variable, with the `75+` source tail split uniformly across output bins `75-80`, `80-85`, and `85-95`.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the requested hhagegrp field is anonymized as A for all rows in househol.csv, while hhageGR4 is the only populated granular HRP age field and gross4 is the household grossing weight; Tradeoff=the final three runtime bins are an explicit uniform split from the source 75+ tail rather than directly observed 75-79, 80-84, and 85+ bins.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/frs-age-distribution-v4.11/FrsAgeDistributionSourceValues.csv`
  - `input-data-versions/calibration-evidence/frs-age-distribution-v4.11/FrsAgeDistributionSummary.json`
  - `input-data-versions/validation/v4.11.json`
- Version(s) affected:
  - `v4.11`

### v4.12
- Script path: `scripts/python/calibration/lcfs/consumption_fractions.py`
- Outputs/keys produced: `ESSENTIAL_CONSUMPTION_FRACTION`, `MAXIMUM_CONSUMPTION_FRACTION`
- Exact run command:
  - `python3 -m scripts.python.calibration.lcfs.consumption_fractions --output-json input-data-versions/calibration-evidence/lcfs-consumption-v4.12/LcfsConsumptionFractionsSummary.json --evidence-dir input-data-versions/calibration-evidence/lcfs-consumption-v4.12`
  - `python3 -m scripts.python.calibration.lcfs.consumption_fractions --dataset-year 2011 --method legacy-match`
  - `bash input-data-versions/validate.sh v4.12 --output-dir tmp/validation/v4.12 --workers 20`
- Expected result snippet:
  - `ESSENTIAL_CONSUMPTION_FRACTION = 0.6510123541`
  - `MAXIMUM_CONSUMPTION_FRACTION = 0.1964658008`
  - legacy reproduction command: `ESSENTIAL_CONSUMPTION_FRACTION = 0.66`, `MAXIMUM_CONSUMPTION_FRACTION = 0.17`
  - tracked validation: `overallCompositeLoss = 0.580818`
- Method chosen:
  - `weighted-modern` = LCFS 2023/24 `dvhh_ukanon_v2_2023.tab`, `weighta` annual weights, `p344p` gross normal weekly household income, and `p600t` all-person total consumption expenditure.
  - `ESSENTIAL_CONSUMPTION_FRACTION` is the annual-weighted median `p600t / p344p` for households with `p344p` between `520` and `640` weekly.
  - `MAXIMUM_CONSUMPTION_FRACTION` is the annual-weighted 99th percentile `p600t / (12 * p344p)` for households with `p344p * 52 > 7400`.
- Method-selection decision logic:
  - `Objective=post-2020 evidence refresh with explicit historical reproduction; Why=the promoted method uses the 2023/24 LCFS household weight, gross weekly income, and all-person total-consumption fields directly, with the essential-consumption weekly income band aligned to 520-640 and the maximum-consumption floor aligned to 7400 from 2024/25 income-support reasoning; Tradeoff=tracked 2024 validation remains worse than v4.11 (overallCompositeLoss 0.580818 versus 0.559981, delta +0.020837), but improves versus the earlier v4.12 LCFS note (0.586644) and restores Household Debt to Income from fail to warn while preserving transparent-literal and legacy-match diagnostics on their historical thresholds.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/lcfs-consumption-v4.12/LcfsConsumptionFractionsSourceValues.csv`
  - `input-data-versions/calibration-evidence/lcfs-consumption-v4.12/LcfsConsumptionFractionsSummary.json`
  - `input-data-versions/validation/v4.12.json`
- Version(s) affected:
  - `v4.12`

### v4.13
- Script path: `scripts/python/calibration/official/gov_income_support_2024.py`
- Outputs/keys produced: `GOVERNMENT_MONTHLY_INCOME_SUPPORT`
- Exact run command:
  - `curl -L -o input-data-versions/calibration-evidence/gov-income-support-v4.13/benefit-and-pension-rates-2024-to-2025.html https://www.gov.uk/government/publications/benefit-and-pension-rates-2024-to-2025/benefit-and-pension-rates-2024-to-2025`
  - `python3 -m scripts.python.calibration.official.gov_income_support_2024 --output-dir input-data-versions/calibration-evidence/gov-income-support-v4.13`
  - `bash input-data-versions/validate.sh v4.13 --output-dir tmp/validation/v4.13 --workers 20`
- Expected result snippet:
  - source weekly rate: `142.25`
  - `GOVERNMENT_MONTHLY_INCOME_SUPPORT = 616.4166666667`
  - tracked validation: `overallCompositeLoss = 0.566435`
- Method chosen:
  - Downloaded GOV.UK `Benefit and pension rates 2024 to 2025` HTML page retained in the evidence bundle.
  - Extracted the `Income Support` personal allowances row `Both 18 or over`, column `Rates 2024/25`.
  - Converted weekly rate to the model's monthly scalar as `142.25 * 52 / 12 = 616.4166666667`.
- Method-selection decision logic:
  - `Objective=direct source-year correction and unit consistency; Why=the calendar-month conversion preserves the official annual entitlement in the model's monthly input, whereas multiplying by four undercounts annual support by treating a year as 48 weeks; Tradeoff=Household Debt to Income moves from warn to fail even though overallCompositeLoss improves versus v4.12 (0.566435 versus 0.580818, delta -0.014383).`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/gov-income-support-v4.13/README.md`
  - `input-data-versions/calibration-evidence/gov-income-support-v4.13/benefit-and-pension-rates-2024-to-2025.html`
  - `input-data-versions/calibration-evidence/gov-income-support-v4.13/GovIncomeSupport2024SourceValues.csv`
  - `input-data-versions/calibration-evidence/gov-income-support-v4.13/GovIncomeSupport2024Summary.json`
  - `input-data-versions/validation/v4.13.json`
- Version(s) affected:
  - `v4.13`

### v4.14
- Script path: `scripts/python/calibration/frs/income_age_joint_dist.py`
- Outputs/keys produced: `DATA_INCOME_GIVEN_AGE` via `AgeGrossIncomeJointDist.csv`
- Exact run command:
  - `python3 -m scripts.python.calibration.frs.income_age_joint_dist --output-dir input-data-versions/v4.14 --evidence-dir input-data-versions/calibration-evidence/frs-income-age-v4.14`
  - `bash input-data-versions/validate.sh v4.14 --output-dir tmp/validation/v4.14 --workers 20`
- Expected result snippet:
  - `DATA_INCOME_GIVEN_AGE = src/main/resources/AgeGrossIncomeJointDist.csv`
  - `Selected age column: hhageGR4`
  - `Valid rows: 16326`
  - row probability sums: `16-20` through `85-95` each sum to `1.0` within floating-point tolerance
  - no empty age-bin fallbacks are needed in `FrsIncomeAgeJointDistSummary.json`
  - zero-bin counts are retained in `FrsIncomeAgeJointDistSummary.json`; the sparse `16-20` group has `14` zero log-income bins
  - tracked validation: `overallCompositeLoss = 0.565682`
- Method chosen:
  - Weighted FRS 2023-24 household gross non-rent income by HRP age joint distribution using derived `gross_non_rent_income = hhinc - rental_income_for_derivation`, `gross4`, and the same age-selection contract as `scripts/python/calibration/frs/age_dist.py`.
  - The script validates the FRS dictionary contracts for `gross4`, `hhinc`, `SUBLET`, `SUBRENT`, `hhagegrp`, and `hhageGR4`; treats `SUBLET == 2` not-applicable `SUBRENT` values as `0.0`; requires non-negative numeric `SUBRENT` only for `SUBLET == 1`; requires positive derived gross non-rent income and positive finite `gross4`; annualizes the derived weekly income with `* 52`; applies the WAS 1% lower/upper income-tail trim; takes `log(annual_income)`; and writes row-normalized probabilities for FRS age bins `16-20` through `85-95`.
  - `hhagegrp` is preferred when populated, but the supplied `househol.csv` has `hhagegrp` anonymized as `A`; therefore the promoted run uses the populated `hhageGR4` fallback and the existing `75+` tail split.
- Method-selection decision logic:
  - `Objective=match the WAS gross non-rent income-age method with FRS data; Why=the model consumes this file as gross non-rent/employment-style income and WAS derives non-rent income before filtering, while FRS encodes non-subletter SUBRENT as not applicable; therefore FRS now uses SUBLET to set non-subletter rental income to zero before deriving hhinc - rental_income_for_derivation; Tradeoff=overallCompositeLoss slightly improves versus v4.13 (0.565682 versus 0.566435, delta -0.000753) and improves versus the earlier sparse SUBRENT-filtered run (0.683570, delta -0.117889), but Income Distribution Realism JSD remains worse than v4.13 (0.090645 versus 0.062847) while still passing. Household Debt to Income changes from fail to warn; no required metric changes between pass and fail.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/frs-income-age-v4.14/FrsIncomeAgeJointDistSourceValues.csv`
  - `input-data-versions/calibration-evidence/frs-income-age-v4.14/FrsIncomeAgeJointDistSummary.json`
  - `input-data-versions/validation/v4.14.json`
- Version(s) affected:
  - `v4.14`

### v4.14o
- Script path: `scripts/python/calibration/output/btl_probability_multiplier.py`
- Outputs/keys produced: `BTL_PROBABILITY_MULTIPLIER`
- Exact run command:
  - `python3 -m scripts.python.calibration.output.btl_probability_multiplier --version v4.14 --output-version v4.14o --workers 20 --precision 0.005 --overwrite-version`
  - `bash input-data-versions/validate.sh v4.14o --output-dir tmp/validation/v4.14o --workers 20`
- Expected result snippet:
  - `BTL_PROBABILITY_MULTIPLIER = 0.435`
  - `DATA_BTL_PROBABILITY` unchanged from `v4.14`
  - weighted WAS R8 positive-gross-rental-income target: `0.0515255103048705`
  - selected model-side rental-income-positive share: `0.0516349791549360`
  - selected absolute target gap: `0.0001094688500655`
  - tracked validation: `overallCompositeLoss = 0.658907`
- Method chosen:
  - BTL-only snapshot-local common-random-number grid search over `BTL_PROBABILITY_MULTIPLIER`.
  - The script used seeds `1..4`, `20` workers, `N_STEPS = 2000`, `t >= 200`, `recordRentalIncome = true`, and `recordCoreIndicators = true`.
  - Coarse grid: `0.05..2.00` by `0.05`; fine grid: `0.30..0.60` by `0.005` after the coarse winner landed at `0.45`.
  - Selection minimized only the absolute gap between the weighted WAS R8 target and the model-side share of households with `MonthlyGrossRentalIncome > 0`.
  - Machine-readable `searchDiagnostics` show that both the coarse and fine stages bracketed the target, selected an interior candidate, and only warn that the selected candidate is not an exact target hit at `1e-12` tolerance.
- Method-selection decision logic:
  - `Objective=output prevalence bridge; Why=MonthlyGrossRentalIncome > 0 is the closest recorded model observable to the weighted WAS R8 positive-gross-rental-income target while DATA_BTL_PROBABILITY was explicitly out of scope; Tradeoff=the expanded search brackets the target and selects an interior closest candidate (0.435) with a small residual target gap, and Advances to BTL moves from fail to pass, but tracked 2024 validation worsens versus v4.14 (overallCompositeLoss 0.658907 versus 0.565682, delta +0.093225) and House Price Growth moves from pass to fail.`
- Rationale category:
  - output calibration
- Evidence links:
  - `input-data-versions/calibration-evidence/output-btl-probability-multiplier-v4.14o/BtlProbabilityMultiplierCandidates.csv`
  - `input-data-versions/calibration-evidence/output-btl-probability-multiplier-v4.14o/BtlProbabilityMultiplierCalibrationSummary.json`
  - `input-data-versions/validation/v4.14o.json`
- Version(s) affected:
  - `v4.14o`

### v0o
- Script path: `scripts/python/calibration/output/btl_probability_multiplier.py`
- Outputs/keys produced: `BTL_PROBABILITY_MULTIPLIER`
- Exact run command:
  - `python3 -m scripts.python.calibration.output.btl_probability_multiplier --version v0 --output-version v0o --seeds 1,2,3,4 --workers 20 --precision 0.005 --coarse-min 0.05 --coarse-max 2 --coarse-step 0.05 --fine-radius 0.15 --target 0.0752616555661275 --output-root tmp/output-calibration`
  - `python3 -m scripts.python.validation.model.validate_all_input_data_versions --versions v0o,v0oo,v4.14oo --seeds 1,2,3,4,5,6,7,8 --workers 20 --output-root tmp/validation`
- Expected result snippet:
  - `BTL_PROBABILITY_MULTIPLIER = 1.63`
  - weighted WAS R8 positive-gross-rental-income target: `0.0752616555661275`
  - selected model-side rental-income-positive share: `0.0751221178308202`
  - selected absolute target gap: `0.0001395377353073`
  - tracked validation: `overallCompositeLoss = 0.716773`
- Method chosen:
  - BTL-only snapshot-local common-random-number grid search over `BTL_PROBABILITY_MULTIPLIER`.
  - The script used seeds `1..4`, `20` workers, `N_STEPS = 2000`, `t >= 200`, `recordRentalIncome = true`, and `recordCoreIndicators = true`.
  - Coarse grid: `0.05..2.00` by `0.05`; fine grid: `1.50..1.80` by `0.005` after the coarse winner landed at `1.65`.
  - Selection minimized only the absolute gap between the weighted WAS R8 target and the model-side share of households with `MonthlyGrossRentalIncome > 0`.
- Method-selection decision logic:
  - `Objective=output prevalence bridge; Why=MonthlyGrossRentalIncome > 0 is the closest recorded model observable to the weighted WAS R8 positive-gross-rental-income target; Tradeoff=the selected multiplier nearly matches the prevalence target, but tracked 2024 validation slightly worsens versus v0 (overallCompositeLoss 0.716773 versus 0.710294, delta +0.006478).`
- Rationale category:
  - output calibration
- Evidence links:
  - `input-data-versions/calibration-evidence/output-btl-probability-multiplier-v0o/BtlProbabilityMultiplierCandidates.csv`
  - `input-data-versions/calibration-evidence/output-btl-probability-multiplier-v0o/BtlProbabilityMultiplierCalibrationSummary.json`
  - `input-data-versions/validation/v0o.json`
- Version(s) affected:
  - `v0o`

### v0oo
- Script path: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
- Exact run command:
  - `python3 -m scripts.python.calibration.output.four_parameter_esmda --version v0o --output-version v0oo --validation-year 2011 --seeds 1,2,3,4 --workers 20 --ensemble-size 40 --assimilation-steps 4 --rng-seed 20260502 --output-root tmp/output-calibration`
  - `python3 -m scripts.python.validation.model.validate_all_input_data_versions --versions v0o,v0oo,v4.14oo --seeds 1,2,3,4,5,6,7,8 --workers 20 --output-root tmp/validation`
- Expected result snippet:
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.25`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.0014`
  - `BTL_CHOICE_INTENSITY = 100`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.6`
  - selected 2011-profile calibration loss: `0.449527` versus baseline `0.505610`
  - tracked 2024 validation: `overallCompositeLoss = 0.705098`
- Method chosen:
  - Four-parameter ESMDA output calibration against the `validation-reference-v0-2011` profile.
  - The script used source snapshot `v0o`, seeds `1..4`, `20` workers, ensemble size `40`, `4` assimilation steps, rng seed `20260502`, and selected snapped iteration `0` member `30`.
  - Canonical 8-seed 2024 validation was then published for dashboard comparability.
- Method-selection decision logic:
  - `Objective=target reproduction; Why=the 2011 reference validation profile is the intended target for a v0-derived output calibration branch; Tradeoff=the promoted branch improves tracked 2024 validation versus v0o (overallCompositeLoss 0.705098 versus 0.716773, delta -0.011675), but it remains a v0-derived reference branch rather than the modern baseline.`
- Rationale category:
  - output calibration
- Evidence links:
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v0oo/AllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v0oo/FourParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/validation/v0oo.json`
- Version(s) affected:
  - `v0oo`

### v0o1
- Script path: `scripts/python/calibration/output/btl_probability_multiplier.py`
- Outputs/keys produced:
  - `BTL_PROBABILITY_MULTIPLIER`
- Exact run command:
  - `python3 -m scripts.python.calibration.output.btl_probability_multiplier --version v0 --output-version v0o1 --seeds 1,2,3,4,5,6,7,8 --workers 20 --precision 0.005 --coarse-min 0.05 --coarse-max 2 --coarse-step 0.05 --fine-radius 0.15 --target 0.0752616555661275 --target-description "WAS Wave 3 household BTL prevalence target. The rounded 0.0752617 target is documented in input-data-versions/v0/config.properties; full precision 0.0752616555661275 is carried from existing v0o calibration evidence because no tracked W3 derivation artifact with more precision is available." --output-root tmp/output-calibration --evidence-dir input-data-versions/calibration-evidence/output-btl-probability-multiplier-v0o1 --overwrite-version`
  - `bash input-data-versions/validate.sh v0o1 --output-dir tmp/validation/v0o1 --workers 20`
- Expected result snippet:
  - `BTL_PROBABILITY_MULTIPLIER = 1.63`
  - WAS W3 household BTL prevalence target: `0.0752616555661275`
  - selected model-side rental-income-positive share: `0.0752794306134058`
  - selected absolute target gap: `0.0000177750472783`
  - 2011 reference overlay: `overallCompositeLoss = 0.526481`
  - secondary tracked 2024 validation: `overallCompositeLoss = 0.691123`
- Method chosen:
  - BTL-only snapshot-local common-random-number grid search over `BTL_PROBABILITY_MULTIPLIER`.
  - The script used seeds `1..8`, `20` workers, `N_STEPS = 2000`, `t >= 200`, `recordRentalIncome = true`, and `recordCoreIndicators = true`.
  - Coarse grid: `0.05..2.00` by `0.05`; fine grid: `1.50..1.80` by `0.005` after the coarse winner landed at `1.65`.
  - Selection minimized only the absolute gap between the W3/2011 prevalence target and the model-side share of households with `MonthlyGrossRentalIncome > 0`.
- Method-selection decision logic:
  - `Objective=2011/W3 output prevalence bridge; Why=MonthlyGrossRentalIncome > 0 is the closest recorded model observable to the W3 household BTL prevalence target; Tradeoff=the selected multiplier is the same numeric value as old v0o because the W3 target matches the old target value, but v0o1 corrects the campaign provenance, uses seeds 1..8 for selection, and is kept separate from the older R8-labelled v0o artifact.`
- Rationale category:
  - output calibration
- Evidence links:
  - `input-data-versions/calibration-evidence/output-btl-probability-multiplier-v0o1/BtlProbabilityMultiplierCandidates.csv`
  - `input-data-versions/calibration-evidence/output-btl-probability-multiplier-v0o1/BtlProbabilityMultiplierCalibrationSummary.json`
  - `input-data-versions/validation-overlays/v0o1-2011.json`
  - `input-data-versions/validation/v0o1.json`
- Version(s) affected:
  - `v0o1`

### v0o2
- Script path: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
- Exact run command:
  - Pre-run feasibility check: a `160` member, `6` assimilation-step run was started against `validation-reference-v0-2011`, but the live ETA was infeasible for this session and the partial results were retained only as safe cache inputs.
  - `python3 -m scripts.python.calibration.output.four_parameter_esmda --version v0o1 --output-version v0o2 --validation-year 2011 --validation-objective family_aware_metric_loss --validation-loss-error-std 1.0 --seeds 1,2,3,4,5,6,7,8 --workers 20 --ensemble-size 48 --assimilation-steps 5 --rng-seed 20260512 --output-root tmp/output-calibration --evidence-dir input-data-versions/calibration-evidence/output-four-parameter-esmda-v0o2 --local-refinement-top-n 8 --local-refinement-radius 1 --local-refinement-max-candidates 72`
  - `bash input-data-versions/validate.sh v0o2 --output-dir tmp/validation/v0o2 --workers 20`
- Expected result snippet:
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.25`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.0016`
  - `BTL_CHOICE_INTENSITY = 150`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.64`
  - `BTL_PROBABILITY_MULTIPLIER = 1.63` inherited unchanged from `v0o1`
  - selected 2011/W3 profile loss: `0.457489` versus `v0o1` baseline `0.526481`
  - selected status counts: `pass=8`, `warn=0`, `fail=9` versus baseline `pass=5`, `warn=0`, `fail=12`
  - secondary tracked 2024 validation: `overallCompositeLoss = 0.652087`
- Method chosen:
  - Four-parameter ESMDA output calibration against `validation-reference-v0-2011` using the schema-v4 `family_aware_metric_loss` objective and `schema4_metric_loss` assimilation transform.
  - The global pass used source snapshot `v0o1`, seeds `1..8`, `20` workers, ensemble size `48`, `5` assimilation steps plus the initial prior evaluation (`2304` global seed-runs), rng seed `20260512`, and left `BTL_PROBABILITY_MULTIPLIER` fixed.
  - Local refinement ranked snapped/practical parameter sets, deduplicated them, evaluated `52` snapped candidates (`416` local seed-runs), and promoted local candidate `26`.
  - Total calibration selection evidence contains `2720` model seed-runs: `2304` global plus `416` local.
- Guardrail decision logic:
  - Primary objective: lowest 2011/W3 `overallCompositeLoss` under `validation-reference-v0-2011` and `family_aware_metric_loss`.
  - Guardrail thresholds recorded in summary JSON and used for promotion: `requiredLossImprovement=0.001`, `materialLossImprovementForFailCountIncrease=0.02`, `strategicMetricDegradationTolerance=0.1`, `excessiveNormalizedSourceMovement=1.0`, `boundaryParameterMinimumLossImprovement=0.05`.
  - Strategic metrics guarded: `core_advancesToBTL`, `core_hpiMean`, `core_hpiStd`, `core_hpiCyclePeriod`, `income_distribution_jsd`, `housing_wealth_distribution_jsd`, and `financial_wealth_distribution_jsd`.
  - Lowest-loss local candidate `26` was accepted, so no lower-loss candidate was rejected. It improved loss by `0.068993`, reduced required fail count by `3`, had no hard-boundary parameters, and had normalized source movement `0.397650`.
- Method-selection decision logic:
  - `Objective=2011/W3 reference reproduction; Why=the campaign intentionally recalibrates the v0-derived branch against 2011/W3 only and keeps BTL_PROBABILITY_MULTIPLIER outside ES-MDA because it already has a separate prevalence-matching stage; Tradeoff=the scaled 48x5 global run is smaller than the attempted 160x6 plan due to infeasible ETA, but it is still larger than old v0oo in total seed-runs, uses seeds 1..8, applies local snapped refinement, and improves both the retained 2011 overlay and secondary 2024 comparability summary.`
- Rationale category:
  - output calibration
- Evidence links:
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v0o2/AllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v0o2/LocalRefinementMembers.csv`
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v0o2/FourParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/validation-overlays/v0o2-2011.json`
  - `input-data-versions/validation/v0o2.json`
- Version(s) affected:
  - `v0o2`

### v0o3
- Script path:
  - `scripts/python/calibration/output/output_parameter_esmda.py`
  - historical compatibility entrypoint retained: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_PROBABILITY_MULTIPLIER`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
  - Evidence artifacts were retained under `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3/`.
- Exact run command:
  - `python3 -m scripts.python.calibration.output.output_parameter_esmda --version v0 --output-version v0o3 --validation-year 2011 --validation-objective family_aware_metric_loss --validation-loss-error-std 1.0 --seeds 1,2,3,4,5,6,7,8,9,10 --workers 20 --ensemble-size 64 --assimilation-steps 6 --rng-seed 20260515 --n-steps 3500 --validation-window-start 500 --validation-window-end 3500 --output-root tmp/output-calibration --evidence-dir input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3 --local-refinement-top-n 10 --local-refinement-radius 1 --local-refinement-max-candidates 100 --delete-csv-after-metrics`
- Expected result snippet:
  - `createdOutputVersion = false`
  - no output version was promoted because every snapped local-refinement candidate breached guardrails
  - `deleteCsvAfterMetrics = true`
  - `nSteps = 3500`
  - `validationWindow = 500..3500`
  - `seeds = 1..10`
  - best rejected local candidate: `PSYCHOLOGICAL_COST_OF_RENTING = 0.2`, `SENSITIVITY_RENT_OR_PURCHASE = 0.0011`, `BTL_PROBABILITY_MULTIPLIER = 1.13`, `BTL_CHOICE_INTENSITY = 90`, `MARKET_AVERAGE_PRICE_DECAY = 0.68`
  - best rejected 2011/W3 `overallCompositeLoss = 0.403528` versus `v0` campaign baseline `0.516610`
  - best rejected status counts `pass=10`, `warn=0`, `fail=10` versus baseline `pass=4`, `warn=3`, `fail=13`
  - guardrail rejection reason: `core_hpiStd` metric loss degraded from `0.356917` to `0.949698`, exceeding the `0.1` strategic-metric degradation tolerance.
- Method chosen:
  - Five-parameter ESMDA output calibration against `validation-reference-v0-2011` using the schema-v4 `family_aware_metric_loss` objective and `schema4_metric_loss` assimilation transform.
  - The campaign jointly varied `PSYCHOLOGICAL_COST_OF_RENTING`, `SENSITIVITY_RENT_OR_PURCHASE`, `BTL_PROBABILITY_MULTIPLIER`, `BTL_CHOICE_INTENSITY`, and `MARKET_AVERAGE_PRICE_DECAY` from source snapshot `v0`, without running a separate BTL-probability stage.
  - `BTL_PROBABILITY_MULTIPLIER` used positive log-space ESMDA bounds `0.05..2.5`, prior range `0.35..1.9`, and practical snapping to `0.005`.
  - The run used `64` ensemble members, `6` assimilation steps plus the initial prior evaluation, seeds `1..10`, `20` workers, `N_STEPS = 3500`, validation/calibration window `500..3500`, rng seed `20260515`, and snapped local refinement with top-n `10`, radius `1`, and max candidates `100`.
  - Local refinement evaluated `99` deduplicated snapped candidates (`990` local seed-runs). Every snapped candidate was rejected by the promotion guardrails.
- Guardrail decision logic:
  - Promotion required a loss improvement of at least `0.001`, no material strategic-metric degradation beyond `0.1`, no unearned fail-count increase, no excessive normalized source movement for marginal gains, and no hard-boundary parameter unless justified by a strong loss improvement.
  - Strategic metrics guarded: `core_advancesToBTL`, `core_hpiMean`, `core_hpiStd`, `core_hpiCyclePeriod`, `income_distribution_jsd`, `housing_wealth_distribution_jsd`, and `financial_wealth_distribution_jsd`.
  - The automated guardrail correctly rejected the best aggregate candidate because the aggregate 2011/W3 loss gain came with a material `core_hpiStd` regression.
- Method-selection decision logic:
  - `Objective=2011/W3 reference reproduction; Why=the campaign tested whether a direct five-parameter ES-MDA from v0 could jointly replace the separate BTL-probability stage and four-parameter stage under the family-aware validation objective; Tradeoff=the larger 64x6, 10-seed, long-window run improved aggregate 2011 campaign loss for the best rejected candidate but was not promoted because guarded house-price volatility materially regressed.`
- Rationale category:
  - output calibration failed guardrail attempt
- Evidence links:
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3/AllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3/LocalRefinementMembers.csv`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3/OutputParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3/README.md`
- Version(s) affected:
  - `v0o3`

### v0o6
- Script path:
  - `scripts/python/calibration/output/output_parameter_esmda.py`
  - historical compatibility entrypoint retained: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_PROBABILITY_MULTIPLIER`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
- Exact run command:
  - Source campaign member: `tmp/output-calibration/v0o3/five-parameter-esmda/runs/iter-01/member-059`
  - `python3 -m scripts.python.validation.model.validate_input_data_version --version v0o6 --seeds 1,2,3,4,5,6,7,8,9,10 --workers 20 --output-dir tmp/validation/v0o6-10seed-3500 --n-steps 3500 --validation-window-start 500 --validation-window-end 3500 --allow-noncanonical-seeds`
- Expected result snippet:
  - Manual override promoted exact raw cached v0o3 campaign iteration `1`, member `59`.
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.44043118640535517`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.0007341104261340001`
  - `BTL_PROBABILITY_MULTIPLIER = 2.106407975979989`
  - `BTL_CHOICE_INTENSITY = 106.05000372010099`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.5958665034502091`
  - 10-seed 2011 reference overallCompositeLoss improved from rescored `v0=0.5652252115924438` to `v0o6=0.5350597930294947` (delta `-0.030165418562949047`, `-5.336885%`).
  - HPI metric-loss deltas versus `v0`: `core_hpiMean=+0.0730957919906657`, `core_hpiStd=-0.18023522321656262`, `core_hpiCyclePeriod=-0.3714501134599785`.
- Method chosen:
  - Manual promotion of a cached five-parameter ES-MDA candidate from the `v0o3` campaign, using exact raw member parameters rather than snapped local-refinement values.
  - Fresh validation used seeds `1..10`, `20` workers, `N_STEPS = 3500`, and validation window `500..3500`.
- Method-selection decision logic:
  - `Objective=2011/W3 reference validation loss reduction; Why=the selected member improves aggregate 2011 loss, core_hpiStd loss, and core_hpiCyclePeriod loss versus v0; Tradeoff=core_hpiMean loss worsens, so this is validation-loss evidence rather than a broad model-output improvement.`
- Rationale category:
  - output calibration manual override
- Evidence links:
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o6/SourceAllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o6/SourceOutputParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o6/ManualPromotionOverride.md`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o6/ValidationComparison-v0o6-vs-v0-2011-10seed-500-3500.csv`
  - `input-data-versions/validation-overlays/v0o6-2011.json`
  - `input-data-versions/validation/v0o6.json`
- Version(s) affected:
  - `v0o6`

### v4.14oo
- Script path: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
- Exact run command:
  - `python3 -m scripts.python.calibration.output.four_parameter_esmda --version v4.14o --output-version v4.14oo --validation-year 2024 --seeds 1,2,3,4 --workers 20 --ensemble-size 40 --assimilation-steps 4 --rng-seed 20260502 --output-root tmp/output-calibration`
  - `python3 -m scripts.python.validation.model.validate_all_input_data_versions --versions v0o,v0oo,v4.14oo --seeds 1,2,3,4,5,6,7,8 --workers 20 --output-root tmp/validation`
- Expected result snippet:
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.25`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.00078`
  - `BTL_CHOICE_INTENSITY = 250`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.78`
  - selected 2024-profile calibration loss: `0.552406` versus baseline `0.653469`
  - tracked 2024 validation: `overallCompositeLoss = 0.607765`
- Method chosen:
  - Four-parameter ESMDA output calibration against the `validation-2024` profile.
  - The script used source snapshot `v4.14o`, seeds `1..4`, `20` workers, ensemble size `40`, `4` assimilation steps, rng seed `20260502`, and selected snapped iteration `2` member `35`.
  - Canonical 8-seed 2024 validation was then published and improved the current-baseline composite loss versus `v4.14o`.
- Method-selection decision logic:
  - `Objective=target reproduction; Why=the 2024 validation profile is the current-baseline target and the selected member reduces both ESMDA calibration loss and the canonical 8-seed tracked composite loss versus v4.14o; Tradeoff=output calibration improves aggregate validation fit and upgrades House Price Growth from fail to warn, but several required market-level metrics remain outside target bands.`
- Rationale category:
  - output calibration
- Evidence links:
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v4.14oo/AllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-four-parameter-esmda-v4.14oo/FourParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/validation/v4.14oo.json`
- Version(s) affected:
  - `v4.14oo`

### v4.14oo HPA robustness status correction
- Script path: `N/A (documentation-only recalibration-status correction)`
- Outputs/keys produced:
  - `HPA_YEARS_TO_CHECK`
- Exact run command:
  - `N/A`
- Expected result snippet:
  - `HPA_YEARS_TO_CHECK = 2`
  - no config value change
- Method chosen:
  - Status-confirm the existing config note that `2` is the robustness-selected setting after pre- and post-full-calibration analysis.
- Method-selection decision logic:
  - `Objective=stability/robustness; Why=the current config already documents values 1, 2, and 3 as robustness-tested and value 2 as optimal after full model calibration; Tradeoff=this is a ledger correction and does not add new empirical evidence or change model behavior.`
- Rationale category:
  - stability/robustness
- Evidence links:
  - `input-data-versions/v4.14oo/config.properties`
  - `input-data-versions/remaining_recalibration_data_sources.md`
- Version(s) affected:
  - `v4.14oo`

### v4.15
- Script path: `scripts/python/calibration/official/ehs_tenancy_length_2024.py`
- Outputs/keys produced:
  - `TENANCY_LENGTH_MIN`
  - `TENANCY_LENGTH_MAX`
- Exact run command:
  - `python3 -m scripts.python.calibration.official.ehs_tenancy_length_2024 --output-dir input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15`
  - `bash input-data-versions/validate.sh v4.15 --output-dir tmp/validation/v4.15 --workers 20`
- Expected result snippet:
  - `6 months: 23.6% (rounded 24%)`
  - `12 months: 61.3% (rounded 61%)`
  - `18 months: 3.8% (rounded 4%)`
  - `other: 11.3% (rounded 11%)`
  - `TENANCY_LENGTH_MIN = 6`
  - `TENANCY_LENGTH_MAX = 18`
- Method chosen:
  - Published EHS 2023-24 rented-sectors Annex Table 2.10 extraction from `AT2_10`.
  - The retained artifact is `input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15/EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods`, downloaded from `https://assets.publishing.service.gov.uk/media/6874f2a3730a1bf28e2f9321/EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods`.
  - The selected population is private renters with assured shorthold tenancies resident less than 3 years.
  - The model currently supports only uniform discrete support bounds for tenancy length, so `6` and `18` are promoted as the explicit empirical month-category bounds while the full discrete source distribution remains retained for audit.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the EHS 2023-24 rented-sectors annex table is a newer official tenancy-length source than the legacy ARLA 2013 Q4 assumption and directly reports AST initial agreement lengths; Tradeoff=this improves source currency and auditability but does not implement the full empirical multinomial distribution because the current Java model only exposes TENANCY_LENGTH_MIN/MAX support bounds.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15/README.md`
  - `input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15/EhsTenancyLengthSourceValues.csv`
  - `input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15/EhsTenancyLengthSummary.json`
  - `input-data-versions/validation/v4.15.json`
- Version(s) affected:
  - `v4.15`

### v4.16
- Script path: `N/A (direct official-policy source alignment)`
- Outputs/keys produced:
  - `CENTRAL_BANK_LTI_SOFT_MAX_FTB`
  - `CENTRAL_BANK_LTI_SOFT_MAX_HM`
  - `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB`
  - `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM`
- Exact run command:
  - `curl -L https://www.bankofengland.co.uk/financial-policy-summary-and-record/2024/november-2024 -o input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/bank-of-england-fpc-record-november-2024.html`
  - `curl -L https://www.bankofengland.co.uk/-/media/boe/files/financial-policy-summary-and-record/2024/fpc-record-november-2024.pdf -o input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/fpc-record-november-2024.pdf`
  - `bash input-data-versions/validate.sh v4.16 --output-dir tmp/validation/v4.16 --workers 20`
- Expected result snippet:
  - Bank of England FPC Record paragraph 44: LTI flow limit at loan-to-income ratios at or greater than `4.5`
  - Bank of England FPC Record paragraph 44: no more than `15%` of total new residential mortgages over that threshold
  - `CENTRAL_BANK_LTI_SOFT_MAX_FTB = 4.5`
  - `CENTRAL_BANK_LTI_SOFT_MAX_HM = 4.5`
  - `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB = 0.15`
  - `CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM = 0.15`
- Method chosen:
  - Directly promote the official Bank of England November 2024 FPC LTI flow-limit threshold and fraction into the model's central-bank owner-occupier LTI policy parameters.
  - The retained artifacts are `input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/bank-of-england-fpc-record-november-2024.html` and `input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/fpc-record-november-2024.pdf`.
  - The official policy is aggregate across new residential mortgages; the model exposes FTB and HM parameters, so both borrower groups are set to the same source-backed values. Equal FTB/HM flow-limit fractions use the existing Java shared-quota path.
  - The November 2024 de minimis threshold update to GBP 150 million annual residential mortgage lending is retained for audit but not encoded because the model has no lender-size threshold parameter.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the Bank of England November 2024 FPC Record is the official 2024 central-bank policy source and directly states the 4.5 LTI threshold and 15% flow limit; Tradeoff=the model approximates the aggregate FPC recommendation with equal FTB/HM parameters and cannot encode the lender-size de minimis threshold.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/README.md`
  - `input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/CentralBankLtiSoftMaxSourceValues.csv`
  - `input-data-versions/calibration-evidence/central-bank-lti-soft-max-v4.16/CentralBankLtiSoftMaxSummary.json`
  - `input-data-versions/validation/v4.16.json`
- Version(s) affected:
  - `v4.16`

### v4.17
- Script path: `N/A (direct official-policy source alignment)`
- Outputs/keys produced:
  - `CENTRAL_BANK_AFFORDABILITY_HARD_MAX`
- Exact run command:
  - `curl -L https://www.bankofengland.co.uk/news/2022/june/financial-policy-committee-confirms-withdrawal-of-mortgage-market-affordability-test -o input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/bank-of-england-fpc-withdrawal-affordability-test-2022.html`
  - `bash input-data-versions/validate.sh v4.17 --output-dir tmp/validation/v4.17 --workers 20`
- Expected result snippet:
  - Bank of England June 2022 news release: the FPC confirmed withdrawal of the mortgage-market affordability-test Recommendation, effective `2022-08-01`.
  - Bank of England June 2022 news release: the LTI flow limit would not be withdrawn, and FCA MCOB responsible-lending affordability assessments continue to apply.
  - `CENTRAL_BANK_AFFORDABILITY_HARD_MAX = 0.9999`
  - `BANK_AFFORDABILITY_HARD_MAX = 0.4`
  - Effective Java affordability cap remains `min(0.4, 0.9999) = 0.4`.
  - Tracked validation summary generated on `2026-05-03T17:00:01Z` with `overallCompositeLoss=0.6287151104480216`, unchanged from `v4.16`.
- Method chosen:
  - Directly promote the official Bank of England June 2022 FPC affordability-test withdrawal into the model's central-bank affordability hard-cap policy parameter.
  - Set `CENTRAL_BANK_AFFORDABILITY_HARD_MAX` to the high non-binding sentinel `0.9999` rather than duplicating the representative-bank affordability cap.
  - Retain `BANK_AFFORDABILITY_HARD_MAX = 0.4`, so private-bank underwriting behavior remains unchanged and the effective affordability cap remains `0.4`.
  - The retained artifact is `input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/bank-of-england-fpc-withdrawal-affordability-test-2022.html`.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the Bank of England June 2022 release directly confirms withdrawal of the FPC mortgage-market affordability-test Recommendation effective 2022-08-01, supporting a non-binding central-bank affordability cap; Tradeoff=0.9999 is a model sentinel rather than an observed affordability threshold, while the representative-bank cap preserves private-bank underwriting behavior.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/README.md`
  - `input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/CentralBankAffordabilityHardMaxSourceValues.csv`
  - `input-data-versions/calibration-evidence/central-bank-affordability-hard-max-v4.17/CentralBankAffordabilityHardMaxSummary.json`
  - `input-data-versions/validation/v4.17.json`
- Version(s) affected:
  - `v4.17`

### v4.18
- Script path: `N/A (direct official-policy source alignment)`
- Outputs/keys produced:
  - `CENTRAL_BANK_LTI_MONTHS_TO_CHECK`
  - `CENTRAL_BANK_ICR_HARD_MIN`
- Exact run command:
  - `curl -L https://www.bankofengland.co.uk/quarterly-bulletin/2024/2024/the-contribution-of-the-fpc-to-uk-financial-stability -o input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-fpc-contribution-financial-stability-2024.html`
  - `curl -L https://www.bankofengland.co.uk/prudential-regulation/publication/2016/amendments-to-the-pras-rules-on-loan-to-income-ratios-in-mortgage-lending-november-2016 -o input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-pra-lti-four-quarter-rolling-2017.html`
  - `bash input-data-versions/validate.sh v4.18 --output-dir tmp/validation/v4.18 --workers 20`
- Expected result snippet:
  - Bank of England November 2024 FPC Record paragraph 44: active LTI flow limit at loan-to-income ratios at or greater than `4.5`, with no more than `15%` of total new residential mortgages over that threshold.
  - PRA PS5/17: LTI flow-limit compliance uses a `four-quarter rolling basis`, mapped to `CENTRAL_BANK_LTI_MONTHS_TO_CHECK = 12` because the model advances monthly.
  - Bank of England 25 September 2024 Quarterly Bulletin article: the FPC has not yet used its powers of Direction over `LTV` or `DTI/ICR` limits for owner-occupier or buy-to-let mortgages.
  - `CENTRAL_BANK_LTI_MONTHS_TO_CHECK = 12`
  - `CENTRAL_BANK_ICR_HARD_MIN = 0.0`
  - `BANK_ICR_HARD_MIN = 1.25`
  - Effective Java ICR floor remains `max(1.25, 0.0) = 1.25`.
  - Tracked validation summary generated on `2026-05-04T14:37:24Z` with `overallCompositeLoss=0.6287151104480216`, unchanged from `v4.17`.
- Method chosen:
  - Source-confirm `CENTRAL_BANK_LTI_MONTHS_TO_CHECK = 12` by pairing the active 2024 Bank of England LTI flow-limit policy with the PRA four-quarter rolling implementation and the model's monthly step.
  - Set `CENTRAL_BANK_ICR_HARD_MIN = 0.0` to encode no separate FPC hard ICR Direction in the central-bank policy layer.
  - Retain `BANK_ICR_HARD_MIN = 1.25`, so private-bank BTL underwriting behavior remains unchanged and the effective Java ICR floor remains `1.25`.
  - The retained artifacts are `input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-fpc-contribution-financial-stability-2024.html` and `input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/bank-of-england-pra-lti-four-quarter-rolling-2017.html`.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the residual central-bank policy keys should distinguish active FPC policy from lender-side underwriting constraints; Tradeoff=CENTRAL_BANK_LTI_MONTHS_TO_CHECK uses a 2017 implementation source to map the active 2024 LTI policy to monthly steps, while CENTRAL_BANK_ICR_HARD_MIN=0.0 is a non-binding model sentinel rather than an observed numeric ICR threshold.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/README.md`
  - `input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/CentralBankResidualPolicySourceValues.csv`
  - `input-data-versions/calibration-evidence/central-bank-residual-policy-v4.18/CentralBankResidualPolicySummary.json`
  - `input-data-versions/validation/v4.18.json`
- Version(s) affected:
  - `v4.18`

### v4.19
- Script path: `scripts/python/calibration/official/rent_gross_yield_2024.py`
- Outputs/keys produced:
  - `RENT_GROSS_YIELD`
- Exact run command:
  - `curl -L https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/Average-prices-2024-12.csv -o input-data-versions/calibration-evidence/rent-gross-yield-v4.19/Average-prices-2024-12.csv`
  - `curl -L https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-2024-12.csv -o input-data-versions/calibration-evidence/rent-gross-yield-v4.19/UK-HPI-full-file-2024-12.csv`
  - `curl -L 'https://www.ons.gov.uk/file?uri=/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics/18december2024/priceindexofprivaterentsukmonthlypricestatistics.xlsx' -o input-data-versions/calibration-evidence/rent-gross-yield-v4.19/priceindexofprivaterentsukmonthlypricestatistics.xlsx`
  - `python3 -m scripts.python.calibration.official.rent_gross_yield_2024 --pipr-xlsx input-data-versions/calibration-evidence/rent-gross-yield-v4.19/priceindexofprivaterentsukmonthlypricestatistics.xlsx --hpi-full-csv input-data-versions/calibration-evidence/rent-gross-yield-v4.19/UK-HPI-full-file-2024-12.csv --average-prices-csv input-data-versions/calibration-evidence/rent-gross-yield-v4.19/Average-prices-2024-12.csv --output-dir input-data-versions/calibration-evidence/rent-gross-yield-v4.19`
  - `bash input-data-versions/validate.sh v4.19 --output-dir tmp/validation/v4.19 --workers 20`
- Expected result snippet:
  - The December 2024 ONS PIPR workbook marks UK and Northern Ireland rent-price levels as `[x]`, so the selected numerator uses the highest available numeric aggregate, Great Britain.
  - PIPR Great Britain rent-price mean, January-November 2024: `1271.1818181818182`.
  - HM Land Registry UK HPI full-file United Kingdom `AveragePrice` mean, January-December 2024: `262397.5833333333`.
  - `RENT_GROSS_YIELD = 12 * 1271.1818181818182 / 262397.5833333333 = 0.05813385026036566`, rounded in config to `0.0581338503`.
  - Tracked validation summary generated on `2026-05-05T09:51:30Z` with `overallCompositeLoss=0.61541905307338`, improved from `v4.18=0.6287151104480216`.
  - The `core_rentalYield` metric remains failing and moves from `5.8630533611111115%` in `v4.18` to `5.781926166666667%` in `v4.19`, still below the UK Finance 2024 observed target band `[6.88, 7.00]`.
- Method chosen:
  - Clone `v4.18` to `v4.19` and update only `RENT_GROSS_YIELD`.
  - Use the requested rent-to-price formula with ONS PIPR Great Britain rent-price levels and HM Land Registry UK HPI full-file United Kingdom average prices.
  - Retain the HMLR `Average-prices-2024-12.csv` file as a rejected comparator because the full file is richer, auditable, and already aligned with the repository's validation-source shape.
  - Do not add transaction-volume weighting over monthly HPI prices because this parameter needs a price-level denominator rather than a transaction-flow-weighted denominator, and the December 2024 full file lacks UK `SalesVolume` for November and December.
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the PIPR/HMLR formula replaces the legacy 2013 literature/ARLA source with official 2024 rent and price levels while documenting the unavailable literal UK rent numerator; Tradeoff=the numerator is Great Britain rather than UK, and the source-fidelity improvement does not directly fix the realized rental-yield validation metric.`
- Rationale category:
  - direct method justification
- Evidence links:
  - `input-data-versions/calibration-evidence/rent-gross-yield-v4.19/README.md`
  - `input-data-versions/calibration-evidence/rent-gross-yield-v4.19/RentGrossYield2024SourceValues.csv`
  - `input-data-versions/calibration-evidence/rent-gross-yield-v4.19/RentGrossYield2024Summary.json`
  - `input-data-versions/validation/v4.19.json`
- Version(s) affected:
  - `v4.19`

### v4.20
- Script path: `scripts/python/calibration/ppd/house_price_lognormal_fit.py`
- Outputs/keys produced:
  - `HOUSE_PRICES_SCALE`
  - `HOUSE_PRICES_SHAPE`
- Exact run command:
  - `python3 -m scripts.python.calibration.ppd.house_price_lognormal_fit private-datasets/ppd/pp-2025.csv --method focused_repro_default --target-year 2025`
  - `python3 -m scripts.python.calibration.ppd.house_price_lognormal_fit private-datasets/ppd/pp-2024.csv --method focused_repro_default --target-year 2024`
  - `bash input-data-versions/validate.sh v4.20 --output-dir tmp/validation/v4.20 --workers 20`
- Expected result snippet:
  - 2025 reproduction:
    - `HOUSE_PRICES_SCALE = 12.5485368828`
    - `HOUSE_PRICES_SHAPE = 0.6805162153`
  - 2024 promoted values:
    - `HOUSE_PRICES_SCALE = 12.5351947066`
    - `HOUSE_PRICES_SHAPE = 0.7743402838`
  - Tracked validation summary generated on `2026-05-12T17:32:42Z` with `overallCompositeLoss=0.6045043981851204`, compared with current `v4.19=0.5833322259841027`.
  - Status changes versus `v4.19`: none.
- Method chosen:
  - Clone `v4.19` to `v4.20` and update only `HOUSE_PRICES_SCALE` and `HOUSE_PRICES_SHAPE`.
  - Use the existing focused status-A PPD lognormal fit with population standard deviation and no trimming.
  - Keep raw PPD rows out of tracked evidence; retain only derived row counts, commands, and parameter outputs under `input-data-versions/calibration-evidence/house-prices-v4.20/`.
- Method-selection decision logic:
  - `Objective=source fidelity; Why=the current 2024 baseline should not depend on 2025 PPD transactions when a full annual 2024 PPD file exists, and the existing method exactly reproduces the old 2025 config values before recalculation; Tradeoff=the 2024 validation composite worsens modestly under the current validation code, with no metric status changes.`
- Rationale category:
  - source-fidelity correction
- Evidence links:
  - `input-data-versions/calibration-evidence/house-prices-v4.20/README.md`
  - `input-data-versions/calibration-evidence/house-prices-v4.20/HousePricesV420SourceValues.csv`
  - `input-data-versions/calibration-evidence/house-prices-v4.20/HousePricesV420Summary.json`
  - `input-data-versions/validation/v4.20.json`
- Version(s) affected:
  - `v4.20`

### v4.21
- Script path: `scripts/python/calibration/psd/psd_buy_budget_calibration_v2.py`
- Shared helper path: `scripts/python/helpers/psd/buy_budget_quantile_v2.py`
- Outputs/keys produced:
  - `BUY_SCALE`
  - `BUY_EXPONENT`
  - `BUY_MU`
  - `BUY_SIGMA`
- Exact run command:
  - `python3 -m scripts.python.calibration.psd.psd_buy_budget_calibration_v2 --quarterly-csv private-datasets/psd/2024/psd-quarterly-2024.csv --ppd-csv-2024 private-datasets/ppd/pp-2024.csv --target-year-psd 2024 --ppd-status-mode a_only --year-policy 2024_only --guardrail-mode fail --hard-p95-cap 15 --exponent-max 1.0 --median-target-curve 25000:6.5,50000:6.0,100000:5.4,150000:5.0,200000:4.8 --tail-family pareto --pareto-alpha-grid 1.8 --objective-weight-grid-profile minimal --fit-degradation-max 0.10 --within-bin-points 11 --quantile-grid-size 4000 --ppd-mean-anchor-weight 4.0 --fixed-exponent 1.0 --income-open-upper-k 200 --property-open-upper-k 2000 --workers 1 --output-dir tmp/buy-2024-only-v4.21/calibration`
  - `bash input-data-versions/validate.sh v4.21 --output-dir tmp/buy-2024-only-v4.21/validation/v4.21 --workers 20`
- Expected result snippet:
  - `BUY_SCALE = 4.3957479837`
  - `BUY_EXPONENT = 1`
  - `BUY_MU = 0`
  - `BUY_SIGMA = 0.2`
  - `source_year_psd = 2024`
  - `source_year_ppd = 2024`
  - `ppd_2025_loaded = 0`
  - hard BUY calibration guardrails passed.
  - Tracked validation summary generated on `2026-05-12T18:56:44Z` with `overallCompositeLoss=0.573916720919496`, improved from `v4.20=0.6045043981851204` by `-0.03058767726562439`.
  - HPI Mean metric loss improves from `0.4671213798746696` to `0.29732111653870075`.
  - HPI Std metric loss improves from `1.4987466529102156` to `0.2561351239522241`.
  - HPI Cycle Period metric loss worsens from `0.5373901292495852` to `0.794483541872788`.
  - Combined HPI metric loss improves from `2.5032581620344705` to `1.347939782363713`.
- Method chosen:
  - Clone `v4.20` to `v4.21` and update only `BUY_SCALE`, `BUY_EXPONENT`, `BUY_MU`, and `BUY_SIGMA`.
  - Use the true `2024_only` BUY path: PSD 2024 property-value bands, PPD 2024 status-A transaction prices, PSD-raked PPD log-price quantiles, `BUY_MU=0`, fixed primary `BUY_EXPONENT=1.0`, and estimated `BUY_SCALE`/`BUY_SIGMA`.
  - Keep raw private PSD/PPD rows out of tracked evidence; retain only derived row counts, source-year checks, guardrail diagnostics, selected parameters, and quantile residuals under `input-data-versions/calibration-evidence/buy-2024-only-v4.21/`.
- Method-selection decision logic:
  - `Objective=forced source-year correction; Why=the selected candidate removes 2025 and pooled-year dependence from the current BUY calibration and passes hard BUY guardrails; Tradeoff=overall and combined HPI validation losses improve, but HPI Cycle Period regresses, so this forced promotion is not a clean all-HPI-component model improvement.`
- Rationale category:
  - forced source-fidelity correction
- Evidence links:
  - `input-data-versions/calibration-evidence/buy-2024-only-v4.21/README.md`
  - `input-data-versions/calibration-evidence/buy-2024-only-v4.21/PsdBuyBudgetCalibrationV421.csv`
  - `input-data-versions/calibration-evidence/buy-2024-only-v4.21/PsdBuyBudgetCalibrationV421Summary.json`
  - `input-data-versions/validation/v4.21.json`
- Version(s) affected:
  - `v4.21`

### v4.22
- Script path: `N/A (direct official-policy source confirmation)`
- Outputs/keys produced:
  - `GOVERNMENT_GENERAL_PERSONAL_ALLOWANCE`
- Exact run command:
  - `curl -L -o input-data-versions/calibration-evidence/gov-personal-allowance-v4.22/spring-budget-2024-annex-a-rates-and-allowances.html https://www.gov.uk/government/publications/spring-budget-2024-overview-of-tax-legislation-and-rates-ootlar/annex-a-rates-and-allowances`
  - `bash input-data-versions/validate.sh v4.22 --output-dir tmp/validation/v4.22 --workers 20`
- Expected result snippet:
  - GOV.UK Spring Budget 2024 Annex A, Income Tax allowances, Personal allowance for tax year 2024 to 2025: `12570`.
  - `GOVERNMENT_GENERAL_PERSONAL_ALLOWANCE = 12570.0`
  - Tracked validation summary generated on `2026-05-12T20:11:01Z` with `overallCompositeLoss=0.573916720919496`, unchanged from `v4.21`.
  - Status changes versus `v4.21`: none.
- Method chosen:
  - Clone `v4.21` to `v4.22` and update only the `GOVERNMENT_GENERAL_PERSONAL_ALLOWANCE` config provenance comments.
  - Use the official 2024/25 GOV.UK Spring Budget Annex A Personal Allowance row directly; no statistical fitting.
  - Retained artifact: `input-data-versions/calibration-evidence/gov-personal-allowance-v4.22/spring-budget-2024-annex-a-rates-and-allowances.html`.
- Method-selection decision logic:
  - `Objective=source-year fidelity; Why=the 2024 baseline should cite the 2024/25 policy period instead of future-year 2025/26 wording even though the value is unchanged; Tradeoff=this improves provenance but does not change simulation output.`
- Rationale category:
  - source-fidelity correction
- Evidence links:
  - `https://www.gov.uk/government/publications/spring-budget-2024-overview-of-tax-legislation-and-rates-ootlar/annex-a-rates-and-allowances`
  - `input-data-versions/calibration-evidence/gov-personal-allowance-v4.22/README.md`
  - `input-data-versions/calibration-evidence/gov-personal-allowance-v4.22/GovPersonalAllowanceV422SourceValues.csv`
  - `input-data-versions/calibration-evidence/gov-personal-allowance-v4.22/GovPersonalAllowanceV422Summary.json`
  - `input-data-versions/validation/v4.22.json`
- Version(s) affected:
  - `v4.22`

### v4.23
- Script path: `N/A (direct official-policy source confirmation)`
- Outputs/keys produced:
  - `GOVERNMENT_INCOME_LIMIT_FOR_PERSONAL_ALLOWANCE`
- Exact run command:
  - `curl -L -o input-data-versions/calibration-evidence/gov-personal-allowance-income-limit-v4.23/spring-budget-2024-annex-a-rates-and-allowances.html https://www.gov.uk/government/publications/spring-budget-2024-overview-of-tax-legislation-and-rates-ootlar/annex-a-rates-and-allowances`
  - `bash input-data-versions/validate.sh v4.23 --output-dir tmp/validation/v4.23 --workers 20`
- Expected result snippet:
  - GOV.UK Spring Budget 2024 Annex A, Income Tax allowances, Income limit for Personal Allowance for tax year 2024 to 2025: `100000`.
  - `GOVERNMENT_INCOME_LIMIT_FOR_PERSONAL_ALLOWANCE = 100000.0`
  - Tracked validation summary generated on `2026-05-12T20:12:19Z` with `overallCompositeLoss=0.573916720919496`, unchanged from `v4.22`.
  - Status changes versus `v4.22`: none.
- Method chosen:
  - Clone `v4.22` to `v4.23` and update only the `GOVERNMENT_INCOME_LIMIT_FOR_PERSONAL_ALLOWANCE` config provenance comments.
  - Use the official 2024/25 GOV.UK Spring Budget Annex A Income limit for Personal Allowance row directly; no statistical fitting.
  - Retained artifact: `input-data-versions/calibration-evidence/gov-personal-allowance-income-limit-v4.23/spring-budget-2024-annex-a-rates-and-allowances.html`.
- Method-selection decision logic:
  - `Objective=source-year fidelity; Why=the 2024 baseline should cite the 2024/25 policy period instead of future-year 2025/26 wording even though the value is unchanged; Tradeoff=this improves provenance but does not change simulation output.`
- Rationale category:
  - source-fidelity correction
- Evidence links:
  - `https://www.gov.uk/government/publications/spring-budget-2024-overview-of-tax-legislation-and-rates-ootlar/annex-a-rates-and-allowances`
  - `input-data-versions/calibration-evidence/gov-personal-allowance-income-limit-v4.23/README.md`
  - `input-data-versions/calibration-evidence/gov-personal-allowance-income-limit-v4.23/GovPersonalAllowanceIncomeLimitV423SourceValues.csv`
  - `input-data-versions/calibration-evidence/gov-personal-allowance-income-limit-v4.23/GovPersonalAllowanceIncomeLimitV423Summary.json`
  - `input-data-versions/validation/v4.23.json`
- Version(s) affected:
  - `v4.23`

### v4.24
- Script path: `N/A (direct official-policy source confirmation)`
- Outputs/keys produced:
  - `DATA_TAX_RATES`
- Exact run command:
  - `curl -L -o input-data-versions/calibration-evidence/gov-income-tax-rates-v4.24/income-tax-rates-and-allowances-current-and-past.html https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past`
  - `bash input-data-versions/validate.sh v4.24 --output-dir tmp/validation/v4.24 --workers 20`
- Expected result snippet:
  - GOV.UK Income Tax rates and allowances, England, Northern Ireland and Wales, tax year 2024 to 2025: Basic rate `20%` up to `37700`, Higher rate `40%` from `37701` to `125140`, Additional rate `45%` over `125140`.
  - `TaxRates.csv` rows: `0, 0.20`; `37700, 0.40`; `125140, 0.45`.
  - Tracked validation summary generated on `2026-05-12T20:14:13Z` with `overallCompositeLoss=0.573916720919496`, unchanged from `v4.23`.
  - Status changes versus `v4.23`: none.
- Method chosen:
  - Clone `v4.23` to `v4.24` and update only `TaxRates.csv` comments plus the directly related `DATA_TAX_RATES` config provenance comments.
  - Use the official 2024/25 England/Wales/Northern Ireland main-rate table directly. The model applies Personal Allowance separately, so the CSV stores taxable-income band starts after allowance.
  - Retained artifact: `input-data-versions/calibration-evidence/gov-income-tax-rates-v4.24/income-tax-rates-and-allowances-current-and-past.html`.
  - Documented caveat: the current model has one tax table and does not encode separate Scottish Income Tax bands.
- Method-selection decision logic:
  - `Objective=source-year fidelity; Why=the 2024 baseline should cite the 2024/25 policy period instead of future-year 2025/26 wording even though the England/Wales/Northern Ireland main-rate rows are unchanged; Tradeoff=this improves provenance but retains the existing single-table Scottish-rate limitation.`
- Rationale category:
  - source-fidelity correction
- Evidence links:
  - `https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past`
  - `input-data-versions/calibration-evidence/gov-income-tax-rates-v4.24/README.md`
  - `input-data-versions/calibration-evidence/gov-income-tax-rates-v4.24/GovIncomeTaxRatesV424SourceValues.csv`
  - `input-data-versions/calibration-evidence/gov-income-tax-rates-v4.24/GovIncomeTaxRatesV424Summary.json`
  - `input-data-versions/validation/v4.24.json`
- Version(s) affected:
  - `v4.24`

### v4.25
- Script path: `N/A (direct official-policy source update)`
- Outputs/keys produced:
  - `DATA_NATIONAL_INSURANCE_RATES`
- Exact run command:
  - `curl -L -o input-data-versions/calibration-evidence/gov-ni-class1-employee-v4.25/rates-and-thresholds-for-employers-2024-to-2025.html https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2024-to-2025`
  - `bash input-data-versions/validate.sh v4.25 --output-dir tmp/validation/v4.25 --workers 20`
- Expected result snippet:
  - GOV.UK Rates and thresholds for employers 2024 to 2025: annual Primary Threshold `12570`, annual Upper Earnings Limit `50270`, Class 1 employee category A rate `8%` above PT to UEL, and `2%` above UEL.
  - `NationalInsuranceRates.csv` rows changed from `12584, 0.12`; `50284, 0.02` to `12570, 0.08`; `50270, 0.02`.
  - Tracked validation summary generated on `2026-05-12T20:15:28Z` with `overallCompositeLoss=0.5780636756491524`, versus `v4.24=0.573916720919496`.
  - Status changes versus `v4.24`: `HPI Std` warning to fail.
- Method chosen:
  - Clone `v4.24` to `v4.25` and update only `NationalInsuranceRates.csv` plus the directly related `DATA_NATIONAL_INSURANCE_RATES` config provenance comments.
  - Use the official annual 2024/25 Class 1 employee Category A thresholds because the model applies this table to annual gross income.
  - Retained artifact: `input-data-versions/calibration-evidence/gov-ni-class1-employee-v4.25/rates-and-thresholds-for-employers-2024-to-2025.html`.
- Method-selection decision logic:
  - `Objective=source-year fidelity and unit consistency; Why=the prior table retained a stale 12% main rate and 52-times-weekly thresholds while the model consumes annual income; Tradeoff=the tracked 2024 composite worsens modestly and HPI Std moves from warning to failing, but the policy input is more accurate for 2024/25.`
- Rationale category:
  - source-fidelity correction
- Evidence links:
  - `https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2024-to-2025`
  - `input-data-versions/calibration-evidence/gov-ni-class1-employee-v4.25/README.md`
  - `input-data-versions/calibration-evidence/gov-ni-class1-employee-v4.25/GovNationalInsuranceRatesV425SourceValues.csv`
  - `input-data-versions/calibration-evidence/gov-ni-class1-employee-v4.25/GovNationalInsuranceRatesV425Summary.json`
  - `input-data-versions/validation/v4.25.json`
- Version(s) affected:
  - `v4.25`

### v4.26
- Script path: `scripts/python/calibration/official/gov_income_support_2024.py`
- Outputs/keys produced:
  - `GOVERNMENT_MONTHLY_INCOME_SUPPORT`
- Exact run command:
  - `curl -L -o input-data-versions/calibration-evidence/gov-income-support-v4.26/benefit-and-pension-rates-2024-to-2025.html https://www.gov.uk/government/publications/benefit-and-pension-rates-2024-to-2025/benefit-and-pension-rates-2024-to-2025`
  - `bash input-data-versions/validate.sh v4.26 --output-dir tmp/validation/v4.26 --workers 20`
- Expected result snippet:
  - GOV.UK Benefit and pension rates 2024 to 2025, Income Support, `Both 18 or over`, `Rates 2024/25`: `142.25` weekly.
  - `GOVERNMENT_MONTHLY_INCOME_SUPPORT = 142.25 * 52 / 12 = 616.4166666667`.
  - Tracked validation summary generated on `2026-05-12T20:17:27Z` with `overallCompositeLoss=0.5780636756491524`, unchanged from `v4.25`.
  - Status changes versus `v4.25`: none.
- Method chosen:
  - Clone `v4.25` to `v4.26` and update only the `GOVERNMENT_MONTHLY_INCOME_SUPPORT` config provenance comment to point at a v4.26-local evidence bundle.
  - Retain the already-correct v4.13-selected value, but download and store a distinct v4.26 GOV.UK artifact so this version is self-contained.
  - Do not carry forward the stale live `src/main/resources` value `578.6`.
  - Retained artifact: `input-data-versions/calibration-evidence/gov-income-support-v4.26/benefit-and-pension-rates-2024-to-2025.html`.
- Method-selection decision logic:
  - `Objective=source-year fidelity and unit consistency; Why=the model annualizes the monthly value by multiplying by 12, so the weekly rate should be converted with 52/12; Tradeoff=this improves self-contained provenance but does not change simulation output relative to v4.25.`
- Rationale category:
  - source-fidelity correction
- Evidence links:
  - `https://www.gov.uk/government/publications/benefit-and-pension-rates-2024-to-2025/benefit-and-pension-rates-2024-to-2025`
  - `input-data-versions/calibration-evidence/gov-income-support-v4.26/README.md`
  - `input-data-versions/calibration-evidence/gov-income-support-v4.26/GovIncomeSupportV426SourceValues.csv`
  - `input-data-versions/calibration-evidence/gov-income-support-v4.26/GovIncomeSupportV426Summary.json`
  - `input-data-versions/validation/v4.26.json`
- Version(s) affected:
  - `v4.26`

### v5.0o1
- Script path:
  - `scripts/python/calibration/output/output_parameter_esmda.py`
  - historical compatibility entrypoint retained: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_PROBABILITY_MULTIPLIER`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
- Exact run command:
  - `python3 -m scripts.python.calibration.output.output_parameter_esmda --version v4.26 --output-version v5.0o1 --validation-year 2024 --validation-objective family_aware_metric_loss --validation-loss-error-std 1.0 --seeds 1,2,3,4,5,6,7,8,9,10 --workers 20 --ensemble-size 32 --assimilation-steps 4 --rng-seed 20260518 --n-steps 3500 --validation-window-start 500 --validation-window-end 3500 --output-root tmp/output-calibration --evidence-dir input-data-versions/calibration-evidence/output-five-parameter-esmda-v5.0o1 --delete-csv-after-metrics --local-refinement-top-n 10 --local-refinement-radius 1 --local-refinement-max-candidates 100`
  - `bash input-data-versions/validate.sh v5.0o1 --output-dir tmp/validation/v5.0o1 --workers 20`
- Expected result snippet:
  - Automated `createdOutputVersion = false`; no snapped local-refinement candidate was promoted because every snapped candidate with better aggregate loss regressed HPI constraints.
  - Manual override promoted global ES-MDA iteration `3`, member `7`, which passed HPI-constrained eligibility.
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.25`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.0014`
  - `BTL_PROBABILITY_MULTIPLIER = 1.825`
  - `BTL_CHOICE_INTENSITY = 100`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.5`
  - Campaign loss improved from baseline `v4.26` `0.5743372296753784` to `0.5073951690442934` (delta `-0.06694206063108499`, `-11.655532%`).
  - Campaign status counts changed from `pass=6`, `warn=0`, `fail=14` to `pass=7`, `warn=2`, `fail=11`.
  - Promoted HPI constrained metric deltas improved: `core_hpiMean=-0.08827660090626732`, `core_hpiStd=-0.046577414707801135`, `core_hpiCyclePeriod=-0.0818447984939259`.
  - Tracked 2024 validation summary generated on `2026-05-19T09:21:05Z` with `overallCompositeLoss=0.5501176226064236` versus current `v4.26=0.5743372296753784` (delta `-0.024219607068954763`, `-4.216966%`).
  - Tracked 2024 validation status counts changed from `pass=6`, `warn=0`, `fail=14` to `pass=7`, `warn=0`, `fail=13`.
- Method chosen:
  - Five-parameter ES-MDA output calibration against the 2024 validation profile using the schema-v4 `family_aware_metric_loss` objective and `schema4_metric_loss` assimilation transform.
  - The campaign jointly varied `PSYCHOLOGICAL_COST_OF_RENTING`, `SENSITIVITY_RENT_OR_PURCHASE`, `BTL_PROBABILITY_MULTIPLIER`, `BTL_CHOICE_INTENSITY`, and `MARKET_AVERAGE_PRICE_DECAY` from source snapshot `v4.26`.
  - The global pass used seeds `1..10`, `20` workers, ensemble size `32`, `4` assimilation steps, `N_STEPS = 3500`, validation/calibration window `500..3500`, rng seed `20260518`, and snapped local refinement with top-n `10`, radius `1`, and max candidates `100`.
  - Manual override promoted the HPI-constrained global candidate iteration `3`, member `7` after the snapped local-refinement promotion path rejected all candidates.
- Guardrail decision logic:
  - The automated promotion guardrail rejected the snapped local-refinement path and did not create `v5.0o1`.
  - The manual promotion is limited to the global candidate that both improved aggregate campaign loss and improved all HPI constrained metrics relative to `v4.26`.
- Method-selection decision logic:
  - `Objective=2024 family-aware validation fit; Why=the promoted global ES-MDA member materially reduces aggregate loss and improves HPI mean, standard deviation, and cycle-period losses versus v4.26; Tradeoff=this is a manual override because the snapped local-refinement stage found no promotable candidate, so the retained evidence must distinguish the promoted global member from the rejected local-refinement candidates.`
- Rationale category:
  - output calibration manual override
- Evidence links:
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5.0o1/AllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5.0o1/LocalRefinementMembers.csv`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5.0o1/OutputParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5.0o1/ManualPromotionOverride.md`
  - `input-data-versions/validation/v5.0o1.json`
- Version(s) affected:
  - `v5.0o1`

### v5o2
- Script path:
  - `scripts/python/calibration/output/output_parameter_esmda.py`
  - historical compatibility entrypoint retained: `scripts/python/calibration/output/four_parameter_esmda.py`
- Outputs/keys produced:
  - `PSYCHOLOGICAL_COST_OF_RENTING`
  - `SENSITIVITY_RENT_OR_PURCHASE`
  - `BTL_PROBABILITY_MULTIPLIER`
  - `BTL_CHOICE_INTENSITY`
  - `MARKET_AVERAGE_PRICE_DECAY`
- Exact run command:
  - Source campaign member: `tmp/output-calibration/v5.0o1/five-parameter-esmda/runs/iter-03/member-007`
  - `python3 -m scripts.python.validation.model.validate_input_data_version --version v5o2 --seeds 1,2,3,4,5,6,7,8,9,10 --workers 20 --output-dir tmp/validation/v5o2-10seed-3500 --n-steps 3500 --validation-window-start 500 --validation-window-end 3500 --allow-noncanonical-seeds`
- Expected result snippet:
  - Manual override promoted exact raw cached v5.0o1 campaign iteration `3`, member `7`.
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.25061702205009445`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.0014183438663974938`
  - `BTL_PROBABILITY_MULTIPLIER = 1.8268011822613688`
  - `BTL_CHOICE_INTENSITY = 100.67982683612807`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.5064990858425684`
  - 10-seed 2024 overallCompositeLoss improved from rescored `v4.26=0.6137234580996009` to `v5o2=0.591986974767631` (delta `-0.02173648333196989`, `-3.541739%`).
  - HPI metric-loss deltas versus `v4.26`: `core_hpiMean=-0.008146536511386848`, `core_hpiStd=+0.11241424289324455`, `core_hpiCyclePeriod=-0.10180994493677498`.
- Method chosen:
  - Manual promotion of a cached five-parameter ES-MDA candidate from the `v5.0o1` campaign, using exact raw member parameters rather than rounded `v5.0o1` snapshot values.
  - Fresh validation used seeds `1..10`, `20` workers, `N_STEPS = 3500`, and validation window `500..3500`.
- Method-selection decision logic:
  - `Objective=2024 validation loss reduction; Why=the selected member improves aggregate 2024 loss and core_hpiCyclePeriod loss versus v4.26; Tradeoff=core_hpiStd loss worsens in fresh validation, so this is validation-loss evidence rather than a broad model-output improvement.`
- Rationale category:
  - output calibration manual override
- Evidence links:
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5o2/SourceAllEvaluatedMembers.csv`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5o2/SourceOutputParameterEsmdaCalibrationSummary.json`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5o2/ManualPromotionOverride.md`
  - `input-data-versions/calibration-evidence/output-five-parameter-esmda-v5o2/ValidationComparison-v5o2-vs-v4.26-2024-10seed-500-3500.csv`
  - `input-data-versions/validation/v5o2.json`
- Version(s) affected:
  - `v5o2`
