from __future__ import annotations

from typing import Awaitable, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError
from backend.app.security.dependencies import get_authenticated_user
from backend.app.security.entra_auth import AuthenticatedUser
from backend.app.services.onedesk.it_ticket_service import (
    ItTicketConfigurationError,
    ItTicketPermissionError,
    ItTicketService,
    ItTicketTemporaryError,
)

router = APIRouter(prefix="/onedesk/it/tickets", tags=["onedesk-it"])
T = TypeVar("T")


@router.get("")
async def list_tickets(
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    return {"items": await _run(_service(authorization).get_user_tickets(current_user))}


@router.get("/open")
async def list_open_tickets(
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    return {"items": await _run(_service(authorization).get_open_tickets(current_user))}


@router.get("/closed")
async def list_closed_tickets(
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    return {"items": await _run(_service(authorization).get_closed_tickets(current_user))}


@router.get("/latest")
async def latest_ticket(
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    ticket = await _run(_service(authorization).get_latest_ticket(current_user))
    if not ticket:
        return {"item": None, "message": "No IT Service Desk tickets were found for your account."}
    return {"item": ticket}


@router.get("/summary")
async def ticket_summary(
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    return await _run(_service(authorization).get_ticket_summary(current_user))


@router.get("/status/{ticket_status}")
async def tickets_by_status(
    ticket_status: str,
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    return {
        "items": await _run(
            _service(authorization).get_tickets_by_status(
                current_user,
                ticket_status,
            )
        )
    }


@router.get("/serial/{serial_number}")
async def ticket_by_serial_number(
    serial_number: int,
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
):
    ticket = await _run(
        _service(authorization).get_ticket_by_serial_number(
            current_user,
            serial_number,
        )
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket #{serial_number} was not found in your account.",
        )
    return {"item": ticket}


def _service(authorization: str | None) -> ItTicketService:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    return ItTicketService(access_token=token)


async def _run(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except ItTicketPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your Microsoft session is invalid or expired.",
        ) from exc
    except (ItTicketConfigurationError, GraphConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The IT Service Desk integration is not fully configured.",
        ) from exc
    except ItTicketTemporaryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live ticket information is temporarily unavailable.",
        ) from exc
