#!/usr/bin/env bash
# Generic validation runner for input-data versions.
# Author: Max Stoddard

set -euo pipefail

print_usage() {
  cat <<EOF
Usage: $(basename "$0") <version> [--output-dir <path>]

Arguments:
  <version>               Input-data version folder name (for example: v0, v1.0, v4.1).

Options:
  --output-dir <path>     Transient output directory. Defaults to tmp/validation/<version>.
EOF
}

if [[ $# -lt 1 ]]; then
  print_usage
  exit 1
fi

input_version="$1"
shift

output_dir=""
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

python3 -m scripts.python.validation.model.validate_input_data_version \
  --version "${input_version}" \
  --seeds 1,2,3,4,5,6,7,8 \
  --output-dir "${output_dir}"
