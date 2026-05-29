# v0o3 Manual Promotion Override
Author: Max Stoddard

## Decision
- `v0o3` was created as the dashboard optimised 2011 branch by explicit user-directed guardrail override.
- The source snapshot is `v0`.
- The promoted candidate is local-refinement iteration `7`, member `20`.

## Promoted Parameters
- `PSYCHOLOGICAL_COST_OF_RENTING = 0.2`
- `SENSITIVITY_RENT_OR_PURCHASE = 0.0011`
- `BTL_PROBABILITY_MULTIPLIER = 1.13`
- `BTL_CHOICE_INTENSITY = 90`
- `MARKET_AVERAGE_PRICE_DECAY = 0.68`

## Guardrail Status
- The automated calibration summary has `createdOutputVersion = false`.
- The automated local-refinement promotion has `promotionAccepted = false`.
- Rejection reason: `strategic metric loss degraded beyond tolerance: core_hpiStd`.
- Campaign-summary `core_hpiStd` metric loss changed from baseline `0.3569167501789907` to candidate `0.9496982946237966`.
- The degradation delta was `0.5927815444448059`, above the configured `0.1` strategic-metric tolerance.

## Canonical Validation After Override
- Command:
```bash
bash input-data-versions/validate.sh v0o3 --output-dir tmp/validation/v0o3 --workers 20
```
- 2011 overlay:
  - `overallCompositeLoss = 0.43810048381538697`
  - status counts: `pass=8`, `warn=2`, `fail=10`
- Secondary 2024 tracked validation:
  - `overallCompositeLoss = 0.6551250164711795`
  - status counts: `pass=7`, `warn=1`, `fail=12`

## Interpretation
- `v0o3` replaces `v0o2` as the dashboard optimised 2011 branch by override.
- The retained evidence should not be used to claim a guardrail-accepted model-quality improvement.
- Any summary of `v0o3` should state that aggregate 2011/W3 loss improved while guarded house-price volatility regressed.
