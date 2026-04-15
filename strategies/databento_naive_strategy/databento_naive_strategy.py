"""Naive Databento trading strategy used to smoke-test the backtester."""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy


class DatabentoNaiveStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for ``DatabentoNaiveStrategy`` instances."""

    instrument_id: InstrumentId
    trade_size: Decimal = Decimal("1")
    signal_limit: PositiveInt = 50
    exec_algorithm_id: ExecAlgorithmId | None = None
    close_positions_on_stop: bool = True


class DatabentoNaiveStrategy(Strategy):
    """A deterministic tick-driven strategy for backtester smoke tests."""

    def __init__(self, config: DatabentoNaiveStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._signal_count = 0
        self._next_side = OrderSide.BUY

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument not found: {self.config.instrument_id}")
            self.stop()
            return

        self.subscribe_quote_ticks(self.config.instrument_id)
        self.log.info(
            f"DatabentoNaiveStrategy started | instrument={self.config.instrument_id} | "
            f"signal_limit={self.config.signal_limit}",
            color=LogColor.GREEN,
        )

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop:
            self.close_all_positions_via_exec_algorithm(self.config.instrument_id)

        self.unsubscribe_quote_ticks(self.config.instrument_id)
        self.log.info("DatabentoNaiveStrategy stopped.", color=LogColor.RED)

    def on_reset(self) -> None:
        self._signal_count = 0
        self._next_side = OrderSide.BUY

    def on_dispose(self) -> None:
        pass

    def on_save(self) -> dict[str, bytes]:
        return {
            "signal_count": str(self._signal_count).encode(),
        }

    def on_load(self, state: dict[str, bytes]) -> None:
        signal_count = state.get("signal_count")

        if signal_count is not None:
            self._signal_count = int(signal_count.decode())

        # Preserve deterministic alternation after restore.
        self._next_side = OrderSide.BUY if self._signal_count % 2 == 0 else OrderSide.SELL

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if tick.instrument_id != self.config.instrument_id:
            return

        self._emit_signal()

    def on_trade_tick(self, tick: TradeTick) -> None:
        pass

    def on_data(self, data: Data) -> None:
        pass

    def on_event(self, event: Event) -> None:
        pass

    def _emit_signal(self) -> None:
        if self._signal_count >= self.config.signal_limit:
            return

        if self.instrument is None:
            self.log.warning("Instrument is not ready yet; skipping signal.")
            return

        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=self._next_side,
            quantity=self._make_qty(),
            time_in_force=TimeInForce.GTC,
            exec_algorithm_id=self.config.exec_algorithm_id,
        )
        self.log.info(
            f"SIGNAL {self._next_side.value} {order.quantity} {self.config.instrument_id} "
            f"[{self._signal_count + 1}/{self.config.signal_limit}]",
            color=LogColor.MAGENTA if self._next_side == OrderSide.BUY else LogColor.CYAN,
        )
        self.submit_order(order)

        self._signal_count += 1
        self._next_side = OrderSide.SELL if self._next_side == OrderSide.BUY else OrderSide.BUY

    def _make_qty(self) -> Quantity:
        if self.instrument is None:
            raise RuntimeError("Instrument is not available for quantity conversion.")
        return self.instrument.make_qty(self.config.trade_size)

    def close_all_positions_via_exec_algorithm(self, instrument_id: InstrumentId) -> None:
        """Close open positions while preserving execution algorithm routing."""
        positions_open = self.cache.positions_open(
            venue=None,
            instrument_id=instrument_id,
            strategy_id=self.id,
            side=PositionSide.NO_POSITION_SIDE,
        )

        if not positions_open:
            return

        for position in positions_open:
            order: MarketOrder = self.order_factory.market(
                instrument_id=position.instrument_id,
                order_side=position.closing_order_side(),
                quantity=position.quantity,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
                exec_algorithm_id=self.config.exec_algorithm_id,
            )
            self.submit_order(order, position_id=position.id)


def get_trading_strategy(
    instrument_id: str | InstrumentId,
    trade_size: Decimal = Decimal("1"),
    signal_limit: int = 50,
    exec_algorithm_id: str | None = "DATABENTO_GENERIC_ALGO",
    close_positions_on_stop: bool = True,
) -> DatabentoNaiveStrategy:
    """Build and return a ``DatabentoNaiveStrategy`` instance."""
    parsed_instrument_id = (
        instrument_id if isinstance(instrument_id, InstrumentId) else InstrumentId.from_str(instrument_id)
    )

    config = DatabentoNaiveStrategyConfig(
        instrument_id=parsed_instrument_id,
        trade_size=trade_size,
        signal_limit=signal_limit,
        exec_algorithm_id=ExecAlgorithmId(exec_algorithm_id) if exec_algorithm_id else None,
        close_positions_on_stop=close_positions_on_stop,
    )
    return DatabentoNaiveStrategy(config=config)