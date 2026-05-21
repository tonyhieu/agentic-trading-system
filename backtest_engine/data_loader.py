"""Sync a CME GLBX market-data partition from S3 and load it as Nautilus ticks."""
import os
import sys
from pathlib import Path

from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import FuturesContract, Instrument
from nautilus_trader.model.objects import Price, Quantity

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest_engine.dbn_filter import filter_dbn_partition
from scripts.data_retriever import DataRetriever

DATASET_NAME = "glbx-mdp3-market-data"
DATASET_VERSION = "v1.0.0"
_MONTH_CODES = "FGHJKMNQUVXZ"
# Activation pinned in the past, expiration far in the future, so any 1-day
# backtest in the dataset's range falls inside the contract's tradable window.
_ACTIVATION_NS = 1_577_836_800_000_000_000  # 2020-01-01
_EXPIRATION_NS = 4_102_444_800_000_000_000  # 2100-01-01


def _underlying_from_symbol(symbol: str) -> str:
    return symbol.rstrip("0123456789").rstrip(_MONTH_CODES)


def _prune_empty_dirs(start: Path, stop: Path) -> None:
    current = start
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _build_instrument(symbol: str) -> FuturesContract:
    return FuturesContract(
        instrument_id=InstrumentId(symbol=Symbol(symbol), venue=Venue("GLBX")),
        raw_symbol=Symbol(symbol),
        asset_class=AssetClass.INDEX,
        exchange="XCME",
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        underlying=_underlying_from_symbol(symbol),
        activation_ns=_ACTIVATION_NS,
        expiration_ns=_EXPIRATION_NS,
        ts_event=_ACTIVATION_NS,
        ts_init=_ACTIVATION_NS,
    )


def load_dbn_partition(date: str, symbol: str) -> tuple[Instrument, list]:
    """Sync one date partition from S3 and return (instrument, ticks) for one contract.

    `date` is YYYYMMDD (e.g. "20260406"); `symbol` is a Databento raw_symbol
    such as "MESM6" (Micro E-mini S&P 500, June 2026) or "GCM6" (Gold, June 2026).

    Tick subsampling can be enabled via TICK_SUBSAMPLE_RATE env var (default 1 = no subsampling).
    For memory-constrained environments (e.g., Lambda), set to 10 or higher to keep every Nth tick.
    """
    bucket = os.environ["S3_BUCKET_NAME"]
    region = os.environ.get("AWS_REGION", "us-east-1")
    cache_dir = os.environ.get("DATA_CACHE_DIR", "./data-cache")
    subsample_rate = int(os.environ.get("TICK_SUBSAMPLE_RATE", "1"))
    preserve_cache = (
        os.environ.get("EVALUATION_RUNTIME") == "ec2"
        or os.environ.get("PRESERVE_DATA_CACHE") == "1"
    )

    retriever = DataRetriever(bucket, region, cache_dir)

    dataset_root = Path(cache_dir) / DATASET_NAME / DATASET_VERSION
    partition_dir = (
        Path(cache_dir) / DATASET_NAME / DATASET_VERSION
        / "partitions" / f"date={date}"
    )
    full_path = partition_dir / "data.dbn.zst"

    # The raw partitions are multi-instrument (~280 contracts/day); the largest
    # are ~2.2 GB decompressed and OOM-kill the loader on this 15 GB host, since
    # `from_dbn_file` decodes the whole file before any instrument filter runs.
    # Filter to the requested symbol once, cache the small result, and decode
    # that instead. See backtest_engine/dbn_filter.py.
    symbol_path = partition_dir / f"data.{symbol}.dbn.zst"

    if symbol_path.exists():
        instrument = _build_instrument(symbol)
        loader = DatabentoDataLoader()
        all_data = loader.from_dbn_file(symbol_path, include_trades=True)
        ticks = [d for d in all_data if d.instrument_id == instrument.id]
        if subsample_rate > 1:
            ticks = ticks[::subsample_rate]
        return instrument, ticks

    retriever.sync_partition(DATASET_NAME, DATASET_VERSION, f"date={date}")

    if not symbol_path.exists():
        filter_dbn_partition(full_path, symbol_path, symbol)

    # The raw multi-instrument file is only needed while generating the
    # single-symbol cache, so free its space before decoding the smaller file.
    try:
        full_path.unlink()
    except FileNotFoundError:
        pass

    instrument = _build_instrument(symbol)

    loader = DatabentoDataLoader()
    try:
        all_data = loader.from_dbn_file(symbol_path, include_trades=True)
        # `symbol_path` is single-instrument by construction; this is a safety net.
        ticks = [d for d in all_data if d.instrument_id == instrument.id]
        
        # Subsample ticks to reduce memory footprint in memory-constrained environments.
        if subsample_rate > 1:
            ticks = ticks[::subsample_rate]
        
        return instrument, ticks
    finally:
        if not preserve_cache:
            try:
                symbol_path.unlink()
            except FileNotFoundError:
                pass
            _prune_empty_dirs(partition_dir, dataset_root)
