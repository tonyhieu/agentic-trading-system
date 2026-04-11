from backtest_engine.backtest_low_level import run_backtest


if __name__ == "__main__":
    engine = run_backtest()
    engine.dispose()
