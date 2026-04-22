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

## Current Reproducible Commands (Latest Baseline: `input-data-versions/v4.10`)

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
