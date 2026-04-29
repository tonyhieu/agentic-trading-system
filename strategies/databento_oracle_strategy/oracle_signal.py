"""Custom Nautilus data type carrying a pre-shifted "future" price.

The signal is stamped at time T but carries the price observed at T + horizon
(plus optional Gaussian noise). The shift is performed offline in
``preprocessing.build_oracle_signals``, so the engine still sees a normally
ordered stream by ``ts_init`` and ``OracleStrategy`` consumes the future price
through ``on_data`` without any runtime look-ahead.

The current price at T is embedded alongside the future price so the strategy's
decision is fully self-contained and independent of cache state at the moment
the signal is dispatched (ticks and signals at the same ``ts_init`` arrive in
an order the engine controls; carrying both prices removes that ambiguity).
"""
from __future__ import annotations

from nautilus_trader.core.data import Data
from nautilus_trader.model.identifiers import InstrumentId


class OracleSignal(Data):
    def __init__(
        self,
        instrument_id: InstrumentId,
        current_price: float,
        future_price: float,
        ts_event: int,
        ts_init: int,
    ) -> None:
        self.instrument_id = instrument_id
        self.current_price = current_price
        self.future_price = future_price
        self._ts_event = ts_event
        self._ts_init = ts_init

    @property
    def ts_event(self) -> int:
        return self._ts_event

    @property
    def ts_init(self) -> int:
        return self._ts_init

    def __repr__(self) -> str:
        return (
            f"OracleSignal(instrument_id={self.instrument_id}, "
            f"current={self.current_price:.4f}, "
            f"future={self.future_price:.4f}, "
            f"ts_init={self._ts_init})"
        )
