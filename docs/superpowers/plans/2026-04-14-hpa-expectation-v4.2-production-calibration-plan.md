# HPA Expectation v4.2 Production Calibration Implementation Plan

> **Implementation note:** The live code now uses a unified staged HPA workflow with `legacy` and `production` search modes plus an artifact-driven calibration rerun. Treat this file as historical planning context.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refit `HPA_EXPECTATION_FACTOR` and `HPA_EXPECTATION_CONST` on the continuous modern `2018` to `2024` window, reuse the existing NMG and PPD helper stack, and ship the full `v4.2` snapshot, validation, results run, and provenance updates.

**Architecture:** Extend the current NMG expectation helper and PPD signal helper with the smallest missing pieces for multi-year fit diagnostics and plausibility classification, then repurpose the existing method-search and production-fit entrypoints around the modern-window constrained regression design. After the scripts produce the final coefficients, copy forward `v4.1` into `v4.2`, update only the two expectation parameters, validate the snapshot, run a full model output into `Results/v4.2-output`, and record the full provenance in the repo docs.

**Tech Stack:** Python 3, `unittest`, existing helper modules under `scripts/python/helpers`, Maven-backed model execution through the validation framework, JSON provenance under `input-data-versions/`, and subagent code review before release completion.

---

## File Structure

**Files to modify**
- `scripts/python/helpers/nmg/hpa_expectation.py`
  Responsibility: retain `boe39` mapping and linear-fit logic, add compact plausibility and regression-diagnostic helpers only if the existing helper cannot express them cleanly.
- `scripts/python/helpers/ppd/hpa_signal_methods.py`
  Responsibility: retain PPD parsing and signal construction, add only the missing multi-year assembly or same-year anchor helpers needed by the modern `2018` to `2024` fit.
- `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
  Responsibility: change ranking from legacy-distance/2016-holdout to modern-window constrained selection with `2014` and `2016` kept as diagnostics only.
- `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
  Responsibility: change the production CLI and fit logic to use the continuous `2018` to `2024` anchor window and print the locked-method diagnostics.
- `scripts/python/tests/test_nmg_hpa_expectation.py`
  Responsibility: cover any new plausibility or multi-anchor helper behavior added to the NMG helper.
- `scripts/python/tests/test_ppd_hpa_signal_methods.py`
  Responsibility: cover any new same-year anchor or multi-year signal assembly behavior in the PPD helper.
- `scripts/python/tests/test_nmg_hpa_expectation_method_search.py`
  Responsibility: cover the new parser defaults, admissibility/preferred-band ranking, and diagnostic-only legacy-year behavior.
- `scripts/python/tests/test_nmg_hpa_expectation_fit.py`
  Responsibility: cover the new production CLI defaults and the `2018` to `2024` calibration path.
- `scripts/python/AGENT_SCRIPT_STRUCTURE.md`
  Responsibility: document the modern-window method-search and production calibration contracts.
- `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md`
  Responsibility: record the new command set, chosen method family, fit window, and final coefficients for `v4.2`.
- `input-data-versions/dashboard-input-version-history.json`
  Responsibility: add the comprehensive `v4.2` entry with parameter changes, method rationale, and validation metrics.

**Files to create**
- `input-data-versions/v4.2/`
  Responsibility: copy-forward snapshot from `v4.1` with only the two expectation coefficients changed.
- `input-data-versions/validation/v4.2.json`
  Responsibility: published validation summary generated after `validate.sh` completes.
- `Results/v4.2-output/`
  Responsibility: full model output produced from the new snapshot for comparison against `v4.1`.

### Task 1: Extend The Existing Helpers With Only The Missing Modern-Window Logic

**Files:**
- Modify: `scripts/python/helpers/nmg/hpa_expectation.py`
- Modify: `scripts/python/helpers/ppd/hpa_signal_methods.py`
- Test: `scripts/python/tests/test_nmg_hpa_expectation.py`
- Test: `scripts/python/tests/test_ppd_hpa_signal_methods.py`

- [ ] **Step 1: Write failing helper tests for plausibility classification and fit diagnostics**

```python
def test_classify_plausibility_distinguishes_preferred_and_admissible_only():
    self.assertEqual(classify_hpa_expectation_fit(0.44, -0.007).label, "preferred")
    self.assertEqual(classify_hpa_expectation_fit(1.0, 0.02).label, "admissible")
    self.assertEqual(classify_hpa_expectation_fit(-0.1, 0.0).label, "inadmissible")
```

```python
def test_compute_fit_rmse_uses_all_anchor_years():
    rmse = compute_fit_rmse(
        x_values=[0.01, 0.02, 0.03],
        y_values=[0.03, 0.04, 0.05],
        factor=1.0,
        const=0.02,
    )
    self.assertAlmostEqual(rmse, 0.0, places=12)
```

```python
def test_build_hpa_signal_accepts_same_year_anchor_with_two_year_base():
    signal = build_hpa_signal(rows, anchor_year=2020, base_year=2018, method_name="annual_mean_annualised")
    self.assertEqual(signal.anchor_year, 2020)
    self.assertEqual(signal.base_year, 2018)
```

- [ ] **Step 2: Run the helper tests to confirm the new expectations fail**

Run:

```bash
python3 -m unittest \
  scripts.python.tests.test_nmg_hpa_expectation \
  scripts.python.tests.test_ppd_hpa_signal_methods -v
```

Expected: FAIL because the plausibility-classification and fit-diagnostic helpers do not exist yet.

- [ ] **Step 3: Add the minimal helper extensions without creating new helper modules**

```python
@dataclass(frozen=True)
class HpaExpectationFitClassification:
    label: str
    is_admissible: bool
    is_preferred: bool

def classify_hpa_expectation_fit(factor: float, const: float) -> HpaExpectationFitClassification:
    ...

def compute_fit_rmse(*, x_values: Iterable[float], y_values: Iterable[float], factor: float, const: float) -> float:
    ...
```

```python
def build_yearly_hpa_signals(
    rows: Sequence[PpdSaleRow],
    *,
    anchor_years: Sequence[int],
    method_name: str,
    preferred_gap: int = 2,
) -> dict[int, HpaSignal]:
    ...
```

- [ ] **Step 4: Re-run the helper tests**

Run:

```bash
python3 -m unittest \
  scripts.python.tests.test_nmg_hpa_expectation \
  scripts.python.tests.test_ppd_hpa_signal_methods -v
```

Expected: PASS

- [ ] **Step 5: Commit the helper-only change**

```bash
git add \
  scripts/python/helpers/nmg/hpa_expectation.py \
  scripts/python/helpers/ppd/hpa_signal_methods.py \
  scripts/python/tests/test_nmg_hpa_expectation.py \
  scripts/python/tests/test_ppd_hpa_signal_methods.py
git commit -m "feat [MS]: add constrained HPA expectation helper diagnostics for v4.2 calibration"
```

### Task 2: Repurpose The Method Search Around The `2018` To `2024` Production Window

**Files:**
- Modify: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Test: `scripts/python/tests/test_nmg_hpa_expectation_method_search.py`

- [ ] **Step 1: Write failing tests for the new parser defaults and ranking rule**

```python
def test_parser_defaults_use_modern_fit_window():
    args = build_arg_parser().parse_args([
        "nmg-2014.csv",
        "nmg-2016.csv",
        "nmg-2018.csv",
        "nmg-2019.csv",
        "nmg-2020.csv",
        "nmg-2021.csv",
        "nmg-2022.csv",
        "nmg-2023.csv",
        "nmg-2024.csv",
        "pp-2018.csv",
        "pp-2019.csv",
        "pp-2020.csv",
        "pp-2021.csv",
        "pp-2022.csv",
        "pp-2023.csv",
        "pp-2024.csv",
    ])
    self.assertEqual(args.fit_years, "2018,2019,2020,2021,2022,2023,2024")
```

```python
def test_ranking_prefers_preferred_band_before_lower_rmse_outside_band():
    preferred = CandidateEvaluation(..., is_admissible=True, is_preferred=True, rmse=0.012)
    admissible_only = CandidateEvaluation(..., is_admissible=True, is_preferred=False, rmse=0.011)
    ranked = rank_results([admissible_only, preferred])
    self.assertTrue(ranked[0].is_preferred)
```

```python
def test_ranking_uses_simplicity_only_when_rmse_is_effectively_tied():
    simpler = CandidateEvaluation(..., is_admissible=True, is_preferred=True, rmse=0.0100000)
    less_simple = CandidateEvaluation(..., is_admissible=True, is_preferred=True, rmse=0.0100004)
    ranked = rank_results([less_simple, simpler])
    self.assertEqual(ranked[0].survey_method_name, simpler.survey_method_name)
```

- [ ] **Step 2: Run the method-search test module to confirm failure**

Run:

```bash
python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation_method_search -v
```

Expected: FAIL because the CLI and ranking logic still target legacy recovery.

- [ ] **Step 3: Rewrite the method search around the approved design**

```python
PRODUCTION_FIT_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
DIAGNOSTIC_YEARS = (2014, 2016)
RMSE_TIE_TOLERANCE = 1e-6

def evaluate_candidate(...):
    factor, const = fit_linear_rule(...)
    classification = classify_hpa_expectation_fit(factor, const)
    rmse = compute_fit_rmse(...)
    return CandidateEvaluation(...)

def rank_results(results):
    lowest_rmse = min(item.rmse for item in results if item.is_admissible)
    return sorted(results, key=lambda item: (
        not item.is_admissible,
        not item.is_preferred,
        item.rmse,
        0 if abs(item.rmse - lowest_rmse) <= RMSE_TIE_TOLERANCE else 1,
        item.survey_simplicity_rank,
        item.signal_simplicity_rank,
    ))
```

- [ ] **Step 4: Re-run the method-search tests**

Run:

```bash
python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation_method_search -v
```

Expected: PASS

- [ ] **Step 5: Run the focused HPA expectation test slice**

Run:

```bash
python3 -m unittest \
  scripts.python.tests.test_nmg_hpa_expectation \
  scripts.python.tests.test_ppd_hpa_signal_methods \
  scripts.python.tests.test_nmg_hpa_expectation_method_search -v
```

Expected: PASS

- [ ] **Step 6: Commit the method-search refactor**

```bash
git add \
  scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py \
  scripts/python/tests/test_nmg_hpa_expectation_method_search.py
git commit -m "feat [MS]: retarget HPA expectation method search to the 2018-2024 v4.2 fit window"
```

### Task 3: Update The Production Calibration Entrypoint To Fit `2018` To `2024`

**Files:**
- Modify: `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Test: `scripts/python/tests/test_nmg_hpa_expectation_fit.py`

- [ ] **Step 1: Write failing tests for the new production CLI and multi-year fit path**

```python
def test_parser_accepts_modern_nmg_window_and_ppd_inputs():
    args = build_arg_parser().parse_args([
        "nmg-2018.csv",
        "nmg-2019.csv",
        "nmg-2020.csv",
        "nmg-2021.csv",
        "nmg-2022.csv",
        "nmg-2023.csv",
        "nmg-2024.csv",
        "--ppd",
        "pp-2018.csv",
        "pp-2019.csv",
        "pp-2020.csv",
        "pp-2021.csv",
        "pp-2022.csv",
        "pp-2023.csv",
        "pp-2024.csv",
    ])
    self.assertEqual(args.target_year, 2024)
```

```python
def test_run_calibration_returns_plausibility_status_for_modern_window():
    result = run_calibration(...)
    self.assertIn(result.classification.label, {"preferred", "admissible"})
    self.assertEqual(sorted(result.survey_means), [2018, 2019, 2020, 2021, 2022, 2023, 2024])
```

- [ ] **Step 2: Run the fit test module to confirm the current production entrypoint fails these expectations**

Run:

```bash
python3 -m unittest scripts.python.tests.test_nmg_hpa_expectation_fit -v
```

Expected: FAIL because the CLI is still locked to `2014` and `2024` only.

- [ ] **Step 3: Implement the modern-window production fit with locked method reuse**

```python
LOCKED_SURVEY_METHOD = "midpoint_rounded"
LOCKED_SIGNAL_METHOD = "java_like_annualised"  # or annual_mean_annualised if the search proves it wins
PRODUCTION_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)

def run_calibration(...):
    survey_means = ...
    signal_values = ...
    factor, const = fit_linear_rule(...)
    classification = classify_hpa_expectation_fit(factor, const)
    return CalibrationOutput(...)
```

- [ ] **Step 4: Re-run the fit tests and the full focused HPA slice**

Run:

```bash
python3 -m unittest \
  scripts.python.tests.test_nmg_hpa_expectation \
  scripts.python.tests.test_ppd_hpa_signal_methods \
  scripts.python.tests.test_nmg_hpa_expectation_method_search \
  scripts.python.tests.test_nmg_hpa_expectation_fit -v
```

Expected: PASS

- [ ] **Step 5: Commit the production-fit change**

```bash
git add \
  scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py \
  scripts/python/tests/test_nmg_hpa_expectation_fit.py
git commit -m "feat [MS]: fit v4.2 HPA expectation coefficients on the 2018-2024 modern window"
```

### Task 4: Run The Real Calibration, Lock The Winning Method, And Update Provenance Docs

**Files:**
- Modify: `scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py`
- Modify: `scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py`
- Modify: `scripts/python/AGENT_SCRIPT_STRUCTURE.md`
- Modify: `input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md`
- Modify: `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md` (only if wording needs a small factual correction after the real run)

- [ ] **Step 1: Run the modern-window method search on the private datasets**

Run:

```bash
python3 -m scripts.python.experiments.nmg.nmg_hpa_expectation_method_search \
  private-datasets/nmg/nmg-2014.csv \
  private-datasets/nmg/nmg-2016.csv \
  private-datasets/nmg/nmg-2018.csv \
  private-datasets/nmg/nmg-2019.csv \
  private-datasets/nmg/nmg-2020.csv \
  private-datasets/nmg/nmg-2021.csv \
  private-datasets/nmg/nmg-2022.csv \
  private-datasets/nmg/nmg-2023.csv \
  private-datasets/nmg/nmg-2024.csv \
  private-datasets/ppd/pp-2011.csv \
  private-datasets/ppd/pp.2012.csv \
  private-datasets/ppd/pp-2018.csv \
  private-datasets/ppd/pp-2019.csv \
  private-datasets/ppd/pp-2020.csv \
  private-datasets/ppd/pp-2021.csv \
  private-datasets/ppd/pp-2022.csv \
  private-datasets/ppd/pp-2023.csv \
  private-datasets/ppd/pp-2024.csv
```

Expected: ranked candidates with admissibility/preferred-band status, in-window RMSE, yearly anchor diagnostics, and `2014`/`2016` diagnostic outputs.

- [ ] **Step 2: Lock the winning production method family in the production fit script**

Required edits:
- set the winning survey method constant
- set the winning signal method constant
- keep `2018` to `2024` fixed as the production fit window

- [ ] **Step 3: Run the production calibration command and capture the final coefficients**

Run:

```bash
python3 -m scripts.python.calibration.nmg.nmg_hpa_expectation_fit \
  private-datasets/nmg/nmg-2018.csv \
  private-datasets/nmg/nmg-2019.csv \
  private-datasets/nmg/nmg-2020.csv \
  private-datasets/nmg/nmg-2021.csv \
  private-datasets/nmg/nmg-2022.csv \
  private-datasets/nmg/nmg-2023.csv \
  private-datasets/nmg/nmg-2024.csv \
  --ppd \
  private-datasets/ppd/pp-2011.csv \
  private-datasets/ppd/pp.2012.csv \
  private-datasets/ppd/pp-2018.csv \
  private-datasets/ppd/pp-2019.csv \
  private-datasets/ppd/pp-2020.csv \
  private-datasets/ppd/pp-2021.csv \
  private-datasets/ppd/pp-2022.csv \
  private-datasets/ppd/pp-2023.csv \
  private-datasets/ppd/pp-2024.csv \
  --target-year 2024
```

Expected: `HPA_EXPECTATION_FACTOR`, `HPA_EXPECTATION_CONST`, chosen method metadata, yearly anchor diagnostics, and plausibility status.

- [ ] **Step 4: Update script-structure and calibration changelog docs with the actual chosen method and output**

Required facts to record:
- fit window `2018` to `2024`
- chosen survey mapping
- chosen signal method
- final coefficients
- whether the fit landed in the preferred band or only the admissible range
- exact rerun commands

- [ ] **Step 5: Commit the locked method and provenance docs**

```bash
git add \
  scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py \
  scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py \
  scripts/python/AGENT_SCRIPT_STRUCTURE.md \
  input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md \
  docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md
git commit -m "docs [MS]: record v4.2 HPA expectation calibration method and provenance for reruns"
```

### Task 5: Run Subagent Code Review Before Shipping The Snapshot

**Files:**
- Review scope: the commits from Tasks 1 to 4
- Review context: `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md`
- Review context: `docs/superpowers/plans/2026-04-14-hpa-expectation-v4.2-production-calibration-plan.md`

- [ ] **Step 1: Identify the base and head SHAs covering the implementation work**

Run:

```bash
BASE_SHA=$(git rev-parse HEAD~4)
HEAD_SHA=$(git rev-parse HEAD)
printf '%s\n%s\n' "$BASE_SHA" "$HEAD_SHA"
```

Expected: two SHAs covering the helper, method-search, production-fit, and provenance commits. Record `BASE_SHA` for the final whole-change review in Task 7.

- [ ] **Step 2: Dispatch a subagent code review for the implementation range**

Review brief:
- what was implemented: modern-window constrained HPA expectation calibration for `v4.2`
- requirements: the approved design spec and this plan
- code under review: helper updates, method-search refactor, production-fit refactor, provenance docs

Expected: findings ordered by severity, with concrete file references and required follow-up.

- [ ] **Step 3: Fix any Critical or Important review findings and rerun the affected tests**

Run the narrowest relevant `unittest` command for each fix, then rerun the full HPA expectation slice:

```bash
python3 -m unittest \
  scripts.python.tests.test_nmg_hpa_expectation \
  scripts.python.tests.test_ppd_hpa_signal_methods \
  scripts.python.tests.test_nmg_hpa_expectation_method_search \
  scripts.python.tests.test_nmg_hpa_expectation_fit -v
```

Expected: PASS

- [ ] **Step 4: Re-dispatch the subagent review on the updated range if any fixes were required**

Expected: a fresh approval on the corrected code range before proceeding to the snapshot/release task.

- [ ] **Step 5: Commit any review-driven fixes with a narrow pathspec**

```bash
git add \
  scripts/python/helpers/nmg/hpa_expectation.py \
  scripts/python/helpers/ppd/hpa_signal_methods.py \
  scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py \
  scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py \
  scripts/python/tests/test_nmg_hpa_expectation.py \
  scripts/python/tests/test_ppd_hpa_signal_methods.py \
  scripts/python/tests/test_nmg_hpa_expectation_method_search.py \
  scripts/python/tests/test_nmg_hpa_expectation_fit.py \
  scripts/python/AGENT_SCRIPT_STRUCTURE.md \
  input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md \
  docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md \
  docs/superpowers/plans/2026-04-14-hpa-expectation-v4.2-production-calibration-plan.md
git commit -m "fix [MS]: address subagent review findings in v4.2 HPA expectation calibration"
```

### Task 6: Create `v4.2`, Validate It, And Produce The Release Artifacts

**Files:**
- Create: `input-data-versions/v4.2/*`
- Modify: `input-data-versions/dashboard-input-version-history.json`
- Create: `input-data-versions/validation/v4.2.json`
- Create: `Results/v4.2-output/*`

- [ ] **Step 1: Copy `v4.1` forward to `v4.2`**

Run:

```bash
cp -R input-data-versions/v4.1 input-data-versions/v4.2
```

Expected: new snapshot folder with the same baseline files as `v4.1`.

- [ ] **Step 2: Update only the two HPA expectation coefficients in `input-data-versions/v4.2/config.properties`**

Target keys:

```properties
HPA_EXPECTATION_FACTOR = <final factor from Task 4>
HPA_EXPECTATION_CONST = <final const from Task 4>
```

- [ ] **Step 3: Add the `v4.2` entry to `input-data-versions/dashboard-input-version-history.json`**

Required content:

```json
{
  "version_id": "v4.2",
  "snapshot_folder": "v4.2",
  "validation_dataset": "r8",
  "config_parameters": [
    "HPA_EXPECTATION_FACTOR",
    "HPA_EXPECTATION_CONST"
  ]
}
```

Also include:
- updated data sources `["nmg", "ppd"]`
- calibration script path(s)
- parameter change records with `null` dataset source for the two scalar parameters
- method variation describing the `2018` to `2024` constrained regression and plausibility rationale

- [ ] **Step 4: Run validation for the new snapshot**

Run:

```bash
bash input-data-versions/validate.sh v4.2
```

Expected: validation outputs under `tmp/validation/v4.2` and a publishable summary for `input-data-versions/validation/v4.2.json`.

- [ ] **Step 5: Publish the validation summary**

Expected file:

```text
input-data-versions/validation/v4.2.json
```

Confirm it records the final validation metrics used in `dashboard-input-version-history.json`.

- [ ] **Step 6: Run the full model into `Results/v4.2-output`**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
from scripts.python.helpers.common.abm_policy_sweep import build_snapshot_local_config_text

repo_root = Path.cwd()
version_config = repo_root / "input-data-versions" / "v4.2" / "config.properties"
run_config = repo_root / "tmp" / "v4.2-output.properties"
run_config.parent.mkdir(parents=True, exist_ok=True)
run_config.write_text(build_snapshot_local_config_text(version_config, {}), encoding="utf-8")
print(run_config)
PY
mvn -q -DskipTests compile
mvn -q exec:java -Dexec.args="-configFile tmp/v4.2-output.properties -outputFolder Results/v4.2-output -dev"
```

Expected: populated `Results/v4.2-output` comparable to `Results/v4.1-output`, using snapshot-local resource paths rather than mutating `src/main/resources`.

- [ ] **Step 7: Compare headline outputs against `v4.1` and record any material differences**

Run:

```bash
python3 scripts/model/model_speed.py print-v41-simulation-means --run-dir Results/v4.2-output
python3 scripts/model/model_speed.py print-v41-simulation-means --run-dir Results/v4.1-output
```

Expected: a concise comparison of post-200 mean values for house prices, transactions, mortgage approvals, and mortgage debt-to-income.

- [ ] **Step 8: Update `dashboard-input-version-history.json` with the final validation metrics and any release note wording refined by the real run**

- [ ] **Step 9: Commit the snapshot and provenance updates**

```bash
git add \
  input-data-versions/v4.2 \
  input-data-versions/dashboard-input-version-history.json \
  input-data-versions/validation/v4.2.json
git commit -m "feat [MS]: add v4.2 snapshot with 2024 HPA expectation recalibration"
```

### Task 7: Final Verification And Completion Gate

**Files:**
- Verify: all modified Python, docs, and `input-data-versions` files
- Verify: generated release artifacts exist at the expected paths

- [ ] **Step 1: Run the full Python HPA expectation test slice one last time**

Run:

```bash
python3 -m unittest \
  scripts.python.tests.test_nmg_hpa_expectation \
  scripts.python.tests.test_ppd_hpa_signal_methods \
  scripts.python.tests.test_nmg_hpa_expectation_method_search \
  scripts.python.tests.test_nmg_hpa_expectation_fit -v
```

Expected: PASS

- [ ] **Step 2: Confirm the new snapshot values are present**

Run:

```bash
rg -n "HPA_EXPECTATION_FACTOR|HPA_EXPECTATION_CONST" input-data-versions/v4.2/config.properties
```

Expected: exactly two updated coefficient lines with the final calibrated values.

- [ ] **Step 3: Confirm the release artifacts exist**

Run:

```bash
test -f input-data-versions/validation/v4.2.json
test -d Results/v4.2-output
```

Expected: both checks succeed with exit code `0`.

- [ ] **Step 4: Dispatch a final subagent code review for the complete change set**

Review context:
- spec: `docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md`
- plan: `docs/superpowers/plans/2026-04-14-hpa-expectation-v4.2-production-calibration-plan.md`
- implementation range: from `BASE_SHA` recorded in Task 5 through the current `HEAD`

Expected: final review either approves the work or returns concrete findings to address before completion.

- [ ] **Step 5: If review findings require changes, fix them, rerun the narrowest affected verification commands, and create one final commit**

```bash
git add \
  scripts/python/helpers/nmg/hpa_expectation.py \
  scripts/python/helpers/ppd/hpa_signal_methods.py \
  scripts/python/experiments/nmg/nmg_hpa_expectation_method_search.py \
  scripts/python/calibration/nmg/nmg_hpa_expectation_fit.py \
  scripts/python/tests/test_nmg_hpa_expectation.py \
  scripts/python/tests/test_ppd_hpa_signal_methods.py \
  scripts/python/tests/test_nmg_hpa_expectation_method_search.py \
  scripts/python/tests/test_nmg_hpa_expectation_fit.py \
  scripts/python/AGENT_SCRIPT_STRUCTURE.md \
  input-data-versions/CALIBRATION_PARAMETER_CHANGELOG.md \
  input-data-versions/v4.2/config.properties \
  input-data-versions/dashboard-input-version-history.json \
  input-data-versions/validation/v4.2.json \
  docs/superpowers/specs/2026-04-14-hpa-expectation-v4.2-production-calibration-design.md \
  docs/superpowers/plans/2026-04-14-hpa-expectation-v4.2-production-calibration-plan.md
git commit -m "fix [MS]: resolve final review findings for v4.2 HPA expectation release"
```

- [ ] **Step 6: Re-dispatch the final subagent review if Step 5 changed code or docs**

Expected: final approval reflects the post-fix state rather than the pre-fix review.
