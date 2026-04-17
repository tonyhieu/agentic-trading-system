"""Load ES futures Databento DBN files into a Nautilus Trader catalog.

This script loads the local GLBX definition file first, selects the front-month
ES contract for the market-data date, and then writes both the definitions and
the filtered MBP-1 data into the configured Nautilus Parquet catalog.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader
from nautilus_trader.model.instruments import FuturesContract as NautilusFuturesContract
from nautilus_trader.persistence.catalog import ParquetDataCatalog


DATA_DIR = Path(__file__).resolve().parent / "data"
DEFINITION_FILE = DATA_DIR / "glbx-mdp3-20260401.definition.dbn.zst"
MARKET_DATA_FILE = DATA_DIR / "glbx-mdp3-20260401.mbp-1.dbn.zst"


def _ensure_file_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required data file does not exist: {path}")


def _market_data_date_ns(path: Path) -> int:
    match = re.search(r"(\d{8})", path.name)
    if match is None:
        raise ValueError(f"Could not infer a YYYYMMDD date from file name: {path.name}")

    market_date = datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
    return int(market_date.timestamp() * 1_000_000_000)


def _select_front_month_es_contract(contracts, market_data_file: Path):
    market_date_ns = _market_data_date_ns(market_data_file)

    es_contracts = [
        contract
        for contract in contracts
        if str(getattr(contract, "underlying", "")) == "ES"
        and "-" not in str(getattr(contract, "raw_symbol", ""))
    ]
    if not es_contracts:
        raise ValueError("No outright ES contracts were found in the definition file.")

    active_contracts = [
        contract for contract in es_contracts if contract.expiration_ns > market_date_ns
    ]
    if active_contracts:
        return min(active_contracts, key=lambda contract: contract.expiration_ns)

    return min(es_contracts, key=lambda contract: contract.expiration_ns)


def load_es_futures_data() -> None:
    _ensure_file_exists(DEFINITION_FILE)
    _ensure_file_exists(MARKET_DATA_FILE)

    catalog = ParquetDataCatalog.from_env()
    loader = DatabentoDataLoader()

    definition_records = loader.from_dbn_file(path=DEFINITION_FILE, as_legacy_cython=False)
    definitions = [NautilusFuturesContract.from_pyo3(contract) for contract in definition_records]
    catalog.write_data(definitions)

    front_month_contract = _select_front_month_es_contract(definition_records, MARKET_DATA_FILE)
    market_data = loader.from_dbn_file(
        path=MARKET_DATA_FILE,
        instrument_id=front_month_contract.id,
        as_legacy_cython=False,
    )
    catalog.write_data(market_data)

    print(
        "Loaded ES futures data: "
        f"{len(definitions)} definition records, "
        f"{len(market_data)} market-data records, "
        f"front-month contract={front_month_contract.id}"
    )


if __name__ == "__main__":
    load_es_futures_data()