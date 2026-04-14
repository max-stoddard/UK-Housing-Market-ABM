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

Owns `boe39` band mappings, weighted expectation aggregation, and the linear-fit helper used by both the reproduction experiment and the production calibration entrypoint.

### `scripts/python/helpers/ppd/hpa_signal_methods.py`

Owns PPD row parsing for year/month-aware HPA work, explicit base-year resolution, and the small approved national HPA signal family:
- `java_like_annualised`
- `annual_mean_annualised`
- `annual_mean_cumulative`

### `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`

Authoritative reproduction experiment for `HPA_EXPECTATION_FACTOR` and `HPA_EXPECTATION_CONST`. It searches the approved national method space, including explicit pairing rules, ranks candidates by legacy distance then 2016 holdout error then simplicity, and records the locked default family for production reuse.

Current locked default family:
- pairing rule: `previous_available`
- survey mapping: `midpoint_rounded`
- PPD signal: `annual_mean_annualised`

### `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`

Thin production calibration entrypoint that reuses the locked method family from the reproduction experiment without a silent methodology switch. It currently targets the 2014 + 2024 survey anchors and emits production-ready `HPA_EXPECTATION_FACTOR` / `HPA_EXPECTATION_CONST` plus anchor diagnostics.

### Contract

- The reproduction experiment is the method-selection surface.
- The production calibration entrypoint must import the locked default family from the experiment module rather than duplicating string literals independently.
- `private-datasets/ppd/pp-2011.csv` is required for the current reproduction/production commands because the `2014 -> 2012` pairing falls back to `2011` as the nearest available prior PPD base year.
