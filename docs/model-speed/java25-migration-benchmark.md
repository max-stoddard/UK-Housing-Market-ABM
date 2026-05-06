# Java 25 Migration Benchmark
Author: Max Stoddard

Decision: do not treat Java 25 as a model-speed improvement. The Java 25 default build preserved exact model output, but the current 10-run `core-minimal-20k-s1` strategy shows Java 25 is slower than `java8-compat` on wall clock. This 20k result supersedes the earlier 10k inconclusive/noise-dominated result.

Project target: Java 25 only. The previous Java 8 compatibility profile has been retired; the `java8-compat` runs below are retained as historical comparison evidence, not as an active workflow. Java 25 remains the long-term platform default because it reduces compatibility burden and keeps newer language, runtime, and tooling features available.

Scope:
- Build and harness documentation only.
- No `src/main/java` model logic changes.
- No `src/main/resources` mutation.
- No baseline SHA updates.

## Build Evidence
- Toolchain: OpenJDK 25.0.2, Maven 3.8.7.
- `mvn -q test`: passed.
- Java 25 default classfile check: `housing.Model` major version `69`.
- Historical `java8-compat` classfile check before profile removal: `housing.Model` major version `52`.
- Historical harness profile evidence: `environment.txt` records `maven_profiles=java8-compat` for compatibility runs and `maven_profiles=none` for Java 25 default runs.

Note: model-speed harness invocations must be serialized in one workspace. The harness compiles once before running candidates and uses shared `target/classes`; concurrent Maven/model-speed jobs can invalidate the running classpath.

## Exact 5k Regression
All three candidate manifests matched the tracked `v0-e2e-default-5k-s1` baseline and each other exactly.

| Cohort | Report |
| --- | --- |
| Pre-change Java 8-compatible build | `tmp/model-speed/regressions/java8-prechange/v0/e2e-default-5k-s1/exact/20260506T085505Z/regression-report.md` |
| Post-change `java8-compat` | `tmp/model-speed/regressions/java8-compat/v0/e2e-default-5k-s1/exact/20260506T085912Z/regression-report.md` |
| Java 25 default | `tmp/model-speed/regressions/java25-default/v0/e2e-default-5k-s1/exact/20260506T085811Z/regression-report.md` |
| 20k rerun `java8-compat` | `tmp/model-speed/regressions/java25-20k-java8-compat/v0/e2e-default-5k-s1/exact/20260506T100709Z/regression-report.md` |
| 20k rerun Java 25 default | `tmp/model-speed/regressions/java25-20k-default/v0/e2e-default-5k-s1/exact/20260506T100624Z/regression-report.md` |

The pre-change 10k benchmark had already started before the run-order correction and could not be interrupted by the sandbox session. The 5k exact gate passed before any file edits, and both post-change 5k exact gates passed before the post-change 10k benchmarks.

## 20k Rerun
The 20k rerun follows the current model-speed strategy: `core-minimal-20k-s1`, 10 measured repeats, 0 warm-up runs, 0 cool-down runs, CPU `0`, and JVM `-XX:ActiveProcessorCount=1`.

| Cohort | Summary |
| --- | --- |
| `java8-compat` | `tmp/model-speed/benchmarks/java25-20k-java8-compat/v0/core-minimal-20k-s1/20260506T100755Z/summary.json` |
| Java 25 default | `tmp/model-speed/benchmarks/java25-20k-default/v0/core-minimal-20k-s1/20260506T101534Z/summary.json` |

20k execution-time verdict: `slower`.

Java 25 default was slower than `java8-compat`: wall-clock mean increased by `3.921212s`, or `8.755%`, and the candidate-minus-baseline 95% CI was entirely above zero (`+1.250770s` to `+6.591655s`). Output volume was unchanged.

| Metric | `java8-compat` mean +/- 95% CI | Java 25 mean +/- 95% CI | Java 25 - `java8-compat` mean +/- 95% CI | Reduction % | `java8-compat` median | Java 25 median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_clock_seconds | 44.788503 +/- 1.788874 | 48.709716 +/- 2.238234 | 3.921212 +/- 2.670442 | -8.755% | 45.188529 | 48.14506 |
| seconds_per_household_month | 1.119713e-06 +/- 4.472182e-08 | 1.217743e-06 +/- 5.595588e-08 | 9.803030e-08 +/- 6.676106e-08 | -8.755% | 1.129714e-06 | 1.203627e-06 |
| max_rss_kb | 4.517876e+05 +/- 3.422955e+03 | 4.529656e+05 +/- 1.380284e+03 | 1.178000e+03 +/- 3.560167e+03 | -0.261% | 4.524320e+05 | 4.528580e+05 |
| gc_pause_count | 22.3 +/- 2.134115 | 22.6 +/- 1.477635 | 0.3 +/- 2.432316 | -1.345% | 21 | 21 |
| gc_pause_time_ms_total | 241.8267 +/- 17.664256 | 252.0647 +/- 19.798877 | 10.238 +/- 24.666157 | -4.234% | 238.4495 | 239.887 |
| user_cpu_seconds | 44.614 +/- 1.665617 | 48.427 +/- 2.627656 | 3.813 +/- 2.927722 | -8.547% | 44.76 | 48.325 |
| system_cpu_seconds | 0.19 +/- 0.01847 | 0.175 +/- 0.018238 | -0.015 +/- 0.024108 | 7.895% | 0.185 | 0.18 |
| output_bytes | 9.891770e+05 +/- 0 | 9.891770e+05 +/- 0 | 0 +/- 0 | -0.000% | 9.891770e+05 | 9.891770e+05 |

## 10k Benchmark Artifacts
Historical context only. The 20k rerun above is the current strategy result.

| Cohort | Summary |
| --- | --- |
| Pre-change Java 8-compatible build | `tmp/model-speed/benchmarks/java8-prechange/v0/core-minimal-10k-s1/20260506T085123Z/summary.json` |
| Post-change `java8-compat` | `tmp/model-speed/benchmarks/java8-compat/v0/core-minimal-10k-s1/20260506T090015Z/summary.json` |
| Java 25 default | `tmp/model-speed/benchmarks/java25-default/v0/core-minimal-10k-s1/20260506T090345Z/summary.json` |

Verdict rule: `faster` requires the candidate-minus-baseline 95% CI for `wall_clock_seconds` to be entirely below zero; `slower` requires it to be entirely above zero; otherwise the result is inconclusive/noise-dominated.

## Historical 10k Verdict: Java 25 Default vs `java8-compat`
Execution-time verdict: `inconclusive/noise-dominated`.

| Metric | `java8-compat` mean +/- 95% CI | Java 25 mean +/- 95% CI | Java 25 - `java8-compat` mean +/- 95% CI | Delta % | `java8-compat` median | Java 25 median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_clock_seconds | 19.738037 +/- 1.008867 | 20.107368 +/- 0.81495 | 0.369332 +/- 1.208352 | 1.871% | 19.461642 | 20.443256 |
| seconds_per_household_month | 9.869017e-07 +/- 5.044333e-08 | 1.005368e-06 +/- 4.074746e-08 | 1.846670e-08 +/- 6.041757e-08 | 1.871% | 9.730820e-07 | 1.022163e-06 |
| max_rss_kb | 4.365712e+05 +/- 3.242646e+03 | 4.342612e+05 +/- 2.217600e+03 | -2.310000e+03 +/- 3.683243e+03 | -0.529% | 4.361680e+05 | 4.345340e+05 |
| gc_pause_count | 8.2 +/- 1.158397 | 8.4 +/- 0.965658 | 0.2 +/- 1.403964 | 2.439% | 7.5 | 9 |
| gc_pause_time_ms_total | 60.6508 +/- 5.631066 | 59.5593 +/- 2.447695 | -1.0915 +/- 5.89962 | -1.800% | 59.6325 | 59.176 |
| user_cpu_seconds | 19.528 +/- 0.936227 | 19.914 +/- 0.682592 | 0.386 +/- 1.083405 | 1.977% | 18.995 | 19.965 |
| system_cpu_seconds | 0.178 +/- 0.026724 | 0.175 +/- 0.019445 | -0.003 +/- 0.030906 | -1.685% | 0.175 | 0.17 |
| output_bytes | 9.630850e+05 +/- 0 | 9.630850e+05 +/- 0 | 0 +/- 0 | 0.000% | 9.630850e+05 | 9.630850e+05 |

## Secondary Comparison: Post-change `java8-compat` vs Pre-change
Execution-time verdict: `faster`.

This comparison is useful for checking the Java 8 compatibility path after the build migration, but it is not the Java 25 speed verdict.

| Metric | Pre-change mean +/- 95% CI | Post-change `java8-compat` mean +/- 95% CI | Candidate - baseline mean +/- 95% CI | Delta % | Pre-change median | Candidate median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_clock_seconds | 21.306708 +/- 0.779294 | 19.738037 +/- 1.008867 | -1.568671 +/- 1.189403 | -7.362% | 21.293751 | 19.461642 |
| seconds_per_household_month | 1.065335e-06 +/- 3.896471e-08 | 9.869017e-07 +/- 5.044333e-08 | -7.843370e-08 +/- 5.947012e-08 | -7.362% | 1.064687e-06 | 9.730820e-07 |
| max_rss_kb | 4.374048e+05 +/- 3.055689e+03 | 4.365712e+05 +/- 3.242646e+03 | -833.6 +/- 4.139093e+03 | -0.191% | 4.384960e+05 | 4.361680e+05 |
| gc_pause_count | 9 +/- 1.306057 | 8.2 +/- 1.158397 | -0.8 +/- 1.623065 | -8.889% | 9 | 7.5 |
| gc_pause_time_ms_total | 72.3954 +/- 4.80995 | 60.6508 +/- 5.631066 | -11.7446 +/- 6.890369 | -16.223% | 69.322 | 59.6325 |
| user_cpu_seconds | 20.999 +/- 0.561953 | 19.528 +/- 0.936227 | -1.471 +/- 1.030513 | -7.005% | 20.915 | 18.995 |
| system_cpu_seconds | 0.204 +/- 0.021645 | 0.178 +/- 0.026724 | -0.026 +/- 0.03204 | -12.745% | 0.195 | 0.175 |
| output_bytes | 9.630850e+05 +/- 0 | 9.630850e+05 +/- 0 | 0 +/- 0 | 0.000% | 9.630850e+05 | 9.630850e+05 |

## Secondary Comparison: Java 25 Default vs Pre-change
Execution-time verdict: `faster`.

This comparison includes both the toolchain default change and any run-order/build-path differences. The controlled Java 25 default vs post-change `java8-compat` comparison above remains the decision point for the migration.

| Metric | Pre-change mean +/- 95% CI | Java 25 mean +/- 95% CI | Java 25 - pre-change mean +/- 95% CI | Delta % | Pre-change median | Java 25 median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_clock_seconds | 21.306708 +/- 0.779294 | 20.107368 +/- 0.81495 | -1.199339 +/- 1.047374 | -5.629% | 21.293751 | 20.443256 |
| seconds_per_household_month | 1.065335e-06 +/- 3.896471e-08 | 1.005368e-06 +/- 4.074746e-08 | -5.996700e-08 +/- 5.236866e-08 | -5.629% | 1.064687e-06 | 1.022163e-06 |
| max_rss_kb | 4.374048e+05 +/- 3.055689e+03 | 4.342612e+05 +/- 2.217600e+03 | -3.143600e+03 +/- 3.531058e+03 | -0.719% | 4.384960e+05 | 4.345340e+05 |
| gc_pause_count | 9 +/- 1.306057 | 8.4 +/- 0.965658 | -0.6 +/- 1.517966 | -6.667% | 9 | 9 |
| gc_pause_time_ms_total | 72.3954 +/- 4.80995 | 59.5593 +/- 2.447695 | -12.8361 +/- 5.140395 | -17.731% | 69.322 | 59.176 |
| user_cpu_seconds | 20.999 +/- 0.561953 | 19.914 +/- 0.682592 | -1.085 +/- 0.823359 | -5.167% | 20.915 | 19.965 |
| system_cpu_seconds | 0.204 +/- 0.021645 | 0.175 +/- 0.019445 | -0.029 +/- 0.027046 | -14.216% | 0.195 | 0.17 |
| output_bytes | 9.630850e+05 +/- 0 | 9.630850e+05 +/- 0 | 0 +/- 0 | 0.000% | 9.630850e+05 | 9.630850e+05 |
