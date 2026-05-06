#!/usr/bin/env bash
# Shared helpers for snapshot-local model-speed scripts.
# Author: Max Stoddard

set -euo pipefail

model_speed_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
model_speed_repo_root="$(cd "${model_speed_script_dir}/../.." && pwd)"

source "${model_speed_repo_root}/scripts/helpers/log.sh"

MODEL_SPEED_JAVA_OPTS="${MODEL_SPEED_JAVA_OPTS:--Xms1g -Xmx4g}"
MODEL_SPEED_POPULATION_LADDER="${MODEL_SPEED_POPULATION_LADDER:-0}"
MODEL_SPEED_CPU_AFFINITY="${MODEL_SPEED_CPU_AFFINITY:-}"
MODEL_SPEED_ACTIVE_PROCESSOR_COUNT="${MODEL_SPEED_ACTIVE_PROCESSOR_COUNT:-}"
MODEL_SPEED_MAVEN_PROFILES="${MODEL_SPEED_MAVEN_PROFILES:-}"

model_speed_log_init() {
  LOG_TAG="${LOG_TAG:-MODEL-SPEED}"
  LOG_COLOR="${LOG_COLOR:-\033[1;35m}"
  log_init
}

model_speed_mode_file() {
  local snapshot="$1"
  local mode="$2"
  local mode_file="${model_speed_repo_root}/scripts/model/configs/${snapshot}-${mode}.properties"
  if [[ ! -f "${mode_file}" ]]; then
    log_err "Unsupported snapshot/mode combination: snapshot=${snapshot}, mode=${mode}"
    return 1
  fi
  printf '%s\n' "${mode_file}"
}

model_speed_python_helper() {
  printf '%s\n' "${model_speed_repo_root}/scripts/model/model_speed.py"
}

model_speed_tmp_root() {
  printf '%s\n' "${model_speed_repo_root}/tmp/model-speed"
}

model_speed_maven_profile_args() {
  local -n out_ref="$1"
  out_ref=()
  if [[ -n "${MODEL_SPEED_MAVEN_PROFILES}" ]]; then
    out_ref+=( "-P${MODEL_SPEED_MAVEN_PROFILES}" )
  fi
}

model_speed_ensure_compiled() {
  log "Compiling Java sources for snapshot-local model-speed harness."
  local -a profile_args=()
  model_speed_maven_profile_args profile_args
  (
    cd "${model_speed_repo_root}"
    mvn -q "${profile_args[@]}" -DskipTests clean compile
  )
}

model_speed_resolve_classpath() {
  if [[ -n "${MODEL_SPEED_CLASSPATH:-}" ]]; then
    printf '%s\n' "${MODEL_SPEED_CLASSPATH}"
    return 0
  fi
  local classpath
  local -a profile_args=()
  model_speed_maven_profile_args profile_args
  classpath="$(
    cd "${model_speed_repo_root}"
    mvn -q "${profile_args[@]}" -Dexec.classpathScope=runtime -Dexec.executable=echo -Dexec.args='%classpath' exec:exec | tail -n 1
  )"
  if [[ -z "${classpath}" ]]; then
    log_err "Failed to resolve runtime classpath."
    return 1
  fi
  MODEL_SPEED_CLASSPATH="${classpath}"
  export MODEL_SPEED_CLASSPATH
  printf '%s\n' "${classpath}"
}

model_speed_materialize_config() {
  local snapshot="$1"
  local mode="$2"
  local output_path="$3"
  shift 3
  local mode_file
  mode_file="$(model_speed_mode_file "${snapshot}" "${mode}")"
  mkdir -p "$(dirname "${output_path}")"
  python3 "$(model_speed_python_helper)" materialize-config \
    --snapshot "${snapshot}" \
    --mode-file "${mode_file}" \
    --output "${output_path}" \
    "$@"
}

model_speed_read_config_value() {
  local config_path="$1"
  local key="$2"
  awk -F'=' -v wanted="${key}" '
    $1 ~ "^[[:space:]]*" wanted "[[:space:]]*$" {
      value = $2
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      print value
      exit
    }
  ' "${config_path}"
}

model_speed_json_field() {
  local json_path="$1"
  local field_path="$2"
  python3 - "${json_path}" "${field_path}" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
value = data
for key in sys.argv[2].split("."):
    value = value[key]
if isinstance(value, float):
    print(f"{value:.12f}".rstrip("0").rstrip("."))
else:
    print(value)
PY
}

model_speed_sum_output_bytes() {
  local output_dir="$1"
  find "${output_dir}" -type f -printf '%s\n' | awk '{sum += $1} END {print sum + 0}'
}

model_speed_compute_primary_metric() {
  local wall_clock_seconds="$1"
  local target_population="$2"
  local n_steps="$3"
  local n_sims="$4"
  awk -v wall="${wall_clock_seconds}" -v pop="${target_population}" -v steps="${n_steps}" -v sims="${n_sims}" \
    'BEGIN { printf "%.12f", wall / (pop * steps * sims) }'
}

model_speed_extract_model_seconds() {
  local stdout_log="$1"
  awk '/Computing time:/ {value = $3} END { if (value == "") exit 1; print value }' "${stdout_log}"
}

model_speed_extract_time_field() {
  local time_file="$1"
  local label="$2"
  awk -F': *' -v wanted="${label}" '
    {
      field = $1
      value = $2
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", field)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (field == wanted) {
        print value
        exit
      }
    }
  ' "${time_file}"
}

model_speed_capture_environment() {
  local output_path="$1"
  local snapshot="$2"
  local mode="$3"
  local output_root="$4"
  mkdir -p "$(dirname "${output_path}")"
  {
    printf 'date_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'repo_root=%s\n' "${model_speed_repo_root}"
    printf 'snapshot=%s\n' "${snapshot}"
    printf 'mode=%s\n' "${mode}"
    printf 'java_opts=%s\n' "${MODEL_SPEED_JAVA_OPTS}"
    printf 'maven_profiles=%s\n' "${MODEL_SPEED_MAVEN_PROFILES:-none}"
    printf 'cpu_affinity=%s\n' "${MODEL_SPEED_CPU_AFFINITY:-none}"
    printf 'active_processor_count=%s\n' "${MODEL_SPEED_ACTIVE_PROCESSOR_COUNT:-default}"
    printf 'output_root=%s\n' "${output_root}"
    printf 'tmp_root=%s\n' "$(model_speed_tmp_root)"
    printf '\n[uname -a]\n'
    uname -a
    printf '\n[nproc]\n'
    nproc
    if command -v taskset >/dev/null 2>&1; then
      printf '\n[taskset -pc $$]\n'
      taskset -pc $$ || true
    fi
    printf '\n[java -version]\n'
    java -version 2>&1
    printf '\n[mvn -version]\n'
    mvn -version 2>&1
    printf '\n[df -h]\n'
    df -h "${output_root}"
  } > "${output_path}"
}

model_speed_write_tsv_header() {
  local tsv_path="$1"
  printf '%s\n' \
    'run_id	wall_clock_seconds	model_computing_seconds	seconds_per_household_month	output_bytes	max_rss_kb	user_cpu_seconds	system_cpu_seconds	gc_pause_count	gc_pause_time_ms_total	config_path	output_dir	stdout_log	time_file	manifest_path' \
    > "${tsv_path}"
}

model_speed_append_tsv_row() {
  local tsv_path="$1"
  shift
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >> "${tsv_path}"
}

model_speed_build_java_command() {
  local -n out_ref="$1"
  local config_path="$2"
  local output_dir="$3"
  shift 3
  local -a extra_java_flags=( "$@" )
  local -a cmd=(java)
  if [[ -n "${MODEL_SPEED_JAVA_OPTS}" ]]; then
    local -a default_java_flags=()
    read -r -a default_java_flags <<< "${MODEL_SPEED_JAVA_OPTS}"
    cmd+=( "${default_java_flags[@]}" )
  fi
  if [[ -n "${MODEL_SPEED_ACTIVE_PROCESSOR_COUNT}" ]]; then
    cmd+=( "-XX:ActiveProcessorCount=${MODEL_SPEED_ACTIVE_PROCESSOR_COUNT}" )
  fi
  cmd+=( -Xlog:gc*:file="${output_dir%/*}/gc.log":time,level,tags )
  if (( ${#extra_java_flags[@]} > 0 )); then
    cmd+=( "${extra_java_flags[@]}" )
  fi
  cmd+=( -cp "${MODEL_SPEED_CLASSPATH}" housing.Model -configFile "${config_path}" -outputFolder "${output_dir}" -dev )
  out_ref=( "${cmd[@]}" )
}

model_speed_run_model_once() {
  local config_path="$1"
  local run_dir="$2"
  shift 2
  local -a extra_java_flags=( "$@" )

  mkdir -p "${run_dir}"
  local output_dir="${run_dir}/model-output"
  local stdout_log="${run_dir}/model.stdout.log"
  local stderr_log="${run_dir}/model.stderr.log"
  local time_file="${run_dir}/time.txt"
  local gc_summary="${run_dir}/gc-summary.json"
  local manifest_path="${run_dir}/model-output.sha256"
  local wall_clock_file="${run_dir}/wall_clock_seconds.txt"
  local command_file="${run_dir}/command.txt"

  local -a java_cmd=()
  model_speed_build_java_command java_cmd "${config_path}" "${output_dir}" "${extra_java_flags[@]}"
  local -a run_cmd=( "${java_cmd[@]}" )
  if [[ -n "${MODEL_SPEED_CPU_AFFINITY}" ]]; then
    if ! command -v taskset >/dev/null 2>&1; then
      log_err "MODEL_SPEED_CPU_AFFINITY is set but taskset is not available."
      return 1
    fi
    run_cmd=( taskset -c "${MODEL_SPEED_CPU_AFFINITY}" "${java_cmd[@]}" )
  fi
  printf '%q ' "${run_cmd[@]}" > "${command_file}"
  printf '\n' >> "${command_file}"

  local start_ns
  local end_ns
  local wall_clock_seconds
  start_ns="$(date +%s%N)"
  (
    cd "${model_speed_repo_root}"
    LC_ALL=C /usr/bin/time -v -o "${time_file}" "${run_cmd[@]}" > "${stdout_log}" 2> "${stderr_log}"
  )
  end_ns="$(date +%s%N)"
  wall_clock_seconds="$(awk -v start="${start_ns}" -v end="${end_ns}" 'BEGIN { printf "%.6f", (end - start) / 1000000000 }')"
  printf '%s\n' "${wall_clock_seconds}" > "${wall_clock_file}"

  python3 "$(model_speed_python_helper)" gc-summary --gc-log "${run_dir}/gc.log" --output "${gc_summary}"
  python3 "$(model_speed_python_helper)" manifest --output-dir "${output_dir}" --manifest-path "${manifest_path}"
}
