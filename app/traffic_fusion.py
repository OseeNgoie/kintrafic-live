"""Hybrid fusion: community report > veille auto > hourly baseline > Fluide."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from app.baseline import CONGESTION_LABELS, kinshasa_now
from app.trust import REPORT_TYPES

TRAFFIC_TYPES = {"congestion", "breakdown_heavy", "accident", "checkpoint", "flood"}

SRC_LABELS = {
    "user": "Signalement usager",
    "veille": "Veille automatique",
    "base": "Profil horaire (prévision)",
}

SEVERITY = {"fluide": 0, "dense": 1, "sature": 2}


def congestion_from_type(type_code: str) -> str | None:
    if type_code in {"congestion", "accident", "flood"}:
        return "sature"
    if type_code in {"breakdown_heavy", "checkpoint"}:
        return "dense"
    return None


def _best_traffic(rows: Iterable[dict], source: str) -> dict | None:
    best = None
    best_rank = -1
    for r in rows:
        if r.get("source", "community") != source:
            continue
        if r.get("type_code") not in TRAFFIC_TYPES:
            continue
        code = congestion_from_type(r["type_code"])
        if not code:
            continue
        rank = SEVERITY[code]
        trust = float(r.get("trust") or 0)
        if rank > best_rank or (rank == best_rank and trust > float((best or {}).get("trust") or 0)):
            best = {**r, "congestion": code}
            best_rank = rank
    return best


def fuse_axis(
    *,
    axis_id: int,
    axis_name: str,
    reports: list[dict],
    baseline: str,
    now: datetime | None = None,
) -> dict:
    """reports: type_code, source, trust, expires_at optional."""
    local = kinshasa_now(now)
    base = baseline if baseline in CONGESTION_LABELS else "fluide"

    community = _best_traffic(reports, "community")
    veille = _best_traffic(reports, "veille")

    if community:
        code = community["congestion"]
        src = "user"
        ttl = _ttl_seconds(community.get("expires_at"), local)
        type_code = community.get("type_code")
    elif veille:
        code = veille["congestion"]
        src = "veille"
        ttl = _ttl_seconds(veille.get("expires_at"), local)
        type_code = veille.get("type_code")
    else:
        code = base
        src = "base"
        ttl = int((60 - local.minute) * 60 - local.second)
        type_code = None

    meta = REPORT_TYPES.get(type_code or "", {})
    return {
        "axis_id": axis_id,
        "name": axis_name,
        "c": code,
        "l": CONGESTION_LABELS[code],
        "s": src,
        "sl": SRC_LABELS[src],
        "x": ttl,
        "type_code": type_code,
        "type_label": meta.get("label"),
        "verified": bool(community and float(community.get("trust") or 0) >= 0.55 and int(community.get("pos") or 0) >= 2),
        "baseline": base,
        "baseline_label": CONGESTION_LABELS[base],
    }


def _ttl_seconds(expires_at, now: datetime) -> int | None:
    if expires_at is None:
        return None
    if getattr(expires_at, "tzinfo", None) is None:
        exp = expires_at.replace(tzinfo=now.tzinfo)
    else:
        exp = expires_at
    return max(0, int((exp - now).total_seconds()))


def city_summary(axes: list[dict]) -> dict:
    n = {"s": 0, "d": 0, "f": 0}
    src = {"user": 0, "veille": 0, "base": 0}
    for a in axes:
        if a["c"] == "sature":
            n["s"] += 1
        elif a["c"] == "dense":
            n["d"] += 1
        else:
            n["f"] += 1
        src[a["s"]] = src.get(a["s"], 0) + 1
    if n["s"] >= 3:
        code = "sature"
    elif n["s"] >= 1 or n["d"] >= 4:
        code = "dense"
    else:
        code = "fluide"
    return {"c": code, "l": CONGESTION_LABELS[code], "n": n, "src": src}


def compact_axis(fused: dict) -> dict:
    row = {"i": fused["axis_id"], "n": fused["name"], "c": fused["c"], "s": fused["s"]}
    if fused.get("x") is not None:
        row["x"] = fused["x"]
    return row
