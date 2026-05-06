# 20k Speed Detection Benchmark
Author: Max Stoddard

Decision: promote `core-minimal-20k-s1` to the primary model-speed execution-time benchmark. The prior 10k benchmark was too noise-dominated for reliable small speed-improvement detection, while the measured 20k benchmark is sufficient for roughly `2.5%+` wall-clock effects under matching variance.

Scope:
- Benchmark strategy and documentation only.
- No `src/main/java` model logic changes.
- No `src/main/resources` mutation.

## Benchmark Evidence
- Summary path: `tmp/model-speed/benchmarks/v0/core-minimal-20k-s1/20260506T093735Z/summary.json`
- Mode: `core-minimal-20k-s1`
- `TARGET_POPULATION = 20000`
- `N_STEPS = 2000`
- `N_SIMS = 1`
- Measured repeats: `10`
- Warm-up runs: `0`
- Cool-down runs: `0`
- CPU policy: one process pinned to CPU `0`, JVM `-XX:ActiveProcessorCount=1`

| Metric | Value |
| --- | ---: |
| wall-clock mean | `43.469086s` |
| wall-clock median | `43.725334s` |
| wall-clock stdev | `1.046623s` |
| wall-clock CV | `2.4077%` |
| mean 95% CI half-width | `0.748709s` |
| mean 95% CI half-width as percent of mean | `1.7224%` |

## Detection Calculation
Assuming a future baseline and candidate each use 10 measured 20k runs with variance matching this benchmark:

```text
10+10 delta 95% half-width = t_18 * sqrt(2 * stdev^2 / 10)
                             = 0.983366s
                             = 2.2622% of the measured mean

2.5% of the measured mean = 1.086727s
margin to 2.5% threshold  = 0.103361s
```

This means a true `2.5%` wall-clock improvement should clear the estimated 95% candidate-minus-baseline delta uncertainty if the future run variance remains similar.

## Policy Impact
- Use `e2e-default-5k-s1` with three exact repeats as the model-output sanity gate only.
- Use `core-minimal-20k-s1` with 10 measured repeats as the primary speed-improvement benchmark.
- Do not run more 20k repeats by default.
- Run more 20k repeats only when a future candidate's measured variance makes the estimated 10+10 delta half-width exceed `2.5%` of the baseline mean.
