# v0o6 Manual Promotion Override
Author: Max Stoddard

## Decision
- `v0o6` was created by explicit user-directed promotion of `v0o3` campaign iteration `1`, member `59`.
- The source snapshot is `v0`.
- This promotion uses the exact raw cached member parameters, not the snapped local-refinement candidate promoted in `v0o3`.

## Promoted Parameters
- `PSYCHOLOGICAL_COST_OF_RENTING = 0.44043118640535517`
- `SENSITIVITY_RENT_OR_PURCHASE = 0.0007341104261340001`
- `BTL_PROBABILITY_MULTIPLIER = 2.106407975979989`
- `BTL_CHOICE_INTENSITY = 106.05000372010099`
- `MARKET_AVERAGE_PRICE_DECAY = 0.5958665034502091`

## Validation Command
```bash
python3 -m scripts.python.validation.model.validate_input_data_version --version v0o6 --seeds 1,2,3,4,5,6,7,8,9,10 --workers 20 --output-dir tmp/validation/v0o6-10seed-3500 --n-steps 3500 --validation-window-start 500 --validation-window-end 3500 --allow-noncanonical-seeds
```

## 2011 Reference Validation Comparison
- Baseline: cached `v0` 2011 reference validation, seeds `1..10`, window `500..3500`, rescored with the current catalog.
- `v0` 2011 overallCompositeLoss: `0.5652252115924438`
- `v0o6` 2011 overallCompositeLoss: `0.5350597930294947`
- Delta: `-0.030165418562949047`
- Percent delta: `-5.336885%`
- HPI metric-loss deltas:
  - `core_hpiMean = +0.0730957919906657`
  - `core_hpiStd = -0.18023522321656262`
  - `core_hpiCyclePeriod = -0.3714501134599785`

## Interpretation
- `v0o6` should be described as a manual promotion of a cached `v0o3` campaign member.
- The 10-seed 2011 reference validation improves aggregate loss versus `v0`, while `core_hpiMean` loss worsens.
- This is validation-loss evidence only and should not be described as a general model-output improvement.
