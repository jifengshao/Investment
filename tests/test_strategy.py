"""Tests for strategy engine (growth sleeve operations)."""
from __future__ import annotations

import pytest

from engine.strategy_engine import StrategyEngine, StrategyError
from policy.types import AssetMeta


POLICY = {
    "sleeves": {"growth_max": 0.30},
    "growth": {
        "max_single_stock_weight": 0.10,
        "prohibit_leveraged": True,
        "qqq_or_spyg_exclusive": True,
    },
}


def make_engine(
    targets: dict[str, float] | None = None,
    meta: dict[str, AssetMeta] | None = None,
) -> StrategyEngine:
    """Create a strategy engine for testing."""
    if targets is None:
        # Growth sleeve at 25% (below 30% cap), leaving room for additions
        targets = {
            "VTI": 0.55,
            "BND": 0.20,
            "QQQ": 0.10,
            "AAPL": 0.05,
            "MSFT": 0.05,
            "NVDA": 0.05,
        }
    if meta is None:
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
            "QQQ": AssetMeta("QQQ", "etf", "growth", "high"),
            "AAPL": AssetMeta("AAPL", "stock", "growth", "high"),
            "MSFT": AssetMeta("MSFT", "stock", "growth", "high"),
            "NVDA": AssetMeta("NVDA", "stock", "growth", "high"),
        }
    return StrategyEngine(targets=targets, asset_meta=meta, raw_policy=POLICY)


class TestAddAsset:
    """Tests for adding assets to growth sleeve."""

    def test_add_new_asset(self):
        """Should add new asset to targets."""
        engine = make_engine()

        new_targets, msg = engine.add_asset("GOOGL", weight=0.02)

        assert "GOOGL" in new_targets
        assert new_targets["GOOGL"] == 0.02
        assert "added" in msg.lower() or "updated" in msg.lower()

    def test_add_asset_exceeding_growth_cap_fails(self):
        """Should reject adding asset that would exceed growth cap."""
        # Current growth at exactly 30% (QQQ 15% + AAPL 5% + MSFT 5% + NVDA 5%)
        # Adding any more should exceed 30% cap
        targets = {
            "VTI": 0.50,
            "BND": 0.20,
            "QQQ": 0.15,
            "AAPL": 0.05,
            "MSFT": 0.05,
            "NVDA": 0.05,
        }
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
            "QQQ": AssetMeta("QQQ", "etf", "growth", "high"),
            "AAPL": AssetMeta("AAPL", "stock", "growth", "high"),
            "MSFT": AssetMeta("MSFT", "stock", "growth", "high"),
            "NVDA": AssetMeta("NVDA", "stock", "growth", "high"),
        }
        engine = make_engine(targets=targets, meta=meta)

        with pytest.raises(StrategyError, match="exceed cap"):
            engine.add_asset("GOOGL", weight=0.05)

    def test_add_single_stock_above_max_fails(self):
        """Should reject adding stock above single-stock max."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="single-stock"):
            engine.add_asset("GOOGL", weight=0.15)  # 15% > 10% max

    def test_add_leveraged_etf_fails(self):
        """Should reject adding leveraged ETF."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="leveraged"):
            engine.add_asset("TQQQ", weight=0.02)

    def test_add_spyg_when_qqq_exists_fails(self):
        """Should reject adding SPYG when QQQ already in portfolio."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="QQQ|SPYG"):
            engine.add_asset("SPYG", weight=0.05)


class TestRemoveAsset:
    """Tests for removing assets from growth sleeve."""

    def test_remove_existing_asset(self):
        """Should remove asset from targets."""
        engine = make_engine()

        new_targets, msg = engine.remove_asset("AAPL")

        assert new_targets["AAPL"] == 0.0
        assert "removed" in msg.lower()

    def test_remove_nonexistent_asset_fails(self):
        """Should reject removing asset not in targets."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="not found"):
            engine.remove_asset("GOOGL")

    def test_remove_core_asset_fails(self):
        """Should reject removing core sleeve asset."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="not in growth"):
            engine.remove_asset("VTI")


class TestRotate:
    """Tests for rotating between assets."""

    def test_rotate_between_assets(self):
        """Should transfer weight from one asset to another."""
        engine = make_engine()
        initial_aapl = engine.targets["AAPL"]  # 0.05

        new_targets, msg = engine.rotate("AAPL", "GOOGL", weight=0.02)

        assert new_targets["AAPL"] == initial_aapl - 0.02  # 0.03
        assert new_targets["GOOGL"] == 0.02
        assert "rotated" in msg.lower()

    def test_rotate_more_than_available_fails(self):
        """Should reject rotating more weight than available."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="only has"):
            engine.rotate("AAPL", "GOOGL", weight=0.10)  # AAPL only has 0.05

    def test_rotate_to_leveraged_fails(self):
        """Should reject rotating to leveraged ETF."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="leveraged"):
            engine.rotate("AAPL", "TQQQ", weight=0.02)

    def test_rotate_to_spyg_when_qqq_exists_fails(self):
        """Should reject rotating to SPYG when QQQ exists."""
        engine = make_engine()

        with pytest.raises(StrategyError, match="QQQ|SPYG"):
            engine.rotate("AAPL", "SPYG", weight=0.02)

    def test_rotate_exceeding_single_stock_max_fails(self):
        """Should reject rotation that would exceed single-stock max."""
        # Create engine with QQQ at 15% so we have enough to rotate from
        targets = {
            "VTI": 0.55,
            "BND": 0.15,
            "QQQ": 0.15,  # 15% - can rotate 6% from this
            "AAPL": 0.05,
            "MSFT": 0.05,
            "NVDA": 0.05,
        }
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
            "QQQ": AssetMeta("QQQ", "etf", "growth", "high"),
            "AAPL": AssetMeta("AAPL", "stock", "growth", "high"),
            "MSFT": AssetMeta("MSFT", "stock", "growth", "high"),
            "NVDA": AssetMeta("NVDA", "stock", "growth", "high"),
        }
        engine = make_engine(targets=targets, meta=meta)

        # AAPL at 5%, adding 6% would make 11% > 10% max
        with pytest.raises(StrategyError, match="single-stock"):
            engine.rotate("QQQ", "AAPL", weight=0.06)

    def test_rotate_exactly_to_max_passes(self):
        """Rotation exactly to single-stock max should succeed."""
        targets = {
            "VTI": 0.60,
            "BND": 0.15,
            "AAPL": 0.05,
            "MSFT": 0.10,
            "NVDA": 0.10,
        }
        meta = {
            "VTI": AssetMeta("VTI", "etf", "core", "high"),
            "BND": AssetMeta("BND", "etf", "core", "low", stabilizer=True),
            "AAPL": AssetMeta("AAPL", "stock", "growth", "high"),
            "MSFT": AssetMeta("MSFT", "stock", "growth", "high"),
            "NVDA": AssetMeta("NVDA", "stock", "growth", "high"),
        }
        engine = make_engine(targets=targets, meta=meta)

        # Rotate 5% from MSFT to AAPL -> AAPL becomes exactly 10%
        new_targets, msg = engine.rotate("MSFT", "AAPL", weight=0.05)

        assert new_targets["AAPL"] == 0.10


class TestGrowthWeight:
    """Tests for growth weight calculation."""

    def test_current_growth_weight(self):
        """Should correctly calculate current growth sleeve weight."""
        engine = make_engine()

        weight = engine._current_growth_weight()

        # Default targets: QQQ 10% + AAPL 5% + MSFT 5% + NVDA 5% = 25%
        assert abs(weight - 0.25) < 0.001

    def test_growth_max_from_policy(self):
        """Should read growth max from policy."""
        engine = make_engine()

        assert engine.growth_max == 0.30
