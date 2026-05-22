from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SimpleExecutionAlgorithmConfig(ExecAlgorithmConfig, frozen=True):
    """Baseline config.

    `horizon_seconds` must match the oracle strategy's forecast horizon — it is
    wired from `config.yaml -> strategy.kwargs.horizon_seconds` by run_backtest().
    """

    horizon_seconds: float = 30.0


class SimpleExecutionAlgorithm(ExecAlgorithm):
    """Horizon-hold baseline execution algorithm.

    Holds each position for `horizon_seconds`, skipping the strategy's intermediate
    reversal orders, then resumes following the oracle at the first flip after the
    horizon elapses.

    The oracle strategy is always-in-market: it emits a reduce-only close plus a new
    open on every signal direction change. A pure pass-through therefore pays a full
    bid-ask spread on every flip. When the oracle is noisy (high sigma) it flips
    roughly every signal interval, so the pass-through bleeds the spread on a
    near-coin-flip ~once per second.

    This algorithm forwards an opening order, then skips every subsequent order until
    `horizon_seconds` has elapsed since entry; the first flip after that point exits
    the position (close forwarded) and re-enters on the current oracle direction
    (paired open forwarded). Round-trips — and spread cost — drop by roughly
    horizon / flip-interval, and each holding window matches the oracle's forecast
    horizon, so a trade realizes the quantity the oracle actually forecast.

    Uses only `submit_order` (forward) and skipping (return without submitting) — it
    never originates or inflates an order, so `sum(child_fills) <= parent.quantity`
    holds trivially.
    """

    def __init__(self, config: SimpleExecutionAlgorithmConfig) -> None:
        super().__init__(config=config)
        self._horizon_ns: int = int(config.horizon_seconds * 1_000_000_000)
        self._holding: bool = False
        self._entry_ts: int = 0

    def on_start(self) -> None:
        self.log.info(
            f"SimpleExecutionAlgorithm started (horizon={self._horizon_ns / 1e9:.1f}s)."
        )

    def on_reset(self) -> None:
        self._holding = False
        self._entry_ts = 0

    def on_order(self, order) -> None:
        """Forward or skip the incoming order to enforce a `horizon_seconds` hold."""
        now = order.ts_init

        if not getattr(order, "is_reduce_only", False):
            # OPEN leg.
            if self._holding:
                return  # Mid-hold: ignore the intermediate entry.
            self.submit_order(order)
            self._holding = True
            self._entry_ts = now
            return

        # CLOSE leg (reduce-only).
        if not self._holding:
            return  # No position to close.
        if now - self._entry_ts >= self._horizon_ns:
            # Horizon elapsed — let this flip's close exit the position. The paired
            # open that follows re-enters on the current oracle direction.
            self.submit_order(order)
            self._holding = False
        # else: mid-hold — ignore the reversal close.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    horizon_seconds: float = 30.0,
) -> SimpleExecutionAlgorithm:
    """Instantiate and return the horizon-hold baseline execution algorithm."""
    config = SimpleExecutionAlgorithmConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        horizon_seconds=horizon_seconds,
    )
    return SimpleExecutionAlgorithm(config=config)
