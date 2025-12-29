from __future__ import annotations
from typing import List
from engine.trade_planner import Trade

def explain_trades(trades: List[Trade]) -> List[str]:
    return [f"{t.account_id}: {t.action} ${t.value:,.0f} {t.ticker}  |  {t.reason}" for t in trades]
