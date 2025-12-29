from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Literal

AccountType = Literal["taxable", "tax_advantaged"]

@dataclass
class Account:
    id: str
    type: AccountType
    cash: float = 0.0
    holdings: Dict[str, float] = field(default_factory=dict)

    def total_value(self) -> float:
        return self.cash + sum(self.holdings.values())
