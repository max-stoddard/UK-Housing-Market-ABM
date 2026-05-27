# TuRBO v0o7 Evidence
Author: Max Stoddard

## Purpose
- Records the TuRBO-1 five-parameter output-calibration campaign from `v0` to requested `v0o7`.
- Uses the 2011/W3 v0-family validation profile as the primary objective.
- Does not use 2024 validation as evidence for this v0-family decision.

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
- Recommendation status: `evidence-only / not recommended`
- Reason: `v0o7` improves 2011 aggregate loss versus both `v0` and `v0o2`, but it materially regresses `core_hpiMean` metric loss versus the refreshed `v0o2` 2011 overlay.
- Selected iteration/member: `28` / `108`
- Selected parameters: `{'PSYCHOLOGICAL_COST_OF_RENTING': '0.4', 'SENSITIVITY_RENT_OR_PURCHASE': '0.0013', 'BTL_PROBABILITY_MULTIPLIER': '1.825', 'BTL_CHOICE_INTENSITY': '130', 'MARKET_AVERAGE_PRICE_DECAY': '0.54'}`
- Selected overallCompositeLoss: `0.5211689956810397`
- Selected guardrail HPI metric-loss deltas versus `v0`: `{'core_hpiStd': -0.10113609313370375, 'core_hpiCyclePeriod': -0.32145011345997854, 'core_hpiMean': -0.0546882242528135}`

## 2011 Reference Comparison
- `v0` overallCompositeLoss = `0.5652252115924438`
- `v0o2` overallCompositeLoss = `0.5359511617512418`
- `v0o7` overallCompositeLoss = `0.5211689956810397`
- `v0 -> v0o7` overallCompositeLoss delta = `-0.04405621591140407`
- `v0o2 -> v0o7` overallCompositeLoss delta = `-0.014782166070202107`
- `v0 -> v0o7` core_hpiStd metricLoss delta = `-0.10113609313370375`
- `v0o2 -> v0o7` core_hpiStd metricLoss delta = `-0.05496398628835513`
- `v0 -> v0o7` core_hpiCyclePeriod metricLoss delta = `-0.32145011345997854`
- `v0o2 -> v0o7` core_hpiCyclePeriod metricLoss delta = `-0.12857808827672268`
- `v0 -> v0o7` core_hpiMean metricLoss delta = `-0.0546882242528135`
- `v0o2 -> v0o7` core_hpiMean metricLoss delta = `0.10794880054042713`

## 2024 Tracked Validation
- `v0o7` tracked 2024 overallCompositeLoss = `0.7232788599876028`
- `v0o7` tracked 2024 status counts = `pass=5`, `warn=1`, `fail=14`
- The 2024 summary is retained for dashboard comparability and does not change the evidence-only recommendation status.

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
