from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import yaml

def load_yaml(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

@dataclass(frozen=True)
class LoadedConfig:
    policy: Dict[str, Any]
    accounts: Dict[str, Any]
    universe: Dict[str, Any]

def load_all(
    policy_path: str = "config/global_policy.yaml",
    accounts_path: str = "config/accounts.yaml",
    universe_path: str = "config/asset_universe.yaml",
) -> LoadedConfig:
    return LoadedConfig(
        policy=load_yaml(policy_path),
        accounts=load_yaml(accounts_path),
        universe=load_yaml(universe_path),
    )
