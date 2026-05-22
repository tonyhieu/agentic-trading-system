"""Custom Nautilus data type carrying a pre-shifted "future" price."""

from __future__ import annotations

from nautilus_trader.model import register_custom_data_class
from nautilus_trader.model.custom import customdataclass_pyo3
from nautilus_trader.model.identifiers import InstrumentId


@customdataclass_pyo3()
class OracleSignal:
    instrument_id: InstrumentId
    current_price: float = 0.0
    future_price: float = 0.0
    ts_event: int = 0
    ts_init: int = 0


register_custom_data_class(OracleSignal)
