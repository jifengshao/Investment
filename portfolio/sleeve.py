from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

@dataclass
class Sleeve:
    name: str  # core|growth
    holdings: Dict[str, float]  # ticker -> dollar value
