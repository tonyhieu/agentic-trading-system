# Algorithm Notes: ptg-f-l5

Per-iteration experiment — base_algo `position-tier-gate`, context mode
`full-trace`, loop 5.

## Hypothesis

**Context from loops 1-4**:
- Loops 1-3: cap changes are binary, streak gate is no-op, flow gate hurts
- Loop 4: Short 5s flow gate (pending result — same pattern expected)

**Loop 5 hypothesis**: The base cap=1 blocks ALL concurrent opens regardless of
direction. But what if a COUNTER-DIRECTION concurrent open is actually beneficial?
If you're long and the oracle fires a SELL signal immediately, that SELL open would
be blocked by cap=1 (net_qty=1 >= 1). But a counter-direction entry effectively
hedges the existing position — it may be profitable in its own right AND reduce
overall exposure.

**Directional-aware position cap**: Only skip an open if it would ADD to the existing
position in the SAME direction. Allow opens in the OPPOSITE direction (which either
flatten or reverse the position).

**Mechanism**: Check existing position direction vs the new order side. If the new
order is in the SAME direction as existing position, skip. If OPPOSITE direction or no
existing position, submit.

**Expectation**: More trades than base (allows counter-direction entries), potentially
higher P&L if counter-direction oracle signals are profitable.

---

## Implementation Decisions

- Instead of position cap, check position DIRECTION vs order side.
- Reduce-only orders always submit (intraday_flat).
- No look-ahead: cache reflects pre-fill state.

---

## Backtest Observations

**Full 12-date train window:**
ptg-f-l5 (directional cap): pnl=$156.00, -96.34% vs base, trades=136,734 = SIMPLE.
Post-mortem: Oracle always reverses direction (CLOSE LONG + OPEN SHORT). The directional
gate always sees counter-direction new OPEN, so allows all unconditionally = simple.
**Hypothesis verdict**: FALSIFIED. Directional cap = simple because oracle always reverses.
**Suggested next**: Min reentry time (loop 6).
