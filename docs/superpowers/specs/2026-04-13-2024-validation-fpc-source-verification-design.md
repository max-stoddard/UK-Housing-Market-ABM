# 2024 Validation FPC Source Verification Design

**Author:** Max Stoddard
**Date:** 2026-04-13
**Status:** Approved
**Scope:** `.worktrees/validation-framework-2024/scripts/python/validation/model/`, `.worktrees/validation-framework-2024/scripts/python/tests/`, optional dashboard summary/schema updates inside `.worktrees/validation-framework-2024`

## Problem

The current 2024 validation framework implementation in `.worktrees/validation-framework-2024` hard-codes macro target bands in `scripts/python/validation/model/targets_2024.py` with generic labels such as `Official 2024 macro indicator target`.

That creates three methodology problems:
- the catalog does not preserve exact provenance for official macro targets
- there is no machine-checkable validation that the current values match the June 2024 FPC core indicators source
- several current `core_indicator` metrics appear to claim FPC-style support even though the June 2024 source does not contain a clean matching indicator

This must be fixed before the framework can be treated as a defensible 2024 validation methodology.

## Goals

- Make every FPC-backed macro target in `targets_2024.py` traceable to `private-datasets/cis/fpc-core-indicators-june-2024.pdf`.
- Use `private-datasets/cis/fpc-core-indicators-june-2024.txt` as the practical extraction aid for the locked source snapshot.
- Separate official sourced values from methodology-owned validation bands.
- Add a reproducible verifier that fails when the validation catalog drifts from the locked June 2024 FPC evidence.
- Mark unsupported FPC metrics honestly rather than leaving generic or speculative source labels in the catalog.
- Keep all design and implementation work scoped to `.worktrees/validation-framework-2024`.

## Non-Goals

- Replacing the broader 2024 validation framework methodology.
- Parsing the PDF at runtime during normal validation runs.
- Extending the source set beyond the June 2024 FPC document for this design.
- Changing the household JSD metrics away from WAS Round 8.

## Design Summary

Add a locked FPC evidence layer alongside the runtime target catalog.

The design uses two layers:
- a structured source snapshot derived from `private-datasets/cis/fpc-core-indicators-june-2024.txt`
- the runtime validation catalog in `targets_2024.py`

The source snapshot becomes the authoritative record of what the June 2024 FPC source actually says. The runtime catalog must reference that source snapshot explicitly for every supported `core_indicator`.

No metric may claim FPC provenance unless the June 2024 source contains a clean mapping for it.

## Source-Of-Truth Model

Introduce explicit provenance metadata for macro metrics.

Each supported FPC-backed metric should carry:
- `sourceDocumentPath`
- `sourceTextPath`
- `sourceTable`
- `sourcePage`
- `sourceIndicatorLabel`
- `sourceValue`
- `sourceAsOf`
- `sourceUnits`
- `mappingStatus`
- `bandMethod`
- `bandNotes`

Recommended `mappingStatus` values:
- `exact_match`: the model metric maps directly to the FPC indicator label
- `derived_match`: the model metric name differs, but the mapping is explicit and defensible
- `unsupported`: no clean June 2024 FPC mapping exists for that metric

The catalog must also distinguish:
- `sourceValue`: the exact official value from the FPC source
- `targetBand`: the framework acceptance band used for validation scoring

This is a critical methodology distinction. The source value is evidence. The target band is a modeling choice.

## Locked June 2024 FPC Support Outcome

The June 2024 FPC source supports the following current `core_indicator` metrics:
- `core_mortgageApprovals`
- `core_housingTransactions`
- `core_debtToIncome`, but only if remapped to FPC `Household debt to income ratio`
- `core_housePriceGrowth`
- `core_priceToIncome`, but only if remapped to FPC `House price to household disposable income ratio`
- `core_interestRateSpread`, but only if remapped to FPC `Spreads on new owner-occupier mortgages with 2-year fix and 75% LTV`

The June 2024 FPC source does not provide a clean match for these current `core_indicator` metrics:
- `core_advancesToFTB`
- `core_advancesToHM`
- `core_advancesToBTL`
- `core_ooDebtToIncome`
- `core_rentalYield`

For this design, unsupported means unsupported. Those metrics must not claim FPC provenance unless a later methodology revision adds another official source.

## Locked Expected Official Values

The verifier should lock these June 2024 FPC values:
- `core_mortgageApprovals`: `61325`, `Mar 2024`
- `core_housingTransactions`: `84200`, `Mar 2024`
- `core_debtToIncome`: `133.8`, `2023Q4`, mapped from `Household debt to income ratio`
- `core_housePriceGrowth`: `1.1`, `Mar 2024`
- `core_priceToIncome`: `5.4`, `2023Q4`, mapped from `House price to household disposable income ratio`
- `core_interestRateSpread`: `0.53`, `Mar 2024`, mapped from `Spreads on new owner-occupier mortgages with 2-year fix and 75% LTV`

These values are distinct from the framework bands and must be preserved explicitly in the catalog and published summaries.

## Worktree-Local File Changes

Create:
- `scripts/python/validation/model/fpc_source_2024.py`
- `scripts/python/tests/test_validation_framework_fpc_sources.py`

Modify:
- `scripts/python/validation/model/schema.py`
- `scripts/python/validation/model/targets_2024.py`
- `scripts/python/validation/model/runner.py`
- `scripts/python/validation/model/publish.py`

Optional follow-on updates:
- `dashboard/shared/types.ts`
- `dashboard/src/pages/ValidationPage.tsx`

The implementation must stay within `.worktrees/validation-framework-2024`.

## Structured FPC Evidence Layer

`fpc_source_2024.py` should be a hand-curated, reviewable snapshot of the June 2024 source. It should not parse the PDF at runtime.

Recommended structure:
- `FpcSourceEntry`
- `MetricSourceMetadata`
- `FPC_SOURCE_2024_BY_METRIC_ID`

Each entry should include the exact indicator name, exact official value, date, units, source table, page number, and source file paths.

This makes the methodology reviewable in code and avoids brittle runtime parsing of private documents.

## Verifier Design

Add a focused verifier test:
- `scripts/python/tests/test_validation_framework_fpc_sources.py`

The verifier should:
1. load the locked FPC source snapshot
2. load `TARGET_CATALOG`
3. inspect every `core_indicator` metric
4. require explicit provenance metadata
5. require a valid `mappingStatus`
6. require an FPC source entry for every non-unsupported FPC metric
7. assert that `sourceValue`, `sourceAsOf`, `sourceIndicatorLabel`, `sourcePage`, and related source fields match the locked FPC evidence
8. assert that generic labels such as `Official 2024 macro indicator target` are not used
9. assert that `targetBand` is present only for supported metrics
10. assert that the methodology band contains the official source value unless an explicit methodology note documents a deliberate exception

This test is the hard gate against future drift.

## Runtime Summary And Publication Changes

The runner and publisher should propagate richer source metadata into the validation summary.

At minimum, each metric summary should expose:
- `sourceLabel`
- `sourceIndicatorLabel`
- `sourceValue`
- `sourceAsOf`
- `sourceUnits`
- `mappingStatus`
- `bandMethod`
- `bandNotes`

This preserves the distinction between official source evidence and methodology-owned scoring bands.

## Unsupported Metric Semantics

Unsupported metrics must remain visible in the validation summary with `status: "unsupported"`, but unsupported metrics must not silently behave like supported ones.

Rules:
- unsupported diagnostics are visible but excluded from family loss
- unsupported required metrics are a methodology error, not a soft warning
- if a currently required metric cannot be supported by the locked June 2024 FPC source, the framework must either remap it cleanly, downgrade it to diagnostic, or remove it from the locked required set

## Immediate Catalog Corrections Implied By This Design

This design implies at least these catalog corrections:
- `core_priceToIncome` cannot continue to claim FPC provenance with the current `7.0..9.0` values while the June 2024 FPC latest value is `5.4`
- `core_debtToIncome` is not defensibly labeled as `Mortgage Debt to Income` if its FPC source is `Household debt to income ratio`
- `core_advancesToFTB`, `core_advancesToHM`, `core_advancesToBTL`, `core_ooDebtToIncome`, and `core_rentalYield` must become unsupported unless a later methodology revision introduces another official source

## Recommended Minimum Implementation Order

1. Add the locked FPC source snapshot module.
2. Extend the schema to represent provenance and mapping status explicitly.
3. Update `targets_2024.py` to reference the locked source entries and mark unsupported metrics honestly.
4. Add the verifier test and make it fail on any generic or mismatched source metadata.
5. Propagate provenance fields through the runner and published summary JSON.
6. Optionally surface provenance in the dashboard UI.

## Success Criteria

This design is complete when:
- every supported macro target in `targets_2024.py` has exact June 2024 FPC provenance
- unsupported FPC claims have been removed from the catalog
- the locked verifier test catches future source drift
- the published validation summary distinguishes official source values from methodology-owned target bands
- all changes remain scoped to `.worktrees/validation-framework-2024`
