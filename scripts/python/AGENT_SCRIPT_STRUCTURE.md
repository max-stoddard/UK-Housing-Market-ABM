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
