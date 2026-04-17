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
    """
    bucket = os.environ["S3_BUCKET_NAME"]
    region = os.environ.get("AWS_REGION", "us-east-1")
    cache_dir = os.environ.get("DATA_CACHE_DIR", "./data-cache")

    retriever = DataRetriever(bucket, region, cache_dir)
    retriever.sync_partition(DATASET_NAME, DATASET_VERSION, f"date={date}")

    dbn_path = (
        Path(cache_dir) / DATASET_NAME / DATASET_VERSION
        / "partitions" / f"date={date}" / "data.dbn.zst"
    )

    instrument = _build_instrument(symbol)

    loader = DatabentoDataLoader()
    all_data = loader.from_dbn_file(dbn_path, include_trades=True)
    ticks = [d for d in all_data if d.instrument_id == instrument.id]
    return instrument, ticks
