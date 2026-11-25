"""Request-body size limit enforced while the body streams in (raw ASGI middleware).

A FastAPI dependency is too late: the framework parses (and spools to disk) a multipart body
before dependencies run. This middleware rejects a declared oversized Content-Length immediately
and, for chunked bodies, stops reading as soon as the running total passes the limit.
"""

from __future__ import annotations

import json
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SAFE_CID = re.compile(rb"^[A-Za-z0-9-]{1,64}$")


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        limit_mb: int,
        route_limits: dict[tuple[str, str], tuple[int, str]] | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.limit_mb = limit_mb
        self.route_limits = route_limits or {}

    async def _reject(self, scope: Scope, send: Send, detail: str) -> None:
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-correlation-id", b"")
        cid = incoming.decode() if _SAFE_CID.match(incoming) else uuid.uuid4().hex
        body = json.dumps(
            {
                "type": "/errors/payload-too-large",
                "title": "Payload too large",
                "status": 413,
                "detail": detail,
                "correlation_id": cid,
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"x-correlation-id", cid.encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes, detail = self.route_limits.get(
            (scope["method"], scope["path"].rstrip("/")),
            (self.max_bytes, f"Request bodies are limited to {self.limit_mb} MB."),
        )
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_bytes:
            await self._reject(scope, send, detail)
            return

        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:
                # Whatever the app made of the aborted body (400/500), the answer is 413.
                if message["type"] == "http.response.start" and not started:
                    started = True
                    await self._reject(scope, send, detail)
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(scope, send, detail)
