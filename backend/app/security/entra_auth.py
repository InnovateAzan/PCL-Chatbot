from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthenticatedUser:
    oid: str | None
    email: str
    display_name: str
    preferred_name: str | None = None
    upn: str | None = None
    preferred_username: str | None = None
    roles: set[str] = field(default_factory=set)
    is_development_identity: bool = False

    @property
    def normalized_identifiers(self) -> set[str]:
        values = {
            self.email,
            self.upn,
            self.preferred_username,
            self.oid,
        }
        return {
            str(value).strip().lower()
            for value in values
            if str(value or "").strip()
        }


class AuthenticationError(ValueError):
    """Raised when a bearer token cannot be trusted."""
