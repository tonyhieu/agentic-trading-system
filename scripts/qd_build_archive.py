#!/usr/bin/env python3
"""Build the quality_diversity afg-arm archive from completed backtests.

Computes both candidate axis-2 descriptors so we can pick the more meaningful map:
  - timing_concentration: Gini of open-fill counts over a FIXED 96-bucket 24h
    reference grid (15-min buckets including zeros), per-date then averaged.
    Fixed reference is essential: bucketing over the observed min->max span makes
    a narrow trading window look uniform (low Gini) instead of concentrated.
  - long_fraction: long_count / (long_count + short_count) from metrics.json —
    a directional-balance axis that does not mechanically depend on selectivity.

Axis 1 is always selectivity = trade_count / simple_trade_count (train-aggregated).
Fitness = realized_pnl. Slippage excluded (zero-slippage fill model).

Run after all afg-qd-s* backtests have aggregated. Prints a table; writes nothing
unless --write is passed (then emits archive/loops/report under the chosen axis-2).
"""
from __future__ import annotations
import argparse, glob, json, sys
import numpy as np
import pandas as pd

BASE = "aggressor-flow-gate"
EXP = "experiments/quality_diversity_experiment"
TRAIN_DATES = ["20260308","20260309","20260310","20260311","20260312","20260313",
               "20260315","20260316","20260317","20260318","20260319","20260320"]


def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def timing_concentration(algo: str) -> float | None:
    """Mean over train dates of Gini(open-fills per 15-min bucket, fixed 96-bucket 24h grid)."""
    vals = []
    for d in TRAIN_DATES:
        fp = f"execution_algos/{algo}/results/{d}/fills.csv"
        try:
            f = pd.read_csv(fp, usecols=["ts_init", "is_reduce_only"])
        except FileNotFoundError:
            continue
        o = f[~f["is_reduce_only"].astype(bool)]
        if o.empty:
            vals.append(0.0); continue
        t = pd.to_datetime(o["ts_init"], utc=True)
        # fixed 96-bucket grid: 15-min bucket index within the day
        idx = (t.dt.hour * 4 + t.dt.minute // 15).to_numpy()
        counts = np.bincount(idx, minlength=96).astype(float)
        vals.append(gini(counts))
    return float(np.mean(vals)) if vals else None


def load_perf(algo: str) -> dict | None:
    try:
        return json.load(open(f"execution_algos/{algo}/results/backtest-results.json"))["performance"]
    except (FileNotFoundError, KeyError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--axis2", choices=["timing", "long_fraction"], default="timing")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    simple_tc = sum(json.load(open(f))["trade_count"]
                    for f in glob.glob("execution_algos/simple_execution_strategy/results/2026*/metrics.json"))
    base = load_perf(BASE)
    base_pnl = base["realized_pnl"]

    algos = sorted(glob.glob("execution_algos/afg-qd-s*")) + sorted(glob.glob("execution_algos/afg-qd-l*"))
    algos = [a.split("/")[-1] for a in algos]

    rows = []
    for a in algos:
        perf = load_perf(a)
        if perf is None:
            continue
        tc = perf["trade_count"]
        sel = max(0.0, min(1.0, tc / simple_tc))
        # long_count/short_count live only in per-date metrics.json, not the
        # aggregated performance block — sum them across train dates.
        lc = sc = 0
        for f in glob.glob(f"execution_algos/{a}/results/2026*/metrics.json"):
            md = json.load(open(f))
            lc += md.get("long_count") or 0
            sc += md.get("short_count") or 0
        lf = lc / (lc + sc) if (lc + sc) else None
        tcz = timing_concentration(a)
        rows.append(dict(algo=a, tc=tc, sel=sel, timing=tcz, long_fraction=lf,
                         pnl=perf["realized_pnl"], sharpe=perf["sharpe_ratio"],
                         mdd=perf["max_drawdown_pct"], win_rate=perf["win_rate"],
                         vs_base=(perf["realized_pnl"] - base_pnl) / abs(base_pnl) * 100))

    print(f"simple_tc={simple_tc}  base_pnl={base_pnl}  variants={len(rows)}")
    print(f"{'algo':12}{'tc':>8}{'sel':>7}{'timing':>8}{'longfrac':>9}{'pnl':>9}{'sharpe':>8}{'vs_base%':>9}")
    for r in sorted(rows, key=lambda r: r["sel"]):
        tm = f"{r['timing']:.3f}" if r["timing"] is not None else "  n/a"
        lf = f"{r['long_fraction']:.3f}" if r["long_fraction"] is not None else "  n/a"
        print(f"{r['algo']:12}{r['tc']:>8}{r['sel']:>7.3f}{tm:>8}{lf:>9}{r['pnl']:>9.1f}{r['sharpe']:>8.2f}{r['vs_base']:>+9.1f}")

    # axis-2 spread diagnostics
    tv = [r["timing"] for r in rows if r["timing"] is not None]
    lv = [r["long_fraction"] for r in rows if r["long_fraction"] is not None]
    print(f"\ntiming spread      : {min(tv):.3f}..{max(tv):.3f}  (range {max(tv)-min(tv):.3f})")
    print(f"long_fraction spread: {min(lv):.3f}..{max(lv):.3f}  (range {max(lv)-min(lv):.3f})")

    if not args.write:
        print("\n(dry run — pass --write to emit archive/loops/report)")
        return

    # ---- Build MAP-Elites archive over (selectivity, axis2) ----
    SEL_BINS, SEL_LO, SEL_HI = 5, 0.0, 1.0
    if args.axis2 == "timing":
        A2_BINS, A2_LO, A2_HI, A2KEY = 5, 0.20, 0.95, "timing"
    else:
        A2_BINS, A2_LO, A2_HI, A2KEY = 5, 0.30, 0.70, "long_fraction"

    def binidx(v, b, lo, hi):
        return max(0, min(b - 1, int((v - lo) / (hi - lo) * b)))

    for r in rows:
        r["cell"] = f"{binidx(r['sel'],SEL_BINS,SEL_LO,SEL_HI)}_{binidx(r[A2KEY],A2_BINS,A2_LO,A2_HI)}"

    archive, tally = {}, {"added": 0, "replaced": 0, "rejected": 0}
    for r in sorted(rows, key=lambda r: r["algo"]):  # deterministic order
        c = r["cell"]
        if c not in archive:
            archive[c] = r; res = "added"
        elif r["pnl"] > archive[c]["pnl"]:
            archive[c] = r; res = "replaced"
        else:
            res = "rejected"
        r["ins"] = res; tally[res] += 1

    elites = list(archive.values())
    def dom(a, b):
        ge = a["pnl"] >= b["pnl"] and a["mdd"] >= b["mdd"] and a["sharpe"] >= b["sharpe"]
        gt = a["pnl"] > b["pnl"] or a["mdd"] > b["mdd"] or a["sharpe"] > b["sharpe"]
        return ge and gt
    pareto = sorted([e for e in elites if not any(dom(o, e) for o in elites if o is not e)], key=lambda e: -e["pnl"])
    TOTAL = SEL_BINS * A2_BINS
    qd = sum(max(0, e["pnl"]) for e in elites)
    qdb = sum(max(0, e["pnl"] - base_pnl) for e in elites)
    best = max(elites, key=lambda e: e["pnl"])

    print(f"\n=== ARCHIVE over (selectivity x {A2KEY}) ===")
    print(f"coverage {len(archive)}/{TOTAL} = {len(archive)/TOTAL*100:.0f}%  | tally {tally}")
    print(f"qd_score={qd:.1f}  qd_vs_base={qdb:.1f}  best={best['algo']}@{best['cell']} pnl={best['pnl']:.1f} (+{best['vs_base']:.1f}%)")
    print(f"pareto: {[e['algo'] for e in pareto]}")

    # render map
    print(f"\n           {A2KEY} bins ->")
    for s in range(SEL_BINS - 1, -1, -1):
        row = f"sel-b{s} "
        for w in range(A2_BINS):
            k = f"{s}_{w}"
            row += f"{archive[k]['pnl']:8.0f}" if k in archive else f"{'·':>8}"
        print(row)

    import datetime
    ts = "2026-05-29T00:00:00Z"
    # archive.json
    json.dump({"grid": {"selectivity": {"bins": SEL_BINS, "range": [SEL_LO, SEL_HI]},
                        A2KEY: {"bins": A2_BINS, "range": [A2_LO, A2_HI]}},
               "cells": {e["cell"]: {"algo_id": e["algo"], "descriptors": {"selectivity": round(e["sel"],4), A2KEY: round(e[A2KEY],4)},
                                     "fitness": e["pnl"],
                                     "objectives": {"realized_pnl": e["pnl"], "max_drawdown_pct": e["mdd"], "sharpe_ratio": e["sharpe"], "trade_count": e["tc"]}}
                         for e in elites}},
              open(f"{EXP}/{BASE}/archive.json", "w"), indent=2)
    # report
    json.dump({"experiment": "quality_diversity_experiment", "base_algo": BASE, "pass": "structural",
               "axis2": A2KEY, "loops_run": len(rows), "total_cells": TOTAL,
               "coverage": round(len(archive)/TOTAL, 4), "qd_score": round(qd,2), "qd_score_vs_base": round(qdb,2),
               "base_pnl": base_pnl,
               "best_cell": {"cell_key": best["cell"], "algo_id": best["algo"], "fitness": best["pnl"]},
               "pareto_front": [{"algo_id": e["algo"], "cell_key": e["cell"], "realized_pnl": e["pnl"],
                                 "max_drawdown_pct": e["mdd"], "sharpe_ratio": e["sharpe"]} for e in pareto],
               "insertion_tally": tally, "timestamp": ts},
              open(f"{EXP}/reports/{BASE}-illumination-structural.json", "w"), indent=2)
    print(f"\nwrote {EXP}/{BASE}/archive.json and {EXP}/reports/{BASE}-illumination-structural.json")


if __name__ == "__main__":
    main()
