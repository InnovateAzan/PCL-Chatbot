from functools import lru_cache
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
    azure_admin_role: str = "ADMIN"
    azure_user_role: str = "USER"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
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
