from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.core.config import get_settings


request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "oneassist_request_id",
    default=None,
)

SENSITIVE_KEY_PATTERNS = (
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "api_key",
    "cookie",
    "database_url",
)

SAFE_TOKEN_DIAGNOSTIC_KEYS = {
    "token_present",
    "token_length",
    "jwt_segment_count",
    "token_audience",
    "token_issuer",
    "token_expiry",
    "token_expired",
}

EMAIL_PATTERN = re.compile(
    r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)

_configured = False


def configure_logging() -> None:
    global _configured

    if _configured:
        return

    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_file = Path(settings.log_file)
    error_file = Path(settings.log_error_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    error_file.parent.mkdir(parents=True, exist_ok=True)

    formatter: logging.Formatter
    if settings.log_json:
        formatter = JsonFormatter()
    else:
        formatter = StructuredTextFormatter()

    handlers: list[logging.Handler] = []
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    handlers.append(console_handler)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    handlers.append(file_handler)

    error_handler = RotatingFileHandler(
        error_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    handlers.append(error_handler)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)
    for handler in handlers:
        handler.addFilter(RedactionFilter())
        root_logger.addHandler(handler)

    logging.captureWarnings(True)
    _configured = True


def install_request_logging(app: FastAPI) -> None:
    logger = logging.getLogger("backend.app.request")

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = _resolve_request_id(request.headers.get("x-request-id"))
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500

        log_event(
            logger,
            "request_started",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
            client_origin=request.headers.get("origin"),
            auth_header_present=bool(request.headers.get("authorization")),
            session_id=request.headers.get("x-oneassist-user-id"),
        )

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(
                logger,
                "request_failed",
                level=logging.ERROR,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                exception_type=type(exc).__name__,
                safe_message=str(exc)[:300],
                stack_trace=_safe_stack_trace(),
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(
                logger,
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration_ms=duration_ms,
                authenticated_oid=getattr(request.state, "authenticated_oid", None),
                session_id=getattr(request.state, "session_id", None)
                or request.headers.get("x-oneassist-user-id"),
            )
            try:
                response.headers["X-Request-ID"] = request_id
            except Exception:
                pass
            request_id_var.reset(token)


def install_exception_handlers(app: FastAPI) -> None:
    logger = logging.getLogger("backend.app.errors")

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        settings = get_settings()
        request_id = getattr(request.state, "request_id", None) or request_id_var.get()
        log_event(
            logger,
            "unhandled_exception",
            level=logging.ERROR,
            request_id=request_id,
            path=request.url.path,
            exception_type=type(exc).__name__,
            safe_message=str(exc)[:300],
            stack_trace=_safe_stack_trace()
            if settings.environment.lower() in {"development", "dev", "local"}
            else None,
        )
        content = {
            "detail": "An unexpected error occurred.",
            "request_id": request_id,
        }
        if settings.environment.lower() in {"development", "dev", "local"}:
            content["error_code"] = "UNHANDLED_EXCEPTION"
        return JSONResponse(status_code=500, content=content)


def log_startup_configuration() -> None:
    settings = get_settings()
    logger = logging.getLogger("backend.app.startup")
    database_backend = (
        "postgresql"
        if settings.database_url.startswith("postgresql")
        else "sqlite"
        if settings.database_url.startswith("sqlite")
        else "unconfigured"
    )
    log_event(
        logger,
        "startup_configuration",
        app_env=settings.app_env,
        environment=settings.environment,
        log_level=settings.log_level,
        enable_database=settings.enable_database,
        database_configured=bool(settings.database_url),
        database_backend=database_backend,
        database_url=settings.database_url,
        chroma_path_configured=bool(settings.chroma_path),
        gemini_configured=bool(settings.gemini_api_key),
        entra_tenant_configured=bool(settings.azure_tenant_id),
        client_id_configured=bool(settings.azure_client_id),
        client_secret_configured=bool(settings.azure_client_secret),
        api_audience_configured=bool(settings.azure_api_audience),
        obo_scopes_configured=bool(settings.azure_obo_scopes),
        onedesk_read_enabled=settings.enable_onedesk_it_read,
        mock_mode=settings.enable_onedesk_mock_mode,
        sharepoint_site_url_configured=bool(settings.onedesk_site_url),
        list_title=settings.effective_it_service_desk_list_title,
        list_id_configured=bool(settings.effective_it_service_desk_list_id),
    )


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    safe_fields = sanitize_log_data(fields)
    if "request_id" not in safe_fields:
        safe_fields["request_id"] = request_id_var.get()
    logger.log(
        level,
        event,
        extra={
            "event_name": event,
            "safe_fields": safe_fields,
        },
    )


def sanitize_log_data(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in SAFE_TOKEN_DIAGNOSTIC_KEYS:
                sanitized[key_text] = sanitize_log_data(item)
            elif _is_sensitive_key(key_text):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = sanitize_log_data(item)
        return sanitized

    if isinstance(value, list):
        return [sanitize_log_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_log_data(item) for item in value)

    if isinstance(value, str):
        if _looks_like_database_url(value):
            return "[REDACTED_DATABASE_URL]"
        return mask_email(value)

    return value


def mask_email(value: str) -> str:
    return EMAIL_PATTERN.sub(r"\1***\2", value)


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_log_data(record.msg)
        if isinstance(record.args, dict):
            record.args = sanitize_log_data(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(sanitize_log_data(item) for item in record.args)
        if hasattr(record, "safe_fields"):
            record.safe_fields = sanitize_log_data(record.safe_fields)
        return True


class StructuredTextFormatter(logging.Formatter):
    converter = time.gmtime

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, UTC).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record)
        event = getattr(record, "event_name", record.getMessage())
        fields = getattr(record, "safe_fields", {})
        field_text = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
            for key, value in fields.items()
            if value is not None
        )
        return (
            f"{timestamp} level={record.levelname} "
            f"logger={record.name} event={event} {field_text}"
        ).strip()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event_name", record.getMessage()),
            **getattr(record, "safe_fields", {}),
        }
        return json.dumps(sanitize_log_data(payload), ensure_ascii=False, default=str)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(pattern in normalized for pattern in SENSITIVE_KEY_PATTERNS)


def _looks_like_database_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("postgresql://", "postgresql+", "mysql://"))


def _resolve_request_id(value: str | None) -> str:
    if value:
        candidate = value.strip()
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", candidate):
            return candidate
    return str(uuid.uuid4())


def _safe_stack_trace() -> str:
    return sanitize_log_data("".join(traceback.format_exc(limit=20)))
