from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OneDeskIntent:
    intent_type: str
    module: str | None
    request_number: str | None


class OneDeskIntentService:
    REQUEST_PATTERN = re.compile(r"\b([A-Z]{1,6}-?\d{2,8})\b", re.IGNORECASE)

    def detect(self, message: str) -> OneDeskIntent:
        normalized = message.lower()
        request_number = self._extract_request_number(message)

        if any(word in normalized for word in ("ticket", "it-", "service desk")):
            if any(word in normalized for word in ("show", "list", "open")) and not request_number:
                return OneDeskIntent("IT_TICKET_LIST", "it", None)
            return OneDeskIntent("IT_TICKET_STATUS", "it", request_number)

        if "qc" in normalized or "inspection" in normalized:
            return OneDeskIntent("QC_REQUEST_STATUS", "qc", request_number)

        if "fleet" in normalized:
            return OneDeskIntent("FLEET_REQUEST_STATUS", "fleet", request_number)

        if "facilit" in normalized:
            return OneDeskIntent("FACILITIES_REQUEST_STATUS", "facilities", request_number)

        if "approval" in normalized or "pending" in normalized:
            return OneDeskIntent("APPROVAL_STATUS", "approvals", request_number)

        if any(word in normalized for word in ("hi", "hello", "salam", "aoa")):
            return OneDeskIntent("GREETING", None, None)

        if any(word in normalized for word in ("policy", "procedure", "standard")):
            return OneDeskIntent("POLICY_QUESTION", None, None)

        return OneDeskIntent("GENERAL_QUESTION", None, None)

    def _extract_request_number(self, message: str) -> str | None:
        match = self.REQUEST_PATTERN.search(message)
        return match.group(1).upper() if match else None
