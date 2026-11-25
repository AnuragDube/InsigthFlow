"""Loads metric definitions from a domain pack (trusted configuration, not user input)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import yaml

from insightflow.domains.loader import DOMAINS_DIR

Unit = Literal["GBP", "count", "ratio"]


@dataclass(frozen=True)
class Source:
    name: str
    time_column: str | None = None  # table sources
    query: str | None = None  # virtual sources (range already applied via $start/$end)


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    unit: Unit
    description: str
    kind: Literal["aggregate", "formula"]
    source: Source | None = None
    expression: str = ""
    op: Literal["difference", "ratio"] | None = None
    operands: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = field(default_factory=tuple)


def load_metrics(pack_name: str) -> dict[str, Metric]:
    if not pack_name.isidentifier():
        raise ValueError(f"invalid domain pack name: {pack_name!r}")
    with (DOMAINS_DIR / pack_name / "metrics.yaml").open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    sources = {name: Source(name=name, **spec) for name, spec in doc["sources"].items()}
    metrics: dict[str, Metric] = {}
    for m in doc["metrics"]:
        metric = Metric(
            name=m["name"],
            label=m["label"],
            unit=m["unit"],
            description=m["description"],
            kind=m["kind"],
            source=sources[m["source"]] if "source" in m else None,
            expression=m.get("expression", ""),
            op=m.get("op"),
            operands=tuple(m.get("operands", ())),
            dimensions=tuple(m.get("dimensions", ())),
        )
        metrics[metric.name] = metric
    for metric in metrics.values():  # formulas may only reference earlier-defined metrics
        missing = [o for o in metric.operands if o not in metrics]
        if missing:
            raise ValueError(f"{metric.name}: unknown operands {missing}")
    return metrics
