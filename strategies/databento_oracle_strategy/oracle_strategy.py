"""Oracle trading strategy.

Consumes pre-shifted ``OracleSignal`` custom data and trades the comparison
between the embedded current price and the (noisy) future price. Designed as a
research harness: holds signal quality constant (via the noise sigma chosen at
preprocessing time) so the variable under study is the execution algorithm.
"""
from __future__ import annotations

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.model import DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy

from strategies.databento_oracle_strategy.oracle_signal import OracleSignal


class OracleStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    trade_size: Decimal
    entry_threshold: float = 0.5
    exec_algorithm_id: ExecAlgorithmId | None = None
    close_positions_on_stop: bool = True


class OracleStrategy(Strategy):
    """Long when the future price beats current by ``entry_threshold``, short on the inverse."""

    def __init__(self, config: OracleStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument not found: {self.config.instrument_id}")
            self.stop()
            return

        # Custom data is delivered to ``on_data`` only after subscribing — even
        # for items injected via ``BacktestEngine.add_data``. The topic
        # published by the data engine includes the instrument_id, so the
        # subscription must match (otherwise no delivery).
        self.subscribe_data(
            DataType(OracleSignal),
            instrument_id=self.config.instrument_id,
        )

        self.log.info(
            f"OracleStrategy started | threshold={self.config.entry_threshold}",
            color=LogColor.GREEN,
        )

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop:
            self._close_all_positions()
        self.unsubscribe_data(
            DataType(OracleSignal),
            instrument_id=self.config.instrument_id,
        )
        self.log.info("OracleStrategy stopped.", color=LogColor.RED)

    def on_reset(self) -> None:
        pass

    def on_data(self, data: Data) -> None:
        if not isinstance(data, OracleSignal):
            return
        if data.instrument_id != self.config.instrument_id:
            return

        edge = data.future_price - data.current_price

        if edge > self.config.entry_threshold:
            if self.portfolio.is_flat(self.config.instrument_id):
                self._buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self._close_all_positions()
                self._buy()
        elif edge < -self.config.entry_threshold:
            if self.portfolio.is_flat(self.config.instrument_id):
                self._sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self._close_all_positions()
                self._sell()

    def _buy(self) -> None:
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self._make_qty(),
            time_in_force=TimeInForce.GTC,
            exec_algorithm_id=self.config.exec_algorithm_id,
        )
        self.log.info(
            f"BUY {order.quantity} {self.config.instrument_id}",
            color=LogColor.GREEN,
        )
        self.submit_order(order)

    def _sell(self) -> None:
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self._make_qty(),
            time_in_force=TimeInForce.GTC,
            exec_algorithm_id=self.config.exec_algorithm_id,
        )
        self.log.info(
            f"SELL {order.quantity} {self.config.instrument_id}",
            color=LogColor.RED,
        )
        self.submit_order(order)

    def _close_all_positions(self) -> None:
        positions_open = self.cache.positions_open(
            venue=None,
            instrument_id=self.config.instrument_id,
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
            self.log.info(
                f"CLOSE {order.quantity} {position.instrument_id}",
                color=LogColor.YELLOW,
            )
            self.submit_order(order, position_id=position.id)

    def _make_qty(self) -> Quantity:
        return self.instrument.make_qty(self.config.trade_size)


def get_trading_strategy(
    instrument_id: InstrumentId,
    trade_size: Decimal = Decimal("1"),
    entry_threshold: float = 0.5,
    exec_algorithm_id: str | None = "MY_GENERIC_ALGO",
) -> OracleStrategy:
    """Build an OracleStrategy for the given instrument."""
    config = OracleStrategyConfig(
        instrument_id=instrument_id,
        trade_size=trade_size,
        entry_threshold=entry_threshold,
        exec_algorithm_id=ExecAlgorithmId(exec_algorithm_id) if exec_algorithm_id else None,
    )
    return OracleStrategy(config=config)
