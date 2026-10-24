"""
Pydantic schemas for Authentication and Session Management.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterOrgRequest(BaseModel):
    org_name: str = Field(..., min_length=2, max_length=100)
    site_name: str = Field(..., min_length=2, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=10)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserSummaryResponse(BaseModel):
    id: str
    org_id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    user: UserSummaryResponse
    refresh_token: Optional[str] = None  # Returned only in dev mode for API testing


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=10)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=10)


class SessionResponse(BaseModel):
    id: str
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
