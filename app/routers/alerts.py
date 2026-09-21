from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_session
from app.errors import ApiError
from app.models import AlertSubscription, FeatureFlags, PushSubscription, Report, User
from app.schemas import AlertCommunesIn
from app.security import utcnow
from app.trust import REPORT_TYPES

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alerts")
def alerts(pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    flags = db.get(FeatureFlags, 1)
    user = db.get(User, sess.user_id) if sess.user_id else None
    premium = bool(user and user.is_premium)
    gated = bool(flags and flags.monetization_enabled and not premium)
    now = utcnow()
    q = (
        select(Report)
        .where(Report.status == "active", Report.expires_at > now, Report.trust >= 0.6, Report.pos_votes >= 2)
        .order_by(Report.created_at.desc())
    )
    rows = db.scalars(q).all()
    majors = []
    for r in rows:
        meta = REPORT_TYPES.get(r.type_code, {})
        if not meta.get("major_push"):
            continue
        majors.append(
            {
                "id": str(r.id),
                "type_code": r.type_code,
                "label": meta.get("label"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    if gated:
        majors = majors[:3]
    return {"alerts": majors, "gated": gated, "max_communes": 10 if premium else 3}


@router.put("/alerts/communes")
def set_communes(body: AlertCommunesIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    flags = db.get(FeatureFlags, 1)
    user = db.get(User, sess.user_id) if sess.user_id else None
    premium = bool(user and user.is_premium)
    cap = 10 if (premium and flags and flags.monetization_enabled) else 3
    if len(body.commune_ids) > cap:
        raise ApiError(400, "too_many", f"Maximum {cap} communes suivies.")
    existing = db.scalars(select(AlertSubscription).where(AlertSubscription.device_id == device.id)).all()
    for e in existing:
        db.delete(e)
    for cid in body.commune_ids:
        db.add(AlertSubscription(device_id=device.id, commune_id=cid))
    return {"ok": True, "count": len(body.commune_ids)}


@router.post("/push/subscribe")
def push_sub(payload: dict, pair=Depends(require_session), db: Session = Depends(get_db)):
    _, device = pair
    db.add(
        PushSubscription(
            device_id=device.id,
            endpoint=payload.get("endpoint") or "",
            p256dh=(payload.get("keys") or {}).get("p256dh") or "",
            auth=(payload.get("keys") or {}).get("auth") or "",
        )
    )
    device.push_enabled = True
    return {"ok": True}


@router.delete("/push/subscribe")
def push_unsub(pair=Depends(require_session), db: Session = Depends(get_db)):
    _, device = pair
    device.push_enabled = False
    return {"ok": True}
