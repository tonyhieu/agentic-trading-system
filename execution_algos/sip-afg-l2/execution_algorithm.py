"""sip-afg-l2 — side-asymmetric aggressor-flow gate.

A loop-2 variant of `aggressor-flow-gate` for the
self_improving_prompt_experiment. Hypothesis (see NOTES.md):

  The base algo's symmetric SELL gate is empirically inverted in the
  training window. Pooled across 4 train dates (n=266,063 SELL-skip
  evaluations), the mean 30s-ahead drift when net_flow >= +2 is -0.144
  ticks (t = -41.46) — i.e. the would-be SELL order would have been
  profitable on average. The base algo throws away P&L on every SELL
  skip.

Mechanism (one concrete change vs base):
  - Keep the 10s rolling deque of signed aggressor volume (+size BUYER,
    -size SELLER, 0 NO_AGGRESSOR).
  - For BUY orders: skip when net_flow <= -flow_threshold_buy (= 2.0,
    identical to base). Mean BUY-skip value = +0.0931 ticks (t = +25.13)
    on the same pooled train EDA — the BUY gate is correctly signed.
  - For SELL orders: never skip (effectively flow_threshold_sell = +inf).
  - Reduce-only orders always submit (intraday_flat compliance).
  - Anti-cascade `_position_flat = True` is set only after a BUY skip
    (the only side that can gate), so the next open is unconditional.

No look-ahead bias: identical deque mechanics to the base algo. No
quantity modification — the participation_cap and top_of_book_only
constraints are inherited from the base order routing.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL2Config(ExecAlgorithmConfig, frozen=True):
    """Config for sip-afg-l2.

    Parameters
    ----------
    window_seconds : float
        Rolling lookback for aggressor-volume flow. Default 10.0s
        (identical to base `aggressor-flow-gate`).
    flow_threshold_buy : float
        Minimum |net_flow| (contracts) to gate a BUY open order when
        net_flow <= -flow_threshold_buy. Default 2.0 (identical to
        base's symmetric `flow_threshold`).
    """

    window_seconds: float = 10.0
    flow_threshold_buy: float = 2.0


class SipAfgL2Algorithm(ExecAlgorithm):
    """Side-asymmetric aggressor-flow gate.

    BUY gating: identical to `aggressor-flow-gate` (skip when net_flow
    <= -flow_threshold_buy over the rolling window).

    SELL gating: disabled. SELL open orders are always submitted.

    Reduce-only / close orders always submit.
    """

    def __init__(self, config: SipAfgL2Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold_buy: float = config.flow_threshold_buy

        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        self._position_flat: bool = True
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL2Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold_buy={self._flow_threshold_buy:.1f} contracts, "
            f"SELL gate DISABLED)."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._position_flat = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade-tick handler — maintain signed aggressor-volume deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        aggressor = tick.aggressor_side
        size = float(str(tick.size))
        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            signed_vol = 0.0
        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Gate evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _buy_flow_is_adverse(self, order) -> bool:
        """Return True if net aggressor flow is adverse for this BUY order.

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up)
          - net_flow > -flow_threshold_buy (neutral or favorable)
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            return False

        if self._net_flow <= -self._flow_threshold_buy:
            self.log.debug(
                f"BUY adverse flow: net_flow={self._net_flow:.2f} <= "
                f"-threshold={-self._flow_threshold_buy:.2f}; SKIP."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only / close orders always execute (intraday_flat).
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — anti-cascade guarantee.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # SELL orders: gate disabled — always submit.
        if order.side == OrderSide.SELL:
            self.log.debug(
                f"SUBMIT SELL {order.client_order_id} — SELL gate disabled "
                f"(net_flow={self._net_flow:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # BUY orders: evaluate adverse-flow gate.
        if self._buy_flow_is_adverse(order):
            self.log.info(
                f"SKIP BUY {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT BUY {order.client_order_id} — flow neutral/favorable "
                f"(net_flow={self._net_flow:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold_buy: float = 2.0,
) -> SipAfgL2Algorithm:
    """Instantiate the sip-afg-l2 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s (identical to `aggressor-flow-gate`).
    flow_threshold_buy : float
        Minimum |net_flow| (contracts) for the BUY-side gate. Default
        2.0 (identical to `aggressor-flow-gate`'s symmetric
        `flow_threshold`). The SELL-side gate is hard-disabled.
    """
    config = SipAfgL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold_buy=flow_threshold_buy,
    )
    return SipAfgL2Algorithm(config=config)
