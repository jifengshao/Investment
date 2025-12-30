"""Tests for initial portfolio creation workflow."""
from __future__ import annotations

import pytest

from accounts.account import Account
from engine.init_engine import (
    InitRecommendation,
    compute_init_allocation,
    validate_target_invariants,
)
from policy.types import AssetMeta


# Sample policy configuration
POLICY = {
    "stabilizer": {"min_pct_total": 0.15, "stabilizer_tickers": ["BND", "BNDX"]},
    "sleeves": {"core_min": 0.65, "core_target": 0.75, "growth_max": 0.30, "growth_target": 0.25},
    "growth": {
        "max_single_stock_weight": 0.10,
        "trim_multiple_of_target": 2.0,
        "prohibit_leveraged": True,
    },
}


def make_accounts() -> list[Account]:
    """Create test accounts."""
    return [
        Account("401k", "tax_advantaged", cash=0.0, holdings={}),
        Account("taxable", "taxable", cash=0.0, holdings={}),
    ]


def make_asset_meta() -> dict[str, AssetMeta]:
    """Create test asset metadata."""
    return {
        "VTI": AssetMeta("VTI", "etf", "core", "high"),
        "VXUS": AssetMeta("VXUS", "etf", "core", "high"),
        "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        "BNDX": AssetMeta("BNDX", "etf", "core", "low", stabilizer=True),
        "QQQ": AssetMeta("QQQ", "etf", "growth", "high"),
        "AAPL": AssetMeta("AAPL", "stock", "growth", "high"),
    }


class TestValidateTargetInvariants:
    """Tests for target invariant validation before allocation."""

    def test_valid_targets_pass(self):
        """Valid targets should produce no warnings."""
        targets = {
            "VTI": 0.40,
            "VXUS": 0.15,
            "BND": 0.15,
            "BNDX": 0.05,
            "QQQ": 0.15,
            "AAPL": 0.10,
        }
        meta = make_asset_meta()

        warnings = validate_target_invariants(targets, meta, POLICY)

        assert len(warnings) == 0

    def test_stabilizer_below_minimum_warns(self):
        """Targets with low stabilizer should warn."""
        targets = {
            "VTI": 0.50,
            "VXUS": 0.20,
            "BND": 0.05,  # Only 10% stabilizer (BND + BNDX)
            "BNDX": 0.05,
            "QQQ": 0.20,
        }
        meta = make_asset_meta()

        warnings = validate_target_invariants(targets, meta, POLICY)

        assert any("stabilizer" in w.lower() for w in warnings)

    def test_growth_above_cap_warns(self):
        """Targets with growth above cap should warn."""
        targets = {
            "VTI": 0.40,
            "BND": 0.15,
            "QQQ": 0.25,  # 35% growth > 30% cap
            "AAPL": 0.10,
            "BNDX": 0.10,
        }
        meta = make_asset_meta()

        warnings = validate_target_invariants(targets, meta, POLICY)

        assert any("growth" in w.lower() for w in warnings)

    def test_single_stock_above_max_warns(self):
        """Targets with single stock above max should warn."""
        targets = {
            "VTI": 0.55,
            "BND": 0.15,
            "QQQ": 0.15,
            "AAPL": 0.15,  # 15% > 10% max
        }
        meta = make_asset_meta()

        warnings = validate_target_invariants(targets, meta, POLICY)

        assert any("single-stock" in w.lower() or "exceeds" in w.lower() for w in warnings)


class TestComputeInitAllocation:
    """Tests for initial allocation computation."""

    def test_allocates_full_amount(self):
        """Should allocate the full requested amount."""
        targets = {"VTI": 0.60, "BND": 0.40}
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = make_accounts()
        account_cash = {"401k": 50000, "taxable": 50000}

        rec = compute_init_allocation(
            total_value=100000,
            targets=targets,
            asset_meta=meta,
            accounts=accounts,
            account_cash=account_cash,
            raw_policy=POLICY,
        )

        total_allocated = sum(t.value for t in rec.trades)
        assert abs(total_allocated - 100000) < 1.0

    def test_respects_target_weights(self):
        """Should allocate according to target weights."""
        targets = {"VTI": 0.70, "BND": 0.30}
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = make_accounts()
        account_cash = {"401k": 50000, "taxable": 50000}

        rec = compute_init_allocation(
            total_value=100000,
            targets=targets,
            asset_meta=meta,
            accounts=accounts,
            account_cash=account_cash,
            raw_policy=POLICY,
        )

        # Calculate allocated amounts per ticker
        by_ticker = rec.summary["allocated_by_ticker"]
        vti_allocated = by_ticker.get("VTI", 0)
        bnd_allocated = by_ticker.get("BND", 0)

        assert abs(vti_allocated - 70000) < 1.0
        assert abs(bnd_allocated - 30000) < 1.0

    def test_bonds_go_to_tax_advantaged(self):
        """Tax-inefficient assets should go to tax-advantaged accounts first."""
        targets = {"BND": 0.50, "VTI": 0.50}
        meta = {
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
        }
        accounts = make_accounts()
        account_cash = {"401k": 60000, "taxable": 40000}

        rec = compute_init_allocation(
            total_value=100000,
            targets=targets,
            asset_meta=meta,
            accounts=accounts,
            account_cash=account_cash,
            raw_policy=POLICY,
        )

        # Find BND trades
        bnd_trades = [t for t in rec.trades if t.ticker == "BND"]

        # BND should primarily go to 401k
        bnd_in_401k = sum(t.value for t in bnd_trades if t.account_id == "401k")
        assert bnd_in_401k > 0

    def test_growth_goes_to_taxable(self):
        """Growth assets should go to taxable accounts first when there's taxable cash."""
        targets = {"AAPL": 0.50, "VTI": 0.50}
        meta = {
            "AAPL": AssetMeta("AAPL", "stock", "growth", "high"),
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
        }
        accounts = make_accounts()
        # Give taxable plenty of cash to receive growth assets
        account_cash = {"401k": 20000, "taxable": 80000}

        rec = compute_init_allocation(
            total_value=100000,
            targets=targets,
            asset_meta=meta,
            accounts=accounts,
            account_cash=account_cash,
            raw_policy=POLICY,
        )

        # Find AAPL trades
        aapl_trades = [t for t in rec.trades if t.ticker == "AAPL"]

        # AAPL (growth stock) should prefer taxable when cash is available
        # With 80k in taxable and 50k target for AAPL, should fit in taxable
        aapl_in_taxable = sum(t.value for t in aapl_trades if t.account_id == "taxable")
        assert aapl_in_taxable > 0

    def test_all_trades_are_buys(self):
        """Initial allocation should only generate buy trades."""
        targets = {"VTI": 0.60, "BND": 0.40}
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = make_accounts()
        account_cash = {"401k": 50000, "taxable": 50000}

        rec = compute_init_allocation(
            total_value=100000,
            targets=targets,
            asset_meta=meta,
            accounts=accounts,
            account_cash=account_cash,
            raw_policy=POLICY,
        )

        for trade in rec.trades:
            assert trade.action == "BUY"

    def test_rejects_targets_not_summing_to_one(self):
        """Should reject targets that don't sum to 1.0."""
        targets = {"VTI": 0.30, "BND": 0.30}  # Sum = 0.60
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = make_accounts()
        account_cash = {"401k": 50000, "taxable": 50000}

        with pytest.raises(ValueError, match="sum to 1.0"):
            compute_init_allocation(
                total_value=100000,
                targets=targets,
                asset_meta=meta,
                accounts=accounts,
                account_cash=account_cash,
                raw_policy=POLICY,
            )

    def test_rejects_mismatched_cash(self):
        """Should reject when account cash doesn't match total."""
        targets = {"VTI": 1.0}
        meta = {"VTI": AssetMeta("VTI", "etf", "core", "high")}
        accounts = make_accounts()
        account_cash = {"401k": 30000, "taxable": 30000}  # 60k != 100k

        with pytest.raises(ValueError, match="must equal"):
            compute_init_allocation(
                total_value=100000,
                targets=targets,
                asset_meta=meta,
                accounts=accounts,
                account_cash=account_cash,
                raw_policy=POLICY,
            )
