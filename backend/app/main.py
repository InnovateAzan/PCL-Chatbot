from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.chat import (
    get_chatbot,
    router as chat_router,
)
from backend.app.api.routes.policies import router as policies_router
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


@app.get(f"{settings.api_prefix}/health")
def health_check() -> dict[str, str | bool]:
    payload: dict[str, str | bool] = {
        "status": "ok",
        "environment": settings.environment,
        "mode": "starter-scaffold",
    }
    payload.update(get_chatbot().health_snapshot())
    return payload


app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(policies_router, prefix=settings.api_prefix)
