"""Models used for API request and response payloads."""

from fabricat_backend.api.models.auth import (
    AuthTokenResponse,
    UserLoginRequest,
    UserLoginResponse,
    UserRegisterRequest,
    UserRegisterResponse,
    UserResponse,
)
from fabricat_backend.api.models.session import (
    GameSessionAckResponse,
    GameSessionAdvanceMonthRequest,
    GameSessionDecisionRequest,
    GameSessionDecisionsStoredResponse,
    GameSessionErrorResponse,
    GameSessionJoinRequest,
    GameSessionMonthResultResponse,
    GameSessionRequest,
    GameSessionSettingsResponse,
    GameSessionStateResponse,
    GameSessionSubmitDecisionsRequest,
)

__all__ = [
    "AuthTokenResponse",
    "GameSessionAckResponse",
    "GameSessionAdvanceMonthRequest",
    "GameSessionDecisionRequest",
    "GameSessionDecisionsStoredResponse",
    "GameSessionErrorResponse",
    "GameSessionJoinRequest",
    "GameSessionMonthResultResponse",
    "GameSessionRequest",
    "GameSessionSettingsResponse",
    "GameSessionStateResponse",
    "GameSessionSubmitDecisionsRequest",
    "UserLoginRequest",
    "UserLoginResponse",
    "UserRegisterRequest",
    "UserRegisterResponse",
    "UserResponse",
]
