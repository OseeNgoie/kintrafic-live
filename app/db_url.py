"""Normalize hoster DATABASE_URL values for SQLAlchemy + psycopg3."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def sqlalchemy_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ValueError("DATABASE_URL is empty")

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]

    scheme, sep, rest = url.partition("://")
    if not sep:
        return url

    if scheme in {"postgresql", "postgres"}:
        scheme = "postgresql+psycopg"
    elif scheme == "postgresql+psycopg2":
        scheme = "postgresql+psycopg"

    return f"{scheme}://{rest}"


def with_connect_timeout(url: str, seconds: int = 8) -> str:
    """Add a connect timeout so a missing host fails fast between retries."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("connect_timeout", str(seconds))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
