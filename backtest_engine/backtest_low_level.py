from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast

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


def _load_symbol(module_name: str, module_path: Path, symbol_name: str) -> Any:
    spec = spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to create module spec for {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    try:
        return getattr(module, symbol_name)
    except AttributeError as exc:
        raise ImportError(f"{module_path} does not define '{symbol_name}'") from exc


_ROOT_DIR = Path(__file__).resolve().parents[1]
get_trading_strategy: Callable[..., object] = cast(Callable[..., object], _load_symbol(
    module_name="ema_trading_strategy",
    module_path=_ROOT_DIR / "strategies" / "ema-strategy" / "trading_strategy.py",
    symbol_name="get_trading_strategy",
))

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
