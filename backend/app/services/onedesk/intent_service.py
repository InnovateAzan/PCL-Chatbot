from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OneDeskIntent:
    intent_type: str
    module: str | None
    request_number: str | None
    status: str | None = None


class OneDeskIntentService:
    REQUEST_PATTERN = re.compile(
        r"(?:serial\s*(?:number|no\.?)?|ticket\s*#?|#)\s*([0-9]{1,8})\b|\b([A-Z]{1,6}-?\d{2,8})\b",
        re.IGNORECASE,
    )

    def detect(self, message: str) -> OneDeskIntent:
        normalized = message.lower()
        request_number = self._extract_request_number(message)

        if self._looks_like_it_ticket_intent(normalized, request_number):
            if request_number:
                if not request_number.isdigit():
                    return OneDeskIntent("IT_TICKET_STATUS", "it", request_number)
                return OneDeskIntent("IT_TICKET_SERIAL", "it", request_number)
            if "latest" in normalized or "akhri" in normalized:
                return OneDeskIntent("IT_TICKET_LATEST", "it", None)
            if "summary" in normalized or "how many" in normalized or "kitn" in normalized:
                status_name = self._extract_status(normalized)
                if status_name:
                    return OneDeskIntent("IT_TICKET_STATUS_COUNT", "it", None, status_name)
                return OneDeskIntent("IT_TICKET_SUMMARY", "it", None)
            if "open" in normalized:
                return OneDeskIntent("IT_TICKET_OPEN", "it", None)
            if "closed" in normalized:
                return OneDeskIntent("IT_TICKET_CLOSED", "it", None)
            status_name = self._extract_status(normalized)
            if status_name:
                return OneDeskIntent("IT_TICKET_STATUS_LIST", "it", None, status_name)
            return OneDeskIntent("IT_TICKET_LIST", "it", None)

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
        if not match:
            return None
        value = match.group(1) or match.group(2)
        return value.upper() if value and not value.isdigit() else value

    @staticmethod
    def _looks_like_it_ticket_intent(normalized: str, request_number: str | None) -> bool:
        if request_number:
            return any(term in normalized for term in ("ticket", "serial", "status"))
        english_terms = ("ticket", "tickets", "service desk")
        roman_urdu_terms = ("meri ticket", "meri tickets", "dikhao", "ka status")
        return any(term in normalized for term in english_terms + roman_urdu_terms)

    @staticmethod
    def _extract_status(normalized: str) -> str | None:
        status_phrases = {
            "in progress": ("in progress", "in-progress", "progress"),
            "resolved": ("resolved",),
            "closed": ("closed",),
            "pending": ("pending",),
            "new": ("new",),
            "blocked": ("blocked",),
            "reopen": ("reopen", "reopened"),
            "incomplete": ("incomplete",),
        }
        for status_name, aliases in status_phrases.items():
            if any(alias in normalized for alias in aliases):
                return status_name
        return None
