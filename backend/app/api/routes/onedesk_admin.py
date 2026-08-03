from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query

from backend.app.security.dependencies import require_authenticated_admin
from backend.app.security.entra_auth import AuthenticatedUser
from backend.app.services.onedesk.schema_discovery_service import (
    OneDeskSchemaDiscoveryService,
)

router = APIRouter(prefix="/admin/onedesk", tags=["admin-onedesk"])


def _access_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


@router.get("/site")
async def get_onedesk_site(
    authorization: str | None = Header(default=None),
    _: AuthenticatedUser = Depends(require_authenticated_admin),
):
    return await OneDeskSchemaDiscoveryService(
        access_token=_access_token(authorization),
    ).site()


@router.get("/lists")
async def list_onedesk_lists(
    authorization: str | None = Header(default=None),
    _: AuthenticatedUser = Depends(require_authenticated_admin),
):
    return await OneDeskSchemaDiscoveryService(
        access_token=_access_token(authorization),
    ).lists()


@router.get("/it-service-desk/schema")
async def get_it_service_desk_schema(
    authorization: str | None = Header(default=None),
    _: AuthenticatedUser = Depends(require_authenticated_admin),
):
    return await OneDeskSchemaDiscoveryService(
        access_token=_access_token(authorization),
    ).it_service_desk_schema()


@router.get("/it-service-desk/sample-items")
async def get_it_service_desk_sample_items(
    top: int = Query(default=5, ge=1, le=25),
    authorization: str | None = Header(default=None),
    _: AuthenticatedUser = Depends(require_authenticated_admin),
):
    return await OneDeskSchemaDiscoveryService(
        access_token=_access_token(authorization),
    ).sample_items(top=top)
