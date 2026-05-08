# Model Speed Changelog
Author: Max Stoddard

This changelog is dedicated only to the model-speed improvement programme.

## Entry Format
- Date
- Phase or change label
- Scope
- Benchmark and regression impact
- Required follow-up

## 2026-05-07 - True JDK 25 vs JDK 8 Runtime Diagnostic
- Re-ran the Java toolchain comparison as actual runtimes, with JDK 25 first and JDK 8 second, using fresh disposable clones and the current `v0 / core-minimal-20k-s1` 20k x 10 policy.
- Kept JDK 8 changes benchmark-only: Java 8 bytecode, JDK 8-compatible GC logging, and JDK 8 GC pause parsing in the disposable clone.
- No Java model source, runtime resources, canonical baselines, or Java alternatives changed.

Benchmark and regression impact:
- JDK 25 exact gate passed: `tmp/model-speed/jdk-runtime-rerun/20260507T144346Z/java25-first/regressions/v0/e2e-default-5k-s1/exact/20260507T144455Z/regression-report.md`.
- JDK 8 exact gate failed, but candidate repeats matched each other: `tmp/model-speed/jdk-runtime-rerun/20260507T144346Z/java8-second/regressions/v0/e2e-default-5k-s1/exact/20260507T145427Z/regression-report.md`.
- Diagnostic 20k comparison report: `tmp/model-speed/jdk-runtime-rerun/20260507T144346Z/jdk8-vs-jdk25-20k-comparison.md`.
- JDK 25 mean wall clock: `50.033577s +/- 3.485862s` 95% CI.
- JDK 8 mean wall clock: `58.576502s +/- 2.010190s` 95% CI.
- JDK8-minus-JDK25 wall-clock delta: `+8.542924s +/- 3.805914s`; verdict JDK 25 faster, diagnostic only because JDK 8 output differed.

Required follow-up:
- Keep Java 25 as the active project target. Do not treat the JDK 8 timing as model-equivalent speed evidence unless a future true JDK 8 runtime path passes the exact output gate.

## 2026-05-06 - Cached Rental Income 20k Contract Rerun
- Re-ran the lazy cached `Household.getMonthlyGrossRentalIncome()` candidate under the current model-speed contract using isolated source copies.
- The candidate source was run first, followed by default model source, both using the same current harness, CPU `0`, and JVM `-XX:ActiveProcessorCount=1`.
- The candidate preserves exact `sum(RentalAgreement.nextPayment())` output by dirty-invalidating rental income on rental-contract lifecycle changes and recomputing in `TreeMap` value order on demand.

Benchmark and regression impact:
- Candidate exact gate passed: `tmp/model-speed/rental-income-rerun/after-first/regressions/v0/e2e-default-5k-s1/exact/20260506T104844Z/regression-report.md`.
- Default exact gate passed: `tmp/model-speed/rental-income-rerun/default-second/regressions/v0/e2e-default-5k-s1/exact/20260506T104927Z/regression-report.md`.
- 20k speed comparison report: `tmp/model-speed/rental-income-rerun/20k-speed-comparison.md`.
- `core-minimal-20k-s1` default mean wall clock: `45.266753s +/- 1.163163s` 95% CI.
- `core-minimal-20k-s1` cached candidate mean wall clock: `41.831341s +/- 1.172032s` 95% CI.
- Candidate-minus-default wall-clock delta: `-3.435412s +/- 1.533559s`, `-7.589%`; verdict `faster`.
- Output volume was unchanged at `989177` bytes.

Required follow-up:
- Reconcile future rental-income work against the current main-worktree `Household.getMonthlyGrossRentalIncome()` dirty cache before treating this isolated rerun as a new opportunity.

## 2026-05-06 - Java 25-Only Target Cleanup
- Removed the active `java8-compat` Maven profile and made Java 25 the only supported Java compile target.
- Kept generic `MODEL_SPEED_MAVEN_PROFILES` harness support for future Maven-profile experiments, but removed Java 8-specific active command examples.
- Documented Java 25 as the long-term platform default because it reduces compatibility burden and keeps newer language, runtime, and tooling features available.

Benchmark and regression impact:
- No Java model source or runtime resources changed.
- The existing 20k Java 25 migration benchmark remains historical evidence: Java 25 preserved exact output but was slower than the retired compatibility build on the current speed gate.

Required follow-up:
- Continue using Java 25 for active development; evaluate future model-speed work on the 20k gate rather than reintroducing Java 8 compatibility.

## 2026-05-06 - 20k Speed Detection Strategy
- Promoted `core-minimal-20k-s1` to the primary minimal-output execution-time benchmark while keeping `e2e-default-5k-s1` as a three-run exact model-output sanity gate only.
- Added `docs/model-speed/20k-speed-detection-benchmark.md` to record the measured `20k x 10` evidence and detection calculation.
- Added the pinned `v0-core-minimal-20k-s1` mode, matching the 10k minimal-output mode except for `TARGET_POPULATION = 20000`.

Benchmark and regression impact:
- The measured `20k x 10` run at `tmp/model-speed/benchmarks/v0/core-minimal-20k-s1/20260506T093735Z/summary.json` had wall-clock mean `43.469086s`, stdev `1.046623s`, and CV `2.4077%`.
- The estimated 10-baseline-run plus 10-candidate-run 95% candidate-minus-baseline delta half-width is `0.983366s`, or `2.2622%` of the measured mean.
- This is below the `2.5%` improvement-detection target and below the broader `5%` uncertainty ceiling, so no additional 20k repeats are required before using the 20k gate.

Required follow-up:
- For future speed candidates, run more 20k repeats only if the measured 10+10 delta uncertainty exceeds `2.5%` of the baseline mean.

## 2026-05-06 - Java 25 Toolchain Experiment
- Migrated Maven compiler configuration from Java 8 `source`/`target` to `--release`, with Java 25 as the default release and `-Pjava8-compat` preserving the Java 8 compatibility path.
- Added `MODEL_SPEED_MAVEN_PROFILES` to the model-speed harness so benchmark, regression, and profile runs can compile and resolve classpaths through Maven profiles.
- Kept the experiment scoped to build/harness/documentation changes only; no model Java source or runtime input resources were changed.

Regression policy for this experiment:
- exact output similarity uses three repeated `v0 / e2e-default-5k-s1` runs
- the original speed comparison used 10 repeated `v0 / core-minimal-10k-s1` runs for pre-change Java 8-compatible output, post-change `java8-compat`, and post-change Java 25 default
- the current strategy rerun uses 10 repeated `v0 / core-minimal-20k-s1` runs comparing post-change `java8-compat` against Java 25 default

Required follow-up:
- Do not treat the Java 25 default migration as a speed improvement. The 20k rerun preserved exact output, but Java 25 was slower than `java8-compat` on wall clock: `+3.921212s` mean, `+8.755%`, with the 95% CI entirely above zero.

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
