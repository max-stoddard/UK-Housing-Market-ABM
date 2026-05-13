#!/usr/bin/env bash
set -euo pipefail

# Summary:
#   Run production BUY* calibration v2 with hard plausibility gates.
# Purpose:
#   Emit model-ready BUY_SCALE/BUY_EXPONENT/BUY_MU/BUY_SIGMA from modern PSD/PPD policies.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
cd "${repo_root}"

workers="${PSD_BUY_V2_WORKERS:-16}"

python3 -m scripts.python.calibration.psd.psd_buy_budget_calibration_v2 \
  --quarterly-csv private-datasets/psd/2024/psd-quarterly-2024.csv \
  --ppd-csv-2024 private-datasets/ppd/pp-2024.csv \
  --target-year-psd 2024 \
  --ppd-status-mode a_only \
  --year-policy 2024_only \
  --guardrail-mode fail \
  --hard-p95-cap 15 \
  --exponent-max 1.0 \
  --median-target-curve 25000:6.5,50000:6.0,100000:5.4,150000:5.0,200000:4.8 \
  --tail-family pareto \
  --pareto-alpha-grid 1.2,1.4,1.6,1.8,2.0,2.5,3.0 \
  --objective-weight-grid-profile balanced \
  --fit-degradation-max 0.10 \
  --within-bin-points 11 \
  --quantile-grid-size 4000 \
  --ppd-mean-anchor-weight 4.0 \
  --fixed-exponent 1.0 \
  --income-open-upper-k 200 \
  --property-open-upper-k 2000 \
  --workers "${workers}" \
  "$@"
