#!/usr/bin/env bash
# Snapshot-local benchmark harness for the Java housing model.
# Author: Max Stoddard

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/model-speed-lib.sh"

LOG_TAG="SPEED-BENCH"
LOG_COLOR="\033[1;36m"
model_speed_log_init

usage() {
  cat <<EOF
Usage: $(basename "$0") --snapshot <version> --mode <mode> --repeat <n> --output-root <dir>

Required arguments:
  --snapshot     Snapshot folder under input-data-versions (canonical model-speed snapshot: v0)
  --mode         e2e-default-10k-s1 | core-minimal-20k-s1
  --repeat       Number of measured repeats (one warm-up is always added)
  --output-root  Root directory for benchmark artifacts

Environment:
  MODEL_SPEED_JAVA_OPTS          JVM flags for direct Java execution (default: -Xms1g -Xmx4g)
  MODEL_SPEED_POPULATION_LADDER  Set to 1 to record the 10k/20k population ladder for core-minimal-20k-s1
EOF
}

snapshot=""
mode=""
repeat=""
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
    --repeat)
      repeat="$2"
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

if [[ -z "${snapshot}" || -z "${mode}" || -z "${repeat}" || -z "${output_root}" ]]; then
  usage
  exit 1
fi

if ! [[ "${repeat}" =~ ^[0-9]+$ ]] || (( repeat < 1 )); then
  log_err "--repeat must be a positive integer."
  exit 1
fi

mode_file="$(model_speed_mode_file "${snapshot}" "${mode}")"
mkdir -p "${output_root}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_root="${output_root%/}/${snapshot}/${mode}/${timestamp}"
generated_config_dir="$(model_speed_tmp_root)/generated-configs/${snapshot}/${mode}"
generated_config_dir="${generated_config_dir}/${timestamp}"
config_path="${generated_config_dir}/${snapshot}-${mode}.properties"
runs_tsv="${run_root}/measured-runs.tsv"
summary_json="${run_root}/summary.json"
environment_txt="${run_root}/environment.txt"

log "Benchmark session root: ${run_root}"
log "Pinned mode definition: ${mode_file}"
log "Materialised config path: ${config_path}"

mkdir -p "${run_root}"
model_speed_capture_environment "${environment_txt}" "${snapshot}" "${mode}" "${output_root}"
model_speed_materialize_config "${snapshot}" "${mode}" "${config_path}"

target_population="$(model_speed_read_config_value "${config_path}" TARGET_POPULATION)"
n_steps="$(model_speed_read_config_value "${config_path}" N_STEPS)"
n_sims="$(model_speed_read_config_value "${config_path}" N_SIMS)"

log "Benchmark config pins TARGET_POPULATION=${target_population}, N_STEPS=${n_steps}, N_SIMS=${n_sims}"
model_speed_ensure_compiled
model_speed_resolve_classpath >/dev/null

log "Running warm-up pass."
model_speed_run_model_once "${config_path}" "${run_root}/warmup"

model_speed_write_tsv_header "${runs_tsv}"
for run_index in $(seq 1 "${repeat}"); do
  run_id="$(printf 'run-%03d' "${run_index}")"
  run_dir="${run_root}/runs/${run_id}"
  log "Running measured benchmark ${run_id}/${repeat}."
  model_speed_run_model_once "${config_path}" "${run_dir}"

  wall_clock_seconds="$(cat "${run_dir}/wall_clock_seconds.txt")"
  model_computing_seconds="$(model_speed_extract_model_seconds "${run_dir}/model.stdout.log")"
  primary_metric="$(model_speed_compute_primary_metric "${wall_clock_seconds}" "${target_population}" "${n_steps}" "${n_sims}")"
  output_bytes="$(model_speed_sum_output_bytes "${run_dir}/model-output")"
  max_rss_kb="$(model_speed_extract_time_field "${run_dir}/time.txt" "Maximum resident set size (kbytes)")"
  user_cpu_seconds="$(model_speed_extract_time_field "${run_dir}/time.txt" "User time (seconds)")"
  system_cpu_seconds="$(model_speed_extract_time_field "${run_dir}/time.txt" "System time (seconds)")"
  gc_pause_count="$(model_speed_json_field "${run_dir}/gc-summary.json" "pause_count")"
  gc_pause_time_ms_total="$(model_speed_json_field "${run_dir}/gc-summary.json" "pause_time_ms_total")"

  model_speed_append_tsv_row \
    "${runs_tsv}" \
    "${run_id}" \
    "${wall_clock_seconds}" \
    "${model_computing_seconds}" \
    "${primary_metric}" \
    "${output_bytes}" \
    "${max_rss_kb}" \
    "${user_cpu_seconds}" \
    "${system_cpu_seconds}" \
    "${gc_pause_count}" \
    "${gc_pause_time_ms_total}" \
    "${config_path}" \
    "${run_dir}/model-output" \
    "${run_dir}/model.stdout.log" \
    "${run_dir}/time.txt" \
    "${run_dir}/model-output.sha256"
done

python3 "$(model_speed_python_helper)" benchmark-summary --runs-tsv "${runs_tsv}" --output "${summary_json}"
median_run_id="$(
  python3 - "${summary_json}" <<'PY'
import json
import sys
summary = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
print(summary["median_run_id"])
PY
)"
log "Measured summary written to ${summary_json}"
log "Median measured run: ${median_run_id}"

median_jfr_dir="${run_root}/median-jfr"
median_jfr_file="${median_jfr_dir}/profile.jfr"
mkdir -p "${median_jfr_dir}"
log "Re-running median scenario with JFR capture."
model_speed_run_model_once \
  "${config_path}" \
  "${median_jfr_dir}" \
  "-XX:StartFlightRecording=filename=${median_jfr_file},settings=profile,dumponexit=true"

if [[ "${mode}" == "core-minimal-20k-s1" && "${MODEL_SPEED_POPULATION_LADDER}" == "1" ]]; then
  ladder_tsv="${run_root}/population-ladder.tsv"
  printf '%s\n' \
    'population	wall_clock_seconds	seconds_per_household_month	output_bytes	max_rss_kb	gc_pause_count	gc_pause_time_ms_total	output_dir	manifest_path' \
    > "${ladder_tsv}"
  for ladder_population in 10000 20000; do
    ladder_config="${generated_config_dir}/${snapshot}-${mode}-ladder-${ladder_population}.properties"
    ladder_run_dir="${run_root}/population-ladder/pop-${ladder_population}"
    log "Running population ladder point TARGET_POPULATION=${ladder_population}."
    model_speed_materialize_config \
      "${snapshot}" \
      "${mode}" \
      "${ladder_config}" \
      --override "TARGET_POPULATION=${ladder_population}"
    model_speed_run_model_once "${ladder_config}" "${ladder_run_dir}"
    ladder_wall="$(cat "${ladder_run_dir}/wall_clock_seconds.txt")"
    ladder_steps="$(model_speed_read_config_value "${ladder_config}" N_STEPS)"
    ladder_sims="$(model_speed_read_config_value "${ladder_config}" N_SIMS)"
    ladder_primary="$(model_speed_compute_primary_metric "${ladder_wall}" "${ladder_population}" "${ladder_steps}" "${ladder_sims}")"
    ladder_output_bytes="$(model_speed_sum_output_bytes "${ladder_run_dir}/model-output")"
    ladder_rss="$(model_speed_extract_time_field "${ladder_run_dir}/time.txt" "Maximum resident set size (kbytes)")"
    ladder_pause_count="$(model_speed_json_field "${ladder_run_dir}/gc-summary.json" "pause_count")"
    ladder_pause_time="$(model_speed_json_field "${ladder_run_dir}/gc-summary.json" "pause_time_ms_total")"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "${ladder_population}" \
      "${ladder_wall}" \
      "${ladder_primary}" \
      "${ladder_output_bytes}" \
      "${ladder_rss}" \
      "${ladder_pause_count}" \
      "${ladder_pause_time}" \
      "${ladder_run_dir}/model-output" \
      "${ladder_run_dir}/model-output.sha256" \
      >> "${ladder_tsv}"
  done
  log "Population ladder written to ${ladder_tsv}"
fi

log "Benchmark complete."
log "Artifacts:"
log "  environment: ${environment_txt}"
log "  runs:        ${runs_tsv}"
log "  summary:     ${summary_json}"
log "  median JFR:  ${median_jfr_file}"
