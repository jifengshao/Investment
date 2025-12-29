from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
from portfolio.portfolio import Portfolio

@dataclass(frozen=True)
class RiskPolicy:
    raw: Dict[str, Any]

    @property
    def stabilizer_min(self) -> float:
        return float(self.raw["stabilizer"]["min_pct_total"])

    @property
    def stabilizer_tickers(self) -> List[str]:
        return list(self.raw["stabilizer"]["stabilizer_tickers"])

def stabilizer_weight(portfolio: Portfolio, stabilizer_tickers: List[str]) -> float:
    total = portfolio.total_value()
    if total <= 0:
        return 0.0
    vals = portfolio.current_values()
    return sum(vals.get(t, 0.0) for t in stabilizer_tickers) / total

def validate_stabilizer(portfolio: Portfolio, pol: RiskPolicy) -> List[str]:
    w = stabilizer_weight(portfolio, pol.stabilizer_tickers)
    if w < pol.stabilizer_min:
        return [f"Stabilizer below minimum: {w:.2%} < {pol.stabilizer_min:.2%}"]
    return []
