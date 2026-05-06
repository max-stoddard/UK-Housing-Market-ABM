# Abandoned Rental-Income Cached-Total Benchmark
Author: Max Stoddard

Decision: abandoned and reverted. The candidate Java implementation is no longer active in `src/main/java`.

Candidate implementation audit: the reverted change was a lazy cached monthly gross rental income total. It invalidated the cache when rental contracts were added, removed, or expired, then recomputed on demand. It was not a pure incremental running-total update.

Validation completed:
- `mvn -q -Dtest=HouseholdAccountingTest test` passed.
- `mvn -q test` passed.
- Three-run exact `v0 / e2e-default-5k-s1` similarity check passed against `docs/model-speed/baselines/v0-e2e-default-5k-s1.exact.sha256`.
- The three 5k candidate manifests also matched each other exactly.

Verdict rule: `faster` requires the candidate-minus-baseline 95% CI for `wall_clock_seconds` to be entirely below zero; `slower` requires it to be entirely above zero; otherwise the result is inconclusive/noise-dominated. The 10-run contract result was inconclusive, so the code was reverted rather than accepted as a speed improvement.

## e2e-default-5k-s1
- Contract role: similarity-only full-output check.
- Latest report: `tmp/model-speed/regressions/v0/e2e-default-5k-s1/exact/20260505T212555Z/regression-report.md`
- Result: all three candidate runs matched the tracked baseline manifest and each other exactly.
- Speed interpretation: none. The 5k path is not part of the speed verdict.

## core-minimal-10k-s1
- Baseline summary: `tmp/model-speed/benchmarks-clean-baseline-contract/v0/core-minimal-10k-s1/20260505T212659Z/summary.json`
- Candidate summary: `tmp/model-speed/benchmarks-candidate-contract/v0/core-minimal-10k-s1/20260505T213031Z/summary.json`
- Headline metric: `wall_clock_seconds`
- Execution-time verdict: `inconclusive/noise-dominated`

| Metric | Baseline mean ± 95% CI | Candidate mean ± 95% CI | Candidate - baseline mean ± 95% CI | Delta % | Baseline median | Candidate median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_clock_seconds | 20.131384 +/- 0.905429 | 20.067546 +/- 0.948981 | -0.063838 +/- 1.218345 | -0.317% | 19.684795 | 19.741962 |
| seconds_per_household_month | 1.006569e-06 +/- 4.527139e-08 | 1.003377e-06 +/- 4.744903e-08 | -3.192200e-09 +/- 6.091723e-08 | -0.317% | 9.842400e-07 | 9.870980e-07 |
| max_rss_kb | 4.357964e+05 +/- 2.502859e+03 | 4.370168e+05 +/- 2.697815e+03 | 1.220400e+03 +/- 3.419173e+03 | 0.280% | 4.365980e+05 | 4.372720e+05 |
| gc_pause_count | 8.9 +/- 1.633006 | 8.5 +/- 1.131079 | -0.4 +/- 1.861376 | -4.494% | 8 | 9 |
| gc_pause_time_ms_total | 72.3389 +/- 6.329392 | 70.2191 +/- 6.374148 | -2.1198 +/- 8.342597 | -2.930% | 68.2305 | 69.861 |
| user_cpu_seconds | 20.035 +/- 0.757027 | 19.86 +/- 0.841348 | -0.175 +/- 1.052002 | -0.873% | 19.715 | 19.47 |
| system_cpu_seconds | 0.199 +/- 0.017668 | 0.19 +/- 0.012618 | -0.009 +/- 0.020318 | -4.523% | 0.2 | 0.185 |
| output_bytes | 9.630850e+05 +/- 0 | 9.630850e+05 +/- 0 | 0 +/- 0 | 0.000% | 9.630850e+05 | 9.630850e+05 |

## Were The Contract Runs Enough?
- `core-minimal-10k-s1`: no after 10 measured repeats; verdict `inconclusive/noise-dominated`.

Historical note: the earlier 8-run 10k measurement showed a faster result, but the 10-run contract measurement above did not reproduce a statistically clear wall-clock improvement. Under the current contract, do not claim this experiment is faster.

Outcome: keep this report as negative evidence and prefer future optimisation work elsewhere.
