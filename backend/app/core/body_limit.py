from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Defense-in-depth request size cap. The reverse proxy (Caddy) should enforce this
    too via `request_body { max_size ... }` — this middleware covers the case where the
    app is reached directly (e.g. local dev without Caddy in front).

    Only checks Content-Length, so it doesn't catch a chunked-encoding request with no
    declared length; that's an acceptable gap given the proxy is the primary control.
    """

    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse(
                        status_code=413, content={"detail": "Request body too large"}
                    )
            except ValueError:
                pass
        return await call_next(request)
