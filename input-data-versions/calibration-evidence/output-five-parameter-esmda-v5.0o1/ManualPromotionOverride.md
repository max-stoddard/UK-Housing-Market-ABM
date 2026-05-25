# v5.0o1 Manual Promotion Override
Author: Max Stoddard

## Decision
- `v5.0o1` was created by explicit user-directed promotion of the best HPI-constrained ES-MDA candidate.
- The source snapshot is `v4.26`.
- The promoted candidate is global ES-MDA iteration `3`, member `7`.
- This promotion intentionally does not use the rejected snapped local-refinement candidate.

## Promoted Parameters
- `PSYCHOLOGICAL_COST_OF_RENTING = 0.25`
- `SENSITIVITY_RENT_OR_PURCHASE = 0.0014`
- `BTL_PROBABILITY_MULTIPLIER = 1.825`
- `BTL_CHOICE_INTENSITY = 100`
- `MARKET_AVERAGE_PRICE_DECAY = 0.5`

## Guardrail Status
- The automated calibration summary has `createdOutputVersion = false`.
- The automated local-refinement promotion has `promotionAccepted = false`.
- Summary warnings:
  - Composite validation loss improved, but strategic metrics degraded materially: `core_hpiStd`.
  - No snapped local-refinement candidate improved total loss without HPI regression; output version was not created.
- The promoted iteration `3`, member `7` candidate is marked `hpiConstrainedEligible = true`.
- The promoted candidate's HPI constrained metric deltas all improved relative to `v4.26`:
  - `core_hpiMean = -0.08827660090626732`
  - `core_hpiStd = -0.046577414707801135`
  - `core_hpiCyclePeriod = -0.0818447984939259`

## Campaign Loss Comparison
- Baseline `v4.26` campaign loss: `0.5743372296753784`
- Promoted candidate campaign loss: `0.5073951690442934`
- Delta: `-0.06694206063108499`
- Percent delta: `-11.655532%`
- Baseline status counts: `pass=6`, `warn=0`, `fail=14`
- Promoted candidate status counts: `pass=7`, `warn=2`, `fail=11`

## Canonical Validation After Override
- Command:
```bash
bash input-data-versions/validate.sh v5.0o1 --output-dir tmp/validation/v5.0o1 --workers 20
```
- Tracked 2024 validation:
  - `overallCompositeLoss = 0.5501176226064236`
  - status counts: `pass=7`, `warn=0`, `fail=13`
- Current `v4.26` tracked 2024 validation comparison:
  - `v4.26 overallCompositeLoss = 0.5743372296753784`
  - delta: `-0.024219607068954763`
  - percent delta: `-4.216966%`
  - status counts changed from `pass=6`, `warn=0`, `fail=14` to `pass=7`, `warn=0`, `fail=13`

## Interpretation
- `v5.0o1` should be described as a manual promotion of an HPI-constrained global ES-MDA candidate, not as an automated snapped-local-refinement acceptance.
- The promotion positively improves the model under the requested 2024 family-aware validation objective: aggregate campaign loss improves, all HPI constrained metrics improve, and canonical tracked validation improves versus the current `v4.26` baseline.
- The rejected snapped local-refinement path remains useful diagnostic evidence, but it is not the promoted parameter set.
