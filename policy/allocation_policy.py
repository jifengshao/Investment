from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
from portfolio.portfolio import Portfolio

@dataclass(frozen=True)
class AllocationPolicy:
    raw: Dict[str, Any]

    @property
    def core_min(self) -> float:
        return float(self.raw["sleeves"]["core_min"])

    @property
    def growth_max(self) -> float:
        return float(self.raw["sleeves"]["growth_max"])

def sleeve_weights(portfolio: Portfolio) -> Dict[str, float]:
    total = portfolio.total_value()
    if total <= 0:
        return {"core": 0.0, "growth": 0.0}
    vals = portfolio.current_values()
    core = growth = 0.0
    for t, v in vals.items():
        meta = portfolio.asset_meta.get(t)
        if not meta:
            continue
        if meta.sleeve == "core":
            core += v
        elif meta.sleeve == "growth":
            growth += v
    return {"core": core/total, "growth": growth/total}

def validate_sleeves(portfolio: Portfolio, pol: AllocationPolicy) -> List[str]:
    sw = sleeve_weights(portfolio)
    issues: List[str] = []
    if sw["core"] < pol.core_min:
        issues.append(f"Core sleeve below minimum: {sw['core']:.2%} < {pol.core_min:.2%}")
    if sw["growth"] > pol.growth_max:
        issues.append(f"Growth sleeve above maximum: {sw['growth']:.2%} > {pol.growth_max:.2%}")
    return issues
