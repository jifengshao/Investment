from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class RebalancePolicy:
    raw: Dict[str, Any]

    @property
    def drift_abs(self) -> float:
        return float(self.raw["rebalance"]["drift_absolute"])

    @property
    def drift_rel(self) -> float:
        return float(self.raw["rebalance"]["drift_relative"])

def is_drifted(current: float, target: float, drift_abs: float, drift_rel: float) -> bool:
    if target <= 0:
        return False
    abs_d = abs(current - target)
    rel_d = abs_d / target
    return abs_d > drift_abs or rel_d > drift_rel
