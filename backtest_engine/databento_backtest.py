"""Databento backtest engine for replaying market data from .dbn.zst files."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.core.data import Data
from nautilus_trader.model import Money
from nautilus_trader.model import TraderId
from nautilus_trader.model import Venue
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Commodity
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity

from execution_algos import create_execution_algorithm
from strategies.databento_synthetic_signal import SyntheticDatabentoSignal
from strategies import create_strategy


def _generate_synthetic_signal_data(
    data_records: list[Data],
    horizon: int,
    noise_std: float,
    seed: int,
) -> list[CustomData]:
    if horizon <= 0:
        raise ValueError("`synthetic_signal_horizon` must be > 0")

    if noise_std < 0:
        raise ValueError("`synthetic_signal_noise_std` must be >= 0")

    quotes_by_instrument: dict[InstrumentId, list[QuoteTick]] = defaultdict(list)
    for record in data_records:
        if isinstance(record, QuoteTick):
            quotes_by_instrument[record.instrument_id].append(record)

    if not quotes_by_instrument:
        return []

    rng = random.Random(seed)
    generated: list[CustomData] = []

    for instrument_quotes in quotes_by_instrument.values():
        instrument_quotes.sort(key=lambda tick: tick.ts_event)

        for idx in range(len(instrument_quotes) - horizon):
            current = instrument_quotes[idx]
            future = instrument_quotes[idx + horizon]

            current_mid = (current.bid_price.as_double() + current.ask_price.as_double()) / 2.0
            future_mid = (future.bid_price.as_double() + future.ask_price.as_double()) / 2.0
            signal_value = (future_mid - current_mid) + rng.gauss(0.0, noise_std)

            signal = SyntheticDatabentoSignal(
                instrument_id=current.instrument_id,
                value=signal_value,
                ts_event=current.ts_event,
                ts_init=current.ts_init,
            )
            generated.append(CustomData(data_type=DataType(SyntheticDatabentoSignal), data=signal))

    return generated


def run_databento_backtest(
    dbn_file_path: str | Path | None = None,
    instrument_ids: list[str] | None = None,
    strategy_name: str = "databento_subscriber",
    execution_algorithm_name: str = "simple",
    strategy_kwargs: dict | None = None,
    execution_algorithm_kwargs: dict | None = None,
    skip_on_error: bool = True,
    include_trades: bool = False,
    synthetic_signal_horizon: int = 10,
    synthetic_signal_noise_std: float = 0.0,
    synthetic_signal_seed: int = 7,
    generate_synthetic_signals: bool | None = None,
) -> BacktestEngine:
    """
    Run a backtest using Databento data loaded from a .dbn.zst file.

    Parameters
    ----------
    dbn_file_path : str | Path | None
        Path to the Databento .dbn.zst file. If ``None``, defaults to
        ``data/glbx-mdp3-20260401.mbp-1.dbn.zst``.
    instrument_ids : list[str] | None
        List of instrument IDs to filter by (e.g., ["ESM6.GLBX", "GCM6.GLBX"]).
        If ``None``, all instruments from the file are used.
    strategy_name : str, default "databento_subscriber"
        The name of the strategy to instantiate from the registry.
    execution_algorithm_name : str, default "simple"
        The name of the execution algorithm to instantiate from the registry.
    strategy_kwargs : dict | None
        Additional keyword arguments to pass to the strategy factory.
    execution_algorithm_kwargs : dict | None
        Additional keyword arguments to pass to the execution algorithm factory.
    skip_on_error : bool, default True
        Whether to skip malformed Databento records instead of failing.
    include_trades : bool, default False
        Whether to include trades while decoding the Databento file.
    synthetic_signal_horizon : int, default 10
        Lookahead horizon in quote ticks used for synthetic signal generation.
    synthetic_signal_noise_std : float, default 0.0
        Standard deviation of Gaussian noise added to synthetic signal values.
    synthetic_signal_seed : int, default 7
        Random seed for reproducible synthetic signal generation.
    generate_synthetic_signals : bool | None, default None
        If True, inject synthetic custom signals into the replay stream.
        If None, signals are injected only for ``strategy_name='databento_synthetic_signal'``.

    Returns
    -------
    BacktestEngine
        The configured and run backtest engine.

    Raises
    ------
    FileNotFoundError
        If the specified Databento file does not exist.
    ValueError
        If no records are decoded from the file or instrument parsing fails.

    """
    # Resolve file path
    if dbn_file_path is None:
        repo_root = Path(__file__).resolve().parents[1]
        dbn_file_path = repo_root / "data" / "glbx-mdp3-20260401.mbp-1.dbn.zst"
    else:
        dbn_file_path = Path(dbn_file_path).expanduser().resolve()

    if not dbn_file_path.exists():
        raise FileNotFoundError(f"Databento file not found: {dbn_file_path}")

    # Load Databento records
    loader = DatabentoDataLoader()
    parsed_instrument_id = None
    if instrument_ids and len(instrument_ids) == 1:
        # If filtering to a single instrument, use the DatabentoDataLoader filter
        try:
            parsed_instrument_id = InstrumentId.from_str(instrument_ids[0])
        except Exception as exc:
            raise ValueError(
                f"Failed to parse instrument ID '{instrument_ids[0]}': {exc}"
            ) from exc

    records = loader.from_dbn_file(
        path=str(dbn_file_path),
        instrument_id=parsed_instrument_id,
        as_legacy_cython=True,  # Use Cython objects that inherit from Data
        include_trades=include_trades,
        skip_on_error=skip_on_error,
    )

    if not records:
        raise ValueError(
            f"No records decoded from {dbn_file_path}. "
            "Check file path and instrument filters."
        )

    # Extract unique instruments from records
    record_instruments: set[InstrumentId] = set()
    for record in records:
        if hasattr(record, "instrument_id"):
            record_instruments.add(record.instrument_id)

    # Filter instruments if specified (for multiple instruments)
    if instrument_ids and len(instrument_ids) > 1:
        filter_ids = set(InstrumentId.from_str(iid) for iid in instrument_ids)
        record_instruments = record_instruments.intersection(filter_ids)

    if not record_instruments:
        raise ValueError("No matching instruments found in records.")

    # Configure and build backtest engine
    config = BacktestEngineConfig(trader_id=TraderId("BACKTESTER-DATABENTO-001"))
    engine = BacktestEngine(config=config)

    # Add a trading venue (GLBX for CME Globex in this case)
    venue = Venue("GLBX")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(1_000_000.0, USD)],
    )

    # Add instruments - create Commodity instruments for CME contracts
    for instrument_id in record_instruments:
        ts_now = int(datetime.utcnow().timestamp() * 1_000_000_000)
        instrument = Commodity(
            instrument_id=instrument_id,
            raw_symbol=instrument_id.symbol,
            asset_class=AssetClass.COMMODITY,
            quote_currency=USD,
            price_precision=2,
            size_precision=0,
            price_increment=Price(0.01, 2),
            size_increment=Quantity(1, 0),
            ts_event=ts_now,
            ts_init=ts_now,
        )
        engine.add_instrument(instrument)

    # Filter records to exclude Instrument objects (keep market data like QuoteTick, TradeTick, etc.)
    # The DatabentoDataLoader returns a mix of market data and instrument definitions
    data_records = [r for r in records if type(r).__name__ != "Instrument"]

    if not data_records:
        raise ValueError("No market data records found after filtering records.")

    if generate_synthetic_signals is None:
        generate_synthetic_signals = strategy_name == "databento_synthetic_signal"

    if generate_synthetic_signals:
        synthetic_data = _generate_synthetic_signal_data(
            data_records=data_records,
            horizon=synthetic_signal_horizon,
            noise_std=synthetic_signal_noise_std,
            seed=synthetic_signal_seed,
        )
        if not synthetic_data:
            raise ValueError(
                "Synthetic signal generation produced no data. "
                "Ensure QuoteTick data exists and reduce `synthetic_signal_horizon` if needed.",
            )
        data_records.extend(synthetic_data)

    # Add data
    engine.add_data(data_records)

    # Instantiate and add strategy
    strategy_options = dict(strategy_kwargs or {})
    if strategy_name == "databento_subscriber":
        strategy_options.setdefault("instrument_ids", list(instrument_ids) if instrument_ids else None)
    elif strategy_name == "databento_naive" and "instrument_id" not in strategy_options:
        if instrument_ids and len(instrument_ids) > 0:
            strategy_options.setdefault("instrument_id", instrument_ids[0])
        else:
            strategy_options.setdefault(
                "instrument_id",
                str(sorted(record_instruments, key=str)[0]),
            )
    elif strategy_name == "databento_synthetic_signal" and "instrument_id" not in strategy_options:
        if instrument_ids and len(instrument_ids) > 0:
            strategy_options.setdefault("instrument_id", instrument_ids[0])
        else:
            strategy_options.setdefault(
                "instrument_id",
                str(sorted(record_instruments, key=str)[0]),
            )

    strategy = create_strategy(strategy_name, **strategy_options)
    engine.add_strategy(strategy=strategy)

    # Instantiate and add execution algorithm
    exec_options = dict(execution_algorithm_kwargs or {})
    if execution_algorithm_name == "simple":
        exec_options.setdefault("exec_id", "DATABENTO_GENERIC_ALGO")

    exec_algorithm = create_execution_algorithm(execution_algorithm_name, **exec_options)
    engine.add_exec_algorithm(exec_algorithm)

    # Run the engine
    engine.run()

    # Generate reports
    engine.trader.generate_account_report(venue)
    engine.trader.generate_orders_report()
    engine.trader.generate_order_fills_report()
    engine.trader.generate_positions_report()

    return engine


if __name__ == "__main__":
    backtest_engine = run_databento_backtest()
    backtest_engine.dispose()
