"""Verify the single-symbol DBN partition filter (backtest_engine/dbn_filter.py).

The filter's correctness claim is: the records it keeps decode *identically*
to the same instrument's slice of a full-file decode. This test proves that
against the cached 2026-03-08 partition by decoding both the filtered file and
the full file with Nautilus and comparing every tick value.

No pytest required — run it directly:

    python tests/test_dbn_filter.py

It is also pytest-collectable if pytest is ever added to the project. The test
skips (exit 0 / pytest skip) when the 2026-03-08 partition is not in the local
data-cache, so it never blocks a checkout that hasn't synced data.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backtest_engine.dbn_filter import filter_dbn_partition, instrument_id_for_symbol

_REF_DATE = "20260308"
_REF_SYMBOL = "MESM6"
_PARTITION = (
    REPO_ROOT / "data-cache" / "glbx-mdp3-market-data" / "v1.0.0"
    / "partitions" / f"date={_REF_DATE}" / "data.dbn.zst"
)


def _require_partition():
    if not _PARTITION.exists():
        msg = f"reference partition not in data-cache: {_PARTITION}"
        try:
            import pytest

            pytest.skip(msg)
        except ImportError:
            print(f"SKIP: {msg}")
            sys.exit(0)


def _tick_key(d):
    """A hashable, order-sensitive fingerprint of a QuoteTick / TradeTick."""
    from nautilus_trader.model.data import QuoteTick

    if isinstance(d, QuoteTick):
        return ("Q", d.ts_event, d.bid_price.raw, d.ask_price.raw,
                d.bid_size.raw, d.ask_size.raw)
    return ("T", d.ts_event, d.price.raw, d.size.raw,
            str(d.aggressor_side), d.trade_id.value)


def test_symbol_map_scan_is_unambiguous():
    """The metadata scan resolves MESM6 to exactly one numeric instrument id."""
    _require_partition()
    import struct
    import subprocess

    proc = subprocess.Popen(["zstd", "-dc", str(_PARTITION)], stdout=subprocess.PIPE)
    head = proc.stdout.read(300_000)
    proc.stdout.close()
    proc.terminate()

    assert head[:3] == b"DBN"
    version = head[3]
    meta_len = struct.unpack_from("<I", head, 4)[0]
    metadata = head[8 : 8 + meta_len]

    ids = instrument_id_for_symbol(metadata, _REF_SYMBOL, version)
    assert ids == {42005163}, f"expected {{42005163}}, got {ids}"


def test_filtered_partition_matches_full_decode():
    """Filtered file decodes identically to the MESM6 slice of the full file."""
    _require_partition()
    from nautilus_trader.adapters.databento.loaders import DatabentoDataLoader

    loader = DatabentoDataLoader()

    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / f"data.{_REF_SYMBOL}.dbn.zst"
        kept = filter_dbn_partition(_PARTITION, dst, _REF_SYMBOL)
        assert kept > 0
        # The filtered file must be a small fraction of the multi-instrument original.
        assert dst.stat().st_size < _PARTITION.stat().st_size

        filtered = loader.from_dbn_file(str(dst), include_trades=True)
        full = loader.from_dbn_file(str(_PARTITION), include_trades=True)

    expected = [d for d in full if str(d.instrument_id) == f"{_REF_SYMBOL}.GLBX"]

    # Every record kept by the byte-level filter became exactly one quote.
    from nautilus_trader.model.data import QuoteTick

    assert sum(isinstance(d, QuoteTick) for d in filtered) == kept
    # The filtered file is single-instrument.
    assert {str(d.instrument_id) for d in filtered} == {f"{_REF_SYMBOL}.GLBX"}
    # And it is value-for-value identical to the full decode's MESM6 slice.
    assert [_tick_key(d) for d in filtered] == [_tick_key(d) for d in expected]


def test_unknown_symbol_raises():
    """A symbol absent from the metadata map fails loudly, not silently empty."""
    _require_partition()
    import struct
    import subprocess

    proc = subprocess.Popen(["zstd", "-dc", str(_PARTITION)], stdout=subprocess.PIPE)
    head = proc.stdout.read(300_000)
    proc.stdout.close()
    proc.terminate()
    version = head[3]
    meta_len = struct.unpack_from("<I", head, 4)[0]
    metadata = head[8 : 8 + meta_len]

    try:
        instrument_id_for_symbol(metadata, "NOPE9", version)
    except ValueError:
        return
    raise AssertionError("expected ValueError for an unknown symbol")


if __name__ == "__main__":
    tests = [
        test_symbol_map_scan_is_unambiguous,
        test_filtered_partition_matches_full_decode,
        test_unknown_symbol_raises,
    ]
    for t in tests:
        print(f"... {t.__name__}", flush=True)
        t()
        print(f"PASS {t.__name__}")
    print(f"\nAll {len(tests)} dbn_filter tests passed.")
