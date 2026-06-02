#!/usr/bin/env python3
"""Build research/roll_schedule.yaml from Databento per-expiry daily volume.

For each `root` (e.g. MES, GC), fetch `ohlcv-1d` across the configured
backtest window via the `parent` symbology (e.g. `MES.FUT` expands to every
live MES expiry). For each session, pick the raw_symbol with the highest
volume as the active front month. Apply N-session hysteresis so a one-day
volume blip doesn't flip the table.

This is a one-shot data-prep step — the agent does NOT run it. Re-run when
extending the backtest window:

    python scripts/build_roll_schedule.py
    python scripts/build_roll_schedule.py --roots MES,GC --start 2026-03-01 --end 2026-09-30
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*a, **k):
        return False

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "research" / "config.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "research" / "roll_schedule.yaml"
DEFAULT_DATASET = "GLBX.MDP3"
DEFAULT_HYSTERESIS = 2  # consecutive sessions of higher volume required to roll


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--roots",
        default="MES",
        help="Comma-separated root symbols (e.g. MES,GC). Each is expanded "
             "via parent symbology (MES.FUT).",
    )
    p.add_argument(
        "--dataset", default=DEFAULT_DATASET,
        help=f"Databento dataset code (default: {DEFAULT_DATASET}).",
    )
    p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="Path to research/config.yaml (used to default start/end from "
             "data_window if --start/--end not given).",
    )
    p.add_argument(
        "--start", help="ISO date YYYY-MM-DD. Defaults to data_window.train[0].",
    )
    p.add_argument(
        "--end", help="ISO date YYYY-MM-DD (inclusive). Defaults to data_window.test[1].",
    )
    p.add_argument(
        "--hysteresis", type=int, default=DEFAULT_HYSTERESIS,
        help=f"Consecutive sessions of higher volume required to roll "
             f"(default: {DEFAULT_HYSTERESIS}).",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)}).",
    )
    return p.parse_args()


def resolve_window(args: argparse.Namespace) -> tuple[str, str]:
    if args.start and args.end:
        return args.start, args.end
    with args.config.open() as f:
        cfg = yaml.safe_load(f)
    start = args.start or cfg["data_window"]["train"][0]
    # Default end = test window end so the table covers train + test.
    end = args.end or cfg["data_window"]["test"][1]
    return start, end


def fetch_daily_volume(dataset: str, root: str, start: str, end: str) -> pd.DataFrame:
    """Returns a DataFrame indexed by (date, raw_symbol) with a `volume` column."""
    import databento

    client = databento.Historical()  # uses DATABENTO_API_KEY
    # end is exclusive in Databento's API; bump by a day so the user's
    # inclusive --end is actually included.
    end_exclusive = (
        datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    store = client.timeseries.get_range(
        dataset=dataset,
        schema="ohlcv-1d",
        symbols=[f"{root}.FUT"],
        stype_in="parent",
        start=start,
        end=end_exclusive,
    )
    df = store.to_df()  # map_symbols=True attaches `symbol` (raw_symbol) column
    if df.empty:
        raise RuntimeError(
            f"No ohlcv-1d records returned for {root}.FUT over {start} → {end}"
        )

    # Index is `ts_event` (timestamp). Normalize to a date column.
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["ts_event"]).dt.tz_convert("UTC").dt.date
    return df[["date", "symbol", "volume"]]


def pick_front_month(daily: pd.DataFrame, hysteresis: int) -> dict[str, str]:
    """For each date, pick the highest-volume raw_symbol; require `hysteresis`
    consecutive sessions of leadership before switching to a new contract.

    Returns {YYYY-MM-DD: raw_symbol}. Sessions with no volume data are
    dropped (the date is absent from the output — callers will fall back
    to the previous mapped date or fail loudly).
    """
    schedule: dict[str, str] = {}
    current_front: str | None = None
    candidate: str | None = None
    candidate_streak = 0

    for date, group in daily.groupby("date"):
        top = group.sort_values("volume", ascending=False).iloc[0]
        top_symbol = top["symbol"]

        if current_front is None:
            # First date — seed with whatever's leading.
            current_front = top_symbol
            candidate = None
            candidate_streak = 0
        elif top_symbol == current_front:
            # No challenger; reset.
            candidate = None
            candidate_streak = 0
        else:
            if top_symbol == candidate:
                candidate_streak += 1
            else:
                candidate = top_symbol
                candidate_streak = 1
            if candidate_streak >= hysteresis:
                current_front = candidate
                candidate = None
                candidate_streak = 0

        schedule[date.isoformat()] = current_front

    return schedule


def main() -> int:
    args = parse_args()
    start, end = resolve_window(args)
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]

    if not os.environ.get("DATABENTO_API_KEY"):
        print(
            "ERROR: DATABENTO_API_KEY not set. Add it to .env or export it.",
            file=sys.stderr,
        )
        return 2

    schedule_by_root: dict[str, dict[str, str]] = {}
    for root in roots:
        print(f">>> {root}.FUT  {start} → {end}", flush=True)
        daily = fetch_daily_volume(args.dataset, root, start, end)
        schedule = pick_front_month(daily, args.hysteresis)
        n_rolls = sum(
            1 for a, b in zip(list(schedule.values())[:-1], list(schedule.values())[1:])
            if a != b
        )
        print(f"    {len(schedule)} sessions, {n_rolls} roll(s)")
        schedule_by_root[root] = schedule

    args.output.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Generated by scripts/build_roll_schedule.py — DO NOT hand-edit.\n"
        f"# Source: {args.dataset} ohlcv-1d, parent symbology, "
        f"{args.hysteresis}-session hysteresis.\n"
        f"# Window: {start} → {end}.\n"
    )
    with args.output.open("w") as f:
        f.write(header)
        yaml.safe_dump(schedule_by_root, f, sort_keys=True, default_flow_style=False)
    print(f"Wrote: {args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
