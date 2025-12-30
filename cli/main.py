"""Investment system CLI.

Provides commands for:
- init: Initial portfolio creation
- rebalance: Ongoing portfolio rebalancing
- strategy: Growth sleeve management
- backtest: Portfolio simulation
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

from accounts.account import Account
from backtest.simulator import compare, generate_synthetic_prices
from common.config_loader import load_all, load_yaml
from engine.explanation_engine import explain_trades
from engine.init_engine import InitRecommendation, compute_init_allocation
from engine.rebalance_engine import RebalanceMode, recommend
from policy.types import AssetMeta
from portfolio.portfolio import Portfolio


def build_asset_meta(universe: Dict[str, Any]) -> Dict[str, AssetMeta]:
    """Build asset metadata from universe configuration."""
    meta = {}
    for t, info in (universe.get("assets") or {}).items():
        meta[t] = AssetMeta(
            ticker=t,
            asset_type=info.get("asset_type", "etf"),
            sleeve=info.get("sleeve", "core"),
            tax_efficiency=info.get("tax_efficiency", "high"),
            stabilizer=bool(info.get("stabilizer", False)),
            leveraged=bool(info.get("leveraged", False)),
        )
    return meta


def build_portfolio(cfg) -> Portfolio:
    """Build portfolio from loaded configuration."""
    meta = build_asset_meta(cfg.universe)

    accounts = []
    for a in cfg.accounts.get("accounts") or []:
        accounts.append(
            Account(
                id=a["id"],
                type=a["type"],
                cash=float(a.get("cash", 0.0)),
                holdings={k: float(v) for k, v in (a.get("holdings") or {}).items()},
            )
        )

    targets = {k: float(v) for k, v in (cfg.universe.get("targets") or {}).items()}
    return Portfolio(accounts=accounts, asset_meta=meta, targets=targets)


def build_empty_accounts(cfg) -> List[Account]:
    """Build empty account structures from configuration."""
    accounts = []
    for a in cfg.accounts.get("accounts") or []:
        accounts.append(
            Account(
                id=a["id"],
                type=a["type"],
                cash=0.0,
                holdings={},
            )
        )
    return accounts


def load_targets_with_generated(cfg) -> Dict[str, float]:
    """Load targets, merging generated targets if available."""
    base_targets = {k: float(v) for k, v in (cfg.universe.get("targets") or {}).items()}

    # Try loading generated targets
    try:
        generated = load_yaml("config/targets.generated.yaml")
        if generated and "targets" in generated:
            # Generated targets override base targets
            for k, v in generated["targets"].items():
                base_targets[k] = float(v)
    except FileNotFoundError:
        pass

    return base_targets


def cmd_init(args) -> int:
    """Handle init command: initial portfolio creation."""
    cfg = load_all(args.config, args.accounts, args.universe)

    # Build asset metadata and targets
    asset_meta = build_asset_meta(cfg.universe)
    targets = load_targets_with_generated(cfg)

    # Build empty accounts for allocation
    accounts = build_empty_accounts(cfg)

    # Parse account cash overrides if provided
    account_cash: Optional[Dict[str, float]] = None
    if args.account_cash:
        account_cash = {}
        for item in args.account_cash:
            parts = item.split("=")
            if len(parts) != 2:
                print(f"Error: Invalid --account-cash format: {item}")
                print("Expected format: account_id=amount (e.g., 401k=1000000)")
                return 1
            account_cash[parts[0]] = float(parts[1])

        # Validate total matches
        cash_total = sum(account_cash.values())
        if abs(cash_total - args.total) > 1.0:
            print(f"Error: Account cash total ({cash_total:,.0f}) != --total ({args.total:,.0f})")
            return 1
    else:
        # Default: split proportionally based on account type
        # Tax-advantaged gets more for bonds, taxable for growth
        tax_adv = [a for a in accounts if a.type == "tax_advantaged"]
        taxable = [a for a in accounts if a.type == "taxable"]

        # Calculate rough split based on asset types
        stab_weight = sum(
            targets.get(t, 0.0)
            for t in cfg.policy.get("stabilizer", {}).get("stabilizer_tickers", [])
        )
        low_eff_weight = sum(
            targets.get(t, 0.0)
            for t, meta in asset_meta.items()
            if meta.tax_efficiency == "low" and not meta.stabilizer
        )

        # Tax-advantaged proportion: stabilizers + low-efficiency
        tax_adv_pct = min(0.7, max(0.3, stab_weight + low_eff_weight + 0.1))

        account_cash = {}
        if tax_adv:
            per_tax_adv = (args.total * tax_adv_pct) / len(tax_adv)
            for a in tax_adv:
                account_cash[a.id] = per_tax_adv
        if taxable:
            remaining = args.total - sum(account_cash.values())
            per_taxable = remaining / len(taxable)
            for a in taxable:
                account_cash[a.id] = per_taxable

    # Compute initial allocation
    try:
        rec = compute_init_allocation(
            total_value=args.total,
            targets=targets,
            asset_meta=asset_meta,
            accounts=accounts,
            account_cash=account_cash,
            raw_policy=cfg.policy,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Print results
    print(f"Initial Portfolio Allocation: ${args.total:,.0f}")
    print("=" * 50)

    print("\nAccount Cash Distribution:")
    for acct_id, cash in (account_cash or {}).items():
        print(f"  {acct_id}: ${cash:,.0f}")

    print("\nSummary:")
    for k, v in rec.summary.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: ${vv:,.0f}")
        else:
            print(f"  {k}: {v}")

    if rec.warnings:
        print("\nWarnings:")
        for w in rec.warnings:
            print(f"  - {w}")

    if rec.trades:
        print("\nTrades:")
        if args.explain:
            lines = explain_trades(rec.trades)
        else:
            lines = [f"{t.account_id}: {t.action} ${t.value:,.0f} {t.ticker}" for t in rec.trades]
        for line in lines:
            print("  " + line)
    else:
        print("\nNo trades generated.")

    return 0


def cmd_rebalance(args) -> int:
    """Handle rebalance command: ongoing portfolio rebalancing."""
    cfg = load_all(args.config, args.accounts, args.universe)
    portfolio = build_portfolio(cfg)

    # Parse rebalance mode
    mode = RebalanceMode.STRICT if args.mode == "strict" else RebalanceMode.CONSERVATIVE

    rec = recommend(portfolio, cfg.policy, mode=mode)

    print(f"Rebalance Recommendation (mode: {args.mode})")
    print("=" * 50)

    print("\nSummary:")
    for k, v in rec.summary.items():
        if isinstance(v, (int, float)):
            if k == "total_value":
                print(f"  {k}: ${v:,.0f}")
            elif "weight" in k or "pct" in k:
                print(f"  {k}: {v:.2%}")
            else:
                print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    if rec.warnings:
        print("\nWarnings:")
        for w in rec.warnings:
            print(f"  - {w}")

    if rec.trades:
        print("\nTrades:")
        lines = explain_trades(rec.trades) if args.explain else [str(t) for t in rec.trades]
        for line in lines:
            print("  " + line)
    else:
        print("\nNo trades recommended (within drift bands).")

    return 0


def cmd_strategy(args) -> int:
    """Handle strategy command: growth sleeve management."""
    from engine.strategy_engine import (
        StrategyEngine,
        StrategyError,
        load_current_targets,
        save_generated_targets,
    )

    cfg = load_all(args.config, args.accounts, args.universe)
    asset_meta = build_asset_meta(cfg.universe)

    # Load current targets (base + generated)
    current_targets = load_current_targets(cfg.universe)

    # Create strategy engine
    engine = StrategyEngine(
        targets=current_targets,
        asset_meta=asset_meta,
        raw_policy=cfg.policy,
    )

    try:
        if args.strategy_cmd == "add":
            new_targets, msg = engine.add_asset(
                ticker=args.ticker,
                weight=args.weight,
                asset_type=args.asset_type or "stock",
                sleeve="growth",
                tax_efficiency="high",
            )
        elif args.strategy_cmd == "remove":
            new_targets, msg = engine.remove_asset(args.ticker)
        elif args.strategy_cmd == "rotate":
            new_targets, msg = engine.rotate(
                from_ticker=args.from_ticker,
                to_ticker=args.to_ticker,
                weight=args.weight,
            )
        elif args.strategy_cmd == "show":
            # Show current growth sleeve composition
            growth_assets = [
                (t, w, asset_meta.get(t))
                for t, w in current_targets.items()
                if asset_meta.get(t) and asset_meta[t].sleeve == "growth"
            ]
            print("Growth Sleeve Composition:")
            print("=" * 40)
            total_growth = 0.0
            for ticker, weight, meta in sorted(growth_assets, key=lambda x: -x[1]):
                asset_type = meta.asset_type if meta else "unknown"
                print(f"  {ticker:8} {weight:6.2%}  ({asset_type})")
                total_growth += weight
            print("-" * 40)
            print(f"  {'Total':8} {total_growth:6.2%}")

            # Show policy limits
            growth_max = cfg.policy.get("sleeves", {}).get("growth_max", 0.30)
            print(f"\n  Growth cap: {growth_max:.0%}")
            print(f"  Remaining:  {growth_max - total_growth:.2%}")
            return 0
        else:
            print(f"Unknown strategy command: {args.strategy_cmd}")
            return 1

        # Save generated targets
        save_generated_targets(new_targets, cfg.universe)
        print(msg)
        print("\nUpdated targets saved to config/targets.generated.yaml")

    except StrategyError as e:
        print(f"Strategy error: {e}")
        return 1

    return 0


def cmd_backtest(args) -> int:
    """Handle backtest command: portfolio simulation."""
    cfg = load_all(args.config, args.accounts, args.universe)
    tickers = list((cfg.universe.get("targets") or {}).keys())

    if args.prices:
        df = pd.read_csv(args.prices)
        if "date" not in df.columns:
            raise SystemExit("CSV must contain 'date' column")
        df["date"] = pd.to_datetime(df["date"])
        prices = df.set_index("date").sort_index()
    else:
        prices = generate_synthetic_prices(tickers)

    # Determine scenarios to run
    scenarios_to_run = None
    if args.scenario:
        scenarios_to_run = [args.scenario]

    results = compare(prices, scenarios=scenarios_to_run)

    print("Backtest Results")
    print("=" * 60)

    for r in results:
        print(f"\nScenario: {r.scenario}")
        print("-" * 40)
        print(f"  CAGR:               {r.cagr:>8.2%}")
        print(f"  Annualized Vol:     {r.vol:>8.2%}")
        print(f"  Max Drawdown:       {r.max_drawdown:>8.2%}")
        print(f"  Worst Calendar Year:{r.worst_year_return:>8.2%} ({r.worst_year})")
        print(f"  Recovery Time:      {r.recovery_days:>5} days ({r.recovery_days // 30} months)")
        print(f"  Sharpe Ratio:       {r.sharpe_ratio:>8.2f}")
        print(f"  Ending Value:       ${r.ending_value:>12,.0f}")

    return 0


def main():
    """Main entry point."""
    p = argparse.ArgumentParser(
        prog="cli.main",
        description="Investment system CLI: core-satellite portfolio management",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Common arguments for all commands
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config/global_policy.yaml", help="Policy config file")
    common.add_argument("--accounts", default="config/accounts.yaml", help="Accounts config file")
    common.add_argument("--universe", default="config/asset_universe.yaml", help="Asset universe file")

    # Init command
    init_p = sub.add_parser(
        "init",
        parents=[common],
        help="Initial portfolio creation",
    )
    init_p.add_argument(
        "--total",
        type=float,
        required=True,
        help="Total amount to invest",
    )
    init_p.add_argument(
        "--account-cash",
        nargs="*",
        help="Per-account cash: account_id=amount (e.g., 401k=1000000)",
    )
    init_p.add_argument(
        "--explain",
        action="store_true",
        help="Include explanations for each trade",
    )
    init_p.set_defaults(func=cmd_init)

    # Rebalance command
    rb = sub.add_parser(
        "rebalance",
        parents=[common],
        help="Rebalance existing portfolio",
    )
    rb.add_argument("--explain", action="store_true", help="Include trade explanations")
    rb.add_argument(
        "--mode",
        choices=["strict", "conservative"],
        default="strict",
        help="Rebalance mode: strict (full correction) or conservative (buys-only when possible)",
    )
    rb.set_defaults(func=cmd_rebalance)

    # Strategy command
    strat = sub.add_parser(
        "strategy",
        parents=[common],
        help="Manage growth sleeve strategy",
    )
    strat_sub = strat.add_subparsers(dest="strategy_cmd", required=True)

    # Strategy: show
    strat_show = strat_sub.add_parser("show", help="Show current growth sleeve")

    # Strategy: add
    strat_add = strat_sub.add_parser("add", help="Add asset to growth sleeve")
    strat_add.add_argument("--ticker", required=True, help="Ticker to add")
    strat_add.add_argument("--weight", type=float, required=True, help="Target weight (e.g., 0.02)")
    strat_add.add_argument("--asset-type", choices=["stock", "etf"], default="stock", help="Asset type")

    # Strategy: remove
    strat_remove = strat_sub.add_parser("remove", help="Remove asset from growth sleeve")
    strat_remove.add_argument("--ticker", required=True, help="Ticker to remove")

    # Strategy: rotate
    strat_rotate = strat_sub.add_parser("rotate", help="Rotate between assets")
    strat_rotate.add_argument("--from", dest="from_ticker", required=True, help="Source ticker")
    strat_rotate.add_argument("--to", dest="to_ticker", required=True, help="Target ticker")
    strat_rotate.add_argument("--weight", type=float, required=True, help="Weight to transfer")

    strat.set_defaults(func=cmd_strategy)

    # Backtest command
    bt = sub.add_parser(
        "backtest",
        parents=[common],
        help="Run portfolio backtest",
    )
    bt.add_argument(
        "--scenario",
        choices=["with_bonds", "no_bonds", "with_growth_tilt", "without_growth_tilt"],
        default=None,
        help="Scenario to run (default: all)",
    )
    bt.add_argument("--prices", default=None, help="Path to CSV with historical prices")
    bt.set_defaults(func=cmd_backtest)

    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
