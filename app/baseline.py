"""Heuristic temporal traffic profiles for Kinshasa axes (Africa/Kinshasa).

Not live Google traffic. Default until a community report is active on the axis.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geo_data import MAJOR_AXIS_NAMES
from app.models import AxisTrafficProfile, RoadAxis

KINSHASA_TZ = ZoneInfo("Africa/Kinshasa")

CONGESTION_LABELS = {
    "fluide": "Fluide",
    "dense": "Dense",
    "sature": "Saturé",
}

# Axes that jam hardest on weekday peaks (in addition to the three named majors).
PEAK_SATURATE = MAJOR_AXIS_NAMES | {
    "Boulevard Lumumba",
    "Route de Matadi",
    "Pont Matete / échangeurs Limete",
    "Boulevard Triomphal / Sendwe",
}

PEAK_DENSE = {
    "Avenue de la Libération",
    "Avenue Victoire",
    "Avenue du Commerce / Gombe",
    "Route de Kingasani / Masina",
    "Avenue By-Pass / aéroport Ndjili",
    "Boulevard Colonel Tshatshi",
}


def kinshasa_now(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now(tz=KINSHASA_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=KINSHASA_TZ)
    else:
        now = now.astimezone(KINSHASA_TZ)
    return now


def _in_range(hour: int, start: int, end: int) -> bool:
    return start <= hour < end


def congestion_for(name: str, weekday: int, hour: int) -> str:
    """weekday: 0=Monday … 6=Sunday. hour: 0–23 local."""
    weekend = weekday >= 5
    major = name in PEAK_SATURATE
    arterial = name in PEAK_DENSE or major

    morning = _in_range(hour, 7, 9)
    evening = _in_range(hour, 17, 19)
    lunch = _in_range(hour, 12, 14)
    peak = morning or evening

    if weekend:
        if weekday == 5 and peak and major:
            return "dense"
        if weekday == 6 and _in_range(hour, 16, 19) and name == "Boulevard du 30 Juin":
            return "dense"
        if lunch and arterial:
            return "dense" if major else "fluide"
        return "fluide"

    if peak:
        if major:
            return "sature"
        if arterial:
            return "dense"
        return "dense"
    if lunch:
        if name in MAJOR_AXIS_NAMES:
            return "dense"
        return "fluide"
    if _in_range(hour, 6, 7) or _in_range(hour, 9, 10) or _in_range(hour, 16, 17) or _in_range(hour, 19, 20):
        return "dense" if major else "fluide"
    return "fluide"


def seed_traffic_profiles(db: Session) -> int:
    axes = db.scalars(select(RoadAxis)).all()
    n = 0
    for axis in axes:
        axis.is_major = axis.name in MAJOR_AXIS_NAMES
        for wd in range(7):
            for hour in range(24):
                code = congestion_for(axis.name, wd, hour)
                existing = db.scalar(
                    select(AxisTrafficProfile).where(
                        AxisTrafficProfile.axis_id == axis.id,
                        AxisTrafficProfile.weekday == wd,
                        AxisTrafficProfile.hour == hour,
                    )
                )
                if existing:
                    existing.congestion = code
                else:
                    db.add(
                        AxisTrafficProfile(
                            axis_id=axis.id,
                            weekday=wd,
                            hour=hour,
                            congestion=code,
                        )
                    )
                    n += 1
    db.flush()
    return n


def profile_lookup(db: Session, axis_id: int, when: datetime | None = None) -> str:
    local = kinshasa_now(when)
    row = db.scalar(
        select(AxisTrafficProfile).where(
            AxisTrafficProfile.axis_id == axis_id,
            AxisTrafficProfile.weekday == local.weekday(),
            AxisTrafficProfile.hour == local.hour,
        )
    )
    if row:
        return row.congestion
    return "fluide"
