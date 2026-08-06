from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.onedesk.schema_discovery_service import (  # noqa: E402
    OneDeskSchemaDiscoveryService,
)


async def main() -> None:
    access_token = os.getenv("GRAPH_ACCESS_TOKEN") or os.getenv("ONEASSIST_ACCESS_TOKEN")
    report = await OneDeskSchemaDiscoveryService(access_token=access_token).it_service_desk_schema()
    output_path = PROJECT_ROOT / "artifacts" / "it_service_desk_schema.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote safe schema report: {output_path}")
    print(f"mode: {report.get('mode')}")
    print(f"list ID: {report.get('listId')}")
    print(f"column count: {len(report.get('columns') or [])}")
    print("discovered mappings:")
    for key, value in (report.get("liveTicketFieldMappingSuggestion") or {}).items():
        print(f"  {key}: {value or '(missing)'}")
    if report.get("mode") == "mock":
        print("Mock schema only. Do not use mock internal names for production mapping.")


if __name__ == "__main__":
    asyncio.run(main())
