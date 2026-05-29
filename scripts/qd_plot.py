#!/usr/bin/env python3
"""Render the quality_diversity afg-arm illumination figure from on-disk data.

Two panels, both from real backtest results (no synthetic data):
  (left)  MAP-Elites illumination heatmap: selectivity x timing_concentration,
          each filled cell colored by its elite's realized P&L, annotated with
          algo id + P&L. Empty cells are blank (the unreached / infeasible region).
  (right) P&L vs selectivity scatter for ALL variants, colored by timing, with
          the base afg and the greedy parameter-pass optimum marked — shows the
          single-peaked-in-selectivity structure and where the QD best sits vs greedy.

Reads:
  experiments/quality_diversity_experiment/aggressor-flow-gate/archive.json
  execution_algos/afg-qd-*/results/backtest-results.json (+ per-date fills for timing)
Writes:
  experiments/quality_diversity_experiment/reports/aggressor-flow-gate-illumination.png
"""
from __future__ import annotations
import glob, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm

BASE = "aggressor-flow-gate"
EXP = "experiments/quality_diversity_experiment"
ARCH = f"{EXP}/{BASE}/archive.json"
OUT = f"{EXP}/reports/{BASE}-illumination.png"

SIMPLE_TC = sum(json.load(open(f))["trade_count"]
                for f in glob.glob("execution_algos/simple_execution_strategy/results/2026*/metrics.json"))
BASE_PNL = json.load(open(f"execution_algos/{BASE}/results/backtest-results.json"))["performance"]["realized_pnl"]


def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return 0.0 if n == 0 or x.sum() == 0 else float((2*np.arange(1, n+1)-n-1).dot(x)/(n*x.sum()))


def timing(a):
    v = []
    for f in sorted(glob.glob(f"execution_algos/{a}/results/2026*/fills.csv")):
        o = pd.read_csv(f, usecols=["ts_init", "is_reduce_only"])
        o = o[~o["is_reduce_only"].astype(bool)]
        if o.empty:
            v.append(0.0); continue
        t = pd.to_datetime(o["ts_init"], utc=True)
        idx = (t.dt.hour*4 + t.dt.minute//15).to_numpy()
        v.append(gini(np.bincount(idx, minlength=96).astype(float)))
    return float(np.mean(v)) if v else 0.0


arch = json.load(open(ARCH))
grid = arch["grid"]
SB, (SL, SH) = grid["selectivity"]["bins"], grid["selectivity"]["range"]
TB, (TL, TH) = grid["timing"]["bins"], grid["timing"]["range"]
cells = arch["cells"]

# ---- collect all variants for the scatter ----
algos = [p.split("/")[-1] for p in glob.glob("execution_algos/afg-qd-s*")] + [f"afg-qd-l{i}" for i in range(1, 9)]
pts = []
for a in algos:
    p = json.load(open(f"execution_algos/{a}/results/backtest-results.json"))["performance"]
    pts.append(dict(algo=a, sel=p["trade_count"]/SIMPLE_TC, tim=timing(a),
                    pnl=p["realized_pnl"], vs=(p["realized_pnl"]-BASE_PNL)/abs(BASE_PNL)*100,
                    struct=a.startswith("afg-qd-s")))

fig, (axL, axR) = plt.subplots(1, 2, figsize=(16, 6.5))
fig.suptitle("Quality-Diversity Illumination — aggressor-flow-gate arm\n"
             "(MAP-Elites: best execution algorithm per behavior cell)", fontsize=14, fontweight="bold")

# ---------- LEFT: illumination heatmap ----------
M = np.full((SB, TB), np.nan)
for key, e in cells.items():
    s, t = map(int, key.split("_"))
    M[s, t] = e["fitness"]
cmap = matplotlib.colormaps["viridis"].copy(); cmap.set_bad("#eeeeee")
im = axL.imshow(M, origin="lower", aspect="auto", cmap=cmap,
                extent=[0, TB, 0, SB])
for key, e in cells.items():
    s, t = map(int, key.split("_"))
    axL.text(t+0.5, s+0.5, f"{e['algo_id'].replace('afg-qd-','')}\n{e['fitness']:.0f}",
             ha="center", va="center", fontsize=8,
             color="white" if e["fitness"] < (np.nanmax(M)*0.6) else "black")
# mark best
best = max(cells.values(), key=lambda e: e["fitness"])
bs, bt = map(int, [k for k, v in cells.items() if v is best][0].split("_"))
axL.scatter([bt+0.5], [bs+0.5], marker="*", s=420, c="gold", edgecolor="red", linewidth=1.6, zorder=5)
axL.set_xticks(np.arange(TB)+0.5)
axL.set_xticklabels([f"{TL+(TH-TL)*i/TB:.2f}-{TL+(TH-TL)*(i+1)/TB:.2f}" for i in range(TB)], fontsize=8, rotation=30)
axL.set_yticks(np.arange(SB)+0.5)
axL.set_yticklabels([f"{SL+(SH-SL)*i/SB:.1f}-{SL+(SH-SL)*(i+1)/SB:.1f}" for i in range(SB)], fontsize=8)
axL.set_xlabel("timing concentration  (WHEN it trades: 0=all-day  →  1=one burst)")
axL.set_ylabel("selectivity  (HOW MUCH it trades: 0=little  →  1=everything)")
axL.set_title(f"Illumination map — {len(cells)}/{SB*TB} cells filled\n"
              f"★ best = {best['algo_id']} (P&L {best['fitness']:.0f}, "
              f"+{(best['fitness']-BASE_PNL)/abs(BASE_PNL)*100:.0f}% vs base)", fontsize=10)
cb = fig.colorbar(im, ax=axL, fraction=0.046, pad=0.04); cb.set_label("realized P&L (train)")

# ---------- RIGHT: P&L vs selectivity, colored by timing ----------
sc = axR.scatter([p["sel"] for p in pts], [p["pnl"] for p in pts],
                 c=[p["tim"] for p in pts], cmap="plasma", s=90,
                 edgecolor="k", linewidth=0.5, vmin=TL, vmax=TH, zorder=3)
# base + greedy markers
axR.axhline(BASE_PNL, color="grey", ls="--", lw=1)
axR.annotate(f"base afg = {BASE_PNL:.0f}", (0.02, BASE_PNL), fontsize=8, color="grey", va="bottom")
greedy = next(p for p in pts if p["algo"] == "afg-qd-l8")
axR.scatter([greedy["sel"]], [greedy["pnl"]], marker="s", s=130, facecolor="none",
            edgecolor="red", linewidth=2, zorder=4)
axR.annotate(f"greedy optimum\n(param pass, l8)\nsel {greedy['sel']:.2f}, +{greedy['vs']:.0f}%",
             (greedy["sel"], greedy["pnl"]), xytext=(greedy["sel"] - 0.40, greedy["pnl"] + 600),
             fontsize=8, color="red", ha="left",
             bbox=dict(boxstyle="round", fc="white", ec="red", alpha=0.85),
             arrowprops=dict(arrowstyle="->", color="red"))
bestpt = max(pts, key=lambda p: p["pnl"])
axR.scatter([bestpt["sel"]], [bestpt["pnl"]], marker="*", s=420, c="gold", edgecolor="red", linewidth=1.6, zorder=5)
axR.annotate(f"QD best ({bestpt['algo'].replace('afg-qd-','')})\nsel {bestpt['sel']:.2f}, +{bestpt['vs']:.0f}%",
             (bestpt["sel"], bestpt["pnl"]),
             xytext=(bestpt["sel"] + 0.16, bestpt["pnl"] - 250),
             fontsize=9, ha="left", va="top",
             bbox=dict(boxstyle="round", fc="white", ec="0.6", alpha=0.9),
             arrowprops=dict(arrowstyle="->", color="0.4"))
axR.axhline(0, color="k", lw=0.8)
axR.set_xlim(-0.02, 1.05)
# headroom above the tallest point so annotations never collide with the title
_ymax = max(p["pnl"] for p in pts)
_ymin = min(0, min(p["pnl"] for p in pts))
axR.set_ylim(_ymin - 250, _ymax * 1.18)
axR.set_xlabel("selectivity  (trade_count / simple_trade_count)")
axR.set_ylabel("realized P&L (train)")
axR.set_title("P&L vs selectivity (all 23 variants)\ncolor = timing concentration", fontsize=10, pad=12)
axR.grid(alpha=0.3)
cb2 = fig.colorbar(sc, ax=axR, fraction=0.046, pad=0.04); cb2.set_label("timing concentration")

fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("wrote", OUT)
print(f"cells filled {len(cells)}/{SB*TB} | best {best['algo_id']} pnl={best['fitness']:.1f}")
