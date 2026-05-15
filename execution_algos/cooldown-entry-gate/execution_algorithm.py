"""Cooldown-entry-gate execution algorithm.

After any executed open-leg order, imposes a fixed cooldown period during which
all subsequent open-leg orders are skipped. Closes always execute immediately.

Rationale:
  The oracle strategy fires signals at 1-second intervals. When multiple signals
  fire in rapid succession, the later opens are likely correlated with the same
  underlying price movement already captured by the first entry. Executing all
  of them increases position risk with no new directional information. A short
  cooldown (default 3s) spaces entries by at least 3 signal intervals, concentrating
  execution on the freshest, most independent signal in each epoch.

Algorithm:
  - Track the timestamp (ns) of the most recently EXECUTED open order.
  - At each new open-leg order: if (order.ts_init - last_entry_ts) < cooldown_ns,
    SKIP (do not call submit_order). Otherwise, submit and record the timestamp.
  - Reduce-only (close) orders always execute immediately — intraday_flat compliance.
  - The cooldown timer is set only by actual fill submissions, NOT by skips. A
    skipped open does not extend the cooldown.
  - No quantity modification — quantity invariant always preserved.

No look-ahead bias: only uses order.ts_init and the timestamp of the last
submitted open, both strictly in the past at decision time.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class CooldownEntryGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the cooldown-entry-gate execution algorithm.

    Parameters
    ----------
    cooldown_seconds : float
        Minimum time in seconds that must elapse since the last executed
        open-leg before the next open is eligible.
        Default 3.0 seconds = 3 oracle signal intervals at 1s cadence.
    """

    cooldown_seconds: float = 3.0


class CooldownEntryGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that imposes a cooldown between open-leg entries.

    Opening orders (is_reduce_only == False):
      - If cooldown has not expired since the last executed open, SKIP.
      - If cooldown has expired (or no prior open executed this session), SUBMIT.
      - Record the submitted timestamp as _last_entry_ts_ns.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
      - Do NOT reset the cooldown timer.

    Order quantity is never modified — quantity invariant preserved.
    """

    def __init__(self, config: CooldownEntryGateConfig) -> None:
        super().__init__(config=config)
        self._cooldown_ns: int = int(config.cooldown_seconds * 1_000_000_000)
        self._last_entry_ts_ns: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"CooldownEntryGateAlgorithm started "
            f"(cooldown={self._cooldown_ns / 1e9:.1f}s)."
        )

    def on_reset(self) -> None:
        self._last_entry_ts_ns = None

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on time since last open."""

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # First open of the session (no prior entry) — always submit.
        if self._last_entry_ts_ns is None:
            self.log.debug(
                f"First open {order.client_order_id}; submitting unconditionally."
            )
            self._last_entry_ts_ns = order.ts_init
            self.submit_order(order)
            return

        # Check whether cooldown has expired.
        elapsed_ns = order.ts_init - self._last_entry_ts_ns
        if elapsed_ns < self._cooldown_ns:
            elapsed_s = elapsed_ns / 1_000_000_000
            self.log.debug(
                f"SKIP {order.client_order_id} — cooldown active "
                f"(elapsed={elapsed_s:.3f}s < "
                f"cooldown={self._cooldown_ns / 1e9:.1f}s)."
            )
            # Do NOT call submit_order — quantity invariant preserved.
            # Do NOT update _last_entry_ts_ns — timer stays at last actual submit.
            return

        # Cooldown has expired — submit and record timestamp.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — cooldown expired "
            f"(elapsed={elapsed_ns / 1e9:.3f}s)."
        )
        self._last_entry_ts_ns = order.ts_init
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    cooldown_seconds: float = 3.0,
) -> CooldownEntryGateAlgorithm:
    """Instantiate and return the CooldownEntryGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    cooldown_seconds : float
        Minimum seconds between consecutive executed open-leg orders.
        Default 3.0s (3 oracle signal intervals at 1s cadence).
    """
    config = CooldownEntryGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        cooldown_seconds=cooldown_seconds,
    )
    return CooldownEntryGateAlgorithm(config=config)
