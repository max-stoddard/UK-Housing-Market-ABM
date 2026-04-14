# Calibration Parameter Changelog
Author: Max Stoddard

## Purpose And Maintenance Rule
This is the canonical calibration provenance ledger for Python-driven and related parameter updates.

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

## Current Reproducible Commands (Latest Baseline: `input-data-versions/v4.0`)

### `scripts/python/calibration/was/age_dist.py`
- Outputs/keys produced:
  - `Age8-R8-Weighted.csv`
- Command:
```bash
python3 -m scripts.python.calibration.was.age_dist --dataset R8 --output-dir input-data-versions/v3.6
```
- Expected-result snippet:
  - file exists: `input-data-versions/v3.6/Age8-R8-Weighted.csv`
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
python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search \
  private-datasets/nmg/nmg-2014.csv \
  private-datasets/nmg/nmg-2016.csv \
  private-datasets/nmg/nmg-2018.csv \
  private-datasets/nmg/nmg-2019.csv \
  private-datasets/nmg/nmg-2020.csv \
  private-datasets/nmg/nmg-2021.csv \
  private-datasets/nmg/nmg-2022.csv \
  private-datasets/nmg/nmg-2023.csv \
  private-datasets/nmg/nmg-2024.csv \
  private-datasets/ppd/pp-2011.csv \
  private-datasets/ppd/pp.2012.csv \
  private-datasets/ppd/pp-2018.csv \
  private-datasets/ppd/pp-2019.csv \
  private-datasets/ppd/pp-2020.csv \
  private-datasets/ppd/pp-2021.csv \
  private-datasets/ppd/pp-2022.csv \
  private-datasets/ppd/pp-2023.csv \
  private-datasets/ppd/pp-2024.csv \

python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit \
  private-datasets/nmg/nmg-2018.csv \
  private-datasets/nmg/nmg-2019.csv \
  private-datasets/nmg/nmg-2020.csv \
  private-datasets/nmg/nmg-2021.csv \
  private-datasets/nmg/nmg-2022.csv \
  private-datasets/nmg/nmg-2023.csv \
  private-datasets/nmg/nmg-2024.csv \
  --ppd \
  private-datasets/ppd/pp-2011.csv \
  private-datasets/ppd/pp.2012.csv \
  private-datasets/ppd/pp-2018.csv \
  private-datasets/ppd/pp-2019.csv \
  private-datasets/ppd/pp-2020.csv \
  private-datasets/ppd/pp-2021.csv \
  private-datasets/ppd/pp-2022.csv \
  private-datasets/ppd/pp-2023.csv \
  private-datasets/ppd/pp-2024.csv \
  --target-year 2024
```
- Expected-result snippet:
  - revised production winner:
    - `survey-method: midpoint_exact`
    - `signal-method: annual_mean_annualised`
    - `category-types: A`
    - `plausibility: admissible`
    - `fit-rmse: 0.0121267301`
    - `HPA_EXPECTATION_FACTOR = 0.1150752545`
    - `HPA_EXPECTATION_CONST = 0.0034084162`
  - rejected all-transactions comparison:
    - `plausibility: inadmissible`
    - `factor = -0.0919792144`
    - `const = 0.0104582814`
  - strict `2020` to `2024` sensitivity:
    - `survey-method: midpoint_exact`
    - `factor = 0.0535966141`
    - `const = 0.0092043687`
- Method chosen:
  - `Category A` only + `annual_mean_annualised` + `midpoint_exact` over the `2018` to `2024` NMG window
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the revised production surface ranks admissible before inadmissible, then preferred-band status, in-window RMSE, and simplicity, and the real-data all-transactions comparison stayed inadmissible while the Category A fit remained positive and admissible; Tradeoff=the winning fit is admissible but outside the preferred factor band, and the earliest modern anchors still rely on fallback historical bases.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  - `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
  - `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md`
- Version(s) affected:
  - `v4.2`

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

## Per-Version Changelog Entries (Append-Only)

### v1.0
- Script path: `scripts/python/calibration/was/income_age_joint_prob_dist.py`
- Outputs/keys produced: `AgeGrossIncomeJointDist.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.income_age_joint_prob_dist --dataset R8 --output-dir input-data-versions/v1.0`
- Expected result snippet: output file generated with weighted age-income density rows.
- Method chosen: weighted log-income by age joint distribution with positive-and-trimmed income filtering.
- Method-selection decision logic: `Objective=stability/robustness; Why=positive filtering and tail trimming stabilize bin estimates; Tradeoff=extreme tails are removed from calibration support.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/was/age_gross_income_joint_dist_comparison.py`
- Version(s) affected: `v1.0`

### v1.1
- Script path: `scripts/python/calibration/was/wealth_income_joint_prob_dist.py`
- Outputs/keys produced: `GrossIncomeNetWealthJointDist.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.wealth_income_joint_prob_dist --dataset R8 --output-dir input-data-versions/v1.1`
- Expected result snippet: `GrossIncomeNetWealthJointDist.csv` generated.
- Method chosen: weighted joint distribution for gross income vs net wealth in log space.
- Method-selection decision logic: `Objective=stability/robustness; Why=positive wealth constraints and filtered income support stable log-space joint densities; Tradeoff=non-positive wealth rows are excluded.`
- Rationale category: alteration-vs-legacy evidence and justification.
- Evidence links: `scripts/python/experiments/was/gross_income_net_wealth_joint_dist_comparison.py`
- Version(s) affected: `v1.1`

### v1.2
- Script path: `scripts/python/calibration/was/btl_probability_per_income_percentile_bin.py`
- Outputs/keys produced: `BTLProbabilityPerIncomePercentileBin-R8.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.btl_probability_per_income_percentile_bin --dataset R8`
- Expected result snippet: 100 percentile-bin rows plus BTL probability values.
- Method chosen: percentile binning over gross non-rent income and rental-income positivity as BTL marker.
- Method-selection decision logic: `Objective=target reproduction; Why=direct percentile-bin estimator aligns with required output table shape; Tradeoff=keeps a simple semantic indicator instead of model-heavy inference.`
- Rationale category: direct method justification.
- Evidence links: `scripts/python/experiments/was/btl_probability_per_income_percentile_comparison.py`
- Version(s) affected: `v1.2`

### v1.3
- Script path: `scripts/python/calibration/was/age_dist.py`
- Outputs/keys produced: `Age8-R8-Weighted.csv`
- Exact run command: `python3 -m scripts.python.calibration.was.age_dist --dataset R8`
- Expected result snippet: final bin uses `75-95` compatibility convention.
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
- Evidence links: `input-data-versions/version-notes.json`
- Version(s) affected: `v2.0`

### v2.1
- Script path: `N/A (manual source-data update)`
- Outputs/keys produced: `DATA_TAX_RATES`
- Exact run command: `N/A (manual update from public tax-rate table source)`
- Expected result snippet: `TaxRates.csv` updated and referenced in config.
- Method chosen: direct table update from source data.
- Method-selection decision logic: `Objective=target reproduction; Why=tax bands/rates are direct-source values and should not be statistically fitted; Tradeoff=depends on source table update cadence.`
- Rationale category: direct method justification.
- Evidence links: `input-data-versions/version-notes.json`
- Version(s) affected: `v2.1`

### v2.2
- Script path: `scripts/python/experiments/was/personal_allowance.py`
- Outputs/keys produced: `GOVERNMENT_GENERAL_PERSONAL_ALLOWANCE` policy choice context
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
  - `input-data-versions/version-notes.json`
- Version(s) affected: `v3.8`

### v4.0: BUY v2 Modern Realism Workflow
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

### HPA Expectation `v4.2` Production Calibration
- Script path: `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Companion experiment path: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Helper paths:
  - `scripts/python/helpers/nmg/hpa_expectation.py`
  - `scripts/python/helpers/ppd/hpa_signal_methods.py`
- Outputs/keys produced: `HPA_EXPECTATION_FACTOR`, `HPA_EXPECTATION_CONST`
- Exact run command:
  - `python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search private-datasets/nmg/nmg-2014.csv private-datasets/nmg/nmg-2016.csv private-datasets/nmg/nmg-2018.csv private-datasets/nmg/nmg-2019.csv private-datasets/nmg/nmg-2020.csv private-datasets/nmg/nmg-2021.csv private-datasets/nmg/nmg-2022.csv private-datasets/nmg/nmg-2023.csv private-datasets/nmg/nmg-2024.csv private-datasets/ppd/pp-2011.csv private-datasets/ppd/pp.2012.csv private-datasets/ppd/pp-2018.csv private-datasets/ppd/pp-2019.csv private-datasets/ppd/pp-2020.csv private-datasets/ppd/pp-2021.csv private-datasets/ppd/pp-2022.csv private-datasets/ppd/pp-2023.csv private-datasets/ppd/pp-2024.csv`
  - `python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit private-datasets/nmg/nmg-2018.csv private-datasets/nmg/nmg-2019.csv private-datasets/nmg/nmg-2020.csv private-datasets/nmg/nmg-2021.csv private-datasets/nmg/nmg-2022.csv private-datasets/nmg/nmg-2023.csv private-datasets/nmg/nmg-2024.csv --ppd private-datasets/ppd/pp-2011.csv private-datasets/ppd/pp.2012.csv private-datasets/ppd/pp-2018.csv private-datasets/ppd/pp-2019.csv private-datasets/ppd/pp-2020.csv private-datasets/ppd/pp-2021.csv private-datasets/ppd/pp-2022.csv private-datasets/ppd/pp-2023.csv private-datasets/ppd/pp-2024.csv --target-year 2024`
- Expected result snippet:
  - `survey-method: midpoint_exact`
  - `signal-method: annual_mean_annualised`
  - `category-types: A`
  - `plausibility: admissible`
  - `HPA_EXPECTATION_FACTOR = 0.1150752545`
  - `HPA_EXPECTATION_CONST = 0.0034084162`
- Method chosen:
  - `Category A` only + `annual_mean_annualised` + `midpoint_exact`
- Method-selection decision logic:
  - `Objective=direct method justification; Why=the revised Category A production surface produced an admissible positive-factor fit while the all-transactions comparison remained inadmissible at factor=-0.0919792144 and const=0.0104582814; Tradeoff=the winning fit remains outside the preferred factor band and depends on fallback historical bases for the earliest modern anchors.`
- Rationale category:
  - alteration-vs-legacy evidence and justification
- Evidence links:
  - `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  - `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
  - `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md`
- Version(s) affected:
  - `v4.2`
