"""Loop-7 Tier-A falsification (Propose-Audit-Falsify-Commit, prompt-l5).

Run once. Output stays in this file for traceability.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path
import re

DATES = ['20260308','20260309','20260310','20260311','20260312','20260313',
         '20260315','20260316','20260317','20260318','20260320']
BASE = Path('execution_algos/vol-regime-sizer/results')


def parse_usd(s):
    if isinstance(s, (int, float)):
        return float(s)
    return float(re.sub(r'[^\d\.\-]', '', str(s)))


def load_joined(d):
    od = pd.read_csv(BASE / d / 'orders.csv')
    pos = pd.read_csv(BASE / d / 'positions.csv')
    od = od[(~od['is_reduce_only']) & (od['status'] == 'FILLED')].copy().sort_values('ts_init').reset_index(drop=True)
    pos['realized_pnl_usd'] = pos['realized_pnl'].apply(parse_usd)
    pos = pos[pos['side'] == 'FLAT'].copy()
    m = od.merge(pos[['opening_order_id', 'realized_pnl_usd', 'duration_ns']],
                 left_on='exec_spawn_id', right_on='opening_order_id', how='left')
    return m


def main():
    print("=" * 70)
    print("Tier-A falsification — Loop 7")
    print("=" * 70)

    # ------------------------------------------------------------------
    # C1: arrival_mid rolling jump magnitude (K=5)
    # Decision rule: SURVIVED if delta = mean_pnl(low) - mean_pnl(high) >= 0.03
    # on >= 8 of 11 dates AND no sign-reversal of magnitude > 0.06.
    # ------------------------------------------------------------------
    print("\n--- C1: arrival_mid K=5 jump magnitude (per-date median split) ---")
    print(f"{'date':<10} {'n':>6} {'med_jump':>10} {'n_low':>6} {'n_high':>7} {'mean_low':>10} {'mean_high':>10} {'delta':>10}")
    c1_results = []
    for d in DATES:
        m = load_joined(d)
        m['mid_diff'] = m['arrival_mid'].diff().abs()
        m['jump'] = m['mid_diff'].rolling(5, min_periods=5).mean()
        m = m.dropna(subset=['jump', 'realized_pnl_usd'])
        med = m['jump'].median()
        low = m[m['jump'] <= med]
        high = m[m['jump'] > med]
        ml = low['realized_pnl_usd'].mean() if len(low) else float('nan')
        mh = high['realized_pnl_usd'].mean() if len(high) else float('nan')
        delta = ml - mh
        c1_results.append({'date': d, 'med_jump': med, 'n_low': len(low),
                           'n_high': len(high), 'mean_low': ml, 'mean_high': mh,
                           'delta': delta})
        print(f"{d:<10} {len(m):>6d} {med:>10.4f} {len(low):>6d} {len(high):>7d} {ml:>10.4f} {mh:>10.4f} {delta:>10.4f}")

    n_pos = sum(1 for r in c1_results if r['delta'] >= 0.03)
    max_neg = min(r['delta'] for r in c1_results)
    print(f"\nC1 result: n_pass (delta>=0.03)={n_pos}/11; min delta={max_neg:.4f}")
    print(f"C1 rule: SURVIVED if n_pass>=8 AND no date with delta<-0.06.")
    n_bad = sum(1 for r in c1_results if r['delta'] < -0.06)
    if n_pos >= 8 and n_bad == 0:
        c1_verdict = 'SURVIVED'
    else:
        c1_verdict = 'FALSIFIED'
    print(f"C1 VERDICT: {c1_verdict} (n_pass={n_pos}, n_bad_reversal={n_bad})")

    # ------------------------------------------------------------------
    # C2: rolling-pnl streak (M=10 closed positions)
    # delta = mean_pnl(streak<0) - mean_pnl(streak>=0). Predicted < 0.
    # Decision rule: SURVIVED if delta <= -0.03 on >= 8 of 11 dates
    # AND no sign-reversal of magnitude > 0.06.
    # ------------------------------------------------------------------
    print("\n--- C2: Rolling-pnl streak (M=10, lag 1) ---")
    print(f"{'date':<10} {'n':>6} {'n_neg':>6} {'n_nn':>6} {'mn_neg':>10} {'mn_nn':>10} {'delta':>10}")
    c2_results = []
    for d in DATES:
        pos = pd.read_csv(BASE / d / 'positions.csv')
        pos['realized_pnl_usd'] = pos['realized_pnl'].apply(parse_usd)
        pos = pos[pos['side'] == 'FLAT'].copy().sort_values('ts_init').reset_index(drop=True)
        pos['streak'] = pos['realized_pnl_usd'].rolling(10, min_periods=10).mean().shift(1)
        pos = pos.dropna(subset=['streak'])
        neg = pos[pos['streak'] < 0]
        nn = pos[pos['streak'] >= 0]
        mn_neg = neg['realized_pnl_usd'].mean() if len(neg) else float('nan')
        mn_nn = nn['realized_pnl_usd'].mean() if len(nn) else float('nan')
        delta = mn_neg - mn_nn  # expected < 0
        c2_results.append({'date': d, 'n_neg': len(neg), 'n_nn': len(nn),
                           'mn_neg': mn_neg, 'mn_nn': mn_nn, 'delta': delta})
        print(f"{d:<10} {len(pos):>6d} {len(neg):>6d} {len(nn):>6d} {mn_neg:>10.4f} {mn_nn:>10.4f} {delta:>10.4f}")

    n_pass = sum(1 for r in c2_results if r['delta'] <= -0.03)
    n_bad = sum(1 for r in c2_results if r['delta'] > 0.06)
    if n_pass >= 8 and n_bad == 0:
        c2_verdict = 'SURVIVED'
    else:
        c2_verdict = 'FALSIFIED'
    print(f"\nC2 result: n_pass (delta<=-0.03)={n_pass}/11; max(delta)={max(r['delta'] for r in c2_results):.4f}; n_bad_reversal={n_bad}")
    print(f"C2 VERDICT: {c2_verdict}")

    # ------------------------------------------------------------------
    # C3: is_price tail (per-date p90 split)
    # delta = mean_pnl(|is_price| > p90) - mean_pnl(|is_price| <= p90). Predicted < 0.
    # Decision rule: SURVIVED if delta <= -0.05 on >= 8 of 11 dates AND no sign-reversal > 0.10.
    # ------------------------------------------------------------------
    print("\n--- C3: |is_price| tail (per-date p90 split) ---")
    print(f"{'date':<10} {'n':>6} {'p90':>8} {'n_tail':>7} {'n_body':>7} {'mn_tail':>10} {'mn_body':>10} {'delta':>10}")
    c3_results = []
    for d in DATES:
        m = load_joined(d)
        m['abs_isp'] = m['is_price'].abs()
        m = m.dropna(subset=['realized_pnl_usd'])
        p90 = m['abs_isp'].quantile(0.90)
        tail = m[m['abs_isp'] > p90]
        body = m[m['abs_isp'] <= p90]
        mt = tail['realized_pnl_usd'].mean() if len(tail) else float('nan')
        mb = body['realized_pnl_usd'].mean() if len(body) else float('nan')
        delta = mt - mb
        c3_results.append({'date': d, 'p90': p90, 'n_tail': len(tail),
                           'n_body': len(body), 'mn_tail': mt, 'mn_body': mb,
                           'delta': delta})
        print(f"{d:<10} {len(m):>6d} {p90:>8.4f} {len(tail):>7d} {len(body):>7d} {mt:>10.4f} {mb:>10.4f} {delta:>10.4f}")

    n_pass = sum(1 for r in c3_results if r['delta'] <= -0.05)
    n_bad = sum(1 for r in c3_results if r['delta'] > 0.10)
    if n_pass >= 8 and n_bad == 0:
        c3_verdict = 'SURVIVED'
    else:
        c3_verdict = 'FALSIFIED'
    print(f"\nC3 result: n_pass (delta<=-0.05)={n_pass}/11; n_bad_reversal={n_bad}; max(delta)={max(r['delta'] for r in c3_results):.4f}")
    print(f"C3 VERDICT: {c3_verdict}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"C1 (arrival_mid jump):     {c1_verdict}")
    print(f"C2 (rolling-pnl streak):   {c2_verdict}")
    print(f"C3 (|is_price| tail):      {c3_verdict}")


if __name__ == '__main__':
    main()
