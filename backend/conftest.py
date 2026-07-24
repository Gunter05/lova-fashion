"""
Root-level pytest conftest.

Sets DATABASE_URL to a dummy value before any module is imported so that
`app.database` does not crash when creating the async engine at import time.

The real async engine is never used in tests — the module-level fixture in
`app/modules/auth_catalogues/tests/conftest.py` overrides `get_db` with an
in-memory SQLite engine for complete isolation.
"""
import os

# Must be set before any app module is imported — otherwise sqlalchemy
# raises ArgumentError: Could not parse SQLAlchemy URL from string ''.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",
)
