# HPA Expectation v4.2 Production Calibration Design

> **Implementation note:** The current code now implements a unified staged workflow with a `production` search mode that writes a JSON artifact and an artifact-driven calibration rerun. Treat this document as design context, not the live CLI contract.

**Author:** Max Stoddard
**Date:** 2026-04-14
**Status:** Approved
**Scope:** `scripts/python/experiments/nmg/`, `scripts/python/calibration/nmg/`, `scripts/python/helpers/nmg/`, `scripts/python/helpers/ppd/`, `input-data-versions/`

## Problem

The repository now contains a transparent reconstruction workflow for the HPA expectation rule, but the initial legacy-recovery experiment did not identify a convincing method for reproducing the historical `0.44 / -0.007` coefficients.

That result changes the goal of the remaining work. The next calibration stage should not keep optimizing for legacy recovery. It should produce a defensible `v4.2` update recalibrated to 2024 using the best continuous modern data window now available, while keeping the coefficients numerically plausible and methodologically simple.

## Approved Design Decisions

- Final production coefficients are fit on the continuous modern window `2018` to `2024`.
- `2014` and `2016` remain available only as diagnostics and sensitivity checks.
- The chosen approach is constrained fixed-method regression, not legacy-target recovery and not simulator-tuned calibration.
- "Realistic" means the fitted `HPA_EXPECTATION_FACTOR` and `HPA_EXPECTATION_CONST` should sit in a numerically plausible range, not just minimize regression error.
- Existing helper modules should be reused wherever possible, with only targeted extensions for missing behavior.

## Goals

- Estimate new `HPA_EXPECTATION_FACTOR` and `HPA_EXPECTATION_CONST` values for `v4.2` using `2018` to `2024` survey and PPD anchors.
- Keep the calibration method simple, transparent, and reproducible from private datasets.
- Reuse the current NMG and PPD helper stack rather than introducing parallel one-off code paths.
- Record enough diagnostics that the chosen coefficients can be defended from both a data and parameter-plausibility perspective.
- Create the full `v4.2` release path:
  - production calibration script
  - `input-data-versions/v4.2`
  - validation via `input-data-versions/validate.sh`
  - full model output in `Results/v4.2-output`
  - complete `input-data-versions/version-notes.json` entry

## Non-Goals

- Further optimizing against the historical `0.44 / -0.007` target.
- Introducing region-specific expectation coefficients.
- Using downstream ABM behavior as the primary estimation objective.
- Replacing working helper logic where a small extension will suffice.
- Updating unrelated calibration parameters in the `v4.2` release.

## Runtime Contract

The model still consumes one national linear expectation rule:

`expected_hpa = long_term_hpa * HPA_EXPECTATION_FACTOR + HPA_EXPECTATION_CONST`

This is applied in `HouseholdBehaviour.getLongTermHPAExpectation()`, and the predictor term comes from the model's long-term HPA calculation with `HPA_YEARS_TO_CHECK = 2`.

The production calibration must therefore estimate one national linear rule whose predictor is aligned with the existing 2-year trend logic and whose response is the observed national expectation signal from NMG.

## Data Window

### Production Window

Use yearly anchors from:

- NMG: `2018`, `2019`, `2020`, `2021`, `2022`, `2023`, `2024`
- PPD: `2018`, `2019`, `2020`, `2021`, `2022`, `2023`, `2024`

This is the first continuous modern window where both source families are available without production-time cross-year pairing compromises.

### Diagnostic-Only Years

Retain:

- NMG `2014`
- NMG `2016`
- earlier PPD years already present in the repo

These should be used only to report how the chosen production method behaves outside the fit window. They should not influence the final `v4.2` coefficients.

## Estimation Method

### Survey Target

Construct one national expectation estimate per year from NMG:

- use `boe39`
- exclude `Don't know`
- weight by `we_factor`

Survey mapping candidates are intentionally narrow:

- `midpoint_exact`
- `midpoint_rounded`

The default preference order is:

1. `midpoint_rounded` if in-window performance is materially indistinguishable
2. otherwise `midpoint_exact`

This keeps the mapping transparent and avoids overfitting through arbitrary band remapping.

### HPA Predictor

Construct one national HPA signal per year from PPD with the same 2-year horizon implied by `HPA_YEARS_TO_CHECK = 2`.

Candidate signal methods:

1. `java_like_annualised`
2. `annual_mean_annualised`

Do not use cumulative-growth production fits unless the annualised methods fail structurally. The preferred choice is the Java-like annualised signal because it is the closest match to the runtime semantics.

### Anchor Rule

For the production window, use same-year anchors only:

- survey year `t` pairs to PPD anchor year `t`
- predictor base year resolves to `t - 2` when available

Because the fitted years are `2018` to `2024`, the earliest production predictor year is the HPA signal ending in `2018`, which relies on available earlier PPD history where required by the 2-year window.

### Fit Rule

For each admissible method variant:

- compute yearly survey expectations for `2018` to `2024`
- compute yearly PPD HPA signals for `2018` to `2024`
- fit one OLS line across all yearly anchors

The fitted equation remains:

`expected_hpa = factor * long_term_hpa + const`

No nonlinear transforms, post-fit clipping, or manual coefficient overrides are permitted.

## Plausibility Screen

The calibration must enforce a two-level plausibility screen.

### Hard Admissibility

Reject any fit with:

- `factor < 0`
- `factor > 1.25`
- `abs(const) > 0.03`

These are outside the credible range for a trend-following expectation rule with a small additive bias term.

### Preferred Band

Prefer fits with:

- `0.2 <= factor <= 0.8`
- `abs(const) <= 0.01`

These bounds are not used to hand-set coefficients. They are used to distinguish a numerically plausible parameterisation from a technically admissible but suspicious one.

### Ranking Rule

Rank candidates in this order:

1. admissible before inadmissible
2. inside preferred band before outside preferred band
3. lower in-window error across `2018` to `2024`
4. simpler method choice:
   - `midpoint_rounded` before `midpoint_exact` when fit quality is effectively tied
   - `java_like_annualised` before `annual_mean_annualised` when fit quality is effectively tied

If no candidate lands in the preferred band, select the lowest-error admissible fit and explicitly record that the preferred band was missed.

## Helper Reuse Strategy

Implementation should reuse the current helpers first and only extend them where the new production workflow needs extra behavior.

### Reuse Without Replacement

- `scripts/python/helpers/nmg/hpa_expectation.py`
  - reuse `aggregate_expectation`
  - reuse `fit_linear_rule`
  - reuse existing method-spec structure for `boe39` mappings
- `scripts/python/helpers/ppd/hpa_signal_methods.py`
  - reuse `load_ppd_rows`
  - reuse `build_hpa_signal`
  - reuse `resolve_base_year` where the 2-year history rule still applies
- `scripts/python/helpers/common/math_stats.py`
  - reuse existing small math helpers if ranking math remains generic enough

### Likely Small Extensions

- add compact helper functions for:
  - yearly multi-anchor assembly over `2018` to `2024`
  - plausibility classification for `(factor, const)`
  - in-window regression error diagnostics
- keep those additions in the current domain helper modules when possible instead of creating new modules unless responsibility genuinely changes

### Entry Script Rule

The experiment and production calibration entrypoints should remain thin:

- CLI parsing
- dataset loading
- method enumeration
- ranking / selection
- reporting

Shared data logic should stay in helpers.

## Script Responsibilities

### `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`

Repurpose this script from legacy-recovery ranking to modern-window method selection:

- production ranking uses the `2018` to `2024` fit window
- legacy `2014` and `2016` outputs remain diagnostic only
- report:
  - fitted coefficients
  - admissibility status
  - preferred-band status
  - in-window error
  - yearly anchor diagnostics
  - out-of-window diagnostic behavior on `2014` and `2016`

### `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`

This becomes the production calibration entrypoint for `v4.2`:

- accept NMG yearly files covering `2018` to `2024`
- accept PPD files needed to construct the 2-year signals for `2018` to `2024`
- run only the locked winning method family
- print:
  - `HPA_EXPECTATION_FACTOR`
  - `HPA_EXPECTATION_CONST`
  - chosen survey mapping
  - chosen signal method
  - yearly survey means
  - yearly HPA signals
  - plausibility status
  - fit-window diagnostics

## Required Outputs

The method-search and production scripts must make the following easy to recover:

- exact file inputs used
- fit years used
- chosen method family
- final `factor` and `const`
- coefficient plausibility classification
- yearly observed survey expectations
- yearly predictor signal values
- in-window regression error
- diagnostic-only behavior on `2014` and `2016`

## `v4.2` Snapshot Workflow

After the production calibration yields the final pair:

1. create `input-data-versions/v4.2` by copying forward `v4.1`
2. update only:
   - `HPA_EXPECTATION_FACTOR`
   - `HPA_EXPECTATION_CONST`
3. preserve all other `v4.1` inputs unchanged unless another approved calibration task explicitly changes them

## Validation And Release Workflow

The calibration is not complete until the repo contains the normal release artifacts:

1. run the production calibration script on the private datasets
2. create `input-data-versions/v4.2`
3. run `bash input-data-versions/validate.sh v4.2`
4. publish `input-data-versions/validation/v4.2.json`
5. run a full model output into `Results/v4.2-output`
6. compare headline behavior against `v4.1`

Downstream model behavior is not the fitting objective, but it remains a release gate. If `v4.2` behaves implausibly, revisit the admissibility and preferred-band choice rules rather than hand-editing the final coefficients.

## Version Notes Requirements

`input-data-versions/version-notes.json` must include a new comprehensive `v4.2` entry covering:

- version id and snapshot folder
- human description of the HPA expectation update
- updated data sources
- calibration script path(s)
- changed config parameters
- parameter-level change records
- method-variation entry documenting:
  - `2018` to `2024` fit window
  - chosen survey mapping
  - chosen signal method
  - plausibility rationale
  - why this replaced the legacy-recovery framing
- completed validation metrics once known

## Risks And Assumptions

- Seven production anchors are still a small sample, so the calibration should stay simple and strongly constrained.
- `boe39` remains a survey-band proxy for expectations rather than a continuous measure.
- The preferred-band plausibility rule is a guardrail, not a proof that the coefficients are economically correct.
- Earlier legacy years may not line up with the modern fit, and that is acceptable because `v4.2` is explicitly a modern recalibration.

## Success Criteria

The work is successful when:

- the repo can reproduce a `2018` to `2024` HPA expectation fit from private datasets
- the selected method is simple and explicitly justified
- the final coefficients are admissible and preferably inside the preferred band
- `input-data-versions/v4.2` exists with only the intended config changes
- validation and a full `Results/v4.2-output` run are produced
- `version-notes.json`, changelog, and script-structure docs fully describe what changed and why
