from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import ADMIN_COOKIE, optional_session
from app.models import AdminSession, Commune, FeatureFlags, RoadAxis
from app.security import utcnow
from app.services import metrics as metrics_svc
from app.trust import REPORT_TYPES
from sqlalchemy import select

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _ctx(request: Request, **extra):
    s = get_settings()
    return {
        "request": request,
        "eula_version": s.eula_version,
        "privacy_version": s.privacy_version,
        "types": REPORT_TYPES,
        "default_lat": s.default_lat,
        "default_lng": s.default_lng,
        "bbox": [s.kin_bbox_west, s.kin_bbox_south, s.kin_bbox_east, s.kin_bbox_north],
        **extra,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("map.html", _ctx(request))


@router.get("/legal/cgu", response_class=HTMLResponse)
def cgu(request: Request):
    return templates.TemplateResponse("legal_cgu.html", _ctx(request))


@router.get("/legal/confidentialite", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse("legal_privacy.html", _ctx(request))


@router.get("/legal/refus", response_class=HTMLResponse)
def refus(request: Request):
    return templates.TemplateResponse("legal_refus.html", _ctx(request))


@router.get("/compte", response_class=HTMLResponse)
def compte(request: Request):
    return templates.TemplateResponse("compte.html", _ctx(request))


@router.get("/alertes", response_class=HTMLResponse)
def alertes(request: Request):
    return templates.TemplateResponse("alertes.html", _ctx(request))


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    s = get_settings()
    return templates.TemplateResponse(
        "admin_login.html",
        _ctx(request, totp_required=s.admin_totp_required),
    )


def _admin_ok(request: Request, db: Session) -> bool:
    raw = request.cookies.get(ADMIN_COOKIE)
    if not raw:
        return False
    from uuid import UUID

    try:
        sess = db.get(AdminSession, UUID(raw))
    except Exception:
        return False
    return bool(sess and sess.expires_at > utcnow())


@router.get("/admin/monitoring", response_class=HTMLResponse)
def admin_monitoring(request: Request, db: Session = Depends(get_db)):
    if not _admin_ok(request, db):
        return RedirectResponse("/admin/login", status_code=303)
    data = metrics_svc.compute_metrics(db)
    communes = db.scalars(select(Commune).order_by(Commune.name)).all()
    axes = db.scalars(select(RoadAxis).order_by(RoadAxis.name)).all()
    cmap = {c.id: c.name for c in communes}
    amap = {a.id: a.name for a in axes}
    return templates.TemplateResponse(
        "admin_monitoring.html",
        _ctx(request, metrics=data, cmap=cmap, amap=amap, nav="monitoring"),
    )


@router.get("/admin/moderation", response_class=HTMLResponse)
def admin_moderation(request: Request, db: Session = Depends(get_db)):
    if not _admin_ok(request, db):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("admin_moderation.html", _ctx(request, nav="moderation"))


@router.get("/admin/monetization", response_class=HTMLResponse)
def admin_monetization(request: Request, db: Session = Depends(get_db)):
    if not _admin_ok(request, db):
        return RedirectResponse("/admin/login", status_code=303)
    flags = db.get(FeatureFlags, 1)
    data = metrics_svc.compute_metrics(db)
    return templates.TemplateResponse(
        "admin_monetization.html",
        _ctx(request, nav="monetization", flags=flags, metrics=data),
    )


@router.get("/admin/payments", response_class=HTMLResponse)
def admin_payments(request: Request, db: Session = Depends(get_db)):
    if not _admin_ok(request, db):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("admin_payments.html", _ctx(request, nav="payments"))
