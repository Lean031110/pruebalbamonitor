"""
Rutas web (HTML) para el dashboard en tiempo real + catálogo público.

Integrado en FastAPI con Jinja2Templates. Sin Flask, sin Node, sin React.

Flujo de auth por cookie:
  1. POST /web/login → verifica credenciales contra /api/auth/login (vía
     funciones internas de security.auth, sin HTTP roundtrip) → setea
     cookies HTTPOnly `session_token` (access) y `refresh_token`.
  2. GET /web/dashboard → lee cookie `session_token`, la decodifica.
     Si expiró, intenta refresh con `refresh_token`; si también expiró,
     redirige a /web/login.
  3. GET /web/logout → revoca access token (blacklist) y limpia cookies.

En modo dev (settings.security.require_auth=False) el dashboard es
accesible sin cookie, mostrando un usuario dummy "dev-admin".
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.config import get_settings
from lbamonitor.core.db import get_db
from lbamonitor.core.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    verify_credentials,
)
from lbamonitor.core.services.statistics_service import StatisticsService
from lbamonitor.core.repositories import (
    BillingRepository,
    CatalogRepository,
    InsertedDriveRepository,
)
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/web", tags=["web"])

# Templates apuntando a ./templates relativo a este archivo
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Cookie names
SESSION_COOKIE = "session_token"
REFRESH_COOKIE = "refresh_token"

# Cookie max-age (7 días, alineado con refresh_expiration_days)
_COOKIE_MAX_AGE = 7 * 24 * 60 * 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _business_name() -> str:
    """Nombre del negocio desde la configuración (BusinessSettings.name)."""
    try:
        return get_settings().business.name or "LBAMonitor"
    except Exception:
        return "LBAMonitor"


def _currency_symbol() -> str:
    try:
        return get_settings().business.currency_symbol or "₱"
    except Exception:
        return "₱"


def _json_safe(obj):
    """Convierte recursivamente datetimes a ISO strings para que Jinja tojson no falle."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _is_safe_url(target: str, request: Request) -> bool:
    """Valida que target sea una URL relativa (previene open redirect)."""
    if not target:
        return False
    if not target.startswith("/") or target.startswith("//"):
        return False
    return True


async def _resolve_user_from_cookies(
    request: Request,
    db: AsyncSession,
) -> tuple[str | None, str | None, str | None]:
    """
    Devuelve (username, role, fresh_access_token_or_None) leyendo las cookies.

    - Si `session_token` es válido → (sub, role, None)
    - Si `session_token` expiró y `refresh_token` es válido → (sub, role, new_access)
    - Si ninguno válido → (None, None, None)

    El tercer valor permite al caller refrescar la cookie `session_token`
    cuando se ha rotado.
    """
    s = get_settings().security

    # Modo dev: bypass
    if not s.require_auth:
        return ("dev-admin", "admin", None)

    access = request.cookies.get(SESSION_COOKIE)
    refresh = request.cookies.get(REFRESH_COOKIE)

    if access:
        td = decode_token(access)
        if td and td.token_type == "access":
            return (td.sub, td.role, None)

    # Intentar refresh
    if refresh:
        td = decode_token(refresh)
        if td and td.token_type == "refresh":
            new_access = create_access_token(td.sub, td.role)
            new_refresh = create_refresh_token(td.sub, td.role)
            # Devolver también el nuevo refresh para que el caller actualice ambas cookies
            return (td.sub, td.role, new_access)

    return (None, None, None)


def _set_session_cookies(response: RedirectResponse, access: str, refresh: str) -> None:
    """Setea cookies HTTPOnly con SameSite=Lax."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=access,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # True en producción con HTTPS (configurable)
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _clear_session_cookies(response: RedirectResponse) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    response.delete_cookie(key=REFRESH_COOKIE, path="/")


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def catalog_public(
    request: Request,
    db: AsyncSession = Depends(get_db),
    category: str | None = None,
    q: str | None = None,
    page: int = 1,
):
    """Catálogo público — sin auth. Llama al repositorio directamente."""
    page_size = 60
    if page < 1:
        page = 1

    repo = CatalogRepository(db)
    entries, total = await repo.list_filtered(
        category=category or None,
        active_only=True,
        query=q or None,
        page=page,
        page_size=page_size,
    )

    items = [
        {
            "id": e.id,
            "title": e.title,
            "category": e.category,
            "year": e.year,
            "genre": e.genre,
            "director": e.director,
            "artist": e.artist,
            "rating": e.rating,
            "size_gb": e.size_gb,
            "duration_minutes": e.duration_minutes,
            "times_copied": e.times_copied,
        }
        for e in entries
    ]

    return templates.TemplateResponse(
        "catalog.html",
        {
            "request": request,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "category": category or "",
            "q": q or "",
            "business_name": _business_name(),
            "active_nav": "catalog",
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    next: str | None = None,
    error: str | None = None,
):
    """Formulario de login. Si ya hay cookie válida, redirige a dashboard."""
    # Si require_auth=False, skip login
    s = get_settings().security
    if not s.require_auth:
        return RedirectResponse(url="/web/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": error,
            "next": next or "",
            "business_name": _business_name(),
            "active_nav": "login",
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Procesa login. Setea cookies y redirige a /web/dashboard si OK."""
    user = await verify_credentials(db, username, password)
    if not user:
        log.warning(f"Login web fallido para username={username!r}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Usuario o contraseña incorrectos",
                "next": next,
                "business_name": _business_name(),
                "active_nav": "login",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    access = create_access_token(user.username, user.role)
    refresh = create_refresh_token(user.username, user.role)
    log.info(f"Login web OK: username={user.username!r} role={user.role!r}")

    # Validar next_url (prevenir open redirect)
    target = "/web/dashboard"
    if next and _is_safe_url(next, request):
        target = next

    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookies(response, access, refresh)
    return response


@router.get("/logout")
async def logout(request: Request):
    """Logout: revoca access token (blacklist) y limpia cookies."""
    access = request.cookies.get(SESSION_COOKIE)
    if access:
        td = decode_token(access)
        if td and td.jti:
            try:
                revoke_token(td.jti, td.exp)
            except Exception:
                pass
    response = RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    _clear_session_cookies(response)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Dashboard tiempo real. Requiere cookie de sesión válida."""
    username, role, refreshed_access = await _resolve_user_from_cookies(request, db)

    if username is None:
        return RedirectResponse(url="/web/login?next=/web/dashboard", status_code=303)

    # Pre-fetch datos iniciales para renderizado server-side.
    # El JS hará refresh en tiempo real vía WebSocket + /api/statistics.
    svc = StatisticsService(db)
    try:
        today_kpis = await svc.today_kpis()
    except Exception as e:
        log.warning(f"No se pudieron cargar KPIs hoy: {e}")
        today_kpis = {}

    try:
        insights = await svc.business_insights()
    except Exception as e:
        log.warning(f"No se pudieron cargar insights: {e}")
        insights = {}

    try:
        repo = InsertedDriveRepository(db)
        active_drives_raw = await repo.get_active()
        active_drives = [
            {
                "id": d.id,
                "name": d.name or "—",
                "model": d.model or "—",
                "serial": (d.serial_number or "")[:16],
                "space_gb": round((d.space_bytes or 0) / (1024**3), 2),
                "available_gb": round((d.available_space_bytes or 0) / (1024**3), 2),
                "payment": d.payment or 0,
                "inserted_at": d.insertion_date_time.isoformat() if d.insertion_date_time else None,
            }
            for d in active_drives_raw
        ]
    except Exception as e:
        log.warning(f"No se pudieron cargar USBs activos: {e}")
        active_drives = []

    try:
        billing_repo = BillingRepository(db)
        recent_billings_raw, _ = await billing_repo.list_in_range(
            page=1, page_size=10
        )
        recent_billings = [
            {
                "id": b.id,
                "session_id": b.session_id,
                "charged": b.charged or 0,
                "total": b.total or 0,
                "discount_amount": b.discount_amount or 0,
                "not_charged": b.not_charged,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "created_by": b.created_by or "—",
            }
            for b in recent_billings_raw
        ]
    except Exception as e:
        log.warning(f"No se pudieron cargar cobros recientes: {e}")
        recent_billings = []

    # revenue_by_day (últimos 7) para gráfico SVG/Canvas inicial
    try:
        revenue_by_day = await svc.revenue_by_day(days=7)
    except Exception:
        revenue_by_day = []

    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "username": username,
            "role": role or "viewer",
            "business_name": _business_name(),
            "currency_symbol": _currency_symbol(),
            "active_nav": "dashboard",
            "initial_kpis": _json_safe(today_kpis),
            "initial_insights": _json_safe(insights),
            "initial_active_drives": _json_safe(active_drives),
            "initial_recent_billings": _json_safe(recent_billings),
            "initial_revenue_by_day": _json_safe(revenue_by_day),
            "ws_url": f"ws://{request.url.hostname or '127.0.0.1'}:{request.url.port or 8123}/ws/events",
        },
    )

    # Si el access token fue refrescado, setear la nueva cookie
    if refreshed_access:
        response.set_cookie(
            key=SESSION_COOKIE,
            value=refreshed_access,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )

    return response
