"""ASGI request-size guard that also covers chunked transfer bodies."""
from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject HTTP request bodies larger than ``max_body_size`` bytes.

    A Content-Length precheck handles normal requests cheaply. The wrapped
    ``receive`` callable counts actual chunks as well, so omitting or spoofing
    Content-Length cannot bypass the limit.
    """

    def __init__(self, app: ASGIApp, *, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max(int(max_body_size), 1)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                await self._respond(send, 400, "invalid_content_length")
                return
            if content_length < 0:
                await self._respond(send, 400, "invalid_content_length")
                return
            if content_length > self.max_body_size:
                await self._respond(send, 413, "request_too_large")
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await self._respond(send, 413, "request_too_large")

    @staticmethod
    async def _respond(send: Send, status_code: int, code: str) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": {"code": code}},
        )

        async def empty_receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        await response({"type": "http"}, empty_receive, send)
