"""Ingest public Kinshasa incident hints (OSM notes + optional RSS) as automatic reports.

Items are tagged « Source : Veille Automatique ». They are never user-verified.
If live feeds fail, a local sample cache is used — not Google live traffic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
from geoalchemy2 import WKTElement
from geoalchemy2.functions import ST_DistanceSphere, ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.baseline import kinshasa_now
from app.config import get_settings
from app.models import Commune, Device, Report, RoadAxis, VeilleRun
from app.security import utcnow
from app.trust import REPORT_TYPES

log = logging.getLogger("kintrafic.veille")

SYSTEM_DEVICE_ID = UUID("00000000-0000-4000-a000-0000000000aa")
SAMPLE_PATH = Path(__file__).resolve().parent / "veille_sample.json"
SOURCE_TAG = "Source : Veille Automatique"
KEYWORDS = (
    (re.compile(r"\b(accident|collision|carambolage|heurt)\b", re.I), "accident"),
    (re.compile(r"\b(inondation|inondé|route coupée|pluie torrentielle)\b", re.I), "flood"),
    (re.compile(r"\b(travaux|chantier|déviation)\b", re.I), "travaux"),
    (re.compile(r"\b(nid.?de.?poule|nids.de.poule)\b", re.I), "pothole"),
    (re.compile(r"\b(panne|poids lourd|camion en panne|bus en panne)\b", re.I), "breakdown_heavy"),
    (re.compile(r"\b(barrage|roulage|contrôle police|checkpoint)\b", re.I), "checkpoint"),
    (re.compile(r"\b(embouteillage|bouchon|saturé|encombr|trafic dense|circulation dense)\b", re.I), "congestion"),
)


def classify_text(text: str, hint: str | None = None) -> str | None:
    if hint and hint in REPORT_TYPES:
        return hint
    blob = text or ""
    for rx, code in KEYWORDS:
        if rx.search(blob):
            return code
    return None


def ensure_system_device(db: Session) -> Device:
    device = db.get(Device, SYSTEM_DEVICE_ID)
    if device:
        return device
    device = Device(id=SYSTEM_DEVICE_ID, platform="veille", trust_score=0.250)
    db.add(device)
    db.flush()
    return device


def _headers() -> dict[str, str]:
    return {"User-Agent": get_settings().veille_user_agent, "Accept": "application/json, application/atom+xml, application/rss+xml, text/xml"}


def fetch_osm_notes(client: httpx.Client) -> list[dict]:
    s = get_settings()
    bbox = f"{s.kin_bbox_west},{s.kin_bbox_south},{s.kin_bbox_east},{s.kin_bbox_north}"
    url = f"https://api.openstreetmap.org/api/0.6/notes.json?bbox={bbox}&limit=40&closed=0"
    r = client.get(url, headers=_headers(), timeout=8.0)
    r.raise_for_status()
    data = r.json()
    out = []
    for feat in data.get("features") or []:
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        lng, lat = coords[0], coords[1]
        props = feat.get("properties") or {}
        comments = props.get("comments") or []
        text = " ".join(c.get("text") or "" for c in comments)
        nid = props.get("id") or feat.get("id")
        if lat is None or lng is None:
            continue
        out.append(
            {
                "external_key": f"osmnote:{nid}",
                "lat": float(lat),
                "lng": float(lng),
                "text": text,
                "feed": "osm_notes",
            }
        )
    return out


def fetch_rss(client: httpx.Client, url: str) -> list[dict]:
    r = client.get(url, headers=_headers(), timeout=8.0)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for node in list(root.iter()):
        tag = node.tag.split("}")[-1].lower()
        if tag not in {"item", "entry"}:
            continue
        title = ""
        summary = ""
        link = ""
        for child in list(node):
            ct = child.tag.split("}")[-1].lower()
            if ct == "title":
                title = (child.text or "").strip()
            elif ct in {"description", "summary", "content"}:
                summary = (child.text or "").strip()[:800]
            elif ct == "link":
                link = (child.get("href") or child.text or "").strip()
        text = f"{title} {summary}"
        if not classify_text(text):
            continue
        key = "rss:" + hashlib.sha256(f"{url}|{title}|{link}".encode()).hexdigest()[:24]
        items.append(
            {
                "external_key": key,
                "lat": None,
                "lng": None,
                "text": text,
                "feed": "rss",
                "axis_hint": title,
            }
        )
    return items


def load_sample() -> list[dict]:
    raw = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    out = []
    for row in raw:
        out.append(
            {
                "external_key": f"sample:{row['id']}",
                "lat": row["lat"],
                "lng": row["lng"],
                "text": row.get("text") or "",
                "type_hint": row.get("type_hint"),
                "feed": "sample_cache",
            }
        )
    return out


def snap_to_axis(db: Session, lng: float, lat: float, max_m: float) -> tuple[int | None, int | None]:
    pt = ST_SetSRID(ST_MakePoint(lng, lat), 4326)
    dist = ST_DistanceSphere(RoadAxis.geom, pt)
    axis = db.execute(select(RoadAxis.id, dist.label("d")).order_by(dist).limit(1)).first()
    axis_id = axis.id if axis and axis.d is not None and axis.d <= max_m else None
    commune_id = db.scalar(select(Commune.id).where(func.ST_Contains(Commune.geom, pt)))
    return axis_id, commune_id


def _axis_midpoint(db: Session, axis_id: int) -> tuple[float, float] | None:
    row = db.execute(
        select(
            func.ST_X(func.ST_Centroid(RoadAxis.geom)),
            func.ST_Y(func.ST_Centroid(RoadAxis.geom)),
        ).where(RoadAxis.id == axis_id)
    ).first()
    if not row or row[0] is None:
        return None
    return float(row[0]), float(row[1])


def guess_axis_from_text(db: Session, text: str) -> RoadAxis | None:
    axes = db.scalars(select(RoadAxis)).all()
    blob = (text or "").lower()
    for axis in axes:
        token = axis.name.split("/")[0].strip().lower()
        if len(token) >= 8 and token in blob:
            return axis
        short = token.replace("boulevard ", "bd ").replace("avenue ", "av ").replace("route ", "")
        if len(short) >= 8 and short in blob:
            return axis
    return None


def persist_item(db: Session, device: Device, item: dict) -> str:
    """Return inserted | skipped | ignored."""
    s = get_settings()
    existing = db.scalar(select(Report.id).where(Report.external_key == item["external_key"]))
    if existing:
        return "skipped"
    type_code = classify_text(item.get("text") or "", item.get("type_hint"))
    if not type_code:
        return "ignored"

    lng, lat = item.get("lng"), item.get("lat")
    if lng is None or lat is None:
        axis = guess_axis_from_text(db, item.get("text") or "")
        if not axis:
            return "ignored"
        mid = _axis_midpoint(db, axis.id)
        if not mid:
            return "ignored"
        lng, lat = mid[0], mid[1]
        axis_id, commune_id = axis.id, None
        commune_id = db.scalar(
            select(Commune.id).where(
                func.ST_Contains(Commune.geom, ST_SetSRID(ST_MakePoint(lng, lat), 4326))
            )
        )
    else:
        axis_id, commune_id = snap_to_axis(db, float(lng), float(lat), s.veille_snap_m)
        if axis_id is None:
            return "ignored"

    ttl = REPORT_TYPES[type_code]["ttl_min"]
    now = utcnow()
    db.add(
        Report(
            device_id=device.id,
            type_code=type_code,
            geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
            accuracy_m=80,
            commune_id=commune_id,
            axis_id=axis_id,
            status="active",
            trust=0.280,
            pos_votes=0,
            neg_votes=0,
            expires_at=now + timedelta(minutes=ttl),
            source="veille",
            external_key=item["external_key"],
        )
    )
    return "inserted"


def collect_live(client: httpx.Client) -> tuple[str, list[dict], list[str]]:
    settings = get_settings()
    items: list[dict] = []
    feed = "none"
    errors: list[str] = []
    if settings.veille_osm_notes:
        try:
            items.extend(fetch_osm_notes(client))
            feed = "osm_notes"
        except Exception as exc:  # network / 429 / parse
            errors.append(f"osm:{exc.__class__.__name__}")
            log.info("OSM notes unavailable: %s", exc)
    for url in [u.strip() for u in settings.veille_rss_urls.split(",") if u.strip()]:
        try:
            rss_items = fetch_rss(client, url)
            items.extend(rss_items)
            feed = "rss" if feed == "none" else f"{feed}+rss"
        except Exception as exc:
            errors.append(f"rss:{exc.__class__.__name__}")
            log.info("RSS unavailable %s: %s", url, exc)
    return feed, items, errors


def run_veille(db: Session, *, force_sample: bool = False) -> dict:
    settings = get_settings()
    if not settings.veille_enabled and not force_sample:
        return {"status": "disabled", "inserted": 0}

    run = VeilleRun(status="running", feed="none")
    db.add(run)
    db.flush()
    device = ensure_system_device(db)

    feed = "none"
    items: list[dict] = []
    errors: list[str] = []
    if not force_sample:
        try:
            with httpx.Client(follow_redirects=True) as client:
                feed, items, errors = collect_live(client)
        except Exception as exc:
            errors.append(str(exc.__class__.__name__))

    used_fallback = False
    if not items and settings.veille_fallback_sample:
        items = load_sample()
        feed = "sample_cache"
        used_fallback = True

    inserted = skipped = ignored = 0
    for item in items:
        result = persist_item(db, device, item)
        if result == "inserted":
            inserted += 1
        elif result == "skipped":
            skipped += 1
        else:
            ignored += 1

    run.finished_at = utcnow()
    run.status = "fallback" if used_fallback else ("ok" if not errors else "partial")
    run.feed = feed
    run.fetched = len(items)
    run.inserted = inserted
    run.skipped = skipped
    run.detail = {
        "ignored": ignored,
        "errors": errors,
        "fallback": used_fallback,
        "tag": SOURCE_TAG,
        "tz": "Africa/Kinshasa",
        "local": kinshasa_now().isoformat(),
        "note": "Veille automatique — pas un signalement usager, pas du trafic Google.",
    }
    db.commit()
    return {
        "status": run.status,
        "feed": feed,
        "fetched": len(items),
        "inserted": inserted,
        "skipped": skipped,
        "ignored": ignored,
        "errors": errors,
        "fallback": used_fallback,
    }


def maybe_run_veille(db: Session) -> dict | None:
    settings = get_settings()
    if not settings.veille_enabled:
        return None
    last = db.scalar(select(VeilleRun).order_by(VeilleRun.started_at.desc()).limit(1))
    now = utcnow()
    if last and last.started_at:
        started = last.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=now.tzinfo)
        elapsed = (now - started).total_seconds()
        if elapsed < max(settings.veille_interval_sec, settings.veille_min_interval_sec):
            return None
    return run_veille(db)


if __name__ == "__main__":
    from app.db import SessionLocal

    _db = SessionLocal()
    try:
        print(run_veille(_db))
    finally:
        _db.close()
