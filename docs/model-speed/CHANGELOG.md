# Model Speed Changelog
Author: Max Stoddard

This changelog is dedicated only to the model-speed improvement programme.

## Entry Format
- Date
- Phase or change label
- Scope
- Benchmark and regression impact
- Required follow-up

## 2026-05-05 - v0 Contract Split And Uncertainty Reset
- Replaced the active canonical model-speed populations with:
  - `e2e-default-5k-s1` for three-run exact output similarity only
  - `core-minimal-10k-s1` for primary minimal-output execution-time evidence
- Changed canonical speed benchmarking to 10 measured 10k repeats, 0 warm-up runs, 0 cool-down runs, serial execution, and one-core pinning with JVM `-XX:ActiveProcessorCount=1`.
- Removed mandatory median JFR capture from the benchmark path; profiling remains available through the profile harness or explicit benchmark JFR capture.
- Extended benchmark summaries to report uncertainty for each numeric metric, including SEM, coefficient of variation, and a 95% CI for the mean.

Regression policy from this point:
- exact output similarity is anchored on three repeated `v0 / e2e-default-5k-s1` runs
- speed claims are anchored on 10 repeated `v0 / core-minimal-10k-s1` runs and use `wall_clock_seconds` as the headline verdict metric

Benchmark and regression impact:
- Refreshed the tracked exact hash manifest for `e2e-default-5k-s1`.
- Refreshed the 10k summary snapshot under the new one-core, no-warm-up policy.
- Benchmarked the `monthlyGrossRentalIncome` cached-total experiment against the refreshed baselines:
  - `e2e-default-5k-s1` is similarity-only and should not be used for a speed verdict.
  - `core-minimal-10k-s1` was faster in the initial 8-run measurement, but the later 10-run wall-clock contract measurement was inconclusive/noise-dominated.
- Abandoned and reverted the cached-total Java implementation because the model risk and added lifecycle state were not justified by the 10-run contract result.

Required follow-up:
- Treat the rental-income cached-total report as negative evidence and prioritise other speed work.

## 2026-05-05 - v0 Canonical Baseline Set
- Rebased the active model-speed benchmark strategy from `input-data-versions/v4.1` to the full `input-data-versions/v0` snapshot while preserving snapshot-local config materialisation.
- Replaced the old active mode set with exactly two canonical baselines:
  - `e2e-default-10k-s1` for exact correctness and output-contract regression
  - `core-minimal-20k-s1` for primary single-run speed and scaling
- Retired `core-minimal-10k` as a primary speed baseline identity; `10k` remains only in the full-output exact regression gate.
- Rejected `core-minimal-100k-s1` as a routine canonical baseline after benchmark execution showed it was too slow for the programme's regular gate.
- Rejected `core-minimal-10k-s8` as a routine canonical baseline because `N_SIMS = 8` currently measures expensive serial multi-simulation execution rather than worker-level parallel scaling.
- Documented worker ladders `1`, `8`, and `16` as hardware-specific scaling experiments rather than canonical baseline identities.

Regression policy from this point:
- exact regression is anchored on `v0 / e2e-default-10k-s1`
- the minimal-output baseline summary is speed and scaling evidence, not an exact correctness contract

Required follow-up:
- regenerate and review the v0 exact hash manifest for `e2e-default-10k-s1`
- refresh summary snapshots for both canonical baselines after the first full benchmark set
- refresh profiling artifacts against `core-minimal-20k-s1` when prioritising the next optimisation slice

## 2026-03-07 - Phase 1 Scaffolding
- Froze the speed programme baseline at `input-data-versions/v4.1` with `r8` as the validation target.
- Defined the primary engineering metric as `seconds_per_household_month = wall_clock_seconds / (TARGET_POPULATION * N_STEPS * N_SIMS)`.
- Kept end-to-end `wall_clock_seconds` as the main user-facing guardrail metric.
- Set the first scale SLO to `TARGET_POPULATION = 100000` in `core-minimal-100k` with a target runtime under `60s` on the pinned WSL2 benchmark setup.
- Pinned the benchmark environment around WSL2 Ubuntu, OpenJDK 25, and Maven 3.8.7.
- Added snapshot-local benchmark, regression, and profiling harnesses under `scripts/model/`.
- Added tracked benchmark mode definitions under `scripts/model/configs/`.
- Added the `docs/model-speed/` documentation set, including this changelog, the canonical README, the local agent guide, and baseline-manifest storage.
- Established the rule that all future speed changes must pass strict regression before merge.

Regression policy from this point:
- exact single-thread work must remain bitwise exact
- tolerance-based regression is reserved for a later explicitly approved parallel track

Historical runtime context captured before fresh harness remeasurement:
- recent validation logs in `tmp/validation-refresh-20260214-210435/` show roughly `14s` to `16.5s` for the existing `10k / 2000-step / 1-sim` configuration
- existing `Results/v4.1-output` footprint is roughly `66 MB`

Required follow-up:
- collect the first fully measured multi-repeat benchmark set with the new harness
- refresh the tracked summary snapshot in `docs/model-speed/baselines/`
- begin hotspot ranking from JFR evidence rather than intuition

## 2026-03-07 - JFR Reporting Artifacts
- Extended `scripts/model/model_speed.py` with JFR execution-sample parsing, modelStep phase attribution, method-share reporting, and self-contained SVG flame graph rendering.
- Added checked-in profiling artifacts under `docs/model-speed/profiles/` for both existing median JFR recordings:
  - `core-minimal-10k-modelstep-flamegraph.svg`
  - `e2e-default-10k-modelstep-flamegraph.svg`
  - `JFR_METHOD_BREAKDOWN.md`
- Added machine-readable method-share companions for both profiles as JSON and CSV.
- Locked the current JFR validation counts into the report-generation flow:
  - core-minimal-10k `ExecutionSample` count `1363`, modelStep count `1355`
  - e2e-default-10k `ExecutionSample` count `1705`, modelStep count `1693`

Required follow-up:
- regenerate the checked-in profiling artifacts after any future benchmark/profile refresh
- compare new phase shares against the current household-loop, rental-market, and household-stats-heavy baseline before prioritising the next optimisation slice
