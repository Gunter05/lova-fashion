"""
Re-export the FastAPI app instance so that tests can import it via
`from app.main import app` when pytest is run from the `backend/` directory.
"""
import sys
import os

# Ensure the backend root is on sys.path so that `import main` resolves correctly.
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from main import app  # noqa: E402  (imported from backend/main.py)

__all__ = ["app"]
