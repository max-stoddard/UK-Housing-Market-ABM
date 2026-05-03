python3 -m scripts.python.calibration.output.four_parameter_esmda \
  --version v4.14o \
  --output-version v4.14oo \
  --validation-year 2024 \
  --seeds 1,2,3,4 \
  --workers 20 \
  --ensemble-size 40 \
  --assimilation-steps 4 \
  --rng-seed 20260502 \
  --output-root tmp/output-calibration
