from backtest_engine.backtest_low_level import run_backtest


if __name__ == "__main__":
    engine = run_backtest(
        strategy_name="oracle",
        strategy_kwargs={
            "horizon_seconds": 30.0,
            "sigma": 0.1,
            "signal_interval_seconds": 60.0,
            "entry_threshold": 0.5,
            "seed": 42,
        },
    )
    engine.dispose()
