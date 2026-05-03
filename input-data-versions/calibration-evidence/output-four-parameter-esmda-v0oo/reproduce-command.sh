python3 -m scripts.python.calibration.output.four_parameter_esmda \
  --version v0o \
  --output-version v0oo \
  --validation-year 2011 \
  --seeds 1,2,3,4 \
  --workers 20 \
  --ensemble-size 40 \
  --assimilation-steps 4 \
  --rng-seed 20260502 \
  --output-root tmp/output-calibration
