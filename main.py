# from backtest_engine.backtest_low_level import run_backtest
from backtest_engine.databento_backtest import run_databento_backtest


if __name__ == "__main__":
    engine = run_databento_backtest(dbn_file_path="data/glbx-mdp3-20260401.mbp-1.dbn.zst",
                                    strategy_name="databento_naive")
    engine.dispose()
