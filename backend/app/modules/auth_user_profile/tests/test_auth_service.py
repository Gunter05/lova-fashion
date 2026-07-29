"""
Unit tests for Auth_Service business logic.

Tests registration, login, and logout flows.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
from app.modules.auth_user_profile.auth.repository import (
    DuplicateCNIError,
    DuplicateEmailError,
)
from app.db.models import UserModel


@pytest.fixture
def mock_session():
    """Mock AsyncSession for testing."""
    return AsyncMock()


@pytest.fixture
def auth_service(mock_session):
    """AuthService instance with mocked session."""
    return AuthService(mock_session)


@pytest.mark.asyncio
class TestRegistration:
    """Test user registration logic."""

    async def test_register_user_success(self, auth_service, mock_session):
        """Test successful user registration."""
        # Arrange
        request = RegisterRequest(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="password123",
            role=UserRole.CLIENT
        )
        
        mock_user = UserModel(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="hashed_password",
            role=UserRole.CLIENT,
            is_active=True,
            date_inscription=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_service._repo, 'create_user', return_value=mock_user):
            # Act
            response = await auth_service.register_user(request)
        
        # Assert
        assert response.cni == "A12345678"
        assert response.nom == "Test User"
        assert response.email == "test@example.com"
        assert response.role == UserRole.CLIENT

    async def test_register_duplicate_cni(self, auth_service):
        """Test registration fails with duplicate CNI."""
        # Arrange
        request = RegisterRequest(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="password123",
            role=UserRole.CLIENT
        )
        
        with patch.object(
            auth_service._repo,
            'create_user',
            side_effect=DuplicateCNIError("CNI already exists")
        ):
            # Act & Assert
            with pytest.raises(RegistrationError) as exc_info:
                await auth_service.register_user(request)
            
            assert exc_info.value.field == "cni"

    async def test_register_duplicate_email(self, auth_service):
        """Test registration fails with duplicate email."""
        # Arrange
        request = RegisterRequest(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="password123",
            role=UserRole.CLIENT
        )
        
        with patch.object(
            auth_service._repo,
            'create_user',
            side_effect=DuplicateEmailError("Email already exists")
        ):
            # Act & Assert
            with pytest.raises(RegistrationError) as exc_info:
                await auth_service.register_user(request)
            
            assert exc_info.value.field == "email"


@pytest.mark.asyncio
class TestLogin:
    """Test user login logic."""

    async def test_login_success(self, auth_service):
        """Test successful login."""
        # Arrange
        request = LoginRequest(
            email="test@example.com",
            mot_de_passe="password123"
        )
        
        mock_user = UserModel(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="$2b$12$hash",  # bcrypt hash
            role=UserRole.CLIENT,
            is_active=True,
            date_inscription=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_service._repo, 'get_by_email', return_value=mock_user), \
             patch('app.modules.auth_user_profile.auth.service.verify_password', return_value=True), \
             patch('app.modules.auth_user_profile.auth.service.issue_token', return_value="mock_token"), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=False), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.reset'):
            
            # Act
            response = await auth_service.login_user(request)
        
        # Assert
        assert response.access_token == "mock_token"
        assert response.token_type == "bearer"

    async def test_login_rate_limited(self, auth_service):
        """Test login fails when rate limited."""
        # Arrange
        request = LoginRequest(
            email="test@example.com",
            mot_de_passe="password123"
        )
        
        with patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=True), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.retry_after', return_value=600):
            
            # Act & Assert
            with pytest.raises(RateLimitError) as exc_info:
                await auth_service.login_user(request)
            
            assert exc_info.value.retry_after == 600

    async def test_login_invalid_credentials(self, auth_service):
        """Test login fails with invalid credentials."""
        # Arrange
        request = LoginRequest(
            email="test@example.com",
            mot_de_passe="wrong_password"
        )
        
        mock_user = UserModel(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="$2b$12$hash",
            role=UserRole.CLIENT,
            is_active=True,
            date_inscription=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_service._repo, 'get_by_email', return_value=mock_user), \
             patch('app.modules.auth_user_profile.auth.service.verify_password', return_value=False), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=False), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.record_failure'):
            
            # Act & Assert
            with pytest.raises(AuthenticationError):
                await auth_service.login_user(request)

    async def test_login_deactivated_account(self, auth_service):
        """Test login fails with deactivated account."""
        # Arrange
        request = LoginRequest(
            email="test@example.com",
            mot_de_passe="password123"
        )
        
        mock_user = UserModel(
            cni="A12345678",
            nom="Test User",
            email="test@example.com",
            mot_de_passe="$2b$12$hash",
            role=UserRole.CLIENT,
            is_active=False,  # Deactivated
            date_inscription=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_service._repo, 'get_by_email', return_value=mock_user), \
             patch('app.modules.auth_user_profile.auth.service.verify_password', return_value=True), \
             patch('app.modules.auth_user_profile.auth.service.rate_limiter.is_locked', return_value=False):
            
            # Act & Assert
            with pytest.raises(AccountDeactivatedError):
                await auth_service.login_user(request)


@pytest.mark.asyncio
class TestLogout:
    """Test user logout logic."""

    async def test_logout_success(self, auth_service):
        """Test successful logout."""
        # Arrange
        token = "mock.jwt.token"
        mock_claims = {
            "jti": "mock-jti-uuid",
            "exp": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "cni": "A12345678",
            "role": "Client"
        }
        
        with patch('app.modules.auth_user_profile.auth.service.decode_token', return_value=mock_claims), \
             patch.object(auth_service._repo, 'add_jti') as mock_add_jti:
            
            # Act
            await auth_service.logout_user(token)
        
        # Assert
        mock_add_jti.assert_called_once()
