"""Rebalance engine for ongoing portfolio management.

Computes rebalancing recommendations based on drift detection,
policy validation, and tax-aware trade planning.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from engine.drift_engine import compute_drift
from engine.trade_planner import Trade, plan_trades
from policy.allocation_policy import AllocationPolicy, validate_sleeves
from policy.growth_policy import GrowthPolicy, validate_growth_constraints
from policy.rebalance_policy import RebalancePolicy
from policy.risk_policy import RiskPolicy, stabilizer_weight, validate_stabilizer
from policy.tax_policy import TaxPolicy
from portfolio.portfolio import Portfolio


class RebalanceMode(Enum):
    """Rebalance strategy modes."""

    STRICT = "strict"
    """Fully correct drift within constraints. May require sells."""

    CONSERVATIVE = "conservative"
    """Prefer buys-only; sell only when constraints are violated."""


@dataclass
class Recommendation:
    """Rebalancing recommendation with trades and diagnostics."""

    trades: List[Trade]
    warnings: List[str]
    summary: Dict[str, Any]


def _filter_buys_only(trades: List[Trade]) -> List[Trade]:
    """Filter trades to only include buys."""
    return [t for t in trades if t.action == "BUY"]


def _constraint_violation_sells(
    portfolio: Portfolio,
    raw_policy: Dict[str, Any],
) -> List[Trade]:
    """Generate sells required to fix constraint violations.

    In conservative mode, we only sell when constraints are violated:
    - Single stock exceeds max weight
    - Growth sleeve exceeds cap
    - Leveraged ETFs held (must be sold)

    Args:
        portfolio: Current portfolio state.
        raw_policy: Raw policy configuration.

    Returns:
        List of sell trades to fix violations.
    """
    trades: List[Trade] = []
    growth_policy = GrowthPolicy(raw_policy)
    alloc_policy = AllocationPolicy(raw_policy)

    total_value = portfolio.total_value()
    if total_value <= 0:
        return trades

    current_weights = portfolio.current_weights()
    current_values = portfolio.current_values()

    # Check for leveraged ETFs - must sell completely
    for ticker, weight in current_weights.items():
        meta = portfolio.asset_meta.get(ticker)
        if meta and meta.leveraged and weight > 0 and growth_policy.prohibit_leveraged:
            # Sell all leveraged ETF holdings
            for acct in portfolio.accounts:
                held = acct.holdings.get(ticker, 0.0)
                if held > 0:
                    trades.append(
                        Trade(
                            account_id=acct.id,
                            ticker=ticker,
                            action="SELL",
                            value=held,
                            reason="Constraint violation: leveraged ETF must be sold",
                        )
                    )

    # Check for single-stock overweight
    for ticker, weight in current_weights.items():
        meta = portfolio.asset_meta.get(ticker)
        if not meta:
            continue

        if (
            meta.asset_type == "stock"
            and meta.sleeve == "growth"
            and weight > growth_policy.max_single_stock_weight
        ):
            excess_weight = weight - growth_policy.max_single_stock_weight
            excess_value = excess_weight * total_value

            # Sell excess, preferring tax-advantaged accounts
            remaining_to_sell = excess_value
            for acct in sorted(
                portfolio.accounts, key=lambda a: 0 if a.type == "tax_advantaged" else 1
            ):
                held = acct.holdings.get(ticker, 0.0)
                if held <= 0 or remaining_to_sell <= 0:
                    continue

                sell_amt = min(held, remaining_to_sell)
                trades.append(
                    Trade(
                        account_id=acct.id,
                        ticker=ticker,
                        action="SELL",
                        value=sell_amt,
                        reason=f"Constraint violation: {ticker} exceeds single-stock max",
                    )
                )
                remaining_to_sell -= sell_amt

    # Check for growth sleeve overweight
    growth_weight = sum(
        w
        for t, w in current_weights.items()
        if portfolio.asset_meta.get(t) and portfolio.asset_meta[t].sleeve == "growth"
    )

    if growth_weight > alloc_policy.growth_max:
        excess_weight = growth_weight - alloc_policy.growth_max
        excess_value = excess_weight * total_value

        # Sell growth assets proportionally, preferring tax-advantaged
        growth_tickers = [
            t
            for t in current_weights
            if portfolio.asset_meta.get(t) and portfolio.asset_meta[t].sleeve == "growth"
        ]

        remaining_to_sell = excess_value
        for ticker in sorted(growth_tickers, key=lambda t: -current_weights.get(t, 0)):
            if remaining_to_sell <= 0:
                break

            for acct in sorted(
                portfolio.accounts, key=lambda a: 0 if a.type == "tax_advantaged" else 1
            ):
                held = acct.holdings.get(ticker, 0.0)
                if held <= 0 or remaining_to_sell <= 0:
                    continue

                sell_amt = min(held, remaining_to_sell)
                trades.append(
                    Trade(
                        account_id=acct.id,
                        ticker=ticker,
                        action="SELL",
                        value=sell_amt,
                        reason="Constraint violation: growth sleeve exceeds cap",
                    )
                )
                remaining_to_sell -= sell_amt

    return trades


def recommend(
    portfolio: Portfolio,
    raw_policy: Dict[str, Any],
    mode: RebalanceMode = RebalanceMode.STRICT,
) -> Recommendation:
    """Generate rebalancing recommendation.

    Args:
        portfolio: Current portfolio state.
        raw_policy: Raw policy configuration.
        mode: Rebalancing strategy mode.

    Returns:
        Recommendation with trades, warnings, and summary.
    """
    alloc = AllocationPolicy(raw_policy)
    risk = RiskPolicy(raw_policy)
    growth = GrowthPolicy(raw_policy)
    reb = RebalancePolicy(raw_policy)
    tax = TaxPolicy(raw_policy)

    # Validate current state
    warnings: List[str] = []
    warnings += validate_sleeves(portfolio, alloc)
    warnings += validate_stabilizer(portfolio, risk)
    warnings += validate_growth_constraints(portfolio, growth)

    # Compute drift
    drift = compute_drift(portfolio, reb)

    # Generate trades
    if mode == RebalanceMode.STRICT:
        # Full rebalancing with all necessary trades
        trades = plan_trades(
            portfolio=portfolio,
            drifted=drift.drifted_tickers,
            deltas_value=drift.deltas_value,
            taxable_sell_last=tax.buy_first_sell_last,
        )
    else:
        # Conservative: buys only, plus constraint-violation sells
        all_trades = plan_trades(
            portfolio=portfolio,
            drifted=drift.drifted_tickers,
            deltas_value=drift.deltas_value,
            taxable_sell_last=tax.buy_first_sell_last,
        )
        buy_trades = _filter_buys_only(all_trades)
        constraint_sells = _constraint_violation_sells(portfolio, raw_policy)
        trades = constraint_sells + buy_trades

    # Build summary
    summary = {
        "total_value": portfolio.total_value(),
        "stabilizer_weight": stabilizer_weight(portfolio, risk.stabilizer_tickers),
        "drifted_assets": drift.drifted_tickers,
        "num_trades": len(trades),
        "mode": mode.value,
    }

    return Recommendation(trades=trades, warnings=warnings, summary=summary)
