from decimal import Decimal

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model import Money
from nautilus_trader.model import TraderId
from nautilus_trader.model import Venue
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType

from backtest_engine.data_loader import load_dbn_partition
from execution_algos import create_execution_algorithm
from strategies import create_strategy


def run_backtest(
    strategy_name: str = "ema_cross",
    execution_algorithm_name: str = "simple",
    strategy_kwargs: dict | None = None,
    execution_algorithm_kwargs: dict | None = None,
    date: str = "20260406",
    symbol: str = "MESM6",
) -> BacktestEngine:
    """Run the low-level backtest and return the configured engine."""
    instrument, ticks = load_dbn_partition(date, symbol)

    config = BacktestEngineConfig(trader_id=TraderId("BACKTESTER-001"))
    engine = BacktestEngine(config=config)

    glbx = Venue("GLBX")
    engine.add_venue(
        venue=glbx,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(1_000_000.0, USD)],
    )

    engine.add_instrument(instrument)
    engine.add_data(ticks)

    strategy_options = dict(strategy_kwargs or {})
    execution_options = dict(execution_algorithm_kwargs or {})

    if strategy_name == "ema_cross":
        strategy_options.setdefault("instrument_id", instrument.id)
        strategy_options.setdefault("trade_size", Decimal("1"))
    if execution_algorithm_name == "simple":
        execution_options.setdefault("exec_id", "MY_GENERIC_ALGO")

    strategy = create_strategy(strategy_name, **strategy_options)
    engine.add_strategy(strategy=strategy)

    exec_algorithm = create_execution_algorithm(
        execution_algorithm_name,
        **execution_options,
    )
    engine.add_exec_algorithm(exec_algorithm)

    engine.run()

    engine.trader.generate_account_report(glbx)
    engine.trader.generate_orders_report()
    engine.trader.generate_order_fills_report()
    engine.trader.generate_positions_report()

    return engine


if __name__ == "__main__":
    backtest_engine = run_backtest()
    backtest_engine.dispose()
