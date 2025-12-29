from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
from portfolio.portfolio import Portfolio
from policy.allocation_policy import AllocationPolicy, validate_sleeves
from policy.risk_policy import RiskPolicy, validate_stabilizer, stabilizer_weight
from policy.growth_policy import GrowthPolicy, validate_growth_constraints
from policy.rebalance_policy import RebalancePolicy
from policy.tax_policy import TaxPolicy
from engine.drift_engine import compute_drift
from engine.trade_planner import plan_trades, Trade

@dataclass
class Recommendation:
    trades: List[Trade]
    warnings: List[str]
    summary: Dict[str, Any]

def recommend(portfolio: Portfolio, raw_policy: Dict[str, Any]) -> Recommendation:
    alloc = AllocationPolicy(raw_policy)
    risk = RiskPolicy(raw_policy)
    growth = GrowthPolicy(raw_policy)
    reb = RebalancePolicy(raw_policy)
    tax = TaxPolicy(raw_policy)

    warnings: List[str] = []
    warnings += validate_sleeves(portfolio, alloc)
    warnings += validate_stabilizer(portfolio, risk)
    warnings += validate_growth_constraints(portfolio, growth)

    drift = compute_drift(portfolio, reb)
    trades = plan_trades(
        portfolio=portfolio,
        drifted=drift.drifted_tickers,
        deltas_value=drift.deltas_value,
        taxable_sell_last=tax.buy_first_sell_last,
    )

    summary = {
        "total_value": portfolio.total_value(),
        "stabilizer_weight": stabilizer_weight(portfolio, risk.stabilizer_tickers),
        "drifted_assets": drift.drifted_tickers,
        "num_trades": len(trades),
    }
    return Recommendation(trades=trades, warnings=warnings, summary=summary)
