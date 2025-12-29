from __future__ import annotations
from typing import Dict, Any
from portfolio.portfolio import Portfolio

def portfolio_summary(portfolio: Portfolio) -> Dict[str, Any]:
    return {
        "total_value": portfolio.total_value(),
        "accounts": [{"id": a.id, "type": a.type, "value": a.total_value()} for a in portfolio.accounts],
        "weights": portfolio.current_weights(),
    }
