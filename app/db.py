from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import time

from app.config import get_settings
from app.db_url import with_connect_timeout


class Base(DeclarativeBase):
    pass


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


def wait_for_db(*, timeout_sec: float = 90.0, interval_sec: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("kintrafic-live: database is ready", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 — retry any connect/auth/DNS blip
            last = exc
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
