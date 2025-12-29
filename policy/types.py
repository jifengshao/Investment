from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class AssetMeta:
    ticker: str
    asset_type: str
    sleeve: str
    tax_efficiency: str
    stabilizer: bool = False
    leveraged: bool = False
