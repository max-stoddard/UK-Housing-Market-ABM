# Model Speed Baselines
Author: Max Stoddard

This folder stores tracked baseline artifacts for the model-speed programme.

Allowed here:
- exact hash manifests for the canonical e2e correctness gate
- benchmark summary snapshots for the two canonical baselines
- tolerance-spec snapshots once a future parallel track is approved

Not allowed here:
- raw model outputs
- JFR recordings
- GC logs
- temporary comparison reports
- generated configs

Those transient artifacts belong under `tmp/model-speed/`.

Tracked baseline artifacts should be small, reviewable, and stable enough to support exact or tolerance-based regression checks.

Current canonical baselines:
- `v0-e2e-default-10k-s1`: exact hash regression contract
- `v0-core-minimal-20k-s1`: primary single-run speed/scaling summary
