from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import PaymentEvent, Subscription, User
from app.security import utcnow


def sync_premium(db: Session, user: User) -> None:
    now = utcnow()
    active = db.scalar(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
            Subscription.current_period_end > now,
        )
    )
    if active:
        user.is_premium = True
        user.premium_until = active.current_period_end
    else:
        user.is_premium = False


def initiate(db: Session, user: User, provider: str, msisdn: str) -> Subscription:
    settings = get_settings()
    from app.models import FeatureFlags

    flags = db.get(FeatureFlags, 1)
    if not flags or not flags.monetization_enabled:
        raise ApiError(404, "monetization_off", "Le module payant n’est pas activé.")
    if not user.phone_e164:
        raise ApiError(400, "phone_required", "Un numéro vérifié est requis pour payer.")
    sub = Subscription(
        user_id=user.id,
        status="pending",
        provider=provider,
        msisdn=msisdn,
        external_ref=f"KT-{uuid4().hex[:12].upper()}",
    )
    db.add(sub)
    db.flush()
    if settings.mock_payments:
        # Leave pending: UI polls. Mock webhook can complete it.
        pass
    return sub


def apply_webhook(db: Session, provider: str, event_id: str, event_type: str, payload: dict) -> Subscription:
    existing = db.scalar(select(PaymentEvent).where(PaymentEvent.provider_event_id == event_id))
    ref = payload.get("external_ref")
    sub = db.scalar(select(Subscription).where(Subscription.external_ref == ref))
    if not sub:
        raise ApiError(404, "unknown_ref", "Référence de paiement inconnue.")
    if existing:
        return sub
    db.add(
        PaymentEvent(
            subscription_id=sub.id,
            provider_event_id=event_id,
            payload=payload,
            type=event_type,
        )
    )
    user = db.get(User, sub.user_id)
    if event_type == "success":
        sub.status = "active"
        sub.current_period_end = utcnow() + timedelta(days=get_settings().premium_days)
        if user:
            user.is_premium = True
            user.premium_until = sub.current_period_end
    elif event_type == "failure":
        sub.status = "failed"
        if user:
            sync_premium(db, user)
    elif event_type == "reversal":
        sub.status = "needs_review"
        if user:
            user.is_premium = False
    sub.updated_at = utcnow()
    return sub


def grant_manual(db: Session, sub: Subscription) -> None:
    sub.status = "active"
    sub.current_period_end = utcnow() + timedelta(days=get_settings().premium_days)
    user = db.get(User, sub.user_id)
    if user:
        user.is_premium = True
        user.premium_until = sub.current_period_end
