"""Smoke tests for module imports and basic functionality."""
from __future__ import annotations


def test_imports():
    """All main modules should be importable."""
    import cli.main
    import common.config_loader
    import accounts.account
    import portfolio.portfolio
    import policy.types
    import policy.allocation_policy
    import policy.growth_policy
    import policy.rebalance_policy
    import policy.risk_policy
    import policy.tax_policy
    import engine.drift_engine
    import engine.init_engine
    import engine.rebalance_engine
    import engine.strategy_engine
    import engine.trade_planner
    import engine.explanation_engine
    import backtest.simulator
    import reporting.summary
    import reporting.explainability


def test_cli_main_help(capsys):
    """CLI should show help without error."""
    import sys
    from cli.main import main

    # Capture help output
    sys.argv = ["cli.main", "--help"]
    try:
        main()
    except SystemExit as e:
        assert e.code == 0

    captured = capsys.readouterr()
    assert "init" in captured.out or "rebalance" in captured.out


def test_config_loader():
    """Config loader should work."""
    from common.config_loader import load_all

    cfg = load_all()

    assert cfg.policy is not None
    assert cfg.accounts is not None
    assert cfg.universe is not None


def test_portfolio_construction():
    """Should be able to construct a portfolio from config."""
    from cli.main import build_portfolio
    from common.config_loader import load_all

    cfg = load_all()
    portfolio = build_portfolio(cfg)

    assert portfolio is not None
    assert portfolio.total_value() > 0
    assert len(portfolio.accounts) > 0


def test_rebalance_engine():
    """Rebalance engine should run without error."""
    from cli.main import build_portfolio
    from common.config_loader import load_all
    from engine.rebalance_engine import recommend

    cfg = load_all()
    portfolio = build_portfolio(cfg)

    rec = recommend(portfolio, cfg.policy)

    assert rec is not None
    assert isinstance(rec.warnings, list)
    assert isinstance(rec.trades, list)


def test_backtest_simulator():
    """Backtest simulator should run without error."""
    from backtest.simulator import compare, generate_synthetic_prices

    prices = generate_synthetic_prices(["VTI", "BND", "QQQ"])

    results = compare(prices)

    assert len(results) > 0
    for r in results:
        assert r.cagr is not None
        assert r.vol is not None
        assert r.max_drawdown <= 0  # Drawdown should be negative or zero
