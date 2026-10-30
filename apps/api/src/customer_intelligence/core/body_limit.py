from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _TooLarge(Exception):
    pass


def _too_large(limit: int) -> JSONResponse:
    return JSONResponse(
        {
            "code": "request_too_large",
            "message": f"Request exceeds {limit / 1024 / 1024:.0f} MB.",
        },
        status_code=413,
    )


class BodyLimitMiddleware:
    """Bound request bytes per path, streaming the body instead of buffering it.

    A declared Content-Length over the limit is refused before anything is read; chunked bodies
    are counted as they arrive and stopped as soon as they pass the limit.
    """

    def __init__(self, app: ASGIApp, limit_for: Callable[[str], int]) -> None:
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope["path"])
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await _too_large(limit)(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    {"code": "invalid_content_length", "message": "Invalid content length."},
                    status_code=400,
                )
                await response(scope, receive, send)
                return
        total = 0
        started = False

        async def counted() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise _TooLarge
            return message

        async def tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, tracked)
        except _TooLarge:
            if not started:
                await _too_large(limit)(scope, receive, send)
