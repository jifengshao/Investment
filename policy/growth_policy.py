from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
from portfolio.portfolio import Portfolio

@dataclass(frozen=True)
class GrowthPolicy:
    raw: Dict[str, Any]

    @property
    def max_single_stock_weight(self) -> float:
        return float(self.raw["growth"]["max_single_stock_weight"])

    @property
    def prohibit_leveraged(self) -> bool:
        return bool(self.raw["growth"]["prohibit_leveraged"])

def validate_growth_constraints(portfolio: Portfolio, pol: GrowthPolicy) -> List[str]:
    issues: List[str] = []
    weights = portfolio.current_weights()
    for t, w in weights.items():
        meta = portfolio.asset_meta.get(t)
        if not meta:
            continue
        if pol.prohibit_leveraged and meta.leveraged and w > 0:
            issues.append(f"Leveraged asset held long-term: {t}")
        if meta.asset_type == "stock" and meta.sleeve == "growth" and w > pol.max_single_stock_weight:
            issues.append(f"Single stock overweight: {t} {w:.2%} > {pol.max_single_stock_weight:.2%}")
    return issues
