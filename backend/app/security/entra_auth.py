from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthenticatedUser:
    oid: str | None
    email: str
    display_name: str
    preferred_name: str | None = None
    roles: set[str] = field(default_factory=set)
    is_development_identity: bool = False


class AuthenticationError(ValueError):
    """Raised when a bearer token cannot be trusted."""
