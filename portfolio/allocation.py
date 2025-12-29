from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class Allocation:
    targets: Dict[str, float]  # ticker -> weight

    def validate_sum_to_one(self, tol: float = 1e-6) -> None:
        s = sum(self.targets.values())
        if abs(s - 1.0) > tol:
            raise ValueError(f"Targets must sum to 1.0, got {s}")
