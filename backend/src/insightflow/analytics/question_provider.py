"""Select a registered metric from question text without granting data or SQL access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Whole-question aliases only. Additional clauses must not be silently ignored.
_ALIASES = {
    "how much did we sell": "gross_revenue",
    "what was our gross revenue": "gross_revenue",
    "how many orders did we have": "orders",
    "how many units did we sell": "units_sold",
    "what was our net revenue": "net_revenue",
    "what was the average order value": "average_order_value",
    "how many active customers did we have": "active_customers",
    "how many new customers did we have": "new_customers",
    "what was the repeat customer rate": "repeat_customer_rate",
    "what was the return rate by value": "return_rate_value",
    "what was the value of returns": "returns_value",
}


@dataclass(frozen=True)
class MetricOption:
    name: str
    label: str
    description: str


class QuestionProvider(Protocol):
    def select_metric(self, question: str, options: tuple[MetricOption, ...]) -> str | None: ...


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split()).removesuffix("?").rstrip()


class OfflineQuestionProvider:
    def select_metric(self, question: str, options: tuple[MetricOption, ...]) -> str | None:
        normalized = _normalize(question)
        alias = _ALIASES.get(normalized)
        for option in options:
            if alias == option.name or normalized in {
                _normalize(option.label),
                option.name.replace("_", " "),
                option.name,
            }:
                return option.name
        return None
