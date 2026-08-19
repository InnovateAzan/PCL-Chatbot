from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OneDeskIntent:
    intent_type: str
    module: str | None
    request_number: str | None
    request_query: str | None = None
    status: str | None = None
    follow_up: bool = False


class OneDeskIntentService:
    REQUEST_PATTERN = re.compile(
        r"(?:serial\s*(?:number|no\.?)?|ticket\s*#?|#)\s*([0-9]{1,8})\b|\b([A-Z]{1,6}-?\d{2,8})\b",
        re.IGNORECASE,
    )

    KNOWN_POLICY_NAMES = (
        "acceptable use",
        "ai governance",
        "information security",
        "access control",
        "backup disaster recovery",
        "backup & disaster recovery",
        "incident response",
        "hardware procurement",
        "software procurement",
        "vendor third party risk",
        "vendor & third party risk",
    )

    def detect(
        self,
        message: str,
        *,
        context_request_number: str | None = None,
    ) -> OneDeskIntent:
        normalized = message.lower()
        request_number = self._extract_request_number(message)
        resolved_request_number = request_number or context_request_number
        follow_up = (
            not request_number
            and bool(context_request_number)
            and self._looks_like_follow_up(normalized)
        )
        query = self._extract_ticket_query(normalized)

        policy_intent = self._looks_like_policy_intent(normalized)
        policy_summary = self._looks_like_policy_summary(normalized)
        policy_name_hit = self._matches_known_policy_name(normalized)
        ticket_intent = self._looks_like_it_ticket_intent(
            normalized,
            request_number,
            context_request_number,
        )

        if policy_name_hit and not ticket_intent:
            return OneDeskIntent("POLICY_QUESTION", "policy", None)

        if policy_intent and policy_summary:
            return OneDeskIntent("POLICY_QUESTION", "policy", None)

        if (policy_intent or policy_name_hit) and ticket_intent:
            return OneDeskIntent("MIXED", None, None, request_query=query)

        if policy_intent:
            return OneDeskIntent("POLICY_QUESTION", "policy", None)

        if follow_up or self._looks_like_it_ticket_intent(
            normalized,
            request_number,
            context_request_number,
        ):
            if request_number or follow_up:
                serial = resolved_request_number or request_number or context_request_number

                if self._wants_assignee(normalized):
                    return OneDeskIntent("IT_TICKET_ASSIGNEE", "it", serial, follow_up=follow_up)
                if self._wants_request_type(normalized):
                    return OneDeskIntent("IT_TICKET_REQUEST_TYPE", "it", serial, follow_up=follow_up)
                if self._wants_created_date(normalized):
                    return OneDeskIntent("IT_TICKET_CREATED", "it", serial, follow_up=follow_up)
                if self._wants_modified_date(normalized):
                    return OneDeskIntent("IT_TICKET_MODIFIED", "it", serial, follow_up=follow_up)
                if self._wants_status(normalized):
                    return OneDeskIntent("IT_TICKET_STATUS", "it", serial, follow_up=follow_up)
                if not request_number and follow_up:
                    return OneDeskIntent("IT_TICKET_DETAILS", "it", serial, follow_up=True)
                if request_number and not request_number.isdigit():
                    return OneDeskIntent("IT_TICKET_STATUS", "it", serial, follow_up=follow_up)
                return OneDeskIntent("IT_TICKET_DETAILS", "it", serial, follow_up=follow_up)

            if "latest" in normalized or "akhri" in normalized:
                return OneDeskIntent("IT_TICKET_LATEST", "it", None)
            if self._wants_assigned_to_me(normalized):
                return OneDeskIntent("IT_TICKET_ASSIGNED_TO_ME", "it", None)
            if self._wants_unassigned(normalized):
                return OneDeskIntent("IT_TICKET_UNASSIGNED", "it", None)
            if "summary" in normalized or "how many" in normalized or "kitn" in normalized:
                status_name = self._extract_status(normalized)
                if status_name:
                    return OneDeskIntent("IT_TICKET_STATUS_COUNT", "it", None, status_name)
                return OneDeskIntent("IT_TICKET_SUMMARY", "it", None)
            if self._wants_open(normalized):
                return OneDeskIntent("IT_TICKET_OPEN", "it", None)
            if self._wants_resolved(normalized):
                return OneDeskIntent("IT_TICKET_RESOLVED", "it", None)
            if any(
                phrase in normalized
                for phrase in ("show my tickets", "my tickets", "list my tickets", "all my tickets", "all tickets")
            ):
                return OneDeskIntent("IT_TICKET_LIST", "it", None)
            status_name = self._extract_status(normalized)
            if status_name:
                return OneDeskIntent("IT_TICKET_STATUS_LIST", "it", None, status_name)
            if query:
                if self._wants_assignee(normalized):
                    return OneDeskIntent("IT_TICKET_ASSIGNEE_LOOKUP", "it", None, request_query=query)
                if self._wants_request_type(normalized):
                    return OneDeskIntent("IT_TICKET_REQUEST_TYPE_LOOKUP", "it", None, request_query=query)
                if self._wants_created_date(normalized):
                    return OneDeskIntent("IT_TICKET_CREATED_LOOKUP", "it", None, request_query=query)
                if self._wants_modified_date(normalized):
                    return OneDeskIntent("IT_TICKET_MODIFIED_LOOKUP", "it", None, request_query=query)
                if self._wants_status(normalized):
                    return OneDeskIntent("IT_TICKET_STATUS_LOOKUP", "it", None, request_query=query)
                return OneDeskIntent("IT_TICKET_DETAILS_LOOKUP", "it", None, request_query=query)
            return OneDeskIntent("IT_TICKET_LIST", "it", None)

        if query and self._looks_like_ticket_natural_language(normalized):
            if self._wants_assignee(normalized):
                return OneDeskIntent("IT_TICKET_ASSIGNEE_LOOKUP", "it", None, request_query=query)
            if self._wants_request_type(normalized):
                return OneDeskIntent("IT_TICKET_REQUEST_TYPE_LOOKUP", "it", None, request_query=query)
            if self._wants_created_date(normalized):
                return OneDeskIntent("IT_TICKET_CREATED_LOOKUP", "it", None, request_query=query)
            if self._wants_modified_date(normalized):
                return OneDeskIntent("IT_TICKET_MODIFIED_LOOKUP", "it", None, request_query=query)
            if self._wants_status(normalized):
                return OneDeskIntent("IT_TICKET_STATUS_LOOKUP", "it", None, request_query=query)
            return OneDeskIntent("IT_TICKET_DETAILS_LOOKUP", "it", None, request_query=query)

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

        return OneDeskIntent("GENERAL_QUESTION", None, None)

    def _extract_request_number(self, message: str) -> str | None:
        match = self.REQUEST_PATTERN.search(message)
        if not match:
            return None
        value = match.group(1) or match.group(2)
        return value.upper() if value and not value.isdigit() else value

    @staticmethod
    def _extract_ticket_query(normalized: str) -> str | None:
        cleaned = re.sub(
            r"\b(my|the|a|an|ticket|tickets|details|detail|status|assigned|assignment|assigned to|who is|is|of|complain|complaint|request|issue|problem|case|query|record|report|case|case details|what happened|what happened to|show|provide|get|please|kindly)\b",
            " ",
            normalized,
        )
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if len(cleaned) >= 2 else None

    @staticmethod
    def _looks_like_ticket_natural_language(normalized: str) -> bool:
        cues = (
            "ticket",
            "request",
            "complain",
            "complaint",
            "issue",
            "status",
            "details",
            "assigned",
            "assign",
            "what happened",
            "show my",
            "provide my",
            "my ",
        )
        return any(cue in normalized for cue in cues)

    @staticmethod
    def _looks_like_policy_intent(normalized: str) -> bool:
        policy_phrases = (
            "policy",
            "policies",
            "policy summary",
            "key responsibilities",
            "compliance requirements",
            "requirements",
            "overview",
            "acceptable use",
            "ai governance",
            "information security",
            "access control",
            "backup disaster recovery",
            "backup & disaster recovery",
            "incident response",
            "hardware procurement",
            "software procurement",
            "vendor third party risk",
            "vendor & third party risk",
        )
        return any(phrase in normalized for phrase in policy_phrases)

    @classmethod
    def _matches_known_policy_name(cls, normalized: str) -> bool:
        return any(name in normalized for name in cls.KNOWN_POLICY_NAMES)

    @staticmethod
    def _looks_like_policy_summary(normalized: str) -> bool:
        summary_cues = (
            "policy summary",
            "summary of",
            "key responsibilities",
            "compliance requirements",
            "requirements",
            "overview",
        )
        return any(cue in normalized for cue in summary_cues)

    @staticmethod

    @staticmethod
    def _looks_like_it_ticket_intent(
        normalized: str,
        request_number: str | None,
        context_request_number: str | None,
    ) -> bool:
        if request_number or context_request_number:
            return any(term in normalized for term in ("ticket", "serial"))
        english_terms = ("ticket", "tickets", "service desk")
        roman_urdu_terms = ("meri ticket", "meri tickets", "dikhao")
        return any(term in normalized for term in english_terms + roman_urdu_terms)

    @staticmethod
    def _looks_like_follow_up(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in (
                "who is it",
                "who is this",
                "show full details",
                "full details",
                "details",
                "what about it",
                "assign it",
                "assigned to",
                "who is assigned",
                "what is the status",
                "status kya",
                "kis ko assigned",
                "kis ko assign",
                "kis ko assign hai",
                "kis ko hai",
                "only unresolved",
                "only resolved",
                "just ticket",
                "i asked for",
            )
        )

    @staticmethod
    def _wants_assignee(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in (
                "assigned to",
                "assigned",
                "assign member",
                "kis ko assign",
                "kis ko assigned",
                "kis ko assign hai",
            )
        )

    @staticmethod
    def _wants_request_type(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in ("request type", "requesttype", "type of request")
        )

    @staticmethod
    def _wants_created_date(normalized: str) -> bool:
        return "created" in normalized or "created at" in normalized

    @staticmethod
    def _wants_modified_date(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in ("last updated", "updated", "modified")
        )

    @staticmethod
    def _wants_status(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in (
                "status",
                "resolved",
                "closed",
                "open",
                "pending",
                "new",
                "blocked",
                "in progress",
            )
        )

    @staticmethod
    def _wants_assigned_to_me(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in (
                "assigned to me",
                "assign to me",
                "my assigned tickets",
                "provide assign tickets only",
                "which tickets are assigned to me",
                "mera assigned",
                "meri assigned",
                "meri ticket kis ko assign hai",
            )
        )

    @staticmethod
    def _wants_unassigned(normalized: str) -> bool:
        return "unassigned" in normalized

    @staticmethod
    def _wants_open(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in ("open tickets", "unresolved", "pending", "active")
        ) or (
            "open" in normalized and "open ticket" not in normalized
        )

    @staticmethod
    def _wants_resolved(normalized: str) -> bool:
        return "resolved" in normalized or "closed" in normalized

    @staticmethod
    def _extract_status(normalized: str) -> str | None:
        status_phrases = {
            "open": ("open", "unresolved", "pending", "active"),
            "resolved": ("resolved",),
            "closed": ("closed",),
            "in progress": ("in progress", "in-progress", "progress"),
            "new": ("new",),
            "blocked": ("blocked",),
            "reopen": ("reopen", "reopened"),
            "incomplete": ("incomplete",),
        }
        for status_name, aliases in status_phrases.items():
            if any(alias in normalized for alias in aliases):
                return status_name
        return None
