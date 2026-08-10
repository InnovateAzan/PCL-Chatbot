from __future__ import annotations

import logging
import base64
import json
from datetime import UTC, datetime
from typing import Any

from backend.app.core.logging_config import log_event

logger = logging.getLogger(__name__)


def safe_token_diagnostics(token: str | None) -> dict[str, Any]:
    token_value = str(token or "").strip()
    diagnostics: dict[str, Any] = {
        "token_present": bool(token_value),
        "token_length": len(token_value),
        "jwt_segment_count": token_value.count(".") + 1 if token_value else 0,
        "token_audience": None,
        "token_issuer": None,
        "token_expiry": None,
        "token_expired": None,
    }

    if diagnostics["jwt_segment_count"] != 3:
        return diagnostics

    claims = _decode_payload_segment(token_value)
    if not claims:
        return diagnostics

    exp = claims.get("exp")
    expiry = _format_expiry(exp)

    diagnostics.update(
        {
            "token_audience": claims.get("aud"),
            "token_issuer": claims.get("iss"),
            "token_expiry": expiry,
            "token_expired": _is_expired(exp),
        }
    )
    return diagnostics


def token_format_error(token: str | None) -> str | None:
    diagnostics = safe_token_diagnostics(token)
    if not diagnostics["token_present"]:
        return "token_missing"
    if diagnostics["token_length"] <= 100:
        return "token_too_short"
    if diagnostics["jwt_segment_count"] != 3:
        return "invalid_token_format"
    if diagnostics["token_expired"] is True:
        return "expired_token"
    return None


def log_auth_stage(
    stage: str,
    *,
    token: str | None = None,
    result: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = safe_token_diagnostics(token)
    payload["stage"] = stage
    payload["result"] = result
    if extra:
        payload.update(extra)
    log_event(logger, stage, **payload)


def public_auth_message(code: str) -> str:
    messages = {
        "token_missing": "Microsoft API token is missing. Please refresh the OneDesk page and try again.",
        "token_too_short": "Microsoft API token is invalid. The token received by the assistant was too short.",
        "invalid_token_format": "Microsoft API token is invalid. Expected a JWT with 3 segments.",
        "expired_token": "Microsoft API token is expired. Please retry so the assistant can request a fresh token.",
        "wrong_audience": "Microsoft API token has the wrong audience. SPFx must request the OneDesk API token, not a Microsoft Graph token.",
        "wrong_issuer": "Microsoft API token has the wrong issuer or tenant.",
        "tenant_mismatch": "Microsoft API token tenant does not match the configured tenant.",
        "signature_invalid": "Microsoft API token signature validation failed.",
        "obo_failed": "Microsoft Graph On-Behalf-Of exchange failed.",
        "graph_permission_denied": "Microsoft Graph or SharePoint permission was denied.",
        "validation_failed": "Microsoft API token validation failed.",
    }
    return messages.get(code, "Microsoft authentication failed.")


def _format_expiry(exp: Any) -> str | None:
    try:
        timestamp = int(exp)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def _is_expired(exp: Any) -> bool | None:
    try:
        timestamp = int(exp)
    except (TypeError, ValueError):
        return None
    return timestamp <= int(datetime.now(UTC).timestamp())


def _decode_payload_segment(token: str) -> dict[str, Any]:
    try:
        payload_segment = token.split(".")[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

    return payload if isinstance(payload, dict) else {}
