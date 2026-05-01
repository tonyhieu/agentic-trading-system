import databento as db
import pandas as pd
from pathlib import Path

DATA_DIR   = Path(__file__).parent / "data"
TRAIN_FILE = "glbx-mdp3-20260406.mbp-1.dbn.zst"
VAL_FILE   = "glbx-mdp3-20260407.mbp-1.dbn.zst"


def load_ticks(filename: str, symbol: str = "GCM6") -> pd.DataFrame:
    store = db.DBNStore.from_file(str(DATA_DIR / filename))
    df = store.to_df().reset_index()
    df = df[df["symbol"] == symbol]
    df = df[df["bid_px_00"].notna() & df["ask_px_00"].notna()].copy()
    df["mid"] = (df["bid_px_00"] + df["ask_px_00"]) / 2
    return df.sort_values("ts_recv").reset_index(drop=True)
