from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from geoalchemy2 import WKTElement
from geoalchemy2.functions import ST_AsGeoJSON, ST_Contains, ST_DistanceSphere, ST_DWithin, ST_MakePoint, ST_SetSRID, ST_X, ST_Y
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_session
from app.errors import ApiError
from app.models import AbuseFlag, Commune, Device, Report, ReportVote, RoadAxis, ViewportHit
from app.rate_limit import limiter
from app.schemas import AbuseIn, LocationIn, ReportCreate, VoteIn
from app.security import utcnow
from app.trust import REPORT_TYPES, device_weight, report_trust, should_auto_hide, trust_label

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _in_bbox(lng: float, lat: float) -> bool:
    s = get_settings()
    return s.kin_bbox_west <= lng <= s.kin_bbox_east and s.kin_bbox_south <= lat <= s.kin_bbox_north


@router.get("/geo/communes")
def communes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Commune).order_by(Commune.name)).all()
    return {
        "communes": [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "bbox": db.execute(
                    text(
                        "SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM communes WHERE id=:id"
                    ),
                    {"id": c.id},
                ).one(),
            }
            for c in rows
        ]
    }


@router.get("/geo/axes")
def axes(db: Session = Depends(get_db)):
    rows = db.scalars(select(RoadAxis).order_by(RoadAxis.name)).all()
    return {"axes": [{"id": a.id, "name": a.name} for a in rows]}


@router.get("/reports/viewport")
def viewport(
    bbox: str = Query(..., description="west,south,east,north"),
    pair=Depends(require_session),
    db: Session = Depends(get_db),
):
    sess, device = pair
    limiter.check(f"vp:{device.id}", 60, 60)
    device.last_seen_at = utcnow()
    sess.last_viewport_at = utcnow()
    db.add(ViewportHit(device_id=device.id))
    try:
        west, south, east, north = [float(x) for x in bbox.split(",")]
    except ValueError:
        raise ApiError(400, "bad_bbox", "bbox invalide")
    now = utcnow()
    env = func.ST_MakeEnvelope(west, south, east, north, 4326)
    q = (
        select(
            Report,
            func.ST_X(Report.geom).label("lng"),
            func.ST_Y(Report.geom).label("lat"),
        )
        .where(Report.status == "active", Report.expires_at > now, func.ST_Intersects(Report.geom, env))
        .order_by(Report.created_at.desc())
        .limit(80)
    )
    rows = db.execute(q).all()
    features = []
    for report, lng, lat in rows:
        meta = REPORT_TYPES.get(report.type_code, {})
        expired = report.expires_at <= now
        features.append(
            {
                "type": "Feature",
                "id": str(report.id),
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "type_code": report.type_code,
                    "label": meta.get("label", report.type_code),
                    "color": meta.get("color", "#333"),
                    "trust": float(report.trust),
                    "trust_label": trust_label(float(report.trust), report.pos_votes, report.neg_votes, expired),
                    "pos": report.pos_votes,
                    "neg": report.neg_votes,
                    "created_at": report.created_at.isoformat() if report.created_at else None,
                    "expires_at": report.expires_at.isoformat(),
                    "commune_id": report.commune_id,
                    "axis_id": report.axis_id,
                    "show_counts": (report.pos_votes + report.neg_votes) >= 3,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "server_time": now.isoformat(),
        "empty": len(features) == 0,
    }


@router.post("/reports")
def create_report(body: ReportCreate, pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    limiter.check(f"rep:{device.id}", 10, 60)
    if body.type_code not in REPORT_TYPES:
        raise ApiError(400, "bad_type", "Type de signalement inconnu.")
    if not _in_bbox(body.lng, body.lat):
        raise ApiError(400, "out_of_area", "Hors de la zone Kinshasa couverte.")
    now = utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)
    n_hour = db.scalar(
        select(func.count()).select_from(Report).where(Report.device_id == device.id, Report.created_at >= hour_ago)
    ) or 0
    n_day = db.scalar(
        select(func.count()).select_from(Report).where(Report.device_id == device.id, Report.created_at >= day_ago)
    ) or 0
    if n_hour >= 5:
        raise ApiError(429, "limit_hour", "Maximum 5 signalements par heure.")
    if n_day >= 15:
        raise ApiError(429, "limit_day", "Maximum 15 signalements par jour.")

    pt = func.ST_SetSRID(func.ST_MakePoint(body.lng, body.lat), 4326)
    dup = db.scalar(
        select(Report.id).where(
            Report.device_id == device.id,
            Report.type_code == body.type_code,
            Report.created_at >= now - timedelta(minutes=20),
            func.ST_DistanceSphere(Report.geom, pt) < 20,
        )
    )
    if dup:
        dup.status = "dup"
        raise ApiError(409, "duplicate", "Signalement identique trop proche. Attends un peu.")

    commune_id = db.scalar(select(Commune.id).where(func.ST_Contains(Commune.geom, pt)))
    dist = func.ST_DistanceSphere(RoadAxis.geom, pt)
    axis = db.execute(select(RoadAxis.id, dist.label("d")).order_by(dist).limit(1)).first()
    axis_id = axis.id if axis and axis.d is not None and axis.d <= 40 else None

    ttl = REPORT_TYPES[body.type_code]["ttl_min"]
    trust0 = 0.35
    if float(device.trust_score) < 0.20:
        trust0 = min(trust0, 0.4)
    report = Report(
        device_id=device.id,
        user_id=sess.user_id,
        type_code=body.type_code,
        geom=WKTElement(f"POINT({body.lng} {body.lat})", srid=4326),
        accuracy_m=body.accuracy,
        commune_id=commune_id,
        axis_id=axis_id,
        status="active",
        trust=trust0,
        expires_at=now + timedelta(minutes=ttl),
    )
    db.add(report)
    db.flush()
    return {"id": str(report.id), "expires_at": report.expires_at.isoformat(), "commune_id": commune_id, "axis_id": axis_id}


@router.get("/reports/{report_id}")
def get_report(report_id: str, pair=Depends(require_session), db: Session = Depends(get_db)):
    from uuid import UUID

    report = db.get(Report, UUID(report_id))
    if not report:
        raise ApiError(404, "not_found", "Signalement introuvable.")
    lng, lat = db.execute(select(func.ST_X(report.geom), func.ST_Y(report.geom))).one()
    commune = db.get(Commune, report.commune_id) if report.commune_id else None
    axis = db.get(RoadAxis, report.axis_id) if report.axis_id else None
    expired = report.status == "expired" or report.expires_at <= utcnow()
    meta = REPORT_TYPES.get(report.type_code, {})
    n = report.pos_votes + report.neg_votes
    return {
        "id": str(report.id),
        "type_code": report.type_code,
        "label": meta.get("label"),
        "lat": lat,
        "lng": lng,
        "trust": float(report.trust),
        "trust_label": trust_label(float(report.trust), report.pos_votes, report.neg_votes, expired),
        "pos": report.pos_votes if n >= 3 else None,
        "neg": report.neg_votes if n >= 3 else None,
        "counts_hidden": n < 3,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "expires_at": report.expires_at.isoformat(),
        "commune": commune.name if commune else None,
        "axis": axis.name if axis else None,
        "disclaimer": "Fait communautaire signalé ici. Ce n’est pas un conseil de circulation ni d’infraction.",
    }


@router.put("/reports/{report_id}/vote")
def vote(report_id: str, body: VoteIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    from uuid import UUID

    sess, device = pair
    limiter.check(f"vote:{device.id}", 30, 60)
    report = db.get(Report, UUID(report_id))
    if not report or report.status not in ("active",):
        raise ApiError(404, "not_found", "Signalement inactif.")
    existing = db.scalar(
        select(ReportVote).where(ReportVote.report_id == report.id, ReportVote.device_id == device.id)
    )
    if existing:
        if existing.changed_once:
            raise ApiError(409, "vote_locked", "Tu as déjà modifié ton vote.")
        if existing.value == body.value:
            return {"ok": True, "unchanged": True}
        if existing.value == 1:
            report.pos_votes = max(0, report.pos_votes - 1)
        else:
            report.neg_votes = max(0, report.neg_votes - 1)
        existing.value = body.value
        existing.changed_once = True
    else:
        db.add(ReportVote(report_id=report.id, device_id=device.id, value=body.value))
    if body.value == 1:
        report.pos_votes += 1
    else:
        report.neg_votes += 1

    votes = db.scalars(select(ReportVote).where(ReportVote.report_id == report.id)).all()
    weights = []
    for v in votes:
        voter = db.get(Device, v.device_id)
        age_h = 48.0
        if voter and voter.created_at:
            age_h = (utcnow() - voter.created_at.replace(tzinfo=voter.created_at.tzinfo)).total_seconds() / 3600
        weights.append(device_weight(float(voter.trust_score) if voter else 0.5, age_h))
    report.trust = report_trust(report.pos_votes, report.neg_votes, weights)
    if should_auto_hide(report.pos_votes, report.neg_votes):
        report.status = "hidden"
        report.hidden_at = utcnow()
        report.hidden_reason = "community"
    return {"ok": True, "trust": float(report.trust), "status": report.status}


@router.post("/reports/{report_id}/abuse")
def abuse(report_id: str, body: AbuseIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    from uuid import UUID

    _, device = pair
    report = db.get(Report, UUID(report_id))
    if not report:
        raise ApiError(404, "not_found", "Signalement introuvable.")
    db.add(AbuseFlag(report_id=report.id, device_id=device.id, reason=body.reason))
    return {"ok": True}


@router.post("/me/location")
def location(body: LocationIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    _, device = pair
    limiter.check(f"loc:{device.id}", 2, 30)
    if not _in_bbox(body.lng, body.lat):
        raise ApiError(400, "out_of_area", "Position hors Kinshasa.")
    device.last_point = WKTElement(f"POINT({body.lng} {body.lat})", srid=4326)
    device.last_point_at = utcnow()
    return {"ok": True}
