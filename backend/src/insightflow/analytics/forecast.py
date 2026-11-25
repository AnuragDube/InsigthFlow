"""Deterministic weekly forecasts and rolling-origin evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

from insightflow.core.errors import ValidationFailed

WEEK = 7
TRAINING_DAYS = WEEK * 4
MAX_FOLDS = 4
MAX_HISTORY = TRAINING_DAYS + MAX_FOLDS * WEEK


@dataclass(frozen=True)
class ForecastPoint:
    date: date
    seasonal_naive: float
    weekday_average: float


@dataclass(frozen=True)
class Backtest:
    folds: int
    days_evaluated: int
    seasonal_naive_mae: float
    weekday_average_mae: float


def _predict(history: list[float]) -> tuple[list[float], list[float]]:
    return (
        history[-WEEK:],
        [mean(history[-TRAINING_DAYS + day :: WEEK]) for day in range(WEEK)],
    )


def forecast_week(history: list[float], as_of: date) -> tuple[list[ForecastPoint], Backtest]:
    if len(history) < TRAINING_DAYS + WEEK:
        raise ValidationFailed("Forecasting requires at least 35 calendar days of sales history.")
    if (date.max - as_of).days < WEEK:
        raise ValidationFailed("The published date range leaves no room for a seven-day forecast.")

    folds = min(MAX_FOLDS, (len(history) - TRAINING_DAYS) // WEEK)
    naive_errors: list[float] = []
    average_errors: list[float] = []
    for origin in range(len(history) - folds * WEEK, len(history), WEEK):
        naive, average = _predict(history[:origin])
        for observed, baseline, candidate in zip(
            history[origin : origin + WEEK], naive, average, strict=True
        ):
            naive_errors.append(abs(observed - baseline))
            average_errors.append(abs(observed - candidate))

    naive, average = _predict(history)
    return (
        [
            ForecastPoint(as_of + timedelta(days=day), baseline, candidate)
            for day, (baseline, candidate) in enumerate(zip(naive, average, strict=True), start=1)
        ],
        Backtest(folds, len(naive_errors), mean(naive_errors), mean(average_errors)),
    )
