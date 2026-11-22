"""Bound request bodies before multipart parsing can spool unbounded data.

Install using ``app.add_middleware`` so this user middleware sits inside
Starlette's ServerErrorMiddleware. It does not read or buffer a request before
the application requests bytes. Both Content-Length and streamed/chunked bodies
are bounded, including requests rejected later by authentication dependencies.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(Exception):
    """Internal control flow; never expose request data in an error response."""


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int):
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    def limit_for(self, path: str) -> int:
        # The source allowance includes 1 MiB for multipart headers/rights notes.
        # Smaller upload routes and JSON cannot consume the full media allowance.
        if path == "/api/sources":
            return self.max_body_bytes
        if path == '/api/editor/assets':
            return min(self.max_body_bytes, 51 * 1024 * 1024)
        if path.startswith("/api/campaigns/") and path.endswith("/attachments"):
            return min(self.max_body_bytes, 21 * 1024 * 1024)
        if path == "/api/analytics/import-csv":
            return min(self.max_body_bytes, 2 * 1024 * 1024)
        if path.startswith('/api/sources/') and path.endswith('/subtitles'):
            return min(self.max_body_bytes, 3 * 1024 * 1024)
        return min(self.max_body_bytes, 1024 * 1024)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.limit_for(scope.get("path", ""))
        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]

        async def reject(status: int, body: bytes) -> None:
            await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        for value in lengths:
            if not value.isdigit():
                await reject(400, b'{"detail":"Invalid Content-Length."}')
                return
            if int(value) > limit:
                await reject(413, b'{"detail":"Request body exceeds the upload limit."}')
                return

        received = 0
        exceeded = False
        response_started = False
        rejection_sent = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise RequestBodyTooLarge()
            return message

        async def limited_send(message: Message) -> None:
            nonlocal response_started, rejection_sent
            if exceeded:
                # Some applications catch request-read exceptions themselves.
                # Replace their response too, rather than returning a success.
                if not response_started and not rejection_sent:
                    rejection_sent = True
                    await reject(413, b'{"detail":"Request body exceeds the upload limit."}')
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except RequestBodyTooLarge:
            if response_started:
                # A duplex/streaming endpoint has already sent headers. Closing
                # the stream is safer than emitting a second response status.
                raise
            if not rejection_sent:
                await reject(413, b'{"detail":"Request body exceeds the upload limit."}')
