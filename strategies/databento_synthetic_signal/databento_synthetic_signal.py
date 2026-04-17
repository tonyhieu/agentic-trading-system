"""Synthetic-signal Databento strategy for execution algorithm testing."""

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.model.data import DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy


class SyntheticDatabentoSignal(Data):
    """A simple synthetic signal payload for Databento replay tests."""

    def __init__(
        self,
        instrument_id: InstrumentId,
        value: float,
        ts_event: int,
        ts_init: int,
    ) -> None:
        self.instrument_id = instrument_id
        self.value = value
        self._ts_event = ts_event
        self._ts_init = ts_init

    @property
    def ts_event(self) -> int:
        return self._ts_event

    @property
    def ts_init(self) -> int:
        return self._ts_init


class DatabentoSyntheticSignalStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for synthetic-signal Databento strategy instances."""

    instrument_id: InstrumentId
    trade_size: Decimal = Decimal("1")
    signal_limit: PositiveInt = 50
    signal_threshold: float = 0.0
    exec_algorithm_id: ExecAlgorithmId | None = None
    close_positions_on_stop: bool = True


class DatabentoSyntheticSignalStrategy(Strategy):
    """Submit market orders based on synthetic custom data signal values."""

    def __init__(self, config: DatabentoSyntheticSignalStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._signal_count = 0

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument not found: {self.config.instrument_id}")
            self.stop()
            return

        self.subscribe_data(
            data_type=DataType(SyntheticDatabentoSignal),
            instrument_id=self.config.instrument_id,
        )
        self.log.info(
            f"DatabentoSyntheticSignalStrategy started | instrument={self.config.instrument_id} | "
            f"signal_limit={self.config.signal_limit} | threshold={self.config.signal_threshold}",
            color=LogColor.GREEN,
        )

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop:
            self.close_all_positions_via_exec_algorithm(self.config.instrument_id)

        self.unsubscribe_data(
            data_type=DataType(SyntheticDatabentoSignal),
            instrument_id=self.config.instrument_id,
        )
        self.log.info("DatabentoSyntheticSignalStrategy stopped.", color=LogColor.RED)

    def on_reset(self) -> None:
        self._signal_count = 0

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

    def on_data(self, data: Data) -> None:
        if not isinstance(data, SyntheticDatabentoSignal):
            return
        if data.instrument_id != self.config.instrument_id:
            return
        if self._signal_count >= self.config.signal_limit:
            return
        if abs(data.value) <= self.config.signal_threshold:
            return
        if self.instrument is None:
            return

        side = OrderSide.BUY if data.value > 0 else OrderSide.SELL
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=self.instrument.make_qty(self.config.trade_size),
            time_in_force=TimeInForce.GTC,
            exec_algorithm_id=self.config.exec_algorithm_id,
        )
        self.log.info(
            f"SYNTHETIC SIGNAL value={data.value:.6f} -> {side.value} {order.quantity} "
            f"{self.config.instrument_id} [{self._signal_count + 1}/{self.config.signal_limit}]",
            color=LogColor.MAGENTA if side == OrderSide.BUY else LogColor.CYAN,
        )
        self.submit_order(order)
        self._signal_count += 1

    def on_event(self, event: Event) -> None:
        pass

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
    signal_threshold: float = 0.0,
    exec_algorithm_id: str | None = "DATABENTO_GENERIC_ALGO",
    close_positions_on_stop: bool = True,
) -> DatabentoSyntheticSignalStrategy:
    """Build and return a DatabentoSyntheticSignalStrategy instance."""
    parsed_instrument_id = (
        instrument_id if isinstance(instrument_id, InstrumentId) else InstrumentId.from_str(instrument_id)
    )

    config = DatabentoSyntheticSignalStrategyConfig(
        instrument_id=parsed_instrument_id,
        trade_size=trade_size,
        signal_limit=signal_limit,
        signal_threshold=signal_threshold,
        exec_algorithm_id=ExecAlgorithmId(exec_algorithm_id) if exec_algorithm_id else None,
        close_positions_on_stop=close_positions_on_stop,
    )
    return DatabentoSyntheticSignalStrategy(config=config)