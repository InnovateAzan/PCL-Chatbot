from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.exc import OperationalError, SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.existing_database import test_connection


def main() -> None:
    try:
        result = test_connection()
    except OperationalError as exc:
        print("PostgreSQL connection failed.")
        print("Please verify DATABASE_URL in .env, especially username/password.")
        print(f"Details: {exc.orig}")
        raise SystemExit(1) from exc
    except SQLAlchemyError as exc:
        print("PostgreSQL connection failed.")
        print(f"Details: {exc}")
        raise SystemExit(1) from exc

    print(f"current_database(): {result.get('database_name')}")
    print(f"current_user: {result.get('user_name')}")
    print(f"server IP: {result.get('server_ip')}")
    print(f"port: {result.get('server_port')}")


if __name__ == "__main__":
    main()
