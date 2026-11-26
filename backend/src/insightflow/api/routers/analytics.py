from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from insightflow.analytics import service
from insightflow.analytics.question_provider import QuestionProvider
from insightflow.analytics.registry import load_metrics
from insightflow.api.deps import (
    get_engine,
    get_org_context,
    get_question_provider,
    get_settings_dep,
)
from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["analytics"])

Ctx = Annotated[OrgContext, Depends(get_org_context)]
Eng = Annotated[Engine, Depends(get_engine)]
Cfg = Annotated[Settings, Depends(get_settings_dep)]
From = Annotated[date | None, Query(alias="from")]
To = Annotated[date | None, Query(alias="to")]
Provider = Annotated[QuestionProvider | None, Depends(get_question_provider)]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=240)
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")


@router.post("/datasets/{dataset_id}/questions")
def ask_question(
    dataset_id: uuid.UUID,
    body: QuestionRequest,
    ctx: Ctx,
    engine: Eng,
    settings: Cfg,
    provider: Provider,
) -> dict[str, Any]:
    return service.answer_question(
        ctx,
        engine,
        settings,
        dataset_id,
        body.question,
        body.from_date,
        body.to_date,
        provider=provider,
    )


@router.get("/metrics")
def metric_catalog() -> dict[str, list[dict[str, Any]]]:
    return {
        "items": [
            {
                "name": m.name,
                "label": m.label,
                "unit": m.unit,
                "description": m.description,
                "dimensions": list(m.dimensions),
            }
            for m in load_metrics("ecommerce").values()
        ]
    }


@router.get("/datasets/{dataset_id}/dashboard")
def dashboard(
    dataset_id: uuid.UUID, ctx: Ctx, engine: Eng, settings: Cfg, start: From = None, end: To = None
) -> dict[str, Any]:
    return service.dashboard(ctx, engine, settings, dataset_id, start, end)


@router.get("/datasets/{dataset_id}/metrics/{name}/series")
def metric_series(
    dataset_id: uuid.UUID,
    name: str,
    ctx: Ctx,
    engine: Eng,
    settings: Cfg,
    start: From = None,
    end: To = None,
    grain: Literal["day", "month"] = "month",
) -> dict[str, Any]:
    return service.series(ctx, engine, settings, dataset_id, name, start, end, grain)


@router.get("/datasets/{dataset_id}/metrics/{name}/breakdown")
def metric_breakdown(
    dataset_id: uuid.UUID,
    name: str,
    dimension: Literal["country", "product"],
    ctx: Ctx,
    engine: Eng,
    settings: Cfg,
    start: From = None,
    end: To = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    return service.breakdown(ctx, engine, settings, dataset_id, name, dimension, start, end, limit)


@router.get("/datasets/{dataset_id}/forecast")
def sales_forecast(dataset_id: uuid.UUID, ctx: Ctx, engine: Eng, settings: Cfg) -> dict[str, Any]:
    return service.sales_forecast(ctx, engine, settings, dataset_id)


@router.get("/datasets/{dataset_id}/customer-segments")
def customer_segments(
    dataset_id: uuid.UUID, ctx: Ctx, engine: Eng, settings: Cfg
) -> dict[str, Any]:
    return service.customer_segments(ctx, engine, settings, dataset_id)


@router.get("/datasets/{dataset_id}/inactivity-backtest")
def inactivity_backtest(
    dataset_id: uuid.UUID, ctx: Ctx, engine: Eng, settings: Cfg
) -> dict[str, Any]:
    return service.inactivity_backtest(ctx, engine, settings, dataset_id)
