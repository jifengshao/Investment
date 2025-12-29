from __future__ import annotations
import argparse
import pandas as pd

from common.config_loader import load_all
from accounts.account import Account
from policy.types import AssetMeta
from portfolio.portfolio import Portfolio
from engine.rebalance_engine import recommend
from engine.explanation_engine import explain_trades
from backtest.simulator import generate_synthetic_prices, compare

def build_portfolio(cfg) -> Portfolio:
    meta = {}
    for t, info in (cfg.universe.get("assets") or {}).items():
        meta[t] = AssetMeta(
            ticker=t,
            asset_type=info.get("asset_type", "etf"),
            sleeve=info.get("sleeve", "core"),
            tax_efficiency=info.get("tax_efficiency", "high"),
            stabilizer=bool(info.get("stabilizer", False)),
            leveraged=bool(info.get("leveraged", False)),
        )

    accounts = []
    for a in (cfg.accounts.get("accounts") or []):
        accounts.append(Account(
            id=a["id"],
            type=a["type"],
            cash=float(a.get("cash", 0.0)),
            holdings={k: float(v) for k, v in (a.get("holdings") or {}).items()},
        ))

    targets = {k: float(v) for k, v in (cfg.universe.get("targets") or {}).items()}
    return Portfolio(accounts=accounts, asset_meta=meta, targets=targets)

def cmd_rebalance(args) -> int:
    cfg = load_all(args.config, args.accounts, args.universe)
    portfolio = build_portfolio(cfg)

    rec = recommend(portfolio, cfg.policy)

    print("Summary")
    for k, v in rec.summary.items():
        print(f"  {k}: {v}")

    if rec.warnings:
        print("\nWarnings")
        for w in rec.warnings:
            print(f"  - {w}")

    if rec.trades:
        print("\nTrades")
        lines = explain_trades(rec.trades) if args.explain else [str(t) for t in rec.trades]
        for line in lines:
            print("  " + line)
    else:
        print("\nNo trades recommended (within drift bands).")
    return 0

def cmd_backtest(args) -> int:
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

    results = compare(prices)
    for r in results:
        if args.scenario and r.scenario != args.scenario:
            continue
        print(f"Scenario: {r.scenario}")
        print(f"  CAGR: {r.cagr:.2%}")
        print(f"  Vol:  {r.vol:.2%}")
        print(f"  MaxDD:{r.max_drawdown:.2%}")
        print(f"  End:  {r.ending_value:,.2f}")
        print()
    return 0

def main():
    p = argparse.ArgumentParser(prog="cli.main", description="Investment system CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config/global_policy.yaml")
    common.add_argument("--accounts", default="config/accounts.yaml")
    common.add_argument("--universe", default="config/asset_universe.yaml")

    rb = sub.add_parser("rebalance", parents=[common])
    rb.add_argument("--explain", action="store_true")
    rb.set_defaults(func=cmd_rebalance)

    bt = sub.add_parser("backtest", parents=[common])
    bt.add_argument("--scenario", choices=["with_bonds", "no_bonds"], default=None)
    bt.add_argument("--prices", default=None)
    bt.set_defaults(func=cmd_backtest)

    args = p.parse_args()
    raise SystemExit(args.func(args))

if __name__ == "__main__":
    main()
