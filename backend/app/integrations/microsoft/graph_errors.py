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
    pass
