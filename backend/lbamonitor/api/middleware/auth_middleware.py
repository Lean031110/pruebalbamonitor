"""
Auth middleware para LBAMonitor v4.3.

Diseño:
- Verifica JWT en headers Authorization: Bearer <token>
- Setea request.state.current_user y request.state.current_role si el token es válido
- NO bloquea requests sin token (eso lo hacen los routers vía Depends(get_current_user))
- Solo aplica a rutas bajo /api/ que NO estén en public_paths
- Respeta configuración require_auth (si es False, no hace nada)

Diferencias con v4.2:
- Eliminado el fallback `nojwt:` (peligroso)
- Eliminado el path público incorrecto `/api/sessions` (era ServiceSession, no login)
- public_paths ahora viene de config (settings.security.public_paths)
"""
from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from lbamonitor.core.config import get_settings
from lbamonitor.core.security.auth import decode_token
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware que parsea el JWT del header Authorization y setea
    request.state.current_user / current_role.

    No bloquea requests (los routers lo hacen vía Depends(get_current_user)).
    Solo es informativo para logging y para que los routers puedan acceder
    al usuario sin re-decodificar el token.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        s = get_settings().security

        # Inicializar state
        request.state.current_user = None
        request.state.current_role = None

        if not s.require_auth:
            return await call_next(request)

        # Solo procesar rutas /api/
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        # Verificar si es ruta pública
        if any(path.startswith(p) for p in s.public_paths):
            return await call_next(request)

        # Intentar extraer y decodificar el token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            token_data = decode_token(token)
            if token_data:
                request.state.current_user = token_data.sub
                request.state.current_role = token_data.role

        return await call_next(request)
