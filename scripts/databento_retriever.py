#!/usr/bin/env python3
"""Direct Databento HTTP fetcher for single-symbol, single-day DBN partitions.

Counterpart to scripts/data_retriever.py: instead of pulling multi-instrument
day partitions from S3, this fetches exactly one (dataset, schema, symbol,
date) tuple from Databento's Historical API and caches it under
`data-cache/databento/<dataset>/<schema>/<symbol>/<YYYYMMDD>.dbn.zst`.

Selected via `DATA_SOURCE=databento` in the backtest loader; the S3 path
remains the default and is untouched.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*a, **k):
        return False

load_dotenv()


class DatabentoRetriever:
    """Idempotent, on-disk-cached single-symbol DBN fetcher."""

    def __init__(self, api_key: str | None = None, cache_dir: str = "./data-cache"):
        # Lazy import so importing this module does not require the dep at
        # parse time (e.g. for the S3-only branch).
        import databento

        self.client = databento.Historical(api_key)  # uses DATABENTO_API_KEY env if api_key is None
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def sync_partition(
        self,
        dataset: str,
        schema: str,
        symbol: str,
        date: str,
        verbose: bool = False,
    ) -> Path:
        """Fetch one (dataset, schema, symbol, date) DBN file. Idempotent.

        `date` is YYYYMMDD. Returns the local path to the cached `.dbn.zst`.
        Skips the HTTP roundtrip entirely when the file is already on disk.
        """
        out = self._cache_path(dataset, schema, symbol, date)
        if out.exists() and out.stat().st_size > 0:
            if verbose:
                print(f"✓ Using cached partition: {out}")
            return out

        start, end = _day_bounds_utc(date)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Stream to a temp file then atomically rename, so a crash mid-download
        # cannot leave a half-written `*.dbn.zst` in the cache.
        tmp = out.with_suffix(out.suffix + ".download")

        if verbose:
            print(
                f"Fetching {dataset} {schema} {symbol} {date} "
                f"({start.isoformat()} → {end.isoformat()}) → {out}"
            )
        self.client.timeseries.get_range(
            dataset=dataset,
            schema=schema,
            symbols=[symbol],
            stype_in="raw_symbol",
            start=start,
            end=end,
            path=str(tmp),
        )
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError(
                f"Databento returned empty file for {dataset} {schema} {symbol} {date}"
            )
        os.replace(tmp, out)
        return out

    def _cache_path(self, dataset: str, schema: str, symbol: str, date: str) -> Path:
        # e.g. data-cache/databento/glbx.mdp3/mbp-1/MESM6/20260308.dbn.zst
        return (
            self.cache_dir
            / "databento"
            / dataset.lower()
            / schema
            / symbol
            / f"{date}.dbn.zst"
        )


def _day_bounds_utc(date: str) -> tuple[datetime, datetime]:
    """YYYYMMDD → (start, end) UTC datetimes spanning a single calendar day.

    Databento's `get_range` treats `end` as exclusive, so [00:00, +24h) covers
    one UTC day. CME GLBX sessions run on US Central time and roll Sundays
    17:00 CT through Fridays 16:00 CT; a single UTC day clips a portion of
    one or two trading sessions — fine for backtests that key off UTC dates.
    """
    d = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc)
    return d, d + timedelta(days=1)


def main() -> int:
    """CLI mirroring scripts/data_retriever.py for ad-hoc fetches."""
    cache_dir = os.environ.get("DATA_CACHE_DIR", "./data-cache")

    if len(sys.argv) < 5:
        print(
            "Usage: databento_retriever.py <dataset> <schema> <symbol> <YYYYMMDD>",
            file=sys.stderr,
        )
        print("Example: databento_retriever.py GLBX.MDP3 mbp-1 MESM6 20260308", file=sys.stderr)
        return 2

    dataset, schema, symbol, date = sys.argv[1:5]
    retriever = DatabentoRetriever(cache_dir=cache_dir)
    path = retriever.sync_partition(dataset, schema, symbol, date, verbose=True)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
