from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Holding:
    ticker: str
    value: float  # dollar value (scaffolding simplification)
