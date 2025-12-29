from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class TaxPolicy:
    raw: Dict[str, Any]

    @property
    def buy_first_sell_last(self) -> bool:
        return bool(self.raw["taxable"]["buy_first_sell_last"])

    @property
    def avoid_short_term_days(self) -> int:
        return int(self.raw["taxable"]["avoid_short_term_days"])
