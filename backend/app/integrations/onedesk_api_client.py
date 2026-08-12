from __future__ import annotations

from typing import Any

import httpx

from backend.app.core.config import get_settings


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

    async def get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
            ) as client:
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
            raise OneDeskApiError(
                f"OneDesk API returned HTTP "
                f"{exc.response.status_code}."
            ) from exc

        except httpx.RequestError as exc:
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
            async with httpx.AsyncClient(
                timeout=20.0,
            ) as client:
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
            raise OneDeskApiError(
                f"OneDesk API returned HTTP "
                f"{exc.response.status_code}."
            ) from exc

        except httpx.RequestError as exc:
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