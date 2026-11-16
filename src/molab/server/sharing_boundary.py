"""Proxy authentication, same-origin mutations, and bounded sharing bodies."""

from __future__ import annotations

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from molab.ids import generate_uuid7
from molab.sharing.settings import ProxySettings
from molab.sharing.store import audit_request_id

MAX_SHARING_BODY = 2 * 1024 * 1024


class SharingBoundary:
    def __init__(
        self, app: ASGIApp, *, settings: ProxySettings, worker_subject: str | None = None
    ) -> None:
        self.app = app
        self.settings = settings
        self.worker_subject = worker_subject

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        request = HTTPConnection(scope)
        websocket = scope["type"] == "websocket"
        path = request.url.path
        browser_api = (
            path.startswith("/api/")
            if self.worker_subject is not None
            else path.startswith("/api/sharing/")
        )
        browser_api = browser_api or websocket
        error: str | None = None
        status = 401
        if browser_api:
            subject = request.headers.get("x-molab-subject")
            if not self.settings.accepts(request.headers.get("x-molab-proxy-key")) or not subject:
                error = "Trusted authentication required"
            elif self.worker_subject is not None and subject != self.worker_subject:
                error, status = "Workspace owner required", 403
            else:
                request.state.sharing_subject = subject
                origin = request.headers.get("origin")
                expected_origin = str(self.settings.public_origin).rstrip("/")
                needs_origin = websocket or scope.get("method") not in {"GET", "HEAD", "OPTIONS"}
                if (
                    (origin is not None and origin != expected_origin)
                    or (needs_origin and origin is None)
                    or request.headers.get("sec-fetch-site") in {"same-site", "cross-site"}
                ):
                    error, status = "Same-origin request required", 403
        if error:
            if websocket:
                await send({"type": "websocket.close", "code": 1008, "reason": error})
                return
            await JSONResponse(
                {"detail": error}, status_code=status, headers={"Cache-Control": "no-store"}
            )(scope, receive, send)
            return
        if websocket:
            await self.app(scope, receive, send)
            return
        if not path.startswith(("/api/sharing/", "/internal/sharing/")):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_SHARING_BODY:
                await JSONResponse({"detail": "Sharing request exceeds 2 MiB"}, status_code=413)(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break
        delivered = False
        request_id = generate_uuid7()

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                message = {
                    **message,
                    "headers": [
                        *headers,
                        (b"cache-control", b"no-store"),
                        (b"x-request-id", request_id.encode()),
                    ],
                }
            await send(message)

        context = audit_request_id.set(request_id)
        try:
            await self.app(scope, replay, no_store)
        finally:
            audit_request_id.reset(context)
