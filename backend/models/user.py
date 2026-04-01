from pydantic import BaseModel, EmailStr
from typing import Literal


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    risk_profile: str
    budget_pln: float
    preferred_currency: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserUpdate(BaseModel):
    risk_profile: Literal["low", "medium", "high"] | None = None
    budget_pln: float | None = None
    preferred_currency: str | None = None
