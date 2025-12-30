# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run all tests
pytest -q

# Run a single test file
pytest tests/test_invariants.py -v

# Run a single test
pytest tests/test_invariants.py::TestStabilizerMinimum::test_stabilizer_below_minimum_triggers_warning -v

# Initial portfolio allocation
python -m cli.main init --total 3000000 --explain

# Rebalance existing portfolio
python -m cli.main rebalance --mode strict --explain
python -m cli.main rebalance --mode conservative --explain

# Strategy management
python -m cli.main strategy show
python -m cli.main strategy add --ticker GOOGL --weight 0.02
python -m cli.main strategy remove --ticker TSLA
python -m cli.main strategy rotate --from AAPL --to MSFT --weight 0.01

# Backtest
python -m cli.main backtest --scenario with_bonds
python -m cli.main backtest --scenario with_growth_tilt
```

## Architecture

This is a long-term, tax-aware **core-satellite** investment system with household-level portfolio management.

### Core Concepts

- **Sleeves**: Portfolio divided into "core" (diversified ETFs, 65-75%) and "growth" (Magnificent 7, QQQ, max 30%)
- **Stabilizers**: Bond holdings (BND, BNDX) maintaining minimum 15%
- **Asset Location**: Tax-efficient placement across taxable and tax-advantaged accounts

### Data Flow

1. **Configuration** (`config/`): YAML files define policy rules, account structure, and asset universe
2. **Portfolio Construction** (`cli/main.py:build_portfolio`): Loads config, creates `Portfolio` with `Account` objects and `AssetMeta`
3. **Policy Validation** (`engine/rebalance_engine.py:recommend`):
   - `AllocationPolicy` validates sleeve weights
   - `RiskPolicy` validates stabilizer minimums
   - `GrowthPolicy` validates single-stock concentration and leverage rules
4. **Drift Detection** (`engine/drift_engine.py`): Compares current weights to targets using absolute (5%) and relative (20%) thresholds
5. **Trade Planning** (`engine/trade_planner.py`): Generates trades with tax-aware account selection
6. **Explanation** (`engine/explanation_engine.py`): Attaches human-readable reasons to trades

### Key Engines

- **init_engine.py**: Initial portfolio allocation with asset-location optimization
- **rebalance_engine.py**: Ongoing rebalancing with strict/conservative modes
- **strategy_engine.py**: Growth sleeve add/remove/rotate with policy enforcement
- **drift_engine.py**: Detects which assets have drifted from targets
- **trade_planner.py**: Plans trades respecting taxable-sell-last rule

### Key Policy Invariants

- Core sleeve must stay above `core_min` (65%)
- Growth sleeve must stay below `growth_max` (30%)
- Stabilizer assets must maintain `min_pct_total` (15%)
- Single growth stocks capped at `max_single_stock_weight` (10%)
- Leveraged ETFs prohibited when `prohibit_leveraged: true`
- QQQ/SPYG mutually exclusive when `qqq_or_spyg_exclusive: true`
- Taxable accounts: buy first, sell last to minimize tax events

### Generated Files

- `config/targets.generated.yaml`: Created by strategy commands, overrides base targets
