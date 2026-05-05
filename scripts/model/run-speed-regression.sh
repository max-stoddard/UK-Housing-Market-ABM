#!/usr/bin/env bash
# Snapshot-local regression harness for model-speed work.
# Author: Max Stoddard

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/model-speed-lib.sh"

LOG_TAG="SPEED-REG"
LOG_COLOR="\033[1;33m"
model_speed_log_init

usage() {
  cat <<EOF
Usage: $(basename "$0") --snapshot <version> --mode <mode> --contract <exact|tolerance> --baseline-manifest <path> --output-root <dir>

Required arguments:
  --snapshot          Snapshot folder under input-data-versions
  --mode              e2e-default-10k-s1 | core-minimal-20k-s1
  --contract          exact | tolerance
  --baseline-manifest Exact SHA-256 manifest path or tolerance-spec JSON path
  --output-root       Root directory for regression artifacts
EOF
}

snapshot=""
mode=""
contract=""
baseline_manifest=""
output_root=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot)
      snapshot="$2"
      shift 2
      ;;
    --mode)
      mode="$2"
      shift 2
      ;;
    --contract)
      contract="$2"
      shift 2
      ;;
    --baseline-manifest)
      baseline_manifest="$2"
      shift 2
      ;;
    --output-root)
      output_root="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      log_err "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${snapshot}" || -z "${mode}" || -z "${contract}" || -z "${baseline_manifest}" || -z "${output_root}" ]]; then
  usage
  exit 1
fi

if [[ "${contract}" != "exact" && "${contract}" != "tolerance" ]]; then
  log_err "--contract must be exact or tolerance."
  exit 1
fi

if [[ ! -f "${baseline_manifest}" ]]; then
  log_err "Baseline manifest/spec not found: ${baseline_manifest}"
  exit 1
fi

mode_file="$(model_speed_mode_file "${snapshot}" "${mode}")"
mkdir -p "${output_root}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_root="${output_root%/}/${snapshot}/${mode}/${contract}/${timestamp}"
generated_config_dir="$(model_speed_tmp_root)/generated-configs/${snapshot}/${mode}"
generated_config_dir="${generated_config_dir}/${timestamp}"
config_path="${generated_config_dir}/${snapshot}-${mode}.properties"
environment_txt="${run_root}/environment.txt"
candidate_dir="${run_root}/candidate"
report_path="${run_root}/regression-report.md"

log "Regression session root: ${run_root}"
log "Pinned mode definition: ${mode_file}"
log "Regression contract: ${contract}"
log "Baseline manifest/spec: ${baseline_manifest}"

mkdir -p "${run_root}"
model_speed_capture_environment "${environment_txt}" "${snapshot}" "${mode}" "${output_root}"
model_speed_materialize_config "${snapshot}" "${mode}" "${config_path}"
model_speed_ensure_compiled
model_speed_resolve_classpath >/dev/null

log "Running candidate model execution."
model_speed_run_model_once "${config_path}" "${candidate_dir}"

candidate_manifest="${candidate_dir}/model-output.sha256"
if [[ "${contract}" == "exact" ]]; then
  log "Comparing exact manifests."
  python3 "$(model_speed_python_helper)" exact-compare \
    --baseline-manifest "${baseline_manifest}" \
    --candidate-manifest "${candidate_manifest}" \
    --report-path "${report_path}"
else
  log "Running tolerance-based comparison."
  python3 "$(model_speed_python_helper)" tolerance-compare \
    --spec "${baseline_manifest}" \
    --candidate-dir "${candidate_dir}/model-output" \
    --report-path "${report_path}"
fi

log "Regression succeeded."
log "Artifacts:"
log "  environment: ${environment_txt}"
log "  candidate:   ${candidate_dir}/model-output"
log "  manifest:    ${candidate_manifest}"
log "  report:      ${report_path}"
