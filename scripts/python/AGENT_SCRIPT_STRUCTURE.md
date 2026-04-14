# Python Script Structure

**Author:** Max Stoddard

## Validation Framework

### `scripts/python/validation/model/`

The 2024 model validation framework lives under `scripts/python/validation/model/`. It owns the locked target catalog, metric extraction, scoring, multi-seed execution, and publication of tracked validation summaries.

### `scripts/python/validation/model/fpc_source_2024.py`

Locked June 2024 FPC source snapshot used to validate the macro target catalog. This module stores official indicator labels, dates, raw source values, normalized comparison values, and mapping status. It is reviewable provenance metadata, not a runtime PDF or TXT parser.

### Source provenance contract

- `targets_2024.py` must distinguish official source values from methodology-owned target bands.
- Supported FPC-backed metrics carry explicit source metadata including source paths, table, page, label, source value, and as-of date.
- Unsupported FPC metrics remain visible in validation summaries but are not scored.
- Validation summaries publish both the raw official source value and the normalized comparison value used by the framework.

### Runtime behavior

- `runner.py` emits provenance-rich metric summaries for both supported and unsupported core-indicator metrics.
- `publish.py` writes the same provenance fields into tracked JSON and transient CSV outputs.
- `fpc_source_2024.py` is the locked review surface for June 2024 FPC evidence; changes to it are methodology changes, not incidental refactors.

## NMG HPA Expectation Recalibration

### `scripts/python/helpers/nmg/hpa_expectation.py`

Owns `boe39` band mappings, weighted expectation aggregation, linear-fit helper, and the shared plausibility/RMSE helpers used by both the reproduction experiment and the production calibration entrypoint.

### `scripts/python/helpers/ppd/hpa_signal_methods.py`

Owns PPD row parsing for year/month-aware HPA work, explicit `Category A` filtering for the revised production path, base-year resolution, yearly signal assembly, and the small approved national HPA signal family:
- `java_like_annualised`
- `annual_mean_annualised`
- `annual_mean_cumulative`

### `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`

Authoritative method-selection surface for the revised `v4.2` HPA expectation calibration. It fits the production window `2018` to `2024`, holds the PPD predictor fixed to `Category A` plus `annual_mean_annualised`, ranks `midpoint_rounded` versus `midpoint_exact` by admissibility then preferred-band status then in-window RMSE then simplicity, and reports the rejected all-transactions comparison plus the strict `2020` to `2024` sensitivity fit.

Current locked default family:
- category filter: `Category A`
- survey mapping: `midpoint_exact`
- PPD signal: `annual_mean_annualised`

### `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`

Thin production calibration entrypoint that imports the locked revised method family from the experiment module without a silent methodology switch. It targets the `2018` to `2024` survey anchors, enforces `Category A` plus `annual_mean_annualised`, hard-fails inadmissible fits, and emits production-ready `HPA_EXPECTATION_FACTOR` / `HPA_EXPECTATION_CONST` plus anchor diagnostics.

### Contract

- The reproduction experiment is the method-selection surface.
- The production calibration entrypoint must import the locked default family from the experiment module rather than duplicating string literals independently.
- The revised `v4.2` production fit is `Category A` only + `annual_mean_annualised` + `midpoint_exact`, yielding `HPA_EXPECTATION_FACTOR = 0.1150752545` and `HPA_EXPECTATION_CONST = 0.0034084162` on the approved private datasets.
- The rejected all-transactions comparison remains a required diagnostic and was inadmissible on the real run (`factor = -0.0919792144`, `const = 0.0104582814`).
- `private-datasets/ppd/pp-2011.csv` and `private-datasets/ppd/pp.2012.csv` remain part of the canonical rerun commands because the early modern anchors still require historical fallback context when the preferred `t - 2` base is unavailable.
