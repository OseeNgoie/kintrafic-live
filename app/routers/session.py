from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import PUBLIC_COOKIE, optional_session, require_session
from app.errors import ApiError
from app.models import Device, EulaAcceptance, FeatureFlags, OtpChallenge, Session as UserSession, User
from app.rate_limit import limiter
from app.schemas import BootstrapIn, OtpRequestIn, OtpVerifyIn
from app.security import detect_platform, hash_password, ip_hash, new_token, utcnow, verify_password

router = APIRouter(prefix="/api/v1", tags=["session"])


@router.post("/session/bootstrap")
def bootstrap(
    body: BootstrapIn,
    request: Request,
    db: Session = Depends(get_db),
    pair=Depends(optional_session),
):
    settings = get_settings()
    if body.eula_version != settings.eula_version:
        raise ApiError(400, "eula_stale", "Version des CGU incorrecte. Recharge la page.")
    sess, device = pair
    ua = request.headers.get("user-agent")
    if not device:
        device = Device(platform=detect_platform(ua), last_seen_at=utcnow())
        db.add(device)
        db.flush()
    else:
        device.last_seen_at = utcnow()
        device.sessions_count = (device.sessions_count or 1) + 1
    if not sess:
        sess = UserSession(
            device_id=device.id,
            expires_at=utcnow() + timedelta(days=settings.session_days),
            csrf_token=new_token(16),
        )
        db.add(sess)
        db.flush()
    db.add(
        EulaAcceptance(
            device_id=device.id,
            eula_version=body.eula_version,
            privacy_version=body.privacy_version or settings.privacy_version,
            ip_hash=ip_hash(request.client.host if request.client else None),
            user_agent=(ua or "")[:255],
        )
    )
    flags = db.get(FeatureFlags, 1)
    resp = {
        "device_id": str(device.id),
        "csrf": sess.csrf_token,
        "monetization_enabled": bool(flags and flags.monetization_enabled),
    }
    from fastapi.responses import JSONResponse

    out = JSONResponse(resp)
    out.set_cookie(
        PUBLIC_COOKIE,
        str(sess.id),
        httponly=True,
        samesite="lax",
        max_age=settings.session_days * 86400,
        path="/",
    )
    return out


@router.get("/me")
def me(pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    settings = get_settings()
    flags = db.get(FeatureFlags, 1)
    user = db.get(User, sess.user_id) if sess.user_id else None
    prompt_push = device.sessions_count >= 3 and not device.push_enabled
    return {
        "device_id": str(device.id),
        "user_id": str(user.id) if user else None,
        "phone": user.phone_e164 if user else None,
        "is_premium": bool(user and user.is_premium),
        "premium_until": user.premium_until.isoformat() if user and user.premium_until else None,
        "monetization_enabled": bool(flags and flags.monetization_enabled),
        "eula_version": settings.eula_version,
        "sessions_count": device.sessions_count,
        "prompt_push": prompt_push,
        "trust_score": float(device.trust_score),
    }


@router.post("/session/logout")
def logout(pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, _ = pair
    db.delete(sess)
    from fastapi.responses import JSONResponse

    out = JSONResponse({"ok": True})
    out.delete_cookie(PUBLIC_COOKIE, path="/")
    return out


@router.delete("/me")
def delete_me(pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    if sess.user_id:
        user = db.get(User, sess.user_id)
        if user:
            user.deleted_at = utcnow()
            user.phone_e164 = None
            user.is_premium = False
    device.user_id = None
    from app.models import Report

    for r in db.scalars(select(Report).where(Report.device_id == device.id)).all():
        r.user_id = None
    return {"ok": True, "anonymized": True}


@router.post("/auth/otp/request")
def otp_request(body: OtpRequestIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    limiter.check(f"otp:{body.phone}", 3, 60)
    phone = body.phone.strip()
    if not phone.startswith("+243") or len(phone) < 12:
        raise ApiError(400, "bad_phone", "Numéro attendu au format +243…")
    code = "123456" if get_settings().mock_otp else f"{uuid4().int % 1000000:06d}"
    db.add(
        OtpChallenge(
            phone=phone,
            code_hash=hash_password(code),
            expires_at=utcnow() + timedelta(minutes=5),
        )
    )
    return {"ok": True, "mock": get_settings().mock_otp, "dev_code": code if get_settings().mock_otp else None}


@router.post("/auth/otp/verify")
def otp_verify(body: OtpVerifyIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    ch = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == body.phone, OtpChallenge.consumed_at.is_(None))
        .order_by(OtpChallenge.created_at.desc())
    )
    if not ch or ch.expires_at < utcnow():
        raise ApiError(400, "otp_expired", "Code expiré. Demande-en un autre.")
    if ch.attempts >= 3:
        raise ApiError(400, "otp_locked", "Trop d’essais.")
    ch.attempts += 1
    if not verify_password(ch.code_hash, body.code.strip()):
        raise ApiError(400, "otp_bad", "Code incorrect.")
    ch.consumed_at = utcnow()
    user = db.scalar(select(User).where(User.phone_e164 == body.phone))
    if not user:
        user = User(phone_e164=body.phone, phone_verified_at=utcnow())
        db.add(user)
        db.flush()
    else:
        user.phone_verified_at = utcnow()
        user.deleted_at = None
    device.user_id = user.id
    sess.user_id = user.id
    return {"ok": True, "user_id": str(user.id)}
