# v5o2 Manual Promotion Override
Author: Max Stoddard

## Decision
- `v5o2` was created by explicit user-directed promotion of `v5.0o1` campaign iteration `3`, member `7`.
- The source snapshot is `v4.26`.
- This promotion uses the exact raw cached member parameters, not the rounded `v5.0o1` snapshot values.

## Promoted Parameters
- `PSYCHOLOGICAL_COST_OF_RENTING = 0.25061702205009445`
- `SENSITIVITY_RENT_OR_PURCHASE = 0.0014183438663974938`
- `BTL_PROBABILITY_MULTIPLIER = 1.8268011822613688`
- `BTL_CHOICE_INTENSITY = 100.67982683612807`
- `MARKET_AVERAGE_PRICE_DECAY = 0.5064990858425684`

## Validation Command
```bash
python3 -m scripts.python.validation.model.validate_input_data_version --version v5o2 --seeds 1,2,3,4,5,6,7,8,9,10 --workers 20 --output-dir tmp/validation/v5o2-10seed-3500 --n-steps 3500 --validation-window-start 500 --validation-window-end 3500 --allow-noncanonical-seeds
```

## 2024 Validation Comparison
- Baseline: cached `v4.26` 2024 validation, seeds `1..10`, window `500..3500`, rescored with the current catalog.
- `v4.26` 2024 overallCompositeLoss: `0.6137234580996009`
- `v5o2` 2024 overallCompositeLoss: `0.591986974767631`
- Delta: `-0.02173648333196989`
- Percent delta: `-3.541739%`
- HPI metric-loss deltas:
  - `core_hpiMean = -0.008146536511386848`
  - `core_hpiStd = +0.11241424289324455`
  - `core_hpiCyclePeriod = -0.10180994493677498`

## Interpretation
- `v5o2` should be described as a manual promotion of a cached `v5.0o1` campaign member using exact raw member parameters.
- The 10-seed 2024 validation improves aggregate loss versus `v4.26`, but `core_hpiStd` loss worsens in the fresh promoted-snapshot validation.
- This is validation-loss evidence only and should not be described as a general model-output improvement.
