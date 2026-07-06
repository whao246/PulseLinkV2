from __future__ import annotations

from pydantic import BaseModel


class TestLoginRequest(BaseModel):
    user_id: str


class WechatLoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
