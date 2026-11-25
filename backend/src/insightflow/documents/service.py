"""Bounded local document storage and extractive search."""

from __future__ import annotations

import re
import uuid
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

import bm25s  # type: ignore[import-untyped]
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import ConflictError, NotFoundError, PayloadTooLarge, ValidationFailed
from insightflow.core.ids import new_id
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import Document, Organization
from insightflow.metadata.repositories import AuditRepo

MAX_DOCUMENT_BYTES = 64 * 1024
MAX_DOCUMENTS = 20
_CHUNK_CHARS = 900
_CHUNK_OVERLAP = 100
_STOP_WORDS = frozenset({
    "a", "am", "an", "and", "are", "as", "at", "be", "been", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "how", "i", "in", "is",
    "it", "me", "of", "on", "or", "our", "should", "that", "the", "their", "this", "to",
    "was", "we", "were", "what", "when", "where", "which", "who", "will", "with", "would", "you",
    "your",
})  # fmt: skip
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class Citation:
    document_id: uuid.UUID
    title: str
    start_line: int
    end_line: int
    excerpt: str


def add_document(ctx: OrgContext, engine: Engine, filename: str, file: BinaryIO) -> Document:
    title = PurePosixPath(filename.replace("\\", "/")).name
    if not title or len(title) > 200 or not title.isprintable():
        raise ValidationFailed("Use a printable filename up to 200 characters.")
    if PurePosixPath(title).suffix.lower() not in {".txt", ".md"}:
        raise ValidationFailed("Upload a UTF-8 .txt or .md document.")
    raw = file.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise PayloadTooLarge("Documents are limited to 64 KiB.")
    try:
        content = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise ValidationFailed("The document must be UTF-8 text.") from exc
    if not content.strip() or any(
        not char.isprintable() and char not in "\n\t" for char in content
    ):
        raise ValidationFailed("The document must contain readable text.")

    with session_scope(engine) as session:
        # Serialize quota checks per organization on both SQLite and PostgreSQL.
        session.execute(
            update(Organization)
            .where(Organization.id == ctx.org_id)
            .values(status=Organization.status)
        )
        count = session.scalar(
            select(func.count()).select_from(Document).where(Document.org_id == ctx.org_id)
        )
        if count is not None and count >= MAX_DOCUMENTS:
            raise ConflictError("This organization has reached its 20-document limit.")
        document = Document(org_id=ctx.org_id, id=new_id(), title=title, content=content)
        session.add(document)
        AuditRepo(session).record(
            ctx, action="document.upload", target_type="document", target_id=document.id
        )
    return document


def list_documents(ctx: OrgContext, engine: Engine) -> list[Document]:
    with session_scope(engine) as session:
        return list(
            session.scalars(
                select(Document)
                .where(Document.org_id == ctx.org_id)
                .order_by(Document.title, Document.id)
            )
        )


def delete_document(ctx: OrgContext, engine: Engine, document_id: uuid.UUID) -> None:
    with session_scope(engine) as session:
        document = session.get(Document, (ctx.org_id, document_id))
        if document is None:
            raise NotFoundError("Document not found.")
        session.delete(document)
        AuditRepo(session).record(
            ctx, action="document.delete", target_type="document", target_id=document_id
        )


def _chunks(document: Document) -> list[Citation]:
    content = document.content
    line_starts = [0, *(match.end() for match in re.finditer("\n", content))]
    result = []
    for start in range(0, len(content), _CHUNK_CHARS - _CHUNK_OVERLAP):
        raw = content[start : start + _CHUNK_CHARS]
        excerpt = raw.strip()
        if excerpt:
            first = start + len(raw) - len(raw.lstrip())
            result.append(
                Citation(
                    document.id,
                    document.title,
                    bisect_right(line_starts, first),
                    bisect_right(line_starts, first + len(excerpt) - 1),
                    excerpt,
                )
            )
        if start + _CHUNK_CHARS >= len(content):
            break
    return result


def _tokens(text: str) -> list[str]:
    return [word for word in _TOKEN.findall(text.casefold()) if word not in _STOP_WORDS]


def search_documents(ctx: OrgContext, engine: Engine, question: str) -> list[Citation]:
    terms = set(_tokens(question))
    if not terms:
        return []
    chunks = [chunk for document in list_documents(ctx, engine) for chunk in _chunks(document)]
    tokens = [_tokens(chunk.excerpt) for chunk in chunks]
    eligible = [
        index
        for index, words in enumerate(tokens)
        if 2 * len(terms.intersection(words)) >= len(terms)
    ]
    if not eligible:
        return []
    indexer = bm25s.BM25()
    indexer.index(tokens, show_progress=False)
    scores = indexer.get_scores(sorted(terms))
    ranked = sorted(eligible, key=lambda index: (-float(scores[index]), index))
    matches: list[Citation] = []
    for index in ranked:
        chunk = chunks[index]
        # Overlapping chunks from a single document are redundant evidence.
        if any(
            found.document_id == chunk.document_id
            and found.start_line <= chunk.end_line
            and chunk.start_line <= found.end_line
            for found in matches
        ):
            continue
        matches.append(chunk)
        if len(matches) == 5:
            break
    return matches
