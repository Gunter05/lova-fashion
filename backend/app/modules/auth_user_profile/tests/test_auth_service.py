"""
Unit tests for Auth_Service business logic.
RegisterRequest now has only: nom, email, mot_de_passe.
UserModel primary key is id (UUID).
"""
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.modules.auth_user_profile.auth.service import (
    AuthService,
    RegistrationError,
    AuthenticationError,
    AccountDeactivatedError,
    RateLimitError,
)
from app.modules.auth_user_profile.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    UserRole,
)
from app.modules.auth_user_profile.auth.repository import DuplicateEmailError
from app.db.models import UserModel


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def auth_service(mock_session):
    return AuthService(mock_session)


def _make_user(**kwargs):
    """Helper to create a minimal UserModel with defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        nom="Test User",
        email="test@example.com",
        mot_de_passe="hashed_password",
        role=UserRole.CLIENT,
        is_active=True,
        date_inscription=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return UserModel(**defaults)


@pytest.mark.asyncio
class TestRegistration:
    """Test user registration logic."""

    async def test_register_user_success(self, auth_service):
        """Test successful user registration."""
        request = RegisterRequest(
            nom="Test User",
            email="test@example.com",
            mot_de_passe="password123",
        )
        mock_user = _make_user()

        with patch.object(auth_service._repo, 'create_user', return_value=mock_user):
            response = await auth_service.register_user(request)

        assert response.id == str(mock_user.id)
        assert response.nom == "Test User"
        assert response.email == "test@example.com"
        assert response.role == UserRole.CLIENT

    async def test_register_duplicate_email(self, auth_service):
        """Test registration fails with duplicate email."""
        request = RegisterRequest(
            nom="Test User",
            email="test@example.com",
            mot_de_passe="password123",
        )
        with patch.object(
            auth_service._repo, 'create_user',
            side_effect=DuplicateEmailError("Email already exists")
        ):
            with pytest.raises(RegistrationError) as exc_info:
                await auth_service.register_user(request)
            assert exc_info.value.field == "email"


@pytest.mark.asyncio
class TestLogin:
    """Test user login logic."""

    async def test_login_success(self, auth_service):
        """Test successful login."""
        request = LoginRequest(email="test@example.com", mot_de_passe="password123")
        mock_user = _make_user()

        with patch.object(auth_service._repo, 'get_by_email', return_value=mock_user), \
             patch('app.modules.auth_user_profile.auth.service.verify_password', return_value=True), \
             patch('app.modules.auth_user_profile.auth.service.issue_token', return_value="mock_token"), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=False), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.reset'):
            response = await auth_service.login_user(request)

        assert response.access_token == "mock_token"
        assert response.token_type == "bearer"

    async def test_login_rate_limited(self, auth_service):
        """Test login fails when rate limited."""
        request = LoginRequest(email="test@example.com", mot_de_passe="password123")
        with patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=True), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.retry_after', return_value=600):
            with pytest.raises(RateLimitError) as exc_info:
                await auth_service.login_user(request)
            assert exc_info.value.retry_after == 600

    async def test_login_invalid_credentials(self, auth_service):
        """Test login fails with invalid credentials."""
        request = LoginRequest(email="test@example.com", mot_de_passe="wrong_password")
        mock_user = _make_user()
        with patch.object(auth_service._repo, 'get_by_email', return_value=mock_user), \
             patch('app.modules.auth_user_profile.auth.service.verify_password', return_value=False), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=False), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.record_failure'):
            with pytest.raises(AuthenticationError):
                await auth_service.login_user(request)

    async def test_login_deactivated_account(self, auth_service):
        """Test login fails with deactivated account."""
        request = LoginRequest(email="test@example.com", mot_de_passe="password123")
        mock_user = _make_user(is_active=False)
        with patch.object(auth_service._repo, 'get_by_email', return_value=mock_user), \
             patch('app.modules.auth_user_profile.auth.service.verify_password', return_value=True), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=False):
            with pytest.raises(AccountDeactivatedError):
                await auth_service.login_user(request)


@pytest.mark.asyncio
class TestLogout:
    """Test user logout logic."""

    async def test_logout_success(self, auth_service):
        """Test successful logout."""
        token = "mock.jwt.token"
        mock_claims = {
            "jti": "mock-jti-uuid",
            "exp": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "user_id": str(uuid.uuid4()),
            "role": "Client",
        }
        with patch('app.modules.auth_user_profile.auth.service.decode_token', return_value=mock_claims), \
             patch.object(auth_service._repo, 'add_jti') as mock_add_jti:
            await auth_service.logout_user(token)
        mock_add_jti.assert_called_once()
