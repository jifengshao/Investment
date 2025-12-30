"""Trade planning engine.

Plans trades to rebalance a portfolio based on drift detection,
respecting tax-aware account selection and asset-location heuristics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from policy.types import AssetMeta
from portfolio.portfolio import Portfolio


@dataclass(frozen=True)
class Trade:
    """A recommended trade action."""

    account_id: str
    ticker: str
    action: str  # BUY/SELL
    value: float
    reason: str

    def __str__(self) -> str:
        """Format trade for display."""
        return f"{self.account_id}: {self.action} ${self.value:,.0f} {self.ticker}"

def select_best_account(portfolio: Portfolio, ticker: str) -> str:
    meta: AssetMeta | None = portfolio.asset_meta.get(ticker)
    if meta:
        if meta.asset_type == "stock" or meta.sleeve == "growth":
            for a in portfolio.accounts:
                if a.type == "taxable":
                    return a.id
        if meta.stabilizer or meta.tax_efficiency in ("low", "medium"):
            for a in portfolio.accounts:
                if a.type == "tax_advantaged":
                    return a.id
    return portfolio.accounts[0].id

def plan_trades(
    portfolio: Portfolio,
    drifted: List[str],
    deltas_value: Dict[str, float],
    taxable_sell_last: bool = True,
    max_trades: int = 50,
) -> List[Trade]:
    trades: List[Trade] = []

    for t in drifted:
        delta = deltas_value.get(t, 0.0)
        if abs(delta) < 1e-6:
            continue

        if delta < 0:
            sell_needed = -delta
            # sell in tax-advantaged first
            for a in [acc for acc in portfolio.accounts if acc.type == "tax_advantaged"]:
                held = a.holdings.get(t, 0.0)
                if held <= 0:
                    continue
                amt = min(held, sell_needed)
                if amt > 0:
                    trades.append(Trade(a.id, t, "SELL", amt, "Rebalance sell (prefer tax-advantaged)"))
                    sell_needed -= amt
                if sell_needed <= 1e-6:
                    break

            if sell_needed > 1e-6:
                # taxable sells last resort
                for a in [acc for acc in portfolio.accounts if acc.type == "taxable"]:
                    held = a.holdings.get(t, 0.0)
                    if held <= 0:
                        continue
                    amt = min(held, sell_needed)
                    if amt > 0:
                        trades.append(Trade(a.id, t, "SELL", amt, "Taxable sell (last resort)"))
                        sell_needed -= amt
                    if sell_needed <= 1e-6:
                        break

        else:
            acct = select_best_account(portfolio, t)
            trades.append(Trade(acct, t, "BUY", delta, "Rebalance buy (asset-location aware)"))

        if len(trades) >= max_trades:
            break

    return trades
