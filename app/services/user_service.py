from __future__ import annotations

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserRegisterRequest


class UserService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def register(self, payload: UserRegisterRequest) -> dict:
        if self.user_repository.get_by_username(payload.username):
            raise BadRequestError(code="USERNAME_ALREADY_EXISTS", message="用户名已存在。")
        if self.user_repository.get_by_email(payload.email):
            raise BadRequestError(code="EMAIL_ALREADY_EXISTS", message="邮箱已存在。")

        return self.user_repository.create_user(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
        )

    def authenticate(self, *, identifier: str, password: str) -> dict:
        user = self.user_repository.get_by_username_or_email(identifier)
        if not user or not verify_password(password, user["hashed_password"]):
            raise BadRequestError(code="INVALID_CREDENTIALS", message="用户名或密码错误。")
        if not user["is_active"]:
            raise BadRequestError(code="USER_DISABLED", message="当前用户已被禁用。")
        return user

    def get_user(self, user_id: str) -> dict:
        user = self.user_repository.get(user_id)
        if not user:
            raise NotFoundError(code="USER_NOT_FOUND", message="用户不存在。")
        if not user["is_active"]:
            raise BadRequestError(code="USER_DISABLED", message="当前用户已被禁用。")
        return user
