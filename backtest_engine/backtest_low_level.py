from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model import Money
from nautilus_trader.model import TraderId
from nautilus_trader.model import Venue

from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.test_kit.providers import TestDataProvider
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from execution_algos.simple_execution_strategy import get_execution_algorithm
from strategies.ema_strategy import get_trading_strategy


def run_backtest() -> BacktestEngine:
    """Run the low-level backtest and return the configured engine."""
    # Load stub test data
    provider = TestDataProvider()
    trades_df = provider.read_csv_ticks("binance/ethusdt-trades.csv")

    # Initialize the instrument which matches the data
    ethusdt_binance = TestInstrumentProvider.ethusdt_binance()

    # Process into Nautilus objects
    wrangler = TradeTickDataWrangler(instrument=ethusdt_binance)
    ticks = wrangler.process(trades_df)

    # Configure and build backtest engine
    config = BacktestEngineConfig(trader_id=TraderId("BACKTESTER-001"))
    engine = BacktestEngine(config=config)

    # Add a trading venue (multiple venues possible)
    binance = Venue("BINANCE")
    engine.add_venue(
        venue=binance,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,  # Spot CASH account (not for perpetuals or futures)
        base_currency=None,  # Multi-currency account
        starting_balances=[Money(1_000_000.0, USDT), Money(10.0, ETH)],
    )

    # Add instrument and data
    engine.add_instrument(ethusdt_binance)
    engine.add_data(ticks)

    # Instantiate and add strategy
    strategy = get_trading_strategy(ethusdt_binance.id)
    engine.add_strategy(strategy=strategy)

    # Instantiate and add execution algorithm
    exec_algorithm = get_execution_algorithm(exec_id="MY_GENERIC_ALGO")
    engine.add_exec_algorithm(exec_algorithm)

    # Run the engine (from start to end of data)
    engine.run()

    # Generate reports
    engine.trader.generate_account_report(binance)
    engine.trader.generate_orders_report()
    engine.trader.generate_order_fills_report()
    engine.trader.generate_positions_report()

    return engine


if __name__ == "__main__":
    backtest_engine = run_backtest()
    backtest_engine.dispose()
