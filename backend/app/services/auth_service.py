"""Authentication service — signup, login, token management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repo import UserRepo
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse

logger = structlog.stdlib.get_logger("intra_ai.service.auth")


class AuthService:
    """Handles user registration and credential verification."""

    def __init__(self, user_repo: UserRepo) -> None:
        self._repo = user_repo

    async def signup(self, data: SignupRequest) -> TokenResponse:
        """Create a new user account and return a JWT token."""
        # Public registration must never mint a privileged identity. Recruiter
        # and admin accounts are provisioned by a trusted operator/invitation
        # workflow and can still authenticate through the normal login route.
        target_role = "candidate"
        if data.role.value != "candidate":
            if (settings.APP_ENV == "development" or settings.DEBUG) and data.role.value in ("recruiter", "admin"):
                target_role = data.role.value
            else:
                raise ForbiddenError(
                    "Public signup is limited to candidate accounts; recruiter and admin access requires an invitation"
                )

        normalized_email = str(data.email).strip().lower()

        existing = await self._repo.get_user_by_email(normalized_email)
        if existing:
            raise ConflictError("A user with this email already exists")

        user_id = str(uuid.uuid4())
        hashed = hash_password(data.password)

        user = await self._repo.create_user(
            {
                "id": user_id,
                "email": normalized_email,
                "name": data.name,
                "password_hash": hashed,
                "role": target_role,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        token = create_access_token(
            {"sub": user["id"], "email": user["email"], "role": user["role"]}
        )

        logger.info("user_signup", user_id=user_id, email=data.email, role=target_role)

        return TokenResponse(
            access_token=token,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                name=user["name"],
                role=user["role"],
                avatar_url=user.get("avatar_url"),
                created_at=user["created_at"],
            ),
        )

    async def login(self, data: LoginRequest) -> TokenResponse:
        """Verify credentials and return a JWT token."""
        user = await self._repo.get_user_by_email(str(data.email).strip().lower())
        if not user:
            raise UnauthorizedError("Invalid email or password")

        if not verify_password(data.password, user["password_hash"]):
            raise UnauthorizedError("Invalid email or password")

        token = create_access_token(
            {"sub": user["id"], "email": user["email"], "role": user["role"]}
        )

        logger.info("user_login", user_id=user["id"], email=data.email)

        return TokenResponse(
            access_token=token,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                name=user["name"],
                role=user["role"],
                avatar_url=user.get("avatar_url"),
                created_at=user["created_at"],
            ),
        )

    async def refresh(self, user_payload: dict) -> TokenResponse:
        """Issue a fresh token for an already-authenticated user."""
        user = await self._repo.get_user_by_id(user_payload["sub"])
        if not user:
            raise UnauthorizedError("User not found")

        token = create_access_token(
            {"sub": user["id"], "email": user["email"], "role": user["role"]}
        )

        return TokenResponse(
            access_token=token,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                name=user["name"],
                role=user["role"],
                avatar_url=user.get("avatar_url"),
                created_at=user["created_at"],
            ),
        )

    async def get_user(self, user_id: str) -> dict:
        """Load the canonical user record for identity-sensitive endpoints."""
        user = await self._repo.get_user_by_id(user_id)
        if not user:
            raise UnauthorizedError("User not found")
        return user
