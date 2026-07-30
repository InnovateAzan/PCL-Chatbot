from fastapi import APIRouter
from sqlalchemy import text

from backend.app.api.routes.chat import get_chatbot
from backend.app.core.config import get_settings
from backend.app.core.database import AsyncSessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    payload = {
        "status": "ok",
        "details": {
            "databaseConfigured": AsyncSessionLocal is not None,
        },
    }
    payload["details"].update(get_chatbot().health_snapshot())
    return payload


@router.get("/health/database")
async def database_health() -> dict:
    if AsyncSessionLocal is None:
        return {"status": "not_configured"}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


@router.get("/health/retriever")
async def retriever_health() -> dict:
    snapshot = get_chatbot().health_snapshot()
    return {
        "status": "ok" if snapshot.get("retriever_ready") else "not_loaded",
        "details": snapshot,
    }


@router.get("/health/onedesk")
async def onedesk_health() -> dict:
    settings = get_settings()
    configured = bool(
        settings.sharepoint_site_id
        and (
            settings.onedesk_it_list_id
            or settings.onedesk_qc_list_id
            or settings.onedesk_fleet_list_id
            or settings.onedesk_facilities_list_id
            or settings.onedesk_approvals_list_id
        )
    )
    return {
        "status": (
            "ok"
            if settings.enable_onedesk_integration and configured
            else "disabled_or_not_configured"
        ),
        "details": {
            "enabled": settings.enable_onedesk_integration,
            "configured": configured,
        },
    }
