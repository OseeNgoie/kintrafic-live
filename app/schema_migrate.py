"""Additive schema for autonomy on existing PostGIS databases (create_all + ALTER)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_autonomy_schema(db: Session) -> None:
    db.execute(text("ALTER TABLE road_axes ADD COLUMN IF NOT EXISTS is_major BOOLEAN DEFAULT FALSE"))
    db.execute(text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS source VARCHAR(16) DEFAULT 'community'"))
    db.execute(text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS external_key VARCHAR(160)"))
    db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_reports_external_key "
            "ON reports (external_key) WHERE external_key IS NOT NULL"
        )
    )
    db.execute(text("UPDATE reports SET source = 'community' WHERE source IS NULL"))
    db.commit()
