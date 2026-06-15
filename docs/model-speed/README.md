# Model Speed Programme
Author: Max Stoddard

## Purpose
This folder is the canonical planning and operational home for iterative model-speed work on the Java ABM in `src/main/java`.

The programme is intentionally performance-engineering-led:

1. Freeze reproducible benchmark baselines.
2. Measure before changing anything.
3. Profile before choosing hotspots.
4. Optimise one hotspot family at a time.
5. Re-run strict regression checks after every accepted change.

No speed change is accepted on anecdote alone.

## Frozen Baselines
- Input snapshot: `input-data-versions/v0`
- Validation dataset target: `r8`
- Benchmark host assumption: WSL2 Ubuntu
- Runtime toolchain target: OpenJDK 25, repo-local Maven wrapper pinned to Maven 3.9.15
- Java 25 is the only supported Java compile target. The project no longer carries an active Java 8 compatibility path.
- Primary optimisation goal: reduce single-run latency and improve scale-normalised throughput enough to make larger `TARGET_POPULATION` runs practical
- Java 25 is the long-term platform default because it reduces compatibility burden and keeps future language, runtime, and tooling features available, even though benchmark evidence must still decide whether any toolchain change is a speed improvement.

Important:
- The speed harness is snapshot-local and does **not** mutate `src/main/resources`.
- This is deliberate because the repository often has active uncommitted resource edits.
- The legacy validation entrypoint `bash input-data-versions/validate.sh v0 r8 --no-graphs` still switches live resources and should therefore be run only from a clean or explicitly prepared worktree state.
- Run model-speed harnesses one at a time per workspace. Maven compile/classpath steps share `target/classes`, and profile-switching experiments may clean/recompile that directory.

## Metrics
Primary engineering metric for scale-normalised analysis:

```text
seconds_per_household_month = wall_clock_seconds / (TARGET_POPULATION * N_STEPS * N_SIMS)
```

Why this is primary:
- It normalises scale.
- It makes population-growth progress visible even when absolute runtime changes are noisy.
- It directly aligns with the programme goal of making larger `TARGET_POPULATION` runs practical.

Headline speed-contract metric:
- `wall_clock_seconds` for `core-minimal-20k-s1`, including JVM startup and output generation for the minimal-output mode

Supporting metrics:
- `model_computing_seconds` from the model's own stdout
- `max_rss_kb`
- `user_cpu_seconds`
- `system_cpu_seconds`
- `output_bytes`
- `gc_pause_count`
- `gc_pause_time_ms_total`

## Canonical Baselines
Authoritative tracked mode definitions live under [`scripts/model/configs`](/home/max/dev/uni/project/models/uk-housing-model-individual-project/scripts/model/configs).

At runtime the harness materialises a full snapshot-local config copy under `tmp/model-speed/generated-configs/` by:
- loading `input-data-versions/v0/config.properties`
- rewriting resource paths to `input-data-versions/v0/...`
- applying the pinned mode overrides

The canonical baselines are:
- `e2e-default-5k-s1`: `TARGET_POPULATION = 5000`, `N_STEPS = 2000`, `N_SIMS = 1`, default/full output contract. This is the exact correctness and output-contract regression gate.
- `core-minimal-20k-s1`: `TARGET_POPULATION = 20000`, `N_STEPS = 2000`, `N_SIMS = 1`, minimal outputs. This is the primary single-run simulation speed and scaling gate.

The `5k` e2e baseline is not a speed benchmark. Its purpose is to preserve exact model/output correctness and similarity while speed work is evaluated on the minimal-output 20k execution-time baseline.

## Workflow
### 1. Check Similarity First
Run the 5k exact/similarity check:

```bash
bash scripts/model/run-speed-regression.sh \
  --snapshot v0 \
  --mode e2e-default-5k-s1 \
  --contract exact \
  --baseline-manifest docs/model-speed/baselines/v0-e2e-default-5k-s1.exact.sha256 \
  --repeat 3 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root tmp/model-speed/regressions
```

The 5k similarity check runs three full-output candidate executions. Every candidate output manifest must match the tracked baseline manifest, and the three candidate manifests must match each other. Do not use the 5k path for a speed verdict.

### 2. Benchmark Execution Time
Run the canonical 20k execution-time benchmark:

```bash
bash scripts/model/run-speed-benchmark.sh \
  --snapshot v0 \
  --mode core-minimal-20k-s1 \
  --repeat 10 \
  --warmup 0 \
  --cooldown 0 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root tmp/model-speed/benchmarks
```

What the 20k benchmark does:
- compiles the Java project
- honours `MODEL_SPEED_MAVEN_PROFILES` for compile/classpath resolution when an optional Maven profile is needed
- resolves a direct runtime classpath
- materialises a snapshot-local benchmark config
- runs the requested measured repeats with no warm-up or cool-down by default
- can optionally run warm-up/cool-down passes and median JFR capture when explicitly requested
- captures `/usr/bin/time -v`
- captures GC logs and a parsed GC summary
- hashes output files for every measured run
- emits a run TSV and aggregate summary JSON
- reports uncertainty for every numeric metric, including SEM, coefficient of variation, and a 95% confidence interval for the mean

The 20k speed verdict is based on `wall_clock_seconds`. A change is faster only when the candidate-minus-baseline 95% CI for mean wall clock is entirely below zero, slower only when it is entirely above zero, and otherwise inconclusive/noise-dominated. `seconds_per_household_month` remains supporting scale-normalised evidence.

The 20k gate replaces the earlier 10k gate because the measured 10-run 20k benchmark has `2.4077%` wall-clock CV and an estimated 10+10 run baseline-vs-candidate 95% delta half-width of `2.2622%`. This is sufficient to detect roughly `2.5%+` wall-clock improvements under matching variance. See [`20k-speed-detection-benchmark.md`](/home/max/dev/uni/project/models/uk-housing-model-individual-project/docs/model-speed/20k-speed-detection-benchmark.md).

For population-shape sanity checks, the existing ladder mode may be used on `core-minimal-10k-s1`:

```bash
MODEL_SPEED_POPULATION_LADDER=1 \
bash scripts/model/run-speed-benchmark.sh \
  --snapshot v0 \
  --mode core-minimal-10k-s1 \
  --repeat 3 \
  --output-root tmp/model-speed/benchmarks
```

The population ladder records one measured pass each at `5k` and `10k`. These points are diagnostics, not baseline identities.

Diagnostic cache-candidate comparisons can use the seed-1 paired cache benchmark when the question is whether a cache-on source root is measurably faster than a cache-off source root under the same canonical 20k scenario:

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

This paired cache benchmark is diagnostic and does not replace the canonical 10-repeat 20k speed gate. See [`seed-1-paired-cache-benchmark.md`](/home/max/dev/uni/project/models/uk-housing-model-individual-project/docs/model-speed/seed-1-paired-cache-benchmark.md).

### 3. Profile Second
Canonical JFR profile command:

```bash
bash scripts/model/profile-model.sh \
  --snapshot v0 \
  --mode core-minimal-20k-s1 \
  --profiler jfr \
  --output-root tmp/model-speed/profiles
```

Canonical `perf` command:

```bash
bash scripts/model/profile-model.sh \
  --snapshot v0 \
  --mode core-minimal-20k-s1 \
  --profiler perf \
  --output-root tmp/model-speed/profiles
```

Use JFR first. Only reach for `perf` if JFR does not make CPU or allocation hotspots clear enough on WSL.

Current checked-in profiling artifacts from the earlier v4.1 smoke recordings live under [`docs/model-speed/profiles`](/home/max/dev/uni/project/models/uk-housing-model-individual-project/docs/model-speed/profiles). These artifacts are historical hotspot evidence and are not current canonical baselines.

### 4. Optimise In Narrow Slices
Default hotspot order unless profiling disproves it:
1. recorder and output overhead
2. whole-population collectors and recounts
3. repeated per-step allocations
4. repeated mortgage, tax, income, and wealth recomputation inside household flow
5. market queue and data-structure costs

Rules:
- one hotspot family per change
- one speed changelog entry per change
- one benchmark delta report per change
- stop reworking a subsystem once measured gains flatten

### 5. Regression Gate Every Change
Exact regression command:

```bash
bash scripts/model/run-speed-regression.sh \
  --snapshot v0 \
  --mode e2e-default-5k-s1 \
  --contract exact \
  --baseline-manifest docs/model-speed/baselines/v0-e2e-default-5k-s1.exact.sha256 \
  --repeat 3 \
  --pin-cpu 0 \
  --active-processor-count 1 \
  --output-root tmp/model-speed/regressions
```

Future tolerance contract command shape:

```bash
bash scripts/model/run-speed-regression.sh \
  --snapshot v0 \
  --mode e2e-default-5k-s1 \
  --contract tolerance \
  --baseline-manifest path/to/tolerance-spec.json \
  --output-root tmp/model-speed/regressions
```

Current policy:
- speed work must pass the three-run bitwise exact similarity check against `e2e-default-5k-s1`
- speed claims are evaluated on the 10-run `core-minimal-20k-s1` wall-clock benchmark
- tolerance-based regression is reserved for a later explicitly approved track

## Acceptance Criteria
Every accepted speed change must pass:
- `./mvnw -q -DskipTests compile`
- `./mvnw -q test`
- three-run exact deterministic similarity check on `v0 / e2e-default-5k-s1`
- 10-repeat benchmark rerun on `v0 / core-minimal-20k-s1`
- `bash input-data-versions/validate.sh v0 r8 --no-graphs` when a model-code change needs live validation and the worktree is prepared for resource mutation

Exact means:
- same output file set
- same byte content
- same file hashes

The benchmark delta report for each accepted speed change must show:
- wall-clock delta and verdict
- scale-normalised metric delta as supporting evidence
- RSS delta
- GC delta
- output-volume delta

## Tracked Baselines
Tracked baseline manifests and summary snapshots live in [`docs/model-speed/baselines`](/home/max/dev/uni/project/models/uk-housing-model-individual-project/docs/model-speed/baselines).

Rules:
- exact hash manifests are tracked only for the e2e correctness gate
- summary snapshots are tracked only when a speed-baseline snapshot refresh is explicitly accepted
- the existing `v0-core-minimal-10k-s1.summary.json` is historical and not the active speed verdict baseline
- raw run outputs belong in `tmp/model-speed/`
- generated configs belong in `tmp/model-speed/generated-configs/`
- `Results/` is not the canonical home for speed-regression baselines

## Parallel And Scaling Experiments
There is no canonical `N_SIMS > 1` baseline at present. The current Java path executes multiple simulations serially inside one process, so `N_SIMS = 8` is too expensive for routine gating and does not directly measure worker-level parallel execution.

Worker ladders are scaling experiments, not baseline identities. Use `1`, `8`, and `16` workers when evaluating outer-loop parallel execution over independent single-simulation jobs on suitable hardware, and report the worker count alongside the host details. The `16` point is hardware-specific and must not define a canonical baseline name.

Preferred order for parallel work:
1. outer-loop parallelism (`N_SIMS`, seed batches, sweeps)
2. only then consider intra-run parallelism

The exact `e2e-default-5k-s1` path remains the canonical correctness reference after any parallel track begins.
