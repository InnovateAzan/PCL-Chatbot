from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


class OneDeskApiError(Exception):
    pass


class OneDeskApiClient:
    def __init__(self) -> None:
        self.settings = get_settings()

        self.base_url = (
            self.settings.onedesk_api_base_url or ""
        ).rstrip("/")

        self.api_token = (
            self.settings.onedesk_api_token or ""
        ).strip()

    def _ensure_configured(self) -> None:
        if not self.settings.enable_onedesk_database_api:
            raise OneDeskApiError(
                "OneDesk database API is disabled."
            )

        if not self.base_url:
            raise OneDeskApiError(
                "ONEDESK_API_BASE_URL is not configured."
            )

        if not self.api_token:
            raise OneDeskApiError(
                "ONEDESK_API_TOKEN is not configured."
            )

    def _headers(self) -> dict[str, str]:
        self._ensure_configured()

        return {
            "X-Api-Token": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_log_error(event: str, **payload: Any) -> None:
        redacted = {
            key: value
            for key, value in payload.items()
            if key != "token"
        }
        logger.warning("OneDesk API %s: %s", event, redacted)

    async def get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    url,
                    headers=self._headers(),
                    params=params,
                )

                response.raise_for_status()

                if not response.content:
                    return None

                return response.json()

        except httpx.HTTPStatusError as exc:
            self._safe_log_error(
                "request_failed",
                method="GET",
                endpoint=endpoint,
                status_code=exc.response.status_code,
            )
            raise OneDeskApiError(
                f"OneDesk API returned HTTP "
                f"{exc.response.status_code}."
            ) from exc

        except httpx.RequestError as exc:
            self._safe_log_error(
                "request_failed",
                method="GET",
                endpoint=endpoint,
                error=str(exc),
            )
            raise OneDeskApiError(
                "Could not connect to OneDesk API."
            ) from exc

    async def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                )

                response.raise_for_status()

                if not response.content:
                    return None

                return response.json()

        except httpx.HTTPStatusError as exc:
            self._safe_log_error(
                "request_failed",
                method="POST",
                endpoint=endpoint,
                status_code=exc.response.status_code,
            )
            raise OneDeskApiError(
                f"OneDesk API returned HTTP "
                f"{exc.response.status_code}."
            ) from exc

        except httpx.RequestError as exc:
            self._safe_log_error(
                "request_failed",
                method="POST",
                endpoint=endpoint,
                error=str(exc),
            )
            raise OneDeskApiError(
                "Could not connect to OneDesk API."
            ) from exc

    # --------------------------------------------------
    # USERS
    # --------------------------------------------------

    async def get_user_by_email(
        self,
        email: str,
    ) -> dict[str, Any] | None:
        result = await self.get(
            "users",
            params={"email": email},
        )

        if isinstance(result, list):
            return result[0] if result else None

        if isinstance(result, dict):
            return result

        return None

    async def save_user(
        self,
        *,
        email: str,
        entra_object_id: str | None = None,
        display_name: str | None = None,
        department: str | None = None,
        job_title: str | None = None,
    ) -> dict[str, Any]:
        existing = await self.get_user_by_email(email)
        if existing:
            return existing
        return await self.create_user(
            email=email,
            entra_object_id=entra_object_id,
            display_name=display_name,
            department=department,
            job_title=job_title,
        )

    async def create_user(
        self,
        *,
        email: str,
        entra_object_id: str | None = None,
        display_name: str | None = None,
        department: str | None = None,
        job_title: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "entraObjectId": entra_object_id,
            "displayName": display_name,
            "email": email,
            "department": department,
            "jobTitle": job_title,
            "isActive": True,
        }

        return await self.post(
            "users",
            payload,
        )

    async def get_or_create_user(
        self,
        *,
        email: str,
        entra_object_id: str | None = None,
        display_name: str | None = None,
        department: str | None = None,
        job_title: str | None = None,
    ) -> dict[str, Any]:
        existing = await self.get_user_by_email(email)

        if existing:
            return existing

        return await self.create_user(
            email=email,
            entra_object_id=entra_object_id,
            display_name=display_name,
            department=department,
            job_title=job_title,
        )

    # --------------------------------------------------
    # CHAT SESSIONS
    # --------------------------------------------------

    async def create_chat_session(
        self,
        *,
        user_id: int | None,
        title: str | None = None,
    ) -> dict[str, Any]:
        return await self.post(
            "chatsessions",
            {
                "userId": user_id,
                "title": title,
                "status": "active",
            },
        )

    async def get_user_sessions(
        self,
        user_id: int,
    ) -> list[dict[str, Any]]:
        result = await self.get(
            "chatsessions",
            params={"userId": user_id},
        )

        return result if isinstance(result, list) else []

    async def create_or_get_chat_session(
        self,
        *,
        user_id: int | None,
        title: str | None = None,
        session_uuid: str | None = None,
    ) -> dict[str, Any]:
        sessions = await self.get_user_sessions(user_id or 0) if user_id is not None else []
        if session_uuid:
            for session in sessions:
                if str(session.get("sessionUuid") or session.get("session_uuid") or "") == str(session_uuid):
                    return session
        return await self.create_chat_session(user_id=user_id, title=title)

    # --------------------------------------------------
    # CHAT MESSAGES
    # --------------------------------------------------

    async def create_chat_message(
        self,
        *,
        session_id: int,
        role: str,
        message_text: str,
        user_id: int | None = None,
        response_time_ms: int | None = None,
        is_answered: bool = True,
    ) -> dict[str, Any]:
        return await self.post(
            "chatmessages",
            {
                "sessionId": session_id,
                "userId": user_id,
                "role": role,
                "messageText": message_text,
                "responseTimeMs": response_time_ms,
                "isAnswered": is_answered,
            },
        )

    async def get_session_messages(
        self,
        session_id: int,
    ) -> list[dict[str, Any]]:
        result = await self.get(
            "chatmessages",
            params={"sessionId": session_id},
        )

        return result if isinstance(result, list) else []

    async def save_chat_turn(
        self,
        *,
        user: dict[str, Any],
        session_uuid: str | None,
        title: str | None,
        question: str,
        answer: str,
        response_time_ms: int,
        is_answered: bool = True,
    ) -> dict[str, Any]:
        user_id = user.get("id")
        session = await self.create_or_get_chat_session(
            user_id=user_id,
            title=title,
            session_uuid=session_uuid,
        )
        session_id = session.get("id")
        if session_id is None:
            raise OneDeskApiError("OneDesk API did not return a session id.")

        user_message = await self.create_chat_message(
            session_id=int(session_id),
            user_id=user_id,
            role="user",
            message_text=question,
            is_answered=is_answered,
        )
        assistant_message = await self.create_chat_message(
            session_id=int(session_id),
            user_id=None,
            role="assistant",
            message_text=answer,
            response_time_ms=response_time_ms,
            is_answered=is_answered,
        )
        return {
            "session": session,
            "user_message": user_message,
            "assistant_message": assistant_message,
        }

    async def list_chat_sessions_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return await self.get_user_sessions(user_id)

    # --------------------------------------------------
    # FEEDBACK
    # --------------------------------------------------

    async def create_feedback(
        self,
        *,
        message_id: int,
        rating: str,
        user_id: int | None = None,
        comments: str | None = None,
    ) -> dict[str, Any]:
        return await self.post(
            "feedback",
            {
                "messageId": message_id,
                "userId": user_id,
                "rating": rating,
                "comments": comments,
            },
        )

    # --------------------------------------------------
    # MESSAGE SOURCES
    # --------------------------------------------------

    async def create_message_source(
        self,
        *,
        message_id: int,
        document_name: str | None = None,
        document_path: str | None = None,
        page_number: int | None = None,
        section_name: str | None = None,
        chunk_id: str | None = None,
        similarity_score: float | None = None,
        source_text: str | None = None,
    ) -> dict[str, Any]:
        return await self.post(
            "messagesources",
            {
                "messageId": message_id,
                "documentName": document_name,
                "documentPath": document_path,
                "pageNumber": page_number,
                "sectionName": section_name,
                "chunkId": chunk_id,
                "similarityScore": similarity_score,
                "sourceText": source_text,
            },
        )

    # --------------------------------------------------
    # UNANSWERED QUESTIONS
    # --------------------------------------------------

    async def create_unanswered_question(
        self,
        *,
        question: str,
        user_id: int | None = None,
        session_id: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await self.post(
            "unansweredquestions",
            {
                "userId": user_id,
                "sessionId": session_id,
                "question": question,
                "reason": reason,
                "status": "new",
            },
        )
