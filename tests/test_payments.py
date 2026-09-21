from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.payments import apply_webhook, grant_manual
from app.security import utcnow


class FakeDB:
    def __init__(self):
        self.events = {}
        self.subs = {}
        self.users = {}
        self.added = []

    def scalar(self, q):
        return None

    def get(self, model, id_):
        return self.users.get(id_)

    def add(self, obj):
        self.added.append(obj)


def test_webhook_success_sets_active(monkeypatch):
    from app.models import PaymentEvent, Subscription, User
    from app.services import payments as p

    user = User()
    user.id = "u1"
    user.is_premium = False
    sub = Subscription()
    sub.id = "s1"
    sub.user_id = "u1"
    sub.status = "pending"
    sub.external_ref = "KT-ABC"
    sub.current_period_end = None

    db = MagicMock()
    db.scalar.side_effect = [None, sub]  # no event, then sub by ref
    db.get.return_value = user

    out = p.apply_webhook(db, "mock", "evt-1", "success", {"external_ref": "KT-ABC"})
    assert out.status == "active"
    assert user.is_premium is True
    assert out.current_period_end is not None


def test_webhook_idempotent(monkeypatch):
    from app.services import payments as p
    from app.models import PaymentEvent, Subscription

    sub = Subscription()
    sub.status = "active"
    sub.external_ref = "KT-ABC"
    existing = PaymentEvent()
    db = MagicMock()
    db.scalar.side_effect = [existing, sub]
    out = p.apply_webhook(db, "mock", "evt-1", "success", {"external_ref": "KT-ABC"})
    assert out is sub
    db.add.assert_not_called()


def test_grant_manual():
    from app.services import payments as p
    from app.models import Subscription, User

    user = User()
    user.is_premium = False
    sub = Subscription()
    sub.user_id = "u"
    sub.status = "needs_review"
    db = MagicMock()
    db.get.return_value = user
    p.grant_manual(db, sub)
    assert sub.status == "active"
    assert user.is_premium is True
