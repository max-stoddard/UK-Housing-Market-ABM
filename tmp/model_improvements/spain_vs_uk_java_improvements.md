# Spain vs UK Java Improvements

### BTL Finance and Investor Behaviour (PORTED)
Implementation status:
- Baseline: the UK live runtime resources were aligned to `input-data-versions/v4.10` in the implementation worktree and the port was validated against that snapshot as the authoritative UK baseline.
- T6: `enableBTLAmortizingMortgageMode` is backfilled across the checked-in configs and defaults to `false`, so the legacy UK interest-only BTL finance path remains active unless explicitly enabled. When enabled, BTL sizing and financing drag switch to the amortising-payment interpretation without importing Spain-only soft LTV/LTI policy.
- T10: `enableBTLDownpaymentLognormal` is backfilled with `DOWNPAYMENT_BTL_SCALE` and `DOWNPAYMENT_BTL_SHAPE` placeholders in the checked-in configs and defaults to `false`, so the legacy BTL down-payment mean/epsilon path remains active unless explicitly enabled. The new log-normal parameters are TODO-calibrate placeholders and are not active in any checked-in snapshot.
- T11: `enableBTLAlternativeReturn` is backfilled with `BTL_ALTERNATIVE_RETURN = 0.0` placeholders in the checked-in configs and defaults to `false`, so the legacy BTL return path remains active unless explicitly enabled. When enabled, the alternative return is subtracted inside the real BTL buy/sell decision paths.
- Regression coverage: the JUnit suite now includes default-off legacy-path checks for BTL down-payment selection, BTL financing-yield inputs, `Bank.requestApproval(...)`, `Bank.getMaxMortgagePrice(...)`, exhaustive snapshot config loading, and a process-level `v4.10` tiny-run regression against the captured pre-port baseline.
