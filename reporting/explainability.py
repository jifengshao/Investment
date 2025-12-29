from __future__ import annotations
from typing import Dict, Any, List
from engine.trade_planner import Trade

def explainability_report(trades: List[Trade], warnings: List[str], summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "summary": summary,
        "warnings": warnings,
        "trades": [t.__dict__ for t in trades],
    }
