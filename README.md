# Investment System (Long-Term Core–Satellite)

A production-quality, tax-aware **core–satellite** investment system for household-level portfolio management.

## Features

- **Core-Satellite Structure**: Diversified ETFs (core) + growth assets (Magnificent 7, QQQ)
- **Tax-Aware Planning**: Asset location optimization, taxable-sell-last strategy
- **Policy Enforcement**: Stabilizer minimum, growth cap, single-stock limits, leveraged ETF prohibition
- **Multiple Workflows**: Initial allocation, ongoing rebalancing, strategy management
- **Backtesting**: Synthetic and real price data with comprehensive metrics

## Quickstart

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest -q

# Initial portfolio allocation ($3M example)
python -m cli.main init --total 3000000 --explain

# Rebalance existing portfolio
python -m cli.main rebalance --explain

# Run backtest
python -m cli.main backtest --scenario with_bonds
```

## Commands

### Initial Portfolio Creation (`init`)

Creates optimal initial allocation for new investments:

```bash
# Basic usage
python -m cli.main init --total 3000000 --explain

# With per-account cash distribution
python -m cli.main init --total 3000000 \
    --account-cash 401k=1500000 taxable=1500000 \
    --explain
```

Features:
- Asset-location aware: bonds → tax-advantaged, growth → taxable
- Validates targets against policy invariants
- Detailed trade explanations

### Rebalance Portfolio (`rebalance`)

Rebalances existing portfolio to target weights:

```bash
# Strict mode (default): fully corrects drift
python -m cli.main rebalance --mode strict --explain

# Conservative mode: buys-only unless constraints violated
python -m cli.main rebalance --mode conservative --explain
```

Modes:
- **strict**: Generates all trades needed to reach targets
- **conservative**: Only buys; sells only for constraint violations (single-stock overweight, growth cap breach, leveraged ETFs)

### Strategy Management (`strategy`)

Manage growth sleeve composition:

```bash
# Show current growth sleeve
python -m cli.main strategy show

# Add new asset (e.g., 2% weight)
python -m cli.main strategy add --ticker GOOGL --weight 0.02

# Remove asset
python -m cli.main strategy remove --ticker TSLA

# Rotate weight between assets
python -m cli.main strategy rotate --from AAPL --to MSFT --weight 0.01
```

Rules enforced:
- Growth sleeve cap (30%)
- Single-stock max (10%)
- Leveraged ETF prohibition
- QQQ/SPYG exclusivity (choose one, not both)

Changes saved to `config/targets.generated.yaml`.

### Backtest (`backtest`)

Simulate portfolio performance:

```bash
# All scenarios with synthetic data
python -m cli.main backtest

# Specific scenario
python -m cli.main backtest --scenario with_bonds

# With real price data
python -m cli.main backtest --prices data/prices.csv --scenario with_growth_tilt
```

Scenarios:
- `with_bonds`: 80% stocks, 20% bonds
- `no_bonds`: 100% stocks
- `with_growth_tilt`: 70% broad market, 30% growth
- `without_growth_tilt`: 100% broad market

Metrics reported:
- CAGR, annualized volatility, max drawdown
- Worst calendar year return
- Recovery time from max drawdown
- Sharpe ratio

## Configuration

### Policy (`config/global_policy.yaml`)

```yaml
sleeves:
  core_target: 0.75
  core_min: 0.65
  growth_target: 0.25
  growth_max: 0.30

stabilizer:
  min_pct_total: 0.15
  stabilizer_tickers: ["BND", "BNDX"]

growth:
  max_single_stock_weight: 0.10
  prohibit_leveraged: true
  qqq_or_spyg_exclusive: true

rebalance:
  drift_absolute: 0.05
  drift_relative: 0.20

taxable:
  buy_first_sell_last: true
```

### Asset Universe (`config/asset_universe.yaml`)

Defines available assets with metadata:
- `asset_type`: etf/stock
- `sleeve`: core/growth
- `tax_efficiency`: high/medium/low
- `stabilizer`: true/false (for bond-like assets)
- `leveraged`: true/false

### Accounts (`config/accounts.yaml`)

Lists household accounts with type and holdings.

## Example Output

```
$ python -m cli.main rebalance --explain

Rebalance Recommendation (mode: strict)
==================================================

Summary:
  total_value: $3,840,000
  stabilizer_weight: 19.53%
  drifted_assets: ['BND', 'VTI', 'VXUS']
  num_trades: 3
  mode: strict

Warnings:
  - None

Trades:
  401k: BUY $36,000 BND  |  Rebalance buy (asset-location aware)
  taxable: SELL $24,000 VTI  |  Taxable sell (last resort)
  401k: BUY $12,000 VXUS  |  Rebalance buy (asset-location aware)
```

## Project Structure

```
config/              YAML configs (policy, accounts, universe)
common/              Shared helpers (YAML loader)
portfolio/           Portfolio domain models
accounts/            Account-specific behaviors
policy/              Policy modules (risk, allocation, tax, growth)
engine/              Engines (init, drift, rebalance, trade planner, strategy)
backtest/            Simulator & scenario runners
reporting/           Summaries & explainability
cli/                 Command-line interface
tests/               Unit tests
docs/                Documentation
```

## Documentation

- [Implementation Report](docs/IMPLEMENTATION_REPORT.md) - Detailed design decisions and module descriptions

## Disclaimer

For educational/engineering purposes only. Not financial advice.
