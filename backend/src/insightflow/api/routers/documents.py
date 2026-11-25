from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from insightflow.api.deps import get_engine, get_org_context
from insightflow.core.context import OrgContext
from insightflow.documents import service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
Ctx = Annotated[OrgContext, Depends(get_org_context)]
Eng = Annotated[Engine, Depends(get_engine)]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=240)


@router.get("")
def list_documents(ctx: Ctx, engine: Eng) -> list[DocumentOut]:
    return [DocumentOut.model_validate(doc) for doc in service.list_documents(ctx, engine)]


@router.post("", status_code=201)
def upload_document(ctx: Ctx, engine: Eng, file: Annotated[UploadFile, File()]) -> DocumentOut:
    return DocumentOut.model_validate(
        service.add_document(ctx, engine, file.filename or "", file.file)
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, ctx: Ctx, engine: Eng) -> None:
    service.delete_document(ctx, engine, document_id)


@router.post("/search")
def search_documents(body: SearchRequest, ctx: Ctx, engine: Eng) -> list[service.Citation]:
    return service.search_documents(ctx, engine, body.question)
