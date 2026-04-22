# Spanish vs UK Java Improvement Report

This report compares only:

- `housing-model-spain/src/main/java`
- `uk-housing-model-individual-project/src/main/java`

It is based on the changed Java surface identified via `diff -rq` / `git diff --no-index --stat`.

## Comparison Surface

Changed or UK-only Java files covered by this report:

- `collectors/CoreIndicators.java`
- `collectors/HouseholdStats.java`
- `collectors/MicroDataRecorder.java`
- `collectors/Recorder.java`
- `collectors/TransactionRecorder.java`
- `data/EmploymentIncome.java`
- `data/Government.java` (UK-only)
- `housing/Bank.java`
- `housing/CentralBank.java`
- `housing/Config.java`
- `housing/Government.java` (UK-only)
- `housing/Household.java`
- `housing/HouseholdBehaviour.java`
- `housing/Model.java`
- `utilities/Pdf.java`

## Transferable Improvements

### Mortgage Policy and Underwriting

These all change how credit constraints, approvals, and mortgage terms are set or persisted.

#### T1. Central-bank soft-LTV quota engine with rolling enforcement and BTL coverage

- **Classification:** Transferable improvement
- **Improvement:** Replace the UK model's hard central-bank LTV caps with a softer, quota-based macroprudential regime that can allow controlled exceptions over rolling windows and can operate across FTB, HM, and BTL mortgages.
- **Spain locations:**
  - `housing/Config.java:55-70`
  - `housing/CentralBank.java:24-45, 56-81, 90-105, 125-153`
  - `housing/Bank.java:31-77, 156-210, 226-344, 442-474, 660-789, 991-1025`
  - `housing/Household.java:155-167, 436-453`
- **UK locations:**
  - `housing/Config.java:50-60`
  - `housing/CentralBank.java:24-35, 46-63, 88-108`
  - `housing/Bank.java:28-46, 103-156, 141-206, 291-321, 506-583, 605-623`
  - `housing/Household.java:146-153, 443-458`
- **What it achieves:** The Spain fork models borrower-based regulation more realistically than the UK branch's simple `min(bank hard cap, central-bank hard cap)` rule. It lets the model represent regulated soft ceilings with limited exceptions rather than a blunt always-binding cap.
- **Technical implementation:** Spain adds central-bank soft LTV thresholds plus maximum fractions above those thresholds. `Bank` tracks both prospective approvals and actual new mortgages over soft limits for FTB, HM, and BTL groups and only falls back to the central-bank soft cap when the projected breach rate would exceed the allowed quota.
- **Recommendation for UK model:** Potentially transferable, but only with UK-specific macroprudential evidence and only if the extra policy surface is actually wanted in the UK branch.

#### T2. Bank-side internal LTV sampling between soft and hard caps

- **Classification:** Transferable improvement
- **Improvement:** Add an internal bank LTV policy that sometimes samples leverage between a soft and a hard cap instead of always issuing a single deterministic maximum LTV.
- **Spain locations:**
  - `housing/Config.java:162-170`
  - `housing/Bank.java:83-92, 136-145, 663-687, 801-828`
- **UK locations:**
  - `housing/Config.java:146-148`
  - `housing/Bank.java:90-93, 506-515`
- **What it achieves:** Spain makes bank underwriting heterogeneous around a bank-defined soft threshold. That is more realistic than always lending at a single hard maximum whenever the borrower qualifies.
- **Technical implementation:** Spain introduces bank soft LTV levels and probabilities of lending above those soft levels for FTB, HM, and BTL segments. `Bank.getLoanToValueLimit(...)` first samples an internal LTV and only after that compares it with central-bank constraints.
- **Recommendation for UK model:** Transferable in principle, but not required for the T6/T10/T11 port and best treated as a separate underwriting realism change.

#### T3. BTL support in the LTI framework and approval tracking

- **Classification:** Transferable improvement
- **Improvement:** Extend the UK model's owner-occupier-only LTI policy machinery so BTL lending also has an explicit bank hard LTI limit, a central-bank soft LTI quota path, and approval-in-principle tracking.
- **Spain locations:**
  - `housing/Config.java:63-70, 171-173`
  - `housing/CentralBank.java:39-45, 71-77, 100-103, 139-149`
  - `housing/Bank.java:40-43, 73-77, 147-149, 205-210, 251-269, 465-474, 863-956, 991-1025`
  - `housing/Household.java:155-167`
- **UK locations:**
  - `housing/Config.java:54-58, 149-150`
  - `housing/CentralBank.java:30-35, 54-58, 94-108`
  - `housing/Bank.java:42-46, 115-125, 141-156, 302-318, 528-583, 605-623`
  - `housing/Household.java:146-153`
- **What it achieves:** Spain removes an asymmetry in the UK branch where soft-LTI policy is only tracked for FTB/HM lending.
- **Recommendation for UK model:** Not part of the current port. Treat as a distinct structural policy extension rather than bundling it into T6/T10/T11.

#### T4. Persistent household-level LTV offers, not just LTI offers

- **Classification:** Transferable improvement
- **Improvement:** Persist the LTV term offered in the approval-in-principle letter alongside the persistent LTI term, so mortgage pricing and maximum-price calculations use the exact terms already offered to the household.
- **Spain locations:**
  - `housing/Household.java:45-46, 69-70, 155-159, 436-440, 685-687`
  - `housing/Bank.java:504, 614`
- **UK locations:**
  - `housing/Household.java:44-45, 67, 444-445, 688`
  - `housing/Bank.java:345, 451`
- **What it achieves:** Spain makes approval-in-principle logic internally consistent once LTV assignment stops being a pure hard-cap lookup.
- **Recommendation for UK model:** Good standalone consistency improvement, but not required for the scoped T6/T10/T11 work that was requested.

#### T5. Separate minimum and maximum mortgage-age limits

- **Classification:** Transferable improvement
- **Improvement:** Replace the single UK age cap with a more expressive age policy: a minimum origination age and a separate maximum age for origination / repayment completion.
- **Spain locations:**
  - `housing/Config.java:156-158`
  - `housing/Bank.java:400-419`
- **UK locations:**
  - `housing/Config.java:141-142`
  - `housing/Bank.java:262-279`
- **What it achieves:** Spain can bar unrealistically young borrowers while still controlling old-age maturity truncation separately.
- **Technical implementation:** Spain introduces `BANK_MIN_AGE_LIMIT` and `BANK_MAX_AGE_LIMIT` and updates `Bank.getNPayments(...)` to return zero below the minimum age, to shorten owner-occupier maturities near the maximum age, and to preserve separate BTL treatment.
- **Recommendation for UK model:** Potentially useful, but not part of the requested T6/T10/T11 port.

#### T6. Optional interest-only versus amortising BTL mortgage mode

- **Classification:** Transferable improvement
- **Improvement:** Add a configuration switch that can model BTL mortgages either as interest-only or as standard amortising mortgages.
- **Spain locations:**
  - `housing/Config.java:36`
  - `housing/Bank.java:495-496, 597-598`
  - `housing/HouseholdBehaviour.java:342-347, 397-402`
- **UK locations:**
  - `housing/Bank.java:240-253, 291-486`
  - `housing/HouseholdBehaviour.java:321-326, 372-376`
- **What it achieves:** Spain decouples investor behaviour from one fixed financing assumption. That improves model flexibility and allows cleaner sensitivity tests around BTL financing structure.
- **Technical implementation:** Spain adds `interestOnlyMortgagesForBTL` to config. `Bank.requestApproval(...)` and `Bank.getMaxMortgagePrice(...)` can force BTL requests through the owner-occupier amortising path when the toggle is off. `HouseholdBehaviour` also changes how it computes investor mortgage-rate drag depending on the mode.
- **Recommendation for UK model:** Transfer as an opt-in capability only, preserving the legacy UK default unless explicitly enabled.
- **Implementation status (UK):** Ported as `enableBTLAmortizingMortgageMode`, default `false`. The UK branch keeps its legacy interest-only BTL path by default and only switches sizing / financing-drag interpretation when the positive toggle is set to `true`.

### BTL Finance and Investor Behaviour (PORTED)

These are specifically about investor-side financing assumptions and BTL decision behaviour.

**Implementation status**

- Baseline: the implementation was anchored to `input-data-versions/v4.10`, and `src/main/resources` was aligned to that snapshot during the port work.
- Toggle policy: the Spain-derived behaviour is now opt-in. Checked-in UK configs default to legacy behaviour unless a positive feature toggle is set to `true`.
- Regression coverage: the JUnit suite now covers legacy default-off behaviour, new-on paths for T6/T10/T11, exhaustive snapshot config loading, and a process-level `v4.10` regression against the captured pre-port baseline.

#### T10. BTL down-payment distribution upgraded from a noisy percentage rule to a log-normal distribution

- **Classification:** Transferable improvement
- **Improvement:** Replace the UK branch's BTL down-payment rule `housePrice * max(0, mean + epsilon * gaussian)` with the same distributional approach already used for owner-occupiers: an HPI-scaled log-normal draw indexed by the household's income percentile.
- **Spain locations:**
  - `housing/Config.java:105-108`
  - `housing/HouseholdBehaviour.java:34-35, 217-227`
- **UK locations:**
  - `housing/Config.java:93-95`
  - `housing/HouseholdBehaviour.java:199-205`
- **What it achieves:** Spain gives BTL down-payments a more realistic positive-only distribution and aligns investor deposits with the rest of the model's deposit-generation approach.
- **Technical implementation:** Spain adds log-normal scale and shape parameters for BTL down-payments, instantiates `downpaymentDistBTL`, and uses `housingMarketStats.getHPI() * inverseCumulativeProbability(incomePercentile)` when choosing BTL down-payments.
- **Recommendation for UK model:** Transferable as a mechanism, but UK values should be calibrated separately rather than copied from Spain.
- **Implementation status (UK):** Ported as `enableBTLDownpaymentLognormal`, default `false`, with `DOWNPAYMENT_BTL_SCALE` and `DOWNPAYMENT_BTL_SHAPE` backfilled across all checked-in snapshot configs as TODO-calibrate placeholders.

#### T11. BTL expected-yield logic now subtracts alternative returns and handles amortising-finance cases

- **Classification:** Transferable improvement
- **Improvement:** Improve investor buy/sell decisions by comparing property returns to an outside option and by computing financing drag differently when BTL mortgages are amortising rather than interest-only.
- **Spain locations:**
  - `housing/Config.java:128`
  - `housing/HouseholdBehaviour.java:341-350, 397-406`
- **UK locations:**
  - `housing/HouseholdBehaviour.java:321-326, 372-376`
- **What it achieves:** Spain's investor choice rule is economically cleaner. It evaluates BTL as an excess-return decision instead of assuming the alternative return is always zero.
- **Technical implementation:** Spain adds `BTL_ALTERNATIVE_RETURN` and subtracts it inside the expected equity-yield calculation for both buy and sell decisions. It also branches the mortgage-rate term on `interestOnlyMortgagesForBTL`, using annual interest expense instead of annual payment flow when the mortgage is amortising.
- **Recommendation for UK model:** Transferable as an opt-in behaviour change, provided UK-side calibration and regression checks remain explicit.
- **Implementation status (UK):** Ported as `enableBTLAlternativeReturn`, default `false`, with `BTL_ALTERNATIVE_RETURN = 0.0` backfilled across snapshots as a TODO-calibrate placeholder. The call-site logic for the real BTL buy/sell decision paths is now covered in tests.

### Accounting, Wealth, and Microdata (PORTED)

These improve observability, reporting, diagnostics, and empirical analysis rather than core market mechanics.

#### T7. Housing-consumption decomposition recorded before payments and aggregated sector-wide

- **Classification:** Transferable improvement
- **Improvement:** Track housing consumption as separate components rather than burying it inside bank-balance updates: rent, down-payments, principal repayment, interest, and total non-housing consumption.
- **Spain locations:**
  - `housing/Household.java:96-110, 179-193, 313-315`
  - `collectors/HouseholdStats.java:47-57, 80-89, 239-249, 272-305, 371-380`
  - `collectors/Recorder.java:119-124, 247-252`
- **UK locations:**
  - `housing/Household.java:92-103, 320-323`
  - `collectors/HouseholdStats.java:39-44, 53-56, 159-164, 229-232`
  - `collectors/Recorder.java:117-119, 229-240`
- **What it achieves:** Spain turns household spending into interpretable national-accounts-style aggregates. That gives direct visibility into how much cash flow is going to rent, debt service, deposits, and non-housing spending.
- **Recommendation for UK model:** Already ported.

#### T8. Sector wealth accounting for financial wealth, housing net wealth, and housing gross wealth

- **Classification:** Transferable improvement
- **Improvement:** Replace the UK branch's single per-household housing wealth output with sector-wide wealth accounting that distinguishes liquid wealth, gross housing assets, and net housing equity.
- **Spain locations:**
  - `collectors/HouseholdStats.java:59-62, 120-185, 351-354`
  - `collectors/Recorder.java:123-124, 253-256`
- **UK locations:**
  - `collectors/HouseholdStats.java:130-142`
  - `collectors/Recorder.java:117-119, 178-240`
- **What it achieves:** Spain makes wealth composition explicit, which is much more useful for diagnosing leverage, collateral, and balance-sheet channels than the UK's single housing-wealth measure.
- **Recommendation for UK model:** Already ported.

#### T9. Expanded household microdata for housing equity, debt, status, and consumption

- **Classification:** Transferable improvement
- **Improvement:** Extend per-household microdata output beyond employment, rent, bank balance, housing wealth, house count, age, and saving rate to include net housing wealth, total debt, housing status, and consumption.
- **Spain locations:**
  - `housing/Config.java:41-50`
  - `housing/Model.java:128-131, 156-159`
  - `collectors/HouseholdStats.java:123-127, 186-225`
  - `collectors/MicroDataRecorder.java:21-27, 42-47, 80-127, 138-143, 169-317`
  - `housing/Household.java:41-42, 679-681`
- **UK locations:**
  - `housing/Config.java:40-47`
  - `housing/Model.java:128-130, 155-157`
  - `collectors/HouseholdStats.java:75-77, 117-152`
  - `collectors/MicroDataRecorder.java:17-24, 39-42, 75-106, 109-240`
  - `housing/Household.java:41, 684`
- **What it achieves:** Spain makes household-level state far more useful for validation and distributional analysis.
- **Recommendation for UK model:** Already ported.

### Simulation and Numerical Infrastructure (PORTED)

These improve reproducibility and numerical quality at the simulation-engine level.

#### T12. Per-simulation PRNG reseeding for Monte Carlo runs

- **Classification:** Transferable improvement
- **Improvement:** Ensure each Monte Carlo run starts from a deterministic but distinct seed rather than treating `N_SIMS` as one long random stream.
- **Spain locations:**
  - `housing/Model.java:75-76, 121-123`
- **UK locations:**
  - `housing/Model.java:77-80, 121-130`
- **What it achieves:** Spain makes repeated simulations more clearly separable and reproducible.
- **Technical implementation:** Spain constructs `MersenneTwister` without a seed up front, then explicitly reseeds at the start of each simulation loop.
- **Recommendation for UK model:** Already ported.
- **Implementation status (UK):** Implemented on `master` in commit `25f46ef` via per-simulation reseeding in `housing/Model.java`, preserving existing single-run behaviour for run 1.

#### T13. `Pdf` support trimming to the actual non-zero support

- **Classification:** Transferable improvement
- **Improvement:** Ignore zero-probability tails when building the support of empirical PDFs.
- **Spain locations:**
  - `utilities/Pdf.java:44-80`
- **UK locations:**
  - `utilities/Pdf.java`
- **What it achieves:** Spain avoids carrying unnecessary zero-density tails through the PDF support, improving numerical cleanliness.
- **Recommendation for UK model:** Already ported.

## Lower-Confidence Or Non-Transferable Differences

These were present in the Spain fork but were not clearly valid UK improvements, so they should not be silently ported.

#### N1. Spain loosens the UK investor entry / retention heuristics

- **Classification:** Lower-confidence difference
- **Change:** Spain comments out the UK rule that always keeps at least one investment property and the UK rule that always buys when the investor owns no investment property yet, replacing both with TODOs.
- **Why it is not clearly transferable:** Those heuristics materially change investor participation and inventory persistence, and the UK branch already has its own empirical calibration chain for BTL behaviour.
- **Recommendation for UK model:** Do not port as part of T6/T10/T11.

#### N2. Spain's wider BTL policy stack is not a drop-in UK replacement

- **Classification:** Lower-confidence difference
- **Change:** Spain combines the T6 financing toggle with broader BTL LTV/LTI soft-limit machinery and a different supervisory regime.
- **Why it is not clearly transferable:** The UK model's policy baseline is different, and reusing Spain's broader borrower-based policy surface would conflate institutional differences with the narrower financing / investor-behaviour changes that were requested.
- **Recommendation for UK model:** Keep the UK T6/T10/T11 port scoped to opt-in financing and behavioural mechanisms only.
