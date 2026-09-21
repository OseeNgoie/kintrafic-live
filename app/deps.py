from __future__ import annotations

from fastapi import Cookie, Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import AdminSession, AdminUser, Device, FeatureFlags, Session as UserSession
from app.security import utcnow

PUBLIC_COOKIE = "kt_session"
ADMIN_COOKIE = "kt_admin"


def optional_session(
    request: Request,
    db: Session = Depends(get_db),
    kt_session: str | None = Cookie(default=None),
) -> tuple[UserSession | None, Device | None]:
    if not kt_session:
        return None, None
    try:
        from uuid import UUID

        sid = UUID(kt_session)
    except ValueError:
        return None, None
    sess = db.get(UserSession, sid)
    if not sess or sess.expires_at < utcnow():
        return None, None
    device = db.get(Device, sess.device_id)
    request.state.session = sess
    request.state.device = device
    return sess, device


def require_session(
    pair: tuple = Depends(optional_session),
) -> tuple[UserSession, Device]:
    sess, device = pair
    if not sess or not device:
        raise ApiError(401, "auth_required", "Session requise. Accepte d’abord les CGU.")
    if device.banned_until and device.banned_until > utcnow():
        raise ApiError(403, "banned", "Ce appareil est temporairement bloqué.")
    return sess, device


def require_eula(pair: tuple = Depends(require_session), db: Session = Depends(get_db)):
    return pair


def flags(db: Session = Depends(get_db)) -> FeatureFlags:
    f = db.get(FeatureFlags, 1)
    if not f:
        f = FeatureFlags(id=1, monetization_enabled=False)
        db.add(f)
        db.flush()
    return f


def require_admin(
    request: Request,
    db: Session = Depends(get_db),
    kt_admin: str | None = Cookie(default=None),
) -> tuple[AdminSession, AdminUser]:
    if not kt_admin:
        raise ApiError(401, "admin_auth", "Connexion administrateur requise.")
    from uuid import UUID

    try:
        sid = UUID(kt_admin)
    except ValueError:
        raise ApiError(401, "admin_auth", "Session admin invalide.")
    sess = db.get(AdminSession, sid)
    if not sess or sess.expires_at < utcnow():
        raise ApiError(401, "admin_auth", "Session admin expirée.")
    idle = get_settings().admin_idle_minutes
    if (utcnow() - sess.last_seen_at).total_seconds() > idle * 60:
        raise ApiError(401, "admin_idle", "Session admin inactive.")
    admin = db.get(AdminUser, sess.admin_user_id)
    if not admin or not admin.is_active:
        raise ApiError(403, "admin_disabled", "Compte admin inactif.")
    sess.last_seen_at = utcnow()
    request.state.admin = admin
    return sess, admin
