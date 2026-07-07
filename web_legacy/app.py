"""
LBAMonitor Web — Flask app para catálogo público + estadísticas.

v4.3: arregla
- secret_key hardcoded (ahora desde env var)
- open redirect en /login?next= (validación)
- columnas SQL inexistentes en catálogo (usar endpoint correcto /api/catalog)
- usa /api/auth/login (no /api/sessions)
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse, urljoin

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

BACKEND_URL = os.environ.get("LBAMONITOR_BACKEND_URL", "http://127.0.0.1:8123")

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
# secret_key desde env var (obligatorio en producción)
_secret = os.environ.get("LBAMONITOR_WEB_SECRET_KEY", "")
if not _secret:
    if os.environ.get("LBAMONITOR_ENV") == "production":
        raise RuntimeError(
            "LBAMONITOR_WEB_SECRET_KEY no configurado. Setear env var con secret aleatorio."
        )
    # Dev only
    _secret = "dev-only-web-secret-change-me"
app.secret_key = _secret


def _api_request(method: str, path: str, data: dict | None = None, token: str | None = None) -> dict:
    """Hace una request al backend FastAPI. Lanza urllib.error.HTTPError en errores."""
    url = f"{BACKEND_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Reenviar el error para que el caller lo maneje
        try:
            err_body = json.loads(e.read())
        except Exception:
            err_body = {"detail": str(e)}
        raise urllib.error.HTTPError(url, e.code, err_body.get("detail", "Error"), e.headers, None) from None


def _api_get(path: str, token: str | None = None) -> dict:
    return _api_request("GET", path, token=token)


def _api_post(path: str, data: dict, token: str | None = None) -> dict:
    return _api_request("POST", path, data=data, token=token)


def _is_safe_url(target: str) -> bool:
    """Valida que target es una URL relativa (previene open redirect)."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    # Solo permitir URLs en el mismo host, sin esquema externo
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


# --- Rutas ---

@app.route("/")
def catalog():
    """Catálogo público (sin login). Usa /api/catalog (endpoint real del backend)."""
    category = request.args.get("category", "")
    q = request.args.get("q", "")
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    params = {"page": page, "page_size": 50}
    if category:
        params["category"] = category
    if q:
        params["q"] = q

    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _api_get(f"/api/catalog?{qs}")
    except Exception:
        data = {"items": [], "pagination": {"total": 0}}

    pagination = data.get("pagination", {})
    return render_template(
        "catalog.html",
        items=data.get("items", []),
        total=pagination.get("total", 0),
        page=page,
        category=category,
        q=q,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login para admin. Usa /api/auth/login del backend v4.3."""
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        next_url = request.form.get("next", "") or request.args.get("next", "")

        try:
            result = _api_post("/api/auth/login", {"username": username, "password": password})
            if "access_token" in result:
                session["token"] = result["access_token"]
                session["refresh_token"] = result.get("refresh_token", "")
                session["user"] = result.get("username", "")
                session["role"] = result.get("role", "viewer")

                # Validar next_url (prevenir open redirect)
                if next_url and _is_safe_url(next_url):
                    return redirect(next_url)
                return redirect(url_for("stats"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                error = "Usuario o contraseña incorrectos"
            elif e.code == 429:
                error = "Demasiados intentos. Espere un minuto."
            else:
                error = f"Error del servidor ({e.code})"
        except Exception:
            error = "No se pudo conectar al backend"
        return render_template("login.html", error=error, next=next_url)

    next_url = request.args.get("next", "")
    return render_template("login.html", error=None, next=next_url)


@app.route("/logout")
def logout():
    # Intentar revocar el token en el backend
    token = session.get("token")
    if token:
        try:
            _api_post("/api/auth/logout", {"token": token})
        except Exception:
            pass
    session.clear()
    return redirect(url_for("catalog"))


@app.route("/stats")
def stats():
    """Estadísticas (requiere login). Usa /api/statistics del backend."""
    token = session.get("token")
    if not token:
        return redirect(url_for("login", next=url_for("stats")))

    try:
        data = _api_get("/api/statistics", token)
        today_kpis = data.get("today_kpis", {})
        insights = data.get("insights", {})
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return redirect(url_for("login", next=url_for("stats")))
        today_kpis = {}
        insights = {"error": f"Error {e.code}"}
    except Exception as e:
        today_kpis = {}
        insights = {"error": str(e)}

    return render_template(
        "stats.html",
        kpis=today_kpis,
        insights=insights,
        user=session.get("user", ""),
    )


@app.route("/closures")
def closures():
    """Cierres de caja históricos (requiere login). Usa /api/billings del backend."""
    token = session.get("token")
    if not token:
        return redirect(url_for("login", next=url_for("closures")))

    try:
        data = _api_get("/api/billings?page=1&page_size=50", token)
        items = data.get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return redirect(url_for("login", next=url_for("closures")))
        items = []
    except Exception:
        items = []

    return render_template("closures.html", items=items, user=session.get("user", ""))


def run_web(host: str = "0.0.0.0", port: int = 5000) -> None:
    """Arranca la web Flask."""
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web()
