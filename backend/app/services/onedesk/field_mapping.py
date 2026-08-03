from __future__ import annotations

from copy import deepcopy
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
