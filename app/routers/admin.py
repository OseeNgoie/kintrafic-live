from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import ADMIN_COOKIE, require_admin
from app.errors import ApiError
from app.models import (
    AdminAuditLog,
    AdminSession,
    AdminUser,
    Device,
    FeatureFlags,
    Report,
    Subscription,
)
from app.schemas import BanIn, GrantIn, MonetizationIn
from app.security import ip_hash, utcnow, verify_password, verify_totp
from app.services import metrics as metrics_svc
from app.services import payments as pay_svc

router = APIRouter(tags=["admin"])


def _audit(db: Session, admin_id, action: str, target_type=None, target_id=None, before=None, after=None, ip=None):
    db.add(
        AdminAuditLog(
            admin_user_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            before=before,
            after=after,
            ip_hash=ip_hash(ip),
        )
    )


@router.post("/admin/login")
def admin_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    totp: str = Form(""),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    admin = db.scalar(select(AdminUser).where(AdminUser.login == login))
    if not admin or not admin.is_active:
        raise ApiError(401, "bad_login", "Identifiants incorrects.")
    if admin.locked_until and admin.locked_until > utcnow():
        raise ApiError(423, "locked", "Compte temporairement verrouillé.")
    if not verify_password(admin.password_hash, password):
        admin.failed_logins += 1
        if admin.failed_logins >= 10:
            admin.locked_until = utcnow() + timedelta(minutes=15)
        raise ApiError(401, "bad_login", "Identifiants incorrects.")
    if not verify_totp(admin.totp_secret, totp):
        raise ApiError(401, "bad_totp", "Code TOTP invalide.")
    admin.failed_logins = 0
    sess = AdminSession(
        admin_user_id=admin.id,
        expires_at=utcnow() + timedelta(hours=8),
        last_seen_at=utcnow(),
        ip_hash=ip_hash(request.client.host if request.client else None),
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    db.add(sess)
    db.flush()
    _audit(db, admin.id, "login", ip=request.client.host if request.client else None)
    wants_json = "application/json" in (request.headers.get("accept") or "")
    if wants_json:
        out = JSONResponse({"ok": True})
    else:
        out = RedirectResponse("/admin/monitoring", status_code=303)
    out.set_cookie(ADMIN_COOKIE, str(sess.id), httponly=True, samesite="lax", path="/", max_age=8 * 3600)
    return out


@router.post("/admin/logout")
def admin_logout(pair=Depends(require_admin), db: Session = Depends(get_db)):
    sess, _ = pair
    db.delete(sess)
    out = RedirectResponse("/admin/login", status_code=303)
    out.delete_cookie(ADMIN_COOKIE, path="/")
    return out


@router.get("/api/v1/admin/metrics/now")
def metrics_now(pair=Depends(require_admin), db: Session = Depends(get_db)):
    return metrics_svc.compute_metrics(db)


@router.get("/api/v1/admin/metrics/dependency")
def metrics_dep(pair=Depends(require_admin), db: Session = Depends(get_db)):
    data = metrics_svc.compute_metrics(db)
    return {"all_met": data["all_met"], "checks": data["checks"], "alert": data["alert"], "alert_kind": data["alert_kind"]}


@router.get("/api/v1/admin/reports")
def admin_reports(pair=Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).order_by(Report.created_at.desc()).limit(100)).all()
    from app.models import AbuseFlag

    out = []
    for r in rows:
        flags_n = db.scalar(select(AbuseFlag).where(AbuseFlag.report_id == r.id).limit(1))
        out.append(
            {
                "id": str(r.id),
                "type_code": r.type_code,
                "status": r.status,
                "trust": float(r.trust),
                "pos": r.pos_votes,
                "neg": r.neg_votes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "hidden_reason": r.hidden_reason,
                "has_abuse": flags_n is not None,
                "commune_id": r.commune_id,
                "axis_id": r.axis_id,
            }
        )
    return {"reports": out}


@router.post("/api/v1/admin/reports/{report_id}/hide")
def hide_report(report_id: str, pair=Depends(require_admin), db: Session = Depends(get_db)):
    from uuid import UUID

    _, admin = pair
    r = db.get(Report, UUID(report_id))
    if not r:
        raise ApiError(404, "not_found", "Introuvable")
    before = {"status": r.status}
    r.status = "hidden"
    r.hidden_at = utcnow()
    r.hidden_reason = "admin"
    _audit(db, admin.id, "hide_report", "report", r.id, before, {"status": "hidden"})
    return {"ok": True}


@router.post("/api/v1/admin/reports/{report_id}/restore")
def restore_report(report_id: str, pair=Depends(require_admin), db: Session = Depends(get_db)):
    from uuid import UUID

    _, admin = pair
    r = db.get(Report, UUID(report_id))
    if not r:
        raise ApiError(404, "not_found", "Introuvable")
    r.status = "active"
    r.hidden_at = None
    r.hidden_reason = None
    _audit(db, admin.id, "restore_report", "report", r.id)
    return {"ok": True}


@router.post("/api/v1/admin/devices/{device_id}/ban")
def ban_device(device_id: str, body: BanIn, pair=Depends(require_admin), db: Session = Depends(get_db)):
    from uuid import UUID

    _, admin = pair
    if not verify_totp(admin.totp_secret, body.totp):
        raise ApiError(401, "bad_totp", "TOTP requis.")
    d = db.get(Device, UUID(device_id))
    if not d:
        raise ApiError(404, "not_found", "Appareil introuvable")
    d.banned_until = utcnow() + timedelta(hours=body.hours)
    _audit(db, admin.id, "ban_device", "device", d.id, after={"hours": body.hours})
    return {"ok": True, "banned_until": d.banned_until.isoformat()}


@router.get("/api/v1/admin/payments")
def payments(pair=Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Subscription).order_by(Subscription.created_at.desc()).limit(100)).all()
    return {
        "payments": [
            {
                "id": str(s.id),
                "status": s.status,
                "provider": s.provider,
                "msisdn": s.msisdn,
                "external_ref": s.external_ref,
                "period_end": s.current_period_end.isoformat() if s.current_period_end else None,
            }
            for s in rows
        ]
    }


@router.post("/api/v1/admin/payments/{sub_id}/grant")
def grant(sub_id: str, body: GrantIn, pair=Depends(require_admin), db: Session = Depends(get_db)):
    from uuid import UUID

    _, admin = pair
    if not verify_totp(admin.totp_secret, body.totp):
        raise ApiError(401, "bad_totp", "TOTP requis.")
    sub = db.get(Subscription, UUID(sub_id))
    if not sub:
        raise ApiError(404, "not_found", "Paiement introuvable")
    pay_svc.grant_manual(db, sub)
    _audit(db, admin.id, "grant_premium", "subscription", sub.id, after={"motif": body.motif})
    return {"ok": True}


@router.post("/api/v1/admin/flags/monetization")
def set_monetization(body: MonetizationIn, pair=Depends(require_admin), db: Session = Depends(get_db)):
    _, admin = pair
    if body.confirm != "CONFIRMER":
        raise ApiError(400, "confirm", "Saisis CONFIRMER pour basculer.")
    if not verify_totp(admin.totp_secret, body.totp):
        raise ApiError(401, "bad_totp", "TOTP requis.")
    flags = db.get(FeatureFlags, 1)
    before = {"monetization_enabled": flags.monetization_enabled}
    flags.monetization_enabled = body.enabled
    _audit(db, admin.id, "toggle_monetization", "flags", 1, before, {"monetization_enabled": body.enabled})
    return {"ok": True, "monetization_enabled": flags.monetization_enabled, "note": "Les signalements restent gratuits."}
