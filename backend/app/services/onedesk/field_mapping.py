from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from backend.app.core.config import get_settings


DEFAULT_IT_SERVICE_DESK_FIELD_MAPPING: dict[str, dict[str, Any]] = {
    "ticketNumber": {
        "sharePointField": "",
        "displayName": "Serial Number",
        "type": "text",
        "required": False,
    },
    "natureOfComplaint": {
        "sharePointField": "",
        "displayName": "Nature of Complaint",
        "type": "choice",
        "required": True,
    },
    "requestType": {
        "sharePointField": "",
        "displayName": "Request_Type",
        "type": "choice",
        "required": True,
    },
    "title": {
        "sharePointField": "",
        "displayName": "Title",
        "type": "text",
        "required": True,
    },
    "requester": {
        "sharePointField": "",
        "displayName": "Created By",
        "type": "person",
        "required": True,
        "autoPopulate": True,
    },
    "assignedTo": {
        "sharePointField": "",
        "displayName": "Assigned to",
        "type": "person",
        "required": False,
    },
    "status": {
        "sharePointField": "",
        "displayName": "Status",
        "type": "choice",
        "required": False,
    },
    "department": {
        "sharePointField": "",
        "displayName": "Department",
        "type": "choice_or_text",
        "required": True,
    },
    "contactNumber": {
        "sharePointField": "",
        "displayName": "Contact Number",
        "type": "text",
        "required": True,
    },
    "additionalComments": {
        "sharePointField": "",
        "displayName": "Additional Comments",
        "type": "multiline_text",
        "required": True,
    },
    "location": {
        "sharePointField": "",
        "displayName": "Location",
        "type": "choice",
        "required": True,
    },
    "subLocation": {
        "sharePointField": "",
        "displayName": "Sub-Location",
        "type": "choice",
        "required": False,
    },
    "module": {
        "sharePointField": "",
        "displayName": "Module",
        "type": "choice",
        "required": False,
    },
    "application": {
        "sharePointField": "",
        "displayName": "Application",
        "type": "choice",
        "required": False,
    },
    "bugGeneral": {
        "sharePointField": "",
        "displayName": "Bug/General",
        "type": "choice",
        "required": False,
    },
    "networkDetails": {
        "sharePointField": "",
        "displayName": "Network Details",
        "type": "multiline_text",
        "required": False,
    },
    "oracleDetails": {
        "sharePointField": "",
        "displayName": "Oracle Details",
        "type": "multiline_text",
        "required": False,
    },
    "harmonyDetails": {
        "sharePointField": "",
        "displayName": "Harmony Details",
        "type": "multiline_text",
        "required": False,
    },
    "newChange": {
        "sharePointField": "",
        "displayName": "New/Change",
        "type": "choice",
        "required": False,
    },
}


def get_it_service_desk_field_mapping() -> dict[str, dict[str, Any]]:
    mapping = deepcopy(DEFAULT_IT_SERVICE_DESK_FIELD_MAPPING)
    configured_mapping = get_settings().onedesk_it_field_mapping

    for key, value in configured_mapping.items():
        if not isinstance(value, dict):
            continue
        base = mapping.setdefault(key, {})
        base.update(value)

    return mapping


def required_live_mapping_missing(mapping: dict[str, dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for key, config in mapping.items():
        if config.get("required") and not str(config.get("sharePointField") or "").strip():
            missing.append(key)
    return missing


@dataclass(frozen=True)
class ItTicketFieldMapping:
    ticket_number: str
    title: str
    status: str
    assigned_to: str
    created_by: str
    priority: str = ""
    request_type: str = ""
    nature_of_complaint: str = ""
    created: str = ""
    modified: str = ""

    @property
    def missing_required(self) -> list[str]:
        required = {
            "ticket_number": self.ticket_number,
            "title": self.title,
            "status": self.status,
            "created_by": self.created_by,
        }
        return [key for key, value in required.items() if not value]


IT_TICKET_DISPLAY_NAME_CANDIDATES: dict[str, tuple[str, ...]] = {
    "ticket_number": ("Serial Number", "Serial No", "Ticket Number"),
    "title": ("Title",),
    "status": ("Status",),
    "assigned_to": ("Assigned to", "Assigned To", "Assigned"),
    "created_by": ("Created By", "Author", "Created by"),
    "priority": ("Priority",),
    "request_type": ("Request_Type", "Request Type"),
    "nature_of_complaint": (
        "Nature of Complaint",
        "Nature of Complain",
        "Nature Of Complaint",
    ),
    "created": ("Created",),
    "modified": ("Modified",),
}


def get_live_it_ticket_field_mapping(
    columns: list[dict[str, Any]] | None = None,
) -> ItTicketFieldMapping:
    settings = get_settings()
    discovered = _discover_internal_names(columns or [])
    overrides = {
        "ticket_number": settings.it_ticket_number_field,
        "title": settings.it_ticket_title_field,
        "status": settings.it_ticket_status_field,
        "assigned_to": settings.it_ticket_assigned_to_field,
        "created_by": settings.it_ticket_created_by_field,
        "priority": settings.it_ticket_priority_field,
        "request_type": settings.it_ticket_request_type_field,
        "nature_of_complaint": settings.it_ticket_nature_field,
        "created": settings.it_ticket_created_field,
        "modified": settings.it_ticket_modified_field,
    }
    values = {
        key: str(overrides.get(key) or discovered.get(key) or "").strip()
        for key in IT_TICKET_DISPLAY_NAME_CANDIDATES
    }
    return ItTicketFieldMapping(**values)


def _discover_internal_names(columns: list[dict[str, Any]]) -> dict[str, str]:
    by_display_name: dict[str, str] = {}
    by_internal_name: dict[str, str] = {}

    for column in columns:
        display_name = _normalize_name(column.get("displayName"))
        internal_name = str(
            column.get("internalName")
            or column.get("name")
            or ""
        ).strip()
        if not internal_name:
            continue
        if display_name:
            by_display_name[display_name] = internal_name
        by_internal_name[_normalize_name(internal_name)] = internal_name

    discovered: dict[str, str] = {}
    for logical_name, candidates in IT_TICKET_DISPLAY_NAME_CANDIDATES.items():
        for candidate in candidates:
            normalized = _normalize_name(candidate)
            if normalized in by_display_name:
                discovered[logical_name] = by_display_name[normalized]
                break
            if normalized in by_internal_name:
                discovered[logical_name] = by_internal_name[normalized]
                break
    return discovered


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").lower().split())
