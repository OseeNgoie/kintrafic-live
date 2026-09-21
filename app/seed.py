from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from geoalchemy2 import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.geo_data import COMMUNES, ROAD_AXES, box_wkt
from app.models import (
    AdminUser,
    BusinessThresholds,
    Commune,
    Device,
    FeatureFlags,
    Report,
    RoadAxis,
    UsageDaily,
    User,
)
from app.security import hash_password, totp_secret, utcnow
from app.trust import REPORT_TYPES


def ensure_schema(db: Session) -> None:
    db.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    db.commit()


def seed_geo(db: Session) -> None:
    if not db.scalar(select(func.count()).select_from(Commune)):
        for name, slug, prio, w, s, e, n in COMMUNES:
            db.add(
                Commune(
                    name=name,
                    slug=slug,
                    priority=prio,
                    geom=WKTElement(box_wkt(w, s, e, n), srid=4326),
                )
            )
    for name, wkt in ROAD_AXES:
        existing = db.scalar(select(RoadAxis).where(RoadAxis.name == name))
        geom = WKTElement(wkt, srid=4326)
        if existing:
            existing.geom = geom
        else:
            db.add(RoadAxis(name=name, geom=geom))
    db.flush()


def seed_admin(db: Session) -> str | None:
    settings = get_settings()
    existing = db.scalar(select(AdminUser).where(AdminUser.login == settings.admin_login))
    secret = totp_secret()
    if existing:
        existing.password_hash = hash_password(settings.admin_password)
        if not existing.totp_secret:
            existing.totp_secret = secret
        return existing.totp_secret
    admin = AdminUser(
        login=settings.admin_login,
        password_hash=hash_password(settings.admin_password),
        totp_secret=secret,
        is_active=True,
    )
    db.add(admin)
    return secret


def seed_flags(db: Session) -> None:
    if not db.get(FeatureFlags, 1):
        db.add(FeatureFlags(id=1, monetization_enabled=False, push_majors_enabled=True))
    if not db.get(BusinessThresholds, 1):
        db.add(
            BusinessThresholds(
                id=1,
                dau_min=5000,
                peak_concurrent_min=800,
                retention_d7_min=0.25,
                validated_reports_per_day_min=200,
                communes_active_min=8,
                sessions_per_dau_min=2.0,
                dau_mau_min=0.35,
            )
        )


def seed_demo(db: Session) -> None:
    settings = get_settings()
    if not settings.seed_demo:
        return
    now = utcnow()
    if db.scalar(select(func.count()).select_from(Report).where(Report.status == "active")):
        _ensure_condition_demos(db, now)
        return

    demo_device = Device(platform="other", trust_score=Decimal("0.620"), last_seen_at=now)
    db.add(demo_device)
    db.flush()

    points = [
        ("congestion", 15.313, -4.305, "Boulevard du 30 Juin"),
        ("breakdown_heavy", 15.350, -4.350, "Boulevard Lumumba"),
        ("flood", 15.375, -4.370, "Route de Kingasani / Masina"),
        ("checkpoint", 15.292, -4.310, "Boulevard du 30 Juin"),
        ("accident", 15.345, -4.380, "Pont Matete / échangeurs Limete"),
        ("congestion", 15.240, -4.350, "Route de Matadi"),
        ("flood", 15.318, -4.400, "Avenue de l’Université"),
        ("breakdown_heavy", 15.380, -4.400, "Avenue By-Pass / aéroport Ndjili"),
        ("pothole", 15.300, -4.350, "Avenue Kasa-Vubu"),
        ("travaux", 15.275, -4.318, "Boulevard Colonel Tshatshi"),
        ("pothole", 15.265, -4.425, "Route de Kimwenza"),
    ]
    for type_code, lng, lat, axis_name in points:
        axis = db.scalar(select(RoadAxis).where(RoadAxis.name == axis_name))
        commune_id = db.scalar(
            select(Commune.id).where(
                func.ST_Contains(Commune.geom, func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326))
            )
        )
        ttl = REPORT_TYPES[type_code]["ttl_min"]
        db.add(
            Report(
                device_id=demo_device.id,
                type_code=type_code,
                geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
                accuracy_m=25,
                commune_id=commune_id,
                axis_id=axis.id if axis else None,
                status="active",
                trust=Decimal("0.580"),
                pos_votes=3,
                neg_votes=0,
                expires_at=now + timedelta(minutes=ttl),
            )
        )

    _ensure_condition_demos(db, now)

    # Historical metrics so admin is not empty (below critical-mass defaults).
    for i in range(14):
        day = date.today() - timedelta(days=13 - i)
        db.merge(
            UsageDaily(
                day=day,
                dau=420 + i * 18,
                new_devices=40 + i,
                new_phones=8 + i // 2,
                reports=90 + i * 3,
                votes=140 + i * 4,
                dau_by_commune={"Gombe": 80, "Limete": 55, "Ngaliema": 40, "Ndjili": 30},
                peak_concurrent=90 + i * 4,
                retention_d7=0.18 + i * 0.004,
                sessions_per_dau=1.6 + i * 0.02,
                validated_reports=40 + i * 2,
                communes_active=6,
                dau_mau=0.22 + i * 0.004,
            )
        )

    # Extra devices for today's DAU-ish last_seen
    for _ in range(12):
        db.add(Device(platform="android_chrome", last_seen_at=now, trust_score=Decimal("0.500")))


def _ensure_condition_demos(db: Session, now) -> None:
    extra = [
        ("pothole", 15.300, -4.350, "Avenue Kasa-Vubu"),
        ("travaux", 15.275, -4.318, "Boulevard Colonel Tshatshi"),
        ("pothole", 15.265, -4.425, "Route de Kimwenza"),
    ]
    device = db.scalar(select(Device).limit(1))
    if not device:
        device = Device(platform="other", trust_score=Decimal("0.620"), last_seen_at=now)
        db.add(device)
        db.flush()
    for type_code, lng, lat, axis_name in extra:
        exists = db.scalar(
            select(func.count())
            .select_from(Report)
            .where(Report.type_code == type_code, Report.status == "active", Report.expires_at > now)
        )
        if exists:
            continue
        axis = db.scalar(select(RoadAxis).where(RoadAxis.name == axis_name))
        commune_id = db.scalar(
            select(Commune.id).where(
                func.ST_Contains(Commune.geom, func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326))
            )
        )
        ttl = REPORT_TYPES[type_code]["ttl_min"]
        db.add(
            Report(
                device_id=device.id,
                type_code=type_code,
                geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
                accuracy_m=25,
                commune_id=commune_id,
                axis_id=axis.id if axis else None,
                status="active",
                trust=Decimal("0.520"),
                pos_votes=2,
                neg_votes=0,
                expires_at=now + timedelta(minutes=ttl),
            )
        )


def bootstrap_data(db: Session) -> str | None:
    seed_geo(db)
    totp = seed_admin(db)
    seed_flags(db)
    seed_demo(db)
    db.commit()
    return totp
