from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
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


# *** THIS IS A DEMONSTRATION STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY.         ***


class EMACrossStrategyConfig(StrategyConfig, frozen=True):
    """
    Configuration for ``EMACrossStrategy`` instances.

    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument ID for the strategy.
    bar_type : BarType
        The bar type used to drive EMA calculations.
    trade_size : Decimal
        The fixed quantity to trade on each signal.
    fast_ema_period : PositiveInt, default 10
        The number of bars for the fast EMA.
    slow_ema_period : PositiveInt, default 20
        The number of bars for the slow EMA.
    exec_algorithm_id : ExecAlgorithmId, optional
        The execution algorithm to route orders through.  When ``None``
        orders are sent directly to the venue without any intermediate
        algorithm.
    close_positions_on_stop : bool, default True
        Whether to close all open positions when the strategy stops.

    """

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    exec_algorithm_id: ExecAlgorithmId | None = None
    close_positions_on_stop: bool = True


class EMACrossStrategy(Strategy):
    """
    A simple EMA cross strategy built from the blank.py template.

    Entry logic
    -----------
    - **Long**  : fast EMA crosses *above* the slow EMA (or is already above and
                  the position is flat).
    - **Short** : fast EMA crosses *below* the slow EMA (or is already below and
                  the position is flat).

    Exit logic
    ----------
    - On each bar the opposing condition reverses the position by closing all
      existing positions before entering the new direction.

    Parameters
    ----------
    config : EMACrossStrategyConfig
        The configuration for the instance.

    Raises
    ------
    ValueError
        If ``config.fast_ema_period`` is not strictly less than
        ``config.slow_ema_period``.

    """

    def __init__(self, config: EMACrossStrategyConfig) -> None:
        if config.fast_ema_period >= config.slow_ema_period:
            raise ValueError(
                f"fast_ema_period ({config.fast_ema_period}) must be less than "
                f"slow_ema_period ({config.slow_ema_period})"
            )
        super().__init__(config)

        # The resolved instrument object (populated on start)
        self.instrument: Instrument | None = None

        # EMA indicators – values are updated automatically once registered
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """
        Actions to be performed when the strategy is started.
        """
        # Resolve the instrument from the cache
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument not found: {self.config.instrument_id}")
            self.stop()
            return

        # Wire the indicators to the chosen bar type so they update automatically
        self.register_indicator_for_bars(self.config.bar_type, self.fast_ema)
        self.register_indicator_for_bars(self.config.bar_type, self.slow_ema)

        # Subscribe to live bar updates
        self.subscribe_bars(self.config.bar_type)

        self.log.info(
            f"EMACrossStrategy started | "
            f"fast={self.config.fast_ema_period} slow={self.config.slow_ema_period} | "
            f"bar_type={self.config.bar_type}",
            color=LogColor.GREEN,
        )

    def on_stop(self) -> None:
        """
        Actions to be performed when the strategy is stopped.
        """
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop:
            self.close_all_positions_via_exec_algorithm(self.config.instrument_id)

        self.unsubscribe_bars(self.config.bar_type)
        self.log.info("EMACrossStrategy stopped.", color=LogColor.RED)

    def on_reset(self) -> None:
        """
        Actions to be performed when the strategy is reset.
        """
        self.fast_ema.reset()
        self.slow_ema.reset()

    def on_dispose(self) -> None:
        """
        Actions to be performed when the strategy is disposed.

        Cleanup any resources used by the strategy here.
        """

    def on_save(self) -> dict[str, bytes]:
        """
        Actions to be performed when the strategy is saved.

        Create and return a state dictionary of values to be saved.

        Returns
        -------
        dict[str, bytes]
            The strategy state dictionary.

        """
        return {}

    def on_load(self, state: dict[str, bytes]) -> None:
        """
        Actions to be performed when the strategy is loaded.

        Saved state values will be contained in the give state dictionary.

        Parameters
        ----------
        state : dict[str, bytes]
            The strategy state dictionary.

        """

    # ------------------------------------------------------------------
    # Market data handlers
    # ------------------------------------------------------------------

    def on_instrument(self, instrument: Instrument) -> None:
        """
        Actions to be performed when the strategy is running and receives an instrument.

        Parameters
        ----------
        instrument : Instrument
            The instrument received.

        """

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """
        Actions to be performed when the strategy is running and receives a quote tick.

        Parameters
        ----------
        tick : QuoteTick
            The tick received.

        """

    def on_trade_tick(self, tick: TradeTick) -> None:
        """
        Actions to be performed when the strategy is running and receives a trade tick.

        Parameters
        ----------
        tick : TradeTick
            The tick received.

        """

    def on_bar(self, bar: Bar) -> None:
        """
        Actions to be performed when the strategy is running and receives a bar.

        The core signal logic lives here:
        - Wait until both EMAs have warmed up.
        - BUY  when fast EMA >= slow EMA and we are flat or short.
        - SELL when fast EMA <  slow EMA and we are flat or long.

        Parameters
        ----------
        bar : Bar
            The bar received.

        """
        self.log.info(repr(bar), LogColor.CYAN)

        # Wait until both EMAs have enough data to be initialised
        if not self.indicators_initialized():
            self.log.info(
                f"Warming up indicators "
                f"[{self.cache.bar_count(self.config.bar_type)} bars]",
                color=LogColor.BLUE,
            )
            return

        # Ignore zero-range (single-price) bars – they carry no information
        if bar.is_single_price():
            self.log.warning("Single-price bar received – skipping signal check.")
            return

        fast = self.fast_ema.value
        slow = self.slow_ema.value

        self.log.info(
            f"fast_ema={fast:.6f}  slow_ema={slow:.6f}",
            color=LogColor.MAGENTA,
        )

        # ------ BUY signal: fast crosses above slow ------
        if fast >= slow:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions_via_exec_algorithm(self.config.instrument_id)
                self.buy()

        # ------ SELL signal: fast crosses below slow ------
        elif fast < slow:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions_via_exec_algorithm(self.config.instrument_id)
                self.sell()

    def on_data(self, data: Data) -> None:
        """
        Actions to be performed when the strategy is running and receives data.

        Parameters
        ----------
        data : Data
            The data received.

        """

    def on_event(self, event: Event) -> None:
        """
        Actions to be performed when the strategy is running and receives an event.

        Parameters
        ----------
        event : Event
            The event received.

        """

    # ------------------------------------------------------------------
    # Order helpers
    # ------------------------------------------------------------------

    def buy(self) -> None:
        """
        Submit a market BUY order for the configured trade size.

        If an ``exec_algorithm_id`` is configured the order is routed through
        that execution algorithm; otherwise it is sent directly to the venue.
        """
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self._make_qty(),
            time_in_force=TimeInForce.GTC,
            exec_algorithm_id=self.config.exec_algorithm_id,
        )
        self.log.info(f"BUY  {order.quantity} {self.config.instrument_id}", color=LogColor.GREEN)
        self.submit_order(order)

    def sell(self) -> None:
        """
        Submit a market SELL order for the configured trade size.

        If an ``exec_algorithm_id`` is configured the order is routed through
        that execution algorithm; otherwise it is sent directly to the venue.
        """
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self._make_qty(),
            time_in_force=TimeInForce.GTC,
            exec_algorithm_id=self.config.exec_algorithm_id,
        )
        self.log.info(f"SELL {order.quantity} {self.config.instrument_id}", color=LogColor.RED)
        self.submit_order(order)

    def close_all_positions_via_exec_algorithm(self, instrument_id: InstrumentId) -> None:
        """
        Close all open positions using the configured execution algorithm.

        This mirrors ``close_all_positions`` but keeps ``exec_algorithm_id`` on
        the generated reduce-only orders so they are routed through the custom
        execution algorithm.
        """
        positions_open = self.cache.positions_open(
            venue=None,
            instrument_id=instrument_id,
            strategy_id=self.id,
            side=PositionSide.NO_POSITION_SIDE,
        )

        if not positions_open:
            self.log.info(f"No {instrument_id} open positions to close")
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
        """Return a ``Quantity`` matched to the instrument's precision."""
        return self.instrument.make_qty(self.config.trade_size)


# ---------------------------------------------------------------------------
# Factory helper – used by backtest_low_level.py
# ---------------------------------------------------------------------------

def get_trading_strategy(
    instrument_id: InstrumentId,
    exec_algorithm_id: str | None = "MY_GENERIC_ALGO",
    trade_size: Decimal = Decimal("0.10"),
) -> EMACrossStrategy:
    """
    Build and return an ``EMACrossStrategy`` instance for the given instrument.

    The bar type is set to 1-minute LAST-price bars aggregated internally
    (i.e. built from trade ticks by the engine).

    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument the strategy should trade.
    exec_algorithm_id : str or None, default ``"MY_GENERIC_ALGO"``
        The string ID of the execution algorithm to route orders through.
        Pass ``None`` to send orders directly to the venue.

    Returns
    -------
    EMACrossStrategy

    """
    bar_type = BarType.from_str(
        f"{instrument_id}-1-MINUTE-LAST-INTERNAL"
    )

    config = EMACrossStrategyConfig(
        instrument_id=instrument_id,
        bar_type=bar_type,
        trade_size=trade_size,
        fast_ema_period=10,
        slow_ema_period=20,
        exec_algorithm_id=ExecAlgorithmId(exec_algorithm_id) if exec_algorithm_id else None,
    )

    return EMACrossStrategy(config=config)
