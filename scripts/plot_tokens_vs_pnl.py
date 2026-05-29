#!/usr/bin/env python3
"""
Plot context tokens used vs. realized PnL for selected execution algorithms.

Usage:
    python scripts/plot_tokens_vs_pnl.py --algos-file path/to/algos.txt
    python scripts/plot_tokens_vs_pnl.py --algos-file algos.txt --output tokens_vs_pnl.png
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

try:
    import matplotlib.pyplot as plt
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit("matplotlib is required to run this script") from exc


REPO_ROOT = Path(__file__).resolve().parent.parent

ALGO_PATTERN = re.compile(r"^(afg|ptg|vrs)-(b|f|m)-l(\d+)$")
BASE_DIRS = {
    "afg": "aggressor-flow-gate",
    "ptg": "position-tier-gate",
    "vrs": "vol-regime-sizer",
}
MODE_DIRS = {
    "b": "brief-summary",
    "f": "full-trace",
    "m": "metrics-only",
}
TOKEN_KEYS = (
    "context_tokens_in",
    "context_tokens",
    "tokens_in",
    "tokens_used",
    "context_chars_in",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a scatter plot of tokens used vs. PnL.",
    )
    parser.add_argument(
        "--algos-file",
        required=True,
        type=Path,
        help="Path to a .txt file with execution algorithm IDs (one per line).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tokens_vs_pnl.png"),
        help="Output image path (default: tokens_vs_pnl.png).",
    )
    parser.add_argument(
        "--title",
        default="Tokens Used vs. Realized PnL",
        help="Plot title.",
    )
    return parser.parse_args()


def read_algo_ids(path: Path) -> Iterable[str]:
    for line in path.read_text().splitlines():
        algo_id = line.strip()
        if not algo_id or algo_id.startswith("#"):
            continue
        yield algo_id


def find_program_entry(algo_id: str, base: str, mode: str) -> Tuple[Optional[dict], Optional[Path]]:
    program_db = (
        REPO_ROOT
        / "experiments"
        / "per_iteration_experiment"
        / BASE_DIRS[base]
        / MODE_DIRS[mode]
        / "program_database.json"
    )
    if not program_db.exists():
        return None, None
    entries = json.loads(program_db.read_text())
    entry = next((item for item in entries if item.get("algo_id") == algo_id), None)
    return entry, program_db


def extract_tokens(entry: dict) -> Tuple[Optional[float], Optional[str]]:
    for key in TOKEN_KEYS:
        value = entry.get(key)
        if value is not None:
            return float(value), key
    return None, None


def extract_pnl(algo_id: str) -> Tuple[Optional[float], Optional[Path]]:
    results_path = (
        REPO_ROOT
        / "execution_algos"
        / algo_id
        / "results"
        / "backtest-results.json"
    )
    if not results_path.exists():
        return None, None
    data = json.loads(results_path.read_text())
    pnl = data.get("performance", {}).get("realized_pnl")
    return (float(pnl) if pnl is not None else None), results_path


def main() -> int:
    args = parse_args()
    if not args.algos_file.exists():
        print(f"ERROR: {args.algos_file} not found", file=sys.stderr)
        return 2

    points = []
    skipped = []

    for algo_id in read_algo_ids(args.algos_file):
        match = ALGO_PATTERN.match(algo_id)
        if not match:
            skipped.append(f"{algo_id} (invalid id)")
            continue
        base, mode, _loop = match.groups()

        entry, program_db = find_program_entry(algo_id, base, mode)
        if entry is None or program_db is None:
            skipped.append(f"{algo_id} (missing program_database.json)")
            continue

        tokens, token_key = extract_tokens(entry)
        if tokens is None or token_key is None:
            skipped.append(f"{algo_id} (no token field in {program_db})")
            continue

        pnl, results_path = extract_pnl(algo_id)
        if pnl is None or results_path is None:
            skipped.append(f"{algo_id} (missing PnL in results)")
            continue

        points.append(
            {
                "algo_id": algo_id,
                "tokens": tokens,
                "token_key": token_key,
                "pnl": pnl,
            }
        )

    if not points:
        print("No valid algorithms found to plot.", file=sys.stderr)
        return 1

    token_keys_used = sorted({p["token_key"] for p in points})
    x_label = f"Context tokens ({', '.join(token_keys_used)})"

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter([p["tokens"] for p in points], [p["pnl"] for p in points], s=60)
    for point in points:
        ax.annotate(
            point["algo_id"],
            (point["tokens"], point["pnl"]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=8,
        )

    ax.set_title(args.title)
    ax.set_xlabel(x_label)
    ax.set_ylabel("Realized PnL (USD)")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(args.output)

    print(f"Wrote plot to {args.output}")
    if skipped:
        print("Skipped:", file=sys.stderr)
        for item in skipped:
            print(f"  - {item}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
