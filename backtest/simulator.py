from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
import pandas as pd
import numpy as np

@dataclass
class BacktestResult:
    scenario: str
    cagr: float
    vol: float
    max_drawdown: float
    ending_value: float
    equity_curve: pd.Series

def _cagr(series: pd.Series, periods_per_year: int = 252) -> float:
    if len(series) < 2:
        return 0.0
    start = float(series.iloc[0])
    end = float(series.iloc[-1])
    years = (len(series)-1) / periods_per_year
    return (end/start) ** (1/years) - 1 if (start > 0 and years > 0) else 0.0

def _vol(returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(returns.std()) * np.sqrt(periods_per_year)

def _max_drawdown(series: pd.Series) -> float:
    peak = series.cummax()
    dd = (series/peak) - 1.0
    return float(dd.min())

def generate_synthetic_prices(tickers: List[str], start="2000-01-03", end="2023-12-29", seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)
    prices = pd.DataFrame(index=dates)
    for t in tickers:
        if t in ("BND", "BNDX"):
            mu, sigma = 0.00015, 0.004
        else:
            mu, sigma = 0.00035, 0.012
        rets = rng.normal(mu, sigma, size=n)
        prices[t] = 100 * np.exp(np.cumsum(rets))
    prices.index.name = "date"
    return prices

def run_backtest(prices: pd.DataFrame, weights: Dict[str, float], rebalance_freq: str = "M", start_value: float = 100.0) -> pd.Series:
    tickers = [t for t in weights if t in prices.columns]
    w = np.array([weights[t] for t in tickers], dtype=float)
    w = w / w.sum()
    daily = prices[tickers].pct_change().fillna(0.0)
    reb_dates = daily.resample(rebalance_freq).last().index

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
    tickers = list(prices.columns)
    bonds = [t for t in tickers if t in ("BND", "BNDX")]
    stocks = [t for t in tickers if t not in bonds]

    w_with = {}
    if stocks:
        for t in stocks:
            w_with[t] = 0.80 / len(stocks)
    if bonds:
        for t in bonds:
            w_with[t] = 0.20 / len(bonds)

    w_no = {}
    if stocks:
        for t in stocks:
            w_no[t] = 1.0 / len(stocks)
    else:
        w_no = {tickers[0]: 1.0}

    return {"with_bonds": w_with, "no_bonds": w_no}

def compare(prices: pd.DataFrame) -> List[BacktestResult]:
    results = []
    for name, wts in scenario_weights(prices).items():
        eq = run_backtest(prices, wts, rebalance_freq="M")
        rets = eq.pct_change().fillna(0.0)
        results.append(BacktestResult(
            scenario=name,
            cagr=_cagr(eq),
            vol=_vol(rets),
            max_drawdown=_max_drawdown(eq),
            ending_value=float(eq.iloc[-1]),
            equity_curve=eq,
        ))
    return results
