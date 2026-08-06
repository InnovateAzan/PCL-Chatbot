from functools import lru_cache
import json
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "OneAssist"
    environment: str = "development"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    frontend_origins: str = ""
    frontend_origin: str = "http://127.0.0.1:5500"
    sharepoint_origin: str = "https://pakistancable.sharepoint.com"
    additional_allowed_origins: str = ""
    temporary_tunnel_url: str = ""
    public_api_base_url: str = ""
    database_url: str = ""
    db_pool_size: int = 5
    db_max_overflow: int = 10
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_api_audience: str = ""
    azure_authority: str = ""
    azure_obo_scopes: str = "https://graph.microsoft.com/User.Read https://graph.microsoft.com/Sites.Read.All"
    azure_admin_role: str = "ADMIN"
    azure_user_role: str = "USER"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    onedesk_site_url: str = "https://pakistancable.sharepoint.com/sites/ITHelpDesk2"
    onedesk_site_id: str = ""
    it_service_desk_list_id: str = ""
    it_service_desk_list_title: str = "Issue tracker"
    onedesk_it_field_mapping_json: str = ""
    it_ticket_number_field: str = ""
    it_ticket_title_field: str = ""
    it_ticket_status_field: str = ""
    it_ticket_assigned_to_field: str = ""
    it_ticket_created_by_field: str = ""
    it_ticket_priority_field: str = ""
    it_ticket_request_type_field: str = ""
    it_ticket_nature_field: str = ""
    it_ticket_created_field: str = ""
    it_ticket_modified_field: str = ""
    sharepoint_site_id: str = ""
    sharepoint_site_url: str = ""
    onedesk_it_list_id: str = ""
    onedesk_it_list_title: str = ""
    onedesk_it_user_email_field: str = ""
    onedesk_it_ticket_number_field: str = ""
    onedesk_it_status_field: str = ""
    onedesk_it_assigned_to_field: str = ""
    onedesk_it_updated_field: str = ""
    onedesk_it_latest_update_field: str = ""
    onedesk_qc_list_id: str = ""
    onedesk_qc_list_title: str = ""
    onedesk_qc_user_email_field: str = ""
    onedesk_qc_ticket_number_field: str = ""
    onedesk_qc_status_field: str = ""
    onedesk_qc_assigned_to_field: str = ""
    onedesk_qc_updated_field: str = ""
    onedesk_qc_latest_update_field: str = ""
    onedesk_fleet_list_id: str = ""
    onedesk_fleet_list_title: str = ""
    onedesk_fleet_user_email_field: str = ""
    onedesk_fleet_ticket_number_field: str = ""
    onedesk_fleet_status_field: str = ""
    onedesk_fleet_assigned_to_field: str = ""
    onedesk_fleet_updated_field: str = ""
    onedesk_fleet_latest_update_field: str = ""
    onedesk_facilities_list_id: str = ""
    onedesk_facilities_list_title: str = ""
    onedesk_facilities_user_email_field: str = ""
    onedesk_facilities_ticket_number_field: str = ""
    onedesk_facilities_status_field: str = ""
    onedesk_facilities_assigned_to_field: str = ""
    onedesk_facilities_updated_field: str = ""
    onedesk_facilities_latest_update_field: str = ""
    onedesk_approvals_list_id: str = ""
    onedesk_approvals_list_title: str = ""
    onedesk_approvals_user_email_field: str = ""
    onedesk_approvals_ticket_number_field: str = ""
    onedesk_approvals_status_field: str = ""
    onedesk_approvals_assigned_to_field: str = ""
    onedesk_approvals_updated_field: str = ""
    onedesk_approvals_latest_update_field: str = ""
    request_max_bytes: int = 1_000_000
    rate_limit_per_minute: int = 60
    policy_relevance_threshold: float = 0.20
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_use_env_proxy: bool = False
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_path: str = "./chroma_db"
    policies_path: str = "./policies"
    sqlite_url: str = "sqlite:///./app.db"
    max_context_chunks: int = 4
    chunk_size: int = 800
    chunk_overlap: int = 120
    enable_chat_history: bool = True
    enable_feedback: bool = True
    enable_analytics: bool = False
    enable_onedesk_integration: bool = False
    enable_entra_auth: bool = False
    enable_onedesk_schema_discovery: bool = True
    enable_onedesk_it_read: bool = False
    enable_onedesk_it_create: bool = False
    enable_it_ticket_drafts: bool = True
    enable_it_ticket_attachments: bool = False
    enable_onedesk_mock_mode: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        seen: set[str] = set()
        origins: list[str] = []

        for candidate in [
            *self.frontend_origins.split(","),
            self.frontend_origin,
            self.sharepoint_origin,
            _origin_from_url(self.temporary_tunnel_url),
            _origin_from_url(self.public_api_base_url),
            *self.additional_allowed_origins.split(","),
        ]:
            origin = candidate.strip().rstrip("/")
            if not origin or origin in seen:
                continue

            seen.add(origin)
            origins.append(origin)

        return origins

    @property
    def async_database_url(self) -> str:
        if not self.database_url:
            return ""

        database_url = self.database_url
        if self.database_url.startswith("postgresql+psycopg2://"):
            database_url = self.database_url.replace(
                "postgresql+psycopg2://",
                "postgresql+asyncpg://",
                1,
            )

        elif self.database_url.startswith("postgresql://"):
            database_url = self.database_url.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            )

        return _quote_database_credentials(database_url)

    @property
    def effective_azure_authority(self) -> str:
        if self.azure_authority:
            return self.azure_authority.rstrip("/")
        if self.azure_tenant_id:
            return f"https://login.microsoftonline.com/{self.azure_tenant_id}/v2.0"
        return ""

    @property
    def effective_onedesk_site_id(self) -> str:
        return self.onedesk_site_id or self.sharepoint_site_id

    @property
    def effective_it_service_desk_list_id(self) -> str:
        return self.it_service_desk_list_id or self.onedesk_it_list_id

    @property
    def effective_it_service_desk_list_title(self) -> str:
        return self.it_service_desk_list_title or self.onedesk_it_list_title

    @property
    def onedesk_it_field_mapping(self) -> dict[str, dict[str, Any]]:
        if not self.onedesk_it_field_mapping_json.strip():
            return {}
        try:
            payload = json.loads(self.onedesk_it_field_mapping_json)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _quote_database_credentials(database_url: str) -> str:
    parts = urlsplit(database_url)
    if not parts.username or not parts.hostname:
        return database_url

    username = quote(unquote(parts.username), safe="")
    password = (
        f":{quote(unquote(parts.password), safe='')}"
        if parts.password is not None
        else ""
    )
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{username}{password}@{host}{port}"
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def _origin_from_url(value: str) -> str:
    raw_value = (value or "").strip()
    if not raw_value:
        return ""

    parts = urlsplit(raw_value)
    if not parts.scheme or not parts.netloc:
        return raw_value

    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
