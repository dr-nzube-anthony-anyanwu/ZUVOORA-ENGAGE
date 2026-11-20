"""Request/response models. Requests forbid unknown fields so clients cannot smuggle
tenant_id, role, status or other authorisation-relevant fields into a payload."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["owner", "admin", "receptionist", "viewer"]
TenantStatus = Literal["pending", "active", "suspended", "closed"]

_TIMEZONES = frozenset(available_timezones())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ----- requests -------------------------------------------------------------------------------
class InviteMemberIn(StrictModel):
    email: EmailStr
    role: Role


class UpdateMemberRoleIn(StrictModel):
    role: Role


class CreateTenantIn(StrictModel):
    legal_name: str = Field(min_length=2, max_length=200)
    display_name: str = Field(min_length=2, max_length=120)
    timezone: str = Field(default="Africa/Lagos", max_length=64)
    owner_email: EmailStr

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        if value not in _TIMEZONES:
            raise ValueError("unknown IANA timezone")
        return value


# ----- responses ------------------------------------------------------------------------------
class MembershipSummary(BaseModel):
    tenant_id: uuid.UUID
    role: Role
    membership_active: bool
    tenant_display_name: str | None
    tenant_status: TenantStatus | None
    accessible: bool


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str | None
    mfa_verified: bool
    is_platform_admin: bool
    memberships: list[MembershipSummary]


class TenantOut(BaseModel):
    id: uuid.UUID
    legal_name: str
    display_name: str
    status: TenantStatus
    timezone: str
    created_at: datetime


class ClinicProfileOut(BaseModel):
    public_phone: str | None
    public_email: str | None
    public_address: str | None
    opening_hours: dict
    public_description: str | None


class TenantDetailOut(BaseModel):
    tenant: TenantOut
    profile: ClinicProfileOut | None
    my_role: Role


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str | None
    role: Role
    is_active: bool
    created_at: datetime
    revoked_at: datetime | None


class CreatedTenantOut(BaseModel):
    tenant: TenantOut
    owner_user_id: uuid.UUID
    owner_invited: bool
