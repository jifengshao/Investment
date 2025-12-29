from __future__ import annotations
from dataclasses import dataclass
from .account import Account

@dataclass
class TaxableAccount(Account):
    # Future: lots, TLH, wash sales, etc.
    pass
