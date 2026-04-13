# 2024 Validation Framework Redesign

**Author:** Max Stoddard
**Date:** 2026-04-13
**Status:** Approved
**Scope:** `scripts/python/validation/`, `scripts/python/helpers/common/`, `input-data-versions/`, `dashboard/server/`, `dashboard/src/`, `dashboard/shared/`

## Problem

The current validation flow is not strong enough for a 2024-focused housing-market recalibration campaign.

Current weaknesses:
- it relies on a single model run
- it reduces validation to three legacy WAS metrics
- it uses a weak scalar loss on those three values only
- it does not show seed robustness
- it does not make broad use of the model's existing core indicators
- the dashboard validation page is tightly coupled to the old three-metric schema in `input-data-versions/version-notes.json`

This is a bad fit for the current project goal: showing that successive input-data versions move the model closer to the actual state of the UK housing market in 2024.

## Goals

- Replace the legacy three-metric validation system with one permanent validation framework.
- Validate every input-data version against 2024 target data so calibration progress is comparable across versions.
- Treat macro realism and household-distribution realism as equally important.
- Build robustness into validation through fixed multi-seed execution.
- Use acceptable target bands rather than single exact targets.
- Produce a scorecard for decision-making and a secondary composite score for ranking and trend visualisation.
- Make the dashboard consume the new framework directly.
- Keep the website uncertainty-aware, but lightweight.

## Non-Goals

- Building multiple competing validation methodologies.
- Preserving the old three-metric loss in the UI.
- Treating one-seed validation as a supported path.
- Turning the dashboard into a heavy research notebook.
- Recomputing validation logic inside the frontend.

## Design Summary

The new framework is a family-based scorecard with a secondary composite score.

Core rules:
- every input-data version is evaluated against 2024 targets
- canonical validation uses fixed seeds `1..8`
- target definitions are acceptable bands
- the scorecard is the primary decision tool
- the composite score is a secondary summary and ranking tool
- robustness is part of validity, not a separate optional diagnostic

The framework is organised into fixed validation families:
- macro credit and market activity
- macro prices, leverage, and affordability
- household distribution realism
- stochastic robustness

The first three families are the scored realism families. Stochastic robustness is a cross-cutting family: it is displayed explicitly in the scorecard, but it acts mainly through penalties and stability summaries applied across the scored families.

The website uses the new framework only. The old three-metric validation trend is removed rather than shown side by side.

## Validation Families

### Family 1: Macro Credit And Market Activity

Purpose:
- test whether the model reproduces the aggregate lending and transaction picture of the 2024 housing market

Initial metric set:
- mortgage approvals
- housing transactions
- advances to first-time buyers
- advances to home movers
- advances to buy-to-let

Primary target source:
- FPC or other official 2024 macro indicator releases where mapping is clean

### Family 2: Macro Prices, Leverage, And Affordability

Purpose:
- test whether the model reproduces 2024 market conditions, leverage, and affordability pressures

Initial metric set:
- mortgage debt to income
- owner-occupier debt to income if target mapping is reliable
- price to income
- house price growth
- rental yield when target mapping is strong enough
- mortgage interest rate spread when target mapping is strong enough

Primary target source:
- FPC/core-indicator style releases first, with other official 2024 series allowed where needed

### Family 3: Household Distribution Realism

Purpose:
- prevent a version from looking good on headline aggregates while remaining unrealistic at the household level

Initial metric set:
- household income distribution realism
- housing wealth distribution realism
- financial wealth distribution realism

Allowed extensions when supported by defensible 2024 targets:
- tenure composition
- borrower-type composition
- other household realism checks tied to specific external evidence

Primary target source:
- best available external 2024-compatible household evidence, which may be different from FPC macro sources

Initial locked source for this framework:
- `WAS Round 8` is the starting household-realism source for the permanent framework because it is already integrated into the project and is the current household evidence base used during recalibration
- replacing this source later is a methodology change, not a casual implementation detail

### Family 4: Stochastic Robustness

Purpose:
- make seed stability part of the validation result rather than an informal afterthought

Initial metric set:
- fraction of seeds inside target band
- seed spread for each metric
- family-level instability penalties derived from metric-level seed variation

This family is not independent of the others. It is computed from the same 8-seed runs and explicitly penalises fragile versions. It is therefore a cross-cutting family in the methodology rather than a fourth equally weighted realism block.

## Metric Semantics

Each validation metric produces both a fit assessment and a robustness assessment.

For each metric and version:
1. run seeds `1..8`
2. compute the seed mean
3. compute a lightweight uncertainty summary
4. compare the seed mean against the 2024 target band
5. compute a metric status and metric score

Required uncertainty summary:
- seed mean
- interquartile band (`p25` to `p75`)
- fraction of seeds inside the target band

These are lightweight enough for the website and strong enough to expose fragile improvements.

Macro metric scalar extraction rule:
- for each seed and each macro metric, read the model output series
- select the canonical post-burn-in window covering periods `200:2000`
- compute the arithmetic mean over that window
- compare that mean to the 2024 target band

Household-distribution scalar extraction rule:
- for each seed and each household realism metric, build the model-side histogram using the same filtering and fixed-bin approach used by the current WAS validation modules
- normalize the model histogram and external target histogram to unit mass
- compute Jensen-Shannon distance between the two probability distributions
- compare that distance to the metric's acceptance band

## Target Bands

Targets are defined as acceptable bands, not single values.

Each metric definition must include:
- metric id
- family id
- 2024 source attribution
- lower bound
- upper bound
- units
- whether the metric is required or diagnostic-only

Band semantics:
- inside the band means the metric is meeting the 2024 target
- outside the band incurs a penalty based on distance from the nearest band edge

The target catalog is methodology, not incidental configuration. Changes to target bands, metric membership, or family weights must be treated as explicit methodology changes.

## Scorecard Logic

Each metric receives a status:
- `pass`
- `warn`
- `fail`
- `unsupported` only when the target definition or required external mapping does not exist

Interpretation:
- `pass`: mean is inside band and seed stability is acceptable
- `warn`: mean is near the band or inside the band with weak robustness
- `fail`: mean is materially outside the band or clearly unstable

The scorecard is the authoritative validation output. It is what a researcher reads first when deciding whether a version is credible.

Exact status rules:
- let `inside_rate = successful_seeds_inside_band / 8`
- let `band_width = upper_bound - lower_bound`
- let `distance_to_band = 0` when `seed_mean` is inside the band, otherwise the absolute gap from the nearest band edge
- let `normalized_distance = distance_to_band / band_width`
- `pass` when `normalized_distance = 0` and `inside_rate >= 0.75`
- `warn` when `normalized_distance <= 0.50` and `inside_rate >= 0.50`, but the metric does not qualify as `pass`
- `fail` otherwise

This makes the status mapping deterministic and testable.

## Composite Score Logic

The composite score exists to support:
- version ranking
- trend visualisation in the dashboard
- quick comparison across many calibration steps

The composite must not replace the scorecard as the decision tool.

Scoring principles:
- score families, not raw indicators, to avoid double-counting correlated metrics
- treat macro realism and household realism as equally important at the top level
- apply instability penalties so fragile one-seed-looking wins are not rewarded

Recommended aggregation:
1. compute per-metric normalized distance-to-band score
2. apply metric-level stability penalty
3. aggregate metrics into family scores
4. aggregate family scores into the overall composite

Exact per-metric loss:
- `inside_rate = successful_seeds_inside_band / 8`
- `band_width = upper_bound - lower_bound`
- `normalized_distance = 0` when `seed_mean` is inside the band, otherwise `distance_to_band / band_width`
- `normalized_iqr = (p75 - p25) / band_width`
- `metric_loss = normalized_distance + 0.25 * normalized_iqr + 0.50 * (1 - inside_rate)`

Exact family aggregation:
- family loss is the arithmetic mean of required member metric losses
- diagnostic-only metrics are shown in the scorecard but do not contribute to the family loss

Exact overall aggregation:
- `overall_composite_loss = 0.25 * macro_credit_activity_loss + 0.25 * macro_prices_leverage_affordability_loss + 0.50 * household_distribution_realism_loss`

Interpretation:
- lower composite loss is better
- `0` is a perfect result
- robustness enters through `normalized_iqr` and `inside_rate`, not through a separate free-floating summary

Top-level weighting:
- macro families together account for half of the composite
- household distribution realism accounts for the other half
- robustness penalties directly modify metric and family scores rather than being given an independent equal top-level weight

Governance rule:
- a strong overall composite must not override a clearly failing critical family

## Distribution Metric Shape

Household-distribution realism metrics are not represented as raw totals. They are represented as distance-based realism metrics against external household data.

Each distribution metric should therefore expose:
- seed-level distance values against the chosen 2024-compatible household target
- a target acceptance band for that distance metric
- the same summary fields as macro metrics: mean, `p25-p75`, fraction of seeds inside band, status, and score

This keeps the framework unified while still allowing distributional validation to remain substantively different from macro aggregate validation.

Initial required household metrics:
- `income_distribution_jsd`
- `housing_wealth_distribution_jsd`
- `financial_wealth_distribution_jsd`

Initial transformation contract:
- use the current household validation filters already embodied in `scripts.python.validation.was`
- keep fixed bin definitions stable within the framework
- normalize model and target histograms before scoring
- use Jensen-Shannon distance as the scalar realism metric for all three required household-distribution checks

## Canonical Workflow

Canonical validation must not switch live resources in `src/main/resources`.

Instead, the workflow uses snapshot-local execution:
- read `input-data-versions/<version>/config.properties`
- rewrite snapshot-local resource paths
- apply validation-specific runtime overrides
- execute the Java model against that version directly
- read outputs from a validation-specific output directory

Canonical command shape:

```bash
python3 -m scripts.python.validation.model.validate_input_data_version \
  --version v4.1 \
  --seeds 1,2,3,4,5,6,7,8 \
  --output-dir tmp/validation/v4.1
```

The default supported mode is the canonical 8-seed run. The framework does not need multiple competing validation modes to be considered valid.

## Validation Script Architecture

Recommended module split:
- one target catalog module for metric definitions and 2024 bands
- one runner module for snapshot-local multi-seed execution
- one extractor/scoring module for metric computation and family aggregation
- one publisher module for writing tracked summary files for the dashboard
- one bulk migration entrypoint for revalidating all input-data versions

Canonical entrypoints:
- `scripts.python.validation.model.validate_input_data_version`
- `scripts.python.validation.model.validate_all_input_data_versions`

The design should reuse existing snapshot-local multi-seed patterns where possible, especially the infrastructure already present in `scripts/python/helpers/common/abm_policy_sweep.py`.

## Output Artifacts

Validation produces two classes of artifacts.

### Transient Run Artifacts

Purpose:
- keep detailed per-seed outputs and intermediate reports for manual checking

Location:
- `tmp/validation/<version>/`

Recommended contents:
- `validation_summary.json`
- `validation_metrics.csv`
- `validation_seed_results.csv`
- `validation_summary.md`
- any optional lightweight diagnostic plots

These files are generated and can be refreshed at any time.

### Tracked Summary Artifacts

Purpose:
- provide stable, lightweight inputs for the dashboard and historical comparison across versions

Location:
- `input-data-versions/validation/<version>.json`

Recommended contents:
- overall composite score
- family scores
- per-metric summaries
- uncertainty summaries
- target-band references
- source attribution
- validation timestamp and seed list

This tracked summary file is the canonical website-facing validation artifact. The dashboard should read these summaries instead of deriving validation from raw `Results/` folders or from legacy fields in `version-notes.json`.

## Input-Data Version Migration

All calibration versions should be re-evaluated under the new 2024 framework so the website can show whether successive recalibration steps move the model closer to the 2024 housing market.

Canonical bulk command shape:

```bash
python3 -m scripts.python.validation.model.validate_all_input_data_versions \
  --versions all \
  --seeds 1,2,3,4,5,6,7,8 \
  --output-root tmp/validation-history
```

Bulk migration responsibilities:
- iterate versions in calibration order
- run canonical 8-seed validation
- write transient artifacts under `tmp/validation-history/`
- publish tracked summary JSON files under `input-data-versions/validation/`

This is how the validation page becomes a calibration-progress page toward the real 2024 market, rather than a static page attached to the old methodology.

## Relationship To `version-notes.json`

`input-data-versions/version-notes.json` remains the provenance and calibration-history ledger.

It should continue to hold:
- version descriptions
- changed parameters
- calibration script references
- method notes

It should stop being the canonical store for validation measurements beyond high-level status hooks if those remain useful.

The new validation framework should not be forced into the old schema of:
- `income_diff_pct`
- `housing_wealth_diff_pct`
- `financial_wealth_diff_pct`

Validation results should live in the dedicated tracked summary files instead.

## Dashboard Design

The dashboard validation page should be redesigned around the new framework as the only validation system.

Required views:
- overall composite trend across versions
- family summary cards
- metric drill-down for a selected version
- lightweight uncertainty presentation

Recommended top-level layout:
- a trend chart for the overall composite score across versions
- a family-status strip or card row for the selected version
- a details table or compact chart grid for individual metrics

Required per-metric display fields:
- metric name
- family
- target band
- multi-seed mean
- `p25-p75` uncertainty band
- fraction of seeds inside band
- status

Lightweight uncertainty rule:
- show mean plus one compact uncertainty band or whisker
- do not build dense per-seed spaghetti plots by default
- keep richer seed detail in tooltips or version detail panes only if needed

## Dashboard Data Flow

Recommended flow:
1. validation scripts publish tracked summary JSON files
2. dashboard server reads those summary files
3. dashboard API exposes composite, family, and metric summary payloads
4. frontend renders summaries without recomputing validation logic

This keeps methodology in one place and avoids drift between script logic and UI logic.

## Error Handling

The framework must fail clearly when a version cannot be honestly compared to the 2024 methodology.

Required failure behavior:
- if a required target band is missing, the metric is not silently ignored
- if a required model output file is missing or malformed, validation fails
- if fewer than all 8 seeds finish successfully, validation fails and no tracked summary artifact is published
- if an optional diagnostic metric lacks a target mapping, it is marked explicitly as diagnostic-only or unsupported

Dashboard behavior:
- unsupported metrics must be visually distinguished from pass/warn/fail metrics
- failed validation publication must not masquerade as a valid low score

Partial-run policy:
- transient debug artifacts may still record which seeds failed
- tracked publishable validation summaries require all `8/8` successful seeds
- the dashboard must only consume publishable tracked summaries

## Verification Strategy

Required automated coverage:
- unit tests for band comparison and normalized distance scoring
- unit tests for stability penalties
- unit tests for family aggregation and overall composite aggregation
- fixture tests for summary JSON generation from synthetic seed outputs
- regression tests for dashboard API payload shape
- one end-to-end validation test on a small known example

Verification focus:
- methodology consistency
- deterministic seed-list handling
- schema stability for the dashboard
- correct handling of missing targets and partial failures

## Planning Constraints

Implementation planning should preserve these decisions:
- fixed canonical seeds are `1..8`
- macro realism and household-distribution realism remain equally important
- target bands remain the core comparison primitive
- the scorecard remains primary and the composite remains secondary
- validation summaries become tracked lightweight artifacts under `input-data-versions/validation/`
- the dashboard uses the new framework only

## Metric Appendix

This appendix locks the initial metric catalog for planning.

### Required Macro Metrics

- `core_mortgageApprovals`
  - family: macro credit and market activity
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_housingTransactions`
  - family: macro credit and market activity
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_advancesToFTB`
  - family: macro credit and market activity
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_advancesToHM`
  - family: macro credit and market activity
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_advancesToBTL`
  - family: macro credit and market activity
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_debtToIncome`
  - family: macro prices, leverage, and affordability
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_priceToIncome`
  - family: macro prices, leverage, and affordability
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required
- `core_housePriceGrowth`
  - family: macro prices, leverage, and affordability
  - source: official 2024 macro indicator target
  - scalar: mean over periods `200:2000`
  - status: required

### Diagnostic Macro Metrics

- `core_ooDebtToIncome`
  - family: macro prices, leverage, and affordability
  - source: official or near-official 2024 target when mapping is strong
  - scalar: mean over periods `200:2000`
  - status: diagnostic-only until mapping is confirmed
- `core_rentalYield`
  - family: macro prices, leverage, and affordability
  - source: official or near-official 2024 target when mapping is strong
  - scalar: mean over periods `200:2000`
  - status: diagnostic-only until mapping is confirmed
- `core_interestRateSpread`
  - family: macro prices, leverage, and affordability
  - source: official or near-official 2024 target when mapping is strong
  - scalar: mean over periods `200:2000`
  - status: diagnostic-only until mapping is confirmed

### Required Household Metrics

- `income_distribution_jsd`
  - family: household distribution realism
  - source: `WAS Round 8`
  - scalar: Jensen-Shannon distance between normalized model and target income histograms using the framework's fixed bins and current validation filters
  - status: required
- `housing_wealth_distribution_jsd`
  - family: household distribution realism
  - source: `WAS Round 8`
  - scalar: Jensen-Shannon distance between normalized model and target housing-wealth histograms using the framework's fixed bins and current validation filters
  - status: required
- `financial_wealth_distribution_jsd`
  - family: household distribution realism
  - source: `WAS Round 8`
  - scalar: Jensen-Shannon distance between normalized model and target financial-wealth histograms using the framework's fixed bins and current validation filters
  - status: required

## Expected Outcome

After implementation:
- each input-data version has a comparable 2024 validation summary
- the calibration history can be shown as progress toward the 2024 housing market
- the website exposes both fit and robustness without becoming visually heavy
- validation is no longer vulnerable to one-seed artifacts or to the narrowness of the old three-metric loss
