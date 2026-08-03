from __future__ import annotations

import pytest

from backend.app.security.current_user import resolve_current_user_from_authorization
from backend.app.services.onedesk.field_mapping import (
    get_it_service_desk_field_mapping,
    required_live_mapping_missing,
)
from backend.app.services.onedesk.schema_discovery_service import (
    OneDeskSchemaDiscoveryService,
)


def test_default_field_mapping_keeps_sharepoint_internal_names_blank():
    mapping = get_it_service_desk_field_mapping()

    assert mapping["title"]["displayName"] == "Title"
    assert mapping["title"]["sharePointField"] == ""
    assert "title" in required_live_mapping_missing(mapping)


def test_development_identity_is_clearly_marked():
    user = resolve_current_user_from_authorization(None)

    assert user.is_development_identity is True
    assert user.email == "development.oneassist.user@example.com"
    assert "ADMIN" in user.roles


@pytest.mark.asyncio
async def test_mock_schema_discovery_marks_mock_values_and_hides_secrets():
    report = await OneDeskSchemaDiscoveryService().it_service_desk_schema()

    assert report["mode"] == "mock"
    assert report["siteId"]
    assert report["listId"]
    assert report["columns"]
    assert all("secret" not in str(report).lower() for _ in [0])
    assert any(
        str(column.get("internalName", "")).startswith("MOCK_DO_NOT_USE_")
        for column in report["columns"]
    )


@pytest.mark.asyncio
async def test_mock_sample_items_are_available_without_graph_credentials():
    report = await OneDeskSchemaDiscoveryService().sample_items(top=1)

    assert report["mode"] == "mock"
    assert len(report["items"]) == 1
