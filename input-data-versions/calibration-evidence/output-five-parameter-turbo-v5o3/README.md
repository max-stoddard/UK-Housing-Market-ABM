# TuRBO v5o3 Evidence
Author: Max Stoddard

## Purpose
- Records the TuRBO-1 five-parameter output-calibration campaign from `v4.26` to requested `v5o3`.
- Uses the 2024 validation profile as the primary objective.
- Compares the promoted result against both `v4.26` and `v5o2`; `v5o2` is not used as the source snapshot.

## Campaign
- Source snapshot: `v4.26`
- Output snapshot requested: `v5o3`
- Workflow: `five-parameter-turbo`
- Seeds: `1..10`
- Workers: `20`
- Candidate batch size: `2` (`2 candidates * 10 seeds = 20 Java runs per batch`)
- Initial points: `20`
- Max evaluations: `120`
- `N_STEPS`: `3500`
- Validation window: `500..3500`
- CSV deletion after metric extraction: enabled
- Promotion contract: strict aggregate-loss improvement and HPI non-regression versus `v4.26`

## Result
- `createdOutputVersion`: `True`
- Local-refinement promotion accepted: `True`
- Recommendation status: `recommended for review`
- Selected parameters: `{'PSYCHOLOGICAL_COST_OF_RENTING': '0.35', 'SENSITIVITY_RENT_OR_PURCHASE': '0.0011', 'BTL_PROBABILITY_MULTIPLIER': '1.75', 'BTL_CHOICE_INTENSITY': '110', 'MARKET_AVERAGE_PRICE_DECAY': '0.5'}`
- Selected campaign overallCompositeLoss: `0.5864457551658543`
- Selected campaign HPI metric-loss deltas versus `v4.26`: `{'core_hpiStd': -0.16457527693400126, 'core_hpiCyclePeriod': -0.03598777885830695, 'core_hpiMean': -0.06996748134065989}`
- Fresh validation overallCompositeLoss: `0.5864457551658543`

## 2024 Comparison
- `overallCompositeLoss` versus `v4.26`: baselineLoss `0.6137234580996009`, v5o3Loss `0.5864457551658543`, delta `-0.02727770293374665`
- `core_hpiMean` versus `v4.26`: baselineLoss `0.6300179487280769`, v5o3Loss `0.560050467387417`, delta `-0.06996748134065989`
- `core_hpiStd` versus `v4.26`: baselineLoss `0.498968956647887`, v5o3Loss `0.3343936797138857`, delta `-0.16457527693400126`
- `core_hpiCyclePeriod` versus `v4.26`: baselineLoss `0.9023983608041528`, v5o3Loss `0.8664105819458459`, delta `-0.03598777885830695`
- `overallCompositeLoss` versus `v5o2`: baselineLoss `0.5919869747680289`, v5o3Loss `0.5864457551658543`, delta `-0.005541219602174574`
- `core_hpiMean` versus `v5o2`: baselineLoss `0.621871412217045`, v5o3Loss `0.560050467387417`, delta `-0.061820944829627966`
- `core_hpiStd` versus `v5o2`: baselineLoss `0.6113831995407881`, v5o3Loss `0.3343936797138857`, delta `-0.2769895198269024`
- `core_hpiCyclePeriod` versus `v5o2`: baselineLoss `0.800588415867187`, v5o3Loss `0.8664105819458459`, delta `0.06582216607865887`

## Retained Artifacts
- `OutputParameterTurboCalibrationSummary.json`
- `OutputParameterTurboMetadata.json`
- `InitialDesign.csv`
- `TurboEvaluatedMembers.csv`
- `LocalRefinementMembers.csv`
- `AllEvaluatedMembers.csv`
- `validation-v5o3-2024.json`
- `ValidationComparison-v5o3-vs-v4.26-2024-10seed-500-3500.csv`
- `ValidationComparison-v5o3-vs-v5o2-2024-10seed-500-3500.csv`
- `reproduce-command.sh`
