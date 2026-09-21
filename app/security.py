from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime, timezone
from typing import Optional

import argon2
import pyotp

from app.config import get_settings

ph = argon2.PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(hash_: str, password: str) -> bool:
    try:
        return ph.verify(hash_, password)
    except argon2.exceptions.VerifyMismatchError:
        return False


def new_token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def ip_hash(ip: Optional[str]) -> str:
    settings = get_settings()
    day = date.today().isoformat()
    raw = f"{day}:{ip or 'unknown'}"
    return hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]


def totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: Optional[str], code: Optional[str]) -> bool:
    settings = get_settings()
    if not settings.admin_totp_required:
        return True
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def detect_platform(ua: Optional[str]) -> str:
    ua = (ua or "").lower()
    if "android" in ua and "chrome" in ua:
        return "android_chrome"
    if "iphone" in ua or "ipad" in ua:
        return "ios_safari"
    return "other"
