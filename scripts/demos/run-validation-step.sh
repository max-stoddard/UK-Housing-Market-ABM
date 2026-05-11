#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/../helpers/log.sh"
LOG_TAG="VALIDATE"
LOG_COLOR="\033[1;36m"
log_init

if [[ $# -ne 5 ]]; then
  log_err "Usage: $0 <input_version> <output_dir> <dataset_const> <expected_dataset> <expected_file>"
  exit 1
fi

input_version="$1"
output_dir="$2"
dataset_const="$3"
expected_dataset="$4"
expected_file="$5"

repo_root="$(cd "${script_dir}/../.." && pwd)"
cd "${repo_root}"
maven_bin="${MAVEN_BIN:-${repo_root}/mvnw}"

show_config_summary() {
  python3 - <<'PY'
from scripts.python.helpers.was import config

print(f"WAS_DATASET={config.WAS_DATASET}")
print(f"WAS_DATA_FILENAME={config.WAS_DATA_FILENAME}")
print(f"WAS_RESULTS_RUN_SUBDIR={config.WAS_RESULTS_RUN_SUBDIR}")
print(f"WAS_DATA_ROOT={config.WAS_DATA_ROOT}")
print(f"WAS_RESULTS_ROOT={config.WAS_RESULTS_ROOT}")
print(f"WAS_VALIDATION_PLOTS={config.WAS_VALIDATION_PLOTS}")
PY
}

verify_config() {
  local expected_dataset="$1"
  local expected_file="$2"
  python3 - <<PY
from scripts.python.helpers.was import config

expected_dataset = "${expected_dataset}"
expected_file = "${expected_file}"

if config.WAS_DATASET != expected_dataset:
    raise SystemExit(
        f"Config check failed: expected WAS_DATASET={expected_dataset}, got {config.WAS_DATASET}"
    )
if config.WAS_DATA_FILENAME != expected_file:
    raise SystemExit(
        f"Config check failed: expected WAS_DATA_FILENAME={expected_file}, got {config.WAS_DATA_FILENAME}"
    )
print("Config check OK.")
PY
}

run_model() {
  local output_dir="$1"
  log "Running model simulation -> ${output_dir}"
  "${maven_bin}" exec:java -Dexec.args="-outputFolder ${output_dir} -dev"
}

log "Validation step: switch data -> run model -> validate outputs."
log "Input version: ${input_version}"
log "Output folder: ${output_dir}"

./scripts/helpers/switch-input-data.sh "${input_version}"
run_model "${output_dir}"

# Runtime WAS configuration is now environment-driven; no source rewrites.
case "${dataset_const}" in
  WAVE_3_DATA) export WAS_DATASET="W3" ;;
  ROUND_8_DATA) export WAS_DATASET="R8" ;;
  *)
    log_err "Unsupported dataset constant: ${dataset_const}"
    exit 1
    ;;
esac

export WAS_DATA_ROOT="${repo_root}"
export WAS_RESULTS_ROOT="${repo_root}"
export WAS_RESULTS_RUN_SUBDIR="${output_dir}"

log "Applied runtime WAS configuration via environment variables"
show_config_summary
log "Verifying dataset selection"
verify_config "${expected_dataset}" "${expected_file}"
log "Running validation suite"
./scripts/was/run_was_validation.sh
