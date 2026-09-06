"""Auth routes — signup, login, token refresh."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.deps import get_current_user, get_supabase
from app.repositories.user_repo import UserRepo
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_service(supabase: Client = Depends(get_supabase)) -> AuthService:
    return AuthService(user_repo=UserRepo(supabase))


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(
    data: SignupRequest,
    service: AuthService = Depends(_auth_service),
) -> TokenResponse:
    """Create a new user account and return a JWT token."""
    return await service.signup(data)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    service: AuthService = Depends(_auth_service),
) -> TokenResponse:
    """Verify credentials and return a JWT token."""
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    user: dict[str, Any] = Depends(get_current_user),
    service: AuthService = Depends(_auth_service),
) -> TokenResponse:
    """Issue a fresh JWT token for the authenticated user."""
    return await service.refresh(user)


@router.get("/me", response_model=UserResponse)
async def me(
    user: dict[str, Any] = Depends(get_current_user),
    service: AuthService = Depends(_auth_service),
) -> UserResponse:
    """Return the current user from the database-backed identity in the token."""
    current = await service.get_user(user["sub"])
    return UserResponse(
        id=current["id"],
        email=current["email"],
        name=current["name"],
        role=current["role"],
        avatar_url=current.get("avatar_url"),
        created_at=current["created_at"],
    )
