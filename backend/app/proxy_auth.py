from secrets import compare_digest

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class ProxyTokenMiddleware(BaseHTTPMiddleware):
    """Protect API routes when FastAPI is exposed through a public tunnel."""

    def __init__(self, app, *, token: str | None, api_prefix: str) -> None:
        super().__init__(app)
        self.token = token
        self.api_prefix = api_prefix.rstrip("/") + "/"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.token and request.url.path.startswith(self.api_prefix):
            supplied = request.headers.get("X-ArchPilot-Proxy-Token")
            if supplied is None or not compare_digest(supplied, self.token):
                return JSONResponse(
                    {"detail": "Unauthorized frontend proxy"}, status_code=401
                )
        return await call_next(request)
