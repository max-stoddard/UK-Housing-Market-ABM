# TuRBO Optimised Model v0o7 Evidence
Author: Max Stoddard

## Purpose
- Records the TuRBO-1 five-parameter output-calibration campaign from the Original model `v0` to the TuRBO Optimised Model `v0o7`.
- Uses the 2011/W3 v0-family validation profile as the primary objective.
- Presents `v0o7` as a valid improvement over the Original model under the 20-metric 2011 validation loss.
- Does not use 2024 validation as evidence for this v0-family decision.

## Model Roles
- Original model: `input-data-versions/v0`, the Carro et al. published parameterisation calibrated by SMM in *Heterogeneous Effects and Spillovers of Macroprudential Policy in an Agent-Based Model of the UK Housing Market*.
- TuRBO Optimised Model: `input-data-versions/v0o7`, the output-calibrated version found from the Original model with TuRBO and the 20-metric 2011 validation loss.

## Campaign
- Source snapshot: `v0`
- Output snapshot requested: `v0o7`
- Workflow: `five-parameter-turbo`
- Seeds: `1..10`
- Workers: `20`
- Candidate batch size: `2`
- Initial points: `20`
- Max evaluations: `120`
- `N_STEPS`: `3500`
- Validation window: `500..3500`
- CSV deletion after metric extraction: enabled

## Result
- `createdOutputVersion`: `true`
- Local-refinement promotion: `accepted`
- Recommendation status: valid TuRBO optimised model relative to the Original model
- Selected iteration/member: `28` / `108`
- Selected parameters: `{'PSYCHOLOGICAL_COST_OF_RENTING': '0.4', 'SENSITIVITY_RENT_OR_PURCHASE': '0.0013', 'BTL_PROBABILITY_MULTIPLIER': '1.825', 'BTL_CHOICE_INTENSITY': '130', 'MARKET_AVERAGE_PRICE_DECAY': '0.54'}`
- Selected overallCompositeLoss: `0.5211689956810397`
- Original model overallCompositeLoss: `0.5652252115924438`
- Loss improvement versus Original model: approximately `7.79%`
- Fail count improves from `15` to `13`
- Selected guardrail HPI metric-loss deltas versus Original model: `{'core_hpiStd': -0.10113609313370375, 'core_hpiCyclePeriod': -0.32145011345997854, 'core_hpiMean': -0.0546882242528135}`

## 2011 Reference Comparison
- `v0` overallCompositeLoss = `0.5652252115924438`
- `v0o7` overallCompositeLoss = `0.5211689956810397`
- `v0 -> v0o7` overallCompositeLoss delta = `-0.04405621591140407`
- `v0 -> v0o7` core_hpiStd metricLoss delta = `-0.10113609313370375`
- `v0 -> v0o7` core_hpiCyclePeriod metricLoss delta = `-0.32145011345997854`
- `v0 -> v0o7` core_hpiMean metricLoss delta = `-0.0546882242528135`

## Interpretation Boundary
- This evidence supports `v0o7` as the TuRBO Optimised Model for the approved SMM/TuRBO convergence comparison.
- The comparison narrative is against the Original model, not against intermediate output snapshots.
- Existing retained artifact files with intermediate-snapshot names remain in place for auditability and dashboard comparability.

## 2024 Tracked Validation
- `v0o7` tracked 2024 overallCompositeLoss = `0.7232788599876028`
- `v0o7` tracked 2024 status counts = `pass=5`, `warn=1`, `fail=14`
- The 2024 summary is retained for dashboard comparability and does not change the 2011 TuRBO optimisation interpretation.

## Retained Artifacts
- `OutputParameterTurboCalibrationSummary.json`
- `OutputParameterTurboMetadata.json`
- `InitialDesign.csv`
- `TurboEvaluatedMembers.csv`
- `LocalRefinementMembers.csv`
- `AllEvaluatedMembers.csv`
- `ValidationComparison-v0o7-vs-v0-2011-10seed-500-3500.csv`
- `ValidationComparison-v0o7-vs-v0o2-2011-10seed-500-3500.csv`
- `reproduce-command.sh`
- `input-data-versions/validation-overlays/v0o7-2011.json`
- `input-data-versions/validation/v0o7.json`
