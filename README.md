# Investment System (Long-Term Core–Satellite)

This repository scaffolds a long-term, tax-aware **core–satellite** investment system:
- **Core**: diversified ETFs + strict rebalancing & stabilizer minimum
- **Growth sleeve**: Magnificent 7 + QQQ + emerging tech (capped, looser rules)
- **Household-level** management across **taxable** and **tax-advantaged** accounts
- **Explainable** recommendations (every trade has a reason)

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m cli.main rebalance --explain
python -m cli.main backtest --scenario with_bonds
pytest -q
```

## Layout

```text
config/                 YAML configs (policy, accounts, universe)
data/                   optional local data (prices, transactions)
common/                 shared helpers (YAML loader)
portfolio/              portfolio domain models
accounts/               account-specific behaviors (taxable vs tax-advantaged)
policy/                 policy modules (risk, allocation, rebalance, tax, growth)
engine/                 engines (drift, rebalance, trade planner, explanations)
backtest/               simulator & scenario runners
reporting/              summaries & explainability reports
cli/                    command-line entrypoints
tests/                  unit tests for invariants and smoke tests
```

## Disclaimer
For educational/engineering purposes only. Not financial advice.
