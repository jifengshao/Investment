"""Initial portfolio creation engine.

Computes the initial allocation of cash across accounts to reach target weights,
respecting asset-location heuristics and policy invariants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from accounts.account import Account
from engine.trade_planner import Trade
from policy.allocation_policy import AllocationPolicy, validate_sleeves
from policy.growth_policy import GrowthPolicy, validate_growth_constraints
from policy.risk_policy import RiskPolicy, validate_stabilizer
from policy.types import AssetMeta
from portfolio.portfolio import Portfolio


@dataclass
class InitRecommendation:
    """Result of initial portfolio allocation."""
    trades: List[Trade]
    warnings: List[str]
    summary: Dict[str, Any]


def _select_account_for_buy(
    ticker: str,
    meta: Optional[AssetMeta],
    accounts: List[Account],
    account_remaining: Dict[str, float],
) -> Optional[str]:
    """Select best account for buying an asset based on asset-location rules.

    Asset-location heuristics:
    - Tax-inefficient (bonds, REITs, stabilizers) -> tax-advantaged accounts
    - Stocks/growth sleeve -> taxable accounts when possible
    - High tax-efficiency ETFs -> either, prefer taxable for flexibility

    Args:
        ticker: The ticker to buy.
        meta: Asset metadata, if available.
        accounts: List of accounts.
        account_remaining: Map of account_id -> remaining cash to allocate.

    Returns:
        Account ID with available cash, or None if no cash available.
    """
    # Categorize accounts by type
    tax_adv = [a for a in accounts if a.type == "tax_advantaged"]
    taxable = [a for a in accounts if a.type == "taxable"]

    # Determine preference order based on asset characteristics
    if meta:
        # Tax-inefficient assets (bonds, REITs) prefer tax-advantaged
        if meta.tax_efficiency in ("low", "medium") or meta.stabilizer:
            preferred_order = tax_adv + taxable
        # Growth stocks prefer taxable (for potential step-up basis, LTCG rates)
        elif meta.sleeve == "growth" or meta.asset_type == "stock":
            preferred_order = taxable + tax_adv
        # High-efficiency ETFs - prefer taxable for flexibility
        else:
            preferred_order = taxable + tax_adv
    else:
        # Default: taxable first
        preferred_order = taxable + tax_adv

    # Find first account with available cash
    for acct in preferred_order:
        if account_remaining.get(acct.id, 0.0) > 0:
            return acct.id

    return None


def _allocate_to_accounts(
    total_value: float,
    targets: Dict[str, float],
    asset_meta: Dict[str, AssetMeta],
    accounts: List[Account],
    account_cash: Dict[str, float],
) -> List[Trade]:
    """Allocate cash across accounts to reach target weights.

    Uses a priority-based allocation:
    1. Allocate tax-inefficient assets to tax-advantaged accounts first
    2. Allocate growth/stocks to taxable accounts
    3. Fill remaining capacity with any assets

    Args:
        total_value: Total portfolio value to allocate.
        targets: Target weights per ticker.
        asset_meta: Asset metadata.
        accounts: List of accounts.
        account_cash: Initial cash per account.

    Returns:
        List of Trade objects representing buys.
    """
    trades: List[Trade] = []

    # Track remaining cash per account
    account_remaining = {a.id: account_cash.get(a.id, 0.0) for a in accounts}

    # Calculate target dollar amounts
    target_amounts = {t: w * total_value for t, w in targets.items()}
    remaining_to_allocate = dict(target_amounts)

    # Sort assets by priority: tax-inefficient first, then growth, then core
    def allocation_priority(ticker: str) -> tuple:
        meta = asset_meta.get(ticker)
        if not meta:
            return (3, 0, ticker)
        # Priority: stabilizers first, then low-efficiency, then growth, then high-efficiency
        efficiency_order = {"low": 0, "medium": 1, "high": 2}
        sleeve_order = {"growth": 1, "core": 0}
        return (
            0 if meta.stabilizer else 1,
            efficiency_order.get(meta.tax_efficiency, 2),
            sleeve_order.get(meta.sleeve, 2),
            ticker,
        )

    sorted_tickers = sorted(targets.keys(), key=allocation_priority)

    # First pass: allocate to preferred accounts
    for ticker in sorted_tickers:
        amount = remaining_to_allocate.get(ticker, 0.0)
        if amount <= 0:
            continue

        meta = asset_meta.get(ticker)
        account_id = _select_account_for_buy(ticker, meta, accounts, account_remaining)

        if account_id is None:
            continue

        available = account_remaining[account_id]
        buy_amount = min(amount, available)

        if buy_amount > 0.01:  # Minimum $0.01 trade
            reason = _generate_init_reason(ticker, meta, account_id, accounts)
            trades.append(Trade(
                account_id=account_id,
                ticker=ticker,
                action="BUY",
                value=buy_amount,
                reason=reason,
            ))
            account_remaining[account_id] -= buy_amount
            remaining_to_allocate[ticker] -= buy_amount

    # Second pass: allocate remaining to any account with cash
    for ticker in sorted_tickers:
        amount = remaining_to_allocate.get(ticker, 0.0)
        if amount <= 0.01:
            continue

        # Try any account with remaining cash
        for acct in accounts:
            available = account_remaining.get(acct.id, 0.0)
            if available <= 0:
                continue

            buy_amount = min(amount, available)
            if buy_amount > 0.01:
                meta = asset_meta.get(ticker)
                reason = _generate_init_reason(ticker, meta, acct.id, accounts, fallback=True)
                trades.append(Trade(
                    account_id=acct.id,
                    ticker=ticker,
                    action="BUY",
                    value=buy_amount,
                    reason=reason,
                ))
                account_remaining[acct.id] -= buy_amount
                remaining_to_allocate[ticker] -= buy_amount
                amount = remaining_to_allocate[ticker]

            if amount <= 0.01:
                break

    return trades


def _generate_init_reason(
    ticker: str,
    meta: Optional[AssetMeta],
    account_id: str,
    accounts: List[Account],
    fallback: bool = False,
) -> str:
    """Generate explanation for initial allocation trade."""
    acct = next((a for a in accounts if a.id == account_id), None)
    acct_type = acct.type if acct else "unknown"

    if fallback:
        return f"Initial allocation (overflow to {acct_type})"

    if meta is None:
        return "Initial allocation"

    if meta.stabilizer:
        if acct_type == "tax_advantaged":
            return "Initial allocation: stabilizer in tax-advantaged (tax-efficient)"
        return "Initial allocation: stabilizer"

    if meta.tax_efficiency in ("low", "medium"):
        if acct_type == "tax_advantaged":
            return f"Initial allocation: {meta.tax_efficiency} tax-efficiency asset in tax-advantaged"
        return f"Initial allocation: {meta.tax_efficiency} tax-efficiency asset"

    if meta.sleeve == "growth" or meta.asset_type == "stock":
        if acct_type == "taxable":
            return "Initial allocation: growth asset in taxable (LTCG eligible)"
        return "Initial allocation: growth asset"

    return f"Initial allocation: {meta.sleeve} sleeve asset"


def validate_target_invariants(
    targets: Dict[str, float],
    asset_meta: Dict[str, AssetMeta],
    raw_policy: Dict[str, Any],
) -> List[str]:
    """Validate that target allocation satisfies policy invariants.

    Checks:
    - Stabilizer minimum
    - Growth sleeve cap
    - Single-stock max weight
    - Leveraged ETF prohibition

    Args:
        targets: Target weights per ticker.
        asset_meta: Asset metadata.
        raw_policy: Raw policy configuration.

    Returns:
        List of warning messages for violated invariants.
    """
    warnings: List[str] = []

    # Check stabilizer minimum
    stab_cfg = raw_policy.get("stabilizer", {})
    stab_min = float(stab_cfg.get("min_pct_total", 0.15))
    stab_tickers = stab_cfg.get("stabilizer_tickers", [])
    stab_weight = sum(targets.get(t, 0.0) for t in stab_tickers)
    if stab_weight < stab_min - 1e-6:
        warnings.append(
            f"Target stabilizer weight {stab_weight:.2%} below minimum {stab_min:.2%}"
        )

    # Check growth sleeve cap
    sleeve_cfg = raw_policy.get("sleeves", {})
    growth_max = float(sleeve_cfg.get("growth_max", 0.30))
    growth_weight = sum(
        w for t, w in targets.items()
        if asset_meta.get(t) and asset_meta[t].sleeve == "growth"
    )
    if growth_weight > growth_max + 1e-6:
        warnings.append(
            f"Target growth sleeve {growth_weight:.2%} exceeds cap {growth_max:.2%}"
        )

    # Check single-stock max
    growth_cfg = raw_policy.get("growth", {})
    max_single = float(growth_cfg.get("max_single_stock_weight", 0.10))
    for ticker, weight in targets.items():
        meta = asset_meta.get(ticker)
        if meta and meta.asset_type == "stock" and meta.sleeve == "growth":
            if weight > max_single + 1e-6:
                warnings.append(
                    f"Target weight for {ticker} ({weight:.2%}) exceeds single-stock max ({max_single:.2%})"
                )

    # Check leveraged ETFs
    prohibit_leveraged = growth_cfg.get("prohibit_leveraged", True)
    if prohibit_leveraged:
        for ticker, weight in targets.items():
            meta = asset_meta.get(ticker)
            if meta and meta.leveraged and weight > 0:
                warnings.append(f"Target includes prohibited leveraged ETF: {ticker}")

    return warnings


def compute_init_allocation(
    total_value: float,
    targets: Dict[str, float],
    asset_meta: Dict[str, AssetMeta],
    accounts: List[Account],
    account_cash: Optional[Dict[str, float]],
    raw_policy: Dict[str, Any],
) -> InitRecommendation:
    """Compute initial portfolio allocation.

    Args:
        total_value: Total amount to invest.
        targets: Target weights per ticker (must sum to 1.0).
        asset_meta: Asset metadata.
        accounts: List of accounts.
        account_cash: Cash per account (if None, distributes total_value evenly).
        raw_policy: Raw policy configuration.

    Returns:
        InitRecommendation with trades, warnings, and summary.
    """
    # Validate targets sum to ~1.0
    target_sum = sum(targets.values())
    if abs(target_sum - 1.0) > 0.01:
        raise ValueError(f"Targets must sum to 1.0, got {target_sum:.4f}")

    # Default: distribute cash proportionally to account existing values or evenly
    if account_cash is None:
        # Evenly distribute if no existing holdings
        total_existing = sum(a.total_value() for a in accounts)
        if total_existing > 0:
            account_cash = {
                a.id: total_value * (a.total_value() / total_existing)
                for a in accounts
            }
        else:
            account_cash = {a.id: total_value / len(accounts) for a in accounts}

    # Validate total cash matches total_value (with tolerance)
    cash_sum = sum(account_cash.values())
    if abs(cash_sum - total_value) > 1.0:
        raise ValueError(
            f"Account cash ({cash_sum:,.2f}) must equal total_value ({total_value:,.2f})"
        )

    # Validate invariants against targets before allocating
    warnings = validate_target_invariants(targets, asset_meta, raw_policy)

    # Compute allocation
    trades = _allocate_to_accounts(
        total_value=total_value,
        targets=targets,
        asset_meta=asset_meta,
        accounts=accounts,
        account_cash=account_cash,
    )

    # Compute summary
    allocated_by_account: Dict[str, float] = {}
    allocated_by_ticker: Dict[str, float] = {}
    for t in trades:
        allocated_by_account[t.account_id] = allocated_by_account.get(t.account_id, 0.0) + t.value
        allocated_by_ticker[t.ticker] = allocated_by_ticker.get(t.ticker, 0.0) + t.value

    # Check if we achieved targets
    for ticker, target_weight in targets.items():
        target_amount = target_weight * total_value
        actual_amount = allocated_by_ticker.get(ticker, 0.0)
        if abs(actual_amount - target_amount) > 1.0:
            warnings.append(
                f"Could not fully allocate {ticker}: target ${target_amount:,.0f}, actual ${actual_amount:,.0f}"
            )

    summary = {
        "total_value": total_value,
        "num_trades": len(trades),
        "allocated_by_account": allocated_by_account,
        "allocated_by_ticker": allocated_by_ticker,
    }

    return InitRecommendation(trades=trades, warnings=warnings, summary=summary)
