from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.onedesk.schema_discovery_service import (  # noqa: E402
    OneDeskSchemaDiscoveryService,
)


async def main() -> None:
    report = await OneDeskSchemaDiscoveryService().it_service_desk_schema()
    output_path = PROJECT_ROOT / "artifacts" / "it_service_desk_schema.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote safe schema report: {output_path}")
    print(f"mode: {report.get('mode')}")
    if report.get("mode") == "mock":
        print("Mock schema only. Do not use mock internal names for production mapping.")


if __name__ == "__main__":
    asyncio.run(main())
