from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.security.current_user import resolve_current_user_from_authorization  # noqa: E402
from backend.app.services.onedesk.it_ticket_service import ItTicketService  # noqa: E402


async def main() -> None:
    token = os.getenv("ONEASSIST_ACCESS_TOKEN", "").strip()
    if not token:
        print("Set ONEASSIST_ACCESS_TOKEN to test current-user ticket lookup.")
        return

    user = resolve_current_user_from_authorization(f"Bearer {token}")
    tickets = await ItTicketService(access_token=token).get_user_tickets(user)

    print("current user identity:")
    print(f"  oid: {user.oid or '(missing)'}")
    print(f"  email: {user.email}")
    print(f"  upn: {user.upn or user.preferred_username or '(missing)'}")
    print(f"ticket count: {len(tickets)}")
    print("ticket serial numbers:")
    for ticket in tickets:
        print(f"  {ticket.get('serial_number')}")


if __name__ == "__main__":
    asyncio.run(main())
