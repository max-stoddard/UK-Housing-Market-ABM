#!/usr/bin/env bash
# Generic version-gated validation runner for input-data versions.
# Author: Max Stoddard

set -euo pipefail

print_usage() {
  cat <<EOF
Usage: $(basename "$0") <version> [--output-dir <path>] [--workers <n>] [--seeds <list>] [--n-steps <n>] [--validation-window-start <n>] [--validation-window-end <n>] [--reuse-existing-output] [--reference-only] [--allow-noncanonical-seeds]

Arguments:
  <version>               Input-data version folder name (for example: v0, v1.0, v4.1).

Options:
  --output-dir <path>     Transient output directory. Defaults to tmp/validation/<version>.
  --workers <n>          Maximum parallel workers for per-seed validation runs. Defaults to 20.
  --seeds <list>          Comma-separated seeds. Defaults to canonical 1,2,3,4,5,6,7,8.
  --n-steps <n>           Optional N_STEPS override for validation runs.
  --validation-window-start <n>
                          Optional metric extraction window start index.
  --validation-window-end <n>
                          Optional metric extraction window end index.
  --reuse-existing-output Reuse existing per-seed outputs from --output-dir instead of rerunning the model.
  --reference-only       Publish only the optional 2011 reference overlay from existing per-seed outputs.
  --allow-noncanonical-seeds
                          Allow tracked publication with an explicitly supplied non-canonical seed block.

Definitions:
  Symbols                 For one metric, let seed values be x_i, targetBand.lower=L,
                          targetBand.upper=U, seedMean=mu=mean(x_i), p25=q25,
                          p75=q75, IQR=max(0, q75 - q25), and
                          insideRate=r=count(L <= x_i <= U) / count(x_i).
                          Let outside(mu,L,U)=0 when L <= mu <= U, otherwise
                          min(abs(mu - L), abs(mu - U)). For additive formulas,
                          A=max(abs(sourceValue) when present, abs(L), abs(U),
                          (U - L) / 2, 1e-9).

  Target range           The inclusive lower/upper target interval for one validation metric. Published
                          summaries expose it as targetBand.lower and targetBand.upper, with bandMethod
                          and bandNotes explaining how that interval was derived. It is not a CLI
                          argument; it comes from the locked validation catalog for the target year.
                          A metric passes when outside(mu,L,U)/(U-L)=0 and r>=0.75, warns when
                          outside(mu,L,U)/(U-L)<=0.50 and r>=0.50, and fails otherwise.
                          HH owning share and HH private renting share use a +/-0.5 percentage-point
                          target range because the DWP Family Resources Survey tenure tables publish
                          those household shares as whole percentages. The band is therefore the
                          rounded-value interval around the published value (for example, 65% maps to
                          [64.5,65.5]), not an additional modelling tolerance. HH private renting
                          share uses the private-rented-sector value only; social renting is excluded.

  positive_level         Requires L>0 and U>0. Distance D=0 when L<=mu<=U;
                          D=log(mu/U) when mu>U; D=log(L/mu) when 0<mu<L;
                          D=log(100) when mu<=0. Spread Q=max(0,log(q75/q25))
                          when q25>0 and q75>0, otherwise Q=IQR/A.
                          Loss = D + 0.25*Q + 0.50*(1-r).

  signed_additive        Uses additive units around the target band. D=outside(mu,L,U)/A;
                          Q=IQR/A. Loss = D + 0.25*Q + 0.50*(1-r).

  bounded_low_is_better  Requires U>0. D=max(mu-U,0)/U; level=0.25*max(mu,0)/U;
                          Q=IQR/U. Loss = D + level + 0.25*Q + 0.50*(1-r).

  bounded_share          Requires 0<=L<U<=100 and treats values as percentages on a 0..100
                          domain. D=outside(mu,L,U)/100; Q=IQR/100.
                          Loss = D + 0.25*Q + 0.50*(1-r).

  diagnostic             Diagnostic metrics are not scored. They publish metricWeight=0.0,
                          do not contribute a metricLoss, and are excluded from the composite.

  Composite loss         overallCompositeLoss=sum(metricLoss * metricWeight)/sum(metricWeight)
                          over required scored metrics only. Required scored metrics currently
                          carry metricWeight=1.0, so the published composite is their arithmetic
                          mean; diagnostic, unsupported, and non-required metrics are excluded.
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
seeds="1,2,3,4,5,6,7,8"
n_steps=""
validation_window_start=""
validation_window_end=""
reuse_existing_output="false"
reference_only="false"
allow_noncanonical_seeds="false"
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
    --seeds)
      if [[ $# -lt 2 ]]; then
        echo "--seeds requires a comma-separated argument." >&2
        exit 1
      fi
      seeds="$2"
      shift 2
      ;;
    --n-steps)
      if [[ $# -lt 2 ]]; then
        echo "--n-steps requires an integer argument." >&2
        exit 1
      fi
      if [[ ! "$2" =~ ^[0-9]+$ ]] || [[ "$2" == "0" ]]; then
        echo "--n-steps must be a positive integer." >&2
        exit 1
      fi
      n_steps="$2"
      shift 2
      ;;
    --validation-window-start)
      if [[ $# -lt 2 ]]; then
        echo "--validation-window-start requires an integer argument." >&2
        exit 1
      fi
      if [[ ! "$2" =~ ^[0-9]+$ ]]; then
        echo "--validation-window-start must be a non-negative integer." >&2
        exit 1
      fi
      validation_window_start="$2"
      shift 2
      ;;
    --validation-window-end)
      if [[ $# -lt 2 ]]; then
        echo "--validation-window-end requires an integer argument." >&2
        exit 1
      fi
      if [[ ! "$2" =~ ^[0-9]+$ ]] || [[ "$2" == "0" ]]; then
        echo "--validation-window-end must be a positive integer." >&2
        exit 1
      fi
      validation_window_end="$2"
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
    --allow-noncanonical-seeds)
      allow_noncanonical_seeds="true"
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
  --seeds "${seeds}"
  --output-dir "${output_dir}"
  --workers "${workers}"
)

if [[ -n "${n_steps}" ]]; then
  validation_args+=(--n-steps "${n_steps}")
fi

if [[ -n "${validation_window_start}" ]]; then
  validation_args+=(--validation-window-start "${validation_window_start}")
fi

if [[ -n "${validation_window_end}" ]]; then
  validation_args+=(--validation-window-end "${validation_window_end}")
fi

if [[ "${reuse_existing_output}" == "true" ]]; then
  validation_args+=(--reuse-existing-output)
fi

if [[ "${reference_only}" == "true" ]]; then
  validation_args+=(--reference-only)
fi

if [[ "${allow_noncanonical_seeds}" == "true" ]]; then
  validation_args+=(--allow-noncanonical-seeds)
fi

python3 "${validation_args[@]}"
