from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Pakistan Cables IT Bot"
    environment: str = "development"
    api_prefix: str = "/api"
    frontend_origin: str = "http://127.0.0.1:5500"
    sharepoint_origin: str = "https://pakistancable.sharepoint.com"
    additional_allowed_origins: str = ""
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
            self.frontend_origin,
            self.sharepoint_origin,
            *self.additional_allowed_origins.split(","),
        ]:
            origin = candidate.strip().rstrip("/")
            if not origin or origin in seen:
                continue

            seen.add(origin)
            origins.append(origin)

        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
