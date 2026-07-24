"""
auth_catalogues — Fabric Catalog module (Module 3).

Exposes ORM models so that Alembic auto-discovery and other modules
can import them from a single location.
"""

from app.modules.auth_catalogues.models import Fabric, FabricCategory

__all__ = ["Fabric", "FabricCategory"]
