from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Op = Literal["<=", ">=", "=="]


@dataclass(frozen=True)
class QualityRule:
    """A declarative check: ``sql`` returns one number, compared to ``threshold`` with ``op``."""

    id: str
    stage: Literal["silver", "gold"]
    severity: Literal["blocking", "warning"]
    sql: str
    op: Op
    threshold: float
    description: str
