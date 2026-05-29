"""Stream-filter a multi-instrument DBN partition down to a single symbol.

The CME GLBX MDP3 date partitions in this dataset are multi-instrument: one
`data.dbn.zst` holds every contract that traded that day (~280 instruments).
`DatabentoDataLoader.from_dbn_file()` has no instrument filter — it decodes the
*whole* file into a Python list, and the caller can only drop unwanted
instruments afterwards. On the large partitions that decode is fatal: e.g.
2026-03-16 is 543 MB compressed / 2.2 GB raw / ~27M records, and decoding it
into legacy Cython objects needs ~18 GB of RAM. The backtest subprocess is then
OOM-killed by the kernel on this 15 GB host (no swap) — which earlier research
iterations misdiagnosed as a "Nautilus engine hang".

This module does the filtering *before* the decode. It streams the compressed
partition through the `zstd` CLI, keeps only the DBN records whose
`instrument_id` matches the requested symbol, and writes a small single-symbol
`data.<symbol>.dbn.zst` next to the original. Peak memory is one ~1 MB read
buffer; the filtered file for an MES contract is ~3% of the original.
`load_dbn_partition()` then points `from_dbn_file()` at the small file.

Correctness rests on two things, both verified by `tests/test_dbn_filter.py`
against the 2026-03-08 partition:
  1. The metadata block (DBN prefix + symbol map) is copied verbatim, so
     Nautilus still resolves `instrument_id -> "MESM6.GLBX"` exactly as before.
  2. Records are copied byte-for-byte, so the kept subset decodes identically
     to the same instrument's slice of a full-file decode.

Only DBN v1 (the format of this dataset) is supported. The record-header layout
used here is stable across DBN versions, but the symbol-map scan assumes the
v1 fixed 22-byte symbol C-strings; other versions raise a clear error.

Reference: https://databento.com/docs/standards-and-conventions/databento-binary-encoding
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

# DBN v1 fixed length of a symbol C-string field (null-padded ASCII).
_V1_SYMBOL_CSTR_LEN = 22

# DBN record header: length(u8, in 4-byte units), rtype(u8), publisher_id(u16),
# instrument_id(u32), ts_event(u64). 16 bytes; `instrument_id` starts at byte 4.
_REC_HEADER_LEN = 16
_INSTRUMENT_ID_OFFSET = 4

# Read granularity for the decompressed record stream.
_CHUNK = 1 << 20


def _require_zstd() -> str:
    zstd = shutil.which("zstd")
    if zstd is None:
        raise RuntimeError(
            "The `zstd` CLI is required to filter DBN partitions but was not "
            "found on PATH. Install it (e.g. `apt-get install zstd`)."
        )
    return zstd


def _have_zstd_cli() -> bool:
    """Return True if the `zstd` CLI is available on PATH."""
    return shutil.which("zstd") is not None


def _read_exact(stream, n: int) -> bytes:
    """Read exactly `n` bytes from a pipe, looping over short reads."""
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise ValueError(
                f"DBN stream ended early: wanted {n} bytes, got {n - remaining}"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_header_block(stream) -> tuple[bytes, int, bytes]:
    """Read and return (full_header_bytes, version, metadata_bytes).

    `full_header_bytes` is the 8-byte DBN prefix plus the metadata block,
    copied verbatim into the filtered output so Nautilus sees an unchanged
    symbol map.
    """
    prefix = _read_exact(stream, 8)
    if prefix[:3] != b"DBN":
        raise ValueError(f"not a DBN stream: magic={prefix[:3]!r}")
    version = prefix[3]
    metadata_len = struct.unpack_from("<I", prefix, 4)[0]
    metadata = _read_exact(stream, metadata_len)
    return prefix + metadata, version, metadata


def instrument_id_for_symbol(metadata: bytes, symbol: str, version: int) -> set[int]:
    """Resolve a raw symbol (e.g. "MESM6") to its numeric DBN instrument id(s).

    Scans the metadata symbol-map for a mapping entry whose raw symbol matches
    `symbol` and returns every numeric id it maps to (a symbol may map to
    different ids over disjoint date intervals; a 1-day partition has one).

    The scan locates `b"<symbol>\\0"` at a 22-byte C-string boundary, then
    validates the following bytes against the mapping-entry layout — interval
    count in range, dates shaped like YYYYMMDD, mapped value numeric — so a
    coincidental hit in the `symbols` list (which is not a mapping entry) is
    rejected rather than silently misread.
    """
    if version != 1:
        raise RuntimeError(
            f"DBN v{version} is not supported by the partition filter "
            f"(only v1, the format of this dataset). Extend "
            f"backtest_engine/dbn_filter.py if the dataset format changes."
        )
    cstr = _V1_SYMBOL_CSTR_LEN
    want = symbol.encode("ascii")
    if len(want) >= cstr:
        raise ValueError(f"symbol {symbol!r} too long for a {cstr}-byte field")
    padded = want + b"\x00" * (cstr - len(want))

    ids: set[int] = set()
    for match in re.finditer(re.escape(want) + b"\x00", metadata):
        o = match.start()
        # Must be an exact, fully null-padded C-string (a real symbol field).
        if metadata[o : o + cstr] != padded:
            continue
        p = o + cstr
        if p + 4 > len(metadata):
            continue
        interval_count = struct.unpack_from("<I", metadata, p)[0]
        p += 4
        if not (0 < interval_count < 10_000):
            continue  # not a mapping entry — coincidental match elsewhere
        entry_ids: set[int] = set()
        ok = True
        for _ in range(interval_count):
            if p + 8 + cstr > len(metadata):
                ok = False
                break
            start_date, end_date = struct.unpack_from("<II", metadata, p)
            p += 8
            mapped = metadata[p : p + cstr].split(b"\x00")[0].decode("ascii", "replace")
            p += cstr
            # YYYYMMDD-shaped dates confirm we're aligned on a mapping entry.
            if not (19000000 < start_date < 21000000 and 19000000 < end_date < 21000000):
                ok = False
                break
            if mapped.isdigit():
                entry_ids.add(int(mapped))
        if ok and entry_ids:
            ids |= entry_ids

    if not ids:
        raise ValueError(
            f"symbol {symbol!r} not found in the DBN metadata symbol map"
        )
    return ids


def _filter_record_stream(
    read_stream,
    write_callable,
    ids: set[int],
    src_name: str,
) -> int:
    """Pump the decompressed record stream `read_stream` through the
    instrument-id filter and call `write_callable(bytes)` for each kept
    chunk. Returns the number of records kept. Does NOT write the DBN
    header — the caller is responsible for that.
    """
    kept = 0
    buf = b""
    while True:
        chunk = read_stream.read(_CHUNK)
        if not chunk:
            break
        buf += chunk
        i, n = 0, len(buf)
        out: list[bytes] = []
        while i + _REC_HEADER_LEN <= n:
            rec_len = buf[i] * 4
            if rec_len < _REC_HEADER_LEN:
                raise ValueError(
                    f"corrupt DBN record at byte {i}: length={rec_len}"
                )
            if i + rec_len > n:
                break  # record split across chunk boundary
            iid = int.from_bytes(
                buf[i + _INSTRUMENT_ID_OFFSET : i + _INSTRUMENT_ID_OFFSET + 4],
                "little",
            )
            if iid in ids:
                out.append(buf[i : i + rec_len])
                kept += 1
            i += rec_len
        if out:
            write_callable(b"".join(out))
        buf = buf[i:]

    if buf:
        raise ValueError(
            f"trailing {len(buf)} bytes in {src_name} — file truncated "
            f"or record stream misaligned"
        )
    return kept


def _filter_via_cli(src: Path, dst: Path, symbol: str) -> int:
    """zstd-CLI implementation of filter_dbn_partition."""
    zstd = _require_zstd()

    decomp = subprocess.Popen([zstd, "-dc", str(src)], stdout=subprocess.PIPE)
    try:
        assert decomp.stdout is not None
        header, version, metadata = _read_header_block(decomp.stdout)
        ids = instrument_id_for_symbol(metadata, symbol, version)

        tmp = dst.with_suffix(dst.suffix + ".tmp")
        comp = subprocess.Popen(
            [zstd, "-q", "-f", "-o", str(tmp), "-"], stdin=subprocess.PIPE
        )
        kept = 0
        try:
            assert comp.stdin is not None
            comp.stdin.write(header)
            kept = _filter_record_stream(decomp.stdout, comp.stdin.write, ids, src.name)
            comp.stdin.close()
        except BaseException:
            try:
                comp.stdin.close()
            except OSError:
                pass
            comp.wait()
            tmp.unlink(missing_ok=True)
            raise

        if comp.wait() != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"zstd compression failed for {dst}")
        if decomp.wait() != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"zstd decompression failed for {src}")
        if kept == 0:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"no records for symbol {symbol!r} in {src.name} "
                f"(instrument ids {sorted(ids)})"
            )
        os.replace(tmp, dst)
        return kept
    finally:
        if decomp.poll() is None:
            decomp.kill()
            decomp.wait()


def _filter_via_zstandard(src: Path, dst: Path, symbol: str) -> int:
    """Python-zstandard implementation of filter_dbn_partition.

    Used as a fallback when the `zstd` CLI is not on PATH (e.g. Windows
    hosts where installing the CLI separately is awkward). `zstandard`
    is a pip-installable Python binding for libzstd; the streaming
    decoder/encoder used here keeps peak memory bounded the same way
    the CLI version does.
    """
    import zstandard as zstd_mod  # local import: optional dependency

    tmp = dst.with_suffix(dst.suffix + ".tmp")
    kept = 0
    try:
        with open(src, "rb") as fin, open(tmp, "wb") as fout:
            dctx = zstd_mod.ZstdDecompressor()
            cctx = zstd_mod.ZstdCompressor()
            with dctx.stream_reader(fin) as decomp, cctx.stream_writer(fout) as comp:
                header, version, metadata = _read_header_block(decomp)
                ids = instrument_id_for_symbol(metadata, symbol, version)
                comp.write(header)
                kept = _filter_record_stream(decomp, comp.write, ids, src.name)
        if kept == 0:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"no records for symbol {symbol!r} in {src.name} "
                f"(instrument ids {sorted(ids)})"
            )
        os.replace(tmp, dst)
        return kept
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def filter_dbn_partition(src: Path, dst: Path, symbol: str) -> int:
    """Write a single-symbol copy of DBN partition `src` to `dst`.

    Streams `src` (a `.dbn.zst` file), keeps only the records for `symbol`,
    and writes them — behind the original's verbatim header — to `dst`
    (also `.dbn.zst`). Returns the number of records kept.

    Prefers the `zstd` CLI when available (lowest overhead). Falls back to
    the Python `zstandard` module when the CLI is not on PATH — useful on
    Windows hosts. The output is byte-equivalent either way because both
    paths share the same record-filter helper and write the original DBN
    header verbatim.

    Peak memory is bounded by one ~1 MB read buffer regardless of `src` size.
    The write is atomic: `dst` only appears once fully written. Raises if the
    symbol is absent from the file or if zero records are kept (either would
    otherwise surface much later as a confusing empty backtest).
    """
    src, dst = Path(src), Path(dst)
    if _have_zstd_cli():
        return _filter_via_cli(src, dst, symbol)
    return _filter_via_zstandard(src, dst, symbol)
