"""
Smoke tests — Phase 1 checkpoint.
Validates that the app starts, the root endpoint responds, the auth_catalogues
router mounts correctly, and all schema classes import without errors.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestRootEndpoint:
    def test_root_returns_200(self, client):
        """GET / returns HTTP 200."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_json(self, client):
        """GET / returns a JSON body with a status field."""
        response = client.get("/")
        data = response.json()
        assert "status" in data


class TestAuthCataloguesRouter:
    def test_module_health_returns_200(self, client):
        """GET /auth-catalogues/ returns HTTP 200 (module health check)."""
        response = client.get("/auth-catalogues/")
        assert response.status_code == 200

    def test_module_health_returns_ok_status(self, client):
        """GET /auth-catalogues/ returns the expected module status message."""
        response = client.get("/auth-catalogues/")
        data = response.json()
        assert data.get("status") == "auth_catalogues module OK"


class TestSchemaImports:
    def test_auth_schemas_importable(self):
        """All auth schema classes can be imported without errors."""
        from app.modules.auth_catalogues.auth.schemas import (
            RegisterRequest,
            RegisterResponse,
            LoginRequest,
            LoginResponse,
            ErrorResponse,
            MultiFieldErrorResponse,
            UserRole,
        )
        assert UserRole.CLIENT == "Client"
        assert UserRole.TAILOR == "Tailor"
        assert UserRole.ADMIN == "Admin"

    def test_profile_schemas_importable(self):
        """All profile schema classes can be imported without errors."""
        from app.modules.auth_catalogues.profile.schemas import (
            UserProfileResponse,
            UpdateProfileRequest,
            PhotoProfilResponse,
            AdminUserResponse,
            RoleUpdateRequest,
        )
        assert RoleUpdateRequest is not None

    def test_measurement_schemas_importable(self):
        """All measurement schema classes can be imported without errors."""
        from app.modules.auth_catalogues.measurement.schemas import (
            MensurationCreateRequest,
            MensurationResponse,
            MensurationListResponse,
        )
        assert MensurationCreateRequest is not None

    def test_register_request_validation(self):
        """RegisterRequest validates CNI format, email, password length."""
        from app.modules.auth_catalogues.auth.schemas import RegisterRequest, UserRole
        import pytest as _pytest

        # Valid request
        req = RegisterRequest(
            cni="ABC123456",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="password123",
            role=UserRole.CLIENT,
        )
        assert req.cni == "ABC123456"

        # Invalid CNI (too short)
        with _pytest.raises(Exception):
            RegisterRequest(
                cni="AB1",
                nom="Test",
                email="t@example.com",
                mot_de_passe="password123",
                role=UserRole.CLIENT,
            )

        # Password too short
        with _pytest.raises(Exception):
            RegisterRequest(
                cni="ABC123456",
                nom="Test",
                email="t@example.com",
                mot_de_passe="short",
                role=UserRole.CLIENT,
            )

    def test_mensuration_request_validation(self):
        """MensurationCreateRequest rejects non-positive and out-of-range values."""
        from app.modules.auth_catalogues.measurement.schemas import MensurationCreateRequest
        import pytest as _pytest

        # Valid request
        req = MensurationCreateRequest(
            tour_poitrine=90.0,
            tour_taille=70.0,
            tour_hanches=95.0,
            longueur_bras=60.0,
            hauteur=165.0,
        )
        assert req.tour_poitrine == 90.0

        # Zero value rejected
        with _pytest.raises(Exception):
            MensurationCreateRequest(
                tour_poitrine=0.0,
                tour_taille=70.0,
                tour_hanches=95.0,
                longueur_bras=60.0,
                hauteur=165.0,
            )

        # Over-range value rejected
        with _pytest.raises(Exception):
            MensurationCreateRequest(
                tour_poitrine=90.0,
                tour_taille=70.0,
                tour_hanches=95.0,
                longueur_bras=60.0,
                hauteur=400.0,  # > 300
            )
