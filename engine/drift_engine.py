from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from portfolio.portfolio import Portfolio
from policy.rebalance_policy import RebalancePolicy, is_drifted

@dataclass(frozen=True)
class DriftResult:
    drifted_tickers: List[str]
    deltas_value: Dict[str, float]

def compute_drift(portfolio: Portfolio, pol: RebalancePolicy) -> DriftResult:
    total = portfolio.total_value()
    curr_vals = portfolio.current_values()
    curr_w = portfolio.current_weights()
    targets = portfolio.targets

    desired_vals = {t: targets[t] * total for t in targets}
    deltas = {t: desired_vals[t] - curr_vals.get(t, 0.0) for t in targets}

    drifted = []
    for t, tw in targets.items():
        if is_drifted(curr_w.get(t, 0.0), tw, pol.drift_abs, pol.drift_rel):
            drifted.append(t)
    drifted.sort(key=lambda x: abs(deltas.get(x, 0.0)), reverse=True)
    return DriftResult(drifted_tickers=drifted, deltas_value=deltas)
