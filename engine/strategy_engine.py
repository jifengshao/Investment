"""Strategy engine for growth sleeve operations.

Provides operations to add, remove, and rotate assets in the growth sleeve
while enforcing policy constraints:
- Growth sleeve cap
- Single-stock max weight
- Leveraged ETF prohibition
- QQQ/SPYG exclusivity rule
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from common.config_loader import load_yaml
from policy.types import AssetMeta


class StrategyError(Exception):
    """Error raised when a strategy operation violates policy."""

    pass


# Common leveraged ETFs to prohibit
LEVERAGED_TICKERS = frozenset([
    "TQQQ", "SQQQ", "UPRO", "SPXU", "QLD", "QID",
    "SSO", "SDS", "UDOW", "SDOW", "TNA", "TZA",
    "LABU", "LABD", "SOXL", "SOXS", "FNGU", "FNGD",
])

# Growth ETF exclusivity groups (pick one, not both)
EXCLUSIVITY_GROUPS = [
    frozenset(["QQQ", "SPYG"]),  # QQQ or SPYG, not both
]


@dataclass
class StrategyEngine:
    """Engine for managing growth sleeve strategy operations."""

    targets: Dict[str, float]
    asset_meta: Dict[str, AssetMeta]
    raw_policy: Dict[str, Any]

    @property
    def growth_max(self) -> float:
        """Maximum allowed growth sleeve weight."""
        return float(self.raw_policy.get("sleeves", {}).get("growth_max", 0.30))

    @property
    def max_single_stock(self) -> float:
        """Maximum weight for a single growth stock."""
        return float(self.raw_policy.get("growth", {}).get("max_single_stock_weight", 0.10))

    @property
    def prohibit_leveraged(self) -> bool:
        """Whether leveraged ETFs are prohibited."""
        return bool(self.raw_policy.get("growth", {}).get("prohibit_leveraged", True))

    @property
    def qqq_or_spyg_exclusive(self) -> bool:
        """Whether QQQ and SPYG are mutually exclusive (default: True)."""
        return bool(self.raw_policy.get("growth", {}).get("qqq_or_spyg_exclusive", True))

    def _current_growth_weight(self) -> float:
        """Calculate current total growth sleeve weight."""
        return sum(
            w for t, w in self.targets.items()
            if self.asset_meta.get(t) and self.asset_meta[t].sleeve == "growth"
        )

    def _validate_leveraged(self, ticker: str) -> None:
        """Raise if ticker is a leveraged ETF."""
        if not self.prohibit_leveraged:
            return
        if ticker.upper() in LEVERAGED_TICKERS:
            raise StrategyError(
                f"Cannot add {ticker}: leveraged ETFs are prohibited for long-term holding"
            )

    def _validate_exclusivity(self, ticker: str) -> None:
        """Raise if adding ticker would violate exclusivity rules."""
        if not self.qqq_or_spyg_exclusive:
            return

        ticker_upper = ticker.upper()
        for group in EXCLUSIVITY_GROUPS:
            if ticker_upper in group:
                # Check if any other ticker in this group is already in targets
                for existing in self.targets:
                    if existing.upper() in group and existing.upper() != ticker_upper:
                        if self.targets[existing] > 0:
                            raise StrategyError(
                                f"Cannot add {ticker}: conflicts with {existing} "
                                f"(choose QQQ or SPYG, not both)"
                            )

    def _validate_single_stock_max(self, ticker: str, weight: float) -> None:
        """Raise if weight exceeds single-stock max for stocks."""
        meta = self.asset_meta.get(ticker)
        # Only applies to stocks in growth sleeve
        if meta and meta.asset_type == "stock" and meta.sleeve == "growth":
            if weight > self.max_single_stock:
                raise StrategyError(
                    f"Cannot set {ticker} to {weight:.2%}: "
                    f"exceeds single-stock max {self.max_single_stock:.2%}"
                )
        # Also check if it's a new stock we're adding
        if not meta:
            # Assume new asset is a stock in growth
            if weight > self.max_single_stock:
                raise StrategyError(
                    f"Cannot add {ticker} at {weight:.2%}: "
                    f"exceeds single-stock max {self.max_single_stock:.2%}"
                )

    def _validate_growth_cap(self, new_weight_delta: float) -> None:
        """Raise if adding weight would exceed growth cap."""
        current = self._current_growth_weight()
        new_total = current + new_weight_delta
        if new_total > self.growth_max + 1e-6:
            raise StrategyError(
                f"Cannot add {new_weight_delta:.2%} to growth sleeve: "
                f"would exceed cap ({current:.2%} + {new_weight_delta:.2%} = {new_total:.2%} > {self.growth_max:.2%})"
            )

    def add_asset(
        self,
        ticker: str,
        weight: float,
        asset_type: str = "stock",
        sleeve: str = "growth",
        tax_efficiency: str = "high",
    ) -> Tuple[Dict[str, float], str]:
        """Add a new asset to the growth sleeve.

        Args:
            ticker: Ticker symbol to add.
            weight: Target weight for the new asset.
            asset_type: "stock" or "etf".
            sleeve: Should be "growth" for this operation.
            tax_efficiency: Tax efficiency rating.

        Returns:
            Tuple of (new targets dict, success message).

        Raises:
            StrategyError: If operation violates policy constraints.
        """
        if weight <= 0:
            raise StrategyError(f"Weight must be positive, got {weight}")

        if sleeve != "growth":
            raise StrategyError("add_asset is for growth sleeve only")

        # Validate constraints
        self._validate_leveraged(ticker)
        self._validate_exclusivity(ticker)
        self._validate_single_stock_max(ticker, weight)

        # Check if already exists
        current_weight = self.targets.get(ticker, 0.0)
        weight_delta = weight - current_weight

        self._validate_growth_cap(weight_delta)

        # Update targets
        new_targets = dict(self.targets)
        new_targets[ticker] = weight

        # Update asset_meta if new
        if ticker not in self.asset_meta:
            self.asset_meta[ticker] = AssetMeta(
                ticker=ticker,
                asset_type=asset_type,
                sleeve=sleeve,
                tax_efficiency=tax_efficiency,
                stabilizer=False,
                leveraged=False,
            )

        msg = f"Added {ticker} to growth sleeve at {weight:.2%}"
        if current_weight > 0:
            msg = f"Updated {ticker} from {current_weight:.2%} to {weight:.2%}"

        return new_targets, msg

    def remove_asset(self, ticker: str) -> Tuple[Dict[str, float], str]:
        """Remove an asset from the growth sleeve.

        Args:
            ticker: Ticker symbol to remove.

        Returns:
            Tuple of (new targets dict, success message).

        Raises:
            StrategyError: If ticker not found in growth sleeve.
        """
        if ticker not in self.targets:
            raise StrategyError(f"Ticker {ticker} not found in targets")

        meta = self.asset_meta.get(ticker)
        if meta and meta.sleeve != "growth":
            raise StrategyError(f"Cannot remove {ticker}: not in growth sleeve")

        old_weight = self.targets[ticker]
        new_targets = dict(self.targets)
        new_targets[ticker] = 0.0  # Set to 0 rather than delete to track history

        msg = f"Removed {ticker} from growth sleeve (was {old_weight:.2%})"
        return new_targets, msg

    def rotate(
        self,
        from_ticker: str,
        to_ticker: str,
        weight: float,
    ) -> Tuple[Dict[str, float], str]:
        """Rotate weight from one asset to another in the growth sleeve.

        Args:
            from_ticker: Source ticker to reduce.
            to_ticker: Target ticker to increase.
            weight: Amount of weight to transfer.

        Returns:
            Tuple of (new targets dict, success message).

        Raises:
            StrategyError: If operation violates policy constraints.
        """
        if weight <= 0:
            raise StrategyError(f"Weight must be positive, got {weight}")

        # Validate source
        if from_ticker not in self.targets:
            raise StrategyError(f"Source ticker {from_ticker} not found in targets")

        from_meta = self.asset_meta.get(from_ticker)
        if from_meta and from_meta.sleeve != "growth":
            raise StrategyError(f"Cannot rotate from {from_ticker}: not in growth sleeve")

        current_from = self.targets.get(from_ticker, 0.0)
        if weight > current_from + 1e-6:
            raise StrategyError(
                f"Cannot rotate {weight:.2%} from {from_ticker}: only has {current_from:.2%}"
            )

        # Validate target
        self._validate_leveraged(to_ticker)
        self._validate_exclusivity(to_ticker)

        new_to_weight = self.targets.get(to_ticker, 0.0) + weight
        self._validate_single_stock_max(to_ticker, new_to_weight)

        # Note: No growth cap check needed since we're moving within growth sleeve

        # Update targets
        new_targets = dict(self.targets)
        new_targets[from_ticker] = current_from - weight
        new_targets[to_ticker] = new_to_weight

        # Update asset_meta if new
        if to_ticker not in self.asset_meta:
            self.asset_meta[to_ticker] = AssetMeta(
                ticker=to_ticker,
                asset_type="stock",  # Default to stock
                sleeve="growth",
                tax_efficiency="high",
                stabilizer=False,
                leveraged=False,
            )

        msg = (
            f"Rotated {weight:.2%} from {from_ticker} to {to_ticker} "
            f"({from_ticker}: {current_from:.2%} -> {new_targets[from_ticker]:.2%}, "
            f"{to_ticker}: {self.targets.get(to_ticker, 0.0):.2%} -> {new_to_weight:.2%})"
        )

        return new_targets, msg


def load_current_targets(universe: Dict[str, Any]) -> Dict[str, float]:
    """Load current targets, merging base and generated if available.

    Args:
        universe: Base universe configuration.

    Returns:
        Merged targets dictionary.
    """
    base_targets = {k: float(v) for k, v in (universe.get("targets") or {}).items()}

    # Try loading generated targets
    generated_path = Path("config/targets.generated.yaml")
    if generated_path.exists():
        try:
            generated = load_yaml(generated_path)
            if generated and "targets" in generated:
                for k, v in generated["targets"].items():
                    base_targets[k] = float(v)
        except Exception:
            pass

    return base_targets


def save_generated_targets(targets: Dict[str, float], universe: Dict[str, Any]) -> None:
    """Save generated targets to config/targets.generated.yaml.

    Only saves targets that differ from the base universe.

    Args:
        targets: Full targets dictionary.
        universe: Base universe configuration.
    """
    base_targets = {k: float(v) for k, v in (universe.get("targets") or {}).items()}

    # Find differences
    generated = {}
    all_tickers = set(targets.keys()) | set(base_targets.keys())

    for ticker in all_tickers:
        new_val = targets.get(ticker, 0.0)
        old_val = base_targets.get(ticker, 0.0)

        if abs(new_val - old_val) > 1e-6:
            generated[ticker] = new_val

    # Write generated file
    output = {
        "_comment": "Generated targets - overrides base asset_universe.yaml",
        "targets": generated,
    }

    generated_path = Path("config/targets.generated.yaml")
    with generated_path.open("w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)
