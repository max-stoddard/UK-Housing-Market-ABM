# Seed-1 Paired Cache Benchmark
Author: Max Stoddard

Decision: add a diagnostic paired cache benchmark that keeps the canonical `v0 / core-minimal-20k-s1` scenario and `SEED = 1`, but runs cache-off and cache-on source roots in adjacent randomized pairs.

Scope:
- Benchmark strategy and harness only.
- No `src/main/java` model logic changes.
- No `src/main/resources` mutation.
- This is not a replacement for the canonical 10-repeat `core-minimal-20k-s1` speed gate unless it is explicitly promoted later.

## Benchmark Shape
- Snapshot: `v0`
- Mode: `core-minimal-20k-s1`
- Seed: `1`
- Measured repeats: `40` cache-off and `40` cache-on
- Warm-up: `3` balanced cache-off/cache-on pairs, excluded from timing
- Run order: adjacent cache pairs; pair order and within-pair cache-on/off order are deterministic-randomized
- CPU policy for official runs: one process at a time, `taskset -c 0`, JVM `-XX:ActiveProcessorCount=1`

## Command

```bash
bash scripts/model/run-cache-paired-benchmark.sh \
  --snapshot v0 \
  --mode core-minimal-20k-s1 \
  --seed 1 \
  --repeat 40 \
  --warmup-pairs 3 \
  --cache-off-root path/to/cache-off-worktree \
  --cache-on-root path/to/cache-on-worktree \
  --ordering-seed 20260603 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root tmp/model-speed/cache-paired
```

The harness runs `./mvnw -q test` and the three-run exact `e2e-default-5k-s1` regression gate in both source roots before timing.

## Outputs
- `run-plan.tsv`: warm-up and measured order.
- `measured-runs.tsv`: docs-style metrics plus `phase`, `variant`, `pair_index`, `run_order_index`, and `seed`.
- `paired-summary.json`: paired cache speedup from log ratios, per-variant metrics, cache-on-minus-cache-off paired metric summaries, and paired manifest comparison.

Any cache-on/off output-manifest mismatch fails the benchmark report. A speed gain that changes model output should not be treated as positive model-speed evidence.
