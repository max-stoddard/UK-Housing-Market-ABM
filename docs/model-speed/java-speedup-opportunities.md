# Potential Java Speedup Opportunities
Author: Max Stoddard

This artifact records the strongest currently identified opportunities for speeding up the Java ABM in `src/main/java`.
It is based on read-only source review, the checked-in historical JFR method breakdown, current model-speed benchmark policy,
and parallel GPT-5.5 xhigh subagent review.

No code was changed while preparing this document. The impact estimates below are engineering estimates, not accepted speed
claims. Any candidate must pass the current exact model-output contract and the 20k execution-time benchmark before it can
be treated as a model-speed improvement.

## Evidence Base

Primary local evidence:
- `docs/model-speed/README.md`
- `docs/model-speed/20k-speed-detection-benchmark.md`
- `docs/model-speed/profiles/JFR_METHOD_BREAKDOWN.md`
- `src/main/java`

Current speed contract:
- Exact correctness gate: `v0 / e2e-default-5k-s1`, three exact repeats against
  `docs/model-speed/baselines/v0-e2e-default-5k-s1.exact.sha256`.
- Execution-time gate: `v0 / core-minimal-20k-s1`, 10 measured repeats, one pinned core, JVM
  `-XX:ActiveProcessorCount=1`.
- Headline speed metric: `wall_clock_seconds`.
- Supporting normalised metric: `seconds_per_household_month`.

Important caveat:
- The checked-in JFR report is historical v4.1 smoke-profile evidence, not a current v0 profile. It is still useful because
  its hotspot shape matches the current source structure, but every proposed optimisation needs a fresh v0 benchmark and,
  ideally, a fresh JFR after implementation.

Historical JFR hotspot shape:
- `Household.getAnnualFinanceCosts` was the top sampled method: about `8.9%` of core-minimal model-step samples and
  `14.5%` of full-output e2e model-step samples.
- The household loop dominated model-step samples: about `51.7%` core-minimal and `45.4%` e2e.
- `HouseRentalMarket.clearMarket()` was the second largest direct model-step phase: about `24.6%` core-minimal and
  `22.6%` e2e.
- `HouseholdStats.record()` was material: about `12.7%` core-minimal and `21.5%` e2e.
- `TreeMap`/`TreeSet` methods in market queues were heavily represented: `getFirstEntry`, `successor`, `getFloorEntry`,
  `getEntryUsingComparator`, and `put`.

Non-opportunity note:
- The current Java source already contains a dirty cached `Household.getMonthlyGrossRentalIncome()` implementation in
  `Household.java`. Do not count the previously measured rental-income cache as a new speedup opportunity unless a future
  review shows the current worktree differs from that accepted behavior. The old changelog note about promoting that
  isolated candidate should be treated cautiously until reconciled.

## Ranking Summary

| Rank | Opportunity | Likely 20k Speedup | Likelihood | Model Risk | Best First Slice |
| ---: | --- | ---: | --- | --- | --- |
| 1 | Make `HouseholdStats.record()` a true minimal-mode, one-pass collector | `4-9%` | High | Low-medium | Gate core-indicator-only work when unused; reuse per-household locals |
| 2 | Cache or tightly optimise `Household.getAnnualFinanceCosts()` | `3-8%` | Medium-high | Medium | Replace tenant-side lookup with landlord-side rental-contract lookup and local `nextPayment()` values |
| 3 | Specialise market clearing / `PriorityQueue2D` | `3-10%+` | Medium | Medium-high to high | Resolve only matched offers before a full queue rewrite |
| 4 | Reduce repeated household decision math and mortgage approval work | `2-5%` | Medium-high | Low-medium | Hoist duplicate max-mortgage and payment-factor calculations |
| 5 | Remove avoidable collector allocation and disabled-output work | `1.5-4%` | High | Low | Reuse arrays, remove unused bid/offer price arrays, guard disabled bid-up counters |

The first and fifth opportunities are the most attractive starting points because they are mostly collector-local and should
not alter model decisions if implemented carefully. The market queue opportunity has the largest upside but also the most
behavioral risk because exact offer ordering is part of the model.

## 1. Make `HouseholdStats.record()` A True Minimal-Mode, One-Pass Collector

### Scope

Primary files:
- `src/main/java/collectors/HouseholdStats.java`
- `src/main/java/housing/Model.java`
- `src/main/java/collectors/CoreIndicators.java`
- `src/main/java/collectors/MicroDataRecorder.java`

Key current call sites:
- `Model.modelStep()` calls `householdStats.record()` every model step.
- `HouseholdStats.record()` loops through every household every step.
- The core-minimal speed mode has all microdata and core-indicator output disabled, but `record()` still computes many
  values that are only needed for those outputs.

### Current Cost Mechanism

`HouseholdStats.record()` currently does several expensive things in one full-population pass:
- Repeatedly calls `h.getNProperties()` for BTL household classification.
- Calls `h.getMonthlyNetTotalIncome()` for annualised income buckets.
- Calls into the known `getAnnualFinanceCosts()` hotspot through `getMonthlyNetTotalIncome()`.
- Separately scans `h.getHousePayments()` to compute housing wealth, gross housing wealth, and total debt.
- Calls microdata timestamp/record methods every month, even though microdata only writes on selected months and is disabled
  in the core-minimal benchmark.

On the current speed gate, `recordCoreIndicators=false` and microdata flags are false. The main monthly summary still needs
some aggregate fields, but not all core-indicator-only income/yield calculations.

### Why It Should Speed Up

This reduces work on a guaranteed monthly full-population path. On `TARGET_POPULATION=20000` and `N_STEPS=2000`, even small
per-household savings accumulate across roughly 40 million household-step visits.

Expected wins:
- Fewer `TreeMap` scans through `housePayments`.
- Fewer calls into `getMonthlyNetTotalIncome()` and `getAnnualFinanceCosts()` in minimal-output mode.
- Fewer per-household method calls and branches for disabled microdata.
- Less allocation and lower pressure on branch-heavy collector code.

### Candidate Implementation Shape

Recommended first slice:
- Add a collector-local boolean, such as `needsCoreIndicatorInputs`, derived from `config.recordCoreIndicators` and any
  future explicit central-bank-policy dependency on `CoreIndicators`.
- In `HouseholdStats.record()`, compute annualised net income buckets and stock rental yield only when those fields are
  needed.
- Compute `int time = Model.getTime()` once and pass/reuse it.
- Compute microdata activity once per month, e.g. "any microdata flag is true and this is a microdata print month", then
  skip all microdata getter/recorder work when false.
- Within each household iteration, scan `housePayments` once to derive:
  - `nProperties`
  - housing net wealth
  - housing gross wealth
  - total debt
  - rented-home payment needed for stock-yield output, if that output is needed
- Reuse the local `nProperties` for category classification and `recordNHousesOwned`.

Avoid:
- Changing the semantics of `Household.getNProperties()` in the first slice.
- Reordering floating-point summation unless exact output proves unchanged.
- Assuming `recordCoreIndicators=false` always means `CoreIndicators` is irrelevant. `CentralBank.step(coreIndicators)` is
  currently empty, but a future policy implementation could consume these fields without recording them.

### Expected Impact

Estimated 20k speedup: `4-9%` for a full minimal-mode and one-pass collector cleanup.

The lower end is plausible if most income fields are still needed by the main summary output. The upper end is plausible if
minimal mode can skip most annualised income and stock-yield work that currently pulls the finance-cost hotspot.

Likelihood: High.

### Model Risk

Risk: Low-medium.

The change is mostly observational/collector-side, but this model writes exact output hashes. Even if model decisions are
unchanged, output can change if:
- category counts are computed differently,
- floating-point summation order changes,
- microdata row timing changes,
- core-indicator inputs are skipped when a policy consumes them.

### Required Tests And Benchmarks

Focused tests:
- Household category count coverage for BTL active, BTL owner-occupier, BTL homeless, non-BTL owner, renter, and social
  housing.
- Housing wealth/gross wealth/debt accounting fixtures.
- Microdata print-month predicate coverage.
- If a `needsCoreIndicatorInputs` switch is added, tests for both enabled and disabled paths.

Acceptance checks:
- `mvn -q test`
- three-run exact `v0 / e2e-default-5k-s1`
- 10-run `v0 / core-minimal-20k-s1`
- JFR profile after acceptance to confirm `HouseholdStats.record()` and `getAnnualFinanceCosts()` shares fall.

## 2. Cache Or Tightly Optimise `Household.getAnnualFinanceCosts()`

### Scope

Primary files:
- `src/main/java/housing/Household.java`
- `src/main/java/housing/RentalAgreement.java`
- `src/main/java/housing/MortgageAgreement.java`
- `src/main/java/housing/PaymentAgreement.java`

Key current methods:
- `Household.getMonthlyNetTotalIncome()`
- `Household.getAnnualFinanceCosts()`
- `Household.getMonthlyGrossTotalIncome()`
- `Household.getMonthlyGrossRentalIncome()`

### Current Cost Mechanism

`getAnnualFinanceCosts()` scans `housePayments` and checks whether each owned mortgage should receive tax relief. For each
eligible-looking property it:
- checks `payment instanceof MortgageAgreement`,
- checks ownership,
- calls `payment.nextPayment()`,
- checks whether the house has a resident,
- asks the resident household for its `housePayments`,
- performs `get(house)` on the resident's `TreeMap`,
- calls `nextPayment()` again,
- adds the owner's mortgage payment.

The method is reached through `getMonthlyNetTotalIncome()`, which is used in household cash-flow decisions and collector
statistics. Historical JFR identifies this method as the highest single Java method hotspot.

### Why It Should Speed Up

This is a hot method with repeated map traversal and nested map lookup. Reducing the number and cost of calls has direct
payoff because net-income calculation is used throughout the household loop and stats collectors.

Expected wins:
- Fewer `TreeMap` lookups.
- Fewer `nextPayment()` calls.
- Avoid scanning unchanged landlord property portfolios.
- Reduce a top sampled method rather than optimising cold code.

### Candidate Implementation Shape

Conservative first slice:
- In `getAnnualFinanceCosts()`, store `payment.nextPayment()` in a local variable.
- Replace the tenant-side `house.resident.getHousePayments().get(house).nextPayment()` lookup with landlord-side
  `rentalContracts.get(house)` where possible. The landlord already maintains rental contracts for rented-out houses.
- Treat the landlord-side contract as the canonical source only after tests prove lifecycle invariants:
  - `putRentalContract()` runs exactly when a rental starts.
  - `removeRentalContract()` runs on tenancy end, eviction, sale, and inheritance.
  - final tenant payment invalidates landlord rental-income state.

Larger candidate:
- Add a dirty cached monthly or annual finance-cost total to `Household`, following the existing dirty rental-income cache
  pattern.
- Recompute in existing `TreeMap` order to preserve floating-point behavior.
- Mark dirty on every lifecycle path that can affect finance-cost eligibility:
  - mortgage monthly payment reducing `nPayments` or principal,
  - mortgage payoff,
  - house purchase,
  - house sale,
  - residual debt after sale,
  - inheritance,
  - rental contract creation,
  - rental contract removal,
  - final rental payment,
  - eviction,
  - tenant death/end tenancy.

Avoid:
- Incremental arithmetic updates as a first attempt. Dirty recomputation is safer because eligibility depends on both
  landlord mortgage state and tenant payment state.
- Changing tax semantics. Finance-cost relief directly affects disposable income and therefore model behavior.

### Expected Impact

Estimated 20k speedup:
- Local cleanup only: `0.5-2%`.
- Dirty cache or equivalent call elimination: `3-8%`.

Likelihood:
- High for local cleanup.
- Medium-high for a dirty cache if lifecycle invalidation is complete.

### Model Risk

Risk: Medium.

This change can alter model behavior if any invalidation path is missed. Incorrect finance costs change income tax, monthly
net income, consumption, savings, bank balances, purchase/rent decisions, and downstream market outcomes.

The change is likely beneficial if exact regression passes, but it must not be accepted on speed evidence alone.

### Required Tests And Benchmarks

Focused tests:
- Landlord finance cost with active tenant.
- Landlord finance cost after tenant final payment.
- Landlord finance cost after eviction.
- Landlord finance cost after sale of rented property.
- Landlord finance cost after inheritance transfer.
- Mortgage payoff and zero-payment mortgage paths.
- Renter death/end-tenancy paths if covered by existing fixtures.

Acceptance checks:
- `mvn -q test`
- three-run exact `v0 / e2e-default-5k-s1`
- 10-run `v0 / core-minimal-20k-s1`
- JFR profile confirming `Household.getAnnualFinanceCosts()` is no longer dominant.

## 3. Specialise Market Clearing And `PriorityQueue2D`

### Scope

Primary files:
- `src/main/java/housing/HousingMarket.java`
- `src/main/java/housing/HouseSaleMarket.java`
- `src/main/java/housing/HouseRentalMarket.java`
- `src/main/java/housing/HousingMarketRecord.java`
- `src/main/java/housing/HouseOfferRecord.java`
- `src/main/java/housing/HouseBidderRecord.java`
- `src/main/java/utilities/PriorityQueue2D.java`

### Current Cost Mechanism

Both sale and rental markets rely on `PriorityQueue2D`, implemented with two `TreeSet`s:
- `xySortedElements`
- `uncoveredElements`

At market clearing:
- `sortPriorities()` rebuilds the uncovered skyline.
- `peek()` uses `TreeSet.floor()`.
- removals update both sets and may uncover later elements.
- sale-market BTL matching maintains an additional price-yield queue.

Historical JFR shows substantial time in:
- `TreeMap.getFirstEntry`
- `TreeMap.successor`
- `TreeMap.getFloorEntry`
- `TreeMap.getEntryUsingComparator`
- `TreeMap.put`
- `HousingMarketRecord.PQComparator.XCompare`
- `HousingMarket.matchBidsWithOffers`
- `HousingMarket.clearMatches`

`HousingMarket.clearMatches()` also scans every offer each round even though only offers with matched bids can transact.

### Why It Should Speed Up

Market clearing is a large direct model-step phase. Tree-based operations are flexible but expensive for the model's
repeated monthly matching workload. The rental market in particular uses price-quality matching, where quality is an integer
band and could potentially use a more specialised structure.

Expected wins:
- Fewer `TreeSet`/`TreeMap` operations.
- Fewer comparator calls.
- Less full-offer iteration for unmatched offers.
- Lower allocation from matched-bid lists and sorting.

### Candidate Implementation Shape

Safest first slice:
- Track offers that receive at least one bid during `matchBidsWithOffers()`.
- Resolve only that matched-offer set in the same order as the current `offersPQ` iterator.
- Preserve failed-bid requeue order exactly.
- Preserve the current number and order of PRNG draws.

Smaller low-risk cleanups:
- Reuse a singleton `HouseBidderRecord.PComparator` instead of creating a new comparator for every oversubscribed offer.
- Lazily allocate `HouseOfferRecord.matchedBids` only on first match, while preserving zero-size behavior for unmatched
  offers.
- Replace `Math.signum` comparator implementations with branch-based comparisons only if exact tie behavior is covered by
  tests.

Larger candidate:
- Replace or specialise `PriorityQueue2D` with an exact indexed offer-book.
- For price-quality queues, consider per-quality cheapest offer indexes plus a higher-quality search structure.
- For sale-market price-yield BTL matching, keep an exact price-yield path that preserves current price and record-id
  tie-breaks.

Avoid:
- Any approximate price bucketing.
- Any change to transaction ordering.
- Any change to market-clearing rounds.
- Any change to geometric bid-up PRNG draw count or timing.

### Expected Impact

Estimated 20k speedup:
- Matched-offer-only clearing: `1-4%`.
- Small allocation/comparator cleanup: `0.5-2%`.
- Exact `PriorityQueue2D` specialisation: `3-10%+`, with some reviewers estimating more if most tree churn is removed.

Likelihood:
- High for small cleanups.
- Medium-high for matched-offer-only clearing if matched-offer sparsity is high.
- Medium for a full queue replacement.

### Model Risk

Risk:
- Low-medium for matched-offer-only clearing.
- Medium-high to high for a queue replacement.

Market ordering is model behavior. Even a byte-for-byte equivalent-looking data structure can alter outcomes if it changes:
- same-price tie ordering,
- same-quality or same-yield tie ordering,
- offer iterator order,
- bid requeue order,
- removal timing,
- PRNG draw timing.

### Required Tests And Benchmarks

Focused tests:
- `PriorityQueue2D` equivalence tests for add, update, remove, iterator remove, and peek.
- Randomised positive-price/quality/yield tests comparing old and new selection/removal sequences.
- Market-clearing fixtures for:
  - unmatched offers,
  - single matched bid,
  - oversubscribed offers,
  - same-owner bid rejection,
  - failed-bid requeue,
  - BTL sale-market yield ordering,
  - rental price-quality ordering.
- Transaction trace hash tests, if practical.

Acceptance checks:
- `mvn -q test`
- three-run exact `v0 / e2e-default-5k-s1`
- 10-run `v0 / core-minimal-20k-s1`
- JFR profile confirming reduced `TreeMap`/market-clearing samples.

## 4. Reduce Repeated Household Decision Math And Mortgage Approval Work

### Scope

Primary files:
- `src/main/java/housing/Household.java`
- `src/main/java/housing/HouseholdBehaviour.java`
- `src/main/java/housing/Bank.java`
- `src/main/java/data/EmploymentIncome.java`
- `src/main/java/data/Wealth.java`

### Current Cost Mechanism

Several per-household monthly calculations repeat deterministic work:
- `Household.step()` recomputes employment income every month from age and fixed income percentile.
- `EmploymentIncome.getAnnualGrossEmploymentIncome()` searches age bins and evaluates an inverse-CDF interpolation.
- `HouseholdBehaviour.updateDesiredPurchasePrice()` computes `Math.pow`, `Math.exp`, and consumes a Gaussian for every
  household every month, even when many households cannot bid for a home this step.
- `Household.step()` computes `Model.bank.getMaxMortgagePrice(...)` and then behavior methods may compute it again with
  unchanged state.
- `Bank.requestApproval()` and `Bank.getMaxMortgagePrice()` repeatedly call `getNPayments()` and
  `getMonthlyPaymentFactor()`, where non-BTL payment factors include `Math.pow`.

### Why It Should Speed Up

The household loop is the dominant direct model-step phase. These operations are not necessarily the single hottest method
after finance-cost work, but they occur frequently across the population.

Expected wins:
- Avoid repeated age-bin and inverse-CDF work when a household remains in the same income age bin.
- Avoid repeated mortgage factor calculations within the same method call.
- Avoid duplicate max-mortgage calculations in one decision.
- Avoid expensive purchase-price transforms when only the RNG draw must be preserved.

### Candidate Implementation Shape

Recommended first slices:
- In `Bank.requestApproval()` and `Bank.getMaxMortgagePrice()`, compute `age`, `nPayments`, `monthlyPaymentFactor`, LTV
  limit, affordability limit, and BTL annual payment rate once per call.
- In household purchase decisions, pass already computed max mortgage prices into behavior methods rather than recomputing.
- Keep old overloads or wrappers where tests and callers need them.

Potential larger slices:
- Cache each household's current employment-income age-bin result. Recompute only when `age` crosses the next income-bin
  boundary or support clamp.
- When employment income changes, precompute deterministic income power terms such as
  `BUY_SCALE * Math.pow(income, BUY_EXPONENT)` and the corresponding rent-budget scale.
- Split the desired-purchase-price Gaussian draw from the expensive transform. Consume exactly the same Gaussian at the same
  point for every household, but only compute the `pow`/`exp` product when the household can bid this step.

Avoid:
- Changing RNG engine, Gaussian implementation, or draw order.
- Approximating `Math.pow`, `Math.exp`, inverse CDF, or PDF sampling.
- Lowering `Pdf.DEFAULT_CDF_SAMPLES`; that is likely to fail the exact regression contract.

### Expected Impact

Estimated 20k speedup:
- Bank local hoisting: `0.5-2%`.
- Duplicate max-mortgage elimination: `1-3%`.
- Employment-income age-bin cache: `2-5%`.
- Desired-purchase transform gating: `1-3%`.
- Combined carefully: `2-5%`, possibly more if current v0 JFR confirms these paths remain hot.

Likelihood: Medium-high.

### Model Risk

Risk:
- Low for Bank-local hoisting and duplicate max-mortgage elimination.
- Low-medium for employment-income caching due boundary semantics.
- Medium for desired-purchase transform gating because RNG draw order must remain exact.

If RNG draw order changes, exact regression will almost certainly fail and model behavior will diverge.

### Required Tests And Benchmarks

Focused tests:
- Bank approval and max-price fixtures for:
  - first-time buyer,
  - home mover,
  - BTL,
  - age-limit boundary,
  - zero-payment boundary,
  - amortising BTL toggle if enabled.
- Employment-income boundary tests around every age-bin edge and support clamp.
- Seeded household tests proving the same number and order of PRNG draws.
- Formula equality tests for purchase and rent budgets.

Acceptance checks:
- `mvn -q test`
- three-run exact `v0 / e2e-default-5k-s1`
- 10-run `v0 / core-minimal-20k-s1`
- JFR profile confirming household-loop math and Bank approval samples fall.

## 5. Remove Avoidable Collector Allocation And Disabled-Output Work

### Scope

Primary files:
- `src/main/java/collectors/HousingMarketStats.java`
- `src/main/java/collectors/CreditSupply.java`
- `src/main/java/collectors/CoreIndicators.java`
- `src/main/java/housing/HousingMarket.java`
- `src/main/java/collectors/TransactionRecorder.java`
- `src/main/java/collectors/Recorder.java`
- `src/main/java/collectors/MicroDataRecorder.java`

### Current Cost Mechanism

`HousingMarketStats.preClearingRecord()` does per-step allocation:
- `sumMonthsOnMarketPerQualityCount = new double[...]`
- `sumSalePricePerQualityCount = new double[...]`
- `nSalesPerQualityCount = new int[...]`
- `offerPrices = new double[nSellers]`
- `bidPrices = new double[nBuyers]`

The bid/offer price arrays appear to have no current Java consumers except getters. The main output uses aggregate average
values, not the arrays.

`HousingMarket.clearMarket()` also allocates and updates `nBidUpFrequency` even when `recordNBidUpFrequency=false`, which is
the case for both current model-speed gates.

`CreditSupply.recordLoan()` stores boxed `Double` LTV/LTI values for core indicators even when the core-minimal speed mode
does not record core indicators. Core-indicator output later combines and sorts these values.

### Why It Should Speed Up

This reduces repeated allocation in monthly paths. The expected wall-clock effect is smaller than top household and market
hotspots, but it is low-risk and should reduce GC/RSS pressure.

Expected wins:
- Fewer short-lived arrays in market stats.
- Fewer boxed `Double` allocations when core indicators are not needed.
- Less no-op recorder and bid-up counter work in minimal mode.

### Candidate Implementation Shape

Recommended first slices:
- Preallocate per-quality counter arrays and reset them with `Arrays.fill()`.
- Remove `bidPrices` and `offerPrices` if compile/search confirms no real consumers, or make them lazy diagnostic fields.
- Reuse `nBidUpFrequency`, and only allocate/increment it when `recordNBidUpFrequency=true`.
- Gate disabled transaction-recorder calls at hot call sites only when doing so preserves output behavior.

Potential larger slices:
- Add an explicit "core indicators needed" switch for `CreditSupply` rolling LTV/LTI buffers.
- If core indicators remain needed, replace boxed `ArrayList<Double>` storage with primitive rolling buffers while preserving
  median/mean-above-median semantics exactly.
- Replace `PrintWriter.format(Locale.ROOT, ...)` with append-style writers only after higher-priority collector changes,
  because exact output formatting is fragile.

Avoid:
- Removing `Output-run*.csv` from core-minimal mode without an explicit benchmark-policy change. It might be useful, but it
  intentionally changes the speed-mode output file set and would require docs/baseline updates.

### Expected Impact

Estimated 20k speedup:
- Array reuse and unused bid/offer price removal: `1-3%`.
- Disabled bid-up/transaction gating: `0.5-1.5%`.
- Core-indicator LTV/LTI gating in minimal mode: usually `<1%`, more in full-output or core-indicator-heavy runs.
- Combined: `1.5-4%`.

Likelihood: High for array/counter cleanup.

### Model Risk

Risk: Low for allocation cleanup, medium for public getter removal or core-indicator gating.

Main risks:
- Hidden package-level consumers of bid/offer arrays.
- Output differences if averages are accidentally computed from changed sums.
- Future policy code consuming core indicators even when not recorded.
- Formatting differences if recorder output is rewritten.

### Required Tests And Benchmarks

Focused tests:
- Market stats averages and count outputs before/after.
- `recordNBidUpFrequency=true` smoke test.
- Core-indicator mean/median tests if LTV/LTI collection changes.
- Recorder compatibility tests if formatting changes.

Acceptance checks:
- `mvn -q test`
- three-run exact `v0 / e2e-default-5k-s1`
- 10-run `v0 / core-minimal-20k-s1`
- Optional allocation/JFR profile to confirm lower allocation pressure.

## Reviewed But Lower Priority

### Incremental Credit-Stock Totals

Scope:
- `src/main/java/collectors/CreditSupply.java`
- `src/main/java/housing/MortgageAgreement.java`
- `src/main/java/housing/Bank.java`

Current `CreditSupply.postClearingRecord()` scans all active mortgages every month to compute OO and BTL credit stock.
Incremental totals could update on loan creation, scheduled principal payment, payoff, and mortgage removal.

Estimated speedup: `0.5-2%`, likely larger at bigger populations.

Reason lower priority:
- Mortgage lifecycle state is spread across loan issue, monthly payment, payoff, sale, inheritance, and residual debt.
- A missed update silently corrupts credit-stock outputs and core indicators.

Use only after higher-yield collector and household changes, or implement with debug assertions that periodically compare
incremental totals to a full recount.

### Output Formatting Rewrite

Scope:
- `src/main/java/collectors/Recorder.java`
- `src/main/java/collectors/MicroDataRecorder.java`
- `src/main/java/collectors/TransactionRecorder.java`

`PrintWriter.format(Locale.ROOT, ...)` is allocation-heavy. A `StringBuilder` or append-style writer could improve
full-output runs.

Estimated speedup:
- `<1%` on `core-minimal-20k-s1`.
- Possibly `2-5%` on full-output/e2e-style runs.

Reason lower priority:
- Exact output hashes are formatting-sensitive.
- The current headline speed gate is minimal-output and writes much less data than e2e.

### Rental-Market Offer Yield Calculation

Scope:
- `src/main/java/housing/HouseOfferRecord.java`
- `src/main/java/housing/HouseRentalMarket.java`
- `src/main/java/housing/HouseSaleMarket.java`

Rental-market offers currently create `HouseOfferRecord` objects that compute `houseSpecificYield`, but rental matching uses
price-quality, not price-yield. Sale-market BTL offers do need yield.

Estimated speedup: usually `<1%`, maybe more in rental-heavy months.

Reason lower priority:
- Small isolated impact.
- Requires careful separation so BTL sale-market ordering is not touched.

### Tax Band Primitive Arrays

Scope:
- `src/main/java/housing/Government.java`
- `src/main/java/data/Government.java`

Tax and national-insurance bands are boxed `Double[]`. Primitive `double[]` arrays could reduce repeated tax-call overhead.

Estimated speedup: below the current 20k detection threshold alone.

Reason lower priority:
- Useful only as part of a broader income/finance-cost cleanup.

## Changes To Avoid

Do not pursue the following under the current exact-regression speed track:
- Changing `Model` from `t <= N_STEPS` to `t < N_STEPS`. That speeds up by simulating fewer months and changes output.
- Swapping RNG engines.
- Approximating Gaussian draws.
- Replacing exact `Math.exp`/`Math.pow` semantics with approximations.
- Lowering `Pdf.DEFAULT_CDF_SAMPLES`.
- Approximate price bucketing in market queues.
- Intra-run parallelism before the project has an explicitly approved tolerance-based correctness track.

These changes are likely to regress model behavior or fail the exact output contract.

## Recommended Order Of Work

1. Refresh JFR against `v0 / core-minimal-20k-s1` to verify the current hotspot order.
2. If current profiling confirms the ranking, implement a small, exact-preserving `HouseholdStats.record()` one-pass/minimal-mode cleanup.
3. Implement low-risk market-stats allocation cleanup: array reuse and unused bid/offer price removal or lazy materialisation.
4. Implement conservative `getAnnualFinanceCosts()` local cleanup and landlord-side rental-contract lookup.
5. Refresh JFR after accepted collector and finance-cost changes to verify the new hotspot order.
6. Choose between:
   - a dirty finance-cost cache, if the local cleanup still leaves finance costs hot, or
   - matched-offer-only market clearing, if market queue work becomes dominant.
7. Defer full `PriorityQueue2D` replacement until enough equivalence tests exist to make exact regression failure unlikely.

## Acceptance Checklist For Any Candidate

Every accepted speed change should include:
- Narrow implementation scope: one hotspot family per change.
- Unit or regression tests targeted to the touched behavior.
- `mvn -q -DskipTests compile`
- `mvn -q test`
- Three-run exact `v0 / e2e-default-5k-s1` gate.
- 10-run `v0 / core-minimal-20k-s1` benchmark.
- Candidate-minus-baseline 95% CI for `wall_clock_seconds`.
- Supporting `seconds_per_household_month`, RSS, GC, and output-volume deltas.
- Fresh `docs/model-speed/CHANGELOG.md` entry if the change is accepted.
- Raw outputs under `tmp/model-speed/`, not `Results/` and not baseline directories.

No item above should be described as an accepted speedup until the exact gate passes and the 20k benchmark verdict is
statistically faster under the current policy.
