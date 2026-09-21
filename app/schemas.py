from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class BootstrapIn(BaseModel):
    eula_version: str
    privacy_version: str
    continue_without_phone: bool = True


class MeOut(BaseModel):
    device_id: UUID
    user_id: Optional[UUID] = None
    phone: Optional[str] = None
    is_premium: bool = False
    premium_until: Optional[str] = None
    monetization_enabled: bool = False
    eula_version: str
    sessions_count: int = 1
    prompt_push: bool = False


class ReportCreate(BaseModel):
    type_code: str
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None


class VoteIn(BaseModel):
    value: Literal[1, -1]


class AbuseIn(BaseModel):
    reason: Literal["spam", "faux", "sensible"]


class LocationIn(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None


class OtpRequestIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str


class AlertCommunesIn(BaseModel):
    commune_ids: list[int]


class BillingInitiateIn(BaseModel):
    provider: Literal["mpesa", "orange_money", "airtel_money"]
    msisdn: str


class MonetizationIn(BaseModel):
    enabled: bool
    totp: Optional[str] = None
    confirm: str


class BanIn(BaseModel):
    hours: int = 24
    totp: Optional[str] = None


class GrantIn(BaseModel):
    totp: Optional[str] = None
    motif: str
