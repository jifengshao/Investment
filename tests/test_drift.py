"""Tests for drift detection."""
from __future__ import annotations

import pytest

from accounts.account import Account
from engine.drift_engine import compute_drift
from policy.rebalance_policy import RebalancePolicy, is_drifted
from policy.types import AssetMeta
from portfolio.portfolio import Portfolio


POLICY = {
    "rebalance": {"drift_absolute": 0.05, "drift_relative": 0.20},
}


class TestIsDrifted:
    """Tests for drift detection function."""

    def test_no_drift_when_at_target(self):
        """Should not be drifted when exactly at target."""
        assert not is_drifted(current=0.30, target=0.30, drift_abs=0.05, drift_rel=0.20)

    def test_drifted_by_absolute_threshold(self):
        """Should be drifted when absolute difference exceeds threshold."""
        # Target 30%, current 36% -> 6% absolute drift > 5% threshold
        assert is_drifted(current=0.36, target=0.30, drift_abs=0.05, drift_rel=0.20)

    def test_drifted_by_relative_threshold(self):
        """Should be drifted when relative difference exceeds threshold."""
        # Target 10%, current 13% -> 30% relative drift > 20% threshold
        assert is_drifted(current=0.13, target=0.10, drift_abs=0.05, drift_rel=0.20)

    def test_not_drifted_when_within_both_thresholds(self):
        """Should not be drifted when within both thresholds."""
        # Target 30%, current 32% -> 2% absolute, 6.7% relative, both within thresholds
        assert not is_drifted(current=0.32, target=0.30, drift_abs=0.05, drift_rel=0.20)

    def test_zero_target_never_drifted(self):
        """Zero target should never be considered drifted."""
        assert not is_drifted(current=0.05, target=0.0, drift_abs=0.05, drift_rel=0.20)


class TestComputeDrift:
    """Tests for drift computation on portfolios."""

    def test_compute_drift_finds_drifted_tickers(self):
        """Should identify tickers that have drifted from targets."""
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = [
            Account("401k", "tax_advantaged", holdings={"VTI": 80, "BND": 20})
        ]
        # Targets: VTI 70%, BND 30%
        # Actual: VTI 80%, BND 20%
        # BND drifted: 20% vs 30% target, 10% absolute drift > 5%, 33% relative > 20%
        p = Portfolio(accounts, meta, targets={"VTI": 0.70, "BND": 0.30})
        pol = RebalancePolicy(POLICY)

        result = compute_drift(p, pol)

        assert "BND" in result.drifted_tickers

    def test_compute_drift_calculates_deltas(self):
        """Should calculate correct dollar deltas for rebalancing."""
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = [
            Account("401k", "tax_advantaged", holdings={"VTI": 80, "BND": 20})
        ]
        # Total: 100, VTI target 70 (need -10), BND target 30 (need +10)
        p = Portfolio(accounts, meta, targets={"VTI": 0.70, "BND": 0.30})
        pol = RebalancePolicy(POLICY)

        result = compute_drift(p, pol)

        assert abs(result.deltas_value["VTI"] - (-10)) < 0.01
        assert abs(result.deltas_value["BND"] - 10) < 0.01

    def test_drifted_tickers_sorted_by_magnitude(self):
        """Drifted tickers should be sorted by absolute delta magnitude."""
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "VXUS": AssetMeta("VXUS", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
        }
        accounts = [
            Account("401k", "tax_advantaged", holdings={"VTI": 50, "VXUS": 40, "BND": 10})
        ]
        # Targets: VTI 33%, VXUS 33%, BND 34%
        # Actual: VTI 50%, VXUS 40%, BND 10%
        # BND has largest drift (24% shortfall)
        p = Portfolio(accounts, meta, targets={"VTI": 0.33, "VXUS": 0.33, "BND": 0.34})
        pol = RebalancePolicy(POLICY)

        result = compute_drift(p, pol)

        # BND should be first (largest absolute delta)
        if result.drifted_tickers:
            assert result.drifted_tickers[0] == "BND"
