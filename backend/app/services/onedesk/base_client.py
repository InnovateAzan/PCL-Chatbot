from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OneDeskListConfig:
    module: str
    list_id: str
    list_title: str
    user_email_field: str
    request_number_field: str
    status_field: str
    assigned_to_field: str
    updated_field: str
    latest_update_field: str

    @property
    def is_configured(self) -> bool:
        return bool(
            self.list_id
            and self.user_email_field
            and self.request_number_field
            and self.status_field
        )
