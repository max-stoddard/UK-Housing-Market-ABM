# HPA Expectation Recalibration Implementation Plan

> **Implementation note:** The live code now uses a unified staged HPA workflow rather than the separate legacy-only plan below. Treat this file as historical planning context.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruct the legacy `HPA_EXPECTATION_FACTOR` / `HPA_EXPECTATION_CONST` method transparently, lock a simple national default method family, and add the production calibration entrypoint that reuses it.

**Architecture:** Add one NMG helper module for `boe39` band mapping and weighted expectation aggregation, one PPD helper module for national HPA signal construction, and two thin entrypoints: a reproduction method-search script and a production-fit script. The reproduction script fits and ranks small explicit method variants against the legacy target and a 2016 holdout; once that default family is selected, the production script reuses the same survey mapping, PPD transform, and pairing style without a hidden methodology switch.

**Tech Stack:** Python 3, `unittest`, existing helper modules under `scripts/python/helpers`, config provenance via `src/main/resources/config.properties`, documentation in `scripts/python/AGENT_SCRIPT_STRUCTURE.md` and `scripts/python/calibration/CALIBRATION_PARAMETER_CHANGELOG.md`

---

## File Structure

**Files to create**
- `scripts/python/helpers/nmg/hpa_expectation.py`
  Responsibility: `boe39` mapping specs, weighted aggregation, survey diagnostics, and simple linear-fit utilities for expectation targets.
- `scripts/python/helpers/ppd/hpa_signal_methods.py`
  Responsibility: PPD row parsing, monthly/annual national aggregates, anchor pairing, and HPA signal construction for the approved method family search space.
- `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  Responsibility: enumerate candidate survey and PPD methods, fit `y = factor * x + const`, rank by legacy distance and 2016 holdout behavior, and print reproducible diagnostics.
- `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
  Responsibility: run the locked default method family on the approved production anchors and emit `HPA_EXPECTATION_FACTOR` / `HPA_EXPECTATION_CONST` plus method metadata.
- `scripts/python/tests/test_nmg_hpa_expectation.py`
  Responsibility: unit coverage for `boe39` mapping, weighted aggregation, linear fitting, and calibration CLI defaults.
- `scripts/python/tests/test_ppd_hpa_signal_methods.py`
  Responsibility: unit coverage for annual/monthly HPA signal construction, anchor diagnostics, and validation failures.
- `scripts/python/tests/test_nmg_hpa_expectation_method_search.py`
  Responsibility: reproduction ranking behavior, tie-breaks, CLI defaults, and diagnostics formatting.

**Files to modify**
- `scripts/python/helpers/nmg/__init__.py`
  Responsibility: export the new expectation helpers if the package exposes them centrally.
- `scripts/python/helpers/ppd/__init__.py`
  Responsibility: export the new HPA signal helpers.
- `scripts/python/helpers/common/math_stats.py`
  Responsibility: add small reusable helpers only if needed for ranking math already shared elsewhere.
- `scripts/python/AGENT_SCRIPT_STRUCTURE.md`
  Responsibility: document the new helper and entrypoint paths plus the reproduction-vs-production contract.
- `scripts/python/calibration/CALIBRATION_PARAMETER_CHANGELOG.md`
  Responsibility: record the reproduction command, chosen method family, production command, and rationale.

### Task 1: Build The NMG Expectation Helpers

**Files:**
- Create: `scripts/python/helpers/nmg/hpa_expectation.py`
- Modify: `scripts/python/helpers/nmg/__init__.py`
- Test: `scripts/python/tests/test_nmg_hpa_expectation.py`

- [ ] **Step 1: Write failing helper tests for `boe39` mapping and weighted aggregation**

```python
def test_weighted_boe39_midpoint_mean_excludes_dont_know():
    rows = [
        {"we_factor": "2.0", "boe39": "6"},
        {"we_factor": "1.0", "boe39": "7"},
        {"we_factor": "5.0", "boe39": "10"},
    ]
    result = aggregate_expectation(rows, method_name="midpoint_exact")
    assert round(result.expectation_mean, 6) == round(((2 * 0.03) + (1 * 0.05)) / 3, 6)
    assert result.rows_dont_know == 1
```

- [ ] **Step 2: Run the helper tests to confirm they fail**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation -v`

Expected: failure because the helper module or expected functions do not exist yet.

- [ ] **Step 3: Implement the minimal helper module**

```python
@dataclass(frozen=True)
class ExpectationMethodSpec:
    method_name: str
    inner_mode: str
    lower_cap: float
    upper_cap: float

def aggregate_expectation(rows, *, method_name):
    # parse `we_factor`, ignore invalid/non-positive weights,
    # exclude `Don't know`, map ordinal codes to annual HPA values,
    # and return weighted mean plus diagnostics
```

- [ ] **Step 4: Re-run the helper tests**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation -v`

Expected: PASS

### Task 2: Build The PPD HPA Signal Helpers

**Files:**
- Create: `scripts/python/helpers/ppd/hpa_signal_methods.py`
- Modify: `scripts/python/helpers/ppd/__init__.py`
- Test: `scripts/python/tests/test_ppd_hpa_signal_methods.py`

- [ ] **Step 1: Write failing tests for annualised and cumulative signal construction**

```python
def test_annual_mean_annualised_signal_uses_anchor_gap_years():
    rows = [
        PpdRow(price=100.0, transfer_date="2012-01-01 00:00"),
        PpdRow(price=121.0, transfer_date="2014-01-01 00:00"),
    ]
    signal = build_hpa_signal(rows, anchor_year=2014, base_year=2012, method_name="annual_mean_annualised")
    assert round(signal.value, 6) == 0.1
```

- [ ] **Step 2: Run the PPD helper tests to confirm they fail**

Run: `python3 -m unittest scripts.python.tests.test_ppd_hpa_signal_methods -v`

Expected: failure because the helper module or expected functions do not exist yet.

- [ ] **Step 3: Implement the minimal signal helper module**

```python
@dataclass(frozen=True)
class HpaSignal:
    method_name: str
    anchor_year: int
    base_year: int
    value: float
    diagnostics: dict[str, object]

def build_hpa_signal(rows, *, anchor_year, base_year, method_name):
    # support:
    # - java_like_annualised
    # - annual_mean_annualised
    # - annual_mean_cumulative
```

- [ ] **Step 4: Re-run the PPD helper tests**

Run: `python3 -m unittest scripts.python.tests.test_ppd_hpa_signal_methods -v`

Expected: PASS

### Task 3: Build The Reproduction Experiment

**Files:**
- Create: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Modify: `scripts/python/helpers/common/math_stats.py` (only if a small generic ranking helper is genuinely useful)
- Test: `scripts/python/tests/test_nmg_hpa_expectation_method_search.py`

- [ ] **Step 1: Write failing tests for parser defaults, ranking, and holdout scoring**

```python
def test_parser_defaults_use_legacy_targets_and_2016_holdout():
    args = build_arg_parser().parse_args(["nmg_2014.csv", "nmg_2016.csv", "nmg_2024.csv", "pp-2011.csv", "pp.2012.csv", "pp-2018.csv", "pp-2024.csv"])
    assert args.config_path == "src/main/resources/config.properties"
    assert args.holdout_year == 2016
```

- [ ] **Step 2: Run the experiment tests to confirm they fail**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation_method_search -v`

Expected: failure because the script and ranking helpers do not exist yet.

- [ ] **Step 3: Implement the reproduction experiment**

```python
def fit_line(anchor_points):
    # slope/intercept from the explicit calibration anchors

def rank_candidate(result):
    # primary: legacy distance
    # secondary: holdout error
    # tertiary: simplicity tuple
```

- [ ] **Step 4: Re-run the experiment tests**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation_method_search -v`

Expected: PASS

- [ ] **Step 5: Run the full new test slice**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation scripts.python.tests.test_ppd_hpa_signal_methods scripts.python.tests.test_nmg_hpa_expectation_method_search -v`

Expected: PASS

### Task 4: Run The Reproduction Experiment And Lock The Method Family

**Files:**
- Modify: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Modify: `scripts/python/AGENT_SCRIPT_STRUCTURE.md`
- Modify: `scripts/python/calibration/CALIBRATION_PARAMETER_CHANGELOG.md`

- [ ] **Step 1: Run the experiment on the real datasets**

Run:

```bash
python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search \
  private-datasets/nmg/nmg-2014.csv \
  private-datasets/nmg/nmg-2016.csv \
  private-datasets/nmg/nmg-2024.csv \
  private-datasets/ppd/pp-2011.csv \
  private-datasets/ppd/pp.2012.csv \
  private-datasets/ppd/pp-2018.csv \
  private-datasets/ppd/pp-2022.csv \
  private-datasets/ppd/pp-2023.csv \
  private-datasets/ppd/pp-2024.csv \
  private-datasets/ppd/pp-2025.csv \
  --config-path src/main/resources/config.properties \
  --top-k 15
```

Expected: ranked methods table, survey diagnostics, PPD diagnostics, and observed-vs-predicted 2016 holdout output.

- [ ] **Step 2: Record the chosen default method family in the experiment docstring and provenance docs**

Required edits:
- add latest findings to `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- document the new experiment and method-locking contract in `scripts/python/AGENT_SCRIPT_STRUCTURE.md`
- add the reproduction command and decision rationale to `scripts/python/calibration/CALIBRATION_PARAMETER_CHANGELOG.md`

### Task 5: Build The Production Calibration Entrypoint

**Files:**
- Create: `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Modify: `scripts/python/tests/test_nmg_hpa_expectation.py`

- [ ] **Step 1: Add failing tests for production CLI defaults and locked-method reuse**

```python
def test_calibration_cli_defaults_to_locked_method_family():
    args = build_arg_parser().parse_args(["nmg_2014.csv", "nmg_2024.csv", "pp-2011.csv", "pp.2012.csv", "pp-2024.csv"])
    assert args.target_year == 2024
```

- [ ] **Step 2: Run the helper/calibration tests to confirm they fail**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation -v`

Expected: failure because the calibration entrypoint or helper hooks do not exist yet.

- [ ] **Step 3: Implement the production calibration entrypoint**

```python
def main():
    # load only the locked method family
    # use the approved production anchors
    # fit factor/const
    # print exact config keys and diagnostics
```

- [ ] **Step 4: Re-run the tests and a real production-fit invocation**

Run: `python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation scripts.python.tests.test_ppd_hpa_signal_methods scripts.python.tests.test_nmg_hpa_expectation_method_search -v`

Expected: PASS

Run:

```bash
python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit \
  private-datasets/nmg/nmg-2014.csv \
  private-datasets/nmg/nmg-2024.csv \
  private-datasets/ppd/pp-2011.csv \
  private-datasets/ppd/pp.2012.csv \
  private-datasets/ppd/pp-2022.csv \
  private-datasets/ppd/pp-2023.csv \
  private-datasets/ppd/pp-2024.csv \
  private-datasets/ppd/pp-2025.csv \
  --target-year 2024
```

Expected: prints `HPA_EXPECTATION_FACTOR`, `HPA_EXPECTATION_CONST`, method metadata, and anchor diagnostics.

---

## Verification Notes

- Keep the survey-method search space intentionally small: exact midpoints, rounded midpoints, and small open-ended-cap variants only.
- Keep the PPD-method search space intentionally small: `java_like_annualised`, `annual_mean_annualised`, and `annual_mean_cumulative` only.
- The 2016 survey anchor is the holdout for the reproduction experiment and must not be silently pulled into the production fit.
- Do not publish `v4.2` or modify input-data snapshots in this implementation pass unless the approved design is updated first.
- If the real-data experiment identifies ties or ambiguous winners, prefer the simpler Java-like / midpoint method family when the score difference is immaterial and record that rationale explicitly.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-hpa-expectation-recalibration-plan.md`. Ready to execute.
