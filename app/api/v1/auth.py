from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_current_user, get_settings, get_user_service
from app.core.config import Settings
from app.core.security import create_access_token
from app.schemas.auth import TokenResponse, UserRegisterRequest, UserResponse
from app.services.user_service import UserService

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegisterRequest,
    service: UserService = Depends(get_user_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = service.register(payload)
    token = create_access_token(subject=user["id"], settings=settings)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: UserService = Depends(get_user_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = service.authenticate(identifier=form_data.username, password=form_data.password)
    token = create_access_token(subject=user["id"], settings=settings)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
