from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GraphErrorDetail:
    status_code: int
    message: str
    code: str | None = None
    retryable: bool = False
    details: dict[str, Any] | None = None


class GraphClientError(RuntimeError):
    def __init__(self, detail: GraphErrorDetail) -> None:
        self.detail = detail
        super().__init__(detail.message)


class GraphConfigurationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(message)
