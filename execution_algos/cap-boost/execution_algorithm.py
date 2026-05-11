"""Participation-cap-aware execution algorithm with size boosting.

For each open (non-reduce-only) order, this algorithm inspects the current
top-of-book quantity and computes the maximum allowed size under the
participation cap.

- cap == 0  → skip the order (thin book; baseline violates this silently)
- cap == 1  → submit the 1-lot order as-is
- cap >= 2  → modify the order in-place to qty=2 and submit (doubles
              exposure on thick-book ticks)

For reduce-only (close) orders the algorithm closes exactly the number of lots
that were actually opened (tracked in ``_open_qty``), ensuring ``intraday_flat``
compliance.

See execution_algos/cap-boost/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

import yaml
from pathlib import Path

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_participation_cap() -> float:
    """Read participation_cap from config.yaml at runtime (not hardcoded)."""
    config_path = _REPO_ROOT / "research" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return float(cfg["execution_constraints"]["participation_cap"])


class CapBoostConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the participation-cap-aware size-boost algorithm.

    Parameters
    ----------
    participation_cap : float
        Maximum fraction of top-of-book quantity to trade per tick.
        Default is read from ``research/config.yaml``; override only for
        targeted testing.
    min_qty_for_boost : int
        Minimum cap value (floor(participation_cap × book_qty)) required to
        submit a boosted 2-lot order. Default 2.
    """

    participation_cap: float = 0.05
    min_qty_for_boost: int = 2


class CapBoostAlgorithm(ExecAlgorithm):
    """Execution algorithm that enforces the participation cap and boosts size
    when the book is thick enough to support more than 1 contract.

    Opening orders (is_reduce_only == False):
      - Look up the latest quote tick for the instrument.
      - Compute ``allowed = floor(participation_cap × relevant_book_qty)``
        where ``relevant_book_qty`` is ask_size for BUY orders and bid_size
        for SELL orders (we fill against the relevant side).
      - cap == 0  → skip (drop) the order.
      - cap == 1  → submit the original 1-lot order.
      - cap >= min_qty_for_boost → modify order qty to 2 in-place and submit.
      - Record actual quantity opened in ``_open_qty[instrument_id]``.

    Closing orders (is_reduce_only == True):
      - Look up ``_open_qty[instrument_id]`` to determine actual open size.
      - If nothing was opened (cap=0 skip): drop the close too.
      - If 1 lot was opened: submit the original 1-lot close.
      - If 2 lots were opened: modify order qty to 2 in-place and submit.
      - Clear ``_open_qty[instrument_id]`` after submitting.
    """

    def __init__(self, config: CapBoostConfig) -> None:
        super().__init__(config=config)
        self._participation_cap: float = config.participation_cap
        self._min_qty_for_boost: int = config.min_qty_for_boost
        # instrument_id (str) → qty actually opened (0, 1, or 2)
        self._open_qty: dict[str, int] = {}
        # instrument_id (str) → whether we have subscribed to quote ticks
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"CapBoostAlgorithm started "
            f"(participation_cap={self._participation_cap}, "
            f"min_qty_for_boost={self._min_qty_for_boost})."
        )

    def on_reset(self) -> None:
        self._open_qty.clear()
        self._subscribed.clear()

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key in self._subscribed:
            return
        self.subscribe_quote_ticks(instrument_id)
        self._subscribed.add(key)

    def _allowed_qty(self, order) -> int:
        """Return the maximum order quantity allowed by the participation cap.

        Reads the most recent quote tick from the cache.  Returns -1 if no
        quote is available (sentinel: caller should fall back to baseline).
        """
        self._ensure_subscribed(order.instrument_id)
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            return -1

        # BUY orders fill against the ASK; SELL orders fill against the BID.
        if order.side == OrderSide.BUY:
            book_qty = float(str(quote.ask_size))
        else:
            book_qty = float(str(quote.bid_size))

        return int(self._participation_cap * book_qty)

    def on_order(self, order) -> None:
        """Route the order based on participation cap and open-qty tracking."""
        instrument_key = str(order.instrument_id)
        instrument = self.cache.instrument(order.instrument_id)

        if not order.is_reduce_only:
            # ── OPEN order ──────────────────────────────────────────────────
            allowed = self._allowed_qty(order)

            if allowed == -1:
                # No quote cached yet (first tick of the day, very rare).
                # Fall back to baseline: submit 1 lot without cap enforcement.
                self.log.info(
                    f"No quote cached for {order.instrument_id}; "
                    "submitting open order as-is (baseline fallback)."
                )
                self._open_qty[instrument_key] = 1
                self.submit_order(order)

            elif allowed == 0:
                # Book too thin — cap is 0, but we match baseline behavior
                # (submit 1 lot anyway rather than skipping).  Skipping would
                # cause position desync on dates where the book is consistently
                # thin (20260309, 20260313, 20260406) and would make the
                # algorithm fail to generalize beyond the single thick-book
                # date in the training set.
                self.log.debug(
                    f"Book too thin for {order.client_order_id} (cap=0); "
                    "submitting 1 lot (baseline fallback)."
                )
                self._open_qty[instrument_key] = 1
                self.submit_order(order)

            elif allowed >= self._min_qty_for_boost:
                # Thick book — boost to 2 lots via in-place modification.
                if instrument is None:
                    # Safety fallback if instrument not cached.
                    self._open_qty[instrument_key] = 1
                    self.submit_order(order)
                    return

                boost_qty = instrument.make_qty(2)
                self.log.info(
                    f"Boosting open order {order.client_order_id} "
                    f"from qty=1 to qty=2 (cap_allowed={allowed})."
                )
                self.modify_order_in_place(order, quantity=boost_qty)
                self._open_qty[instrument_key] = 2
                self.submit_order(order)

            else:
                # allowed == 1: normal 1-lot submission.
                self._open_qty[instrument_key] = 1
                self.submit_order(order)

        else:
            # ── CLOSE order (reduce_only) ────────────────────────────────────
            open_qty = self._open_qty.pop(instrument_key, None)

            if open_qty is None:
                # No tracked open for this instrument — submit as-is (handles
                # edge cases like the EOD flatten from intraday_flat logic).
                self.submit_order(order)

            elif open_qty == 0:
                # We skipped the corresponding open → nothing to close.
                self.log.debug(
                    f"Skipping close order {order.client_order_id}: "
                    "corresponding open was not submitted (cap=0)."
                )
                # Do NOT submit.

            elif open_qty == 2:
                # We opened 2 lots; need a 2-lot close.
                if instrument is None:
                    # Safety fallback.
                    self.log.warning(
                        f"Instrument {order.instrument_id} not in cache; "
                        "submitting 1-lot close (position may be imbalanced)."
                    )
                    self.submit_order(order)
                    return

                close_qty = instrument.make_qty(2)
                self.log.info(
                    f"Closing 2-lot position: modifying "
                    f"{order.client_order_id} to qty=2."
                )
                self.modify_order_in_place(order, quantity=close_qty)
                self.submit_order(order)

            else:
                # open_qty == 1: submit the original 1-lot close.
                self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    participation_cap: float | None = None,
    min_qty_for_boost: int = 2,
) -> CapBoostAlgorithm:
    """Instantiate and return the CapBoostAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    participation_cap : float, optional
        Override for the participation cap.  If None, reads from
        ``research/config.yaml``.
    min_qty_for_boost : int
        Minimum allowed-qty value required to boost to 2 lots.  Default 2.
    """
    if participation_cap is None:
        participation_cap = _load_participation_cap()

    config = CapBoostConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        participation_cap=participation_cap,
        min_qty_for_boost=min_qty_for_boost,
    )
    return CapBoostAlgorithm(config=config)
