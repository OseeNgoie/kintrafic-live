from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_session
from app.errors import ApiError
from app.models import FeatureFlags, Subscription, User
from app.schemas import BillingInitiateIn
from app.services import payments as pay_svc

router = APIRouter(prefix="/api/v1", tags=["billing"])


@router.get("/billing/quote")
def quote(db: Session = Depends(get_db)):
    flags = db.get(FeatureFlags, 1)
    if not flags or not flags.monetization_enabled:
        raise ApiError(404, "monetization_off", "Module payant désactivé.")
    s = get_settings()
    return {
        "price_cdf": s.premium_price_cdf,
        "days": s.premium_days,
        "operators": ["mpesa", "orange_money", "airtel_money"],
        "free_remains": ["carte", "signaler", "voter", "signalements actifs"],
        "premium": ["alertes élargies (10 communes)", "rafraîchissement 10 s", "badge priorité"],
    }


@router.post("/billing/initiate")
def initiate(body: BillingInitiateIn, pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, device = pair
    if not sess.user_id:
        raise ApiError(400, "phone_required", "Lie un numéro avant de payer.")
    user = db.get(User, sess.user_id)
    sub = pay_svc.initiate(db, user, body.provider, body.msisdn)
    return {
        "subscription_id": str(sub.id),
        "status": sub.status,
        "external_ref": sub.external_ref,
        "instructions": (
            f"Confirme le paiement {get_settings().premium_price_cdf} CDF via {body.provider} "
            f"sur {body.msisdn}. Référence {sub.external_ref}. L’onglet peut perdre le focus (USSD) : reviens ici."
        ),
        "poll_seconds": 5,
    }


@router.get("/billing/subscription")
def current(pair=Depends(require_session), db: Session = Depends(get_db)):
    sess, _ = pair
    if not sess.user_id:
        return {"status": "none"}
    sub = db.scalar(
        select(Subscription).where(Subscription.user_id == sess.user_id).order_by(Subscription.created_at.desc())
    )
    if not sub:
        return {"status": "none"}
    return {
        "status": sub.status,
        "provider": sub.provider,
        "external_ref": sub.external_ref,
        "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


@router.post("/webhooks/{provider}")
async def webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    event_id = payload.get("event_id") or payload.get("id")
    event_type = payload.get("type") or payload.get("status")
    if provider == "mock":
        secret = request.headers.get("x-mock-secret")
        if secret != get_settings().secret_key:
            raise ApiError(401, "bad_webhook", "Secret mock invalide.")
    if not event_id or not event_type:
        raise ApiError(400, "bad_payload", "event_id et type requis.")
    sub = pay_svc.apply_webhook(db, provider, str(event_id), event_type, payload)
    return {"ok": True, "status": sub.status, "idempotent": True}
