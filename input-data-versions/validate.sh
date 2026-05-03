#!/usr/bin/env bash
# Generic version-gated validation runner for input-data versions.
# Author: Max Stoddard

set -euo pipefail

print_usage() {
  cat <<EOF
Usage: $(basename "$0") <version> [--output-dir <path>] [--workers <n>] [--reuse-existing-output] [--reference-only]

Arguments:
  <version>               Input-data version folder name (for example: v0, v1.0, v4.1).

Options:
  --output-dir <path>     Transient output directory. Defaults to tmp/validation/<version>.
  --workers <n>          Maximum parallel workers for per-seed validation runs. Defaults to 20.
  --reuse-existing-output Reuse existing per-seed outputs from --output-dir instead of rerunning the model.
  --reference-only       Publish only the optional 2011 reference overlay from existing per-seed outputs.
EOF
}

if [[ $# -lt 1 ]]; then
  print_usage
  exit 1
fi

input_version="$1"
shift

output_dir=""
workers=20
reuse_existing_output="false"
reference_only="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      if [[ $# -lt 2 ]]; then
        echo "--output-dir requires a path argument." >&2
        exit 1
      fi
      output_dir="$2"
      shift 2
      ;;
    --workers)
      if [[ $# -lt 2 ]]; then
        echo "--workers requires an integer argument." >&2
        exit 1
      fi
      if [[ ! "$2" =~ ^[0-9]+$ ]] || [[ "$2" == "0" ]]; then
        echo "--workers must be a positive integer." >&2
        exit 1
      fi
      workers="$2"
      shift 2
      ;;
    --reuse-existing-output)
      reuse_existing_output="true"
      shift
      ;;
    --reference-only)
      reference_only="true"
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_usage
      exit 1
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

if [[ -z "${output_dir}" ]]; then
  output_dir="tmp/validation/${input_version}"
fi

validation_args=(
  -m scripts.python.validation.model.validate_input_data_version
  --version "${input_version}"
  --seeds 1,2,3,4,5,6,7,8
  --output-dir "${output_dir}"
  --workers "${workers}"
)

if [[ "${reuse_existing_output}" == "true" ]]; then
  validation_args+=(--reuse-existing-output)
fi

if [[ "${reference_only}" == "true" ]]; then
  validation_args+=(--reference-only)
fi

python3 "${validation_args[@]}"
