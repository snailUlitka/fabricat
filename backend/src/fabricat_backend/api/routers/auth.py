"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fabricat_backend.api.dependencies import get_auth_service
from fabricat_backend.api.models import (
    AuthTokenResponse,
    UserLoginRequest,
    UserLoginResponse,
    UserRegisterRequest,
    UserRegisterResponse,
    UserResponse,
)
from fabricat_backend.api.services import (
    AuthService,
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from fabricat_backend.database import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    payload: UserRegisterRequest,
    session: Session = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserRegisterResponse:
    """Register a new user and issue an access token."""

    try:
        user, token = auth_service.register_user(
            session=session,
            nickname=payload.nickname,
            password=payload.password,
            icon=payload.icon,
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User already exists"
        ) from exc

    user_model = UserResponse.model_validate(user, from_attributes=True)
    token_model = AuthTokenResponse(access_token=token)
    return UserRegisterResponse(user=user_model, token=token_model)


@router.post("/login", response_model=UserLoginResponse)
def login_user(
    payload: UserLoginRequest,
    session: Session = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserLoginResponse:
    """Authenticate an existing user using nickname and password."""

    try:
        user, token = auth_service.authenticate_user(
            session=session, nickname=payload.nickname, password=payload.password
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc

    user_model = UserResponse.model_validate(user, from_attributes=True)
    token_model = AuthTokenResponse(access_token=token)
    return UserLoginResponse(user=user_model, token=token_model)
