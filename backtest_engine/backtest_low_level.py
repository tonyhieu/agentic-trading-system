from decimal import Decimal
from pathlib import Path

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model import DataType
from nautilus_trader.model import Money
from nautilus_trader.model import TraderId
from nautilus_trader.model import Venue
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import ClientId

from backtest_engine.data_loader import DATASET_NAME, DATASET_VERSION, load_dbn_partition
from backtest_engine.results import Reports, compute_metrics, persist
from execution_algos import create_execution_algorithm
from strategies import create_strategy
from strategies.databento_oracle_strategy import OracleSignal, build_oracle_signals

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTING_BALANCE_USD = 1_000_000.0

# Maps factory execution_algorithm_name -> on-disk directory under `execution_algos/`.
# The trading strategy is held fixed across runs; the execution algorithm is the
# variable under study, so results are tagged to it. Add an entry when registering
# a new execution algorithm.
EXECUTION_DIRS: dict[str, str] = {
    "simple": "simple_execution_strategy",
}


def run_backtest(
    strategy_name: str = "ema_cross",
    execution_algorithm_name: str = "simple",
    strategy_kwargs: dict | None = None,
    execution_algorithm_kwargs: dict | None = None,
    date: str = "20260406",
    symbol: str = "MESM6",
) -> BacktestEngine:
    """Run the low-level backtest, persist a comparable run artifact, and return the engine."""
    instrument, ticks = load_dbn_partition(date, symbol)

    config = BacktestEngineConfig(trader_id=TraderId("BACKTESTER-001"))
    engine = BacktestEngine(config=config)

    glbx = Venue("GLBX")
    engine.add_venue(
        venue=glbx,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(STARTING_BALANCE_USD, USD)],
    )

    engine.add_instrument(instrument)
    engine.add_data(ticks)

    strategy_options = dict(strategy_kwargs or {})
    execution_options = dict(execution_algorithm_kwargs or {})
    oracle_options: dict | None = None

    if strategy_name == "ema_cross":
        strategy_options.setdefault("instrument_id", instrument.id)
        strategy_options.setdefault("trade_size", Decimal("1"))
    if strategy_name == "oracle":
        # The oracle pipeline is split: preprocessing keys here are popped and
        # used to generate OracleSignal data offline; whatever remains is passed
        # straight through to the strategy factory.
        oracle_options = {
            "horizon_seconds": strategy_options.pop("horizon_seconds", 30.0),
            "sigma": strategy_options.pop("sigma", 0.0),
            "seed": strategy_options.pop("seed", 42),
            "signal_interval_seconds": strategy_options.pop("signal_interval_seconds", 1.0),
        }
        signals = build_oracle_signals(ticks, **oracle_options)
        # The DataEngine only routes custom Data subclasses through on_data
        # when they're delivered as `CustomData(DataType, payload)` — raw
        # subclass instances get dropped as "unrecognized type".
        signal_data_type = DataType(OracleSignal)
        wrapped_signals = [CustomData(signal_data_type, sig) for sig in signals]
        engine.add_data(wrapped_signals, client_id=ClientId("ORACLE"))
        print(f"Generated {len(signals)} oracle signals from {len(ticks)} ticks")

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

    reports = Reports(
        account=engine.trader.generate_account_report(glbx),
        orders=engine.trader.generate_orders_report(),
        fills=engine.trader.generate_order_fills_report(),
        positions=engine.trader.generate_positions_report(),
    )

    metrics = compute_metrics(reports, starting_balance=STARTING_BALANCE_USD)
    metadata = {
        "strategy_name": strategy_name,
        "strategy_kwargs": strategy_options,
        "execution_algorithm_name": execution_algorithm_name,
        "execution_algorithm_kwargs": execution_options,
        "date": date,
        "symbol": symbol,
        "venue": str(glbx),
        "dataset_name": DATASET_NAME,
        "dataset_version": DATASET_VERSION,
    }
    if oracle_options is not None:
        metadata["oracle_preprocessing"] = oracle_options

    execution_dir_name = EXECUTION_DIRS.get(execution_algorithm_name, execution_algorithm_name)
    run_dir = persist(
        strategy_dir=REPO_ROOT / "execution_algos" / execution_dir_name,
        metadata=metadata,
        metrics=metrics,
        reports=reports,
    )
    print(f"Run artifact: {run_dir}")

    return engine


if __name__ == "__main__":
    backtest_engine = run_backtest()
    backtest_engine.dispose()
