from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessThresholds, Device, FeatureFlags, Report, UsageDaily, User, ViewportHit
from app.security import utcnow

ALERT_TEXT = (
    "Seuil de masse critique atteint. Activation recommandée du module de monétisation. "
    "Ceci n’active rien. Va dans Monétisation et confirme avec le second facteur."
)
NEAR_TEXT = "Approche du seuil de masse critique (au moins 70 % des indicateurs). La monétisation reste éteinte."


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_metrics(db: Session) -> dict:
    today = date.today()
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    flags = db.get(FeatureFlags, 1)
    th = db.get(BusinessThresholds, 1)
    devices_total = db.scalar(select(func.count()).select_from(Device)) or 0
    phones = db.scalar(
        select(func.count()).select_from(User).where(User.phone_verified_at.is_not(None), User.deleted_at.is_(None))
    ) or 0
    dau = db.scalar(select(func.count(func.distinct(ViewportHit.device_id))).where(ViewportHit.ts >= start)) or 0
    window = utcnow() - timedelta(minutes=5)
    concurrent = (
        db.scalar(select(func.count(func.distinct(ViewportHit.device_id))).where(ViewportHit.ts >= window)) or 0
    )
    reports_today = (
        db.scalar(select(func.count()).select_from(Report).where(Report.created_at >= start, Report.status != "dup"))
        or 0
    )
    by_commune = db.execute(
        select(Report.commune_id, func.count())
        .where(Report.created_at >= start, Report.status != "dup")
        .group_by(Report.commune_id)
    ).all()
    by_axis = db.execute(
        select(Report.axis_id, func.count())
        .where(Report.created_at >= start, Report.status != "dup")
        .group_by(Report.axis_id)
    ).all()

    hist = db.scalars(select(UsageDaily).order_by(UsageDaily.day.desc()).limit(14)).all()
    peak_p50 = 0
    peaks = sorted([h.peak_concurrent for h in hist]) if hist else []
    if peaks:
        peak_p50 = peaks[len(peaks) // 2]
    ret_avg = _avg([h.retention_d7 for h in hist])
    val_avg = _avg([h.validated_reports for h in hist[:7]])
    dau_mau = hist[0].dau_mau if hist else 0.0
    sessions = hist[0].sessions_per_dau if hist else 0.0
    communes_active = hist[0].communes_active if hist else 0

    # Retention J7 from devices created 7 days ago if possible
    day7 = start - timedelta(days=7)
    day6_end = start
    created_j7 = db.scalar(
        select(func.count()).select_from(Device).where(Device.created_at >= day7, Device.created_at < day7 + timedelta(days=1))
    ) or 0
    returned = 0
    if created_j7:
        returned = (
            db.scalar(
                select(func.count(func.distinct(ViewportHit.device_id))).where(
                    ViewportHit.ts >= day7 + timedelta(days=1),
                    ViewportHit.ts < day6_end + timedelta(days=1),
                    ViewportHit.device_id.in_(
                        select(Device.id).where(
                            Device.created_at >= day7, Device.created_at < day7 + timedelta(days=1)
                        )
                    ),
                )
            )
            or 0
        )
    retention_live = (returned / created_j7) if created_j7 else ret_avg

    checks = {
        "dau_min": {"value": dau, "threshold": th.dau_min if th else 5000, "ok": dau >= (th.dau_min if th else 5000)},
        "peak_concurrent_min": {
            "value": peak_p50,
            "threshold": th.peak_concurrent_min if th else 800,
            "ok": peak_p50 >= (th.peak_concurrent_min if th else 800),
        },
        "retention_d7_min": {
            "value": round(retention_live, 3),
            "threshold": th.retention_d7_min if th else 0.25,
            "ok": retention_live >= (th.retention_d7_min if th else 0.25),
        },
        "validated_reports_per_day_min": {
            "value": round(val_avg, 1),
            "threshold": th.validated_reports_per_day_min if th else 200,
            "ok": val_avg >= (th.validated_reports_per_day_min if th else 200),
        },
        "communes_active_min": {
            "value": communes_active,
            "threshold": th.communes_active_min if th else 8,
            "ok": communes_active >= (th.communes_active_min if th else 8),
        },
        "sessions_per_dau_min": {
            "value": sessions,
            "threshold": th.sessions_per_dau_min if th else 2.0,
            "ok": sessions >= (th.sessions_per_dau_min if th else 2.0),
        },
        "dau_mau_min": {
            "value": dau_mau,
            "threshold": th.dau_mau_min if th else 0.35,
            "ok": dau_mau >= (th.dau_mau_min if th else 0.35),
        },
    }
    all_met = all(c["ok"] for c in checks.values())
    near = (sum(1 for c in checks.values() if c["ok"]) / len(checks)) >= 0.7
    # NEVER auto-enable
    return {
        "devices_total": devices_total,
        "phones_verified": phones,
        "dau": dau,
        "concurrent_approx": concurrent,
        "reports_today": reports_today,
        "reports_by_commune": [{"commune_id": c, "n": n} for c, n in by_commune],
        "reports_by_axis": [{"axis_id": a, "n": n} for a, n in by_axis],
        "retention_d7": round(retention_live, 3),
        "peak_concurrent_p50_14d": peak_p50,
        "monetization_enabled": bool(flags and flags.monetization_enabled),
        "all_met": all_met,
        "near_threshold": near and not all_met,
        "alert": ALERT_TEXT if all_met else (NEAR_TEXT if near else None),
        "alert_kind": "critical" if all_met else ("warn" if near else None),
        "checks": checks,
        "history": [
            {
                "day": h.day.isoformat(),
                "dau": h.dau,
                "peak": h.peak_concurrent,
                "reports": h.reports,
                "retention_d7": h.retention_d7,
            }
            for h in reversed(hist)
        ],
    }
