import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.admin import router as admin_router
from backend.app.api.routes.chat import router as chat_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.messages import router as messages_router
from backend.app.api.routes.onedesk_admin import router as onedesk_admin_router
from backend.app.api.routes.policies import router as policies_router
from backend.app.api.routes.users import router as users_router
from backend.app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Starter API for a policy-aware IT chatbot.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

request_buckets: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    content_length = int(request.headers.get("content-length") or 0)
    if content_length > settings.request_max_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body is too large."},
        )

    client_host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = request_buckets[client_host]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= settings.rate_limit_per_minute:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded."},
        )
    bucket.append(now)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(policies_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(messages_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(onedesk_admin_router, prefix=settings.api_prefix)
app.include_router(health_router, prefix=settings.api_prefix)
