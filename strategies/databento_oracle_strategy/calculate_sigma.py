
import os
import sys
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backtest_engine.data_loader import load_dbn_partition
from nautilus_trader.model.data import TradeTick

def calculate_delta_ps(ticks, horizon_seconds=30.0, signal_interval_seconds=1.0):
    horizon_ns = int(horizon_seconds * 1_000_000_000)
    interval_ns = int(signal_interval_seconds * 1_000_000_000)
    
    trades = [t for t in ticks if isinstance(t, TradeTick)]
    if not trades:
        return []

    delta_ps = []
    j = 0
    last_emit_ns = -interval_ns

    for current in trades:
        if interval_ns and current.ts_event - last_emit_ns < interval_ns:
            continue

        target_ts = current.ts_event + horizon_ns
        while j < len(trades) and trades[j].ts_event < target_ts:
            j += 1
        if j >= len(trades):
            break

        future_price = float(trades[j].price)
        current_price = float(current.price)
        delta_ps.append(future_price - current_price)
        last_emit_ns = current.ts_event
        
    return delta_ps

def main():
    symbol = "MESM6"
    dates = ["20260308", "20260309", "20260310", "20260311", "20260312", "20260313", "20260315"]
    horizon_seconds = 30.0
    signal_interval_seconds = 1.0
    target_r2 = 0.0001  # 1 bps
    
    # Mock environment variables for data loader if not set
    if "S3_BUCKET_NAME" not in os.environ:
        os.environ["S3_BUCKET_NAME"] = "dummy-bucket"
    if "DATA_CACHE_DIR" not in os.environ:
        os.environ["DATA_CACHE_DIR"] = str(REPO_ROOT / "data-cache")

    # Mock DataRetriever to avoid AWS CLI check and skip sync
    from scripts.data_retriever import DataRetriever
    def mock_check_aws_cli(self):
        pass
    def mock_sync_partition(self, dataset_name, version, partition_path, verbose=False):
        print(f"  (Skipping AWS sync for {partition_path})")
        pass
    
    DataRetriever._check_aws_cli = mock_check_aws_cli
    DataRetriever.sync_partition = mock_sync_partition

    all_delta_ps = []
    
    for date in dates:
        print(f"Loading data for {date}...")
        try:
            instrument, ticks = load_dbn_partition(date, symbol)
            day_delta_ps = calculate_delta_ps(ticks, horizon_seconds, signal_interval_seconds)
            print(f"  Found {len(day_delta_ps)} signals.")
            all_delta_ps.extend(day_delta_ps)
        except Exception as e:
            print(f"  Error loading {date}: {e}")

    if not all_delta_ps:
        print("No delta Ps found.")
        return

    var_dp = np.var(all_delta_ps)
    std_dp = np.sqrt(var_dp)
    
    # R^2 = Var(DP) / (Var(DP) + sigma^2)
    # sigma^2 = Var(DP) * (1/R^2 - 1)
    sigma2 = var_dp * (1.0 / target_r2 - 1.0)
    sigma = np.sqrt(sigma2)
    
    print("\nResults:")
    print(f"Period: {dates[0]} to {dates[-1]}")
    print(f"Symbol: {symbol}")
    print(f"Horizon: {horizon_seconds}s")
    print(f"Signal Interval: {signal_interval_seconds}s")
    print(f"Target R^2: {target_r2} (1 bps)")
    print(f"Sample size: {len(all_delta_ps)}")
    print(f"Var(Delta P): {var_dp:.6f}")
    print(f"Std(Delta P): {std_dp:.6f}")
    print(f"Required Sigma: {sigma:.6f}")

if __name__ == "__main__":
    main()
