# Five-Parameter ESMDA v0o3 Attempt Evidence
Author: Max Stoddard

## Purpose
- Records the attempted direct five-parameter ESMDA output-calibration campaign from `v0` to `v0o3`.
- The automated calibration did not create `input-data-versions/v0o3` because every snapped local-refinement candidate breached the configured promotion guardrails.
- This bundle is retained as failed-campaign calibration evidence. It does not document or imply a promoted model version.

## Campaign
- Source snapshot: `v0`
- Output snapshot requested: `v0o3`
- Validation profile: `validation-reference-v0-2011`
- Validation objective: `family_aware_metric_loss`
- Seeds: `1..10`
- Workers: `20`
- `N_STEPS`: `3500`
- Validation/calibration window: `500..3500`
- Ensemble size: `64`
- Assimilation steps: `6`
- Local refinement: top-n `10`, radius `1`, max candidates `100`
- RNG seed: `20260515`
- CSV deletion after metric extraction: enabled

## Parameters
- `PSYCHOLOGICAL_COST_OF_RENTING`
- `SENSITIVITY_RENT_OR_PURCHASE`
- `BTL_PROBABILITY_MULTIPLIER`
- `BTL_CHOICE_INTENSITY`
- `MARKET_AVERAGE_PRICE_DECAY`

`BTL_PROBABILITY_MULTIPLIER` was included directly in the ESMDA state vector rather than calibrated in a separate stage.

## Result
- `createdOutputVersion`: `false`
- No output version was promoted by this workflow.
- Local snapped candidates evaluated: `99`
- Local refinement seed runs: `990`
- Best rejected candidate:
  - `PSYCHOLOGICAL_COST_OF_RENTING = 0.2`
  - `SENSITIVITY_RENT_OR_PURCHASE = 0.0011`
  - `BTL_PROBABILITY_MULTIPLIER = 1.13`
  - `BTL_CHOICE_INTENSITY = 90`
  - `MARKET_AVERAGE_PRICE_DECAY = 0.68`
  - `overallCompositeLoss = 0.40352788427184727`
  - status counts: `pass=10`, `warn=0`, `fail=10`
- Campaign baseline `v0`:
  - `overallCompositeLoss = 0.5166098865546315`
  - status counts: `pass=4`, `warn=3`, `fail=13`
- Guardrail rejection:
  - `core_hpiStd` metric loss degraded from `0.3569167501789907` to `0.9496982946237966`.
  - The degradation delta `0.5927815444448059` exceeded the strategic-metric tolerance `0.1`.

The aggregate 2011/W3 loss improved, but the material `core_hpiStd` regression means this candidate should not be described as a guardrail-accepted model improvement.

## Reproduction
```bash
python3 -m scripts.python.calibration.output.output_parameter_esmda \
  --version v0 \
  --output-version v0o3 \
  --validation-year 2011 \
  --validation-objective family_aware_metric_loss \
  --validation-loss-error-std 1.0 \
  --seeds 1,2,3,4,5,6,7,8,9,10 \
  --workers 20 \
  --ensemble-size 64 \
  --assimilation-steps 6 \
  --rng-seed 20260515 \
  --n-steps 3500 \
  --validation-window-start 500 \
  --validation-window-end 3500 \
  --output-root tmp/output-calibration \
  --evidence-dir input-data-versions/calibration-evidence/output-five-parameter-esmda-v0o3 \
  --local-refinement-top-n 10 \
  --local-refinement-radius 1 \
  --local-refinement-max-candidates 100 \
  --delete-csv-after-metrics
```

## Retained Artifacts
- `OutputParameterEsmdaCalibrationSummary.json`
- `OutputParameterEsmdaMetadata.json`
- `AllEvaluatedMembers.csv`
- `LocalRefinementMembers.csv`
- `reproduce-command.sh`
- legacy alias artifacts retained for historical four-parameter tooling compatibility
