"""Data subscriber strategy for ingesting and analyzing Databento data."""

from __future__ import annotations

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class DataSubscriberConfig(StrategyConfig, frozen=True):
    """
    Configuration for ``DataSubscriber`` instances.

    Parameters
    ----------
    instrument_ids : list[InstrumentId] | None
        List of instrument IDs to subscribe to. If ``None``, no subscriptions
        are made on start.

    """

    instrument_ids: list[InstrumentId] | None = None


class DataSubscriber(Strategy):
    """
    A simple data subscriber strategy that ingests and logs market data.

    This strategy subscribes to quote ticks, trade ticks, and order book data
    for a configured set of instruments and logs all incoming data for analysis.

    It does not generate trading signals or place orders.

    Parameters
    ----------
    config : DataSubscriberConfig
        The configuration for the instance.

    """

    def __init__(self, config: DataSubscriberConfig) -> None:
        super().__init__(config)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """
        Actions to be performed when the strategy is started.

        Subscribes to market data for all configured instruments.
        """
        if not self.config.instrument_ids:
            self.log.warning("No instrument IDs configured for subscription.")
            return

        for instrument_id in self.config.instrument_ids:
            self.subscribe_quote_ticks(instrument_id)
            self.subscribe_trade_ticks(instrument_id)
            # Uncomment to subscribe to order book updates:
            # self.subscribe_order_book_deltas(instrument_id)

        self.log.info(
            f"DataSubscriber started | subscribed to {len(self.config.instrument_ids)} instruments",
            color=LogColor.GREEN,
        )

    def on_stop(self) -> None:
        """
        Actions to be performed when the strategy is stopped.
        """
        if self.config.instrument_ids:
            for instrument_id in self.config.instrument_ids:
                self.unsubscribe_quote_ticks(instrument_id)
                self.unsubscribe_trade_ticks(instrument_id)

        self.log.info("DataSubscriber stopped.", color=LogColor.RED)

    def on_reset(self) -> None:
        """
        Actions to be performed when the strategy is reset.
        """
        pass

    def on_dispose(self) -> None:
        """
        Actions to be performed when the strategy is disposed.
        """
        pass

    def on_save(self) -> dict[str, bytes]:
        """
        Actions to be performed when the strategy is saved.

        Returns
        -------
        dict[str, bytes]
            The strategy state dictionary (empty for this strategy).

        """
        return {}

    def on_load(self, state: dict[str, bytes]) -> None:
        """
        Actions to be performed when the strategy is loaded.

        Parameters
        ----------
        state : dict[str, bytes]
            The strategy state dictionary.

        """
        pass

    # ------------------------------------------------------------------
    # Market data handlers
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """
        Actions to be performed when a quote tick is received.

        Parameters
        ----------
        tick : QuoteTick
            The quote tick received.

        """
        self.log.info(repr(tick), LogColor.CYAN)

    def on_trade_tick(self, tick: TradeTick) -> None:
        """
        Actions to be performed when a trade tick is received.

        Parameters
        ----------
        tick : TradeTick
            The trade tick received.

        """
        self.log.info(repr(tick), LogColor.MAGENTA)

    def on_bar(self, bar: Bar) -> None:
        """
        Actions to be performed when a bar is received.

        Parameters
        ----------
        bar : Bar
            The bar received.

        """
        self.log.info(repr(bar), LogColor.BLUE)

    def on_data(self, data: Data) -> None:
        """
        Actions to be performed when generic data is received.

        Parameters
        ----------
        data : Data
            The data received.

        """

    def on_event(self, event: Event) -> None:
        """
        Actions to be performed when an event is received.

        Parameters
        ----------
        event : Event
            The event received.

        """

    def on_historical_data(self, data: Data) -> None:
        """
        Actions to be performed when historical data is received.

        Parameters
        ----------
        data : Data
            The historical data received.

        """
        self.log.info(repr(data), LogColor.CYAN)


# ---------------------------------------------------------------------------
# Factory helper – used by backtest_engine/databento_backtest.py
# ---------------------------------------------------------------------------


def get_trading_strategy(instrument_ids: list[str] | None = None) -> DataSubscriber:
    """
    Build and return a ``DataSubscriber`` instance for the given instruments.

    Parameters
    ----------
    instrument_ids : list[str] | None
        List of instrument ID strings to subscribe to (e.g., ["ESM6.GLBX", "GCM6.GLBX"]).
        If ``None``, no instruments are subscribed on start.

    Returns
    -------
    DataSubscriber

    """
    # Convert string instrument IDs to InstrumentId objects
    parsed_instrument_ids = None
    if instrument_ids:
        try:
            parsed_instrument_ids = [
                InstrumentId.from_str(instr_id) for instr_id in instrument_ids
            ]
        except Exception as exc:
            raise ValueError(f"Failed to parse instrument IDs: {exc}") from exc

    config = DataSubscriberConfig(instrument_ids=parsed_instrument_ids)
    return DataSubscriber(config=config)
