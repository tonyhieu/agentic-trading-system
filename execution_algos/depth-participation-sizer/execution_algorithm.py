"""Adaptive participation-sizer conditioned on top-of-book depth.

Core idea: scale open-leg order submission probability as a continuous
function of the current same-side top-of-book quantity at the moment the
signal fires:

    p_submit = clip(min_prob, 1.0, (q_same_side / depth_scale) ** alpha)

where:
  - q_same_side = ask_size for BUY orders (supply absorbing our buy)
                  bid_size for SELL orders (demand absorbing our sell)
  - depth_scale  = the quantity threshold at which p approaches 1.0
  - alpha        = elasticity (0 < alpha <= 1; alpha<1 = concave/saturating)
  - min_prob     = probability floor (no signal is permanently locked out)

In calm, deep-book moments (q_same_side >= depth_scale), p = 1.0 and every
signal executes. In thin-book moments, p falls proportionally, reducing
participation to preserve expected fill quality. The key differentiator from
all prior algorithms: this conditions solely on *absolute* same-side depth
magnitude — the raw liquidity available to fill our order at top of book.

Reduce-only (position-closing) orders always execute unconditionally at full
quantity — intraday_flat compliance.

Quantity invariant: child_qty = parent_qty for every submitted order.
The participation probability is realized as probabilistic skip/submit of
1-contract orders, not partial-quantity fragmentation.

This algorithm is distinct from:
  - ob-imbalance-gate / microprice-divergence-gate: those use the bid/ask
    SIZE RATIO (relative imbalance), not the absolute depth on one side.
  - vol-regime-sizer: conditions on mid-price volatility ratio, not depth.
  - streak-spread-tight: conditions on loss streak + bid/ask spread.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class DepthParticipationSizerConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the depth-adaptive participation sizer.

    Parameters
    ----------
    depth_scale : float
        Same-side top-of-book quantity at which submission probability
        reaches 1.0. For quantities >= depth_scale, p=1.0. Default 10.
    alpha : float
        Elasticity of the depth-to-probability mapping.
        p = (q / depth_scale) ** alpha
        alpha=1.0: linear (thin book = proportionally lower p)
        alpha<1.0: concave (small depth still gets decent p; diminishing
                   return from extra depth)
        alpha>1.0: convex (requires substantial depth before p rises)
        Default 0.5 (concave, saturates at moderate depth levels).
    min_prob : float
        Floor on submission probability. Even with empty/thin book, at least
        this fraction of orders executes. Default 0.10.
    """

    depth_scale: float = 10.0
    alpha: float = 0.5
    min_prob: float = 0.10


class DepthParticipationSizerAlgorithm(ExecAlgorithm):
    """Execution algorithm that scales open-leg submission probability with same-side book depth.

    For each incoming OPEN (non-reduce-only) order:
      1. Fetch the current top-of-book quote from the cache.
      2. Extract same-side quantity:
           BUY  -> ask_size (counterparty supply at best ask)
           SELL -> bid_size (counterparty demand at best bid)
      3. Compute p = clip(min_prob, 1.0, (q / depth_scale) ** alpha).
      4. Accept/skip via a deterministic pseudo-random draw keyed on the
         order's client_order_id (reproducible, no shared randomness state).

    For reduce-only (CLOSE) orders: always submit unconditionally.

    Quantity invariant: child_qty = parent_qty = 1 for submitted orders.
    """

    def __init__(self, config: DepthParticipationSizerConfig) -> None:
        super().__init__(config=config)

        self._depth_scale: float = config.depth_scale
        self._alpha: float = config.alpha
        self._min_prob: float = config.min_prob

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"DepthParticipationSizerAlgorithm started "
            f"(depth_scale={self._depth_scale:.2f}, "
            f"alpha={self._alpha:.3f}, min_prob={self._min_prob:.3f})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Depth-to-probability mapping
    # ------------------------------------------------------------------

    def _compute_submit_prob(self, order, quote) -> float:
        """Compute submission probability from same-side top-of-book depth.

        Returns 1.0 (full participation) when no quote is available (safe
        fallback — do not penalize for missing data).
        """
        if quote is None:
            self.log.debug("No quote available; submitting at p=1.0 (safe fallback).")
            return 1.0

        try:
            # Same-side quantity: the counterparty liquidity available to fill us.
            if order.side == OrderSide.BUY:
                # Buying: we consume ask-side liquidity
                q_same = float(str(quote.ask_size))
            else:
                # Selling: we consume bid-side liquidity
                q_same = float(str(quote.bid_size))
        except Exception:
            return 1.0

        if q_same <= 0.0:
            return self._min_prob

        # p = (q / scale) ^ alpha, clipped to [min_prob, 1.0]
        ratio = q_same / self._depth_scale
        p = math.pow(ratio, self._alpha)
        p = max(self._min_prob, min(1.0, p))

        self.log.debug(
            f"q_same={q_same:.1f} depth_scale={self._depth_scale:.1f} "
            f"ratio={ratio:.4f} alpha={self._alpha:.3f} p={p:.4f}"
        )
        return p

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (from vol-regime-sizer pattern)
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        """Return a deterministic float in [0, 1) from the order's client ID.

        Uses SHA-256 of the string representation, takes the first 8 bytes
        as a uint64, and normalizes. Reproducible across runs given the same
        order_id sequence.
        """
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on same-side top-of-book depth."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        # Fetch current quote for depth computation.
        quote = self.cache.quote_tick(order.instrument_id)

        # Compute submission probability
        p = self._compute_submit_prob(order, quote)

        if p >= 1.0 - 1e-9:
            # Full participation (deep book or no quote)
            self._submitted += 1
            self.log.debug(f"SUBMIT {order.client_order_id} (p=1.0, deep/fallback).")
            self.submit_order(order)
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < p:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p={p:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            self._skipped += 1
            self.log.info(
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}). "
                f"submitted={self._submitted} skipped={self._skipped}."
            )
            # Do NOT call submit_order — quantity invariant preserved.

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (subscription side-effect)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    depth_scale: float = 10.0,
    alpha: float = 0.5,
    min_prob: float = 0.10,
) -> DepthParticipationSizerAlgorithm:
    """Instantiate and return the DepthParticipationSizerAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    depth_scale : float
        Same-side top-of-book quantity at which p -> 1.0. Default 10.
    alpha : float
        Elasticity of depth-to-probability mapping. Default 0.5 (concave).
    min_prob : float
        Floor on submission probability. Default 0.10.
    """
    config = DepthParticipationSizerConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        depth_scale=depth_scale,
        alpha=alpha,
        min_prob=min_prob,
    )
    return DepthParticipationSizerAlgorithm(config=config)
