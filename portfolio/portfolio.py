from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from accounts.account import Account
from policy.types import AssetMeta

@dataclass
class Portfolio:
    accounts: List[Account]
    asset_meta: Dict[str, AssetMeta]
    targets: Dict[str, float]

    def total_value(self) -> float:
        return sum(a.total_value() for a in self.accounts)

    def current_values(self) -> Dict[str, float]:
        vals: Dict[str, float] = {}
        for a in self.accounts:
            for t, v in a.holdings.items():
                vals[t] = vals.get(t, 0.0) + float(v)
        return vals

    def current_weights(self) -> Dict[str, float]:
        total = self.total_value()
        vals = self.current_values()
        if total <= 0:
            return {t: 0.0 for t in self.targets}
        return {t: vals.get(t, 0.0) / total for t in self.targets}
