from __future__ import annotations
from dataclasses import dataclass
from .account import Account

@dataclass
class TaxAdvantagedAccount(Account):
    # Future: 401k fund menu constraints, etc.
    pass
