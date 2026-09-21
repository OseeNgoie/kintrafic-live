from __future__ import annotations

import re
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings
from app.db_url import (
    database_name,
    with_connect_timeout,
    with_database_name,
)

_SAFE_DBNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAINT_DBS = ("postgres", "template1")


class Base(DeclarativeBase):
    pass


def configure_engine(url: str) -> None:
    global engine, SessionLocal
    engine = create_engine(
        with_connect_timeout(url),
        pool_pre_ping=True,
        pool_recycle=300,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _engine():
    settings = get_settings()
    return create_engine(
        with_connect_timeout(settings.database_url),
        pool_pre_ping=True,
        pool_recycle=300,
    )


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def is_missing_database(exc: BaseException) -> bool:
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        if code == "3D000":
            return True
        msg = str(cur).lower()
        if "does not exist" in msg and "database" in msg:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _ping() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _create_database(admin_url: str, name: str) -> None:
    if not _SAFE_DBNAME.match(name):
        raise ValueError(f"refusing to CREATE DATABASE with unsafe name {name!r}")
    admin = create_engine(
        with_connect_timeout(admin_url),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": name},
            ).scalar()
            if exists:
                print(f"kintrafic-live: database {name!r} already exists", flush=True)
                return
            conn.execute(text(f'CREATE DATABASE "{name}" ENCODING \'UTF8\''))
            print(f"kintrafic-live: created database {name!r}", flush=True)
    finally:
        admin.dispose()


def _ensure_target_database() -> None:
    """If DATABASE_URL's dbname is missing (Railway PostGIS often only has postgres), create it."""
    settings = get_settings()
    target_url = settings.database_url
    name = database_name(target_url)
    last_create: Exception | None = None
    for maint in _MAINT_DBS:
        if maint == name:
            continue
        admin_url = with_database_name(target_url, maint)
        try:
            _create_database(admin_url, name)
            return
        except Exception as exc:  # noqa: BLE001
            last_create = exc
            print(
                f"kintrafic-live: CREATE DATABASE {name!r} via {maint!r} failed: {exc}",
                flush=True,
            )
    if name != "postgres":
        fallback = with_database_name(target_url, "postgres")
        print(
            "kintrafic-live: CREATE DATABASE forbidden or failed; "
            f"falling back to dbname 'postgres' ({last_create})",
            flush=True,
        )
        settings.database_url = fallback
        configure_engine(fallback)


def wait_for_db(*, timeout_sec: float = 90.0, interval_sec: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: Exception | None = None
    created = False
    while time.monotonic() < deadline:
        try:
            _ping()
            print("kintrafic-live: database is ready", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            if is_missing_database(exc) and not created:
                print(
                    f"kintrafic-live: target database missing ({exc}); creating",
                    flush=True,
                )
                try:
                    _ensure_target_database()
                    created = True
                    _ping()
                    print("kintrafic-live: database is ready", flush=True)
                    return
                except Exception as create_exc:  # noqa: BLE001
                    last = create_exc
                    created = True
            left = max(0, int(deadline - time.monotonic()))
            print(
                f"kintrafic-live: waiting for database ({left}s left): {exc}",
                flush=True,
            )
            time.sleep(interval_sec)
    raise RuntimeError(f"database not ready after {timeout_sec:.0f}s: {last}") from last


def enable_postgis() -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        print("kintrafic-live: PostGIS extension ensured", flush=True)
        return
    except Exception as exc:  # noqa: BLE001
        with engine.connect() as conn:
            present = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
            ).scalar()
        if present:
            print(
                "kintrafic-live: CREATE EXTENSION denied, PostGIS already installed",
                flush=True,
            )
            return
        raise RuntimeError(
            "PostGIS is not installed. On Railway: Postgres plugin Online, "
            "then CREATE EXTENSION postgis (the app retries this at boot)."
        ) from exc
