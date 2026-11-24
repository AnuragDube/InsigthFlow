"""Domain packs: the data (contracts, rules, SQL models) that make the core domain-specific."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from insightflow.quality.rules import QualityRule

DOMAINS_DIR = Path(__file__).parent


@dataclass(frozen=True)
class DomainPack:
    name: str
    contract_version: str
    column_map: dict[str, str]
    adjustment_codes: list[str]
    adjustment_code_patterns: list[str]
    quality_rules: list[QualityRule]
    models_dir: Path

    @property
    def required_columns(self) -> list[str]:
        return list(self.column_map)


def _yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain_pack(name: str) -> DomainPack:
    if not name.isidentifier():  # pack names are code identifiers, never paths
        raise ValueError(f"invalid domain pack name: {name!r}")
    root = DOMAINS_DIR / name
    contract = _yaml(root / "contract.yaml")
    rules = _yaml(root / "rules.yaml")
    quality = _yaml(root / "quality.yaml") or {}
    return DomainPack(
        name=name,
        contract_version=str(contract["version"]),
        column_map=dict(contract["columns"]),
        adjustment_codes=[str(c).upper() for c in rules["adjustment_codes"]],
        adjustment_code_patterns=list(rules["adjustment_code_patterns"]),
        quality_rules=[QualityRule(**r) for r in quality.get("rules") or []],
        models_dir=root / "models",
    )
