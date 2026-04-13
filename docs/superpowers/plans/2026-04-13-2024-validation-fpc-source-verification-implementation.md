# 2024 Validation FPC Source Verification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 2024 validation catalog in `.worktrees/validation-framework-2024` explicitly traceable to the June 2024 FPC core indicators source, downgrade unsupported FPC claims honestly, and lock the result behind reproducible tests.

**Architecture:** Add a locked Python source snapshot for the June 2024 FPC evidence, then extend the validation schema and target catalog so each `core_indicator` carries explicit provenance and mapping status. Keep the runtime validation flow in Python, publish richer source metadata into validation summaries, and avoid runtime parsing of the private PDF/TXT by treating the source paths as provenance strings rather than files the worktree must open.

**Tech Stack:** Python 3 `unittest`, existing validation framework modules under `scripts/python/validation/model/`, JSON publication under `input-data-versions/validation/`, Markdown documentation.

**Spec:** `docs/superpowers/specs/2026-04-13-2024-validation-fpc-source-verification-design.md`
**Implementation discipline:** Follow `@superpowers/test-driven-development` task-by-task and `@superpowers/verification-before-completion` before claiming the work is done.
**Workspace rule:** Only touch files under `.worktrees/validation-framework-2024`. Do not edit the parent checkout.

---

## Scope Decision

Keep this as one implementation plan. The source snapshot, target catalog, summary builder, publisher, and Python documentation form one contract; splitting them would create intermediate states where provenance fields exist in one layer but not the others.

Dashboard changes are intentionally out of scope for this plan. The current TypeScript summary reader ignores unknown JSON fields, so source-verification can land cleanly without forcing frontend changes.

## File Structure

### Create

- `scripts/python/validation/model/fpc_source_2024.py`
  Locked June 2024 FPC source snapshot with exact indicator labels, raw official values, normalized comparison values, dates, units, table/page metadata, and mapping status helpers.
- `scripts/python/tests/test_validation_framework_fpc_sources.py`
  Hard-gate tests for the supported/unsupported matrix, exact official values, target-catalog provenance, and the removal of generic source labels.

### Modify

- `scripts/python/validation/model/schema.py`
  Add provenance dataclasses and typed fields for mapping status, source metadata, raw source value, and normalized comparison value.
- `scripts/python/validation/model/targets_2024.py`
  Replace generic source labels with explicit FPC metadata, remap supported metrics cleanly, downgrade unsupported FPC claims to diagnostics, and fix bands that do not contain the sourced comparison value.
- `scripts/python/validation/model/runner.py`
  Publish provenance-rich metric summaries and keep source-backed-but-unbanded diagnostics visible as `unsupported`.
- `scripts/python/validation/model/publish.py`
  Write the new provenance columns into the transient CSV output without breaking existing summary generation.
- `scripts/python/validation/model/__init__.py`
  Export the new FPC source module types/constants needed by tests and callers.
- `scripts/python/tests/test_validation_framework_publish.py`
  Extend summary/publication tests to cover the new provenance fields and unsupported-diagnostic behavior.
- `scripts/python/AGENT_SCRIPT_STRUCTURE.md`
  Document the new `fpc_source_2024.py` source snapshot and the richer validation-summary provenance contract.

### Do Not Change

- `private-datasets/cis/fpc-core-indicators-june-2024.pdf`
- `private-datasets/cis/fpc-core-indicators-june-2024.txt`

The worktree does not own those files. Use them only as the external evidence source for the locked snapshot.

## Locked Method Decisions

Implement these design decisions exactly:

- Supported from the June 2024 FPC source:
  - `core_mortgageApprovals`
  - `core_housingTransactions`
  - `core_debtToIncome` mapped to `Household debt to income ratio`
  - `core_housePriceGrowth`
  - `core_priceToIncome` mapped to `House price to household disposable income ratio`
  - `core_interestRateSpread` mapped to `Spreads on new owner-occupier mortgages with 2-year fix and 75% LTV`
- Unsupported from the June 2024 FPC source:
  - `core_advancesToFTB`
  - `core_advancesToHM`
  - `core_advancesToBTL`
  - `core_ooDebtToIncome`
  - `core_rentalYield`
- Unsupported former required metrics must be downgraded to `diagnostic` so the framework remains runnable.
- Keep metric ids stable to avoid unnecessary downstream churn.
- Store both:
  - the raw official source value, eg `61325`
  - the normalized comparison value used by the validation framework, eg `61.325` when `scale=0.001`
- Preserve existing bands when they already contain the normalized source value.
- For supported metrics whose current band excludes the normalized source value, widen the band minimally so the official comparison value is included:
  - `core_housingTransactions`: change band from `88.0..100.0` to `84.2..100.0`
  - `core_priceToIncome`: change band from `7.0..9.0` to `5.4..9.0`
- Keep `core_interestRateSpread` source-backed but unbanded in this plan. It should publish provenance metadata but remain `unsupported` at runtime until a separate band-methodology change is approved.

## Task 1: Lock The June 2024 FPC Evidence Layer

**Files:**
- Create: `scripts/python/tests/test_validation_framework_fpc_sources.py`
- Create: `scripts/python/validation/model/fpc_source_2024.py`
- Modify: `scripts/python/validation/model/schema.py`
- Modify: `scripts/python/validation/model/__init__.py`

- [ ] **Step 1: Write the failing source-snapshot tests**

```python
import unittest

from scripts.python.validation.model.fpc_source_2024 import (
    FPC_SOURCE_2024_BY_METRIC_ID,
    SUPPORTED_FPC_METRIC_IDS,
    UNSUPPORTED_FPC_METRIC_IDS,
)


class TestValidationFrameworkFpcSources(unittest.TestCase):
    def test_locked_support_matrix_matches_june_2024_source(self) -> None:
        self.assertEqual(
            SUPPORTED_FPC_METRIC_IDS,
            (
                "core_mortgageApprovals",
                "core_housingTransactions",
                "core_debtToIncome",
                "core_housePriceGrowth",
                "core_priceToIncome",
                "core_interestRateSpread",
            ),
        )
        self.assertEqual(
            UNSUPPORTED_FPC_METRIC_IDS,
            (
                "core_advancesToFTB",
                "core_advancesToHM",
                "core_advancesToBTL",
                "core_ooDebtToIncome",
                "core_rentalYield",
            ),
        )

    def test_locked_official_values_capture_raw_and_comparison_units(self) -> None:
        mortgage = FPC_SOURCE_2024_BY_METRIC_ID["core_mortgageApprovals"]
        self.assertEqual(mortgage.source_indicator_label, "Mortgage approvals")
        self.assertEqual(mortgage.raw_source_value, 61325.0)
        self.assertEqual(mortgage.normalized_source_value, 61.325)
        self.assertEqual(mortgage.source_as_of, "Mar 2024")
```

- [ ] **Step 2: Run the new tests and verify they fail for missing modules or symbols**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_fpc_sources -v`
Expected: `ImportError` or `AttributeError` for `fpc_source_2024` and the new schema/types.

- [ ] **Step 3: Implement the provenance schema and locked FPC source snapshot**

```python
from dataclasses import dataclass
from typing import Literal

MappingStatus = Literal["exact_match", "derived_match", "unsupported"]


@dataclass(frozen=True)
class MetricSourceMetadata:
    source_document_path: str
    source_text_path: str
    source_table: str
    source_page: int
    source_indicator_label: str
    raw_source_value: float | None
    normalized_source_value: float | None
    source_units: str
    comparison_units: str
    source_as_of: str | None
    mapping_status: MappingStatus
    band_method: str | None = None
    band_notes: str | None = None
```

Implement `FPC_SOURCE_2024_BY_METRIC_ID` with exact entries for the six supported metrics and helper tuples for the supported/unsupported ids.

- [ ] **Step 4: Re-run the source-snapshot tests and make them pass**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_fpc_sources -v`
Expected: `OK`

- [ ] **Step 5: Commit the source-layer change**

```bash
git add scripts/python/tests/test_validation_framework_fpc_sources.py scripts/python/validation/model/fpc_source_2024.py scripts/python/validation/model/schema.py scripts/python/validation/model/__init__.py
git commit -m "test [MS]: lock June 2024 FPC source evidence for validation metrics"
```

## Task 2: Migrate The Target Catalog To Explicit Provenance

**Files:**
- Modify: `scripts/python/tests/test_validation_framework_fpc_sources.py`
- Modify: `scripts/python/validation/model/targets_2024.py`
- Modify: `scripts/python/validation/model/schema.py`

- [ ] **Step 1: Extend the failing verifier tests to assert target-catalog behavior**

```python
from scripts.python.validation.model.targets_2024 import TARGETS_BY_ID


def test_target_catalog_uses_locked_fpc_metadata(self) -> None:
    self.assertEqual(TARGETS_BY_ID["core_debtToIncome"].label, "Household Debt to Income")
    self.assertEqual(TARGETS_BY_ID["core_priceToIncome"].target_band.lower, 5.4)
    self.assertEqual(TARGETS_BY_ID["core_housingTransactions"].target_band.lower, 84.2)
    self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].requirement, "diagnostic")
    self.assertIsNone(TARGETS_BY_ID["core_advancesToFTB"].target_band)
    self.assertNotEqual(TARGETS_BY_ID["core_mortgageApprovals"].source_label, "Official 2024 macro indicator target")


def test_supported_bands_contain_normalized_official_values(self) -> None:
    for metric_id in (
        "core_mortgageApprovals",
        "core_housingTransactions",
        "core_debtToIncome",
        "core_housePriceGrowth",
        "core_priceToIncome",
    ):
        metric = TARGETS_BY_ID[metric_id]
        source = metric.source_metadata
        self.assertIsNotNone(metric.target_band)
        self.assertLessEqual(metric.target_band.lower, source.normalized_source_value)
        self.assertGreaterEqual(metric.target_band.upper, source.normalized_source_value)
```

- [ ] **Step 2: Run the verifier tests and confirm they fail on the current generic catalog**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_fpc_sources -v`
Expected: failures on label text, missing `source_metadata`, unsupported metrics still marked `required`, and invalid bands.

- [ ] **Step 3: Update `targets_2024.py` to use explicit provenance and honest unsupported statuses**

Implement these exact catalog changes:
- attach `source_metadata=FPC_SOURCE_2024_BY_METRIC_ID[...]` to all supported FPC-backed metrics
- rename labels:
  - `core_debtToIncome` -> `Household Debt to Income`
  - `core_priceToIncome` -> `House Price to Household Disposable Income`
- downgrade unsupported former required metrics to `requirement="diagnostic"`
- set `target_band=None` for unsupported metrics
- set `target_band=TargetBand(lower=84.2, upper=100.0)` for `core_housingTransactions`
- set `target_band=TargetBand(lower=5.4, upper=9.0)` for `core_priceToIncome`
- leave `core_interestRateSpread` diagnostic with `target_band=None`, but attach its source metadata with `mapping_status="derived_match"`

Use explicit, non-generic source labels such as:

```python
source_label="Bank of England FPC core indicators, June 2024"
```

- [ ] **Step 4: Re-run the verifier tests and make them pass**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_fpc_sources -v`
Expected: `OK`

- [ ] **Step 5: Commit the catalog migration**

```bash
git add scripts/python/tests/test_validation_framework_fpc_sources.py scripts/python/validation/model/targets_2024.py scripts/python/validation/model/schema.py
git commit -m "fix [MS]: align 2024 validation targets with June FPC evidence"
```

## Task 3: Publish Provenance-Rich Validation Summaries

**Files:**
- Modify: `scripts/python/tests/test_validation_framework_publish.py`
- Modify: `scripts/python/validation/model/runner.py`
- Modify: `scripts/python/validation/model/publish.py`

- [ ] **Step 1: Write the failing summary/publication tests**

Add assertions to `test_build_validation_summary_rejects_missing_required_target_metadata` and a new synthetic summary test:

```python
def test_build_validation_summary_emits_source_provenance_fields(self) -> None:
    summary = build_validation_summary(
        version="v-test",
        seed_results=self._synthetic_seed_results(),
        seeds=[1, 2, 3, 4, 5, 6, 7, 8],
    )
    metric = next(item for item in summary["metrics"] if item["metricId"] == "core_mortgageApprovals")
    self.assertEqual(metric["sourceIndicatorLabel"], "Mortgage approvals")
    self.assertEqual(metric["rawSourceValue"], 61325.0)
    self.assertEqual(metric["sourceValue"], 61.325)
    self.assertEqual(metric["mappingStatus"], "exact_match")


def test_source_backed_unbanded_diagnostic_remains_unsupported(self) -> None:
    summary = build_validation_summary(
        version="v-test",
        seed_results=self._synthetic_seed_results(),
        seeds=[1, 2, 3, 4, 5, 6, 7, 8],
    )
    metric = next(item for item in summary["metrics"] if item["metricId"] == "core_interestRateSpread")
    self.assertEqual(metric["status"], "unsupported")
    self.assertEqual(metric["sourceIndicatorLabel"], "Spreads on new owner-occupier mortgages with 2-year fix and 75% LTV")
```

- [ ] **Step 2: Run the publication tests and verify they fail for missing fields**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_publish -v`
Expected: failures on missing provenance fields in `build_validation_summary` and missing CSV columns in `publish.py`.

- [ ] **Step 3: Implement provenance propagation in the runner and publisher**

Update `build_validation_summary` to emit these fields for every metric:
- `sourceIndicatorLabel`
- `sourceDocumentPath`
- `sourceTextPath`
- `sourceTable`
- `sourcePage`
- `rawSourceValue`
- `sourceValue`
- `sourceAsOf`
- `sourceUnits`
- `comparisonUnits`
- `mappingStatus`
- `bandMethod`
- `bandNotes`

Keep runtime behavior consistent:
- metrics with `target_band is None` publish provenance but stay `status="unsupported"`
- only metrics with a band compute `insideRate`, `normalizedDistance`, `normalizedIqr`, and `metricLoss`

Extend `_write_metrics_csv` to include the new provenance columns.

- [ ] **Step 4: Re-run the publication tests and make them pass**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_publish -v`
Expected: `OK`

- [ ] **Step 5: Run the full validation-framework Python test slice**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_scoring scripts.python.tests.test_validation_framework_extractors scripts.python.tests.test_validation_framework_publish scripts.python.tests.test_validation_framework_fpc_sources -v`
Expected: `OK`

- [ ] **Step 6: Commit the runtime/publication changes**

```bash
git add scripts/python/tests/test_validation_framework_publish.py scripts/python/validation/model/runner.py scripts/python/validation/model/publish.py
git commit -m "fix [MS]: publish June FPC provenance in validation summaries"
```

## Task 4: Update Python Agent Documentation For The New Provenance Contract

**Files:**
- Modify: `scripts/python/AGENT_SCRIPT_STRUCTURE.md`

- [ ] **Step 1: Add a failing documentation checklist in the commit message scratchpad or working notes**

Document these required doc updates before editing:
- mention `scripts/python/validation/model/fpc_source_2024.py`
- explain that FPC provenance is locked in code, not parsed at runtime
- explain that validation summaries now distinguish raw official source values from normalized comparison values
- explain that unsupported FPC metrics remain visible but unscored

- [ ] **Step 2: Update the Python script architecture guide**

Add a short section like:

```markdown
### `scripts/python/validation/model/fpc_source_2024.py`

Locked June 2024 FPC source snapshot used to validate the macro target catalog. This module stores official indicator labels, dates, raw values, normalized comparison values, and mapping status. It is reviewable source metadata, not a runtime PDF/TXT parser.
```

- [ ] **Step 3: Verify the doc mentions the new module and summary contract**

Run: `rg -n "fpc_source_2024|normalized comparison values|unsupported" scripts/python/AGENT_SCRIPT_STRUCTURE.md`
Expected: matching lines for the new source snapshot and provenance behavior.

- [ ] **Step 4: Commit the documentation update**

```bash
git add scripts/python/AGENT_SCRIPT_STRUCTURE.md
git commit -m "docs [MS]: document FPC provenance contracts for validation scripts"
```

## Final Verification

- [ ] **Step 1: Run the complete targeted Python test slice again**

Run: `python3 -m unittest scripts.python.tests.test_validation_framework_scoring scripts.python.tests.test_validation_framework_extractors scripts.python.tests.test_validation_framework_publish scripts.python.tests.test_validation_framework_fpc_sources -v`
Expected: `OK`

- [ ] **Step 2: Inspect the worktree diff for scope control**

Run: `git status --short`
Expected: only the planned worktree-local Python/docs files are changed.

- [ ] **Step 3: Summarize the locked metric outcome in the handoff**

Include:
- supported FPC-backed metrics
- unsupported metrics downgraded to diagnostics
- exact official values now locked in code
- target bands widened only where needed to contain the official comparison value
