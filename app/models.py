from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Commune(Base):
    __tablename__ = "communes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    geom = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=1)


class RoadAxis(Base):
    __tablename__ = "road_axes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    geom = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    phone_e164: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    premium_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    platform: Mapped[str] = mapped_column(String(32), default="other")
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trust_score: Mapped[float] = mapped_column(Numeric(4, 3), default=0.500)
    last_point = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    last_point_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sessions_count: Mapped[int] = mapped_column(Integer, default=1)

    user: Mapped[Optional[User]] = relationship()


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    csrf_token: Mapped[str] = mapped_column(String(64))
    last_viewport_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = uuid_pk()
    login: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    admin_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    admin: Mapped[AdminUser] = relationship()


class EulaAcceptance(Base):
    __tablename__ = "eula_acceptances"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    eula_version: Mapped[str] = mapped_column(String(32))
    privacy_version: Mapped[str] = mapped_column(String(32))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    type_code: Mapped[str] = mapped_column(String(32), index=True)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    accuracy_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commune_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("communes.id"), nullable=True)
    axis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("road_axes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    trust: Mapped[float] = mapped_column(Numeric(4, 3), default=0.350)
    pos_votes: Mapped[int] = mapped_column(Integer, default=0)
    neg_votes: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    hidden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    commune: Mapped[Optional[Commune]] = relationship()
    axis: Mapped[Optional[RoadAxis]] = relationship()


class ReportVote(Base):
    __tablename__ = "report_votes"
    __table_args__ = (UniqueConstraint("report_id", "device_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id"), index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    value: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    changed_once: Mapped[bool] = mapped_column(Boolean, default=False)


class AbuseFlag(Base):
    __tablename__ = "abuse_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id"))
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    reason: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    __table_args__ = (UniqueConstraint("device_id", "commune_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    commune_id: Mapped[int] = mapped_column(Integer, ForeignKey("communes.id"))


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    day: Mapped[datetime] = mapped_column(Date, primary_key=True)
    dau: Mapped[int] = mapped_column(Integer, default=0)
    new_devices: Mapped[int] = mapped_column(Integer, default=0)
    new_phones: Mapped[int] = mapped_column(Integer, default=0)
    reports: Mapped[int] = mapped_column(Integer, default=0)
    votes: Mapped[int] = mapped_column(Integer, default=0)
    dau_by_commune: Mapped[dict] = mapped_column(JSONB, default=dict)
    peak_concurrent: Mapped[int] = mapped_column(Integer, default=0)
    retention_d7: Mapped[float] = mapped_column(Float, default=0.0)
    sessions_per_dau: Mapped[float] = mapped_column(Float, default=0.0)
    validated_reports: Mapped[int] = mapped_column(Integer, default=0)
    communes_active: Mapped[int] = mapped_column(Integer, default=0)
    dau_mau: Mapped[float] = mapped_column(Float, default=0.0)


class ViewportHit(Base):
    """Hits used to compute DAU / concurrent without storing GPS traces."""

    __tablename__ = "viewport_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BusinessThresholds(Base):
    __tablename__ = "business_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dau_min: Mapped[int] = mapped_column(Integer, default=5000)
    peak_concurrent_min: Mapped[int] = mapped_column(Integer, default=800)
    retention_d7_min: Mapped[float] = mapped_column(Float, default=0.25)
    validated_reports_per_day_min: Mapped[int] = mapped_column(Integer, default=200)
    communes_active_min: Mapped[int] = mapped_column(Integer, default=8)
    sessions_per_dau_min: Mapped[float] = mapped_column(Float, default=2.0)
    dau_mau_min: Mapped[float] = mapped_column(Float, default=0.35)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeatureFlags(Base):
    __tablename__ = "feature_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monetization_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    push_majors_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(32))
    msisdn: Mapped[str] = mapped_column(String(20))
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    external_ref: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id"))
    provider_event_id: Mapped[str] = mapped_column(String(80), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    type: Mapped[str] = mapped_column(String(32))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = uuid_pk()
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    before: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
