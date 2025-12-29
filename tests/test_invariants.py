from accounts.account import Account
from policy.types import AssetMeta
from portfolio.portfolio import Portfolio
from policy.risk_policy import RiskPolicy, validate_stabilizer

W = {
    "stabilizer": {"min_pct_total": 0.15, "stabilizer_tickers": ["BND", "BNDX"]},
    "sleeves": {"core_min": 0.65, "growth_max": 0.30},
    "rebalance": {"drift_absolute": 0.05, "drift_relative": 0.20},
    "growth": {"max_single_stock_weight": 0.10, "trim_multiple_of_target": 2.0, "prohibit_leveraged": True},
    "taxable": {"buy_first_sell_last": True, "avoid_short_term_days": 365},
}

def test_stabilizer_min():
    meta = {
        "BND": AssetMeta("BND","etf","core","low", stabilizer=True),
        "VTI": AssetMeta("VTI","etf","core","high"),
    }
    a = Account("401k","tax_advantaged", holdings={"BND": 10, "VTI": 90})
    p = Portfolio([a], meta, targets={"BND": 0.2, "VTI": 0.8})
    pol = RiskPolicy(W)
    issues = validate_stabilizer(p, pol)
    assert issues and "below minimum" in issues[0]
