"""Portfolio backtesting simulator.

Provides synthetic price generation, portfolio simulation, and performance metrics.

Metrics computed:
- CAGR (Compound Annual Growth Rate)
- Annualized volatility
- Maximum drawdown
- Worst calendar year return
- Recovery time from max drawdown
- Sharpe ratio
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    """Results from a portfolio backtest."""

    scenario: str
    cagr: float
    vol: float
    max_drawdown: float
    worst_year_return: float
    worst_year: int
    recovery_days: int
    sharpe_ratio: float
    ending_value: float
    equity_curve: pd.Series


def _cagr(series: pd.Series, periods_per_year: int = 252) -> float:
    """Calculate compound annual growth rate.

    Args:
        series: Equity curve series.
        periods_per_year: Trading periods per year (default 252 for daily).

    Returns:
        CAGR as a decimal (e.g., 0.10 for 10%).
    """
    if len(series) < 2:
        return 0.0
    start = float(series.iloc[0])
    end = float(series.iloc[-1])
    years = (len(series) - 1) / periods_per_year
    return (end / start) ** (1 / years) - 1 if (start > 0 and years > 0) else 0.0


def _vol(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calculate annualized volatility.

    Args:
        returns: Daily return series.
        periods_per_year: Trading periods per year.

    Returns:
        Annualized volatility as a decimal.
    """
    return float(returns.std()) * np.sqrt(periods_per_year)


def _max_drawdown(series: pd.Series) -> float:
    """Calculate maximum drawdown.

    Args:
        series: Equity curve series.

    Returns:
        Maximum drawdown as a negative decimal (e.g., -0.30 for 30% drawdown).
    """
    peak = series.cummax()
    dd = (series / peak) - 1.0
    return float(dd.min())


def _worst_year_return(series: pd.Series) -> tuple[float, int]:
    """Calculate worst calendar year return.

    Args:
        series: Equity curve series with DatetimeIndex.

    Returns:
        Tuple of (worst return, year).
    """
    if len(series) < 2:
        return 0.0, 0

    # Resample to yearly, taking last value of each year
    try:
        yearly = series.resample("YE").last()
    except Exception:
        yearly = series.resample("A").last()

    if len(yearly) < 2:
        return 0.0, 0

    # Calculate year-over-year returns
    yearly_returns = yearly.pct_change().dropna()

    if len(yearly_returns) == 0:
        return 0.0, 0

    worst_idx = yearly_returns.idxmin()
    worst_return = float(yearly_returns[worst_idx])
    worst_year = worst_idx.year

    return worst_return, worst_year


def _recovery_days(series: pd.Series) -> int:
    """Calculate recovery time from maximum drawdown in days.

    Args:
        series: Equity curve series.

    Returns:
        Number of days to recover from max drawdown, or -1 if never recovered.
    """
    if len(series) < 2:
        return 0

    peak = series.cummax()
    drawdown = (series / peak) - 1.0

    # Find the date of maximum drawdown
    max_dd_idx = drawdown.idxmin()
    max_dd_date = max_dd_idx

    # Find the peak value at max drawdown
    peak_at_max_dd = peak[max_dd_idx]

    # Find when/if we recovered (equity >= peak)
    post_dd = series[max_dd_date:]

    recovery_mask = post_dd >= peak_at_max_dd
    if recovery_mask.any():
        recovery_idx = recovery_mask.idxmax()
        # Calculate days between max drawdown and recovery
        return (recovery_idx - max_dd_date).days
    else:
        # Never recovered
        return -1


def _sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sharpe ratio.

    Args:
        returns: Daily return series.
        risk_free_rate: Annual risk-free rate (default 2%).
        periods_per_year: Trading periods per year.

    Returns:
        Sharpe ratio.
    """
    if len(returns) < 2 or returns.std() == 0:
        return 0.0

    excess_return = returns.mean() * periods_per_year - risk_free_rate
    annual_vol = returns.std() * np.sqrt(periods_per_year)

    return excess_return / annual_vol if annual_vol > 0 else 0.0


def generate_synthetic_prices(
    tickers: List[str],
    start: str = "2000-01-03",
    end: str = "2023-12-29",
    seed: int = 7,
) -> pd.DataFrame:
    """Generate synthetic daily prices for backtesting.

    Different asset classes have different return/volatility profiles:
    - Bonds (BND, BNDX): Low return, low volatility
    - Broad market ETFs: Medium return, medium volatility
    - Growth stocks/ETFs: Higher return, higher volatility

    Args:
        tickers: List of ticker symbols.
        start: Start date string.
        end: End date string.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with date index and ticker columns.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)
    prices = pd.DataFrame(index=dates)

    # Define asset characteristics
    bond_tickers = {"BND", "BNDX"}
    growth_tickers = {"QQQ", "SPYG", "TQQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"}

    for t in tickers:
        if t in bond_tickers:
            mu, sigma = 0.00015, 0.004  # ~4% annual return, ~6% vol
        elif t in growth_tickers:
            mu, sigma = 0.00045, 0.016  # ~12% annual return, ~25% vol
        else:
            mu, sigma = 0.00035, 0.012  # ~9% annual return, ~19% vol

        rets = rng.normal(mu, sigma, size=n)
        prices[t] = 100 * np.exp(np.cumsum(rets))

    prices.index.name = "date"
    return prices


def run_backtest(
    prices: pd.DataFrame,
    weights: Dict[str, float],
    rebalance_freq: str = "M",
    start_value: float = 100.0,
) -> pd.Series:
    """Run portfolio backtest with periodic rebalancing.

    Args:
        prices: DataFrame of daily prices with date index.
        weights: Target weights per ticker.
        rebalance_freq: Rebalance frequency ('M' for monthly, 'Q' for quarterly).
        start_value: Starting portfolio value.

    Returns:
        Equity curve as a Series.
    """
    tickers = [t for t in weights if t in prices.columns]
    if not tickers:
        return pd.Series([start_value], index=prices.index[:1], name="equity")

    w = np.array([weights[t] for t in tickers], dtype=float)
    w = w / w.sum()  # Normalize weights

    daily = prices[tickers].pct_change().fillna(0.0)
    # Use 'ME' (month end) instead of deprecated 'M'
    freq = "ME" if rebalance_freq == "M" else rebalance_freq
    reb_dates = daily.resample(freq).last().index

    value = start_value
    holdings = value * w
    curve = []

    for dt, r in daily.iterrows():
        holdings = holdings * (1.0 + r.values)
        value = float(holdings.sum())
        if dt in reb_dates:
            holdings = value * w
        curve.append(value)

    return pd.Series(curve, index=daily.index, name="equity")


def scenario_weights(prices: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Generate weight configurations for different scenarios.

    Scenarios:
    - with_bonds: 80% stocks, 20% bonds
    - no_bonds: 100% stocks
    - with_growth_tilt: 70% broad market, 30% growth
    - without_growth_tilt: 100% broad market

    Args:
        prices: Price DataFrame to determine available tickers.

    Returns:
        Dictionary mapping scenario name to weights.
    """
    tickers = list(prices.columns)
    bonds = [t for t in tickers if t in ("BND", "BNDX")]
    growth = [t for t in tickers if t in ("QQQ", "SPYG", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA")]
    broad = [t for t in tickers if t not in bonds and t not in growth]

    # If no broad market tickers, use non-growth, non-bond
    if not broad:
        broad = [t for t in tickers if t not in bonds]

    scenarios = {}

    # with_bonds: 80% stocks, 20% bonds
    w_with: Dict[str, float] = {}
    stocks = [t for t in tickers if t not in bonds]
    if stocks:
        for t in stocks:
            w_with[t] = 0.80 / len(stocks)
    if bonds:
        for t in bonds:
            w_with[t] = 0.20 / len(bonds)
    scenarios["with_bonds"] = w_with

    # no_bonds: 100% stocks
    w_no: Dict[str, float] = {}
    if stocks:
        for t in stocks:
            w_no[t] = 1.0 / len(stocks)
    else:
        w_no = {tickers[0]: 1.0} if tickers else {}
    scenarios["no_bonds"] = w_no

    # with_growth_tilt: 70% broad market, 30% growth (from non-bond assets)
    w_growth: Dict[str, float] = {}
    if broad:
        for t in broad:
            w_growth[t] = 0.70 / len(broad)
    if growth:
        for t in growth:
            w_growth[t] = 0.30 / len(growth)
    elif stocks:
        # If no growth tickers available, just use stocks
        for t in stocks:
            w_growth[t] = 1.0 / len(stocks)
    scenarios["with_growth_tilt"] = w_growth

    # without_growth_tilt: Only broad market (or all stocks if no broad)
    w_no_growth: Dict[str, float] = {}
    if broad:
        for t in broad:
            w_no_growth[t] = 1.0 / len(broad)
    elif stocks:
        for t in stocks:
            w_no_growth[t] = 1.0 / len(stocks)
    else:
        w_no_growth = {tickers[0]: 1.0} if tickers else {}
    scenarios["without_growth_tilt"] = w_no_growth

    return scenarios


def compare(
    prices: pd.DataFrame,
    scenarios: Optional[List[str]] = None,
) -> List[BacktestResult]:
    """Compare multiple portfolio scenarios.

    Args:
        prices: DataFrame of daily prices.
        scenarios: List of scenario names to run (default: all).

    Returns:
        List of BacktestResult objects.
    """
    all_scenarios = scenario_weights(prices)

    if scenarios is None:
        scenarios = list(all_scenarios.keys())

    results = []
    for name in scenarios:
        if name not in all_scenarios:
            continue

        wts = all_scenarios[name]
        if not wts:
            continue

        eq = run_backtest(prices, wts, rebalance_freq="M")
        rets = eq.pct_change().fillna(0.0)

        worst_ret, worst_yr = _worst_year_return(eq)
        rec_days = _recovery_days(eq)

        results.append(
            BacktestResult(
                scenario=name,
                cagr=_cagr(eq),
                vol=_vol(rets),
                max_drawdown=_max_drawdown(eq),
                worst_year_return=worst_ret,
                worst_year=worst_yr,
                recovery_days=rec_days if rec_days >= 0 else 9999,
                sharpe_ratio=_sharpe_ratio(rets),
                ending_value=float(eq.iloc[-1]),
                equity_curve=eq,
            )
        )

    return results
