"""Run safe, versioned Arthvest migrations against configured DATABASE_URL."""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from app.services import observation_store


def main() -> int:
    load_dotenv(".env")
    try:
        if not observation_store.initialize_storage():
            print("Migration not run: DATABASE_URL is not configured.")
            return 2
        status = observation_store.get_storage_summary()
        print("database_status=" + str(status["database_status"]))
        print("schema_status=" + str(status["schema_status"]))
        print("schema_version=" + str(status["schema_version"]))
        return 0 if status["available"] else 1
    except Exception as exc:
        print("Migration failed (" + type(exc).__name__ + "). Check database connectivity and migration logs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
