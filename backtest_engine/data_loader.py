"""Load a CME GLBX market-data partition as Nautilus ticks.

Two source backends, selected by the `DATA_SOURCE` env var:
  - `s3` (default): multi-instrument daily partition pulled from S3, then
    filtered to one symbol via filter_dbn_partition. Legacy path.
  - `databento`: single-symbol mbp-1 + trades files pulled directly from
    the Databento Historical API. No filter step needed.

Both backends produce the same `(instrument, ticks)` tuple shape for
run_backtest().
"""
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
DATABENTO_DATASET = "GLBX.MDP3"
_MONTH_CODES = "FGHJKMNQUVXZ"
# Activation pinned in the past, expiration far in the future, so any 1-day
# backtest in the dataset's range falls inside the contract's tradable window.
_ACTIVATION_NS = 1_577_836_800_000_000_000  # 2020-01-01
_EXPIRATION_NS = 4_102_444_800_000_000_000  # 2100-01-01


def _underlying_from_symbol(symbol: str) -> str:
    return symbol.rstrip("0123456789").rstrip(_MONTH_CODES)


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
    """Return (instrument, ticks) for one (date, symbol).

    `date` is YYYYMMDD (e.g. "20260406"); `symbol` is a Databento raw_symbol
    such as "MESM6" (Micro E-mini S&P 500, June 2026) or "GCM6" (Gold, June 2026).

    Source backend is selected by `DATA_SOURCE` env var (`s3` | `databento`).
    Default is `s3` for back-compat.
    """
    cache_dir = os.environ.get("DATA_CACHE_DIR", "./data-cache")
    source = os.environ.get("DATA_SOURCE", "s3").lower()

    if source == "databento":
        return _load_from_databento(date, symbol, cache_dir)
    if source == "s3":
        return _load_from_s3(date, symbol, cache_dir)
    raise ValueError(
        f"Unknown DATA_SOURCE={source!r}; expected 's3' or 'databento'"
    )


def _load_from_s3(date: str, symbol: str, cache_dir: str) -> tuple[Instrument, list]:
    bucket = os.environ["S3_BUCKET_NAME"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    retriever = DataRetriever(bucket, region, cache_dir)
    retriever.sync_partition(DATASET_NAME, DATASET_VERSION, f"date={date}")

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
    if not symbol_path.exists():
        filter_dbn_partition(full_path, symbol_path, symbol)

    instrument = _build_instrument(symbol)

    loader = DatabentoDataLoader()
    all_data = loader.from_dbn_file(symbol_path, include_trades=True)
    # `symbol_path` is single-instrument by construction; this is a safety net.
    ticks = [d for d in all_data if d.instrument_id == instrument.id]
    return instrument, ticks


def _load_from_databento(date: str, symbol: str, cache_dir: str) -> tuple[Instrument, list]:
    # Imported here so the S3 branch does not require `databento` installed.
    from scripts.databento_retriever import DatabentoRetriever

    retriever = DatabentoRetriever(cache_dir=cache_dir)
    # Match the S3 codepath: the legacy partition is mbp-1 ONLY (rtype=1
    # exclusively, no separate TradeMsg stream), and Nautilus synthesizes
    # trade ticks from the book updates via include_trades=True. Fetching a
    # separate `trades` schema here would inject denser real trade prints
    # and break parity with historical pass_gate calibration.
    mbp1_path = retriever.sync_partition(DATABENTO_DATASET, "mbp-1", symbol, date)

    instrument = _build_instrument(symbol)
    loader = DatabentoDataLoader()
    all_data = loader.from_dbn_file(mbp1_path, include_trades=True)
    # Single-symbol by construction (symbols=[symbol] passed to get_range);
    # this filter is the same safety net as the S3 branch.
    ticks = [d for d in all_data if d.instrument_id == instrument.id]
    return instrument, ticks
