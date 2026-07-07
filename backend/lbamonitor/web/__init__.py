"""
LBAMonitor Web — Dashboard de estadísticas en tiempo real + catálogo público.

Integrado en FastAPI mediante Jinja2Templates (sin Flask, sin Node.js, sin React).

Rutas:
  - GET  /web/             → Catálogo público (sin auth)
  - GET  /web/login        → Formulario de login
  - POST /web/login        → Procesa login (cookie HTTPOnly session_token)
  - GET  /web/dashboard    → Dashboard tiempo real (auth por cookie + WebSocket)
  - GET  /web/logout       → Limpia cookies y redirige a /web/login

Auth:
  - Login interno POST /api/auth/login
  - access_token guardado en cookie HTTPOnly `session_token`
  - refresh_token en cookie HTTPOnly `refresh_token`
  - Si access expira, se intenta refresh automático
"""
from __future__ import annotations

from lbamonitor.web.routes import router

__all__ = ["router"]
