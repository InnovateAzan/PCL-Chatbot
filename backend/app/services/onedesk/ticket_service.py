from __future__ import annotations

from backend.app.core.config import get_settings
from backend.app.models.schemas import ChatResponse
from backend.app.services.onedesk.base_client import OneDeskListConfig
from backend.app.services.onedesk.graph_client import GraphOneDeskClient
from backend.app.services.onedesk.intent_service import OneDeskIntentService
from backend.app.services.onedesk.response_formatter import OneDeskResponseFormatter


class OneDeskService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.intent_service = OneDeskIntentService()
        self.client = GraphOneDeskClient()
        self.formatter = OneDeskResponseFormatter()

    def should_handle(self, message: str) -> bool:
        intent = self.intent_service.detect(message)
        return intent.module is not None and intent.intent_type not in {
            "POLICY_QUESTION",
            "GENERAL_QUESTION",
            "GREETING",
        }

    async def answer(
        self,
        *,
        message: str,
        user_email: str,
        access_token: str | None = None,
    ) -> ChatResponse:
        intent = self.intent_service.detect(message)
        if not intent.module:
            return ChatResponse(
                answer="This does not look like a OneDesk live-data request.",
                fallback=True,
                provider="onedesk-rules",
            )

        if not self.settings.enable_onedesk_integration:
            return ChatResponse(
                answer=(
                    "OneDesk live-data lookup is not enabled yet. "
                    "Please set ENABLE_ONEDESK_INTEGRATION=true after configuring SharePoint list settings."
                ),
                fallback=True,
                provider="onedesk-disabled",
                responseSource="ONEDESK",
            )

        config = self._config_for(intent.module)
        if not config or not config.is_configured:
            return ChatResponse(
                answer=f"OneDesk {intent.module} configuration is incomplete.",
                fallback=True,
                provider="onedesk-config",
                responseSource="ONEDESK",
            )

        records = await self.client.query_user_records(
            config=config,
            user_email=user_email,
            request_number=intent.request_number,
            access_token=access_token,
        )
        return ChatResponse(
            answer=self.formatter.format_records(
                config=config,
                records=records,
                request_number=intent.request_number,
            ),
            fallback=False,
            provider="onedesk-live",
            responseSource="ONEDESK",
        )

    def _config_for(self, module: str) -> OneDeskListConfig | None:
        prefix = f"onedesk_{module}_"
        return OneDeskListConfig(
            module=module,
            list_id=getattr(self.settings, f"{prefix}list_id", ""),
            list_title=getattr(self.settings, f"{prefix}list_title", ""),
            user_email_field=getattr(self.settings, f"{prefix}user_email_field", ""),
            request_number_field=getattr(self.settings, f"{prefix}ticket_number_field", ""),
            status_field=getattr(self.settings, f"{prefix}status_field", ""),
            assigned_to_field=getattr(self.settings, f"{prefix}assigned_to_field", ""),
            updated_field=getattr(self.settings, f"{prefix}updated_field", ""),
            latest_update_field=getattr(self.settings, f"{prefix}latest_update_field", ""),
        )
