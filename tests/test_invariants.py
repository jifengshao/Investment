"""Tests for policy invariant validation.

Covers:
- Stabilizer minimum enforcement
- Growth sleeve cap enforcement
- Single-stock max weight
- Leveraged ETF prohibition
"""
from __future__ import annotations

import pytest

from accounts.account import Account
from policy.allocation_policy import AllocationPolicy, sleeve_weights, validate_sleeves
from policy.growth_policy import GrowthPolicy, validate_growth_constraints
from policy.risk_policy import RiskPolicy, stabilizer_weight, validate_stabilizer
from policy.types import AssetMeta
from portfolio.portfolio import Portfolio


# Shared policy configuration for tests
POLICY = {
    "stabilizer": {"min_pct_total": 0.15, "stabilizer_tickers": ["BND", "BNDX"]},
    "sleeves": {"core_min": 0.65, "core_target": 0.75, "growth_max": 0.30, "growth_target": 0.25},
    "rebalance": {"drift_absolute": 0.05, "drift_relative": 0.20},
    "growth": {
        "max_single_stock_weight": 0.10,
        "trim_multiple_of_target": 2.0,
        "prohibit_leveraged": True,
    },
    "taxable": {"buy_first_sell_last": True, "avoid_short_term_days": 365},
}


def make_portfolio(holdings_401k: dict, holdings_taxable: dict, meta: dict) -> Portfolio:
    """Helper to create a test portfolio."""
    accounts = [
        Account("401k", "tax_advantaged", holdings=holdings_401k),
        Account("taxable", "taxable", holdings=holdings_taxable),
    ]
    asset_meta = {t: AssetMeta(**m) for t, m in meta.items()}
    targets = {t: 0.0 for t in meta}  # Targets not relevant for invariant tests
    return Portfolio(accounts=accounts, asset_meta=asset_meta, targets=targets)


class TestStabilizerMinimum:
    """Tests for stabilizer minimum enforcement."""

    def test_stabilizer_below_minimum_triggers_warning(self):
        """Stabilizer below 15% should trigger warning."""
        meta = {
            "BND": {"ticker": "BND", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
        }
        # BND is 10% of total, below 15% minimum
        p = make_portfolio({"BND": 10, "VTI": 90}, {}, meta)
        pol = RiskPolicy(POLICY)

        issues = validate_stabilizer(p, pol)

        assert len(issues) == 1
        assert "below minimum" in issues[0].lower()

    def test_stabilizer_at_minimum_passes(self):
        """Stabilizer at exactly 15% should pass."""
        meta = {
            "BND": {"ticker": "BND", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
        }
        p = make_portfolio({"BND": 15, "VTI": 85}, {}, meta)
        pol = RiskPolicy(POLICY)

        issues = validate_stabilizer(p, pol)

        assert len(issues) == 0

    def test_stabilizer_above_minimum_passes(self):
        """Stabilizer above 15% should pass."""
        meta = {
            "BND": {"ticker": "BND", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "BNDX": {"ticker": "BNDX", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
        }
        # BND + BNDX = 25%
        p = make_portfolio({"BND": 15, "BNDX": 10, "VTI": 75}, {}, meta)
        pol = RiskPolicy(POLICY)

        issues = validate_stabilizer(p, pol)

        assert len(issues) == 0

    def test_stabilizer_weight_calculation(self):
        """Stabilizer weight should sum all stabilizer tickers."""
        meta = {
            "BND": {"ticker": "BND", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "BNDX": {"ticker": "BNDX", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
        }
        p = make_portfolio({"BND": 100, "BNDX": 50}, {"VTI": 350}, meta)
        pol = RiskPolicy(POLICY)

        weight = stabilizer_weight(p, pol.stabilizer_tickers)

        # 150 / 500 = 0.30
        assert abs(weight - 0.30) < 0.001


class TestGrowthSleeveCap:
    """Tests for growth sleeve cap enforcement."""

    def test_growth_above_cap_triggers_warning(self):
        """Growth sleeve above 30% should trigger warning."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
            "QQQ": {"ticker": "QQQ", "asset_type": "etf", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False},
        }
        # QQQ is 40% of total, above 30% cap
        p = make_portfolio({"VTI": 60}, {"QQQ": 40}, meta)
        pol = AllocationPolicy(POLICY)

        issues = validate_sleeves(p, pol)

        # May have multiple issues (core below min + growth above max)
        growth_issues = [i for i in issues if "growth" in i.lower()]
        assert len(growth_issues) >= 1
        assert any("above maximum" in i.lower() or "exceeds" in i.lower() for i in growth_issues)

    def test_growth_at_cap_passes(self):
        """Growth sleeve at exactly 30% should pass."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
            "QQQ": {"ticker": "QQQ", "asset_type": "etf", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False},
        }
        p = make_portfolio({"VTI": 70}, {"QQQ": 30}, meta)
        pol = AllocationPolicy(POLICY)

        issues = validate_sleeves(p, pol)

        # Only check that growth cap is not violated (core might be below min)
        growth_issues = [i for i in issues if "growth" in i.lower()]
        assert len(growth_issues) == 0


class TestSingleStockMax:
    """Tests for single-stock max weight enforcement."""

    def test_single_stock_above_max_triggers_warning(self):
        """Single growth stock above 10% should trigger warning."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
            "AAPL": {"ticker": "AAPL", "asset_type": "stock", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False},
        }
        # AAPL is 15% of total, above 10% max
        p = make_portfolio({"VTI": 85}, {"AAPL": 15}, meta)
        pol = GrowthPolicy(POLICY)

        issues = validate_growth_constraints(p, pol)

        assert len(issues) >= 1
        assert any("overweight" in i.lower() or "single stock" in i.lower() for i in issues)

    def test_single_stock_at_max_passes(self):
        """Single growth stock at exactly 10% should pass."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
            "AAPL": {"ticker": "AAPL", "asset_type": "stock", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False},
        }
        p = make_portfolio({"VTI": 90}, {"AAPL": 10}, meta)
        pol = GrowthPolicy(POLICY)

        issues = validate_growth_constraints(p, pol)

        stock_issues = [i for i in issues if "overweight" in i.lower() or "single stock" in i.lower()]
        assert len(stock_issues) == 0


class TestLeveragedBan:
    """Tests for leveraged ETF prohibition."""

    def test_leveraged_etf_triggers_warning(self):
        """Holding a leveraged ETF should trigger warning."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False, "leveraged": False},
            "TQQQ": {"ticker": "TQQQ", "asset_type": "etf", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False, "leveraged": True},
        }
        p = make_portfolio({"VTI": 95}, {"TQQQ": 5}, meta)
        pol = GrowthPolicy(POLICY)

        issues = validate_growth_constraints(p, pol)

        assert len(issues) >= 1
        assert any("leveraged" in i.lower() for i in issues)

    def test_no_leveraged_passes(self):
        """Portfolio without leveraged ETFs should pass."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False, "leveraged": False},
            "QQQ": {"ticker": "QQQ", "asset_type": "etf", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False, "leveraged": False},
        }
        p = make_portfolio({"VTI": 90}, {"QQQ": 10}, meta)
        pol = GrowthPolicy(POLICY)

        issues = validate_growth_constraints(p, pol)

        leveraged_issues = [i for i in issues if "leveraged" in i.lower()]
        assert len(leveraged_issues) == 0


class TestSleeveWeights:
    """Tests for sleeve weight calculation."""

    def test_sleeve_weights_calculation(self):
        """Sleeve weights should correctly categorize assets."""
        meta = {
            "VTI": {"ticker": "VTI", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "high", "stabilizer": False},
            "BND": {"ticker": "BND", "asset_type": "etf", "sleeve": "core", "tax_efficiency": "low", "stabilizer": True},
            "QQQ": {"ticker": "QQQ", "asset_type": "etf", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False},
            "AAPL": {"ticker": "AAPL", "asset_type": "stock", "sleeve": "growth", "tax_efficiency": "high", "stabilizer": False},
        }
        # Total: 100, Core: 75 (VTI 50 + BND 25), Growth: 25 (QQQ 15 + AAPL 10)
        p = make_portfolio({"VTI": 50, "BND": 25}, {"QQQ": 15, "AAPL": 10}, meta)

        sw = sleeve_weights(p)

        assert abs(sw["core"] - 0.75) < 0.001
        assert abs(sw["growth"] - 0.25) < 0.001
