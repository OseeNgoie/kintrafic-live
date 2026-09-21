from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.baseline import kinshasa_now, profile_lookup
from app.db import get_db
from app.models import Report, RoadAxis
from app.security import utcnow
from app.traffic_fusion import city_summary, compact_axis, fuse_axis
from app.veille import SOURCE_TAG

router = APIRouter(tags=["traffic"])


def fused_axes(db: Session) -> list[dict]:
    now = utcnow()
    axes = db.scalars(select(RoadAxis).order_by(RoadAxis.id)).all()
    reports = db.execute(
        select(Report).where(Report.status == "active", Report.expires_at > now)
    ).scalars().all()
    by_axis: dict[int, list] = {}
    for r in reports:
        if r.axis_id is None:
            continue
        by_axis.setdefault(r.axis_id, []).append(
            {
                "type_code": r.type_code,
                "source": r.source or "community",
                "trust": float(r.trust),
                "pos": r.pos_votes,
                "neg": r.neg_votes,
                "expires_at": r.expires_at,
            }
        )
    fused = []
    when = kinshasa_now(now)
    for axis in axes:
        baseline = profile_lookup(db, axis.id, when)
        fused.append(
            fuse_axis(
                axis_id=axis.id,
                axis_name=axis.name,
                reports=by_axis.get(axis.id, []),
                baseline=baseline,
                now=when,
            )
        )
    return fused


@router.get("/api/traffic/status-global")
def status_global(db: Session = Depends(get_db)):
    """Compact city traffic state: baseline + veille + community. Not Google live."""
    axes = fused_axes(db)
    city = city_summary(axes)
    when = kinshasa_now()
    return {
        "tz": "Africa/Kinshasa",
        "t": when.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "city": city,
        "axes": [compact_axis(a) for a in axes],
        "tag": SOURCE_TAG,
        "d": "fusion: usager>veille>profil horaire; pas Google",
    }
